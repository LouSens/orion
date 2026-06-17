"""Pydantic contracts for agent inputs/outputs.

These are the *structured, actionable outputs* each agent emits. Every
transition in the graph is gated on one of these validating — which is
how we turn the LLM's reasoning into workflow control flow.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------- Intake ---------------------------------------------------------


class IntakeClaim(BaseModel):
    vendor: Optional[str] = Field(None, description="Canonical vendor name, e.g. 'Notion Labs Inc.'")
    product: Optional[str] = Field(None, description="Product / subscription name, e.g. 'Notion Team Plan'")
    category: Optional[Literal[
        "productivity", "design", "engineering", "ai_tools",
        "communication", "analytics", "security", "other"
    ]] = None
    amount_myr: Optional[float] = Field(None, ge=0)
    currency_original: Optional[str] = Field(None, description="ISO-4217 code on the receipt")
    amount_original: Optional[float] = Field(None, ge=0)
    billing_period: Optional[Literal["monthly", "annual", "one_time", "unknown"]] = None
    purchase_date: Optional[date] = None
    business_justification: Optional[str] = None
    confidence: float = Field(0.5, ge=0, le=1, description="Self-reported extraction confidence")
    missing_fields: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    regex_extracted_amount: Optional[float] = Field(
        None, description="Largest currency token found by regex pre-pass — anti-hallucination anchor"
    )


# ---------- Intelligence Agent --------------------------------------------


class SemanticMatch(BaseModel):
    existing_subscription_id: str
    existing_product: str
    owner_team: str
    similarity_score: float = Field(..., ge=0, le=1)
    reasoning: str


class AlternativeSuggestion(BaseModel):
    product: str
    reason: str
    estimated_savings_myr: Optional[float] = None
    source: Literal["org_existing_license", "approved_catalog", "cheaper_tier"]


class IntelligenceReport(BaseModel):
    is_likely_duplicate: bool
    duplicate_matches: list[SemanticMatch] = Field(default_factory=list)
    alternatives: list[AlternativeSuggestion] = Field(default_factory=list)
    cross_reference_notes: str = ""
    recommendation: Literal["proceed", "suggest_alternative", "block_duplicate"]
    rationale: str


# ---------- Policy Engine --------------------------------------------------


class PolicyViolation(BaseModel):
    rule_id: str
    description: str
    severity: Literal["warn", "block"]


class HardPolicyResult(BaseModel):
    hard_violations: list[PolicyViolation]
    routing_hints: list[str]
    ambiguous_flags: list[str]
    fast_reject: bool


class PolicyReport(BaseModel):
    compliant: bool
    applied_rules: list[str]
    violations: list[PolicyViolation] = Field(default_factory=list)  # kept for recorder compat
    hard_violations: list[PolicyViolation] = Field(default_factory=list)
    routing_hints: list[str] = Field(default_factory=list)
    ambiguous_flags: list[str] = Field(default_factory=list)
    fast_reject: bool = False
    summary: str


# ---------- Supervisor Agent ----------------------------------------------


class SupervisorRoute(str, Enum):
    """The five routing destinations the Supervisor can choose."""
    route_to_approval           = "route_to_approval"
    route_back_to_intelligence  = "route_back_to_intelligence"
    route_back_to_policy        = "route_back_to_policy"
    request_human_escalation    = "request_human_escalation"
    request_user_clarification  = "request_user_clarification"


class SupervisorDecision(BaseModel):
    route: SupervisorRoute
    reasoning: str = Field(..., description="Natural-language justification for the routing choice.")
    focus_areas: List[str] = Field(
        default_factory=list,
        description="Specific aspects the next agent should investigate or re-examine.",
    )
    clarification_questions: List[str] = Field(
        default_factory=list,
        description="Populated only when route=request_user_clarification. Max 3 questions.",
    )


# ---------- Approval / Critic Agent ----------------------------------------


class ApprovalDecision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    AUTO_REJECT = "auto_reject"
    ESCALATE_MANAGER = "escalate_manager"
    ESCALATE_FINANCE = "escalate_finance"
    REQUEST_INFO = "request_info"


class ApprovalOutcome(BaseModel):
    decision: ApprovalDecision
    approver_role: Optional[str] = None
    reason: str
    confidence: float = Field(..., ge=0, le=1)
    next_action: str


# ---------- Recorder ------------------------------------------------------


class LedgerRecord(BaseModel):
    claim_id: str
    employee_id: str
    vendor: str
    product: str
    amount_myr: float
    decision: ApprovalDecision
    recorded_at: str
    notification_sent_to: list[str] = Field(default_factory=list)
    submission_hash: Optional[str] = Field(
        None, description="SHA256 of submission content (excl. timestamp) — used for idempotency dedup"
    )


# ---------- Submission (inbound) ------------------------------------------


class ReimbursementSubmission(BaseModel):
    employee_id: str
    employee_name: str
    employee_team: str
    free_text: str = Field(..., description="Free-form message describing the claim")
    receipt_text: Optional[str] = Field(None, description="OCR'd receipt text or pasted invoice body")
    attachments: list[str] = Field(default_factory=list, description="Filenames only — stored out of band")
