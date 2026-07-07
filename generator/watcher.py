"""watcher.py — detect celebrity deaths and generate splice edits.

Detection (all free, no API keys):

PRIMARY — the celebrity list. Put Wikipedia article titles in celebs.txt (one
per line). Each check, ONE batched Wikidata query asks "which of these people
have a death date?" — cheap even for thousands of names. Everyone who is dead
but not yet on the timeline gets an edit, however long ago they died.

FALLBACK — if celebs.txt doesn't exist, poll the Wikipedia category
"Deaths in <current month>" and filter by pageviews (FAME_THRESHOLD).
This catches famous people you forgot to list.

Then for each new death:
1. Fetch their lead portrait from the Wikipedia REST summary API.
2. Splice with the XXXTentacion base image (downloaded once to assets/xxx.jpg).
3. Append to site/data/edits.json and drop the image in site/edits/.
4. Optional: send a push notification (see notify()).

Usage:
    python watcher.py --once            # single check
    python watcher.py --poll 1800       # check every 30 min, forever
    python watcher.py --name "Ozzy Osbourne"   # force an edit for one person
    python watcher.py --demo            # offline demo with placeholder faces
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from splice import make_splice, CANVAS

ROOT = os.path.dirname(os.path.abspath(__file__))        # generator/
REPO = os.path.dirname(ROOT)                              # repo root
ASSETS = os.path.join(ROOT, "assets")
SITE = os.path.join(REPO, "site")
SITE_EDITS = os.path.join(SITE, "edits")
DATA_FILE = os.path.join(SITE, "data", "edits.json")
STATE_FILE = os.path.join(ROOT, "seen.json")
XXX_IMG = os.path.join(ASSETS, "xxx.jpg")

CELEBS_FILE = os.path.join(REPO, "data", "celebs.txt")

# Wikimedia etiquette: identify yourself and don't hammer.
HEADERS = {"User-Agent": "the-other-half/0.1 (kjeffrey@stout.ai; personal project)"}
THROTTLE_SECONDS = 0.6              # minimum gap between any two requests

# Optional: a free personal API token from api.wikimedia.org raises the
# Wikimedia rate limit from 500/hr (per IP) to 5,000/hr.
#   export WIKIMEDIA_TOKEN=...        (locally)
#   repo Settings -> Secrets -> Actions -> WIKIMEDIA_TOKEN   (GitHub Action)
if os.environ.get("WIKIMEDIA_TOKEN"):
    HEADERS["Authorization"] = "Bearer " + os.environ["WIKIMEDIA_TOKEN"]
FAME_THRESHOLD = 1_000_000          # pageviews in the last 12 months (fallback mode)
MAX_NEW_PER_RUN = int(os.environ.get("MAX_NEW_PER_RUN", 20))  # backfill batch size
WIKI = "https://en.wikipedia.org"
SPARQL = "https://query.wikidata.org/sparql"
SKIP_TITLES = re.compile(r"^(List of|Deaths in|Category:|Template:)", re.I)


_last_request = 0.0


def _request(url, timeout, data=None):
    """Throttled fetch with backoff on 429/503 (honors Retry-After)."""
    global _last_request
    req = urllib.request.Request(url, data=data, headers=HEADERS)
    for attempt in range(4):
        wait = _last_request + THROTTLE_SECONDS - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 3:
                delay = int(e.headers.get("Retry-After") or 0) or 15 * (attempt + 1)
                print(f"    (rate limited — waiting {delay}s)")
                time.sleep(delay)
                continue
            raise


def get_json(url):
    with _request(url, 30) as r:
        return json.load(r)


def download(url, path):
    with _request(url, 60) as r, open(path, "wb") as f:
        f.write(r.read())


# ------------------------------------------------------- list-based detection
def load_celebs():
    with open(CELEBS_FILE) as f:
        names = [ln.strip() for ln in f]
    return [n for n in names if n and not n.startswith("#")]


def query_deaths(titles, batch_size=250):
    """One batched Wikidata query per 250 names: which of these English
    Wikipedia articles are about people with a death date (P570)?
    Returns {title: 'YYYY-MM-DD'}. Absent = alive (or title not found)."""
    dead = {}
    for i in range(0, len(titles), batch_size):
        batch = titles[i:i + batch_size]
        values = " ".join('"%s"@en' % t.replace('"', '\\"') for t in batch)
        q = """SELECT ?name ?death WHERE {
                 VALUES ?name { %s }
                 ?article schema:about ?p ;
                          schema:isPartOf <https://en.wikipedia.org/> ;
                          schema:name ?name .
                 ?p wdt:P570 ?death . }""" % values
        body = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
        with _request(SPARQL, 60, data=body) as r:
            data = json.load(r)
        for row in data["results"]["bindings"]:
            dead[row["name"]["value"]] = row["death"]["value"][:10]
    return dead


def check_list(publish=False):
    """Primary mode: diff the celebrity list against Wikidata death dates.
    Everyone on the list who is dead but not yet on the timeline gets an
    edit, however long ago they died. The timeline itself is the record —
    local edits.json, or the worker API when publishing."""
    celebs = load_celebs()
    print(f"checking {len(celebs)} names against Wikidata...")
    dead = query_deaths(celebs)

    edits = load(DATA_FILE, [])
    have = api_slugs() if publish else {e["slug"] for e in edits}
    new = 0
    # newest deaths first, so recent ones never wait behind a backfill
    for title, death_date in sorted(dead.items(), key=lambda kv: kv[1], reverse=True):
        if slugify(title) in have:
            continue
        if new >= MAX_NEW_PER_RUN:
            print(f"  (cap of {MAX_NEW_PER_RUN} reached — the rest backfill next run)")
            break
        print(f"  {title}: died {death_date}")
        ensure_base_image()
        try:
            entry = make_edit(title, died=death_date)
        except Exception as e:
            print(f"  ✗ {title}: {e}")
            continue
        if entry:
            if publish:
                publish_entry(entry)
            edits.insert(0, entry)
            new += 1
            print(f"  ✔ edit created: {entry['image']}")
            notify(entry)
    if new and not publish:
        save(DATA_FILE, edits)
    print(f"done — {new} new edit(s)")


# ------------------------------------------- category detection (fallback)
def recent_death_titles(limit=50):
    """Titles most recently added to this month's deaths category."""
    now = dt.date.today()
    cat = f"Deaths in {now.strftime('%B %Y')}"
    url = (f"{WIKI}/w/api.php?action=query&list=categorymembers"
           f"&cmtitle={urllib.parse.quote('Category:' + cat)}"
           f"&cmsort=timestamp&cmdir=desc&cmlimit={limit}&format=json")
    data = get_json(url)
    titles = [m["title"] for m in data["query"]["categorymembers"]]
    return [t for t in titles if not SKIP_TITLES.match(t)]


def yearly_pageviews(title):
    end = dt.date.today().replace(day=1) - dt.timedelta(days=1)
    start = end - dt.timedelta(days=365)
    t = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
           f"en.wikipedia/all-access/user/{t}/monthly/"
           f"{start.strftime('%Y%m01')}/{end.strftime('%Y%m%d')}")
    try:
        return sum(i["views"] for i in get_json(url).get("items", []))
    except Exception:
        return 0


def summary(title):
    t = urllib.parse.quote(title.replace(" ", "_"), safe="")
    return get_json(f"{WIKI}/api/rest_v1/page/summary/{t}")


# --------------------------------------------------------- portrait picking
BAD_FILES = re.compile(r"signature|logo|map|flag|coat|stamp|icon|plaque|"
                       r"grave|album|cover|poster", re.I)


def media_candidates(title, limit=8):
    """(thumb_url, File: title) pairs for article images that could be portraits."""
    t = urllib.parse.quote(title.replace(" ", "_"), safe="")
    data = get_json(f"{WIKI}/api/rest_v1/page/media-list/{t}")
    out = []
    for item in data.get("items", []):
        name = item.get("title", "")
        if (item.get("type") != "image" or BAD_FILES.search(name)
                or not re.search(r"\.(jpe?g|png)$", name, re.I)):
            continue
        src = (item.get("srcset") or [{}])[0].get("src", "")
        if src.startswith("//"):
            src = "https:" + src
        if src:
            out.append((src, name))
        if len(out) >= limit:
            break
    return out


def original_url(file_title):
    """Full-resolution URL for a File: title via the imageinfo API."""
    url = (f"{WIKI}/w/api.php?action=query&prop=imageinfo&iiprop=url"
           f"&titles={urllib.parse.quote(file_title)}&format=json")
    pages = get_json(url)["query"]["pages"]
    return next(iter(pages.values()))["imageinfo"][0]["url"]


def pick_portrait(title, s):
    """Pick the flattest head-on portrait: score the lead image and the other
    article images by face frontality x size (splice.assess_portrait)."""
    from splice import assess_portrait
    lead = s.get("originalimage", {}).get("source")
    cands = [(lead, None)] if lead else []
    try:
        cands += media_candidates(title)
    except Exception as e:
        print(f"    (media list failed: {e})")

    os.makedirs(ASSETS, exist_ok=True)
    tmp = os.path.join(ASSETS, "_candidate.jpg")
    best, best_score = None, 0.0
    for url, ftitle in cands[:9]:
        try:
            download(url, tmp)
            score = assess_portrait(tmp)
        except Exception:
            continue
        print(f"    candidate {url.rsplit('/', 1)[-1][:48]}: {score:.3f}")
        if score > best_score:
            best, best_score = (url, ftitle), score
    if best is None:
        if lead:
            print("    (no frontal face found anywhere — using lead image)")
        return lead
    url, ftitle = best
    if ftitle:  # media-list thumb — resolve the original file
        try:
            return original_url(ftitle)
        except Exception:
            return url  # the thumb we already validated
    return url


# ---------------------------------------------------------------- pipeline
def ensure_base_image():
    if os.path.exists(XXX_IMG):
        return
    s = summary("XXXTentacion")
    img = pick_portrait("XXXTentacion", s)
    if not img:
        sys.exit("Could not find XXXTentacion portrait — put one at assets/xxx.jpg")
    download(img, XXX_IMG)
    print("downloaded base image ->", XXX_IMG)


def load(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def make_edit(title, s=None, died=None):
    """Generate the splice + metadata entry for one person. Returns entry or None."""
    s = s or summary(title)
    if died is None:  # look up the real date of death (Wikidata P570)
        try:
            died = query_deaths([title]).get(title)
        except Exception:
            died = None
    if s.get("type") != "standard":
        print(f"  {title}: not a normal article page, skipping")
        return None
    img = pick_portrait(title, s)
    if not img:
        print(f"  {title}: no portrait, skipping")
        return None

    slug = slugify(title)
    raw = os.path.join(ASSETS, f"{slug}-raw.jpg")
    out = os.path.join(SITE_EDITS, f"{slug}.jpg")
    os.makedirs(SITE_EDITS, exist_ok=True)
    download(img, raw)
    make_splice(XXX_IMG, raw, out)
    try:
        os.remove(raw)
    except OSError:
        pass

    return {
        "title": title,
        "slug": slug,
        "description": s.get("description", ""),
        "extract": s.get("extract", ""),
        "wiki_url": s.get("content_urls", {}).get("desktop", {}).get("page", ""),
        "image": f"edits/{slug}.jpg",
        "died": died,  # date of death from Wikidata (P570), YYYY-MM-DD or null
        "detected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


# ------------------------------------------------------- publish to worker
WORKER_URL = os.environ.get("WORKER_URL", "").rstrip("/")
INGEST_TOKEN = os.environ.get("INGEST_TOKEN", "")


def _api(method, path, data, ctype):
    req = urllib.request.Request(
        WORKER_URL + path, data=data, method=method,
        headers={**HEADERS, "Authorization": "Bearer " + INGEST_TOKEN,
                 "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def api_slugs():
    return {e["slug"] for e in get_json(WORKER_URL + "/api/edits")}


def publish_entry(entry):
    """Upload the image to R2 and the metadata to D1 via the worker API."""
    with open(os.path.join(SITE, entry["image"]), "rb") as f:
        _api("PUT", f"/api/images/{entry['slug']}", f.read(), "image/jpeg")
    meta = {k: v for k, v in entry.items() if k != "image"}
    _api("POST", "/api/edits", json.dumps(meta).encode(), "application/json")
    print(f"  ↑ published {entry['slug']} -> {WORKER_URL}")


def notify(entry):
    """Later feature: push a message when an edit is created.

    Easiest zero-signup option — ntfy.sh. Pick a secret topic name, subscribe
    in the ntfy phone app, then uncomment:

    # req = urllib.request.Request(
    #     "https://ntfy.sh/YOUR-SECRET-TOPIC",
    #     data=f"RIP {entry['title']} — new edit is up".encode(),
    #     headers={"Title": "death-splice"})
    # urllib.request.urlopen(req)
    """


def check_once():
    if os.path.exists(CELEBS_FILE):
        check_list()
        return
    print("no celebs.txt — falling back to category polling")
    ensure_base_image()
    seen = load(STATE_FILE, [])
    edits = load(DATA_FILE, [])
    new = 0
    for title in recent_death_titles():
        if title in seen:
            continue
        seen.append(title)  # mark seen even if below the bar, so we check once
        views = yearly_pageviews(title)
        famous = views >= FAME_THRESHOLD
        print(f"  {title}: {views:,} views/yr {'<- FAMOUS' if famous else ''}")
        if not famous:
            continue
        entry = make_edit(title)
        if entry:
            entry["pageviews_last_year"] = views
            edits.insert(0, entry)
            new += 1
            print(f"  ✔ edit created: {entry['image']}")
            notify(entry)
    save(STATE_FILE, seen)
    if new:
        save(DATA_FILE, edits)
    print(f"done — {new} new edit(s)")


def regen():
    """Rebuild every image on the timeline (after crop/splice changes),
    keeping the original death dates and detection times."""
    ensure_base_image()
    edits = load(DATA_FILE, [])
    for old in edits:
        try:
            entry = make_edit(old["title"], died=old.get("died"))
        except Exception as e:
            print(f"  ✗ {old['title']}: {e} — keeping existing image")
            continue
        if entry:
            entry["detected_at"] = old["detected_at"]
            old.update(entry)
            print(f"  ✔ regenerated {old['image']}")
    save(DATA_FILE, edits)
    print(f"done — {len(edits)} edit(s) rebuilt")


def force_name(name):
    ensure_base_image()
    edits = load(DATA_FILE, [])
    entry = make_edit(name)
    if not entry:
        sys.exit(f"couldn't make an edit for {name}")
    entry["pageviews_last_year"] = yearly_pageviews(name)
    edits = [e for e in edits if e["slug"] != entry["slug"]]
    edits.insert(0, entry)
    save(DATA_FILE, edits)
    print("✔", entry["image"])


# ---------------------------------------------------------------- demo mode
def demo():
    """Offline demo: placeholder 'portraits' so the pipeline and site can be
    tested with no network. Replaced by real data on the first real run."""
    from PIL import Image, ImageDraw

    def fake_portrait(path, initials, color):
        img = Image.new("RGB", (CANVAS, CANVAS), color)
        d = ImageDraw.Draw(img)
        # crude head + shoulders silhouette
        cx = CANVAS // 2
        d.ellipse((cx - 160, 140, cx + 160, 460), fill=(28, 28, 34))
        d.rounded_rectangle((cx - 260, 500, cx + 260, CANVAS), 80, fill=(28, 28, 34))
        d.text((40, 40), initials, fill=(240, 240, 240))
        img.save(path)

    os.makedirs(ASSETS, exist_ok=True)
    os.makedirs(SITE_EDITS, exist_ok=True)
    fake_portrait(XXX_IMG, "XXX (placeholder)", (40, 40, 90))
    people = [
        ("Demo Person One", "musician (placeholder)", (120, 60, 40)),
        ("Demo Person Two", "actor (placeholder)", (50, 90, 55)),
    ]
    edits = []
    for i, (name, desc, color) in enumerate(people):
        slug = slugify(name)
        raw = os.path.join(ASSETS, f"{slug}-raw.jpg")
        fake_portrait(raw, name, color)
        make_splice(XXX_IMG, raw, os.path.join(SITE_EDITS, f"{slug}.jpg"))
        try:
            os.remove(raw)
        except OSError:
            pass
        edits.append({
            "title": name, "slug": slug, "description": desc,
            "extract": "Placeholder entry generated by --demo. Run "
                       "`python watcher.py --once` for real data.",
            "wiki_url": "https://en.wikipedia.org/wiki/Deaths_in_2026",
            "image": f"edits/{slug}.jpg",
            "died": (dt.date.today() - dt.timedelta(days=3 * i)).isoformat(),
            "detected_at": (dt.datetime.now(dt.timezone.utc)
                            - dt.timedelta(days=3 * i)).isoformat(),
            "pageviews_last_year": 2_500_000,
        })
    save(DATA_FILE, edits)
    print("demo data written — open the site to see it")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--once", action="store_true")
    g.add_argument("--poll", type=int, metavar="SECONDS")
    g.add_argument("--name")
    g.add_argument("--demo", action="store_true")
    g.add_argument("--regen", action="store_true",
                   help="rebuild all timeline images (after crop changes)")
    g.add_argument("--publish", action="store_true",
                   help="check list and upload new edits to the worker API "
                        "(needs WORKER_URL + INGEST_TOKEN env vars)")
    a = p.parse_args()

    if a.demo:
        demo()
    elif a.publish:
        if not (WORKER_URL and INGEST_TOKEN):
            sys.exit("--publish needs WORKER_URL and INGEST_TOKEN env vars")
        check_list(publish=True)
    elif a.regen:
        regen()
    elif a.name:
        force_name(a.name)
    elif a.once:
        check_once()
    else:
        while True:
            try:
                check_once()
            except Exception as e:
                print("error:", e)
            time.sleep(a.poll)
