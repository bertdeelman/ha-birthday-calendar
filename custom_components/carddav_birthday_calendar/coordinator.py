"""DataUpdateCoordinator for CardDAV Birthday Calendar."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .carddav import Birthday, CardDAVClient
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class BirthdayCalendarCoordinator(DataUpdateCoordinator[list[Birthday]]):
    """Coordinator that fetches birthday data from CardDAV on a schedule."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        username: str,
        password: str,
    ) -> None:
        self._url = url
        self._username = username
        self._password = password

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> list[Birthday]:
        """Fetch birthday data from CardDAV."""
        async with aiohttp.ClientSession() as session:
            client = CardDAVClient(
                url=self._url,
                username=self._username,
                password=self._password,
                session=session,
            )
            try:
                return await client.fetch_birthdays()
            except aiohttp.ClientResponseError as err:
                raise UpdateFailed(f"CardDAV server returned error: {err.status}") from err
            except aiohttp.ClientConnectionError as err:
                raise UpdateFailed(f"Cannot connect to CardDAV server: {err}") from err
            except Exception as err:
                raise UpdateFailed(f"Unexpected error: {err}") from err
