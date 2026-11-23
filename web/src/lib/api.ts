// Typed client for the Python API (proxied at /api by next.config.ts).

export type Provider = { name: string; model: string; enabled: boolean; has_key: boolean };

export type Status = {
  db: { ok: boolean; message: string };
  project: { name: string; market: string; target: string; competitors: string[] };
  providers: Provider[];
  analysis: { model: string; has_key: boolean };
};

export type HistoryRow = {
  run_id: string;
  provider: string;
  started_at: string;
  brand: string;
  is_target: boolean;
  n_responses: number;
  mention_rate: number | null;
  share_of_voice: number | null;
  avg_rank: number | null;
  citation_share: number | null;
  positive_rate: number | null;
};

export type Kpi = {
  provider: string;
  brand: string;
  value: number | null;
  delta: number | null;
  n_responses: number;
};

export type CategoryRow = {
  provider: string;
  brand: string;
  is_target: boolean;
  category: string;
  n_responses: number;
  mention_rate: number | null;
};

export type OpsRow = {
  run_id: string;
  provider: string;
  run_type: string;
  status: string;
  started_at: string;
  calls: number;
  errors: number;
  cost_usd: number | null;
  avg_latency_ms: number | null;
};

export type Overview = {
  counts: Record<string, number>;
  history: HistoryRow[];
  kpis: Kpi[];
  sov: Kpi[];
  leaders: Record<string, string>;
  categories: CategoryRow[];
  top_opportunities: {
    title: string;
    gap_type: string;
    priority_score: number | null;
    effort: string | null;
    review: string | null;
  }[];
  ops: OpsRow[];
};

export type PromptRow = {
  prompt_id: string;
  text: string;
  category: string;
  intent: string;
  language: string;
};

export type Panel = { version: string; prompts: PromptRow[] };

export type DiscoveryPlan = {
  panel_version: string;
  n_prompts: number;
  providers: string[];
  repeats: number;
  n_calls: number;
  missing_keys: string[];
};

export type Run = {
  run_id: string;
  provider: string;
  model: string;
  panel_version: string;
  run_type: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  n_responses: number;
  n_errors: number;
  cost_usd: number | null;
  avg_latency_ms?: number | null;
  diagnosed: boolean;
};

export type VisibilityRow = {
  brand: string;
  is_target: boolean;
  category: string;
  n_responses: number;
  mention_rate: number | null;
  share_of_voice: number | null;
  avg_rank: number | null;
  citation_share: number | null;
  positive_rate: number | null;
};

export type SourceRow = {
  category: string;
  domain: string;
  domain_type: string | null;
  n_citations: number;
  citation_share: number | null;
};

export type VisibilityPayload = {
  visibility: VisibilityRow[];
  sources: SourceRow[];
  repeatability: {
    brand: string;
    n_prompts: number;
    agreement_rate: number | null;
    mean_within_prompt_sd: number | null;
  }[];
  accuracy: {
    subject: string;
    attribute: string;
    n_checked: number;
    n_match: number;
    n_mismatch: number;
    n_not_mentioned: number;
    n_unverifiable: number;
    accuracy_rate: number | null;
  }[];
  products: {
    product_name: string;
    maker: string;
    category: string;
    n_responses: number;
    avg_rank: number | null;
  }[];
};

export type Mention = {
  brand: string;
  is_target: boolean;
  rank: number | null;
  sentiment: string | null;
  recommended: boolean | null;
};

export type ResponseRow = {
  response_id: string;
  repeat_no: number;
  provider: string;
  prompt_id: string;
  prompt: string;
  category: string;
  intent: string;
  answer_text: string | null;
  error: string | null;
  latency_ms: number | null;
  cost_usd: number | null;
  citations: { url: string; domain: string }[];
  mentions: Mention[];
};

export type Opportunity = {
  opportunity_id: string;
  run_id: string;
  gap_type: string;
  category: string | null;
  title: string;
  rationale: string | null;
  validation_approach: string | null;
  severity: number | null;
  confidence: number | null;
  effort: string | null;
  priority_score: number | null;
  status: string;
  metric_name: string | null;
  target_value: number | null;
  benchmark_value: number | null;
  n_evidence: number;
  recommendation_id: string | null;
  action: string | null;
  rec_status: string | null;
  reviewed_by: string | null;
  review_notes: string | null;
  created_at: string;
};

export type Evidence = { response_id: string; provider: string; prompt: string; answer: string };

export type Variant = {
  variant_id: string;
  opportunity_id: string;
  opportunity: string;
  version: number;
  title: string;
  content_type: string | null;
  body: string;
  status: string;
  generated_by: string | null;
  grounded: boolean | null;
  grounding: Record<string, unknown> | null;
  reviewed_by: string | null;
  review_notes: string | null;
  created_at: string;
};

export type Knowledge = {
  stats: { documents: number; chunks: number };
  local_docs: { doc_id: string; title: string; source_url: string; verified_at: string }[];
  error: string | null;
};

export type AgentRun = {
  thread_id: string;
  status: string;
  last_node: string | null;
  summary: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AgentDetail = {
  thread_id: string;
  status: string;
  pending: { drafts: { variant_id: string; title: string; grounded: boolean }[] }[];
  values: {
    run_ids?: string[];
    opportunity_ids?: string[];
    drafts?: { variant_id: string; title: string; grounded: boolean }[];
    report?: Record<string, unknown>;
    log?: { at: string; node: string; message: string }[];
    errors?: string[];
  };
};

export type Experiment = {
  experiment_id: string;
  status: string;
  design: string;
  hypothesis: string | null;
  n_prompts: number;
  baseline_run_id: string;
  retest_run_id: string | null;
  variant: string | null;
  variant_status: string | null;
  created_by: string | null;
  created_at: string;
  completed_at: string | null;
};

export type ExperimentResult = {
  brand: string;
  is_target: boolean;
  baseline_value: number | null;
  retest_value: number | null;
  delta: number | null;
  ci_low: number | null;
  ci_high: number | null;
  p_value: number | null;
  n_baseline: number;
  n_retest: number;
  interpretation: string | null;
};

export type ValidationSample = { sample_version: string; n_responses: number; n_labels: number };

export type PRF = {
  precision: number | null;
  recall: number | null;
  f1: number | null;
  support: number;
  n: number;
};

export type ValidationReport = {
  sample_version: string;
  labellers: string[];
  n_items: number;
  n_disagreements: number;
  kappa_mentioned: number | null;
  kappa_sentiment: number | null;
  mentioned: PRF;
  is_recommended: PRF | null;
  rank_accuracy: number | null;
  rank_n: number;
  sentiment_accuracy: number | null;
  sentiment_macro_f1: number | null;
  sentiment_n: number;
  errors: Record<string, string>[];
};

export type Job = {
  job_id: string;
  kind: string;
  params: Record<string, unknown>;
  status: "queued" | "running" | "done" | "failed";
  progress: { provider?: string; done?: number; total?: number; stage?: string };
  result: unknown;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Can't reach the API. Start it with: uvicorn src.api.main:app --port 8000");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* body was not JSON */
    }
    if (res.status === 500 && !detail) detail = "The API returned an error. Check its terminal.";
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
};
