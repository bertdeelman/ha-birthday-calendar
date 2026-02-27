"""Constants for CardDAV Birthday Calendar integration."""

DOMAIN = "carddav_birthday_calendar"

# Config keys
CONF_DAYS_AHEAD = "days_ahead"
CONF_SHOW_AGE = "show_age"
CONF_LANGUAGE = "language"

# iCloud CardDAV
ICLOUD_CARDDAV_URL = "https://contacts.icloud.com"

# Language options
LANGUAGE_EN = "en"
LANGUAGE_NL = "nl"
LANGUAGES = [LANGUAGE_EN, LANGUAGE_NL]

# Defaults
DEFAULT_DAYS_AHEAD = 365
DEFAULT_SHOW_AGE = True
DEFAULT_LANGUAGE = LANGUAGE_NL
DEFAULT_UPDATE_INTERVAL = 3600  # 1 hour

# Platforms
PLATFORMS = ["calendar"]
