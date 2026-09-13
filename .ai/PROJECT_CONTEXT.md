# PROJECT_CONTEXT.md

## Project name

Anime Tracker Bot - @Anime1st_bot

## Goal

A Telegram bot that tracks serialized anime across multiple source channels.
For each anime it creates a forum topic in the management group, watches the
assigned source channels on a schedule, detects new episodes by matching any
of the anime aliases and parsing the episode number, and posts the original
message link into the anime topic with a NEW badge. Duplicates are stored in
SQLite so each episode is posted once.

## Tech stack

- Language: Python 3.11+
- Telegram client: Telethon for reading channels with a user session
- Posting and topics: Telethon
- Database: SQLite
- Scheduler: APScheduler or asyncio loop
- Config: .env for secrets, config/animes.json for watch list

## Credentials location

All secrets live in .env which is gitignored.
The agent must read secrets from environment variables only.
Never print or commit secrets.

## Management group

Group name: Anime List
Topics: enabled
The bot must be admin with Manage Topics and Post Messages rights.

## Important commands

Install dependencies:
pip install -r requirements.txt

Create Telethon session, run manually once:
python scripts/telethon_login.py

Run the bot:
python -m src.main

## Important notes

- Source channels must be joined by the user account used for Telethon.
- Episode link format: https://t.me/CHANNEL/MSGID
- Keep database schema user_id ready for a future multi-tenant product.
