export type EscalationType =
  | "column_mapping"
  | "date_convention"
  | "enum_value"
  | "duplicate_suspected"
  | "rehire_suspected"
  | "validation_failed"
  | "field_unsourced"
  | "hierarchy_orphan"
  | "hierarchy_cycle"
  | "push_rejected"
  | "batch_anomaly";

export interface Option {
  value: string;
  label: string;
  detail?: string;
}

export interface Escalation {
  id: string;
  run_id: string;
  subject: string;
  type: EscalationType;
  title: string;
  question: string;
  evidence: Record<string, any>;
  options: Option[];
  affected_records: string[];
  affected_count: number;
  status: "open" | "resolved" | "rejected";
  resolution: unknown;
  created_at: string;
}

export interface TargetRecord {
  key: string;
  fields: Record<string, any>;
  sources: string[];
  errors: string[];
  blocked_by: string[];
  push_status: string;
  push_detail: string;
  ready: boolean;
}

export interface AuditEntry {
  id: string;
  at: string;
  actor: "agent" | "human" | "system";
  action: string;
  entity: string;
  before: unknown;
  after: unknown;
  rationale: string;
  disposition: string | null;
}

export interface Summary {
  run_id?: string;
  columns?: number;
  columns_auto?: number;
  columns_flagged?: number;
  columns_ignored?: number;
  records?: number;
  records_ready?: number;
  records_blocked?: number;
  records_skipped?: number;
  escalations?: number;
  escalations_by_type?: Record<string, number>;
  audit_entries?: number;
  breaker_tripped?: boolean;
  elapsed_seconds?: number;
  pushed?: number;
  push_failed?: number;
  push_rejected?: number;
}

export type Decision = string | boolean | { action: string; fields?: Record<string, string> };

export interface ModelStatus {
  enabled: boolean;
  embedding: { provider: string; model: string; base_url: string; reachable: boolean };
  reasoning: { provider: string; model: string; base_url: string; reachable: boolean };
}

/** A column's mapping decision, as persisted by the run. */
export interface Mapping {
  source_file: string;
  column: string;
  target_field: string | null;
  disposition: "auto" | "flagged" | "escalated" | "ignored";
  confidence: number;
  margin: number;
  rationale: string;
  transform: string | null;
  provenance: "scored" | "memory" | "human";
  candidates: {
    target_field: string;
    score: number;
    embedding_score: number;
    fuzzy_score: number;
  }[];
}

export interface SchemaField {
  name: string;
  type: string;
  description: string;
  required: boolean;
  unique: boolean;
  identity: string | null;
  format: string | null;
  enum: string[];
  pii: boolean;
  references: string | null;
}

export interface TargetSchema {
  entity: string;
  version: number;
  fields: SchemaField[];
  business_rules: { name?: string; rule?: string; description?: string }[];
}

/** The escalation boundary, served from `app/policy.py` itself. */
export interface Policy {
  principle: string;
  tiers: { id: string; label: string; meaning: string }[];
  groups: {
    id: string;
    title: string;
    summary: string;
    thresholds: { name: string; key: string; value: number; note: string }[];
  }[];
}

export interface PlanChange {
  action: string;
  what: string;
  before: unknown;
  after: unknown;
  why: string;
  disposition: string | null;
}

export interface PlanRecord {
  key: string;
  employee_code: string | null;
  name: string;
  sources: string[];
  merged: boolean;
  payload: Record<string, any>;
  pii_fields: string[];
  multi_source_fields: string[];
  changes: PlanChange[];
  errors: string[];
  blocked_by: string[];
  push_status: string;
  reason_held: string;
}

export interface Plan {
  run_id: string;
  entity: string;
  will_send: PlanRecord[];
  held_back: PlanRecord[];
  totals: {
    will_send: number;
    held_back: number;
    fields_changed: number;
    records_with_changes: number;
    already_loaded: number;
  };
}

export interface RunSummaryRow {
  run_id: string;
  created_at: string;
  status: string;
  files: string[];
  summary: Summary | null;
}

export interface MemoryEntry {
  column_key: string;
  target: string;
  times_used: number;
  updated_at?: string;
}
