"""CardDAV client for fetching birthdays and custom dates from iCloud contacts."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Apple's built-in label translations
APPLE_LABELS = {
    "_$!<Anniversary>!$_": {"nl": "trouwdag", "en": "anniversary"},
    "_$!<Birthday>!$_": {"nl": "verjaardag", "en": "birthday"},
    "_$!<Other>!$_": {"nl": "overig", "en": "other"},
}


@dataclass
class ContactDate:
    """Represents a date entry from a contact (birthday or custom date)."""

    name: str
    date: date
    year_of_birth: Optional[int]
    label: str  # e.g. "verjaardag", "trouwdag", "sterfdag"


class CardDAVClient:
    """
    iCloud CardDAV client.

    Discovery flow:
    1. PROPFIND contacts.icloud.com/.well-known/carddav
       -> response header x-apple-user-partition: XX
    2. PROPFIND pXX-contacts.icloud.com/
       -> current-user-principal href
    3. PROPFIND principal URL
       -> addressbook-home-set href
    4. addressbook = carddavhome + card/
    5. REPORT addressbook -> all vCards
    """

    WELL_KNOWN = "https://contacts.icloud.com/.well-known/carddav"

    def __init__(self, username: str, password: str, session: aiohttp.ClientSession) -> None:
        self._username = username
        self._password = password
        self._session = session
        self._auth = aiohttp.BasicAuth(username, password)

    async def _get_partition_base(self) -> str:
        async with self._session.request(
            "PROPFIND", self.WELL_KNOWN,
            headers={"Depth": "0"}, auth=self._auth,
            allow_redirects=False, timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            partition = resp.headers.get("x-apple-user-partition")
            if not partition:
                raise ValueError("Could not get iCloud partition number")
            base = f"https://p{partition}-contacts.icloud.com"
            _LOGGER.debug("Partition: %s, Base: %s", partition, base)
            return base

    def _xml_find_in_parent(self, xml_text: str, parent_tag: str, child_tag: str) -> str | None:
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as err:
            _LOGGER.debug("XML parse error: %s", err)
            return None
        for elem in root.iter():
            local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if local == parent_tag:
                for child in elem:
                    child_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child_local == child_tag and child.text and child.text.strip():
                        return child.text.strip()
        return None

    async def _get_principal(self, base: str) -> str:
        async with self._session.request(
            "PROPFIND", base + "/",
            headers={"Depth": "0", "Content-Type": "application/xml"},
            data='<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop><D:current-user-principal/></D:prop></D:propfind>',
            auth=self._auth, timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            text = await resp.text()
            principal = self._xml_find_in_parent(text, "current-user-principal", "href")
            if not principal:
                raise ValueError(f"Could not find principal URL in: {text[:500]}")
            _LOGGER.debug("Principal: %s", principal)
            return principal

    async def _get_addressbook_home(self, base: str, principal: str) -> str:
        async with self._session.request(
            "PROPFIND", base + principal,
            headers={"Depth": "0", "Content-Type": "application/xml"},
            data='<?xml version="1.0"?><D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav"><D:prop><C:addressbook-home-set/></D:prop></D:propfind>',
            auth=self._auth, timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            text = await resp.text()
            home = self._xml_find_in_parent(text, "addressbook-home-set", "href")
            if not home:
                raise ValueError(f"Could not find addressbook home in: {text[:500]}")
            _LOGGER.debug("Addressbook home: %s", home)
            return home

    async def _fetch_vcards(self, addressbook_url: str) -> list[str]:
        report_body = """<?xml version="1.0" encoding="utf-8"?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop><D:getetag/><C:address-data/></D:prop>
</C:addressbook-query>"""
        async with self._session.request(
            "REPORT", addressbook_url,
            headers={"Depth": "1", "Content-Type": "application/xml"},
            data=report_body, auth=self._auth,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 207:
                raise ValueError(f"REPORT returned {resp.status} for {addressbook_url}")
            text = await resp.text()
            vcards = re.findall(r"BEGIN:VCARD.*?END:VCARD", text, re.DOTALL)
            _LOGGER.debug("Fetched %d vCards", len(vcards))
            return vcards

    def _clean(self, value: str) -> str:
        return value.replace("\r", "").replace("&#13;", "").replace("&lt;", "<").replace("&gt;", ">").strip()

    def _normalize_label(self, raw_label: str, language: str = "nl") -> str:
        """Normalize Apple labels like _$!<Anniversary>!$_ to human readable."""
        cleaned = self._clean(raw_label)
        if cleaned in APPLE_LABELS:
            return APPLE_LABELS[cleaned][language]
        # Strip _$!< and >!$_ if present
        cleaned = re.sub(r"_\$!<(.+?)>!\$_", r"\1", cleaned)
        return cleaned.lower()

    def _parse_date(self, date_str: str) -> tuple[Optional[date], Optional[int]]:
        """Parse date in multiple formats."""
        date_str = self._clean(date_str)

        # --MMDD or --MM-DD (no year)
        m = re.match(r"^--(\d{2})-?(\d{2})$", date_str)
        if m:
            try:
                return date(2000, int(m.group(1)), int(m.group(2))), None
            except ValueError:
                return None, None

        # YYYY-MM-DD
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), int(m.group(1))
            except ValueError:
                return None, None

        # YYYYMMDD
        m = re.match(r"^(\d{4})(\d{2})(\d{2})$", date_str)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), int(m.group(1))
            except ValueError:
                return None, None

        _LOGGER.debug("Could not parse date: %s", date_str)
        return None, None

    def _parse_vcard(self, vcard_text: str) -> list[ContactDate]:
        """Parse a vCard and return all ContactDate entries (birthday + custom dates)."""
        results: list[ContactDate] = []

        fn_match = re.search(r"^FN[^:]*:(.+)$", vcard_text, re.MULTILINE)
        name = self._clean(fn_match.group(1)) if fn_match else "Unknown"

        # Parse BDAY
        bday_match = re.search(r"^BDAY[^:]*:(.+)$", vcard_text, re.MULTILINE)
        if bday_match:
            d, year = self._parse_date(bday_match.group(1))
            if d:
                results.append(ContactDate(name=name, date=d, year_of_birth=year, label="bday"))

        # Parse ANNIVERSARY
        ann_match = re.search(r"^ANNIVERSARY[^:]*:(.+)$", vcard_text, re.MULTILINE)
        if ann_match:
            d, year = self._parse_date(ann_match.group(1))
            if d:
                results.append(ContactDate(name=name, date=d, year_of_birth=year, label="anniversary"))

        # Parse itemN.X-ABDATE with itemN.X-ABLabel
        abdate_matches = re.findall(r"^(item\d+)\.X-ABDATE[^:]*:(.+)$", vcard_text, re.MULTILINE)
        for item_id, date_str in abdate_matches:
            label_match = re.search(rf"^{item_id}\.X-ABLabel:(.+)$", vcard_text, re.MULTILINE)
            raw_label = label_match.group(1) if label_match else "custom"
            label = self._normalize_label(raw_label)
            d, year = self._parse_date(date_str)
            if d:
                results.append(ContactDate(name=name, date=d, year_of_birth=year, label=label))
                _LOGGER.debug("Found custom date for %s: %s on %s", name, label, d)

        return results

    async def fetch_dates(self) -> list[ContactDate]:
        """Fetch all contact dates from iCloud."""
        base = await self._get_partition_base()
        principal = await self._get_principal(base)
        home = await self._get_addressbook_home(base, principal)
        addressbook = home.rstrip("/") + "/card/"
        _LOGGER.debug("Addressbook URL: %s", addressbook)

        vcards = await self._fetch_vcards(addressbook)

        all_dates: list[ContactDate] = []
        for vcard in vcards:
            all_dates.extend(self._parse_vcard(vcard))

        bdays = sum(1 for d in all_dates if d.label == "bday")
        custom = len(all_dates) - bdays
        _LOGGER.info("Found %d birthdays and %d custom dates from %d contacts", bdays, custom, len(vcards))
        return all_dates

    async def test_connection(self) -> bool:
        try:
            async with self._session.request(
                "PROPFIND", self.WELL_KNOWN,
                headers={"Depth": "0"}, auth=self._auth,
                allow_redirects=False, timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                partition = resp.headers.get("x-apple-user-partition")
                return partition is not None
        except Exception as err:
            _LOGGER.debug("Connection test failed: %s", err)
            return False
