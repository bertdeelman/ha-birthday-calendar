"""Config flow for CardDAV Birthday Calendar integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .carddav import CardDAVClient
from .const import (
    CONF_DAYS_AHEAD,
    CONF_SHOW_AGE,
    DEFAULT_DAYS_AHEAD,
    DEFAULT_SHOW_AGE,
    DOMAIN,
    ICLOUD_CARDDAV_URL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_URL, default=ICLOUD_CARDDAV_URL): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DAYS_AHEAD, default=DEFAULT_DAYS_AHEAD): vol.All(
            int, vol.Range(min=1, max=730)
        ),
        vol.Optional(CONF_SHOW_AGE, default=DEFAULT_SHOW_AGE): bool,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input by testing a connection."""
    session = async_get_clientsession(hass)
    client = CardDAVClient(
        url=data[CONF_URL],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        session=session,
    )

    if not await client.test_connection():
        raise InvalidAuth

    return {"title": f"CardDAV Birthday Calendar ({data[CONF_USERNAME]})"}


class BirthdayCalendarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for CardDAV Birthday Calendar."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during setup")
                errors["base"] = "unknown"
            else:
                # Prevent duplicate entries for same username
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_URL: user_input[CONF_URL],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                    options={
                        CONF_DAYS_AHEAD: DEFAULT_DAYS_AHEAD,
                        CONF_SHOW_AGE: DEFAULT_SHOW_AGE,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "app_password_url": "https://appleid.apple.com",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> BirthdayCalendarOptionsFlow:
        """Return the options flow."""
        return BirthdayCalendarOptionsFlow(config_entry)


class BirthdayCalendarOptionsFlow(config_entries.OptionsFlow):
    """Handle options for CardDAV Birthday Calendar."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DAYS_AHEAD,
                        default=self._config_entry.options.get(
                            CONF_DAYS_AHEAD, DEFAULT_DAYS_AHEAD
                        ),
                    ): vol.All(int, vol.Range(min=1, max=730)),
                    vol.Optional(
                        CONF_SHOW_AGE,
                        default=self._config_entry.options.get(
                            CONF_SHOW_AGE, DEFAULT_SHOW_AGE
                        ),
                    ): bool,
                }
            ),
        )


class InvalidAuth(Exception):
    """Raised when authentication fails."""
