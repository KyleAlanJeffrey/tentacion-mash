import { useRef, useState, type PointerEvent } from "react";
import { useIsMobile } from "../useIsMobile";
import type { RailInfo } from "../types";

interface TimelineProps {
  info: RailInfo | null;
  count: number;
  feedRef: React.RefObject<HTMLElement | null>;
}

const SKIP = 4; // cards jumped per side-button press

/** The timeline made interactive: a draggable scrubber that scans the whole
 * feed, flanked by skip buttons. Horizontal along the bottom on desktop,
 * vertical up the side on mobile. */
export default function Timeline({ info, count, feedRef }: TimelineProps) {
  const isMobile = useIsMobile();
  const trackRef = useRef<HTMLDivElement | null>(null);
  const [dragging, setDragging] = useState(false);

  if (!info || !count) return null;

  const range = () => {
    const feed = feedRef.current;
    if (!feed) return 0;
    return isMobile
      ? feed.scrollHeight - feed.clientHeight
      : feed.scrollWidth - feed.clientWidth;
  };

  const seek = (frac: number) => {
    const feed = feedRef.current;
    if (!feed) return;
    const to = Math.max(0, Math.min(1, frac)) * range();
    if (isMobile) feed.scrollTop = to;
    else feed.scrollLeft = to;
  };

  const fracFromPointer = (e: PointerEvent) => {
    const t = trackRef.current;
    if (!t) return 0;
    const r = t.getBoundingClientRect();
    return isMobile
      ? (e.clientY - r.top) / r.height
      : (e.clientX - r.left) / r.width;
  };

  const onDown = (e: PointerEvent) => {
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* noop */ }
    setDragging(true);
    seek(fracFromPointer(e));
  };
  const onMove = (e: PointerEvent) => {
    if (dragging) seek(fracFromPointer(e));
  };
  const onUp = (e: PointerEvent) => {
    setDragging(false);
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* noop */ }
  };

  const skip = (dir: number) => {
    const feed = feedRef.current;
    if (!feed) return;
    const card = feed.querySelector<HTMLElement>(".card");
    const stride = card
      ? (isMobile ? card.offsetHeight : card.offsetWidth)
      : (isMobile ? feed.clientHeight : feed.clientWidth);
    const by = dir * stride * SKIP;
    feed.scrollBy(isMobile ? { top: by, behavior: "smooth" }
                           : { left: by, behavior: "smooth" });
  };

  const pct = `${(info.progress * 100).toFixed(2)}%`;
  const fillStyle = isMobile ? { height: pct } : { width: pct };
  const handleStyle = isMobile ? { top: pct } : { left: pct };

  return (
    <div id="timeline" className={isMobile ? "v" : "h"}>
      <button className="tl-skip" onClick={() => skip(-1)}
        aria-label="Skip toward the present">
        {isMobile ? "▲" : "‹‹"}
      </button>

      <div className="tl-main">
        <div className="tl-meta">
          <span className="tl-year">{info.year}</span>
          <span className="tl-pos">{info.pos}</span>
        </div>
        <div
          ref={trackRef}
          className={"tl-track" + (dragging ? " drag" : "")}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
        >
          <div className="tl-fill" style={fillStyle} />
          <div className="tl-handle" style={handleStyle} />
        </div>
      </div>

      <button className="tl-skip" onClick={() => skip(1)}
        aria-label="Skip toward the past">
        {isMobile ? "▼" : "››"}
      </button>
    </div>
  );
}
