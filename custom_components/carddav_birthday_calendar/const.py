"""Constants for CardDAV Birthday Calendar integration."""

DOMAIN = "carddav_birthday_calendar"

# Config keys
CONF_CARDDAV_URL = "carddav_url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DAYS_AHEAD = "days_ahead"
CONF_SHOW_AGE = "show_age"

# Defaults
DEFAULT_CARDDAV_URL = "https://contacts.icloud.com"
DEFAULT_DAYS_AHEAD = 365
DEFAULT_SHOW_AGE = True
DEFAULT_UPDATE_INTERVAL = 3600  # seconds (1 hour)

# iCloud CardDAV
ICLOUD_CARDDAV_URL = "https://contacts.icloud.com"

# Platforms
PLATFORMS = ["calendar"]
