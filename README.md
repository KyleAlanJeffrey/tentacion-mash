# THE OTHER HALF

Auto-generates the classic half-and-half edit — left side forever XXXTentacion,
right side whoever famous just died — and shows every edit on a carousel
timeline. Detection is automatic; the whole thing runs on Cloudflare.

## Project structure

```
├── run.sh              local dev: generate edits + serve the site
├── setup.sh            creates .venv and installs Python deps
├── data/celebs.txt     THE LIST — one Wikipedia article title per line
├── schema.sql          D1 table, run once in the dashboard console
├── wrangler.jsonc      Cloudflare config (worker, container, D1, R2, cron)
├── package.json        @cloudflare/containers dependency for the worker
│
├── generator/          Python image pipeline (runs locally or in the container)
│   ├── watcher.py      detection: diffs celebs.txt against Wikidata deaths,
│   │                   picks portraits, publishes edits
│   ├── splice.py       the edit itself: eye-landmark alignment + splicing
│   ├── server.py       tiny HTTP server the container runs; the worker cron
│   │                   POSTs /generate to it
│   ├── Dockerfile      container image (native Python + Pillow + OpenCV)
│   ├── requirements.txt
│   └── assets/         (gitignored) xxx.jpg base image, yunet.onnx model,
│                       optional xxx.jpg.json manual eye coords
│
├── worker/
│   └── index.js        Cloudflare Worker: JSON API (D1), images (R2),
│                       static site, cron that wakes the container
│
└── app/                the web app — Vite + React + TypeScript + Sass
    ├── index.html      entry point
    ├── vite.config.ts  dev proxy to production /api + /images
    ├── tsconfig.json
    ├── public/
    │   ├── deathwatch.txt   THE WATCHLIST — expected deaths, shown as ghosts
    │   ├── xxx.jpg          base image (haunts the watchlist ghosts)
    │   ├── data/, edits/    (local mode only) generated output
    │   └── favicon.svg
    └── src/
        ├── App.tsx          data loading, refresh, toast state
        ├── lib.ts           fetch + date helpers
        ├── types.ts         Edit / Ghost / RailInfo
        ├── components/      Feed, Card, Watchlist, Rail, Toast (.tsx)
        └── styles/          Sass partials (vars, base, chrome, feed, watch)
```

## Local dev

```bash
./run.sh demo        # offline demo with placeholder faces, serves at :8000
./run.sh             # check the list for new deaths once, then serve
./run.sh name "X Y"  # force an edit for anyone with a Wikipedia page
./run.sh regen       # rebuild all images (after tuning), then serve
./run.sh watch       # serve + keep checking every 30 min
```

First run creates `.venv` and installs npm deps automatically. `./run.sh`
serves the Vite dev server: live data proxies from production, and locally
generated files (`app/public/edits/`, `app/public/data/edits.json`) act as
the offline fallback.

### Tuning the splice

Alignment is driven by eye landmarks: both faces are warped so their eyes sit
on the same line, at the same spacing, with the midpoint on the seam.

```bash
SPLICE_EYELINE=0.42 SPLICE_EYEDIST=0.19 ./run.sh regen      # try values
python generator/splice.py --mark generator/assets/xxx.jpg  # check eye detection
```

`--mark` writes `xxx.jpg.marked.jpg` with the detected eyes circled. If
detection is off (tattoos confuse it), save corrected pixel coordinates as
`generator/assets/xxx.jpg.json`:

```json
{"eyes": [[93, 105], [148, 106]]}
```

A sidecar `.json` next to any image always overrides detection.

## How detection works

`data/celebs.txt` holds Wikipedia article titles. Each check sends one batched
Wikidata query — "which of these people have a death date (P570)?" — cheap
even for thousands of names. Anyone dead but not yet on the timeline gets an
edit (the timeline is the record, nothing generates twice). The best portrait
is chosen by scanning the person's Wikipedia article images and scoring
face frontality × size; date of death comes from Wikidata, not detection time.

## The Cloudflare stack

**Worker** (site + API + cron) · **D1** (metadata) · **R2** (images) ·
**Container** (the generator, woken by the cron every 15 min; exits in ~2s
when nobody died).

### API

```
GET    /api/edits           all edits, newest death first
GET    /api/edits/:slug     one edit
GET    /images/:slug.jpg    the splice image (R2)
POST   /api/edits           upsert metadata      (Bearer INGEST_TOKEN)
PUT    /api/images/:slug    upload image         (Bearer INGEST_TOKEN)
DELETE /api/edits/:slug     remove edit + image  (Bearer INGEST_TOKEN)
```

All GETs are CORS-open.

### One-time wiring (dashboard only)

Requires the Workers Paid plan (containers). In the Cloudflare dashboard:

1. **Workers & Pages → Create → Workers → Import a repository** — pick this
   repo, build command `npm run build`, deploy command
   `npx wrangler deploy` (default). The deploy
   auto-creates the D1 database and R2 bucket (both named `tentacion-mash`)
   and builds + pushes the container image.
2. **Storage & Databases → D1 → tentacion-mash → Console** — paste and run
   `schema.sql` once.
3. Worker → **Settings → Variables and Secrets**:
   - secret `INGEST_TOKEN` — any long random string (auths container uploads)
   - optional secret `WIKIMEDIA_TOKEN` — raises Wikimedia rate limits
     ([free token](https://api.wikimedia.org/wiki/Special:AppManagement))
4. Set `SELF_URL` in `wrangler.jsonc` to your worker URL, commit + push.

Every push redeploys worker, site, and container image — so tuning done
locally ships automatically.

## The watchlist

`app/public/deathwatch.txt` — names you *expect* to lose (one Wikipedia title per
line). They hover above the timeline with a ghostly glow; scroll UP from the
newest death to see the future. Portraits load client-side from Wikipedia, and
once someone on the watchlist actually dies, the pipeline replaces their ghost
with the real edit automatically.

## Notes

- `notify()` in `generator/watcher.py` is a stub for the "message me when
  someone dies" feature — ntfy.sh instructions inside.
- Portraits come from Wikipedia/Wikimedia; most are freely licensed, but
  check before publishing publicly.
