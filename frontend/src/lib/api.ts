export type RunStatus = "running" | "paused" | "stopping" | "stopped" | "completed" | "failed" | "interrupted";

export interface Run {
  id: number;
  status: RunStatus;
  job: "analysis" | "recluster";
  started_at: string;
  finished_at: string | null;
  total_target: number;
  processed_in_run: number;
  current_interaction: string | null;
  current_step: string | null;
  error: string | null;
  settings: Partial<Settings>;
}

export interface Summary {
  interactions: number;
  processed: number;
  failed: number;
  pending: number;
  intents_extracted: number;
  discovered_intents: number;
  l1_nodes: number;
  l2_nodes: number;
  l3_nodes: number;
  l4_nodes: number;
  needs_review: number;
  unclassified: number;
  open_candidates: number;
  open_waiting: number;
  pending_proposals: number;
  overlapping_categories: number;
  assignment_review: Record<string, number>;
  imports: { id: number; name: string; source_format: string; interaction_count: number; created_at: string }[];
  dataset: string | null;
  taxonomy_version: number;
  run: Run | null;
  worker_alive: boolean;
  project: { id: string; name: string };
  taxonomy_language: string;
}

export interface Settings {
  ollama_url: string;
  llm_model: string;
  embedding_model: string;
  batch_size: number;
  clustering_sensitivity: "low" | "medium" | "high";
  request_timeout: number;
  auto_accept_new_categories: boolean;
  thresholds: Record<string, number>;
  sensitivity_presets: Record<string, Record<string, number>>;
  taxonomy_language: string;
  languages: Record<string, string>;
}

export interface Branding {
  logo: boolean;
  version: number | null;
}

export interface OllamaStatus {
  ok: boolean;
  reachable: boolean;
  url: string;
  models: string[];
  missing?: string[];
  error?: string;
}

export interface ConnectionTest {
  ok: boolean;
  models: string[];
  server: { ok: boolean; latency_ms?: number; error?: string } | null;
  llm: { ok: boolean; model: string; latency_ms?: number; error?: string; installed?: boolean } | null;
  embedding: { ok: boolean; model: string; latency_ms?: number; dimensions?: number; error?: string; installed?: boolean } | null;
}

export type NodeFlag = { type: "merge" | "split" | "create"; change_id: number };

export interface TaxNode {
  id: string;
  label: string;
  description: string;
  parent_id: string | null;
  level: 1 | 2 | 3 | 4;
  source: "predefined" | "ai" | "manual";
  status: "active" | "proposed" | "merged" | "split" | "retired" | "rejected";
  merged_into: string | null;
  interaction_count: number;
  intent_count: number;
  candidate_count: number;
  flags: NodeFlag[];
  created_at: string;
  updated_at: string;
}

export interface TaxonomyTree {
  version: number;
  nodes: TaxNode[];
  pending_proposals: number;
}

export interface Change {
  id: number;
  created_at: string;
  node_id: string | null;
  change_type: "create" | "update" | "refine" | "merge" | "split" | "retire" | "move";
  previous: any;
  proposed: any;
  status: "proposed" | "auto_accepted" | "accepted" | "rejected" | "superseded";
  rationale: string | null;
  source: "ai" | "user";
  run_id: number | null;
  decided_at: string | null;
  version: number | null;
}

export interface AnalysisEvent {
  id: number;
  created_at: string;
  run_id: number | null;
  kind: string;
  level: "info" | "success" | "warning" | "error";
  conversation_id: string | null;
  node_id: string | null;
  message: string;
  data: Record<string, any>;
}

export interface NodeExample {
  assignment_id: number;
  review_status: string;
  similarity: number | null;
  method: string;
  intent_text: string;
  evidence: string | null;
  conversation_id: string;
  channel: string | null;
  segment: string | null;
  interaction_id: number;
}

export interface NodeDetail extends Omit<TaxNode, "interaction_count" | "intent_count" | "candidate_count" | "flags"> {
  path: { id: string; label: string; level: number }[];
  children: { id: string; label: string; status: string; level: number }[];
  interaction_count: number;
  intent_count: number;
  examples: NodeExample[];
  proposal_members: { id: number; intent_text: string; evidence: string | null; conversation_id: string; interaction_id: number }[];
  history: Change[];
  events: AnalysisEvent[];
}

export interface AssignmentBrief {
  id: number;
  intent_text: string;
  l1_id: string | null; l1_label: string | null;
  l2_id: string | null; l2_label: string | null;
  l3_id: string | null; l3_label: string | null;
  l4_id: string | null; l4_label: string | null;
  review_status: "pending" | "confirmed" | "corrected" | "unclassified";
  needs_review: number;
  similarity: number | null;
  method: string;
}

export interface InteractionRow {
  id: number;
  conversation_id: string;
  seq: number;
  channel: string | null;
  segment: string | null;
  language: string | null;
  timestamp: string | null;
  queue: string | null;
  status: "pending" | "processing" | "processed" | "failed";
  summary: string | null;
  review_flag: number;
  review_unclassified: number;
  reviewer_notes: string | null;
  processed_order: number | null;
  batch_index: number | null;
  error: string | null;
  assignments: AssignmentBrief[];
  classification_status: "classified" | "partial" | "unclassified" | "failed" | "not_processed";
  review_status: "pending" | "needs_review" | "confirmed" | "corrected" | "unclassified";
}

export interface AssignmentFull extends AssignmentBrief {
  intent_id: number;
  interaction_id: number;
  review_reason: string | null;
  reviewer_notes: string | null;
  alternatives: { node_id: string; similarity: number; label: string | null }[];
  ai_original: Record<string, any> | null;
  l1_status: string | null; l2_status: string | null; l3_status: string | null; l4_status: string | null;
  history: { id: number; created_at: string; actor: string; action: string; before: any; after: any }[];
  updated_at: string;
}

export interface IntentFull {
  id: number;
  position: number;
  intent_text: string;
  evidence: string | null;
  evidence_verified: 0 | 1 | 2;
  reasoning: string | null;
  suggested_l2_id: string | null;
  model: string | null;
  assignment: AssignmentFull | null;
}

export interface InteractionDetail extends Omit<InteractionRow, "assignments"> {
  turns: { speaker: "customer" | "agent" | "system"; text: string }[];
  metadata: Record<string, any>;
  no_intent_reason: string | null;
  intents: IntentFull[];
  events: AnalysisEvent[];
}

export interface ImportPreview {
  token: string;
  format: string;
  total: number;
  columns: string[];
  mapping: Record<string, string | null>;
  needs_mapping: boolean;
  issues: { level: "error" | "warning" | "info"; record: string | null; message: string }[];
  issue_counts: Record<string, number>;
  stats: { avg_turns: number; channels: string[]; segments: string[] };
  preview: { conversation_id: string; channel: string | null; segment: string | null; turns: { speaker: string; text: string }[]; turn_count: number }[];
}

export interface Curve {
  points: { interactions: number; categories: number }[];
  batches: {
    batch_index: number; processed_total: number; interactions_in_batch: number; intents_extracted: number;
    new_l3: number; new_l4: number; total_l3: number; total_l4: number; proposals_created: number; created_at: string;
  }[];
}

export interface Evaluation {
  available: boolean;
  evaluated?: number;
  ground_truth_types?: number;
  discovered_l4?: number;
  l2_recall?: number | null;
  l4_purity?: number | null;
  types?: { key: string; label: string; expected_l2: string; conversations: number; top_categories: { id: string; label: string | null; conversations: number }[]; distinct_categories: number }[];
  tags?: Record<string, number>;
  note?: string;
}

export interface IntentVolumeItem {
  rank: number;
  id: string;
  label: string;
  description: string;
  path: { id: string; label: string; level: number }[];
  interactions: number;
  intents: number;
  share: number;
  channels: { name: string; interactions: number; share: number }[];
  segments: { name: string; interactions: number; share: number }[];
}

export interface IntentVolume {
  processed: number;
  top_n: number;
  items: IntentVolumeItem[];
  kpis: {
    classified_interactions: number;
    classified_share: number;
    top_coverage: number;
    top_intent_share: number;
    intents_for_80: number | null;
    active_l4: number;
    long_tail: number;
    long_tail_max: number;
    multi_intent_share: number;
    avg_intents: number;
  };
  coverage: number[];
  mix: { id: string | null; kind: "intent" | "other" | "none"; count?: number; label: string; intents: number }[];
  notes: Record<string, { text: string; model: string; created_at: string; stale: boolean }>;
}

export interface Overlaps {
  merge_threshold: number;
  compared: number;
  pairs: {
    a: { id: string; label: string; intents: number };
    b: { id: string; label: string; intents: number };
    l2: string;
    similarity: number;
    same_l3: boolean;
    proposal_id: number | null;
  }[];
}

export interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  stats?: {
    interactions?: number; processed?: number; imports?: number; l1?: number; l2?: number; l4?: number;
    pending_proposals?: number; run_status?: RunStatus | null; last_activity?: string | null; dataset?: string | null;
  };
}

export interface ProjectList {
  active: string;
  projects: Project[];
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* not json */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  summary: () => request<Summary>("/api/summary"),
  settings: () => request<Settings>("/api/settings"),
  saveSettings: (s: Partial<Settings>) => request<Settings>("/api/settings", json("PUT", s)),
  testConnection: (s: Partial<Settings>) => request<ConnectionTest>("/api/settings/test", json("POST", s)),
  ollamaStatus: () => request<OllamaStatus>("/api/ollama/status"),

  start: () => request<{ run_id: number }>("/api/analysis/start", json("POST")),
  resume: () => request<{ run_id: number }>("/api/analysis/resume", json("POST")),
  pause: () => request("/api/analysis/pause", json("POST")),
  stop: () => request("/api/analysis/stop", json("POST")),
  recluster: () => request("/api/analysis/recluster", json("POST")),
  retryFailed: () => request<{ requeued: number }>("/api/analysis/retry-failed", json("POST")),
  resetAnalysis: () => request("/api/analysis/reset", json("POST")),
  resetWorkspace: () => request("/api/workspace/reset", json("POST")),

  previewImport: (files: File[], txtSeparator?: string) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    if (txtSeparator) fd.append("txt_separator", txtSeparator);
    return request<ImportPreview>("/api/import/preview", { method: "POST", body: fd });
  },
  remapImport: (token: string, mapping: Record<string, string | null>) =>
    request<ImportPreview>("/api/import/remap", json("POST", { token, mapping })),
  commitImport: (token: string, mapping: Record<string, string | null> | null, name?: string) =>
    request<{ imported: number; skipped_existing: number }>("/api/import/commit", json("POST", { token, mapping, name })),
  importTaxonomy: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ version: number; language: string }>("/api/taxonomy/import", { method: "POST", body: fd });
  },

  taxonomy: (includeInactive = false) => request<TaxonomyTree>(`/api/taxonomy?include_inactive=${includeInactive}`),
  node: (id: string) => request<NodeDetail>(`/api/taxonomy/nodes/${encodeURIComponent(id)}`),
  createNode: (b: { parent_id: string | null; label: string; description: string }) => request<TaxNode>("/api/taxonomy/nodes", json("POST", b)),
  updateNode: (id: string, b: { label?: string; description?: string }) => request<TaxNode>(`/api/taxonomy/nodes/${id}`, json("PATCH", b)),
  moveNode: (id: string, parent_id: string) => request(`/api/taxonomy/nodes/${id}/move`, json("POST", { parent_id })),
  retireNode: (id: string) => request(`/api/taxonomy/nodes/${id}/retire`, json("POST")),
  mergeNodes: (source_id: string, target_id: string) => request("/api/taxonomy/merge", json("POST", { source_id, target_id })),
  proposals: (status: string = "proposed") => request<Change[]>(`/api/proposals?status=${status}`),
  changes: () => request<Change[]>("/api/changes"),
  acceptProposal: (id: number) => request(`/api/proposals/${id}/accept`, json("POST")),
  rejectProposal: (id: number) => request(`/api/proposals/${id}/reject`, json("POST")),

  interactions: () => request<InteractionRow[]>("/api/interactions"),
  interaction: (id: number) => request<InteractionDetail>(`/api/interactions/${id}`),
  reviewInteraction: (id: number, b: { flag?: boolean; unclassified?: boolean; notes?: string }) =>
    request<InteractionDetail>(`/api/interactions/${id}/review`, json("PATCH", b)),
  reviewAssignment: (id: number, b: { action: string; path?: Record<string, string | null>; notes?: string }) =>
    request(`/api/assignments/${id}/review`, json("POST", b)),

  events: (limit = 200) => request<AnalysisEvent[]>(`/api/events?limit=${limit}&newest=true`),
  curve: () => request<Curve>("/api/insights/curve"),
  evaluation: () => request<Evaluation>("/api/insights/evaluation"),
  intentVolume: (lang: string) => request<IntentVolume>(`/api/insights/intents?lang=${lang}`),
  generateIntentNotes: (force: boolean, lang: string) =>
    request<{ generated: number; failed?: string[]; busy: boolean }>(`/api/insights/intents/notes?force=${force}&lang=${lang}`, json("POST")),

  reportPdf: async (lang: string) => {
    const res = await fetch(`/api/export/report.pdf?lang=${lang}`);
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return res.blob();
  },

  branding: () => request<Branding>("/api/branding"),
  uploadLogo: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<Branding>("/api/branding/logo", { method: "POST", body: fd });
  },
  deleteLogo: () => request<Branding>("/api/branding/logo", json("DELETE")),

  projects: () => request<ProjectList>("/api/projects"),
  createProject: (b: { name: string; description?: string }) => request<Project>("/api/projects", json("POST", b)),
  updateProject: (id: string, b: { name?: string; description?: string }) => request<Project>(`/api/projects/${id}`, json("PATCH", b)),
  activateProject: (id: string) => request<Project>(`/api/projects/${id}/activate`, json("POST")),
  deleteProject: (id: string) => request<{ ok: boolean }>(`/api/projects/${id}`, json("DELETE")),
  overlaps: () => request<Overlaps>("/api/insights/overlaps"),
};
