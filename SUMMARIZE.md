# Bloomberg Summarizer

## What it does

`summarize.py` reads the archived Bloomberg emails and produces regional macro briefings using the Claude API. Summaries are written in the style of Goldman Sachs institutional research — measured, analytical, and aimed at sophisticated professional readers.

There are four regional sections: **US**, **Asia** (China focus), **Europe**, and **Global**. Output is organized as `.txt` files and can later be converted to HTML for publication.

---

## Usage

```bash
# Daily summary for a specific date
python3 summarize.py --date 2026-05-25 --mode daily

# Weekly summary (covers the full week containing the date)
python3 summarize.py --date 2026-05-25 --mode weekly

# Monthly summary (covers the full month)
python3 summarize.py --date 2026-05-25 --mode monthly

# Summarize a single region only
python3 summarize.py --date 2026-05-25 --mode daily --region Asia
```

Requires `ANTHROPIC_API_KEY` to be set in the environment.

---

## Output structure

```
summaries/
├── daily/
│   └── 2026/05/25/
│       ├── US.txt
│       ├── Asia.txt
│       ├── Europe.txt
│       └── Global.txt
├── weekly/
│   └── 2026/W21/
│       ├── US.txt
│       └── ...
└── monthly/
    └── 2026/05/
        ├── US.txt
        └── ...
```

Running the same command twice overwrites the existing file.

---

## Regional scope

| Region | Focus |
|--------|-------|
| **US** | Federal Reserve, US monetary policy, US politics and fiscal policy, US equity and credit markets, US corporates, North American macro |
| **Asia** | China (economy, policy, markets, capital flows, geopolitics) first; then Japan, South Korea, India, Southeast Asia, Australia |
| **Europe** | ECB policy, eurozone macro, UK politics and markets, individual European economies, European corporates |
| **Global** | Cross-cutting themes: oil markets, Strait of Hormuz / energy conflict, global monetary policy divergence, geopolitics, climate/energy transition |

---

## Writing guidelines

These are embedded in the Claude system prompt and govern every summary produced.

### Tone
- Write like a Goldman Sachs research analyst, not a journalist.
- Be measured and analytical — avoid sensationalism.
- Use strong words (historic, unprecedented, crisis) **only when truly justified** — not for routine market moves.
- Default to neutral language: fell/rose, declined/gained, increased/decreased.
- Let data speak for itself — "gold fell 8%" is impactful without adding "worst since 1983."
- Readers are sophisticated professionals who find unnecessary hyperbole off-putting.

### Macro consistency
- Ensure narratives are macroeconomically consistent and logical.
- Example: Trump pressuring the Fed = wanting **lower** rates (dovish). Nominating a hawk like Warsh contradicts this narrative, or suggests Warsh may be more dovish than expected. Do not combine contradictory narratives into a single theme — acknowledge the tension.
- Think through cause and effect: if X happens, what does it imply for Y?

### Acknowledge uncertainty
- Reality is messy — avoid false narrative closure.
- Do not declare crises "resolved" when outcomes remain uncertain. A nomination doesn't resolve political tensions; it shifts them.
- Use hedging language: "appears to," "may signal," "remains to be seen."
- Avoid wrapping everything into neat stories — sometimes things are genuinely unclear.
- Distinguish between **facts** (what happened) and **interpretation** (what it might mean).
- Macro is never black and white — be comfortable with ambiguity.

### Time references in weekly / monthly briefs
- In weekly briefs: cite the day for specific data points — "gold fell 8% on Friday," "S&P touched 7,000 on Tuesday."
- In monthly briefs: cite timing context — "gold peaked mid-month," "dollar weakness accelerated in the final week."
- Numbers without time context are less useful for readers.

---

## Dependencies

```bash
python3 -m pip install anthropic
```

The `google-auth` dependencies from `fetch.py` are not required here — `summarize.py` reads local `.txt` files only.

---

## Integration with fetch.py

The intended workflow is:

1. `fetch.py` runs daily (target: 7am via cron) to pull new Bloomberg emails into `YYYY/MM/DD/` folders.
2. `summarize.py --date <today> --mode daily` runs shortly after to produce four regional `.txt` summaries.
3. (Future) An HTML conversion step publishes the summaries to the website.

Cron example (after `fetch.py` cron is configured):

```cron
# Fetch emails at 7:00 AM
0 7 * * * cd /path/to/TheGreatBloombergArchiver && python3 fetch.py

# Summarize at 7:30 AM
30 7 * * * cd /path/to/TheGreatBloombergArchiver && ANTHROPIC_API_KEY=sk-... python3 summarize.py --date $(date +\%Y-\%m-\%d) --mode daily
```

---

## Model

Uses `claude-opus-4-7` by default. Swap in `SUMMARIZE.md` or directly in `summarize.py` if a different model is preferred.
