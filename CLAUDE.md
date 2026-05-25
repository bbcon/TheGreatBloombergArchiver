# TheGreatBloombergArchiver

## What this project does
A Python script that automatically fetches Bloomberg emails from Gmail and saves them as `.txt` files, organized by date in a `Year/Month/Day` folder structure.

## Project structure
```
TheGreatBloombergArchiver/
├── fetch.py              # Main script
├── credentials.json      # Google OAuth credentials (do not commit)
├── token.json            # Auto-generated after first auth (do not commit)
├── CLAUDE.md             # This file
└── 2026/
    └── 05/
        └── 25/
            └── <gmail_message_id>.txt
```

## How it works
1. Authenticates with Gmail API via OAuth2 (credentials stored in `token.json` after first run)
2. Queries Gmail for emails from `bloomberg.com`
3. Saves each email as a `.txt` file named by Gmail message ID (prevents duplicates)
4. Organizes files into `YYYY/MM/DD/` subfolders based on email date
5. Skips emails already saved on previous runs

## Key design decisions
- Files are named by Gmail message ID (not subject) to guarantee uniqueness
- Duplicate check is a simple `os.path.exists()` on the filepath
- Output is saved in the project directory itself (`BASE_DIR`), not `~/Bloomberg_Emails/`
- `maxResults=100` per run — increase if Bloomberg sends more than 100 emails per day
- Plain text body only (no HTML)

## Environment
- Python 3 with virtualenv (`.venv`)
- macOS (M1)
- Dependencies: `google-auth`, `google-auth-oauthlib`, `google-api-python-client`

## Install dependencies
```bash
python3 -m pip install google-auth google-auth-oauthlib google-api-python-client
```

## Run
```bash
python3 fetch.py
```

First run opens a browser for Google OAuth login. Subsequent runs are fully automatic.

## Automation
Intended to run daily via cron (not yet configured). Target: every morning at 7am.

## Secrets
- `credentials.json` and `token.json` must never be committed to git
- Add both to `.gitignore`