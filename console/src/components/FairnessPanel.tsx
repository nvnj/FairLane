import type { AuditPacket } from "../types";
import { JudgeScoreBar } from "./JudgeScoreBar";


function fmtPct(n: number | null | undefined) {
  return n == null ? "—" : `${n.toFixed(2)}%`;
}

function fmtUSD(n: number | null | undefined) {
  return n == null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

const ATTR_LABELS: Record<string, string> = {
  derived_race: "Race",
  derived_sex: "Sex",
  derived_ethnicity: "Ethnicity",
};

export function FairnessPanel({ audit }: { audit: AuditPacket | undefined }) {
  if (!audit) return null;

  const { variants, metrics, packet, baseline } = audit;

  if (!variants || !metrics || !packet || !baseline) return null;

  const thresholds = {
    flip_rate: parseFloat(import.meta.env.VITE_ESCALATION_FLIP_THRESHOLD ?? "0"),
    judge_score: parseFloat(import.meta.env.VITE_ESCALATION_JUDGE_THRESHOLD ?? "0.85"),
    terms_gap: parseFloat(import.meta.env.VITE_ESCALATION_TERMS_GAP_THRESHOLD ?? "0.05"),
  };

  const isEscalate = packet.recommended_action === "escalate";
  const hasFlips = metrics.flip_rate > thresholds.flip_rate;
  const judgeFlag = !hasFlips && metrics.judge_score < thresholds.judge_score;

  const escalationTitle = hasFlips
    ? "Bias signal detected — human review required"
    : judgeFlag
    ? "Reasoning quality flag — human review recommended"
    : "Escalated for review";

  const escalationBody = hasFlips
    ? packet.summary
    : judgeFlag
    ? "No decision flips detected across any variant. However, the LLM-judge consistency score is below threshold, suggesting the reasoning quality may be inconsistent. Decision appears consistent but manual review is recommended."
    : packet.summary;

  return (
    <div className="space-y-4">
      {isEscalate && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-5 py-4 flex items-start gap-3">
          <span className="text-lg mt-0.5">⚠</span>
          <div>
            <p className="text-sm font-semibold text-red-800">{escalationTitle}</p>
            <p className="text-sm text-red-600 mt-0.5">{escalationBody}</p>
          </div>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest">
            Variant Matrix
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="text-left px-4 py-2 text-xs font-semibold text-gray-500 w-32">Attribute</th>
                <th className="text-left px-4 py-2 text-xs font-semibold text-gray-500">Value</th>
                <th className="text-left px-4 py-2 text-xs font-semibold text-gray-500 w-28">Decision</th>
                <th className="text-right px-4 py-2 text-xs font-semibold text-gray-500 w-20">Rate</th>
                <th className="text-right px-4 py-2 text-xs font-semibold text-gray-500 w-28">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {variants.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-4 text-sm text-gray-400 text-center">
                    No variants generated
                  </td>
                </tr>
              ) : (
                variants.map((v, i) => {
                  const isFlip = v.decision !== baseline?.decision;
                  const decisionBadge: Record<string, string> = {
                    approve: "bg-green-100 text-green-700",
                    deny:    "bg-red-100 text-red-700",
                    refer:   "bg-amber-100 text-amber-700",
                  };
                  // Show the actual variant decision (populated from variant_decisions zip)
                  // Flipped rows highlight with a red row background
                  const displayDecision = v.decision ?? baseline?.decision;
                  const badgeCls = decisionBadge[displayDecision ?? ""] ?? "bg-gray-100 text-gray-600";
                  return (
                    <tr key={i} className={isFlip ? "bg-red-50/40" : ""}>
                      <td className="px-4 py-2.5 text-xs text-gray-400 font-medium">
                        {ATTR_LABELS[v.swept_attribute] ?? v.swept_attribute}
                      </td>
                      <td className="px-4 py-2.5 text-gray-700">{v.swept_value}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${badgeCls}`}>
                          {(displayDecision ?? "—").toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-xs font-mono text-gray-600">
                        {v.rate != null ? fmtPct(v.rate) : "–"}
                      </td>
                      <td className="px-4 py-2.5 text-right text-xs font-mono text-gray-600">
                        {v.amount != null ? fmtUSD(v.amount) : "–"}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="px-5 py-3 border-t border-gray-100 bg-gray-50">
          <div className="grid grid-cols-3 gap-4 mb-4">
            <Metric
              label="Flip Rate"
              value={`${(metrics.flip_rate * 100).toFixed(1)}%`}
              threshold={`threshold: ${(thresholds.flip_rate * 100).toFixed(0)}%`}
              alert={metrics.flip_rate > thresholds.flip_rate}
            />
            <Metric
              label="Approval Rate Gap"
              value={`${(metrics.approval_rate_gap * 100).toFixed(1)}%`}
              threshold="across groups"
              alert={metrics.approval_rate_gap > 0.05}
            />
            <Metric
              label="Terms Gap"
              value={`${metrics.terms_gap.toFixed(2)}%`}
              threshold={`threshold: ${thresholds.terms_gap.toFixed(2)}%`}
              alert={metrics.terms_gap > thresholds.terms_gap}
            />
          </div>
          <JudgeScoreBar score={metrics.judge_score} />
        </div>

        <div className="px-5 py-2 border-t border-gray-100 bg-gray-50">
          <p className="text-xs text-gray-400">
            Escalation thresholds — flip_rate &gt; {thresholds.flip_rate} · judge_score &lt; {thresholds.judge_score} · terms_gap &gt; {thresholds.terms_gap}%
          </p>
        </div>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">
              Router Packet
            </h2>
            <p className="text-sm font-semibold text-gray-900">{packet.headline}</p>
          </div>
          <span className={`shrink-0 inline-flex items-center px-2.5 py-1 rounded text-xs font-semibold ${isEscalate ? "bg-red-100 text-red-700 border border-red-200" : "bg-green-100 text-green-700 border border-green-200"}`}>
            {isEscalate ? "ESCALATE" : "AUTO-APPROVE SAFE"}
          </span>
        </div>
        {packet.evidence.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">Evidence</p>
            <ul className="space-y-1">
              {packet.evidence.map((e, i) => (
                <li key={i} className="text-sm text-gray-600 flex gap-2">
                  <span className="text-gray-300">•</span><span>{e}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {packet.next_steps.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">Next Steps</p>
            <ol className="space-y-1 list-decimal list-inside">
              {packet.next_steps.map((s, i) => (
                <li key={i} className="text-sm text-gray-600">{s}</li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  threshold,
  alert,
}: {
  label: string;
  value: string;
  threshold: string;
  alert: boolean;
}) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      <p className={`text-lg font-semibold ${alert ? "text-red-600" : "text-gray-900"}`}>
        {value}
      </p>
      <p className="text-xs text-gray-400">{threshold}</p>
    </div>
  );
}
