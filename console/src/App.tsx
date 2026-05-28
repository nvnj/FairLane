import { useEffect, useRef, useState } from "react";
console.log("default ID from env:", import.meta.env.VITE_DEFAULT_APP_ID);
import { adjudicate, fetchApplications, fetchApplication } from "./api";
import type { ApplicationSummary } from "./api";
import { MOCK_AUDIT } from "./mockData";
import type { AuditPacket } from "./types";
import { ApplicationCard } from "./components/ApplicationCard";
import { FairnessPanel } from "./components/FairnessPanel";
import { ActionBar } from "./components/ActionBar";
import { ObservabilityTab } from "./components/ObservabilityTab";

type Tab = "review" | "observability";

export default function App() {
  const [tab, setTab] = useState<Tab>("review");
  const [applications, setApplications] = useState<ApplicationSummary[]>([]);
  const applicationsRef = useRef<ApplicationSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedApp, setSelectedApp] = useState<ApplicationSummary | null>(null);
  const [audit, setAudit] = useState<AuditPacket | null>(null);
  const [adjudicating, setAdjudicating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionDone, setActionDone] = useState(false);

  // On mount: fetch application list, select default, render left card immediately
  useEffect(() => {
    const defaultId = import.meta.env.VITE_DEFAULT_APP_ID as string | undefined;

    fetchApplications()
      .then(async (apps) => {
        if (defaultId) {
          const alreadyInList = apps.find((a) => String(a.id) === String(defaultId));
          if (!alreadyInList) {
            const pinned = await fetchApplication(defaultId);
            if (pinned) apps.unshift(pinned);
          }
          applicationsRef.current = apps;
          setApplications(apps);
          const selected = apps.find((a) => String(a.id) === String(defaultId)) ?? apps[0];
          if (selected) {
            setSelectedId(selected.id);
            setSelectedApp(selected);
          }
        } else {
          applicationsRef.current = apps;
          setApplications(apps);
          if (apps[0]) {
            setSelectedId(apps[0].id);
            setSelectedApp(apps[0]);
          }
        }
      })
      .catch(() => {
        setError("Could not load applications — showing mock data");
        setSelectedId("mock");
      });
  }, []);

  // Re-adjudicate whenever the selected ID changes — only blocks the right panel
  useEffect(() => {
    if (selectedId === null) return;
    setAdjudicating(true);
    setAudit(null);
    setActionDone(false);
    setError(null);

    if (selectedId === "mock") {
      setSelectedApp(null);
      setAudit(MOCK_AUDIT);
      setAdjudicating(false);
      return;
    }

    adjudicate(selectedId)
      .then((result) => {
        setAudit(result);
      })
      .catch(() => {
        setAudit(MOCK_AUDIT);
        setError("API unavailable — showing mock audit data");
      })
      .finally(() => setAdjudicating(false));
  }, [selectedId]);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 bg-gray-900 rounded flex items-center justify-center">
              <span className="text-white text-xs font-bold">FL</span>
            </div>
            <div>
              <span className="font-semibold text-gray-900 text-sm">FairLane</span>
              <span className="ml-2 text-xs text-gray-400">Loan Officer Console</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {applications.length > 0 && (
              <select
                value={selectedId ?? ""}
                onChange={(e) => {
                  const id = e.target.value;
                  setSelectedId(id);
                  setSelectedApp(applicationsRef.current.find((a) => a.id === id) ?? null);
                }}
                disabled={adjudicating}
                className="text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-gray-400 disabled:opacity-50"
              >
                {applications.map((app) => (
                  <option key={app.id} value={app.id}>
                    {app.id}
                    {app.loan_purpose ? ` · ${app.loan_purpose}` : ""}
                    {app.loan_amount ? ` · $${app.loan_amount.toLocaleString()}` : ""}
                  </option>
                ))}
              </select>
            )}
            {audit && (
              <div className="text-xs text-gray-400 font-mono">
                audit: {audit.audit_id}
              </div>
            )}
          </div>
        </div>
        <div className="max-w-7xl mx-auto px-6">
          <nav className="flex gap-1 -mb-px">
            <TabButton active={tab === "review"} onClick={() => setTab("review")}>
              Review
            </TabButton>
            <TabButton active={tab === "observability"} onClick={() => setTab("observability")}>
              Observability
            </TabButton>
          </nav>
        </div>
      </header>

      {error && (
        <div className="max-w-7xl mx-auto w-full px-6 pt-4">
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-700">
            {error}
          </div>
        </div>
      )}

      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6 pb-28">
        {tab === "review" && (
          <div className="grid grid-cols-5 gap-6">
            {/* Left column — renders immediately from /applications */}
            <div className="col-span-2">
              {selectedApp ? (
                <ApplicationCard
                  application={{
                    // Available immediately from /applications
                    income:       selectedApp.income,
                    loan_amount:  selectedApp.loan_amount,
                    loan_purpose: audit?.application?.loan_purpose ?? selectedApp.loan_purpose,
                    loan_type:    audit?.application?.loan_type ?? null,
                    // Available only after /adjudicate — show "—" until then
                    debt_to_income_ratio:         audit?.application?.debt_to_income_ratio ?? null,
                    combined_loan_to_value_ratio: audit?.application?.combined_loan_to_value_ratio ?? null,
                    property_value:               audit?.application?.property_value ?? null,
                    lien_status:                  audit?.application?.lien_status ?? null,
                  }}
                  baseline={audit?.baseline}
                />
              ) : (
                <div className="flex flex-col items-center justify-center py-16 gap-2">
                  <p className="text-sm text-gray-400">No application selected</p>
                </div>
              )}
            </div>

            {/* Right column — loading spinner while /adjudicate runs */}
            <div className="col-span-3">
              {adjudicating ? (
                <div className="flex flex-col items-center justify-center py-32 gap-4">
                  <div className="w-8 h-8 border-2 border-gray-200 border-t-gray-600 rounded-full animate-spin" />
                  <div className="text-center">
                    <p className="text-sm font-medium text-gray-700">
                      Auditing application {selectedId}…
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      Running counterfactual analysis — this takes ~60 seconds
                    </p>
                  </div>
                </div>
              ) : audit ? (
                <FairnessPanel audit={audit} />
              ) : (
                <div className="flex flex-col items-center justify-center py-32 gap-2">
                  <p className="text-sm font-medium text-gray-500">No audit data</p>
                  <p className="text-xs text-gray-400">Check the API is running on :8000</p>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === "observability" && <ObservabilityTab />}
      </main>

      {tab === "review" && audit && !adjudicating && (
        <ActionBar
          auditId={audit.audit_id}
          disabled={actionDone}
          onComplete={() => setActionDone(true)}
        />
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
        active
          ? "border-gray-900 text-gray-900"
          : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
      }`}
    >
      {children}
    </button>
  );
}
