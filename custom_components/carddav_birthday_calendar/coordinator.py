"""DataUpdateCoordinator for CardDAV Birthday Calendar."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .carddav import Birthday, CardDAVClient
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class BirthdayCalendarCoordinator(DataUpdateCoordinator[list[Birthday]]):
    """Coordinator that fetches birthday data from iCloud CardDAV."""

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        self._username = username
        self._password = password

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> list[Birthday]:
        """Fetch birthday data from iCloud in executor (caldav is synchronous)."""
        client = CardDAVClient(
            username=self._username,
            password=self._password,
        )
        try:
            return await self.hass.async_add_executor_job(
                lambda: self._fetch_sync(client)
            )
        except Exception as err:
            raise UpdateFailed(f"Error fetching birthdays: {err}") from err

    def _fetch_sync(self, client: CardDAVClient) -> list[Birthday]:
        """Synchronous fetch - runs in executor."""
        import asyncio
        return asyncio.run(client.fetch_birthdays())
