import clsx from "clsx";

interface Props {
  label: string;
  score: number;
  max: number;
  detail: string;
}

export default function ScoreBar({ label, score, max, detail }: Props) {
  const pct = Math.round((score / max) * 100);
  const color =
    pct >= 75 ? "bg-green-500" : pct >= 50 ? "bg-yellow-400" : pct >= 25 ? "bg-orange-400" : "bg-red-500";

  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="font-medium text-gray-700">{label}</span>
        <span className="text-gray-500">
          {score}/{max} · {detail}
        </span>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-2">
        <div className={clsx("h-2 rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
