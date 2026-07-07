import { useCallback, useEffect, useRef, useState } from "react";
import Feed from "./components/Feed.jsx";
import Rail from "./components/Rail.jsx";
import Toast from "./components/Toast.jsx";
import { diedDate, fetchEdits, fetchGhosts } from "./lib.js";

const REFRESH_MS = 60_000;

export default function App() {
  const [edits, setEdits] = useState(null);       // null = loading
  const [ghosts, setGhosts] = useState([]);
  const [error, setError] = useState(false);
  const [toast, setToast] = useState(false);
  const [rail, setRail] = useState(null);         // {year, pos, fill, top}
  const pending = useRef(null);                   // data waiting behind toast
  const feedRef = useRef(null);

  const apply = useCallback((data) => {
    data.sort((a, b) => diedDate(b) - diedDate(a));
    setEdits((cur) => {
      const changed = !cur || data.length !== cur.length ||
        (data[0] && cur[0] && data[0].slug !== cur[0].slug);
      if (!changed) return cur;
      const browsing = cur?.length &&
        (feedRef.current?.scrollTop ?? 0) > window.innerHeight / 2;
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
      <Rail info={rail} count={edits?.length ?? 0} />
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
