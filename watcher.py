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

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "assets")
SITE_EDITS = os.path.join(ROOT, "site", "edits")
DATA_FILE = os.path.join(ROOT, "site", "data", "edits.json")
STATE_FILE = os.path.join(ROOT, "seen.json")
XXX_IMG = os.path.join(ASSETS, "xxx.jpg")

CELEBS_FILE = os.path.join(ROOT, "celebs.txt")

HEADERS = {"User-Agent": "death-splice-prototype/0.1 (personal project)"}
FAME_THRESHOLD = 1_000_000          # pageviews in the last 12 months (fallback mode)
WIKI = "https://en.wikipedia.org"
SPARQL = "https://query.wikidata.org/sparql"
SKIP_TITLES = re.compile(r"^(List of|Deaths in|Category:|Template:)", re.I)


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def download(url, path):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
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
        req = urllib.request.Request(SPARQL, data=body, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        for row in data["results"]["bindings"]:
            dead[row["name"]["value"]] = row["death"]["value"][:10]
    return dead


def check_list():
    """Primary mode: diff the celebrity list against Wikidata death dates.
    Everyone on the list who is dead but not yet on the timeline gets an
    edit, however long ago they died. The timeline itself is the record."""
    celebs = load_celebs()
    print(f"checking {len(celebs)} names against Wikidata...")
    dead = query_deaths(celebs)

    edits = load(DATA_FILE, [])
    have = {e["slug"] for e in edits}
    new = 0
    for title, death_date in sorted(dead.items(), key=lambda kv: kv[1]):
        if slugify(title) in have:
            continue
        print(f"  {title}: died {death_date}")
        ensure_base_image()
        entry = make_edit(title, died=death_date)
        if entry:
            edits.insert(0, entry)
            new += 1
            print(f"  ✔ edit created: {entry['image']}")
            notify(entry)
    if new:
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


# ---------------------------------------------------------------- pipeline
def ensure_base_image():
    if os.path.exists(XXX_IMG):
        return
    s = summary("XXXTentacion")
    img = s.get("originalimage", {}).get("source")
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
    img = s.get("originalimage", {}).get("source")
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
    a = p.parse_args()

    if a.demo:
        demo()
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
