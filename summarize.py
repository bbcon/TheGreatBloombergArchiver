#!/usr/bin/env python3
"""
summarize.py — Generate regional Bloomberg summaries using the Claude API.

Usage:
    python3 summarize.py --date 2026-05-25 --mode daily
    python3 summarize.py --date 2026-05-25 --mode weekly   # week containing date
    python3 summarize.py --date 2026-05-25 --mode monthly  # month containing date
    python3 summarize.py --date 2026-05-25 --mode daily --region Asia

Requires ANTHROPIC_API_KEY in environment.
"""

import os
import re
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
SUMMARIES_DIR = BASE_DIR / "summaries"

REGIONS = {
    "US": (
        "United States — US macro data releases (GDP, inflation, employment, PMIs) and whether they beat "
        "or missed consensus, Federal Reserve and monetary policy, US politics and fiscal policy, "
        "US equity and credit markets, and US corporate news."
    ),
    "Asia": (
        "Asia-Pacific — macro data releases and consensus surprises for China, Japan, South Korea, India, "
        "and Southeast Asia; central bank policy; capital flows and currency moves; "
        "equity and credit markets; corporate news; and geopolitics."
    ),
    "Europe": (
        "Europe — eurozone and country-level macro data (GDP, CPI, PMIs, unemployment) versus consensus, "
        "ECB and Bank of England policy, UK politics, individual European economies, "
        "and European corporate news."
    ),
    "LatAm": (
        "Latin America — macro data releases and consensus surprises for Brazil, Mexico, Argentina, Colombia, "
        "Chile, and the broader region; central bank policy; commodity dynamics; currency moves; "
        "equity markets; and political economy developments."
    ),
    "Global": (
        "Global — cross-cutting themes that span multiple regions: oil markets and energy, "
        "the US-Iran conflict and Strait of Hormuz, global monetary policy divergence, "
        "geopolitics, climate/energy transition, and macro trends that don't fit neatly into one region."
    ),
}

SYSTEM_PROMPT = """\
You are a senior macro analyst writing institutional research for sophisticated professional investors, \
in the style of Goldman Sachs research. Your tone is measured, analytical, and precise.

Structure and emphasis:
- Lead with economics. For each region, begin with the most important macro data releases of the period — \
GDP, inflation, employment, PMIs, trade — and explicitly state whether each print beat, missed, or met \
consensus. Use specific numbers: "CPI rose 3.8% YoY, above the 3.5% consensus." Economic momentum and \
data surprises are the primary story.
- Markets follow macro. After economic data, cover market developments (equities, rates, credit, FX) and \
what they signal about the economic picture. Market moves without an economic anchor are less useful.
- Top-down framing: start from the macro environment, then what it implies for sectors, assets, and policy.

Writing guidelines:
- Neutral, analytical language by default: fell/rose, declined/gained, increased/decreased.
- Use strong words (historic, unprecedented, crisis) only when genuinely warranted — not for \
routine market moves. Let data speak for itself.
- Ensure macro consistency. Think through cause and effect: if X happens, what does it imply for Y? \
Do not combine contradictory narratives — acknowledge tensions explicitly.
- Acknowledge uncertainty. Do not declare outcomes resolved when they remain uncertain. Use hedging \
language: "appears to," "may signal," "remains to be seen."
- Distinguish facts from interpretation. Separate what happened from what it might mean.
- Avoid false narrative closure. Reality is messy — be comfortable with ambiguity.
- No sensationalism. Sophisticated readers find unnecessary hyperbole off-putting.
- Deliver content directly. No meta-text, no caveats about the summary itself.\
"""


def clean_email(text: str) -> str:
    """Strip Bloomberg boilerplate, tracker characters, and URL noise from raw email text."""
    # Remove zero-width non-joiners used as email layout fillers
    text = text.replace("‌", "")

    # Remove bare URLs in angle brackets (inline links)
    text = re.sub(r"<https?://[^>]+>", "", text)

    lines = [line.rstrip() for line in text.splitlines()]

    # Cut off at boilerplate sections (footer, unsubscribe, follow us)
    cutoff_patterns = re.compile(
        r"^(You received this message"
        r"|Unsubscribe"
        r"|Follow Us"
        r"|More [Ff]rom Bloomberg"
        r"|Enjoying .+\? Check out"
        r"|Explore all newsletters"
        r"|We're improving your newsletter"
        r"|Bloomberg L\.P\."
        r"|731 Lexington"
        r"|New York, NY"
        r"|\s*\|$)"
    )

    cleaned = []
    for line in lines:
        if cutoff_patterns.match(line):
            break
        cleaned.append(line)

    # Collapse 3+ consecutive blank lines into one
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned))
    return result.strip()


def load_emails(dates: list[str]) -> str:
    """Load and clean raw email .txt files for the given YYYY-MM-DD date strings."""
    all_text = []
    for date_str in dates:
        year, month, day = date_str.split("-")
        folder = BASE_DIR / year / month / day
        if not folder.exists():
            continue
        for filepath in sorted(folder.glob("*.txt")):
            raw = filepath.read_text(encoding="utf-8", errors="ignore")
            cleaned = clean_email(raw)
            if cleaned:
                all_text.append(f"=== {filepath.name} ===\n{cleaned}")
    return "\n\n".join(all_text)


def load_daily_summaries(dates: list[str]) -> str:
    """Load daily .md summaries for the given YYYY-MM-DD date strings (used by weekly mode)."""
    all_text = []
    for date_str in dates:
        year, month, day = date_str.split("-")
        folder = SUMMARIES_DIR / "daily" / year / month / day
        if not folder.exists():
            continue
        for filepath in sorted(folder.glob("*.md")):
            text = filepath.read_text(encoding="utf-8")
            if text:
                all_text.append(f"=== {date_str} / {filepath.stem} ===\n{text}")
    return "\n\n".join(all_text)


def load_weekly_summaries(target: datetime) -> str:
    """Load weekly .md summaries for all weeks overlapping the target month (used by monthly mode)."""
    year, month = target.year, target.month
    first_day = datetime(year, month, 1)
    last_day = datetime(year, month, 1) + timedelta(days=32)
    last_day = last_day.replace(day=1) - timedelta(days=1)

    # Collect ISO weeks whose Monday falls within or overlaps the month
    seen = set()
    d = first_day
    while d <= last_day:
        monday = d - timedelta(days=d.weekday())
        iso_year, iso_week, _ = monday.isocalendar()
        seen.add((iso_year, iso_week))
        d += timedelta(days=7)

    all_text = []
    for iso_year, iso_week in sorted(seen):
        folder = SUMMARIES_DIR / "weekly" / str(iso_year) / f"W{iso_week:02d}"
        if not folder.exists():
            continue
        for filepath in sorted(folder.glob("*.md")):
            text = filepath.read_text(encoding="utf-8")
            if text:
                label = f"{iso_year}-W{iso_week:02d} / {filepath.stem}"
                all_text.append(f"=== {label} ===\n{text}")
    return "\n\n".join(all_text)


def dates_for_mode(target: datetime, mode: str) -> list[str]:
    if mode == "daily":
        return [target.strftime("%Y-%m-%d")]
    elif mode == "weekly":
        monday = target - timedelta(days=target.weekday())
        return [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    elif mode == "monthly":
        dates = []
        d = datetime(target.year, target.month, 1)
        while d.month == target.month:
            dates.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)
        return dates
    else:
        raise ValueError(f"Unknown mode: {mode}")


def output_path(target: datetime, mode: str, region: str) -> Path:
    if mode == "daily":
        folder = SUMMARIES_DIR / "daily" / target.strftime("%Y/%m/%d")
    elif mode == "weekly":
        iso_year, iso_week, _ = target.isocalendar()
        folder = SUMMARIES_DIR / "weekly" / str(iso_year) / f"W{iso_week:02d}"
    else:  # monthly
        folder = SUMMARIES_DIR / "monthly" / target.strftime("%Y/%m")
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{region}.md"


def period_instruction(target: datetime, mode: str) -> str:
    if mode == "daily":
        return f"Write a daily briefing for {target.strftime('%B %d, %Y')}."
    elif mode == "weekly":
        iso_year, iso_week, _ = target.isocalendar()
        monday = target - timedelta(days=target.weekday())
        sunday = monday + timedelta(days=6)
        return (
            f"Write a weekly briefing for the week of {monday.strftime('%B %d')}–"
            f"{sunday.strftime('%B %d, %Y')} (ISO week {iso_week}, {iso_year}). "
            "When citing specific data points, include the day of the week "
            "(e.g., 'gold fell 8% on Friday', 'S&P touched 7,000 on Tuesday')."
        )
    else:  # monthly
        return (
            f"Write a monthly briefing for {target.strftime('%B %Y')}. "
            "When citing specific data points, include timing context "
            "(e.g., 'gold peaked mid-month', 'dollar weakness accelerated in the final week')."
        )


def generate_all_regions(
    client: anthropic.Anthropic,
    content: str,
    target: datetime,
    mode: str,
) -> dict[str, str]:
    """Single API call producing all 4 regional summaries. Returns {region: text}."""
    length_instruction = {
        "daily": "250 words per region — treat this as a hard limit. Cover only the 2-3 most consequential developments; omit everything else.",
        "weekly": "400 words per region — treat this as a hard limit. Synthesize how themes evolved; cut anything that does not add new information beyond what the bullets already capture.",
        "monthly": "400 words per region — treat this as a hard limit. Identify the 2-3 dominant themes; omit secondary stories entirely rather than covering them briefly.",
    }[mode]

    region_blocks = "\n".join(
        f"- {r}: {desc}" for r, desc in REGIONS.items()
    )

    user_prompt = f"""{period_instruction(target, mode)}

Produce five regional briefings from the source material below, one per region:
{region_blocks}

Format your response exactly as:
## US
• [key point 1]
• [key point 2]
• [key point 3]

**[Section Title]**
[paragraph text]

## Asia
• [key point 1]
...

## Europe
• [key point 1]
...

## LatAm
• [key point 1]
...

## Global
• [key point 1]
...

Rules:
- Begin each regional section with 3–5 bullet points (• character, one per line) capturing the most important developments. The first bullet should highlight the key macro data print of the period (with the actual number and whether it beat/missed consensus). Bullets appear immediately after the ## heading, before the first bold section title.
- After the bullets, each paragraph must have a short bold title on its own line (e.g. **Monetary Policy**), followed by the paragraph text. Lead with economic data paragraphs before market paragraphs.
- Write paragraphs in flowing prose. No bullet points within the narrative sections.
- {length_instruction}
- If coverage for a region is thin or absent, write exactly: "No significant coverage for this period." (no bullets needed).
- Do not add any text before "## US" or after the Global section.

---

{content}"""

    max_tokens = {"daily": 2500, "weekly": 3500, "monthly": 3500}[mode]
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return parse_regions(message.content[0].text)


def parse_regions(text: str) -> dict[str, str]:
    """Split Claude's combined response into per-region dict."""
    results = {}
    current_region = None
    buffer = []
    for line in text.splitlines():
        if line.startswith("## ") and line[3:].strip() in REGIONS.keys():
            if current_region:
                results[current_region] = "\n".join(buffer).strip()
            current_region = line[3:].strip()
            buffer = []
        else:
            if current_region:
                buffer.append(line)
    if current_region:
        results[current_region] = "\n".join(buffer).strip()
    return results


def all_outputs_exist(target: datetime, mode: str) -> bool:
    return all(output_path(target, mode, r).exists() for r in REGIONS)


def main():
    parser = argparse.ArgumentParser(description="Generate regional Bloomberg summaries via Claude.")
    parser.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="Summary period (default: daily)",
    )
    parser.add_argument(
        "--region",
        choices=list(REGIONS.keys()) + ["all"],
        default="all",
        help="Region to summarize (default: all)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip dates that already have all 4 regional summaries",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Generate even if the period has not yet ended",
    )
    args = parser.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d")

    if args.skip_existing and args.region == "all" and all_outputs_exist(target, args.mode):
        print(f"Skipping {args.date} — summaries already exist.")
        return

    # Refuse to summarise an incomplete period (week/month not yet over)
    if args.mode != "daily" and not args.force:
        dates = dates_for_mode(target, args.mode)
        period_end = datetime.strptime(dates[-1], "%Y-%m-%d")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if period_end >= today:
            print(
                f"Skipping {args.date} — {args.mode} period ends {dates[-1]}, which has not passed yet. "
                "Use --force to override."
            )
            return

    dates = dates_for_mode(target, args.mode)
    print(f"Mode: {args.mode} | Date range: {dates[0]} → {dates[-1]}")

    # Each mode reads from the level below it
    if args.mode == "daily":
        content = load_emails(dates)
        source_label = "emails"
    elif args.mode == "weekly":
        content = load_daily_summaries(dates)
        source_label = "daily summaries"
    else:  # monthly
        content = load_weekly_summaries(target)
        source_label = "weekly summaries"

    if not content:
        print(f"No {source_label} found for this period — run daily summaries first.")
        sys.exit(1)

    print(f"Loaded {len(content):,} characters from {content.count('=== ')} {source_label}.")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set in environment.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Generating {args.mode} summaries...", end=" ", flush=True)
    summaries = generate_all_regions(client, content, target, args.mode)

    regions_to_save = list(REGIONS.keys()) if args.region == "all" else [args.region]
    for region in regions_to_save:
        text = summaries.get(region, "No significant coverage for this period.")
        path = output_path(target, args.mode, region)
        path.write_text(text, encoding="utf-8")
    print(f"saved → summaries/{args.mode}/{args.date.replace('-', '/')[:7] if args.mode == 'monthly' else args.date.replace('-', '/')}/")

    print("Done.")


if __name__ == "__main__":
    main()
