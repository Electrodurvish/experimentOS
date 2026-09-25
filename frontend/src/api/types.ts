// Types mirroring the Django REST backend (apps/*/serializers.py and views.py).
// Fields the backend may omit or that are still being built are optional.

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export type Role = 'ADMIN' | 'EXPERIMENT_MANAGER' | 'ANALYST' | 'VIEWER';

export interface Membership {
  organization_id: string;
  organization_name: string;
  role: Role;
}

export interface User {
  id: string;
  email: string;
  username?: string;
  first_name?: string;
  last_name?: string;
  created_at?: string;
  memberships?: Membership[];
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  organization: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export const EXPERIMENT_STATUSES = [
  'DRAFT',
  'REVIEW',
  'APPROVED',
  'RUNNING',
  'PAUSED',
  'COMPLETED',
  'ARCHIVED',
] as const;
export type ExperimentStatus = (typeof EXPERIMENT_STATUSES)[number];

export const EXPERIMENT_TYPES = ['AB', 'MULTIVARIATE', 'FEATURE_ROLLOUT', 'HOLDOUT'] as const;
export type ExperimentType = (typeof EXPERIMENT_TYPES)[number];

export const EXPERIMENT_TYPE_LABELS: Record<ExperimentType, string> = {
  AB: 'A/B Test',
  MULTIVARIATE: 'Multivariate',
  FEATURE_ROLLOUT: 'Feature Rollout',
  HOLDOUT: 'Holdout',
};

export interface Variant {
  id?: string;
  key: string;
  name: string;
  description?: string;
  is_control: boolean;
  /** Basis points of total traffic (0–10000). */
  traffic_percentage: number;
  bucket_start: number;
  bucket_end: number;
  payload?: Record<string, unknown>;
}

export interface TargetingRule {
  id?: string;
  rules_json: unknown;
}

export interface ExperimentVersion {
  id: string;
  version_number: number;
  traffic_allocation: number;
  is_active: boolean;
  is_locked: boolean;
  variants: Variant[];
  targeting: TargetingRule | null;
  created_at: string;
}

export interface Experiment {
  id: string;
  key: string;
  name: string;
  description: string;
  hypothesis: string;
  experiment_type: ExperimentType;
  status: ExperimentStatus;
  owner: string | null;
  /** Not currently returned by ExperimentListSerializer; used if it appears. */
  project?: string;
  current_version: ExperimentVersion | null;
  /** Basis points (0–10000). */
  rollout_percentage: number;
  started_at: string | null;
  ended_at: string | null;
  allowed_transitions: ExperimentStatus[];
  created_at: string;
  updated_at: string;
}

export interface ExperimentCreateInput {
  project_id: string;
  key: string;
  name: string;
  description?: string;
  hypothesis?: string;
  experiment_type: ExperimentType;
}

export interface VersionCreateInput {
  traffic_allocation: number;
  variants: Variant[];
  targeting?: { rules_json: unknown };
}

export interface ExperimentListParams {
  project?: string;
  status?: string;
  experiment_type?: string;
  search?: string;
  page?: number;
  ordering?: string;
}

// ---- Results ---------------------------------------------------------------

export interface VariantResult {
  exposures: number;
  unique_users: number;
  conversions: number;
  conversion_rate: number;
  ci_lower: number;
  ci_upper: number;
  lift?: number;
  lift_ci_lower?: number;
  lift_ci_upper?: number;
  absolute_difference?: number;
  z_score?: number;
  p_value?: number;
  is_significant?: boolean;
}

export interface SRMResult {
  chi_squared: number;
  p_value: number;
  is_mismatch: boolean;
  expected_proportions: Record<string, number>;
  observed_counts: Record<string, number>;
}

export interface ExperimentResults {
  experiment_id: string;
  experiment_key: string;
  variants: Record<string, VariantResult>;
  srm: SRMResult | null;
  recommended_sample_size_per_variant: number;
}

export interface SRMCheck extends Partial<SRMResult> {
  experiment_id: string;
  message: string;
}

// ---- Health ----------------------------------------------------------------

export interface HealthDimension {
  score: number;
  detail: string;
}

export interface HealthResponse {
  experiment_id: string;
  experiment_key: string;
  health: {
    overall_score: number;
    dimensions: Record<string, HealthDimension>;
  };
}

// ---- Segments --------------------------------------------------------------

export interface SegmentInput {
  dimension: string;
  value: string;
  control: { users: number; conversions: number };
  treatment: { users: number; conversions: number };
}

export interface SegmentResult {
  dimension: string;
  value: string;
  control_users: number;
  control_conversions: number;
  control_rate: number;
  treatment_users: number;
  treatment_conversions: number;
  treatment_rate: number;
  lift: number;
  absolute_difference: number;
  z_score: number;
  p_value: number;
  is_significant: boolean;
  contribution_weight: number;
  contribution_pct: number;
  has_paradox: boolean;
}

export interface SegmentAnalysis {
  segments: SegmentResult[];
  paradox_detected: boolean;
  paradox_segments: { dimension: string; value: string; segment_lift: number; aggregate_lift: number }[];
  top_contributors: { dimension: string; value: string; lift: number; contribution_pct: number }[];
}

export interface SegmentsResponse {
  experiment_id: string;
  experiment_key: string;
  analysis: SegmentAnalysis;
}

// ---- Timeline --------------------------------------------------------------

export interface TimelineEvent {
  id?: string;
  event_type: string;
  title: string;
  detail: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TimelineResponse {
  experiment_id: string;
  experiment_key: string;
  timeline: TimelineEvent[];
}

// ---- Production impact -----------------------------------------------------

export interface MetricImpact {
  control_avg: number;
  variant_avg: number;
  change_pct: number;
  status: 'healthy' | 'warning' | 'critical';
}

export interface ProductionAnomaly {
  variant_key: string;
  metric_name: string;
  control_avg?: number;
  variant_avg?: number;
  deviation_pct?: number;
  severity?: string;
  [key: string]: unknown;
}

export interface ProductionImpactResponse {
  experiment_id: string;
  experiment_key: string;
  telemetry_summary?: Record<string, Record<string, Record<string, number>>>;
  impact: Record<string, Record<string, MetricImpact>>;
  anomalies: ProductionAnomaly[];
  message?: string;
}

// ---- Decisions & rollout ---------------------------------------------------

export const RECOMMENDATIONS = [
  'CONTINUE',
  'PAUSE',
  'ROLLBACK',
  'INCREASE_ROLLOUT',
  'DECREASE_ROLLOUT',
  'COMPLETE',
] as const;
export type Recommendation = (typeof RECOMMENDATIONS)[number];

export interface Evidence {
  id: string;
  kind: string;
  statement: string;
  data?: Record<string, unknown>;
}

export interface DecisionCheck {
  name: string;
  label: string;
  passed: boolean;
  detail: string;
}

export interface DecisionPreview {
  experiment_id: string;
  experiment_key: string;
  rollout_percentage: number;
  recommendation: Recommendation;
  confidence: number;
  confidence_label: 'HIGH' | 'MEDIUM' | 'LOW';
  summary: string;
  evidence: Evidence[];
  checks: DecisionCheck[];
  target_percentage: number | null;
}

export interface Decision {
  id: string;
  recommendation: Recommendation;
  confidence: number;
  confidence_label: string;
  summary: string;
  evidence: Evidence[];
  checks: DecisionCheck[];
  inputs?: Record<string, unknown>;
  applied_action: string;
  from_percentage: number | null;
  to_percentage: number | null;
  triggered_by: string;
  actor: string | null;
  created_at: string;
  applied?: boolean;
}

export interface AnomaliesResponse {
  experiment_id: string;
  experiment_key: string;
  anomalies: ProductionAnomaly[];
}

export interface RolloutPolicy {
  stages: number[];
  auto_advance: boolean;
  auto_rollback: boolean;
  rollback_percentage: number;
  min_health_score: number;
  min_stage_duration_minutes: number;
  min_confidence: number;
  updated_at?: string | null;
}

export interface RolloutChange {
  id: string;
  action: 'increase' | 'decrease' | 'rollback' | 'manual';
  from_percentage: number;
  to_percentage: number;
  reason: string;
  automated: boolean;
  decision: string | null;
  actor: string | null;
  created_at: string;
}

export interface RolloutState {
  experiment_id: string;
  experiment_key: string;
  rollout_percentage: number;
  policy: { stages: number[]; rollback_percentage: number; min_health_score: number };
  history: RolloutChange[];
}

/** Response from POST rollout / rollback. Note: `from`/`to` are whole percents, not basis points. */
export interface RolloutEvent {
  experiment?: string;
  action?: string;
  from?: number;
  to?: number;
  reason?: string;
  automated?: boolean;
  timestamp?: string;
  detail?: string;
  rollout_percentage?: number;
}

export const GUARDRAIL_OPERATORS = [
  'RELATIVE_INCREASE_GT',
  'RELATIVE_DECREASE_GT',
  'ABSOLUTE_GT',
  'ABSOLUTE_LT',
] as const;
export type GuardrailOperator = (typeof GUARDRAIL_OPERATORS)[number];

export const GUARDRAIL_OPERATOR_LABELS: Record<GuardrailOperator, string> = {
  RELATIVE_INCREASE_GT: 'Relative increase vs control above (%)',
  RELATIVE_DECREASE_GT: 'Relative decrease vs control above (%)',
  ABSOLUTE_GT: 'Variant value above',
  ABSOLUTE_LT: 'Variant value below',
};

export type GuardrailSource = 'TELEMETRY' | 'CONVERSION';
export type GuardrailAction = 'PAUSE' | 'ROLLBACK';

export interface Guardrail {
  id: string;
  name: string;
  metric_name: string;
  source: GuardrailSource;
  operator: GuardrailOperator;
  threshold: number;
  action: GuardrailAction;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export type GuardrailInput = Omit<Guardrail, 'id' | 'created_at' | 'updated_at'>;

// ---- Engine debugger -------------------------------------------------------

export interface DebugStep {
  step: string;
  passed: boolean | null;
  detail: string;
}

export interface EvaluationResult {
  assigned: boolean;
  variant_key: string | null;
  variant_payload: Record<string, unknown> | null;
  bucket: number | null;
  version_number: number | null;
  reason: string;
  source: string;
}

export interface DebugResponse {
  experiment: { id: string; key: string; status: ExperimentStatus };
  version: { id: string | null; version_number: number | null; traffic_allocation: number | null } | null;
  cache_status: string;
  evaluation_steps: DebugStep[];
  result: EvaluationResult;
}

// ---- Audit -----------------------------------------------------------------

export interface AuditLog {
  id: string;
  experiment: string | null;
  actor: string | null;
  actor_email: string | null;
  action: string;
  old_value: unknown;
  new_value: unknown;
  metadata: unknown;
  ip_address: string | null;
  created_at: string;
}

// ---- Interactions ----------------------------------------------------------

export interface InteractionGroup {
  users: number;
  conversions: number;
}

export interface InteractionPairInput {
  experiment_a: string;
  experiment_b: string;
  a_only: InteractionGroup;
  b_only: InteractionGroup;
  both: InteractionGroup;
  neither: InteractionGroup;
}

export interface InteractionResult {
  experiment_a: string;
  experiment_b: string;
  expected_combined_rate: number;
  actual_combined_rate: number;
  interaction_effect: number;
  interaction_type: 'none' | 'synergistic' | 'antagonistic';
  is_interaction: boolean;
  combined_p_value?: number;
  [key: string]: unknown;
}

export interface InteractionsResponse {
  interactions: InteractionResult[];
  graph: {
    nodes: { experiment: string; interaction_count: number }[];
    edges: { from: string; to: string; type: string; effect: number }[];
  };
}

// ---- AI (new endpoints) ----------------------------------------------------

export interface ExplainResponse {
  experiment_id?: string;
  experiment_key: string;
  summary: string;
  recommendation?: string;
  cited_evidence?: string[];
  explanation: string;
  evidence: Evidence[];
  generated_by: 'llm' | 'template';
  model?: string | null;
}

export interface AskResponse {
  answer: string;
  cited_evidence: string[];
  evidence: Evidence[];
  generated_by: 'llm' | 'template';
  model?: string | null;
}

export interface AIQueryResponse {
  answer: string;
  experiments: { id: string; key: string; status: ExperimentStatus | string }[];
  generated_by: 'llm' | 'template';
  model?: string | null;
}

export interface ProbeStatus {
  status: string;
  database?: string;
}
