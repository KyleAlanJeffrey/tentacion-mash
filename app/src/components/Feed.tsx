import { forwardRef, useEffect, useLayoutEffect, useRef } from "react";
import Card from "./Card";
import Watchlist from "./Watchlist";
import { useIsMobile } from "../useIsMobile";
import type { Edit, Ghost, RailInfo } from "../types";

interface FeedProps {
  edits: Edit[];
  ghosts: Ghost[];
  onRail: (info: RailInfo) => void;
}

/** The timeline. Horizontal on desktop (future on the left, past to the
 * right), vertical on mobile (future above, past below). Free, fast
 * scrolling — no snapping; the rail tracks whatever's nearest center. */
const Feed = forwardRef<HTMLElement, FeedProps>(function Feed(
  { edits, ghosts, onRail }, outerRef,
) {
  const feedRef = useRef<HTMLElement | null>(null);
  const isMobile = useIsMobile();
  const setRefs = (el: HTMLElement | null) => {
    feedRef.current = el;
    if (typeof outerRef === "function") outerRef(el);
    else if (outerRef) outerRef.current = el;
  };

  const alive = ghosts.filter((g) => !edits.some((e) => e.slug === g.slug));

  const sections = () =>
    [...(feedRef.current?.querySelectorAll<HTMLElement>("#watch, .card") ?? [])];

  const nearestIndex = () => {
    const feed = feedRef.current;
    if (!feed) return 0;
    const center = isMobile
      ? feed.scrollTop + feed.clientHeight / 2
      : feed.scrollLeft + feed.clientWidth / 2;
    let best = Infinity, cur = 0;
    sections().forEach((s, k) => {
      const c = isMobile
        ? s.offsetTop + s.offsetHeight / 2
        : s.offsetLeft + s.offsetWidth / 2;
      const d = Math.abs(c - center);
      if (d < best) { best = d; cur = k; }
    });
    return cur;
  };

  // land on the present whenever the feed is (re)built
  useLayoutEffect(() => {
    const feed = feedRef.current;
    const watch = feed?.querySelector<HTMLElement>("#watch");
    if (!feed || !watch) return;
    if (isMobile) feed.scrollTop = watch.offsetHeight;
    else feed.scrollLeft = watch.offsetWidth;
  }, [edits, alive.length, isMobile]);

  // rail follows whichever card is nearest the viewport center
  useEffect(() => {
    const feed = feedRef.current;
    if (!feed) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const els = sections();
      if (!els.length) return;
      const range = isMobile
        ? feed.scrollHeight - feed.clientHeight
        : feed.scrollWidth - feed.clientWidth;
      const scrolled = isMobile ? feed.scrollTop : feed.scrollLeft;
      const progress = range > 0 ? Math.min(1, Math.max(0, scrolled / range)) : 0;
      const el = els[nearestIndex()];
      if (el.id === "watch") {
        onRail({ year: "SOON", pos: "the future", fill: 0, top: true, progress });
      } else {
        const i = Number(el.dataset.i);
        onRail({
          year: el.dataset.year ?? "",
          pos: `${i + 1} / ${edits.length}`,
          fill: edits.length < 2 ? 100 : (i / (edits.length - 1)) * 100,
          top: i === 0,
          progress,
        });
      }
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(update); };
    feed.addEventListener("scroll", onScroll, { passive: true });
    update();
    return () => {
      feed.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(raf);
    };
  }, [edits, alive.length, onRail, isMobile]);

  // entrance animations
  useEffect(() => {
    const feed = feedRef.current;
    if (!feed) return;
    const io = new IntersectionObserver((entries) => {
      for (const x of entries)
        if (x.isIntersecting) x.target.classList.add("vis");
    }, { root: feed, threshold: 0.25 });
    sections().forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [edits, alive.length]);

  // desktop: vertical wheel drives horizontal travel
  useEffect(() => {
    if (isMobile) return;
    const feed = feedRef.current;
    if (!feed) return;
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        feed.scrollLeft += e.deltaY * 2.2;
        e.preventDefault();
      }
    };
    feed.addEventListener("wheel", onWheel, { passive: false });
    return () => feed.removeEventListener("wheel", onWheel);
  }, [isMobile, edits, alive.length]);

  // keyboard: arrows step card by card
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      const dir = ["ArrowDown", "ArrowRight", "PageDown", " "].includes(ev.key) ? 1
                : ["ArrowUp", "ArrowLeft", "PageUp"].includes(ev.key) ? -1 : 0;
      if (!dir) return;
      ev.preventDefault();
      const els = sections();
      if (!els.length) return;
      const next = Math.max(0, Math.min(els.length - 1, nearestIndex() + dir));
      els[next].scrollIntoView({
        behavior: "smooth",
        inline: isMobile ? "nearest" : "center",
        block: isMobile ? "start" : "nearest",
      });
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isMobile]);

  return (
    <main id="feed" ref={setRefs}>
      <Watchlist ghosts={alive} />
      {edits.map((e, i) => <Card key={e.slug} edit={e} i={i} />)}
    </main>
  );
});

export default Feed;
