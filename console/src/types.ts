export interface Application {
  income: number | null;
  loan_amount: number | null;
  debt_to_income_ratio: number | null;
  combined_loan_to_value_ratio: number | null;
  property_value: number | null;
  loan_type: number | string | null;
  loan_purpose: number | string | null;
  lien_status?: number | string | null;
}

export interface ReasonerOutput {
  decision: "approve" | "deny" | "refer";
  recommended_rate: number;
  recommended_amount: number;
  rationale: string;
  key_factors: string[];
}

export interface Variant {
  swept_attribute: string;
  swept_value: string;
  decision: "approve" | "deny" | "refer";
  rate: number | null;
  amount: number | null;
  [key: string]: unknown;
}


export interface DisparityMetrics {
  flip_rate: number;
  approval_rate_gap: number;
  terms_gap: number;
  judge_score: number;
  recommended_action: string;
  flipped_variants: Array<{ variant: Record<string, unknown>; decision: Record<string, unknown> }>;
}

export interface RouterOutput {
  headline: string;
  recommended_action: "auto_approve_safe" | "escalate";
  summary: string;
  evidence: string[];
  next_steps: string[];
}

// Shape returned by POST /adjudicate (orchestrator result)
export interface AdjudicateResponse {
  audit_id: string;
  application_id: string;
  packet: RouterOutput;
  metrics: DisparityMetrics;
  trace_id: string;
}

// Shape returned by GET /audit/{id} (full compliance log record)
export interface AuditRecord {
  id: string;
  application_id: string;
  baseline_decision: ReasonerOutput;
  variants: Variant[];
  variant_decisions: ReasonerOutput[];
  metrics: DisparityMetrics;
  packet: RouterOutput;
  trace_id: string;
  human_action: string | null;
  officer_note: string | null;
  created_at: string;
  finalized_at: string | null;
}

// Combined view used by the console — merged from both responses
export interface AuditPacket {
  audit_id: string;
  application_id: string;
  application: Application | null;   // fetched separately from /applications
  baseline: ReasonerOutput;
  variants: Variant[];
  metrics: DisparityMetrics;
  packet: RouterOutput;
  trace_id: string;
}

export interface DriftPoint {
  timestamp: string;
  group: string;
  consistency_score: number;
}

export interface DriftResponse {
  overall_avg: number;
  by_group: Record<string, number>;
  window_size: number;
  records_with_flips: number;
  status: "healthy" | "degraded";
  proposed_action: string | null;
}

export type OfficerAction = "approve" | "override_approve" | "send_back";

export interface ApproveRequest {
  audit_id: string;
  action: OfficerAction;
  officer_note: string;
}
