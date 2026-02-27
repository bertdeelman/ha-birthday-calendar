"""Constants for CardDAV Birthday Calendar integration."""

DOMAIN = "carddav_birthday_calendar"

# Config keys
CONF_DAYS_AHEAD = "days_ahead"
CONF_SHOW_AGE = "show_age"

# iCloud CardDAV - hardcoded, no other providers supported
ICLOUD_CARDDAV_URL = "https://contacts.icloud.com"

# Defaults
DEFAULT_DAYS_AHEAD = 365
DEFAULT_SHOW_AGE = True
DEFAULT_UPDATE_INTERVAL = 3600  # 1 hour

# Platforms
PLATFORMS = ["calendar"]
