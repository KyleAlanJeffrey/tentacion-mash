# THE OTHER HALF

Auto-generates the classic half-and-half edit — left side forever XXXTentacion,
right side whoever famous just died — and shows every edit on a timeline.

## Quick start

```bash
./run.sh demo        # offline demo with placeholder faces, serves at :8000
./run.sh             # check for new famous deaths once, then serve
./run.sh watch       # serve + keep checking every 30 min
./run.sh name "X Y"  # force an edit for one person, then serve
```

`run.sh` creates a virtualenv (`.venv`) via `setup.sh` on first run and uses it
for everything. To set up manually: `./setup.sh`.

Real data (needs internet):

```bash
python watcher.py --once                      # check for new famous deaths now
python watcher.py --name "Some Person"        # force an edit for anyone with a Wikipedia page
python watcher.py --poll 1800                 # keep watching, check every 30 min
```

Requires Python 3.9+. Dependencies live in `.venv` (just Pillow). No API keys.

## How detection works (the Wikipedia approach)

When any notable person dies, Wikipedia editors add their article to the
category **"Deaths in July 2026"** (etc.) — usually within minutes to a few
hours. The watcher polls that category sorted by *when pages were added*, so
new members = new deaths. This beats Google Alerts because it's structured
data (a name you can act on, not a headline you'd have to parse), it's free,
and it has no signup.

For each new name the watcher:

1. **Fame check** — sums their English Wikipedia pageviews over the last 12
   months (Wikimedia pageviews API). Default bar: **1,000,000/year** — tune
   `FAME_THRESHOLD` in `watcher.py`.
2. **Portrait** — grabs the lead image from their article (REST summary API).
3. **Splice** — `splice.py` square-crops both portraits (biased toward the
   top, where faces sit), pastes XXX's left half + their right half, adds the
   hairline seam. Output: `site/edits/<slug>.jpg`.
4. **Timeline** — appends metadata to `site/data/edits.json`; the site renders
   it newest-first.

State lives in `seen.json` so nobody is processed twice.

## Messaging (the later feature)

`notify()` in `watcher.py` is stubbed with the easiest option: [ntfy.sh](https://ntfy.sh).
Pick a secret topic name, subscribe in the ntfy phone app, uncomment four
lines — you'll get a push the moment an edit is generated. Twilio SMS or a
Discord webhook drop into the same function.

## Running it for real

Cron on any always-on machine:

```
*/30 * * * * cd /path/to/tentacion-mash && python3 watcher.py --once >> watcher.log 2>&1
```

Or GitHub Actions on a schedule (free) — commit the generated edits and host
`site/` on GitHub Pages. The site is fully static, so any host works.

## Notes

- Crop is geometric, not face-detected. Wikipedia portraits are usually
  head-and-shoulders so it lands well; for perfect eye-line alignment add a
  face detector (e.g. mediapipe) in `_face_crop()`.
- Portraits come from Wikipedia/Wikimedia; most are freely licensed, but check
  before publishing publicly.
