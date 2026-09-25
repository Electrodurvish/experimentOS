// Typed endpoint functions for the ExperimentOS REST API (base /api/v1).

import { ApiError, request, tokenStore } from './client';
import type {
  AIQueryResponse,
  AnomaliesResponse,
  AskResponse,
  AuditLog,
  DebugResponse,
  Decision,
  DecisionPreview,
  Experiment,
  ExperimentCreateInput,
  ExperimentListParams,
  ExperimentResults,
  ExperimentStatus,
  ExperimentVersion,
  ExplainResponse,
  Guardrail,
  GuardrailInput,
  HealthResponse,
  InteractionPairInput,
  InteractionsResponse,
  Organization,
  Paginated,
  ProbeStatus,
  ProductionImpactResponse,
  Project,
  RolloutEvent,
  RolloutPolicy,
  RolloutState,
  SegmentInput,
  SegmentsResponse,
  SRMCheck,
  TimelineResponse,
  TokenPair,
  User,
  VersionCreateInput,
} from './types';

export * from './types';
export { ApiError, LOGOUT_EVENT, tokenStore, extractErrorMessage } from './client';

const exp = (id: string) => `/experiments/${id}`;

export const auth = {
  async login(email: string, password: string): Promise<TokenPair> {
    const pair = await request<TokenPair>('/auth/token/', {
      method: 'POST',
      body: { email, password },
      anonymous: true,
    });
    tokenStore.set(pair);
    return pair;
  },
  logout(): void {
    tokenStore.clear();
  },
  me: () => request<User>('/auth/me/'),
  isLoggedIn: () => !!tokenStore.access || !!tokenStore.refresh,
};

export const organizations = {
  list: (page = 1) => request<Paginated<Organization>>('/organizations/', { query: { page } }),
};

export const projects = {
  list: (params: { organization?: string; page?: number } = {}) =>
    request<Paginated<Project>>('/projects/', { query: params }),
};

export const experiments = {
  list: (params: ExperimentListParams = {}) =>
    request<Paginated<Experiment>>('/experiments/', { query: { ...params } }),
  get: (id: string) => request<Experiment>(`${exp(id)}/`),
  create: (input: ExperimentCreateInput) =>
    request<Experiment>('/experiments/', { method: 'POST', body: input }),
  update: (id: string, patch: Partial<Pick<Experiment, 'name' | 'description' | 'hypothesis'>>) =>
    request<Experiment>(`${exp(id)}/`, { method: 'PATCH', body: patch }),
  transition: (id: string, status: ExperimentStatus, reason?: string) =>
    request<Experiment>(`${exp(id)}/transition/`, { method: 'POST', body: { status, reason } }),
  start: (id: string) => request<Experiment>(`${exp(id)}/start/`, { method: 'POST', body: {} }),
  pause: (id: string, reason?: string) =>
    request<Experiment>(`${exp(id)}/pause/`, { method: 'POST', body: reason ? { reason } : {} }),
  versions: (id: string) => request<ExperimentVersion[]>(`${exp(id)}/versions/`),
  createVersion: (id: string, input: VersionCreateInput) =>
    request<ExperimentVersion>(`${exp(id)}/versions/`, { method: 'POST', body: input }),

  results: (id: string) => request<ExperimentResults>(`${exp(id)}/results/`),
  srm: (id: string) => request<SRMCheck>(`${exp(id)}/results/srm/`),
  health: (id: string) => request<HealthResponse>(`${exp(id)}/health/`),
  segments: (id: string, segments: SegmentInput[], aggregateLift?: number) =>
    request<SegmentsResponse>(`${exp(id)}/segments/`, {
      method: 'POST',
      body: aggregateLift === undefined ? { segments } : { segments, aggregate_lift: aggregateLift },
    }),
  timeline: (id: string) => request<TimelineResponse>(`${exp(id)}/timeline/`),
  productionImpact: (id: string) => request<ProductionImpactResponse>(`${exp(id)}/production-impact/`),

  decisionPreview: (id: string) => request<DecisionPreview>(`${exp(id)}/decision/`),
  decide: (id: string, apply: boolean) =>
    request<Decision>(`${exp(id)}/decision/`, { method: 'POST', body: { apply } }),
  decisions: (id: string, page = 1) =>
    request<Paginated<Decision>>(`${exp(id)}/decisions/`, { query: { page } }),
  anomalies: (id: string) => request<AnomaliesResponse>(`${exp(id)}/anomalies/`),

  rollout: (id: string) => request<RolloutState>(`${exp(id)}/rollout/`),
  setRollout: (id: string, percentage: number, reason: string) =>
    request<RolloutEvent>(`${exp(id)}/rollout/`, { method: 'POST', body: { percentage, reason } }),
  rollback: (id: string, reason: string, toPercentage?: number) =>
    request<RolloutEvent>(`${exp(id)}/rollback/`, {
      method: 'POST',
      body: toPercentage === undefined ? { reason } : { reason, to_percentage: toPercentage },
    }),
  rolloutPolicy: (id: string) => request<RolloutPolicy>(`${exp(id)}/rollout-policy/`),
  updateRolloutPolicy: (id: string, policy: Partial<RolloutPolicy>) =>
    request<RolloutPolicy>(`${exp(id)}/rollout-policy/`, { method: 'PUT', body: policy }),

  guardrails: (id: string) => request<Guardrail[]>(`${exp(id)}/guardrails/`),
  createGuardrail: (id: string, input: GuardrailInput) =>
    request<Guardrail>(`${exp(id)}/guardrails/`, { method: 'POST', body: input }),
  updateGuardrail: (id: string, gid: string, patch: Partial<GuardrailInput>) =>
    request<Guardrail>(`${exp(id)}/guardrails/${gid}/`, { method: 'PATCH', body: patch }),
  deleteGuardrail: (id: string, gid: string) =>
    request<null>(`${exp(id)}/guardrails/${gid}/`, { method: 'DELETE' }),

  // NEW endpoints (may 404 until the backend ships them)
  explain: (id: string) => request<ExplainResponse>(`${exp(id)}/explain/`),
  ask: (id: string, question: string) =>
    request<AskResponse>(`${exp(id)}/ask/`, { method: 'POST', body: { question } }),
};

export const engine = {
  debug: (experimentKey: string, userId: string, context: Record<string, unknown>) =>
    request<DebugResponse>('/evaluate/debug/', {
      method: 'POST',
      body: { experiment_key: experimentKey, user_id: userId, context },
    }),
};

export const audit = {
  list: (params: { experiment?: string; action?: string; page?: number } = {}) =>
    request<Paginated<AuditLog>>('/audit-logs/', { query: params }),
};

export const interactions = {
  detect: (pairs: InteractionPairInput[]) =>
    request<InteractionsResponse>('/interactions/', { method: 'POST', body: { pairs } }),
};

export const ai = {
  query: (question: string) =>
    request<AIQueryResponse>('/ai/query/', { method: 'POST', body: { question } }),
};

export const system = {
  healthz: () => request<ProbeStatus>('/healthz', { anonymous: true, root: true }),
  readyz: () => request<ProbeStatus>('/readyz', { anonymous: true, root: true }),
};

/** True when an error means "endpoint not deployed yet". */
export function isNotAvailable(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 404 || err.status === 405 || err.status === 501);
}

/** Fetch every page of a paginated list, up to `maxPages`. */
export async function fetchAllPages<T>(
  fetchPage: (page: number) => Promise<Paginated<T>>,
  maxPages = 10,
): Promise<T[]> {
  const out: T[] = [];
  for (let page = 1; page <= maxPages; page++) {
    const data = await fetchPage(page);
    out.push(...data.results);
    if (!data.next) break;
  }
  return out;
}
