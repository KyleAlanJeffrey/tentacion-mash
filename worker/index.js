// worker/index.js — THE OTHER HALF, full Cloudflare stack.
//
//   GET    /api/edits            list all edits (newest death first)
//   GET    /api/edits/:slug      one edit
//   POST   /api/edits            upsert metadata            (Bearer INGEST_TOKEN)
//   PUT    /api/images/:slug     upload the splice jpeg     (Bearer INGEST_TOKEN)
//   DELETE /api/edits/:slug      remove edit + image        (Bearer INGEST_TOKEN)
//   GET    /images/:file         serve images from R2
//   *                            static site from the assets binding
//
// A cron trigger polls Wikidata for deaths on celebs.txt. Image generation
// needs Python (face detection), so on a new death the cron dispatches the
// GitHub Action, which generates the edit and POSTs it back here.

const UA = "the-other-half-worker/0.1 (github.com/KyleAlanJeffrey/tentacion-mash)";
const CORS = { "access-control-allow-origin": "*" };

const slugify = (t) =>
  t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

const json = (data, status = 200) =>
  new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { "content-type": "application/json;charset=utf-8", ...CORS },
  });

const authed = (req, env) =>
  env.INGEST_TOKEN &&
  req.headers.get("authorization") === `Bearer ${env.INGEST_TOKEN}`;

// image URL is derived, not stored
const rowToEdit = (r) => ({ ...r, image: `/images/${r.slug}.jpg` });

export default {
  async fetch(req, env) {
    const { pathname: p } = new URL(req.url);
    const m = req.method;

    if (m === "OPTIONS")
      return new Response(null, {
        headers: { ...CORS, "access-control-allow-methods": "GET",
                   "access-control-allow-headers": "content-type" },
      });

    if (p === "/api/edits" && m === "GET") {
      const { results } = await env.DB.prepare(
        "SELECT * FROM edits ORDER BY died DESC, detected_at DESC").all();
      return json(results.map(rowToEdit));
    }

    if (p.match(/^\/api\/edits\/[^/]+$/) && m === "GET") {
      const row = await env.DB.prepare("SELECT * FROM edits WHERE slug=?")
        .bind(p.split("/")[3]).first();
      return row ? json(rowToEdit(row)) : json({ error: "not found" }, 404);
    }

    if (p === "/api/edits" && m === "POST") {
      if (!authed(req, env)) return json({ error: "unauthorized" }, 401);
      const e = await req.json();
      if (!e.slug || !e.title) return json({ error: "slug and title required" }, 400);
      await env.DB.prepare(
        `INSERT INTO edits (slug, title, died, description, wiki_url, detected_at, pageviews)
         VALUES (?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(slug) DO UPDATE SET
           title=excluded.title, died=excluded.died, description=excluded.description,
           wiki_url=excluded.wiki_url, detected_at=excluded.detected_at,
           pageviews=excluded.pageviews`)
        .bind(e.slug, e.title, e.died ?? null, e.description ?? "",
              e.wiki_url ?? "", e.detected_at ?? new Date().toISOString(),
              e.pageviews_last_year ?? null)
        .run();
      return json({ ok: true, slug: e.slug, image: `/images/${e.slug}.jpg` });
    }

    if (p.match(/^\/api\/images\/[^/]+$/) && m === "PUT") {
      if (!authed(req, env)) return json({ error: "unauthorized" }, 401);
      const slug = p.split("/")[3];
      await env.IMAGES.put(`${slug}.jpg`, req.body, {
        httpMetadata: { contentType: "image/jpeg" },
      });
      return json({ ok: true, image: `/images/${slug}.jpg` });
    }

    if (p.match(/^\/api\/edits\/[^/]+$/) && m === "DELETE") {
      if (!authed(req, env)) return json({ error: "unauthorized" }, 401);
      const slug = p.split("/")[3];
      await env.DB.prepare("DELETE FROM edits WHERE slug=?").bind(slug).run();
      await env.IMAGES.delete(`${slug}.jpg`);
      return json({ ok: true });
    }

    if (p.startsWith("/images/") && m === "GET") {
      const obj = await env.IMAGES.get(decodeURIComponent(p.slice(8)));
      if (!obj) return new Response("not found", { status: 404 });
      return new Response(obj.body, {
        headers: {
          "content-type": obj.httpMetadata?.contentType ?? "image/jpeg",
          "cache-control": "public, max-age=3600",
          etag: obj.httpEtag,
          ...CORS,
        },
      });
    }

    return env.ASSETS.fetch(req); // the site itself
  },

  async scheduled(_event, env, ctx) {
    ctx.waitUntil(checkForDeaths(env));
  },
};

// ------------------------------------------------------------- cron side
async function checkForDeaths(env) {
  if (!env.GITHUB_REPO) return console.log("GITHUB_REPO not set — cron idle");
  const names = await celebList(env);
  const dead = await queryDeaths(names);
  const { results } = await env.DB.prepare("SELECT slug FROM edits").all();
  const have = new Set(results.map((r) => r.slug));
  const fresh = Object.keys(dead).filter((t) => !have.has(slugify(t)));
  if (!fresh.length) return console.log(`checked ${names.length} names — no new deaths`);

  console.log("NEW DEATHS:", fresh.join(", "), "— dispatching generator");
  if (!env.GITHUB_TOKEN) return console.log("GITHUB_TOKEN not set — cannot dispatch");
  const r = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/watch.yml/dispatches`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.GITHUB_TOKEN}`,
        accept: "application/vnd.github+json",
        "user-agent": UA,
      },
      body: JSON.stringify({ ref: "main" }),
    },
  );
  console.log("dispatch:", r.status);
}

async function celebList(env) {
  const r = await fetch(
    `https://raw.githubusercontent.com/${env.GITHUB_REPO}/main/celebs.txt`,
    { headers: { "user-agent": UA } },
  );
  if (!r.ok) throw new Error(`celebs.txt fetch: ${r.status}`);
  return (await r.text()).split("\n").map((s) => s.trim())
    .filter((s) => s && !s.startsWith("#"));
}

async function queryDeaths(names, batchSize = 250) {
  const dead = {};
  for (let i = 0; i < names.length; i += batchSize) {
    const values = names.slice(i, i + batchSize)
      .map((n) => `"${n.replace(/"/g, '\\"')}"@en`).join(" ");
    const q = `SELECT ?name ?death WHERE {
      VALUES ?name { ${values} }
      ?article schema:about ?p ;
               schema:isPartOf <https://en.wikipedia.org/> ;
               schema:name ?name .
      ?p wdt:P570 ?death . }`;
    const r = await fetch("https://query.wikidata.org/sparql", {
      method: "POST",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": UA,
      },
      body: new URLSearchParams({ query: q, format: "json" }),
    });
    if (!r.ok) throw new Error(`wikidata: ${r.status}`);
    const data = await r.json();
    for (const row of data.results.bindings)
      dead[row.name.value] = row.death.value.slice(0, 10);
  }
  return dead;
}
