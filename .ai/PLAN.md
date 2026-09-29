# PLAN.md - Project Roadmap

## Main objective

Ship a personal anime tracking Telegram bot, then harden it into a sellable product.

## Phase 1 - Personal MVP

- [x] T001 Project skeleton, config loader, SQLite schema
- [x] T002 Telethon interactive login script
- [x] T003 Alias model and episode number parser
- [x] T004 Channel scanner on a schedule
- [x] T005 New episode detection with dedupe
- [x] T006 Auto topic creation and NEW badge posting
- [x] T007 Bot commands: add_anime, add_channel, list, set_interval

## Phase 2 - Comfort features

- [ ] AniList integration for aliases and poster icons
- [ ] Inline buttons: watched, mute
- [ ] Weekly digest message
- [ ] Next episode date prediction
- [ ] Multi-source listing for one episode

## Phase 3 - Hardening

- [ ] Logging and reconnect handling
- [ ] Tests for parser and matcher
- [ ] Two weeks of real running

## Phase 4 - Productization

- [ ] Multi-tenant schema and onboarding
- [ ] Telegram Stars payments
- [ ] Admin panel and setup guide
- [ ] Public demo group