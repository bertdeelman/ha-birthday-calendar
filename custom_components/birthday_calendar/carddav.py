"""CardDAV client for fetching birthdays from contacts."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

WELL_KNOWN_PATH = "/.well-known/carddav"


@dataclass
class Birthday:
    """Represents a birthday entry."""

    name: str
    birthday: date
    year_of_birth: Optional[int]  # None if year is unknown (--MM-DD format)


class CardDAVClient:
    """Async CardDAV client that fetches vCards and extracts birthdays."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._base_url = url.rstrip("/")
        self._username = username
        self._password = password
        self._session = session
        self._auth = aiohttp.BasicAuth(username, password)

    async def _resolve_principal_url(self) -> str:
        """Resolve the current user principal URL via PROPFIND."""
        propfind_body = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:current-user-principal/>
  </D:prop>
</D:propfind>"""
        url = self._base_url + WELL_KNOWN_PATH
        async with self._session.request(
            "PROPFIND",
            url,
            data=propfind_body,
            headers={
                "Content-Type": "application/xml; charset=utf-8",
                "Depth": "0",
            },
            auth=self._auth,
            allow_redirects=True,
        ) as resp:
            if resp.status in (301, 302, 307, 308):
                # Follow redirect manually if needed
                location = resp.headers.get("Location", url)
                _LOGGER.debug("Redirect to %s", location)
                return location
            text = await resp.text()
            _LOGGER.debug("Principal response: %s", text[:500])
            # Extract href from current-user-principal
            match = re.search(
                r"<[^>]*current-user-principal[^>]*>.*?<[^>]*href[^>]*>([^<]+)</",
                text,
                re.DOTALL | re.IGNORECASE,
            )
            if match:
                href = match.group(1).strip()
                if href.startswith("http"):
                    return href
                return self._base_url.split("/")[0] + "//" + self._base_url.split("/")[2] + href
            return self._base_url

    async def _find_addressbook_home(self, principal_url: str) -> list[str]:
        """Find addressbook-home-set from the principal URL."""
        propfind_body = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <C:addressbook-home-set/>
  </D:prop>
</D:propfind>"""
        async with self._session.request(
            "PROPFIND",
            principal_url,
            data=propfind_body,
            headers={
                "Content-Type": "application/xml; charset=utf-8",
                "Depth": "0",
            },
            auth=self._auth,
        ) as resp:
            text = await resp.text()
            _LOGGER.debug("Addressbook home response: %s", text[:500])
            hrefs = re.findall(
                r"<[^>]*addressbook-home-set[^>]*>.*?<[^>]*href[^>]*>([^<]+)</",
                text,
                re.DOTALL | re.IGNORECASE,
            )
            base = self._base_url.split("/")[0] + "//" + self._base_url.split("/")[2]
            return [
                href if href.startswith("http") else base + href
                for href in hrefs
            ]

    async def _find_addressbooks(self, home_url: str) -> list[str]:
        """Find all addressbook collections under the home set."""
        propfind_body = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:resourcetype/>
    <D:displayname/>
  </D:prop>
</D:propfind>"""
        async with self._session.request(
            "PROPFIND",
            home_url,
            data=propfind_body,
            headers={
                "Content-Type": "application/xml; charset=utf-8",
                "Depth": "1",
            },
            auth=self._auth,
        ) as resp:
            text = await resp.text()
            _LOGGER.debug("Addressbooks response: %s", text[:1000])

            base = self._base_url.split("/")[0] + "//" + self._base_url.split("/")[2]
            addressbooks = []

            # Find responses that contain addressbook resourcetype
            responses = re.findall(
                r"<D:response>(.*?)</D:response>",
                text,
                re.DOTALL | re.IGNORECASE,
            )
            for response in responses:
                if "addressbook" in response.lower() and "<D:href>" in response or "<d:href>" in response.lower():
                    href_match = re.search(r"<[Dd]:href>([^<]+)</[Dd]:href>", response)
                    if href_match:
                        href = href_match.group(1).strip()
                        url = href if href.startswith("http") else base + href
                        if url != home_url:
                            addressbooks.append(url)

            return addressbooks if addressbooks else [home_url]

    async def _fetch_vcards(self, addressbook_url: str) -> list[str]:
        """Fetch all vCards from an addressbook using REPORT."""
        report_body = """<?xml version="1.0" encoding="utf-8"?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:getetag/>
    <C:address-data>
      <C:prop name="FN"/>
      <C:prop name="BDAY"/>
      <C:prop name="N"/>
    </C:address-data>
  </D:prop>
  <C:filter>
    <C:prop-filter name="BDAY"/>
  </C:filter>
</C:addressbook-query>"""
        async with self._session.request(
            "REPORT",
            addressbook_url,
            data=report_body,
            headers={
                "Content-Type": "application/xml; charset=utf-8",
                "Depth": "1",
            },
            auth=self._auth,
        ) as resp:
            if resp.status == 207:
                text = await resp.text()
                _LOGGER.debug("REPORT response status: %s, length: %d", resp.status, len(text))
                return self._extract_vcards(text)
            _LOGGER.warning("REPORT returned status %s for %s", resp.status, addressbook_url)
            return []

    def _extract_vcards(self, xml_text: str) -> list[str]:
        """Extract vCard data from a REPORT XML response."""
        vcards = re.findall(
            r"BEGIN:VCARD.*?END:VCARD",
            xml_text,
            re.DOTALL,
        )
        return vcards

    def _parse_vcard_birthday(self, vcard_text: str) -> Optional[Birthday]:
        """Parse a vCard string and extract name + birthday."""
        # Get display name (FN)
        fn_match = re.search(r"^FN[^:]*:(.+)$", vcard_text, re.MULTILINE)
        name = fn_match.group(1).strip() if fn_match else "Unknown"

        # Get birthday (BDAY)
        bday_match = re.search(r"^BDAY[^:]*:(.+)$", vcard_text, re.MULTILINE)
        if not bday_match:
            return None

        bday_str = bday_match.group(1).strip()
        birthday, year_of_birth = self._parse_bday_value(bday_str)
        if birthday is None:
            return None

        return Birthday(name=name, birthday=birthday, year_of_birth=year_of_birth)

    def _parse_bday_value(self, bday_str: str) -> tuple[Optional[date], Optional[int]]:
        """
        Parse BDAY value in multiple formats:
        - YYYYMMDD         -> date with year
        - YYYY-MM-DD       -> date with year
        - --MMDD           -> date without year (year unknown)
        - --MM-DD          -> date without year (year unknown)
        """
        # --MMDD or --MM-DD (no year)
        no_year = re.match(r"^--(\d{2})-?(\d{2})$", bday_str)
        if no_year:
            month, day = int(no_year.group(1)), int(no_year.group(2))
            try:
                return date(2000, month, day), None  # Use 2000 as placeholder
            except ValueError:
                return None, None

        # YYYY-MM-DD
        full_date = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", bday_str)
        if full_date:
            year, month, day = int(full_date.group(1)), int(full_date.group(2)), int(full_date.group(3))
            try:
                return date(year, month, day), year
            except ValueError:
                return None, None

        # YYYYMMDD
        compact = re.match(r"^(\d{4})(\d{2})(\d{2})$", bday_str)
        if compact:
            year, month, day = int(compact.group(1)), int(compact.group(2)), int(compact.group(3))
            try:
                return date(year, month, day), year
            except ValueError:
                return None, None

        _LOGGER.debug("Could not parse BDAY value: %s", bday_str)
        return None, None

    async def fetch_birthdays(self) -> list[Birthday]:
        """Main entry point: fetch all birthdays from iCloud contacts."""
        birthdays: list[Birthday] = []

        try:
            # Step 1: Resolve principal
            principal_url = await self._resolve_principal_url()
            _LOGGER.debug("Principal URL: %s", principal_url)

            # Step 2: Find addressbook home
            home_urls = await self._find_addressbook_home(principal_url)
            if not home_urls:
                _LOGGER.warning("No addressbook home found, trying base URL")
                home_urls = [self._base_url]
            _LOGGER.debug("Addressbook home URLs: %s", home_urls)

            for home_url in home_urls:
                # Step 3: Find addressbooks
                addressbooks = await self._find_addressbooks(home_url)
                _LOGGER.debug("Found addressbooks: %s", addressbooks)

                for ab_url in addressbooks:
                    # Step 4: Fetch vCards with BDAY filter
                    vcards = await self._fetch_vcards(ab_url)
                    _LOGGER.debug("Found %d vCards with birthdays in %s", len(vcards), ab_url)

                    for vcard in vcards:
                        birthday = self._parse_vcard_birthday(vcard)
                        if birthday:
                            birthdays.append(birthday)

        except aiohttp.ClientError as err:
            _LOGGER.error("Network error fetching birthdays: %s", err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error fetching birthdays: %s", err)
            raise

        _LOGGER.info("Fetched %d birthdays total", len(birthdays))
        return birthdays

    async def test_connection(self) -> bool:
        """Test if the CardDAV connection works."""
        try:
            async with self._session.request(
                "PROPFIND",
                self._base_url + WELL_KNOWN_PATH,
                headers={"Depth": "0"},
                auth=self._auth,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status in (200, 207, 301, 302, 303, 307, 308)
        except Exception as err:
            _LOGGER.debug("Connection test failed: %s", err)
            return False
