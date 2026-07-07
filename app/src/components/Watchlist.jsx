/** Ghosts of the not-yet-dead, hovering above the timeline. */
export default function Watchlist({ ghosts }) {
  if (!ghosts.length) return null;
  return (
    <section id="watch" data-year="SOON">
      <h2>The Watchlist</h2>
      <div className="sub">expected · any day now</div>
      <div id="ghosts">
        {ghosts.map((g) => (
          <div className="ghost" key={g.slug}>
            <div className="gframe">
              <img src={g.img} alt={g.name} loading="lazy" />
            </div>
            <div className="gname">{g.name}</div>
            <div className="soon">✝ soon</div>
          </div>
        ))}
      </div>
      <div className="descend">scroll ↓ back to the present</div>
    </section>
  );
}
