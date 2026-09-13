# TASKS.md - Task List

## Backlog

### T001 - Project skeleton and storage

Status: todo
Priority: high
Acceptance criteria:
- src package with config loader reading .env
- SQLite schema: animes, aliases, channels, episodes, topics
- config/animes.json loader with validation
- No secrets printed or hardcoded

### T002 - Telethon login script

Status: todo
Priority: high
Acceptance criteria:
- scripts/telethon_login.py connects with API_ID and API_HASH from .env
- Saves session file anime_tracker.session
- Prints success message after login

### T003 - Alias matching and episode parser

Status: todo
Priority: high
Acceptance criteria:
- Normalize titles: lowercase, strip punctuation and spaces
- Match any alias inside channel post text
- Parse episode numbers from EP12, Episode 12, [12], S01E12, #12 and CJK forms
- Unit tests cover all listed formats

### T004 - Scheduled channel scanner

Status: todo
Priority: high
Acceptance criteria:
- Iterate animes and their channels every interval from .env
- Read recent posts since last check cursor per channel
- Handle channel not accessible gracefully with a log entry

### T005 - New episode detection and dedupe

Status: todo
Priority: high
Acceptance criteria:
- Store seen episodes keyed by anime id and episode number
- Skip posts already stored
- Record message id and channel for link building

### T006 - Topic creation and posting

Status: todo
Priority: high
Acceptance criteria:
- Create one forum topic per anime in group Anime List if missing
- Post episode link https://t.me/CHANNEL/MSGID into the topic
- Mark first-seen episodes with a NEW badge
- Update TASKS and PROGRESS after completion

### T007 - Management commands

Status: todo
Priority: medium
Acceptance criteria:
- /add_anime with title and aliases
- /add_channel to attach a channel to an anime
- /list shows animes with topic and channel counts
- /set_interval changes check interval

## In progress

None

## Done

None
