"""CardDAV client for fetching birthdays from iCloud contacts."""
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
    year_of_birth: Optional[int]


class CardDAVClient:
    """
    iCloud CardDAV client.

    Discovery flow (proven via curl/requests testing):
    1. PROPFIND contacts.icloud.com/.well-known/carddav
       -> response header x-apple-user-partition: XX
       -> use pXX-contacts.icloud.com as base
    2. PROPFIND pXX-contacts.icloud.com/
       -> <href>/USERID/principal/</href>
    3. PROPFIND pXX-contacts.icloud.com/USERID/principal/
       -> <href xmlns="DAV:">https://pYY-contacts.icloud.com:443/USERID/carddavhome/</href>
    4. addressbook = carddavhome + "card/"
    5. REPORT addressbook -> all vCards, filter locally on BDAY
    """

    WELL_KNOWN = "https://contacts.icloud.com/.well-known/carddav"

    def __init__(self, username: str, password: str, session: aiohttp.ClientSession) -> None:
        self._username = username
        self._password = password
        self._session = session
        self._auth = aiohttp.BasicAuth(username, password)

    async def _get_partition_base(self) -> str:
        """Step 1: Get iCloud partition number from well-known endpoint."""
        async with self._session.request(
            "PROPFIND",
            self.WELL_KNOWN,
            headers={"Depth": "0"},
            auth=self._auth,
            allow_redirects=False,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            partition = resp.headers.get("x-apple-user-partition")
            if not partition:
                raise ValueError("Could not get iCloud partition number")
            base = f"https://p{partition}-contacts.icloud.com"
            _LOGGER.debug("Partition: %s, Base: %s", partition, base)
            return base

    def _xml_find_text(self, xml_text: str, *tags: str) -> str | None:
        """Find text content of first matching element using ElementTree."""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as err:
            _LOGGER.debug("XML parse error: %s", err)
            return None
        namespaces = {
            "D": "DAV:",
            "C": "urn:ietf:params:xml:ns:carddav",
        }
        for tag in tags:
            for elem in root.iter():
                local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if local == tag and elem.text and elem.text.strip():
                    return elem.text.strip()
        return None

    async def _get_principal(self, base: str) -> str:
        """Step 2: Get current user principal path."""
        async with self._session.request(
            "PROPFIND",
            base + "/",
            headers={"Depth": "0", "Content-Type": "application/xml"},
            data='<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop><D:current-user-principal/></D:prop></D:propfind>',
            auth=self._auth,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            text = await resp.text()
            principal = self._xml_find_text(text, "href")
            if not principal or "principal" not in principal:
                raise ValueError(f"Could not find principal URL in: {text[:500]}")
            _LOGGER.debug("Principal: %s", principal)
            return principal

    async def _get_addressbook_home(self, base: str, principal: str) -> str:
        """Step 3: Get addressbook home URL from principal."""
        async with self._session.request(
            "PROPFIND",
            base + principal,
            headers={"Depth": "0", "Content-Type": "application/xml"},
            data='<?xml version="1.0"?><D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav"><D:prop><C:addressbook-home-set/></D:prop></D:propfind>',
            auth=self._auth,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            text = await resp.text()
            home = self._xml_find_text(text, "href")
            if not home or "carddavhome" not in home:
                raise ValueError(f"Could not find addressbook home in: {text[:500]}")
            _LOGGER.debug("Addressbook home: %s", home)
            return home

    async def _fetch_vcards(self, addressbook_url: str) -> list[str]:
        """Step 4+5: Fetch all vCards from the addressbook."""
        report_body = """<?xml version="1.0" encoding="utf-8"?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:getetag/>
    <C:address-data/>
  </D:prop>
</C:addressbook-query>"""
        async with self._session.request(
            "REPORT",
            addressbook_url,
            headers={"Depth": "1", "Content-Type": "application/xml"},
            data=report_body,
            auth=self._auth,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 207:
                raise ValueError(f"REPORT returned {resp.status} for {addressbook_url}")
            text = await resp.text()
            vcards = re.findall(r"BEGIN:VCARD.*?END:VCARD", text, re.DOTALL)
            _LOGGER.debug("Fetched %d vCards", len(vcards))
            return vcards

    def _clean(self, value: str) -> str:
        """Remove carriage returns and whitespace."""
        return value.replace("\r", "").replace("&#13;", "").strip()

    def _parse_bday(self, bday_str: str) -> tuple[Optional[date], Optional[int]]:
        """Parse BDAY in multiple formats."""
        bday_str = self._clean(bday_str)

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

    def _parse_vcard(self, vcard_text: str) -> Optional[Birthday]:
        """Parse a vCard and return Birthday if BDAY is present."""
        bday_match = re.search(r"^BDAY[^:]*:(.+)$", vcard_text, re.MULTILINE)
        if not bday_match:
            return None

        fn_match = re.search(r"^FN[^:]*:(.+)$", vcard_text, re.MULTILINE)
        name = self._clean(fn_match.group(1)) if fn_match else "Unknown"

        bday_str = bday_match.group(1)
        birthday, year_of_birth = self._parse_bday(bday_str)
        if birthday is None:
            return None

        return Birthday(name=name, birthday=birthday, year_of_birth=year_of_birth)

    async def fetch_birthdays(self) -> list[Birthday]:
        """Fetch all birthdays from iCloud contacts."""
        # Step 1: partition
        base = await self._get_partition_base()

        # Step 2: principal
        principal = await self._get_principal(base)

        # Step 3: addressbook home
        home = await self._get_addressbook_home(base, principal)

        # Step 4: addressbook URL = home + card/
        addressbook = home.rstrip("/") + "/card/"
        _LOGGER.debug("Addressbook URL: %s", addressbook)

        # Step 5: fetch vCards
        vcards = await self._fetch_vcards(addressbook)

        # Step 6: parse and filter
        birthdays = []
        for vcard in vcards:
            birthday = self._parse_vcard(vcard)
            if birthday:
                birthdays.append(birthday)

        _LOGGER.info("Found %d birthdays out of %d contacts", len(birthdays), len(vcards))
        return birthdays

    async def test_connection(self) -> bool:
        """Test iCloud connection by checking partition header."""
        try:
            async with self._session.request(
                "PROPFIND",
                self.WELL_KNOWN,
                headers={"Depth": "0"},
                auth=self._auth,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                partition = resp.headers.get("x-apple-user-partition")
                _LOGGER.debug("Connection test partition: %s", partition)
                return partition is not None
        except Exception as err:
            _LOGGER.debug("Connection test failed: %s", err)
            return False
