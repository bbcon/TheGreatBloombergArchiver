# TheGreatBloombergArchiver

## What this project does
A fully automated Bloomberg email archiver + summarizer + static website.

1. **`fetch.py`** — Pulls Bloomberg emails from Gmail via OAuth2 and saves them as `.txt` files organized by `YYYY/MM/DD/`.
2. **`summarize.py`** — Reads the archived emails and generates five regional macro briefings (US, Asia, Europe, LatAm, Global) via the Claude API, written in Goldman Sachs institutional-research style.
3. **`send_brief.py`** — Formats the summaries as HTML email and sends them via SMTP (Gmail).
4. **`build_site.py`** — Builds a static GitHub Pages site from all summaries in `docs/`.
5. **`run.sh`** — Local cron entry point (not used in production; GitHub Actions is the production runner).

---

## Project structure
```
TheGreatBloombergArchiver/
├── fetch.py              # Gmail fetcher
├── summarize.py          # Claude summarizer (daily / weekly / monthly)
├── send_brief.py         # HTML email sender
├── build_site.py         # Static site generator → docs/
├── run.sh                # Local cron wrapper (dev only)
├── credentials.json      # Google OAuth credentials (never commit)
├── token.json            # Auto-generated after first auth (never commit)
├── .env                  # API keys + SMTP config (never commit)
├── saved_ids.txt         # De-dup index of fetched Gmail message IDs
├── state/
│   └── issue_number.txt  # Monotonically incrementing email issue number
├── summaries/
│   ├── daily/YYYY/MM/DD/{US,Asia,Europe,LatAm,Global}.md
│   ├── weekly/YYYY/Www/{US,Asia,Europe,LatAm,Global}.md
│   └── monthly/YYYY/MM/{US,Asia,Europe,LatAm,Global}.md
├── research/             # Ad-hoc topic briefings (YYYY-MM-DD_topic.md)
├── docs/                 # GitHub Pages output
│   ├── index.html
│   ├── daily.html
│   ├── weekly.html
│   ├── monthly.html
│   ├── daily/YYYY-MM-DD.html
│   ├── weekly/YYYY-Www.html
│   └── monthly/YYYY-MM.html
├── YYYY/MM/DD/           # Raw email .txt files (e.g. 2026/05/25/)
└── .github/workflows/
    └── daily_brief.yml   # Production runner (GitHub Actions)
```

---

## Regions

Five regions are generated for every summary period:

| Region | Coverage |
|--------|----------|
| **US** | US macro data (GDP, CPI, employment, PMIs) vs consensus; Fed; fiscal/political; equities; corporates |
| **Asia** | China, Japan, South Korea, India, Southeast Asia, Australia — data, policy, markets, geopolitics |
| **Europe** | Eurozone + UK macro data; ECB and BoE; individual economies; European corporates |
| **LatAm** | Brazil, Mexico, Argentina, Colombia, Chile — data, central banks, commodities, FX, political economy |
| **Global** | Cross-cutting: oil/energy, Hormuz, global monetary policy divergence, geopolitics, climate/energy transition |

---

## Summarize prompt philosophy

Summaries follow a **top-down, economics-first** structure:
1. **Lead with macro data releases** — specific numbers, whether they beat/missed consensus.
2. **Markets follow economics** — market moves are contextualized against the economic picture.
3. **GS research style** — measured, analytical, precise; hedges uncertainty; distinguishes fact from interpretation.

---

## GitHub Actions workflow (production)

**File:** `.github/workflows/daily_brief.yml`

**Schedule:**
- Mon–Fri at 13:15 CEST (11:15 UTC): fetch + daily summary + send
- Saturday at 13:15 CEST (11:15 UTC): fetch + daily summary (generated but not sent) + weekly summary + send; also monthly if last day
- Note: clocks shift in winter (CET = UTC+1), so the local time becomes 12:15 CET in winter.

**What runs each day:**
1. Install deps, write secrets to disk
2. `fetch.py` — pull new Gmail messages
3. `summarize.py --mode daily` — generate daily regional summaries (`continue-on-error: true`)
4. `send_brief.py --mode daily` — send if step 3 succeeded
5. *(Saturday only)* `summarize.py --mode weekly --force` + send
6. *(Last day of month, or Saturday when Sunday is last day)* `summarize.py --mode monthly --force` + send
7. `build_site.py` — rebuild `docs/`
8. `git commit` + `git push` — deploy to GitHub Pages

**Key design notes:**
- `--force` is required for weekly/monthly because `summarize.py` refuses to run on an incomplete period, and Saturday's week ends Sunday (period_end > today).
- Monthly is generated on the last calendar day of the month. If that day is a Sunday (no workflow run), Saturday's run catches it by checking if tomorrow is the last day.
- Each summary step has `continue-on-error: true` so a day with no Bloomberg emails doesn't abort the site build/push.
- Saturday condition uses `github.event.schedule == '15 11 * * 6'` to gate the weekly/monthly steps.

**GitHub Pages setup (one-time):**
Go to repo Settings → Pages → Source: "Deploy from a branch" → Branch: `main` → Folder: `/docs`.
URL: `https://bbcon.github.io/TheGreatBloombergArchiver/`

---

## Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `GMAIL_CREDENTIALS_JSON` | Contents of `credentials.json` (Google OAuth app credentials) |
| `GMAIL_TOKEN_JSON` | Contents of `token.json` (OAuth refresh token — refresh manually if expired) |
| `ANTHROPIC_API_KEY` | Claude API key |
| `SMTP_USERNAME` | Gmail address used to send emails |
| `SMTP_PASSWORD` | Gmail app password (not account password) |

---

## Local development

```bash
# Install deps
python3 -m pip install google-auth google-auth-oauthlib google-api-python-client anthropic python-dotenv

# Fetch emails (first run opens OAuth browser flow)
python3 fetch.py

# Generate today's daily summary
python3 summarize.py --date 2026-05-29 --mode daily

# Send daily email
python3 send_brief.py --mode daily --date 2026-05-29

# Preview email in browser (no send)
python3 send_brief.py --mode daily --date 2026-05-29 --preview

# Rebuild site
python3 build_site.py
```

---

## Key design decisions
- Email files are named by Gmail message ID (guarantees uniqueness; de-dup via `saved_ids.txt`)
- `summarize.py` reads emails → daily; daily summaries → weekly; weekly summaries → monthly (hierarchical)
- Plain text body only (no HTML parsing of emails)
- `--force` flag overrides the period-completeness guard in weekly/monthly modes
- Output committed to `docs/` on `main` branch drives GitHub Pages (branch-based, not Actions-based deployment)
- `research/` folder holds ad-hoc topic briefings; naming convention `YYYY-MM-DD_topic.md`

---

## Environment
- Python 3.13
- macOS (M1) for local dev; Ubuntu (GitHub Actions) for production
- `.venv` virtualenv for local use

## Secrets
`credentials.json`, `token.json`, and `.env` must never be committed to git (covered by `.gitignore`).
