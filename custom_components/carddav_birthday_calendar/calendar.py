"""Calendar platform for CardDAV Birthday Calendar integration."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .carddav import Birthday
from .const import (
    CONF_DAYS_AHEAD,
    CONF_LANGUAGE,
    CONF_SHOW_AGE,
    DEFAULT_DAYS_AHEAD,
    DEFAULT_LANGUAGE,
    DEFAULT_SHOW_AGE,
    DOMAIN,
    LANGUAGE_NL,
)
from .coordinator import BirthdayCalendarCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the CardDAV Birthday Calendar entity from a config entry."""
    coordinator: BirthdayCalendarCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BirthdayCalendarEntity(coordinator, entry)], True)


def _get_next_birthday(birthday: date, reference: date) -> date:
    """Return the next occurrence of a birthday from reference date."""
    try:
        next_bd = birthday.replace(year=reference.year)
    except ValueError:
        next_bd = date(reference.year, 2, 28)
    if next_bd < reference:
        try:
            next_bd = birthday.replace(year=reference.year + 1)
        except ValueError:
            next_bd = date(reference.year + 1, 2, 28)
    return next_bd


def _build_summary(name: str, year_of_birth: int | None, event_year: int, show_age: bool, language: str) -> str:
    """Build the event title."""
    if language == LANGUAGE_NL:
        if show_age and year_of_birth is not None:
            age = event_year - year_of_birth
            return f"{name} is jarig ({age})"
        return f"{name} is jarig"
    else:
        if show_age and year_of_birth is not None:
            age = event_year - year_of_birth
            return f"{name} turns {age}"
        return f"{name}'s birthday"


def _build_description(name: str, year_of_birth: int | None, language: str) -> str:
    """Build the event description."""
    if language == LANGUAGE_NL:
        if year_of_birth:
            return f"Verjaardag van {name} (geboren {year_of_birth})"
        return f"Verjaardag van {name}"
    else:
        if year_of_birth:
            return f"Birthday of {name} (born {year_of_birth})"
        return f"Birthday of {name}"


def _birthday_to_events(
    birthday: Birthday,
    start: date,
    end: date,
    show_age: bool,
    language: str,
) -> list[CalendarEvent]:
    """Generate CalendarEvent instances for a birthday in the given date range."""
    events: list[CalendarEvent] = []
    bd_date = birthday.birthday

    for year in range(start.year, end.year + 2):
        try:
            occurrence = bd_date.replace(year=year)
        except ValueError:
            occurrence = date(year, 2, 28)

        if occurrence < start:
            continue
        if occurrence > end:
            break

        events.append(
            CalendarEvent(
                start=occurrence,
                end=occurrence + timedelta(days=1),
                summary=_build_summary(birthday.name, birthday.year_of_birth, year, show_age, language),
                description=_build_description(birthday.name, birthday.year_of_birth, language),
            )
        )

    return events


class BirthdayCalendarEntity(CoordinatorEntity[BirthdayCalendarCoordinator], CalendarEntity):
    """A HA calendar entity that shows birthdays."""

    _attr_has_entity_name = True
    _attr_name = "iCloud Birthdays"
    _attr_icon = "mdi:cake-variant"

    def __init__(self, coordinator: BirthdayCalendarCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_carddav_birthday_calendar"

    def _get_options(self) -> tuple[bool, str, int]:
        """Return show_age, language, days_ahead from options."""
        show_age = self._entry.options.get(CONF_SHOW_AGE, DEFAULT_SHOW_AGE)
        language = self._entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        days_ahead = self._entry.options.get(CONF_DAYS_AHEAD, DEFAULT_DAYS_AHEAD)
        return show_age, language, days_ahead

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming birthday event."""
        if not self.coordinator.data:
            return None

        today = date.today()
        show_age, language, days_ahead = self._get_options()
        cutoff = today + timedelta(days=days_ahead)
        upcoming: list[tuple[date, CalendarEvent]] = []

        for birthday in self.coordinator.data:
            next_bd = _get_next_birthday(birthday.birthday, today)
            if next_bd > cutoff:
                continue
            event = CalendarEvent(
                start=next_bd,
                end=next_bd + timedelta(days=1),
                summary=_build_summary(birthday.name, birthday.year_of_birth, next_bd.year, show_age, language),
                description=_build_description(birthday.name, birthday.year_of_birth, language),
            )
            upcoming.append((next_bd, event))

        if not upcoming:
            return None

        upcoming.sort(key=lambda x: x[0])
        return upcoming[0][1]

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return all birthday events between start_date and end_date."""
        if not self.coordinator.data:
            return []

        show_age, language, _ = self._get_options()
        start = start_date.date()
        end = end_date.date()
        all_events: list[CalendarEvent] = []

        for birthday in self.coordinator.data:
            all_events.extend(_birthday_to_events(birthday, start, end, show_age, language))

        all_events.sort(key=lambda e: e.start)
        return all_events
