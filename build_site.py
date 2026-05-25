#!/usr/bin/env python3
"""
build_site.py — Static GitHub Pages site from Bloomberg summary .md files.

Output: docs/
  index.html           Landing: latest daily brief + archive navigation
  daily.html           Accordion archive — all daily summaries expand inline
  weekly.html          Accordion archive — all weekly summaries expand inline
  monthly.html         Accordion archive — all monthly summaries expand inline
  daily/YYYY-MM-DD.html    (permalink)
  weekly/YYYY-Www.html
  monthly/YYYY-MM.html
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


# ── Markdown helpers ──────────────────────────────────────────────────────────

def bold_to_strong(text: str) -> str:
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)


def parse_content(text: str) -> tuple[list[str], list[tuple[str | None, str]]]:
    """Return (bullets, paragraph_pairs) from a regional summary .md.

    Bullets are leading lines starting with •, before the first **Title**.
    Remaining lines are parsed into (title, body) pairs as before.
    """
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]

    bullets: list[str] = []
    para_lines: list[str] = []
    in_bullet_zone = True

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if in_bullet_zone and stripped.startswith("•"):
            bullets.append(stripped.lstrip("•").strip())
        else:
            in_bullet_zone = False
            para_lines.append(stripped)

    pairs: list[tuple[str | None, str]] = []
    current_title: str | None = None
    current_body: list[str] = []

    def flush():
        if current_body:
            pairs.append((current_title, " ".join(current_body)))

    for line in para_lines:
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
    return bullets, pairs


# ── CSS + JS ──────────────────────────────────────────────────────────────────

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  background: #f0f2f5;
  color: #1a1a1a;
  min-height: 100vh;
}
a { color: inherit; text-decoration: none; }

/* ── Nav ── */
.nav {
  background: #040505;
  padding: 0 32px;
  display: flex;
  align-items: center;
  height: 56px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,0.4);
  gap: 8px;
}
.nav-logo {
  font-size: 17px; font-weight: bold; color: #fff;
  font-family: Georgia, serif;
  background: #1a1a2e;
  width: 32px; height: 32px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}

/* ── Region filter (left of nav, after logo) ── */
.rgn-filter { display: flex; gap: 3px; margin-right: auto; }
.rgn-btn {
  font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
  color: #666; padding: 5px 10px; border-radius: 4px;
  background: none; border: 1px solid transparent; cursor: pointer;
  transition: all 0.15s; font-family: inherit; white-space: nowrap;
}
.rgn-btn:hover { color: #bbb; border-color: #333; }
.rgn-btn.active { color: #5597cb; border-color: #5597cb; }

/* ── Page nav links (right of nav) ── */
.nav-links { display: flex; gap: 4px; flex-shrink: 0; }
.nav-link {
  font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase;
  color: #888; padding: 8px 14px; border-radius: 4px;
  transition: color 0.15s;
}
.nav-link:hover { color: #ccc; }
.nav-link.active { color: #5597cb; }

/* ── Page shell ── */
.page { max-width: 760px; margin: 0 auto; padding: 40px 20px 80px; }

/* ── Region section ── */
.region { border-left: 3px solid; padding-left: 20px; margin-bottom: 32px; }
.region:last-child { margin-bottom: 0; }
.region-name {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 2px; margin-bottom: 12px;
}

/* ── Per-region bullet list ── */
.region-bullets {
  list-style: none;
  margin: 0 0 16px 0;
  padding: 10px 14px;
  background: rgba(0,0,0,0.03);
  border-radius: 3px;
}
.region-bullets li {
  font-size: 13px; line-height: 1.65; color: #333;
  padding: 3px 0 3px 18px;
  position: relative;
}
.region-bullets li::before {
  content: '•';
  position: absolute; left: 0;
  color: var(--bullet-color, #5597cb);
  font-weight: bold;
}

.para-title {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 1.2px; margin-bottom: 4px; margin-top: 14px;
}
.para-title:first-of-type { margin-top: 0; }
.para-body {
  font-size: 15px; line-height: 1.8; color: #333; margin-bottom: 14px;
}
.para-body:last-child { margin-bottom: 0; }

/* ── Accordion ── */
.accordion { list-style: none; display: flex; flex-direction: column; gap: 6px; }
.accordion-item {
  background: #fff; border-radius: 4px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  overflow: hidden; transition: box-shadow 0.2s;
}
.accordion-item:has(.accordion-trigger.open) {
  box-shadow: 0 4px 16px rgba(0,0,0,0.1);
}
.accordion-trigger {
  width: 100%; background: none; border: none; cursor: pointer;
  display: flex; align-items: center; gap: 14px;
  padding: 16px 20px; text-align: left; transition: background 0.15s;
}
.accordion-trigger:hover { background: #fafbfc; }
.accordion-trigger.open { background: #f5f8fd; }
.accordion-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #5597cb; flex-shrink: 0;
}
.accordion-date { font-size: 14px; font-weight: 500; color: #1a1a1a; flex: 1; }
.accordion-meta { font-size: 11px; color: #bbb; }
.accordion-chevron {
  font-size: 18px; color: #ccc; flex-shrink: 0;
  transition: transform 0.2s ease, color 0.2s; line-height: 1;
}
.accordion-trigger.open .accordion-chevron { transform: rotate(90deg); color: #5597cb; }
.accordion-body { display: none; border-top: 1px solid #f0f0f0; }
.accordion-body.open { display: block; }
.accordion-content { padding: 28px 40px 32px; }
.accordion-content .region { margin-bottom: 24px; }
.accordion-content .para-body { font-size: 14px; }
.accordion-content .region-bullets li { font-size: 12px; }

/* ── Archive page header ── */
.page-title {
  font-size: 26px; font-weight: 300; color: #111;
  letter-spacing: -0.5px; margin-bottom: 6px;
}
.page-subtitle { font-size: 13px; color: #999; margin-bottom: 28px; }
.empty-state {
  color: #999; font-size: 14px; background: #fff; border-radius: 4px;
  padding: 48px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

/* ── Landing page ── */
.landing-hero {
  background: #040505; padding: 36px 48px 32px;
  border-radius: 4px 4px 0 0;
}
.landing-hero-label {
  font-size: 10px; letter-spacing: 3px; text-transform: uppercase;
  color: #5597cb; font-weight: 600; margin-bottom: 8px;
}
.landing-hero-date { font-size: 24px; font-weight: 300; color: #fff; line-height: 1.2; }
.landing-hero-regions { font-size: 11px; color: #555; margin-top: 6px; }
.accent { height: 3px; background: linear-gradient(90deg, #5597cb 0%, #aac3e3 100%); }
.landing-card {
  background: #fff; border-radius: 0 0 4px 4px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.1); margin-bottom: 32px; overflow: hidden;
}
.landing-card-body { padding: 32px 48px; }
.archive-nav { display: flex; gap: 12px; flex-wrap: wrap; }
.archive-nav-card {
  flex: 1; min-width: 160px; background: #fff; border-radius: 4px;
  padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  transition: box-shadow 0.15s, transform 0.15s;
  display: flex; flex-direction: column; gap: 6px;
}
.archive-nav-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); transform: translateY(-1px); }
.archive-nav-label {
  font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
  color: #5597cb; font-weight: 600;
}
.archive-nav-title { font-size: 15px; font-weight: 500; color: #1a1a1a; }
.archive-nav-count { font-size: 12px; color: #aaa; }

/* ── Permalink brief pages ── */
.card {
  background: #fff; border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 32px; overflow: hidden;
}
.brief-hdr { background: #040505; padding: 32px 48px 28px; border-radius: 4px 4px 0 0; }
.brief-hdr-inner { display: flex; align-items: flex-start; gap: 16px; }
.brief-logo {
  font-size: 17px; font-weight: bold; color: #fff;
  font-family: Georgia, serif; background: #1a1a2e;
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.brief-hdr-text { flex: 1; }
.brief-label {
  font-size: 10px; letter-spacing: 3px; text-transform: uppercase;
  color: #5597cb; font-weight: 500; margin-bottom: 4px;
}
.brief-date { font-size: 22px; font-weight: 300; color: #fff; line-height: 1.2; }
.card-body { padding: 36px 48px; }

/* ── Back link ── */
.back {
  font-size: 11px; letter-spacing: 1px; text-transform: uppercase;
  color: #888; display: inline-flex; align-items: center; gap: 6px;
  margin-bottom: 24px; padding: 8px 0;
}
.back:hover { color: #5597cb; }

@media (max-width: 700px) {
  .nav { padding: 0 12px; }
  .rgn-btn { padding: 4px 7px; letter-spacing: 0.8px; }
  .nav-link { padding: 8px 8px; letter-spacing: 0.8px; }
  .page { padding: 24px 16px 60px; }
  .landing-hero { padding: 24px 20px; }
  .landing-card-body, .card-body { padding: 24px 20px; }
  .accordion-content { padding: 20px; }
  .brief-hdr { padding: 24px 20px; }
}
"""

JS = """
function toggleAccordion(btn) {
  var body = btn.nextElementSibling;
  var isOpen = body.classList.contains('open');
  body.classList.toggle('open', !isOpen);
  btn.classList.toggle('open', !isOpen);
}

function setRegion(btn, region) {
  document.querySelectorAll('.rgn-btn').forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
  document.querySelectorAll('[data-region]').forEach(function(el) {
    el.style.display = (region === 'all' || el.dataset.region === region) ? '' : 'none';
  });
  try {
    history.replaceState(null, '', region === 'all' ? location.pathname : '#' + region);
  } catch(e) {}
}

(function() {
  var h = location.hash.replace('#', '');
  if (['US', 'Asia', 'Europe', 'Global'].indexOf(h) !== -1) {
    var btn = document.querySelector('[data-filter="' + h + '"]');
    if (btn) setRegion(btn, h);
  }
})();
"""


# ── HTML components ───────────────────────────────────────────────────────────

def nav_html(active: str = "", prefix: str = "") -> str:
    """prefix is '' for root-level pages, '../' for pages one directory deep."""
    region_btns = "".join(
        f'<button class="rgn-btn{" active" if r == "all" else ""}" '
        f'data-filter="{r}" onclick="setRegion(this,\'{r}\')">{label}</button>'
        for r, label in [
            ("all", "All"), ("US", "US"), ("Asia", "Asia"),
            ("Europe", "Europe"), ("Global", "Global"),
        ]
    )
    page_links = [
        ("index",   "Latest",  f"{prefix}index.html"),
        ("daily",   "Daily",   f"{prefix}daily.html"),
        ("weekly",  "Weekly",  f"{prefix}weekly.html"),
        ("monthly", "Monthly", f"{prefix}monthly.html"),
    ]
    nav_items = "".join(
        f'<a href="{href if active != key else "#"}" '
        f'class="nav-link{" active" if active == key else ""}">{label}</a>'
        for key, label, href in page_links
    )
    return f"""
<nav class="nav">
  <a href="{prefix}index.html" class="nav-logo">M</a>
  <div class="rgn-filter">{region_btns}</div>
  <div class="nav-links">{nav_items}</div>
</nav>"""


def page_wrap(title: str, active: str, body: str, prefix: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — {SITE_TITLE}</title>
<style>{CSS}</style>
</head>
<body>
{nav_html(active, prefix)}
<div class="page">
{body}
</div>
<script>{JS}</script>
</body>
</html>"""


def region_section(region: str, text: str) -> str:
    color = REGION_COLORS[region]
    bullets, pairs = parse_content(text)

    parts = []

    if bullets:
        items = "".join(f"<li>{b}</li>" for b in bullets)
        parts.append(
            f'<ul class="region-bullets" style="--bullet-color:{color};">{items}</ul>'
        )

    for title, body in pairs:
        if title:
            parts.append(f'<p class="para-title" style="color:{color};">{title}</p>')
        parts.append(f'<p class="para-body">{bold_to_strong(body)}</p>')

    inner = "\n".join(parts)
    return f"""<div class="region" style="border-color:{color};" data-region="{region}">
  <p class="region-name" style="color:{color};">{region}</p>
  {inner}
</div>"""


def brief_regions_html(summaries: dict[str, str]) -> str:
    return "\n".join(region_section(r, summaries[r]) for r in REGIONS if r in summaries)


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
    entries = []
    root = SUMMARIES_DIR / "daily"
    if not root.exists():
        return entries
    for y in sorted(root.iterdir()):
        for m in sorted(y.iterdir()):
            for d in sorted(m.iterdir()):
                date_str = f"{y.name}-{m.name}-{d.name}"
                if load_summaries(d):
                    entries.append((date_str, d))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


def find_weekly() -> list[tuple[str, str, Path]]:
    entries = []
    root = SUMMARIES_DIR / "weekly"
    if not root.exists():
        return entries
    for y in sorted(root.iterdir()):
        for w in sorted(y.iterdir()):
            key = f"{y.name}-{w.name}"
            try:
                year, week = int(y.name), int(w.name[1:])
                monday = datetime.fromisocalendar(year, week, 1)
                sunday = monday + timedelta(days=6)
                label = f"{monday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"
            except Exception:
                label = key
            if load_summaries(w):
                entries.append((key, label, w))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


def find_monthly() -> list[tuple[str, str, Path]]:
    entries = []
    root = SUMMARIES_DIR / "monthly"
    if not root.exists():
        return entries
    for y in sorted(root.iterdir()):
        for m in sorted(y.iterdir()):
            key = f"{y.name}-{m.name}"
            try:
                label = datetime(int(y.name), int(m.name), 1).strftime("%B %Y")
            except Exception:
                label = key
            if load_summaries(m):
                entries.append((key, label, m))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


# ── Accordion builder ─────────────────────────────────────────────────────────

def accordion_html(entries: list, mode: str) -> str:
    if not entries:
        return '<div class="empty-state">No summaries yet — check back after the next scheduled run.</div>'

    items = []
    for entry in entries:
        if mode == "daily":
            key, folder = entry
            label = datetime.strptime(key, "%Y-%m-%d").strftime("%A, %B %d, %Y")
        else:
            key, label, folder = entry

        summaries = load_summaries(folder)
        regions_str = " · ".join(summaries.keys())
        content = brief_regions_html(summaries)

        items.append(f"""
<li class="accordion-item">
  <button class="accordion-trigger" onclick="toggleAccordion(this)">
    <span class="accordion-dot"></span>
    <span class="accordion-date">{label}</span>
    <span class="accordion-meta">{regions_str}</span>
    <span class="accordion-chevron">›</span>
  </button>
  <div class="accordion-body">
    <div class="accordion-content">
      {content}
    </div>
  </div>
</li>""")

    return f'<ul class="accordion">{"".join(items)}</ul>'


# ── Page generators ───────────────────────────────────────────────────────────

def generate_archive_page(out_path: Path, mode: str, title: str, entries: list) -> None:
    count = len(entries)
    subtitle = f"{count} brief{'s' if count != 1 else ''}"
    body = f"""<p class="page-title">{title}</p>
<p class="page-subtitle">{subtitle}</p>
{accordion_html(entries, mode)}"""
    out_path.write_text(page_wrap(title, mode, body), encoding="utf-8")


def generate_brief_page(out_path: Path, mode: str, label: str, summaries: dict) -> None:
    """Permalink page for a single brief. Nav uses ../ prefix for root pages."""
    back_href = {"daily": "../daily.html", "weekly": "../weekly.html", "monthly": "../monthly.html"}[mode]
    back_label = {"daily": "Daily archive", "weekly": "Weekly archive", "monthly": "Monthly archive"}[mode]
    mode_label = {"daily": "Daily Brief", "weekly": "Weekly Brief", "monthly": "Monthly Brief"}[mode]
    body = f"""<a class="back" href="{back_href}">‹ {back_label}</a>
<div class="card">
  <div class="brief-hdr">
    <div class="brief-hdr-inner">
      <div class="brief-logo">M</div>
      <div class="brief-hdr-text">
        <p class="brief-label">{mode_label}</p>
        <p class="brief-date">{label}</p>
      </div>
    </div>
  </div>
  <div class="accent"></div>
  <div class="card-body">
    {brief_regions_html(summaries)}
  </div>
</div>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page_wrap(label, mode, body, prefix="../"), encoding="utf-8")


def generate_landing(out_path: Path, daily: list, weekly: list, monthly: list) -> None:
    if daily:
        key, folder = daily[0]
        label = datetime.strptime(key, "%Y-%m-%d").strftime("%A, %B %d, %Y")
        summaries = load_summaries(folder)
        regions_str = " · ".join(summaries.keys())
        latest = f"""<div class="landing-hero">
  <p class="landing-hero-label">Latest Daily Brief</p>
  <p class="landing-hero-date">{label}</p>
  <p class="landing-hero-regions">{regions_str}</p>
</div>
<div class="accent"></div>
<div class="landing-card">
  <div class="landing-card-body">
    {brief_regions_html(summaries)}
  </div>
</div>"""
    else:
        latest = '<div class="empty-state">No briefs yet — check back after the first scheduled run.</div>'

    def nav_card(href, mode_label, entries):
        count = len(entries)
        subtitle = f"{count} brief{'s' if count != 1 else ''}" if count else "None yet"
        return f"""<a href="{href}" class="archive-nav-card">
  <span class="archive-nav-label">{mode_label}</span>
  <span class="archive-nav-title">Archive</span>
  <span class="archive-nav-count">{subtitle}</span>
</a>"""

    archive_nav = f"""<div class="archive-nav">
  {nav_card("daily.html",   "Daily",   daily)}
  {nav_card("weekly.html",  "Weekly",  weekly)}
  {nav_card("monthly.html", "Monthly", monthly)}
</div>"""

    body = latest + "\n" + archive_nav
    out_path.write_text(page_wrap(SITE_TITLE, "index", body), encoding="utf-8")


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

    generate_archive_page(DOCS_DIR / "daily.html",   "daily",   "Daily Briefs",   daily)
    generate_archive_page(DOCS_DIR / "weekly.html",  "weekly",  "Weekly Briefs",  weekly)
    generate_archive_page(DOCS_DIR / "monthly.html", "monthly", "Monthly Briefs", monthly)
    generate_landing(DOCS_DIR / "index.html", daily, weekly, monthly)

    total = len(daily) + len(weekly) + len(monthly) + 4
    print(f"Done — {total} files written to docs/")


if __name__ == "__main__":
    main()
