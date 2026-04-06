interface Props {
  score: number | null;
  size?: "sm" | "md" | "lg";
}

function scoreInfo(score: number): { label: string; borderColor: string; textColor: string } {
  if (score >= 61) return { label: "Safe",       borderColor: "#0038B8", textColor: "#0038B8" };
  if (score >= 41) return { label: "Borderline", borderColor: "#ca8a04", textColor: "#854d0e" };
  if (score >= 21) return { label: "Unsafe",     borderColor: "#ea580c", textColor: "#9a3412" };
  return              { label: "Very Unsafe", borderColor: "#dc2626", textColor: "#7f1d1d" };
}

export default function SafetyBadge({ score, size = "md" }: Props) {
  if (score === null || score === undefined) {
    return <span className="text-gray-400 text-xs">N/A</span>;
  }
  const { label, borderColor, textColor } = scoreInfo(score);
  const isLg = size === "lg";
  return (
    <div
      className={`inline-flex flex-col items-center border-2 rounded bg-white ${isLg ? "px-3 py-2 min-w-[56px]" : "px-2 py-1 min-w-[44px]"}`}
      style={{ borderColor, color: textColor }}
    >
      <span className={`font-bold leading-none ${isLg ? "text-2xl" : "text-base"}`}>
        {score.toFixed(0)}
      </span>
      <span className={`leading-none mt-0.5 ${isLg ? "text-xs" : "text-[10px]"}`}>
        {label}
      </span>
    </div>
  );
}
