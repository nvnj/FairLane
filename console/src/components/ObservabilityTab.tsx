import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { fetchDrift } from "../api";
import { MOCK_DRIFT } from "../mockData";
import type { DriftResponse } from "../types";
import { Skeleton } from "./Skeleton";

// Derive a mock DriftResponse from the existing MOCK_DRIFT points so the
// fallback path renders with the same component logic as the real path.
function mockDriftResponse(): DriftResponse {
  const by_group: Record<string, number> = {};
  const counts: Record<string, number> = {};
  for (const p of MOCK_DRIFT) {
    by_group[p.group] = (by_group[p.group] ?? 0) + p.consistency_score;
    counts[p.group] = (counts[p.group] ?? 0) + 1;
  }
  for (const k of Object.keys(by_group)) {
    by_group[k] = by_group[k] / counts[k];
  }
  const vals = Object.values(by_group);
  const overall_avg = vals.reduce((a, b) => a + b, 0) / vals.length;
  return {
    overall_avg,
    by_group,
    window_size: MOCK_DRIFT.length / 3,
    records_with_flips: 4,
    status: overall_avg >= 0.85 ? "healthy" : "degraded",
    proposed_action:
      overall_avg < 0.85
        ? "Tighten the 'ignore protected attributes' instruction in underwriting_reasoner.md and add a few-shot counterexample."
        : null,
  };
}

// Attribute prefix → display label and bar color
const ATTR_META: Record<string, { label: string; color: string }> = {
  derived_race:      { label: "Race",      color: "#3b82f6" },
  derived_sex:       { label: "Sex",       color: "#8b5cf6" },
  derived_ethnicity: { label: "Ethnicity", color: "#f59e0b" },
};

function attrPrefix(key: string): string {
  return key.includes(":") ? key.split(":")[0] : key;
}

function shortLabel(key: string): string {
  if (key.includes(":")) {
    const [attr, val] = key.split(":");
    const prefix = ATTR_META[attr]?.label ?? attr;
    return `${prefix}: ${val}`;
  }
  return ATTR_META[key]?.label ?? key;
}

type BarRow = { key: string; label: string; score: number; color: string };

function buildBarRows(by_group: Record<string, number>): BarRow[] {
  return Object.entries(by_group)
    .map(([key, score]) => ({
      key,
      label: shortLabel(key),
      score,
      color: ATTR_META[attrPrefix(key)]?.color ?? "#6b7280",
    }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

export function ObservabilityTab() {
  const [drift, setDrift] = useState<DriftResponse | null>(null);
  const [isMock, setIsMock] = useState(false);

  useEffect(() => {
    fetchDrift()
      .then((d) => setDrift(d))
      .catch(() => {
        setDrift(mockDriftResponse());
        setIsMock(true);
      });
  }, []);

  const phoenixUrl = import.meta.env.VITE_PHOENIX_URL ?? "http://localhost:6006";
  const rows = drift ? buildBarRows(drift.by_group) : [];

  return (
    <div className="space-y-4">
      {isMock && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-700">
          API unavailable — showing mock drift data
        </div>
      )}

      {/* Degraded / proposed-action card */}
      {drift?.status === "degraded" && drift.proposed_action && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg px-5 py-4 flex items-start gap-3">
          <span className="text-lg mt-0.5">⚠</span>
          <div>
            <p className="text-sm font-semibold text-amber-800">
              Bias drift detected — consistency below threshold
            </p>
            <p className="text-sm text-amber-700 mt-1">
              <span className="font-medium">Proposed fix: </span>
              {drift.proposed_action}
            </p>
          </div>
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-0.5">
              Consistency Score by Group
            </h2>
            <p className="text-sm text-gray-500">
              LLM-judge consistency per protected group (last {drift?.window_size ?? "—"} applications).
              Dashed line = escalation threshold (0.85).
            </p>
          </div>
          <a
            href={phoenixUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-gray-700 border border-gray-200 rounded hover:bg-gray-50 transition-colors"
          >
            Open in Phoenix ↗
          </a>
        </div>

        {drift === null ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <>
            {/* Summary stats row */}
            <div className="flex gap-6 mb-5 text-sm">
              <div>
                <span className="text-xs text-gray-400 block mb-0.5">Overall avg</span>
                <span className={`font-semibold ${drift.overall_avg >= 0.85 ? "text-green-600" : "text-red-600"}`}>
                  {drift.overall_avg.toFixed(3)}
                </span>
              </div>
              <div>
                <span className="text-xs text-gray-400 block mb-0.5">Status</span>
                <span className={`font-semibold ${drift.status === "healthy" ? "text-green-600" : "text-amber-600"}`}>
                  {drift.status}
                </span>
              </div>
              <div>
                <span className="text-xs text-gray-400 block mb-0.5">Flips in window</span>
                <span className={`font-semibold ${drift.records_with_flips > 0 ? "text-red-600" : "text-gray-700"}`}>
                  {drift.records_with_flips}
                </span>
              </div>
            </div>

            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={rows} margin={{ top: 4, right: 16, bottom: 80, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 10, fill: "#9ca3af" }}
                  tickLine={false}
                  axisLine={false}
                  angle={-45}
                  textAnchor="end"
                  interval={0}
                />
                <YAxis
                  domain={[0, 1]}
                  tick={{ fontSize: 11, fill: "#9ca3af" }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => v.toFixed(2)}
                />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid #e5e7eb" }}
                  formatter={(v) => [
                    typeof v === "number" ? v.toFixed(3) : String(v),
                    "Consistency",
                  ]}
                />
                <ReferenceLine
                  y={0.85}
                  stroke="#ef4444"
                  strokeDasharray="4 2"
                  label={{ value: "0.85", position: "insideRight", fontSize: 10, fill: "#ef4444" }}
                />
                <Bar dataKey="score" radius={[3, 3, 0, 0]}>
                  {rows.map((row) => (
                    <Cell key={row.key} fill={row.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </>
        )}
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
          Phoenix Observability
        </h2>
        <p className="text-sm text-gray-600 mb-4">
          All pipeline runs are traced end-to-end: reasoner span → variant spans (children) → analyzer span.
          Open the Phoenix dashboard to inspect individual traces, eval scores, and datasets.
        </p>
        <a
          href={phoenixUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2 bg-gray-900 text-white text-sm font-semibold rounded hover:bg-gray-700 transition-colors"
        >
          Open Arize Phoenix Dashboard ↗
        </a>
      </div>
    </div>
  );
}
