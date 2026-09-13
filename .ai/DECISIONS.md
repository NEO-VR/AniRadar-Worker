# DECISIONS.md - Project Decisions

## D001 - Local AI project management

Use .ai folder for plan, tasks, progress and decisions so any agent session
can continue from disk.

## D002 - Matt Pocock skills

Use shared skills for grilling, TDD and code review.

## D003 - Telethon user session for reading

Bots cannot read channels where they are not admin. A user session via
Telethon reads any joined channel, which fits personal use.
For the future product, offer bot-admin mode per customer.

## D004 - Multi-tenant ready schema

All tables carry user_id from day one so the sellable version needs no
schema migration.

## D005 - Secrets only in .env

.env is gitignored. The agent reads secrets from environment variables and
never writes them into code or logs.
