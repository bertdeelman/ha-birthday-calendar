"""Calendar platform for CardDAV Birthday Calendar integration."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .carddav import ContactDate
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

# Label translations for built-in labels
LABEL_TRANSLATIONS = {
    "bday": {"nl": "verjaardag", "en": "birthday"},
    "anniversary": {"nl": "trouwdag", "en": "anniversary"},
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BirthdayCalendarCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BirthdayCalendarEntity(coordinator, entry)], True)


def _get_next_occurrence(d: date, reference: date) -> date:
    """Return the next occurrence of a date from reference date."""
    try:
        next_d = d.replace(year=reference.year)
    except ValueError:
        next_d = date(reference.year, 2, 28)
    if next_d < reference:
        try:
            next_d = d.replace(year=reference.year + 1)
        except ValueError:
            next_d = date(reference.year + 1, 2, 28)
    return next_d


def _translate_label(label: str, language: str) -> str:
    """Translate built-in labels, pass through custom labels as-is."""
    if label in LABEL_TRANSLATIONS:
        return LABEL_TRANSLATIONS[label][language]
    return label


def _build_summary(entry: ContactDate, event_year: int, show_age: bool, language: str) -> str:
    """Build event title."""
    label = _translate_label(entry.label, language)
    if language == LANGUAGE_NL:
        if show_age and entry.year_of_birth and entry.label == "bday":
            age = event_year - entry.year_of_birth
            return f"{entry.name} {label} ({age})"
        return f"{entry.name} {label}"
    else:
        if show_age and entry.year_of_birth and entry.label == "bday":
            age = event_year - entry.year_of_birth
            return f"{entry.name} {label} ({age})"
        return f"{entry.name} {label}"


def _build_description(entry: ContactDate, language: str) -> str:
    """Build event description."""
    label = _translate_label(entry.label, language)
    if language == LANGUAGE_NL:
        if entry.year_of_birth and entry.label == "bday":
            return f"{label.capitalize()} van {entry.name} (geboren {entry.year_of_birth})"
        return f"{label.capitalize()} van {entry.name}"
    else:
        if entry.year_of_birth and entry.label == "bday":
            return f"{label.capitalize()} of {entry.name} (born {entry.year_of_birth})"
        return f"{label.capitalize()} of {entry.name}"


def _entry_to_events(
    entry: ContactDate,
    start: date,
    end: date,
    show_age: bool,
    language: str,
) -> list[CalendarEvent]:
    """Generate CalendarEvent instances for a contact date in the given range."""
    events: list[CalendarEvent] = []

    for year in range(start.year, end.year + 2):
        try:
            occurrence = entry.date.replace(year=year)
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
                summary=_build_summary(entry, year, show_age, language),
                description=_build_description(entry, language),
            )
        )

    return events


class BirthdayCalendarEntity(CoordinatorEntity[BirthdayCalendarCoordinator], CalendarEntity):
    """HA calendar entity showing birthdays and custom dates."""

    _attr_icon = "mdi:cake-variant"

    def __init__(self, coordinator: BirthdayCalendarCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_carddav_birthday_calendar"
        self._attr_name = entry.title

    def _get_options(self) -> tuple[bool, str, int]:
        show_age = self._entry.options.get(CONF_SHOW_AGE, DEFAULT_SHOW_AGE)
        language = self._entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        days_ahead = self._entry.options.get(CONF_DAYS_AHEAD, DEFAULT_DAYS_AHEAD)
        return show_age, language, days_ahead

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        if not self.coordinator.data:
            return None

        today = date.today()
        show_age, language, days_ahead = self._get_options()
        cutoff = today + timedelta(days=days_ahead)
        upcoming: list[tuple[date, CalendarEvent]] = []

        for entry in self.coordinator.data:
            next_d = _get_next_occurrence(entry.date, today)
            if next_d > cutoff:
                continue
            event = CalendarEvent(
                start=next_d,
                end=next_d + timedelta(days=1),
                summary=_build_summary(entry, next_d.year, show_age, language),
                description=_build_description(entry, language),
            )
            upcoming.append((next_d, event))

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
        """Return all events between start_date and end_date."""
        if not self.coordinator.data:
            return []

        show_age, language, _ = self._get_options()
        start = start_date.date()
        end = end_date.date()
        all_events: list[CalendarEvent] = []

        for entry in self.coordinator.data:
            all_events.extend(_entry_to_events(entry, start, end, show_age, language))

        all_events.sort(key=lambda e: e.start)
        return all_events
