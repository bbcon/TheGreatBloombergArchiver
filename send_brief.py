#!/usr/bin/env python3
"""
send_brief.py — Format and email Bloomberg regional macro summaries.

Usage:
    python3 send_brief.py --mode daily   --date 2026-05-25
    python3 send_brief.py --mode weekly  --date 2026-05-18   # any date in the week
    python3 send_brief.py --mode monthly --date 2026-04-01   # any date in the month
    python3 send_brief.py --mode daily   --date 2026-05-25 --preview
"""

import os
import re
import sys
import smtplib
import argparse
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import anthropic
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
SUMMARIES_DIR = BASE_DIR / "summaries"
STATE_DIR = BASE_DIR / "state"
ISSUE_FILE = STATE_DIR / "issue_number.txt"

REGIONS = ["US", "Asia", "Europe", "Global"]

REGION_COLORS = {
    "US":     "#5597cb",
    "Asia":   "#e07b39",
    "Europe": "#4a9e6b",
    "Global": "#8b5cf6",
}


# ── Issue number ──────────────────────────────────────────────────────────────

def get_issue_number() -> int:
    if ISSUE_FILE.exists():
        return int(ISSUE_FILE.read_text().strip())
    return 1


def increment_issue_number():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ISSUE_FILE.write_text(str(get_issue_number() + 1))


# ── File paths ────────────────────────────────────────────────────────────────

def summary_folder(mode: str, date: datetime) -> Path:
    if mode == "daily":
        return SUMMARIES_DIR / "daily" / date.strftime("%Y/%m/%d")
    elif mode == "weekly":
        monday = date - timedelta(days=date.weekday())
        _, iso_week, _ = monday.isocalendar()
        return SUMMARIES_DIR / "weekly" / str(monday.year) / f"W{iso_week:02d}"
    else:  # monthly
        return SUMMARIES_DIR / "monthly" / date.strftime("%Y/%m")


def load_region(folder: Path, region: str) -> str:
    path = folder / f"{region}.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


# ── Markdown parsing ──────────────────────────────────────────────────────────

def bold_to_strong(text: str) -> str:
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)


def parse_paragraphs(text: str) -> list[tuple[str | None, str]]:
    """Parse markdown into (title, body) pairs.
    Handles:
      - '## Title'
      - '**Title**' alone on a line
      - '**Title.** Body text...' on a single line (model often writes this)
    """
    lines = text.splitlines()
    # Drop top-level heading
    if lines and lines[0].startswith("# "):
        lines = lines[1:]

    pairs: list[tuple[str | None, str]] = []
    current_title: str | None = None
    current_body: list[str] = []

    def flush():
        if current_body:
            pairs.append((current_title, " ".join(current_body)))

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # ## Section header
        if line.startswith("## "):
            flush()
            current_title = line[3:].strip()
            current_body = []

        # **Title** alone on its own line
        elif re.match(r'^\*\*[^*]+\*\*[.:]?$', line):
            flush()
            current_title = re.sub(r'^\*\*|\*\*[.:]?$', '', line)
            current_body = []

        # **Title.** Body text on the same line — split them
        elif m := re.match(r'^\*\*([^*]+)\*\*[.:]?\s+(.+)', line):
            flush()
            current_title = m.group(1).rstrip('.:')
            current_body = [m.group(2)]

        else:
            current_body.append(line)

    flush()
    return pairs


def estimate_reading_time(text: str) -> int:
    return max(1, round(len(text.split()) / 200))


# ── HTML building ─────────────────────────────────────────────────────────────

def get_logo_html(size: int = 40) -> str:
    scale = size / 40
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="width:{size}px;height:{size}px;background-color:#1a1a2e;'
        f'border-radius:{size // 2}px;">'
        f'<tr><td align="center" valign="middle" '
        f'style="font-family:Georgia,serif;font-size:{int(22*scale)}px;'
        f'font-weight:bold;color:#ffffff;line-height:1;">M</td></tr></table>'
    )


def region_html(region: str, text: str) -> str:
    color = REGION_COLORS[region]
    pairs = parse_paragraphs(text)

    body_html = ""
    for title, body in pairs:
        if title:
            body_html += (
                f'<p style="margin:0 0 5px 0;font-size:11px;font-weight:700;'
                f'text-transform:uppercase;letter-spacing:1.2px;color:{color};">'
                f'{title}</p>'
            )
        body_html += (
            f'<p style="margin:0 0 18px 0;font-size:15px;line-height:1.75;color:#333333;">'
            f'{bold_to_strong(body)}</p>'
        )

    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin-bottom:36px;">'
        f'<tr><td style="border-left:3px solid {color};padding-left:20px;">'
        f'<h2 style="margin:0 0 16px 0;font-size:13px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:2px;color:{color};">{region}</h2>'
        f'{body_html}'
        f'</td></tr></table>'
    )


def generate_bullets(summaries: dict[str, str], mode: str) -> list[str]:
    """Ask Claude for 5 key bullets from the combined regional summaries."""
    combined = "\n\n".join(f"=== {r} ===\n{t}" for r, t in summaries.items())
    period = {"daily": "today", "weekly": "this week", "monthly": "this month"}[mode]
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                f"From the macro summaries below, extract exactly 5 key bullet points "
                f"covering the most important developments {period} across all regions. "
                f"Each bullet must be one concise sentence (max 20 words). "
                f"No bold, no markdown, no numbering — plain sentences only.\n\n{combined}"
            ),
        }],
    )
    lines = [l.strip().lstrip("•-– ") for l in msg.content[0].text.splitlines() if l.strip()]
    return lines[:5]


def bullets_html(bullets: list[str]) -> str:
    items = "".join(
        f'<tr><td style="padding:0 0 10px 0;vertical-align:top;width:18px;">'
        f'<span style="color:#5597cb;font-weight:700;font-size:15px;">›</span></td>'
        f'<td style="padding:0 0 10px 12px;font-size:14px;line-height:1.6;color:#222222;">'
        f'{b}</td></tr>'
        for b in bullets
    )
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:0;">{items}</table>'
    )


def build_html(mode: str, date: datetime, summaries: dict[str, str], issue_num: int,
               bullets: list[str]) -> str:
    if mode == "daily":
        title_line = "The Daily Macro Brief"
        subtitle = date.strftime("%B %d, %Y")
        period_label = date.strftime("%A")
        tagline = "What moved markets today, by order of importance."
        farewell = "Thanks for reading. See you tomorrow."
    elif mode == "weekly":
        monday = date - timedelta(days=date.weekday())
        sunday = monday + timedelta(days=6)
        title_line = "The Weekly Macro Brief"
        subtitle = f"Week of {monday.strftime('%B %d')}–{sunday.strftime('%B %d, %Y')}"
        period_label = "Weekly Digest"
        tagline = "What moved markets this week, by order of importance."
        farewell = "Thanks for reading. See you next week."
    else:
        title_line = "The Monthly Macro Brief"
        subtitle = date.strftime("%B %Y")
        period_label = "Monthly Review"
        tagline = "The dominant macro themes of the month."
        farewell = "Thanks for reading. See you next month."

    all_text = " ".join(summaries.values())
    reading_time = estimate_reading_time(all_text)
    bullets_block = bullets_html(bullets)

    regions_html = "".join(
        region_html(r, summaries[r]) for r in REGIONS if r in summaries
    )

    logo = get_logo_html(40)
    logo_small = get_logo_html(32)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_line} | {subtitle}</title>
</head>
<body style="margin:0;padding:0;background-color:#f5f5f5;
             font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background-color:#f5f5f5;">
  <tr><td align="center" style="padding:40px 20px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="max-width:680px;background-color:#ffffff;
                  box-shadow:0 2px 8px rgba(0,0,0,0.08);">

      <!-- Header -->
      <tr><td style="background-color:#040505;padding:32px 48px 28px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="width:50px;vertical-align:top;">{logo}</td>
            <td style="padding-left:16px;vertical-align:middle;">
              <p style="margin:0 0 4px 0;font-size:11px;letter-spacing:3px;
                        text-transform:uppercase;color:#5597cb;font-weight:500;">{title_line}</p>
              <h1 style="margin:0;font-size:26px;font-weight:300;color:#ffffff;
                         line-height:1.2;letter-spacing:-0.5px;">{subtitle}</h1>
            </td>
            <td align="right" valign="top" style="padding-top:4px;">
              <p style="margin:0 0 4px 0;font-size:10px;letter-spacing:1.5px;
                        text-transform:uppercase;color:#666666;">{period_label}</p>
              <p style="margin:0;font-size:10px;letter-spacing:1px;color:#5597cb;">
                Issue #{issue_num}</p>
              <p style="margin:4px 0 0 0;font-size:10px;color:#666666;">
                {reading_time} min read</p>
            </td>
          </tr>
        </table>
      </td></tr>

      <!-- Accent line -->
      <tr><td style="background:linear-gradient(90deg,#5597cb 0%,#aac3e3 100%);
                     height:3px;"></td></tr>

      <!-- Key bullets -->
      <tr><td style="padding:28px 48px 24px;border-bottom:1px solid #e8e8e8;">
        <p style="margin:0 0 14px 0;font-size:10px;font-weight:700;letter-spacing:2px;
                  text-transform:uppercase;color:#aaaaaa;">Key developments</p>
        {bullets_block}
      </td></tr>

      <!-- Regional content -->
      <tr><td style="padding:36px 48px;">
        {regions_html}
      </td></tr>

      <!-- Farewell -->
      <tr><td style="padding:0 48px 40px;text-align:center;">
        <p style="margin:0;font-size:14px;color:#888888;font-style:italic;">{farewell}</p>
      </td></tr>

      <!-- Footer -->
      <tr><td style="background-color:#040505;padding:36px 48px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="width:40px;vertical-align:top;">{logo_small}</td>
            <td style="padding-left:14px;">
              <p style="margin:0 0 4px 0;font-size:10px;letter-spacing:2px;
                        text-transform:uppercase;color:#5597cb;">{title_line}</p>
              <p style="margin:0;font-size:12px;color:#666666;line-height:1.5;">
                Cut through the noise. Get the macro story fast.</p>
            </td>
          </tr>
        </table>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


# ── Email sending ─────────────────────────────────────────────────────────────

def send_email(subject: str, html: str, plain: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = os.environ["EMAIL_FROM"]
    msg["To"] = os.environ["EMAIL_TO"]
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(os.environ["SMTP_SERVER"], int(os.environ["SMTP_PORT"])) as srv:
        srv.starttls()
        srv.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        srv.sendmail(os.environ["EMAIL_FROM"], os.environ["EMAIL_TO"], msg.as_string())


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Email Bloomberg macro brief.")
    parser.add_argument("--mode", choices=["daily", "weekly", "monthly"], required=True)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--preview", action="store_true",
                        help="Save HTML to previews/ instead of sending")
    args = parser.parse_args()

    date = datetime.strptime(args.date, "%Y-%m-%d")
    folder = summary_folder(args.mode, date)

    summaries = {r: load_region(folder, r) for r in REGIONS}
    summaries = {r: t for r, t in summaries.items() if t}

    if not summaries:
        print(f"No summaries found in {folder}")
        sys.exit(1)

    issue_num = get_issue_number()
    print("Generating key bullets...", end=" ", flush=True)
    bullets = generate_bullets(summaries, args.mode)
    print("done.")
    html = build_html(args.mode, date, summaries, issue_num, bullets)

    if args.mode == "daily":
        subject = f"Daily Macro Brief — {date.strftime('%A, %B %d, %Y')}"
    elif args.mode == "weekly":
        monday = date - timedelta(days=date.weekday())
        subject = f"Weekly Macro Brief — Week of {monday.strftime('%B %d, %Y')}"
    else:
        subject = f"Monthly Macro Brief — {date.strftime('%B %Y')}"

    plain = "\n\n".join(
        f"=== {r} ===\n{summaries[r]}" for r in REGIONS if r in summaries
    )

    if args.preview:
        out_dir = BASE_DIR / "previews"
        out_dir.mkdir(exist_ok=True)
        out = out_dir / f"preview_{args.mode}_{args.date}.html"
        out.write_text(html, encoding="utf-8")
        print(f"Preview saved → {out.relative_to(BASE_DIR)}")
        return

    print(f"Sending: {subject} ...", end=" ", flush=True)
    send_email(subject, html, plain)
    increment_issue_number()
    print(f"done (Issue #{issue_num}).")


if __name__ == "__main__":
    main()
