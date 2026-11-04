import api from './api'

export type StyleReference = { post_id: string; field: string; snippet: string; published_at: number; snippet_sha256: string }
export type StyleFinding = { text: string; summary?: string; labels?: string[]; evidence: StyleReference[] }
export type StyleScope = { days: number; start: number; end: number; eligible: number; inspected: number; usable: number; sampled: number; excluded: number; scan_truncated: boolean; selection: string; material_level: string; sample_limit?: number; sample_limited?: boolean; input_chars?: number; input_char_budget?: number; batch_count?: number; planned_model_requests?: number; context_window?: number; max_batches?: number }
export type StyleSnapshot = {
  id: number; version: string; model: string; generated_at: number; input_sha256: string; scope: StyleScope;
  themes: StyleFinding; title_structure: StyleFinding; phrasing: StyleFinding; geography: StyleFinding; audience: StyleFinding;
  limitations: string[]
  topics?: { label: string; count: number; post_ids: string[] }[]
}
export type AccountStyle = {
  incremental?: { pending_posts: number; reused_posts: number; planned_model_requests: number; reanchor_due: boolean; update_recommended: boolean; automatic_model_calls: boolean; threshold_posts: number; threshold_hours: number; max_model_requests: number | null }
  model_status: { available: boolean; reason: string | null }; scope: StyleScope; latest: StyleSnapshot | null;
  versions: StyleSnapshot[]; changed: boolean; new_posts: number; revised_or_removed: number; history_limit: number; analysis_version: string;
}
export async function fetchAccountStyle(id: number, days: number): Promise<AccountStyle> {
  return (await api.get(`/monitor/accounts/${id}/style-profile`, { params: { days } })).data
}
export async function analyzeAccountStyle(id: number, days: number, maxModelRequests: number | null = null): Promise<StyleSnapshot> {
  return (await api.post(`/monitor/accounts/${id}/style-profile`, { days, max_model_requests: maxModelRequests }, { timeout: 930000 })).data
}
