import { useState } from "react";
import type { Ghost } from "../types";

function GhostCard({ g }: { g: Ghost }) {
  const [loaded, setLoaded] = useState(false);
  return (
    <div className="ghost">
      <div className={"gframe" + (loaded ? " loaded" : "")}>
        <img
          src={g.img}
          alt={g.name}
          loading="lazy"
          onLoad={() => setLoaded(true)}
          onError={() => setLoaded(true)}
        />
        <img className="xxx" src="/xxx.jpg" alt="" aria-hidden="true" />
      </div>
      <div className="gname">{g.name}</div>
      <div className="soon">✝ soon</div>
    </div>
  );
}

/** Ghosts of the not-yet-dead, hovering above the timeline. XXX's half
 * fades in and out over each portrait — the edit, materializing early. */
export default function Watchlist({ ghosts }: { ghosts: Ghost[] }) {
  if (!ghosts.length) return null;
  return (
    <section id="watch" data-year="SOON">
      <h2>The Watchlist</h2>
      <div className="sub">expected · any day now</div>
      <div id="ghosts">
        {ghosts.map((g) => <GhostCard key={g.slug} g={g} />)}
      </div>
      <div className="descend">scroll ↓ back to the present</div>
    </section>
  );
}
