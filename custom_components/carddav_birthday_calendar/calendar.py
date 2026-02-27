"""Calendar platform for CardDAV Birthday Calendar integration."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .carddav import Birthday
from .const import CONF_DAYS_AHEAD, CONF_SHOW_AGE, DEFAULT_DAYS_AHEAD, DEFAULT_SHOW_AGE, DOMAIN
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
        # Feb 29 in non-leap year -> use Feb 28
        next_bd = date(reference.year, 2, 28)

    if next_bd < reference:
        try:
            next_bd = birthday.replace(year=reference.year + 1)
        except ValueError:
            next_bd = date(reference.year + 1, 2, 28)

    return next_bd


def _build_summary(name: str, year_of_birth: int | None, event_year: int, show_age: bool) -> str:
    """Build the event title."""
    if show_age and year_of_birth is not None:
        age = event_year - year_of_birth
        return f"{name} turns {age}"
    return f"{name}'s birthday"


def _birthday_to_events(
    birthday: Birthday,
    start: date,
    end: date,
    show_age: bool,
) -> list[CalendarEvent]:
    """
    Generate CalendarEvent instances for a birthday in the given date range.
    Birthdays repeat yearly, so we may get 0, 1, or 2 occurrences in a range.
    """
    events: list[CalendarEvent] = []
    bd_date = birthday.birthday  # The day/month (year may be placeholder 2000)

    # Check occurrences for the years covered by start..end
    for year in range(start.year, end.year + 2):
        try:
            occurrence = bd_date.replace(year=year)
        except ValueError:
            # Feb 29 in non-leap year
            occurrence = date(year, 2, 28)

        if occurrence < start:
            continue
        if occurrence > end:
            break

        summary = _build_summary(birthday.name, birthday.year_of_birth, year, show_age)

        events.append(
            CalendarEvent(
                start=occurrence,
                end=occurrence + timedelta(days=1),  # All-day event: end is exclusive next day
                summary=summary,
                description=(
                    f"Birthday of {birthday.name}"
                    + (
                        f" (born {birthday.year_of_birth})"
                        if birthday.year_of_birth
                        else ""
                    )
                ),
            )
        )

    return events


class BirthdayCalendarEntity(CoordinatorEntity[BirthdayCalendarCoordinator], CalendarEntity):
    """A HA calendar entity that shows birthdays."""

    _attr_has_entity_name = True
    _attr_name = "iCloud Birthdays"
    _attr_icon = "mdi:cake-variant"

    def __init__(
        self,
        coordinator: BirthdayCalendarCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_carddav_birthday_calendar"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming birthday event."""
        if not self.coordinator.data:
            return None

        today = date.today()
        show_age = self._entry.options.get(CONF_SHOW_AGE, DEFAULT_SHOW_AGE)
        upcoming: list[tuple[date, CalendarEvent]] = []

        for birthday in self.coordinator.data:
            next_bd = _get_next_birthday(birthday.birthday, today)
            event = CalendarEvent(
                start=next_bd,
                end=next_bd + timedelta(days=1),
                summary=_build_summary(birthday.name, birthday.year_of_birth, next_bd.year, show_age),
                description=(
                    f"Birthday of {birthday.name}"
                    + (f" (born {birthday.year_of_birth})" if birthday.year_of_birth else "")
                ),
            )
            upcoming.append((next_bd, event))

        if not upcoming:
            return None

        # Return the soonest upcoming birthday
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

        show_age = self._entry.options.get(CONF_SHOW_AGE, DEFAULT_SHOW_AGE)
        start = start_date.date()
        end = end_date.date()
        all_events: list[CalendarEvent] = []

        for birthday in self.coordinator.data:
            events = _birthday_to_events(birthday, start, end, show_age)
            all_events.extend(events)

        # Sort by date
        all_events.sort(key=lambda e: e.start)
        return all_events

