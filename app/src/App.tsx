import { useCallback, useEffect, useRef, useState } from "react";
import Feed from "./components/Feed";
import Timeline from "./components/Timeline";
import Toast from "./components/Toast";
import { diedDate, fetchEdits, fetchGhosts } from "./lib";
import type { Edit, Ghost, RailInfo } from "./types";

const REFRESH_MS = 60_000;

export default function App() {
  const [edits, setEdits] = useState<Edit[] | null>(null); // null = loading
  const [ghosts, setGhosts] = useState<Ghost[]>([]);
  const [error, setError] = useState(false);
  const [toast, setToast] = useState(false);
  const [rail, setRail] = useState<RailInfo | null>(null);
  const pending = useRef<Edit[] | null>(null);  // data waiting behind toast
  const feedRef = useRef<HTMLElement | null>(null);

  const apply = useCallback((data: Edit[]) => {
    // newest first, with a stable tie-break so data[0] can't flip between
    // fetches (which would falsely re-fire the "new death" toast)
    data.sort((a, b) =>
      diedDate(b).getTime() - diedDate(a).getTime() ||
      b.detected_at.localeCompare(a.detected_at) ||
      a.slug.localeCompare(b.slug));
    setEdits((cur) => {
      const changed = !cur || data.length !== cur.length ||
        (data[0] && cur[0] && data[0].slug !== cur[0].slug);
      if (!changed) return cur;
      const feed = feedRef.current;
      const browsing = !!cur?.length && !!feed &&
        (feed.scrollLeft > window.innerWidth / 2 ||
         feed.scrollTop > window.innerHeight / 2);
      if (browsing) {                 // don't yank the page mid-scroll
        pending.current = data;
        setToast(true);
        return cur;
      }
      return data;
    });
  }, []);

  useEffect(() => {
    fetchGhosts().then(setGhosts);
    const tick = () =>
      fetchEdits().then((d) => { setError(false); apply(d); })
        .catch(() => setEdits((cur) => { if (!cur) setError(true); return cur; }));
    tick();
    const id = setInterval(tick, REFRESH_MS);
    return () => clearInterval(id);
  }, [apply]);

  const surfacePending = () => {
    setToast(false);
    if (pending.current) { setEdits(pending.current); pending.current = null; }
  };

  return (
    <>
      <header><h1>THE <span className="half">OTHER</span> HALF</h1></header>
      <Timeline info={rail} count={edits?.length ?? 0} feedRef={feedRef} />
      <Toast show={toast} onClick={surfacePending} />
      {error && !edits ? (
        <div className="note">
          couldn't load any edit data<br /><br />
          serve the site instead of opening the file:<br /><br />
          <code>./run.sh</code>
        </div>
      ) : edits === null ? (
        <div className="note">summoning…</div>
      ) : edits.length === 0 ? (
        <div className="note">
          no edits yet — the famous are all still alive.<br />
          the watcher checks every 15 minutes.
        </div>
      ) : (
        <Feed ref={feedRef} edits={edits} ghosts={ghosts} onRail={setRail} />
      )}
    </>
  );
}
