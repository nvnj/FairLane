import { useState } from "react";
import { submitAction } from "../api";
import type { OfficerAction } from "../types";

interface Props {
  auditId: string;
  disabled: boolean;
  onComplete: () => void;
}

export function ActionBar({ auditId, disabled, onComplete }: Props) {
  const [pending, setPending] = useState<OfficerAction | null>(null);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const noteRequired = pending === "override_approve" || pending === "send_back";
  const canSubmit = pending !== null && (!noteRequired || note.trim().length > 0);

  async function handleSubmit() {
    if (!pending || !canSubmit) return;
    setLoading(true);
    setError(null);
    try {
      await submitAction({ audit_id: auditId, action: pending, officer_note: note });
      setDone(true);
      onComplete();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`Submission failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-10">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="text-green-600 font-medium text-sm">
              Decision recorded. Compliance log updated.
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-10">
      <div className="max-w-7xl mx-auto px-6 py-4 space-y-3">
        {error && (
          <p className="text-sm text-red-600">{error}</p>
        )}
        <div className="flex items-end gap-3">
          <div className="flex gap-2">
            <ActionButton
              label="Approve"
              colorClass="bg-green-600 hover:bg-green-700 text-white"
              active={pending === "approve"}
              onClick={() => setPending("approve")}
              disabled={disabled || loading}
            />
            <ActionButton
              label="Override & Approve"
              colorClass="bg-amber-500 hover:bg-amber-600 text-white"
              active={pending === "override_approve"}
              onClick={() => setPending("override_approve")}
              disabled={disabled || loading}
            />
            <ActionButton
              label="Send Back"
              colorClass="bg-red-600 hover:bg-red-700 text-white"
              active={pending === "send_back"}
              onClick={() => setPending("send_back")}
              disabled={disabled || loading}
            />
          </div>

          {noteRequired && (
            <textarea
              className="flex-1 text-sm border border-gray-200 rounded px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-gray-300 placeholder:text-gray-400"
              rows={2}
              placeholder="Officer note required…"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          )}

          {pending && (
            <button
              className="px-5 py-2 bg-gray-900 text-white text-sm font-semibold rounded hover:bg-gray-700 disabled:opacity-40 flex items-center gap-2 shrink-0"
              onClick={handleSubmit}
              disabled={!canSubmit || loading}
            >
              {loading && (
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              Confirm
            </button>
          )}
        </div>

        {noteRequired && !note.trim() && (
          <p className="text-xs text-amber-600">
            Officer note is required for this action.
          </p>
        )}
      </div>
    </div>
  );
}

function ActionButton({
  label,
  colorClass,
  active,
  onClick,
  disabled,
}: {
  label: string;
  colorClass: string;
  active: boolean;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-4 py-2 rounded text-sm font-semibold transition-all disabled:opacity-40 ${colorClass} ${active ? "ring-2 ring-offset-2 ring-gray-400" : ""}`}
    >
      {label}
    </button>
  );
}
