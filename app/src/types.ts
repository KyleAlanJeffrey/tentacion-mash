/** One edit as returned by the worker API / local edits.json. */
export interface Edit {
  slug: string;
  title: string;
  died: string | null;          // YYYY-MM-DD from Wikidata
  detected_at: string;          // ISO timestamp
  image: string;                // /images/<slug>.jpg or edits/<slug>.jpg
  description?: string;
  wiki_url?: string;
  pageviews?: number | null;
}

/** A watchlist member (still breathing). */
export interface Ghost {
  name: string;
  slug: string;
  img: string;
}

/** What the timeline scrubber displays for the current section. */
export interface RailInfo {
  year: string;
  pos: string;
  fill: number;                 // 0..100, progress into the past
  top: boolean;                 // at the newest death (or above)
  progress: number;             // 0..1, overall scroll position (drives the slider handle)
}
