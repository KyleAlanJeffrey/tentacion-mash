import { daysSince, diedDate, fmt } from "../lib";
import type { Edit } from "../types";

export default function Card({ edit, i }: { edit: Edit; i: number }) {
  const died = diedDate(edit);
  const days = daysSince(died);
  const when = days === 0 ? "DIED TODAY"
             : days === 1 ? "DIED YESTERDAY"
             : "DIED " + fmt(died);

  return (
    <section className="card" data-i={i} data-year={died.getFullYear()}>
      <div className="frame">
        {days <= 1 && <div className="fresh">✝ just happened</div>}
        <img
          src={edit.image}
          alt={`XXXTentacion spliced with ${edit.title}`}
          loading={i < 2 ? "eager" : "lazy"}
          decoding="async"
        />
      </div>
      <div className="name">{edit.title} <span className="dead">Dead</span></div>
      <div className="when">{when}</div>
      <div className="cross">✝ ✝ ✝</div>
    </section>
  );
}
