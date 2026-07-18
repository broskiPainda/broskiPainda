export default function LessonsList({ lessons }) {
  if (!lessons || lessons.length === 0) {
    return <p className="text-sm text-parchment/50 italic">No lessons recorded.</p>;
  }

  return (
    <ul className="space-y-2">
      {lessons.map((l, i) => (
        <li key={i} className="border-l-2 border-parchment/20 pl-3">
          <p className="text-sm">{l.principle}</p>
          <p className="text-xs text-parchment/50 mt-0.5">Limits: {l.transferability_limits}</p>
        </li>
      ))}
    </ul>
  );
}
