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
// Every 15 minutes the cron wakes the generator container (native Python +
// OpenCV — see container/), which diffs celebs.txt against Wikidata,
// generates splices for new deaths, and publishes back through this API.
// The container exits in ~2s when nobody has died, so it costs pennies.

import { Container } from "@cloudflare/containers";

const CORS = { "access-control-allow-origin": "*" };

export class Generator extends Container {
  defaultPort = 8080;
  sleepAfter = "5m";
  constructor(ctx, env) {
    super(ctx, env);
    this.envVars = {
      WORKER_URL: env.SELF_URL ?? "",
      INGEST_TOKEN: env.INGEST_TOKEN ?? "",
      WIKIMEDIA_TOKEN: env.WIKIMEDIA_TOKEN ?? "",
    };
  }
}

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

    // ------------------------------------------------------------ SEO
    if (p === "/og.jpg" && m === "GET") {
      // social preview = always the newest edit
      const top = await env.DB.prepare(
        "SELECT slug FROM edits ORDER BY died DESC, detected_at DESC LIMIT 1").first();
      const obj = top && await env.IMAGES.get(`${top.slug}.jpg`);
      if (obj)
        return new Response(obj.body, {
          headers: { "content-type": "image/jpeg",
                     "cache-control": "public, max-age=600", ...CORS },
        });
      return env.ASSETS.fetch(new Request(new URL("/xxx.jpg", req.url)));
    }

    if (p === "/sitemap.xml" && m === "GET") {
      const { results } = await env.DB.prepare(
        "SELECT slug, title, died FROM edits ORDER BY died DESC").all();
      const base = env.SELF_URL || new URL(req.url).origin;
      const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      const images = results.map((e) => `  <image:image>
    <image:loc>${base}/images/${e.slug}.jpg</image:loc>
    <image:title>${esc(e.title)} Dead — spliced with XXXTentacion</image:title>
  </image:image>`).join("\n");
      const lastmod = (results[0]?.died ?? new Date().toISOString().slice(0, 10));
      const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
<url>
  <loc>${base}/</loc>
  <lastmod>${lastmod}</lastmod>
  <changefreq>hourly</changefreq>
${images}
</url>
</urlset>`;
      return new Response(xml, {
        headers: { "content-type": "application/xml",
                   "cache-control": "public, max-age=3600" },
      });
    }

    if (p === "/robots.txt" && m === "GET") {
      const base = env.SELF_URL || new URL(req.url).origin;
      return new Response(`User-agent: *\nAllow: /\n\nSitemap: ${base}/sitemap.xml\n`,
        { headers: { "content-type": "text/plain" } });
    }

    if ((p === "/" || p === "/index.html") && m === "GET")
      return seoRewrite(await env.ASSETS.fetch(req), env);

    return env.ASSETS.fetch(req); // the site itself
  },

  async scheduled(_event, env, ctx) {
    ctx.waitUntil(checkForDeaths(env));
  },
};

// ---------------------------------------------------------------- edge SEO
// The app is client-rendered, so at the edge we rewrite the HTML to feature
// the newest death in title/description, inject JSON-LD structured data,
// and add a <noscript> timeline crawlers (and JS-less humans) can read.
async function seoRewrite(res, env) {
  try {
    if (typeof HTMLRewriter === "undefined") return res;
    const { results } = await env.DB.prepare(
      "SELECT slug, title, died FROM edits ORDER BY died DESC, detected_at DESC LIMIT 100"
    ).all();
    if (!results.length) return res;
    const base = env.SELF_URL || "";
    const top = results[0];
    const title = `${top.title} Dead — THE OTHER HALF`;
    const desc = `${top.title} died ${top.died}. Every celebrity death, ` +
      `spliced with XXXTentacion within minutes — an automatic memorial ` +
      `timeline, ${results.length}+ edits and counting.`;

    const ld = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "ImageGallery",
      name: "THE OTHER HALF",
      url: base + "/",
      description: "Every celebrity death, spliced with XXXTentacion. " +
        "An automatic memorial timeline.",
      image: results.slice(0, 25).map((e) => ({
        "@type": "ImageObject",
        contentUrl: `${base}/images/${e.slug}.jpg`,
        name: `${e.title} Dead`,
        description: `${e.title} (died ${e.died}) spliced with XXXTentacion`,
        datePublished: e.died,
      })),
    });

    const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const noscript = `<noscript><h1>THE OTHER HALF — every celebrity death, ` +
      `spliced with XXXTentacion</h1><ol>` +
      results.map((e) =>
        `<li><a href="${base}/images/${e.slug}.jpg">${esc(e.title)} Dead` +
        `</a> — died ${e.died}</li>`).join("") +
      `</ol></noscript>`;

    const setContent = (v) => ({ element(el) { el.setAttribute("content", v); } });
    return new HTMLRewriter()
      .on("title", { element(el) { el.setInnerContent(title); } })
      .on('meta[name="description"]', setContent(desc))
      .on('meta[property="og:title"]', setContent(title))
      .on('meta[property="og:description"]', setContent(desc))
      .on('meta[name="twitter:title"]', setContent(title))
      .on('meta[name="twitter:description"]', setContent(desc))
      .on("head", { element(el) {
        el.append(`<script type="application/ld+json">${ld}</script>`,
                  { html: true });
      }})
      .on("body", { element(el) { el.append(noscript, { html: true }); } })
      .transform(res);
  } catch (e) {
    console.log("seo rewrite failed:", e);
    return res;
  }
}

// ------------------------------------------------------------- cron side
async function checkForDeaths(env) {
  const stub = env.GENERATOR.get(env.GENERATOR.idFromName("generator"));
  const r = await stub.fetch("https://generator/generate", { method: "POST" });
  const out = await r.text();
  console.log("generator:", r.status, out.slice(-800));
}
