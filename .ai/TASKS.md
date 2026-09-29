# TASKS.md - Task List

## Backlog

### T001 - Project skeleton and storage

Status: done
Priority: high
Acceptance criteria:
- src package with config loader reading .env
- SQLite schema: animes, aliases, channels, episodes, topics
- config/animes.json loader with validation
- No secrets printed or hardcoded

### T002 - Telethon login script

Status: done
Priority: high
Acceptance criteria:
- scripts/telethon_login.py connects with API_ID and API_HASH from .env
- Saves session file anime_tracker.session
- Prints success message after login

### T003 - Alias matching and episode parser

Status: done
Priority: high
Acceptance criteria:
- Normalize titles: lowercase, strip punctuation and spaces
- Match any alias inside channel post text
- Parse episode numbers from EP12, Episode 12, [12], S01E12, #12 and CJK forms
- Unit tests cover all listed formats

### T004 - Scheduled channel scanner

Status: done
Priority: high
Acceptance criteria:
- Iterate animes and their channels every interval from .env
- Read recent posts since last check cursor per channel
- Handle channel not accessible gracefully with a log entry

### T005 - New episode detection and dedupe

Status: done
Priority: high
Acceptance criteria:
- Store seen episodes keyed by anime id and episode number
- Skip posts already stored
- Record message id and channel for link building

### T006 - Topic creation and posting

Status: done
Priority: high
Acceptance criteria:
- Create one forum topic per anime in group Anime List if missing
- Post episode link https://t.me/CHANNEL/MSGID into the topic
- Mark first-seen episodes with a NEW badge
- Update TASKS and PROGRESS after completion

### T007 - Management commands

Status: done
Priority: medium
Acceptance criteria:
- /add_anime with title and aliases
- /add_channel to attach a channel to an anime
- /list shows animes with topic and channel counts
- /set_interval changes check interval

## In progress

None

## Done

### T001 - Project skeleton and storage

Completed: 2026-09-22
- src/config.py with Pydantic Settings
- src/database.py with async SQLite (aiosqlite) and soft-delete
- src/anime_loader.py with Pydantic validation
- tests/test_t001.py with 13 passing tests
- .env.example with all required vars

### T002 - Telethon interactive login script

Completed: 2026-09-22
- scripts/telethon_login.py created
- Uses settings from config.py

### T003 - Alias matching and episode parser

Completed: 2026-09-22
- src/parser.py with comprehensive episode parsing
- Supports EP, Episode, bracketed, S##E##, #, CJK (Japanese/Chinese/Korean)
- Alias matching with normalization
- 32 passing tests in tests/test_parser.py

### T004 - Scheduled channel scanner

Completed: 2026-09-22
- src/bot.py with AnimeTrackerBot class
- Runs scan cycle every CHECK_INTERVAL seconds
- Handles FloodWait and channel access errors

### T005 - New episode detection and dedupe

Completed: 2026-09-22
- Uses is_episode_seen() and record_episode() from database
- Deduplicates by anime_id + episode_number
- Records message_id and channel for link building

### T006 - Topic creation and posting

Completed: 2026-09-22
- Creates forum topic per anime using CreateForumTopicRequest
- Posts episode link to topic with NEW badge for high-confidence matches
- Stores topic_id in database for reuse

### T007 - Management commands

Completed: 2026-09-22
- src/commands.py with handlers for /start, /help, /list, /add_anime, /add_channel, /set_interval
- Commands registered in bot startup
- Admin authorization support
- Updates both database and config/animes.json