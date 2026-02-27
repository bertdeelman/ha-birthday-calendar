"""CardDAV client for fetching birthdays from contacts."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)


@dataclass
class Birthday:
    """Represents a birthday entry."""

    name: str
    birthday: date
    year_of_birth: Optional[int]  # None if year is unknown (--MM-DD format)


class CardDAVClient:
    """Async CardDAV client that fetches vCards and extracts birthdays."""

    def __init__(self, url: str, username: str, password: str, session: aiohttp.ClientSession) -> None:
        self._base_url = url.rstrip("/")
        self._username = username
        self._password = password
        self._session = session
        self._auth = aiohttp.BasicAuth(username, password)

    def _make_absolute(self, href: str, base: str) -> str:
        """Convert a relative href to an absolute URL."""
        if href.startswith("http"):
            return href
        parts = base.split("/")
        host = parts[0] + "//" + parts[2]
        return host + (href if href.startswith("/") else "/" + href.lstrip("/"))

    async def _discover_addressbook_home(self) -> str:
        """
        Discover the addressbook home URL.
        iCloud redirects /.well-known/carddav to the real home URL.
        """
        well_known = self._base_url + "/.well-known/carddav"
        _LOGGER.debug("Discovering addressbook home via %s", well_known)

        try:
            async with self._session.request(
                "PROPFIND",
                well_known,
                headers={"Content-Type": "application/xml; charset=utf-8", "Depth": "0"},
                auth=self._auth,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                _LOGGER.debug("Well-known response: %s", resp.status)
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "")
                    _LOGGER.debug("Redirect to: %s", location)
                    if location:
                        return await self._get_principal_home(self._make_absolute(location, self._base_url))
                elif resp.status == 207:
                    text = await resp.text()
                    home = self._extract_addressbook_home(text)
                    if home:
                        return self._make_absolute(home, self._base_url)
        except aiohttp.ClientError as err:
            _LOGGER.debug("Well-known request failed: %s", err)

        return await self._get_principal_home(self._base_url)

    async def _get_principal_home(self, url: str) -> str:
        """Get the addressbook-home-set from a principal URL."""
        propfind_body = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:current-user-principal/>
    <C:addressbook-home-set/>
  </D:prop>
</D:propfind>"""
        try:
            async with self._session.request(
                "PROPFIND",
                url,
                data=propfind_body,
                headers={"Content-Type": "application/xml; charset=utf-8", "Depth": "0"},
                auth=self._auth,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                _LOGGER.debug("Principal PROPFIND at %s -> %s", url, resp.status)
                if resp.status == 207:
                    text = await resp.text()
                    _LOGGER.debug("Principal response: %s", text[:2000])

                    home = self._extract_addressbook_home(text)
                    if home:
                        return self._make_absolute(home, url)

                    principal = self._extract_href_after(text, "current-user-principal")
                    if principal and principal != url:
                        return await self._get_principal_home(self._make_absolute(principal, url))
        except aiohttp.ClientError as err:
            _LOGGER.warning("Principal PROPFIND failed: %s", err)

        _LOGGER.warning("Could not discover addressbook home, falling back to: %s", url)
        return url

    def _extract_addressbook_home(self, xml_text: str) -> Optional[str]:
        """Extract addressbook-home-set href from PROPFIND response."""
        match = re.search(
            r"addressbook-home-set[^>]*>.*?<[^>]*href[^>]*>([^<]+)<",
            xml_text, re.DOTALL | re.IGNORECASE,
        )
        return match.group(1).strip() if match else None

    def _extract_href_after(self, xml_text: str, element: str) -> Optional[str]:
        """Extract href from inside a named element."""
        match = re.search(
            rf"{element}[^>]*>.*?<[^>]*href[^>]*>([^<]+)<",
            xml_text, re.DOTALL | re.IGNORECASE,
        )
        return match.group(1).strip() if match else None

    async def _find_addressbooks(self, home_url: str) -> list[str]:
        """Find all addressbook collections under the home set."""
        propfind_body = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:resourcetype/>
    <D:displayname/>
  </D:prop>
</D:propfind>"""
        try:
            async with self._session.request(
                "PROPFIND",
                home_url,
                data=propfind_body,
                headers={"Content-Type": "application/xml; charset=utf-8", "Depth": "1"},
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                _LOGGER.debug("Addressbooks PROPFIND at %s -> %s", home_url, resp.status)
                if resp.status != 207:
                    return [home_url]

                text = await resp.text()
                addressbooks = []
                responses = re.split(r"<[Dd]:response>", text)[1:]
                for response in responses:
                    if "addressbook" in response.lower():
                        href_match = re.search(r"<[Dd]:href>([^<]+)</[Dd]:href>", response)
                        if href_match:
                            ab_url = self._make_absolute(href_match.group(1).strip(), home_url)
                            if ab_url not in addressbooks:
                                addressbooks.append(ab_url)

                return addressbooks if addressbooks else [home_url]
        except aiohttp.ClientError as err:
            _LOGGER.warning("Addressbooks PROPFIND failed: %s", err)
            return [home_url]

    async def _fetch_all_vcards(self, addressbook_url: str) -> list[str]:
        """
        Fetch ALL vCards from an addressbook without server-side filtering.
        iCloud returns HTTP 400 for filtered REPORT queries, so we filter locally.
        """
        report_body = """<?xml version="1.0" encoding="utf-8"?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:getetag/>
    <C:address-data/>
  </D:prop>
</C:addressbook-query>"""
        try:
            async with self._session.request(
                "REPORT",
                addressbook_url,
                data=report_body,
                headers={"Content-Type": "application/xml; charset=utf-8", "Depth": "1"},
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                _LOGGER.debug("REPORT at %s -> %s", addressbook_url, resp.status)
                if resp.status == 207:
                    text = await resp.text()
                    vcards = re.findall(r"BEGIN:VCARD.*?END:VCARD", text, re.DOTALL)
                    _LOGGER.debug("Got %d vCards from %s", len(vcards), addressbook_url)
                    return vcards
                _LOGGER.warning("REPORT returned %s for %s", resp.status, addressbook_url)
                return []
        except aiohttp.ClientError as err:
            _LOGGER.warning("REPORT request failed: %s", err)
            return []

    def _parse_vcard(self, vcard_text: str) -> Optional[Birthday]:
        """Parse a vCard and return Birthday if BDAY is present."""
        fn_match = re.search(r"^FN[^:]*:(.+)$", vcard_text, re.MULTILINE)
        name = fn_match.group(1).strip() if fn_match else "Unknown"
        name = re.sub(r"\r?\n[ \t]", "", name)

        bday_match = re.search(r"^BDAY[^:]*:(.+)$", vcard_text, re.MULTILINE)
        if not bday_match:
            return None

        bday_str = bday_match.group(1).strip()
        if not bday_str or bday_str.lower() == "unknown":
            return None

        birthday, year_of_birth = self._parse_bday(bday_str)
        if birthday is None:
            return None

        return Birthday(name=name, birthday=birthday, year_of_birth=year_of_birth)

    def _parse_bday(self, bday_str: str) -> tuple[Optional[date], Optional[int]]:
        """Parse BDAY value in multiple formats."""
        # --MMDD or --MM-DD (no year)
        m = re.match(r"^--(\d{2})-?(\d{2})$", bday_str)
        if m:
            try:
                return date(2000, int(m.group(1)), int(m.group(2))), None
            except ValueError:
                return None, None

        # YYYY-MM-DD
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", bday_str)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), int(m.group(1))
            except ValueError:
                return None, None

        # YYYYMMDD
        m = re.match(r"^(\d{4})(\d{2})(\d{2})$", bday_str)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), int(m.group(1))
            except ValueError:
                return None, None

        _LOGGER.debug("Could not parse BDAY: %s", bday_str)
        return None, None

    async def fetch_birthdays(self) -> list[Birthday]:
        """Main entry point: fetch all birthdays from CardDAV contacts."""
        birthdays: list[Birthday] = []

        home_url = await self._discover_addressbook_home()
        _LOGGER.debug("Addressbook home: %s", home_url)

        addressbooks = await self._find_addressbooks(home_url)
        _LOGGER.debug("Addressbooks: %s", addressbooks)

        for ab_url in addressbooks:
            vcards = await self._fetch_all_vcards(ab_url)
            for vcard in vcards:
                birthday = self._parse_vcard(vcard)
                if birthday:
                    birthdays.append(birthday)

        _LOGGER.info("Found %d contacts with birthdays", len(birthdays))
        return birthdays

    async def test_connection(self) -> bool:
        """Test if the CardDAV connection works."""
        try:
            async with self._session.request(
                "PROPFIND",
                self._base_url,
                headers={"Depth": "0"},
                auth=self._auth,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                _LOGGER.debug("Connection test -> %s", resp.status)
                return resp.status in (200, 207, 301, 302, 303, 307, 308)
        except Exception as err:
            _LOGGER.debug("Connection test failed: %s", err)
            return False
