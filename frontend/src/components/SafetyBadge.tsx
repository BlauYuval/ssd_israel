import clsx from "clsx";

interface Props {
  score: number | null;
  size?: "sm" | "md" | "lg";
}

function scoreColor(score: number) {
  if (score >= 70) return "bg-green-100 text-green-800 ring-green-200";
  if (score >= 50) return "bg-yellow-100 text-yellow-800 ring-yellow-200";
  if (score >= 30) return "bg-orange-100 text-orange-800 ring-orange-200";
  return "bg-red-100 text-red-800 ring-red-200";
}

function scoreLabel(score: number) {
  if (score >= 70) return "Safe";
  if (score >= 50) return "Moderate";
  if (score >= 30) return "Risky";
  return "Unsafe";
}

export default function SafetyBadge({ score, size = "md" }: Props) {
  if (score === null || score === undefined) {
    return <span className="text-gray-400 text-xs">N/A</span>;
  }
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full font-semibold ring-1",
        scoreColor(score),
        size === "sm" && "px-2 py-0.5 text-xs",
        size === "md" && "px-2.5 py-1 text-sm",
        size === "lg" && "px-3 py-1.5 text-base",
      )}
    >
      {score.toFixed(0)}
      <span className={clsx("font-normal", size === "sm" ? "text-xs" : "text-xs")}>
        {scoreLabel(score)}
      </span>
    </span>
  );
}
