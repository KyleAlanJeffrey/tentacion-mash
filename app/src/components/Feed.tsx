import { forwardRef, useEffect, useLayoutEffect, useRef } from "react";
import Card from "./Card";
import Watchlist from "./Watchlist";
import type { Edit, Ghost, RailInfo } from "../types";

interface FeedProps {
  edits: Edit[];
  ghosts: Ghost[];
  onRail: (info: RailInfo) => void;
}

/** Full-screen scroll-snap feed. The watchlist (the future) sits above the
 * newest death; the page lands on the present and you scroll up into the
 * future, down into the past. */
const Feed = forwardRef<HTMLElement, FeedProps>(function Feed(
  { edits, ghosts, onRail }, outerRef,
) {
  const feedRef = useRef<HTMLElement | null>(null);
  const setRefs = (el: HTMLElement | null) => {
    feedRef.current = el;
    if (typeof outerRef === "function") outerRef(el);
    else if (outerRef) outerRef.current = el;
  };

  const alive = ghosts.filter((g) => !edits.some((e) => e.slug === g.slug));

  // land on the present whenever the feed is (re)built
  useLayoutEffect(() => {
    const feed = feedRef.current;
    const watch = feed?.querySelector<HTMLElement>("#watch");
    if (feed && watch) feed.scrollTop = watch.offsetHeight;
  }, [edits, alive.length]);

  // rail updates + entrance animations
  useEffect(() => {
    const feed = feedRef.current;
    if (!feed) return;
    const io = new IntersectionObserver((entries) => {
      for (const x of entries) {
        if (!x.isIntersecting) continue;
        const el = x.target as HTMLElement;
        el.classList.add("vis");
        if (el.id === "watch") {
          onRail({ year: "SOON", pos: "the future", fill: 0, top: true });
        } else {
          const i = Number(el.dataset.i);
          onRail({
            year: el.dataset.year ?? "",
            pos: `${i + 1} / ${edits.length}`,
            fill: edits.length < 2 ? 100 : (i / (edits.length - 1)) * 100,
            top: i === 0,
          });
        }
      }
    }, { root: feed, threshold: 0.55 });
    feed.querySelectorAll(".card, #watch").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [edits, alive.length, onRail]);

  // keyboard: step section by section
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      const dir = ["ArrowDown", "ArrowRight", "PageDown", " "].includes(ev.key) ? 1
                : ["ArrowUp", "ArrowLeft", "PageUp"].includes(ev.key) ? -1 : 0;
      if (!dir) return;
      ev.preventDefault();
      const feed = feedRef.current;
      if (!feed) return;
      const sections = [...feed.querySelectorAll<HTMLElement>("#watch, .card")];
      if (!sections.length) return;
      let cur = 0, best = Infinity;
      sections.forEach((s, k) => {
        const d = Math.abs(s.offsetTop - feed.scrollTop);
        if (d < best) { best = d; cur = k; }
      });
      sections[Math.max(0, Math.min(sections.length - 1, cur + dir))]
        .scrollIntoView({ behavior: "smooth" });
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <main id="feed" ref={setRefs}>
      <Watchlist ghosts={alive} />
      {edits.map((e, i) => <Card key={e.slug} edit={e} i={i} />)}
    </main>
  );
});

export default Feed;
