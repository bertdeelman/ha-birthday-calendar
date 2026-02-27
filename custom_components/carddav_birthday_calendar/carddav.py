"""CardDAV client for fetching birthdays from iCloud contacts."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

_LOGGER = logging.getLogger(__name__)


@dataclass
class Birthday:
    """Represents a birthday entry."""

    name: str
    birthday: date
    year_of_birth: Optional[int]


class CardDAVClient:
    """
    iCloud CardDAV client using the caldav library.
    The caldav library handles iCloud's partition-based discovery automatically.
    """

    ICLOUD_URL = "https://contacts.icloud.com"

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    def _parse_bday(self, bday_str: str) -> tuple[Optional[date], Optional[int]]:
        """
        Parse BDAY value in multiple formats:
        - YYYYMMDD
        - YYYY-MM-DD
        - --MMDD  (no year)
        - --MM-DD (no year)
        """
        bday_str = bday_str.strip()

        # No year: --MMDD or --MM-DD
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
        """Parse a vCard string and return Birthday if BDAY is present."""
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

    async def fetch_birthdays(self) -> list[Birthday]:
        """Fetch all birthdays from iCloud contacts using the caldav library."""
        import caldav

        birthdays: list[Birthday] = []

        client = caldav.DAVClient(
            url=self.ICLOUD_URL,
            username=self._username,
            password=self._password,
        )

        try:
            principal = client.principal()
            address_books = principal.addressbooks()
            _LOGGER.debug("Found %d address books", len(address_books))

            for address_book in address_books:
                _LOGGER.debug("Fetching vCards from: %s", address_book.url)
                try:
                    vcards = address_book.vobjects()
                    count = 0
                    for vcard in vcards:
                        vcard_text = vcard.serialize()
                        birthday = self._parse_vcard(vcard_text)
                        if birthday:
                            birthdays.append(birthday)
                            count += 1
                    _LOGGER.debug("Found %d birthdays in %s", count, address_book.url)
                except Exception as err:
                    _LOGGER.warning("Error fetching vCards from %s: %s", address_book.url, err)

        except Exception as err:
            _LOGGER.error("Error connecting to iCloud CardDAV: %s", err)
            raise

        _LOGGER.info("Total birthdays found: %d", len(birthdays))
        return birthdays

    async def test_connection(self) -> bool:
        """Test if iCloud credentials are valid."""
        import caldav

        try:
            client = caldav.DAVClient(
                url=self.ICLOUD_URL,
                username=self._username,
                password=self._password,
            )
            client.principal()
            return True
        except Exception as err:
            _LOGGER.debug("Connection test failed: %s", err)
            return False
