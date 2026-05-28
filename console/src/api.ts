import axios from "axios";
import type { AuditPacket, AdjudicateResponse, AuditRecord, ApproveRequest, DriftResponse } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface ApplicationSummary {
  id: string;
  income: number | null;
  loan_amount: number | null;
  loan_purpose: string | null;
}

export async function fetchApplications(): Promise<ApplicationSummary[]> {
  const { data } = await axios.get<ApplicationSummary[]>(`${BASE}/applications`);
  return data;
}

async function _adjudicate(application_id: string): Promise<AdjudicateResponse> {
  const { data } = await axios.post<AdjudicateResponse>(`${BASE}/adjudicate`, {
    application_id,
  });
  return data;
}

async function _fetchAuditRecord(audit_id: string): Promise<AuditRecord> {
  const { data } = await axios.get<AuditRecord>(`${BASE}/audit/${audit_id}`);
  return data;
}

// Single call used by App.tsx: adjudicate → fetch full audit record → merge into AuditPacket
export async function adjudicate(application_id: string): Promise<AuditPacket> {
  const adjResult = await _adjudicate(application_id);
  const record = await _fetchAuditRecord(adjResult.audit_id);
  // Legitimate features are byte-identical across all variants — read from variants[0]
  const legitimateFeatures = (record.variants[0] ?? {}) as Record<string, unknown>;
  // Zip variant feature dicts with their parallel decisions into Variant shape
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const variants = (record.variants as any[]).map((v: any, i: number) => ({
    swept_attribute: v.swept_attribute ?? "",
    swept_value:     v.swept_value ?? "",
    decision:        (record.variant_decisions[i] ?? {}).decision ?? "refer",
    rate:            (record.variant_decisions[i] ?? {}).recommended_rate ?? null,
    amount:          (record.variant_decisions[i] ?? {}).recommended_amount ?? null,
  })) as import("./types").Variant[];
  return {
    audit_id: adjResult.audit_id,
    application_id: adjResult.application_id,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    application: (legitimateFeatures as any) ?? null,
    baseline: record.baseline_decision,
    variants,
    metrics: adjResult.metrics,
    packet: adjResult.packet,
    trace_id: adjResult.trace_id,
  };
}

export async function submitAction(req: ApproveRequest): Promise<void> {
  await axios.post(`${BASE}/approve`, req);
}

export async function fetchApplication(id: string): Promise<ApplicationSummary | null> {
  try {
    const { data } = await axios.get<ApplicationSummary>(`${BASE}/applications/${id}`);
    return data;
  } catch {
    return null;
  }
}

export async function fetchDrift(): Promise<DriftResponse> {
  const { data } = await axios.get<DriftResponse>(`${BASE}/drift`);
  if (data?.overall_avg === undefined) throw new Error("unexpected drift shape");
  return data;
}
