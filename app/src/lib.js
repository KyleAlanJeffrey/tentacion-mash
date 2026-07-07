const DAY = 864e5;

export const slugify = (t) =>
  t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

export const diedDate = (e) =>
  new Date((e.died || e.detected_at).slice(0, 10) + "T00:00:00");

const mid = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate());

export const daysSince = (d) => Math.round((mid(new Date()) - mid(d)) / DAY);

export const fmt = (d) =>
  d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
    .toUpperCase();

const ok = (r) => { if (!r.ok) throw new Error(r.status); return r; };

/** Production API first, local files as fallback (./run.sh mode). */
export const fetchEdits = () =>
  fetch("/api/edits", { cache: "no-store" }).then(ok).then((r) => r.json())
    .catch(() => fetch("/data/edits.json", { cache: "no-store" })
      .then(ok).then((r) => r.json()));

/** The watchlist: names from deathwatch.txt + portraits from Wikipedia. */
export const fetchGhosts = () =>
  fetch("/deathwatch.txt", { cache: "no-store" }).then(ok).then((r) => r.text())
    .then((txt) => {
      const names = txt.split("\n").map((s) => s.trim())
        .filter((s) => s && !s.startsWith("#"));
      return Promise.all(names.map((n) =>
        fetch("https://en.wikipedia.org/api/rest_v1/page/summary/" +
              encodeURIComponent(n.replaceAll(" ", "_")))
          .then(ok).then((r) => r.json())
          .then((s) => ({ name: n, slug: slugify(n),
                          img: s.thumbnail?.source || null }))
          .catch(() => null)));
    })
    .then((list) => (list || []).filter((g) => g && g.img))
    .catch(() => []);
