/**
 * TypeScript interfaces for the Orion backend API contract.
 */

export interface LedgerRecord {
  claim_id: string;
  employee_id: string;
  vendor: string;
  product: string;
  amount_myr: number;
  decision: string;
  recorded_at: string;
  notification_sent_to: string[];
}

export interface LedgerResponse {
  records: LedgerRecord[];
}

// ---------- Submission (inbound) ------------------------------------------

export interface SubmitClaimRequest {
  employee_id: string;
  employee_name: string;
  employee_team: string;
  free_text: string;
  receipt_text?: string;
  attachments?: string[];
}

// ---------- Intake ---------------------------------------------------------

export interface IntakeClaim {
  vendor: string | null;
  product: string | null;
  category: string | null;
  amount_myr: number | null;
  currency_original: string | null;
  amount_original: number | null;
  billing_period: string | null;
  purchase_date: string | null;
  business_justification: string | null;
  confidence: number;
  missing_fields: string[];
  notes: string | null;
}

// ---------- Intelligence Agent --------------------------------------------

export interface SemanticMatch {
  existing_subscription_id: string;
  existing_product: string;
  owner_team: string;
  similarity_score: number;
  reasoning: string;
}

export interface AlternativeSuggestion {
  product: string;
  reason: string;
  estimated_savings_myr: number | null;
  source: string;
}

export interface IntelligenceReport {
  is_likely_duplicate: boolean;
  duplicate_matches: SemanticMatch[];
  alternatives: AlternativeSuggestion[];
  cross_reference_notes: string;
  recommendation: string;
  rationale: string;
}

// ---------- Policy Agent ---------------------------------------------------

export interface PolicyViolation {
  rule_id: string;
  description: string;
  severity: 'warn' | 'block';
}

export interface PolicyReport {
  compliant: boolean;
  applied_rules: string[];
  violations: PolicyViolation[];
  summary: string;
}

// ---------- Validation Agent ----------------------------------------------

export interface ClarificationRequest {
  field: string;
  question: string;
}

export interface ValidationReport {
  ready_for_decision: boolean;
  clarifications: ClarificationRequest[];
  summary: string;
}

// ---------- Approval Agent ------------------------------------------------

export interface ApprovalOutcome {
  decision: 'auto_approve' | 'auto_reject' | 'escalate_manager' | 'escalate_finance' | 'request_info';
  approver_role: string | null;
  reason: string;
  confidence: number;
  next_action: string;
}

// ---------- Recorder ------------------------------------------------------

export interface RecordedClaim {
  claim_id: string;
  employee_id: string;
  vendor: string;
  product: string;
  amount_myr: number;
  decision: string;
  recorded_at: string;
  notification_sent_to: string[];
}

// ---------- Full Submit Response ------------------------------------------

export interface SubmitClaimResponse {
  claim_id: string;
  trace: string[];
  terminal: boolean;
  intake: IntakeClaim | null;
  intelligence: IntelligenceReport | null;
  policy: PolicyReport | null;
  validation: ValidationReport | null;
  approval: ApprovalOutcome | null;
  record: RecordedClaim | null;
}

// ---------- Parse Document Response ---------------------------------------

export interface ParseDocumentResponse {
  text: string;
  filename?: string;
  size_bytes?: number;
}
