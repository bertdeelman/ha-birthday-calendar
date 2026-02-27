# Birthday Calendar for Home Assistant

A custom integration that connects to your iCloud contacts via CardDAV and displays birthdays as a native Home Assistant calendar. Works with all HA calendar cards including **Calendar Card Pro**.

## Features

- Fetches birthdays directly from your iCloud contacts
- Native HA `calendar` entity - works with any calendar card
- Event titles like *"John turns 35"* (age display optional)
- All-day yearly events - no manual maintenance
- Configurable via the HA UI (no YAML needed)
- Refreshes every hour

## Requirements

- Home Assistant 2023.5.0 or newer
- An iCloud account with contacts that have birthdays set
- An **app-specific password** from Apple (not your regular Apple ID password)

## Installation via HACS

1. Open HACS in your Home Assistant
2. Go to **Integrations**
3. Click the three dots (⋮) → **Custom repositories**
4. Add this repository URL and select category **Integration**
5. Search for "Birthday Calendar" and install
6. Restart Home Assistant

## Manual Installation

1. Download the `custom_components/birthday_calendar` folder from this repository
2. Copy it to your HA config directory: `config/custom_components/birthday_calendar/`
3. Restart Home Assistant

## Setup

### Step 1: Create an App-Specific Password

1. Go to [appleid.apple.com](https://appleid.apple.com)
2. Sign in → **Sign-In and Security** → **App-Specific Passwords**
3. Click **+** and give it a name like `Home Assistant`
4. Copy the generated password (format: `xxxx-xxxx-xxxx-xxxx`)

### Step 2: Add the Integration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **Birthday Calendar**
3. Fill in:
   - **Apple ID**: your iCloud email address
   - **App-Specific Password**: the password from Step 1
   - **CardDAV URL**: leave as `https://contacts.icloud.com` for iCloud
4. Click **Submit**

## Using with Calendar Card Pro

Once the integration is set up, a `calendar.birthdays` entity is created. Add it to Calendar Card Pro like any other calendar:

```yaml
type: custom:calendar-card-pro
entities:
  - calendar.birthdays
```

## Options

After setup, click **Configure** on the integration to adjust:

| Option | Default | Description |
|---|---|---|
| Days ahead | 365 | How many days ahead to load birthdays |
| Show age | Yes | Show "turns X" in event title |

## Entity Attributes

The calendar entity exposes extra attributes you can use in automations:

```yaml
birthdays:
  - name: "John Doe"
    birthday: "03-15"
    next_birthday: "2025-03-15"
    days_until: 47
    year_of_birth: 1985
    age_next_birthday: 40
total_count: 12
```

### Example Automation

Send a notification 7 days before a birthday:

```yaml
alias: Birthday reminder
trigger:
  - platform: template
    value_template: >
      {{ state_attr('calendar.birthdays', 'birthdays') | 
         selectattr('days_until', 'equalto', 7) | list | count > 0 }}
action:
  - service: notify.mobile_app
    data:
      message: >
        {{ state_attr('calendar.birthdays', 'birthdays') | 
           selectattr('days_until', 'equalto', 7) | 
           map(attribute='name') | join(', ') }} has a birthday in 7 days!
```

## Using with Other CardDAV Servers

The integration also works with other CardDAV servers (Nextcloud, Fastmail, etc.). Just change the URL in the setup:

| Provider | URL |
|---|---|
| iCloud | `https://contacts.icloud.com` |
| Nextcloud | `https://your-nextcloud.com/remote.php/dav` |
| Fastmail | `https://carddav.fastmail.com` |

## Troubleshooting

**"Cannot connect"** - Check your CardDAV URL and internet connection.

**"Invalid auth"** - Make sure you're using an app-specific password, not your Apple ID password.

**No birthdays showing** - Check that your contacts have a birthday date set in iCloud Contacts.

**Wrong age** - Some contacts may have birthdays stored without a year (`--MM-DD` format). The integration handles this by omitting the age for those contacts.

Check the HA logs for more details: **Settings** → **System** → **Logs**, filter on `birthday_calendar`.
