export default function Toast({ show, onClick }) {
  return (
    <button id="toast" className={show ? "show" : ""} onClick={onClick}>
      ✝ a new death — return to the top
    </button>
  );
}
