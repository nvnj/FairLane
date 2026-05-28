import type { Application, ReasonerOutput } from "../types";
import { DecisionBadge } from "./DecisionBadge";

const LOAN_TYPE: Record<number, string> = {
  1: "Conventional",
  2: "FHA-insured",
  3: "VA-guaranteed",
  4: "RHS or FSA",
};

const LOAN_PURPOSE: Record<number, string> = {
  1: "Home purchase",
  2: "Home improvement",
  3: "Refinancing",
  4: "Cash-out refinancing",
  5: "Other",
  31: "Home purchase (reverse)",
  32: "Refinancing (reverse)",
};

const LIEN_STATUS: Record<number, string> = {
  1: "First lien",
  2: "Second lien",
};

function decodeCode(
  map: Record<number, string>,
  value: number | string | null | undefined,
): string {
  if (value == null || value === "") return "Not specified";
  const key = typeof value === "string" ? parseInt(value, 10) : value;
  return map[key] ?? "Unknown";
}

const fmtPct = (v: unknown): string => {
  if (v == null) return "N/A";
  const n = parseFloat(String(v));
  if (isNaN(n)) return String(v);
  return n.toFixed(1) + "%";
};

const fmtCurrency = (v: unknown): string => {
  if (v == null) return "N/A";
  const n = parseFloat(String(v));
  if (isNaN(n)) return String(v);
  return "$" + Math.round(n).toLocaleString("en-US");
};

function toTitleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatKeyFactor(raw: string): string {
  const colon = raw.indexOf(":");
  if (colon === -1) return raw;

  const key = raw.slice(0, colon).trim();
  const val = raw.slice(colon + 1).trim();
  const label = toTitleCase(key);

  if (key === "income") {
    const n = parseFloat(val);
    return isNaN(n) ? `${label}: ${val}` : `${label}: $${Math.round(n * 1000).toLocaleString("en-US")}`;
  }

  // Range strings like "30%-<36%" — pass through as-is
  const n = parseFloat(val);
  if (isNaN(n)) return `${label}: ${val}`;

  // Plain numeric — 1 decimal place
  return `${label}: ${n.toFixed(1)}`;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-2 border-b border-gray-100 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className="text-sm font-medium text-gray-900">{value}</span>
    </div>
  );
}

export function ApplicationCard({
  application,
  baseline,
}: {
  application: Application | undefined;
  baseline: ReasonerOutput | undefined;
}) {
  if (!application) return null;

  return (
    <div className="space-y-4">
      <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
          Application
        </h2>
        <Row label="Annual Income" value={fmtCurrency(application.income != null ? parseFloat(String(application.income)) * 1000 : null)} />
        <Row label="Loan Amount" value={fmtCurrency(application.loan_amount)} />
        <Row label="Debt-to-Income Ratio" value={fmtPct(application.debt_to_income_ratio)} />
        <Row label="Combined LTV" value={fmtPct(application.combined_loan_to_value_ratio)} />
        <Row label="Property Value" value={fmtCurrency(application.property_value)} />
        <Row label="Loan Type" value={decodeCode(LOAN_TYPE, application.loan_type)} />
        <Row label="Loan Purpose" value={decodeCode(LOAN_PURPOSE, application.loan_purpose)} />
        <Row label="Lien Status" value={decodeCode(LIEN_STATUS, application.lien_status)} />
      </div>

      {baseline ? (
        <>
          <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
              Recommendation
            </h2>
            <div className="flex items-center gap-3 mb-4">
              <DecisionBadge decision={baseline.decision} />
              {baseline.decision === "approve" &&
                baseline.recommended_amount != null &&
                baseline.recommended_rate != null && (
                <div className="text-sm text-gray-600">
                  <span className="font-medium text-gray-900">
                    {fmtCurrency(baseline.recommended_amount)}
                  </span>{" "}
                  at{" "}
                  <span className="font-medium text-gray-900">
                    {fmtPct(baseline.recommended_rate)}
                  </span>
                </div>
              )}
            </div>
            <div className="mb-3">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">
                Key Factors
              </p>
              <ul className="space-y-1">
                {baseline.key_factors.map((f, i) => (
                  <li key={i} className="text-sm text-gray-600 flex gap-2">
                    <span className="text-gray-300 mt-0.5">•</span>
                    <span>{formatKeyFactor(f)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
              Gemini Rationale
            </h2>
            <p className="text-sm text-gray-700 leading-relaxed">{baseline.rationale}</p>
          </div>
        </>
      ) : (
        <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-gray-200 border-t-gray-500 rounded-full animate-spin shrink-0" />
          <p className="text-sm text-gray-400">Awaiting underwriting decision…</p>
        </div>
      )}
    </div>
  );
}
