#!/usr/bin/env python3
"""
build_site.py — Generate a static GitHub Pages site from summary .md files.

Output: docs/
  index.html          Landing page (latest daily brief + navigation)
  daily.html          Archive list of all daily summaries
  weekly.html         Archive list of all weekly summaries
  monthly.html        Archive list of all monthly summaries
  daily/YYYY-MM-DD.html
  weekly/YYYY-Www.html
  monthly/YYYY-MM.html

Usage:
    python3 build_site.py
"""

import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
SUMMARIES_DIR = BASE_DIR / "summaries"
DOCS_DIR = BASE_DIR / "docs"

REGIONS = ["US", "Asia", "Europe", "Global"]
REGION_COLORS = {
    "US":     "#5597cb",
    "Asia":   "#e07b39",
    "Europe": "#4a9e6b",
    "Global": "#8b5cf6",
}

SITE_TITLE = "The Macro Brief"


# ── Markdown helpers (mirrors send_brief.py) ──────────────────────────────────

def bold_to_strong(text: str) -> str:
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)


def parse_paragraphs(text: str) -> list[tuple[str | None, str]]:
    lines = text.splitlines()
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
        if line.startswith("## "):
            flush()
            current_title = line[3:].strip()
            current_body = []
        elif re.match(r'^\*\*[^*]+\*\*[.:]?$', line):
            flush()
            current_title = re.sub(r'^\*\*|\*\*[.:]?$', '', line)
            current_body = []
        elif m := re.match(r'^\*\*([^*]+)\*\*[.:]?\s+(.+)', line):
            flush()
            current_title = m.group(1).rstrip('.:')
            current_body = [m.group(2)]
        else:
            current_body.append(line)

    flush()
    return pairs


# ── HTML components ───────────────────────────────────────────────────────────

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  background: #f0f2f5;
  color: #333;
  min-height: 100vh;
}
a { color: inherit; text-decoration: none; }

/* Nav */
.nav {
  background: #040505;
  padding: 0 48px;
  display: flex;
  align-items: center;
  height: 56px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,0.4);
}
.nav-logo {
  font-size: 20px; font-weight: bold; color: #fff;
  font-family: Georgia, serif;
  background: #1a1a2e;
  width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  margin-right: 14px; flex-shrink: 0;
}
.nav-title {
  font-size: 10px; letter-spacing: 3px; text-transform: uppercase;
  color: #5597cb; font-weight: 600; margin-right: auto;
}
.nav-links { display: flex; gap: 4px; }
.nav-link {
  font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
  color: #888; padding: 8px 14px; border-radius: 4px;
  transition: color 0.15s;
}
.nav-link:hover { color: #ccc; }
.nav-link.active { color: #5597cb; }

/* Page shell */
.page { max-width: 720px; margin: 0 auto; padding: 40px 20px 80px; }

/* Brief header (on individual brief pages) */
.brief-hdr {
  background: #040505;
  padding: 32px 48px 28px;
  border-radius: 4px 4px 0 0;
}
.brief-hdr-inner {
  display: flex; align-items: flex-start; gap: 16px;
}
.brief-logo {
  font-size: 20px; font-weight: bold; color: #fff;
  font-family: Georgia, serif;
  background: #1a1a2e;
  width: 40px; height: 40px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.brief-hdr-text { flex: 1; }
.brief-label {
  font-size: 10px; letter-spacing: 3px; text-transform: uppercase;
  color: #5597cb; font-weight: 500; margin-bottom: 4px;
}
.brief-date {
  font-size: 24px; font-weight: 300; color: #fff;
  letter-spacing: -0.3px; line-height: 1.2;
}
.brief-hdr-meta { text-align: right; }
.brief-meta-label {
  font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
  color: #666; margin-bottom: 4px;
}
.brief-issue { font-size: 10px; letter-spacing: 1px; color: #5597cb; }

/* Accent bar */
.accent { height: 3px; background: linear-gradient(90deg, #5597cb 0%, #aac3e3 100%); }

/* Card (wraps header + content) */
.card {
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  margin-bottom: 32px;
  overflow: hidden;
}
.card-body { padding: 36px 48px; }

/* Region section */
.region { border-left: 3px solid; padding-left: 20px; margin-bottom: 36px; }
.region:last-child { margin-bottom: 0; }
.region-name {
  font-size: 12px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 2px; margin-bottom: 14px;
}
.para-title {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 1.2px; margin-bottom: 4px;
}
.para-body {
  font-size: 15px; line-height: 1.75; color: #333;
  margin-bottom: 16px;
}
.para-body:last-child { margin-bottom: 0; }

/* Archive list page */
.section-hdr {
  font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase;
  color: #999; font-weight: 600; margin: 0 0 16px 0;
}
.archive-list { list-style: none; display: flex; flex-direction: column; gap: 6px; }
.archive-item {
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  transition: box-shadow 0.15s;
}
.archive-item:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.12); }
.archive-link {
  display: flex; align-items: center; gap: 16px;
  padding: 14px 20px;
}
.archive-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #5597cb; flex-shrink: 0;
}
.archive-date { font-size: 14px; font-weight: 500; color: #222; flex: 1; }
.archive-regions { font-size: 11px; color: #999; }
.archive-chevron { font-size: 14px; color: #ccc; }

/* Landing page sections */
.latest-label {
  font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase;
  color: #999; font-weight: 600; margin-bottom: 16px;
}
.mode-tabs { display: flex; gap: 8px; margin-bottom: 24px; }
.mode-tab {
  font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
  padding: 8px 16px; border-radius: 20px; border: 1px solid #ddd;
  color: #666; font-weight: 600;
  transition: all 0.15s;
}
.mode-tab:hover { border-color: #5597cb; color: #5597cb; }
.mode-tab.active { background: #5597cb; border-color: #5597cb; color: #fff; }

/* Back link */
.back {
  font-size: 11px; letter-spacing: 1px; text-transform: uppercase;
  color: #888; display: inline-flex; align-items: center; gap: 6px;
  margin-bottom: 24px; padding: 8px 0;
}
.back:hover { color: #5597cb; }

/* Page title for archive pages */
.page-title {
  font-size: 28px; font-weight: 300; color: #111;
  letter-spacing: -0.5px; margin-bottom: 28px;
}
"""


def nav_html(active: str = "") -> str:
    links = [
        ("index", "Latest", "index.html"),
        ("daily", "Daily", "daily.html"),
        ("weekly", "Weekly", "weekly.html"),
        ("monthly", "Monthly", "monthly.html"),
    ]
    items = "".join(
        f'<a href="{href if active != key else "#"}" class="nav-link{"  active" if active == key else ""}">{label}</a>'
        for key, label, href in links
    )
    return f"""
<nav class="nav">
  <div class="nav-logo">M</div>
  <span class="nav-title">{SITE_TITLE}</span>
  <div class="nav-links">{items}</div>
</nav>"""


def page_wrap(title: str, active: str, body: str, nav_href_base: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — {SITE_TITLE}</title>
<style>{CSS}</style>
</head>
<body>
{nav_html(active)}
<div class="page">
{body}
</div>
</body>
</html>"""


def region_section(region: str, text: str) -> str:
    color = REGION_COLORS[region]
    pairs = parse_paragraphs(text)
    parts = []
    for title, body in pairs:
        if title:
            parts.append(
                f'<p class="para-title" style="color:{color};">{title}</p>'
            )
        parts.append(
            f'<p class="para-body">{bold_to_strong(body)}</p>'
        )
    inner = "\n".join(parts)
    return f"""
<div class="region" style="border-color:{color};">
  <p class="region-name" style="color:{color};">{region}</p>
  {inner}
</div>"""


def brief_card(mode: str, label: str, subtitle: str, summaries: dict[str, str]) -> str:
    regions = "".join(region_section(r, summaries[r]) for r in REGIONS if r in summaries)
    mode_labels = {"daily": "Daily Brief", "weekly": "Weekly Brief", "monthly": "Monthly Brief"}
    return f"""
<div class="card">
  <div class="brief-hdr">
    <div class="brief-hdr-inner">
      <div class="brief-logo">M</div>
      <div class="brief-hdr-text">
        <p class="brief-label">{mode_labels[mode]}</p>
        <p class="brief-date">{subtitle}</p>
      </div>
    </div>
  </div>
  <div class="accent"></div>
  <div class="card-body">
    {regions}
  </div>
</div>"""


# ── Summary loading ───────────────────────────────────────────────────────────

def load_summaries(folder: Path) -> dict[str, str]:
    out = {}
    for r in REGIONS:
        p = folder / f"{r}.md"
        if p.exists():
            out[r] = p.read_text(encoding="utf-8").strip()
    return out


# ── Discovery ─────────────────────────────────────────────────────────────────

def find_daily() -> list[tuple[str, Path]]:
    """Return [(date_str, folder), ...] sorted newest first."""
    entries = []
    daily_root = SUMMARIES_DIR / "daily"
    if not daily_root.exists():
        return entries
    for y in sorted(daily_root.iterdir()):
        for m in sorted(y.iterdir()):
            for d in sorted(m.iterdir()):
                date_str = f"{y.name}-{m.name}-{d.name}"
                summaries = load_summaries(d)
                if summaries:
                    entries.append((date_str, d))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


def find_weekly() -> list[tuple[str, str, Path]]:
    """Return [(iso_week_key, label, folder), ...] sorted newest first."""
    entries = []
    weekly_root = SUMMARIES_DIR / "weekly"
    if not weekly_root.exists():
        return entries
    for y in sorted(weekly_root.iterdir()):
        for w in sorted(y.iterdir()):
            key = f"{y.name}-{w.name}"
            # Compute Monday date for label
            try:
                year = int(y.name)
                week = int(w.name[1:])
                monday = datetime.fromisocalendar(year, week, 1)
                sunday = monday + timedelta(days=6)
                label = f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"
            except Exception:
                label = key
            summaries = load_summaries(w)
            if summaries:
                entries.append((key, label, w))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


def find_monthly() -> list[tuple[str, str, Path]]:
    """Return [(YYYY-MM, label, folder), ...] sorted newest first."""
    entries = []
    monthly_root = SUMMARIES_DIR / "monthly"
    if not monthly_root.exists():
        return entries
    for y in sorted(monthly_root.iterdir()):
        for m in sorted(y.iterdir()):
            key = f"{y.name}-{m.name}"
            try:
                label = datetime(int(y.name), int(m.name), 1).strftime("%B %Y")
            except Exception:
                label = key
            summaries = load_summaries(m)
            if summaries:
                entries.append((key, label, m))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


# ── Page generators ───────────────────────────────────────────────────────────

def archive_list_html(entries: list[tuple], mode: str) -> str:
    if not entries:
        return '<p style="color:#999;font-size:14px;">No summaries yet.</p>'
    items = []
    for entry in entries:
        if mode == "daily":
            key, folder = entry
            href = f"daily/{key}.html"
            label = datetime.strptime(key, "%Y-%m-%d").strftime("%A, %B %d, %Y")
            summaries = load_summaries(folder)
        elif mode == "weekly":
            key, label, folder = entry
            href = f"weekly/{key}.html"
            summaries = load_summaries(folder)
        else:
            key, label, folder = entry
            href = f"monthly/{key}.html"
            summaries = load_summaries(folder)
        regions_str = " · ".join(summaries.keys())
        items.append(
            f'<li class="archive-item">'
            f'<a class="archive-link" href="{href}">'
            f'<span class="archive-dot" style="background:{REGION_COLORS["US"]};"></span>'
            f'<span class="archive-date">{label}</span>'
            f'<span class="archive-regions">{regions_str}</span>'
            f'<span class="archive-chevron">›</span>'
            f'</a></li>'
        )
    return f'<ul class="archive-list">{"".join(items)}</ul>'


def generate_brief_page(out_path: Path, mode: str, label: str, summaries: dict) -> None:
    back_labels = {"daily": "Daily archive", "weekly": "Weekly archive", "monthly": "Monthly archive"}
    back_hrefs = {"daily": "../daily.html", "weekly": "../weekly.html", "monthly": "../monthly.html"}
    body = f"""
<a class="back" href="{back_hrefs[mode]}">‹ {back_labels[mode]}</a>
{brief_card(mode, mode, label, summaries)}
"""
    html = page_wrap(label, mode, body)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def generate_index_page(out_path: Path, mode: str, title: str, entries: list) -> None:
    list_html = archive_list_html(entries, mode)
    body = f"""
<p class="page-title">{title}</p>
{list_html}
"""
    html = page_wrap(title, mode, body)
    out_path.write_text(html, encoding="utf-8")


def generate_landing(out_path: Path, daily: list, weekly: list, monthly: list) -> None:
    def latest_brief(entries, mode):
        if not entries:
            return '<p style="color:#999;font-size:14px;margin-bottom:32px;">No summaries yet.</p>'
        entry = entries[0]
        if mode == "daily":
            key, folder = entry
            label = datetime.strptime(key, "%Y-%m-%d").strftime("%A, %B %d, %Y")
            href = f"daily/{key}.html"
        elif mode == "weekly":
            key, label, folder = entry
            href = f"weekly/{key}.html"
        else:
            key, label, folder = entry
            href = f"monthly/{key}.html"
        summaries = load_summaries(folder)
        card = brief_card(mode, mode, label, summaries)
        return f'{card}<p style="text-align:center;margin-top:-20px;margin-bottom:32px;"><a href="{href}" style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#5597cb;">View full brief ›</a></p>'

    daily_html = latest_brief(daily, "daily")
    weekly_html = latest_brief(weekly, "weekly")
    monthly_html = latest_brief(monthly, "monthly")

    def tab(label, anchor, active=False):
        cls = "mode-tab active" if active else "mode-tab"
        return f'<a href="#{anchor}" class="{cls}">{label}</a>'

    body = f"""
<div class="mode-tabs">
  {tab("Daily", "daily", True)}
  {tab("Weekly", "weekly")}
  {tab("Monthly", "monthly")}
</div>

<div id="daily">
  <p class="latest-label">Latest daily</p>
  {daily_html}
</div>

<div id="weekly">
  <p class="latest-label">Latest weekly</p>
  {weekly_html}
</div>

<div id="monthly">
  <p class="latest-label">Latest monthly</p>
  {monthly_html}
</div>
"""
    html = page_wrap(SITE_TITLE, "index", body)
    out_path.write_text(html, encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Building site...")

    if DOCS_DIR.exists():
        for sub in ["daily", "weekly", "monthly"]:
            p = DOCS_DIR / sub
            if p.exists():
                shutil.rmtree(p)

    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / ".nojekyll").touch()

    daily = find_daily()
    weekly = find_weekly()
    monthly = find_monthly()

    # Individual brief pages
    for date_str, folder in daily:
        summaries = load_summaries(folder)
        label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
        generate_brief_page(DOCS_DIR / "daily" / f"{date_str}.html", "daily", label, summaries)
    print(f"  {len(daily)} daily pages")

    for key, label, folder in weekly:
        summaries = load_summaries(folder)
        generate_brief_page(DOCS_DIR / "weekly" / f"{key}.html", "weekly", label, summaries)
    print(f"  {len(weekly)} weekly pages")

    for key, label, folder in monthly:
        summaries = load_summaries(folder)
        generate_brief_page(DOCS_DIR / "monthly" / f"{key}.html", "monthly", label, summaries)
    print(f"  {len(monthly)} monthly pages")

    # Archive index pages
    generate_index_page(DOCS_DIR / "daily.html",   "daily",   "Daily Briefs",   daily)
    generate_index_page(DOCS_DIR / "weekly.html",  "weekly",  "Weekly Briefs",  weekly)
    generate_index_page(DOCS_DIR / "monthly.html", "monthly", "Monthly Briefs", monthly)

    # Landing page
    generate_landing(DOCS_DIR / "index.html", daily, weekly, monthly)

    total = len(daily) + len(weekly) + len(monthly) + 4
    print(f"Done — {total} files written to docs/")


if __name__ == "__main__":
    main()
