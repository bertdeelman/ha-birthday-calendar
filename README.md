# CardDAV Birthday Calendar for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/bertdeelman/ha-birthday-calendar)](https://github.com/bertdeelman/ha-birthday-calendar/releases)
[![GitHub Downloads](https://img.shields.io/github/downloads/bertdeelman/ha-birthday-calendar/total)](https://github.com/bertdeelman/ha-birthday-calendar/releases)
[![Stars](https://img.shields.io/github/stars/bertdeelman/ha-birthday-calendar)](https://github.com/bertdeelman/ha-birthday-calendar/stargazers)
[![Issues](https://img.shields.io/github/issues/bertdeelman/ha-birthday-calendar)](https://github.com/bertdeelman/ha-birthday-calendar/issues)
[![Last Commit](https://img.shields.io/github/last-commit/bertdeelman/ha-birthday-calendar)](https://github.com/bertdeelman/ha-birthday-calendar/commits)
[![License](https://img.shields.io/github/license/bertdeelman/ha-birthday-calendar)](LICENSE)

A Home Assistant custom integration that reads birthdays and custom dates from your **iCloud Contacts** via CardDAV and exposes them as a native HA calendar entity. Compatible with all Home Assistant calendar cards.

---

## Features

- Reads birthdays and custom dates (anniversary, memorial day, etc.) from iCloud Contacts via CardDAV
- Native Home Assistant calendar entity
- Yearly recurring all-day events
- Configurable language: English or Dutch
- Configurable event title with or without age
- Compatible with all Home Assistant calendar cards

## Installation

### Via HACS (recommended)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bertdeelman&repository=ha-birthday-calendar&category=integration)

1. HACS → Integrations → Custom repositories
2. Add `https://github.com/bertdeelman/ha-birthday-calendar` as **Integration**
3. Download **CardDAV Birthday Calendar**
4. Restart Home Assistant

### Manual

Copy `custom_components/carddav_birthday_calendar` to your HA `custom_components` folder and restart.

## Setup

1. Settings → Devices & Services → Add Integration → **CardDAV Birthday Calendar**
2. Enter your **Apple ID** (email address)
3. Enter an **app-specific password** — not your regular Apple ID password!
   - Create one at [appleid.apple.com](https://appleid.apple.com) → Sign-In and Security → App-Specific Passwords

## Configuration

After setup, click **Configure** on the integration to set:

- **Language** — English or Dutch
- **Show age** — Include age in the event title
- **Days ahead** — How far ahead to load events (default: 365)

## Event title examples

| Language | With age | Without age |
|----------|----------|-------------|
| English  | Emma birthday (32) | Emma birthday |
| Dutch    | Emma birthday (32) | Emma birthday |
| Custom   | Thomas and Lisa anniversary | Grandpa memorial day |

## Credits

Inspired by [MMM-CalDAV](https://github.com/MMRIZE/MMM-CalDAV) by MMRIZE.
