import type { Edit, Ghost } from "./types";

const DAY = 864e5;

export const slugify = (t: string): string =>
  t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

export const diedDate = (e: Edit): Date =>
  new Date((e.died || e.detected_at).slice(0, 10) + "T00:00:00");

const mid = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate());

export const daysSince = (d: Date): number =>
  Math.round((mid(new Date()).getTime() - mid(d).getTime()) / DAY);

export const fmt = (d: Date): string =>
  d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
    .toUpperCase();

const ok = (r: Response): Response => {
  if (!r.ok) throw new Error(String(r.status));
  return r;
};

/** Production API first, local files as fallback (./run.sh mode). */
export const fetchEdits = (): Promise<Edit[]> =>
  fetch("/api/edits", { cache: "no-store" }).then(ok).then((r) => r.json())
    .catch(() => fetch("/data/edits.json", { cache: "no-store" })
      .then(ok).then((r) => r.json()));

interface WikiSummary {
  thumbnail?: { source?: string };
}

/** The watchlist: names from deathwatch.txt + portraits from Wikipedia. */
export const fetchGhosts = (): Promise<Ghost[]> =>
  fetch("/deathwatch.txt", { cache: "no-store" }).then(ok).then((r) => r.text())
    .then((txt) => {
      const names = txt.split("\n").map((s) => s.trim())
        .filter((s) => s && !s.startsWith("#"));
      return Promise.all(names.map((n) =>
        fetch("https://en.wikipedia.org/api/rest_v1/page/summary/" +
              encodeURIComponent(n.replaceAll(" ", "_")))
          .then(ok).then((r) => r.json() as Promise<WikiSummary>)
          .then((s) => ({ name: n, slug: slugify(n),
                          img: s.thumbnail?.source ?? null }))
          .catch(() => null)));
    })
    .then((list) =>
      (list ?? []).filter((g): g is Ghost => !!g && !!g.img))
    .catch(() => []);
