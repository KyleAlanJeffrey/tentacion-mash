import type { RailInfo } from "../types";

interface RailProps {
  info: RailInfo | null;
  count: number;
}

/** Fixed side rail: year you're passing, position, progress into the past. */
export default function Rail({ info, count }: RailProps) {
  if (!info || !count) return null;
  return (
    <>
      <aside id="rail">
        <div id="railYear">{info.year}</div>
        <div id="railPos">{info.pos}</div>
        <div id="railBar">
          <div id="railFill" style={{ height: `${info.fill}%` }} />
        </div>
      </aside>
      {info.top && <div id="hint">↑ the future · the past ↓</div>}
    </>
  );
}
