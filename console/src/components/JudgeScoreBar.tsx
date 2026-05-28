export function JudgeScoreBar({ score }: { score: number }) {
  const pct = Math.max(Math.round(score * 100), score > 0 ? 1 : 2);
  const color =
    score >= 0.85
      ? "bg-green-500"
      : score >= 0.7
      ? "bg-amber-400"
      : "bg-red-500";
  const textColor =
    score >= 0.85
      ? "text-green-700"
      : score >= 0.7
      ? "text-amber-700"
      : "text-red-700";

  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-gray-500">LLM-Judge Consistency</span>
        <span className={`text-sm font-semibold ${textColor}`}>{score.toFixed(2)}</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-gray-300">
        <span>0</span>
        <span className="text-gray-400">threshold: 0.85</span>
        <span>1</span>
      </div>
    </div>
  );
}
