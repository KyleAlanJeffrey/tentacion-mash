export default function Toast(
  { show, onClick }: { show: boolean; onClick: () => void },
) {
  return (
    <button id="toast" className={show ? "show" : ""} onClick={onClick}>
      ✝ a new death — return to the top
    </button>
  );
}
