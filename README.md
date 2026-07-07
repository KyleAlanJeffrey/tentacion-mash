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

## How detection works

**Primary — the celebrity list.** `celebs.txt` holds Wikipedia article titles,
one per line (~160 seeded, add your own). Each check sends one batched query to
Wikidata asking "which of these people have a death date?" — cheap even for
thousands of names. Everyone on the list who is dead but not yet on the
timeline gets an edit, however long ago they died — the timeline itself is
the record, so nothing is generated twice.

**Fallback — category polling.** If `celebs.txt` is missing, the watcher polls
Wikipedia's "Deaths in <this month>" category (editors add people within
minutes of a notable death) and filters by pageviews (`FAME_THRESHOLD`,
default 1M/year).

For each new death the watcher grabs the lead portrait from the Wikipedia
REST summary API, splices it with the XXX base image (`splice.py`,
face-centered via OpenCV), writes `site/edits/<slug>.jpg`, and prepends the
entry to `site/data/edits.json`.

State: the timeline itself (list mode), `seen.json` (category mode).

## Messaging (the later feature)

`notify()` in `watcher.py` is stubbed with the easiest option: [ntfy.sh](https://ntfy.sh).
Pick a secret topic name, subscribe in the ntfy phone app, uncomment four
lines — you'll get a push the moment an edit is generated. Twilio SMS or a
Discord webhook drop into the same function.

## Deploying — the Cloudflare stack

**Worker** (serves site + API, cron-polls Wikidata) · **D1** (edit metadata) ·
**R2** (splice images) · **GitHub Action** (Python image generation, dispatched
by the cron, publishes back via the API).

### API

```
GET    /api/edits           all edits, newest death first
GET    /api/edits/:slug     one edit
GET    /images/:slug.jpg    the splice image (R2)
POST   /api/edits           upsert metadata      (Bearer INGEST_TOKEN)
PUT    /api/images/:slug    upload image         (Bearer INGEST_TOKEN)
DELETE /api/edits/:slug     remove edit + image  (Bearer INGEST_TOKEN)
```

All GETs are CORS-open — build anything on top.

### One-time wiring (dashboard only, ~10 minutes)

Requires the Workers Paid plan (containers). In the Cloudflare dashboard:

1. **Storage & Databases → D1 → Create** — name it `the-other-half`, copy its
   ID into `database_id` in `wrangler.jsonc` (commit + push).
2. In the new database's **Console**, paste and run `schema.sql`.
3. **R2 → Create bucket** named `the-other-half-images`.
4. **Workers & Pages → Create → Workers → Import a repository** — pick this
   repo, deploy command `npx wrangler deploy` (default). Deploy. This also
   builds and pushes the generator container image.
5. Worker → **Settings → Variables and Secrets**:
   - secret `INGEST_TOKEN` — any long random string (auths container uploads)
   - optional secret `WIKIMEDIA_TOKEN` — raises Wikimedia rate limits
6. Put your worker URL (e.g. `https://the-other-half.you.workers.dev`) in
   `SELF_URL` in `wrangler.jsonc`, commit + push (auto-redeploys).

### How it flows

Worker cron (every 15 min) wakes the generator **Container** — native Python,
Pillow, OpenCV, no serverless-runtime compromises. It diffs `celebs.txt`
against Wikidata and the API, generates splices for anyone new, uploads image
to R2 + metadata to D1 through the API, then the container sleeps. A no-death
check costs ~2 seconds of billed container time.

The GitHub Action remains as a manual backup generator (Actions tab → Run
workflow; needs `WORKER_URL` + `INGEST_TOKEN` repo secrets).

Local dev is unchanged: `./run.sh` serves everything from local files.

## Notes

- Crop is geometric, not face-detected. Wikipedia portraits are usually
  head-and-shoulders so it lands well; for perfect eye-line alignment add a
  face detector (e.g. mediapipe) in `_face_crop()`.
- Portraits come from Wikipedia/Wikimedia; most are freely licensed, but check
  before publishing publicly.
