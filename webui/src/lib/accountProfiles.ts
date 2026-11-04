import api from './api'

export interface ProfileEvidence {
  post_id: string
  field: 'title'
  snippet: string
  published_at: number
}

export interface AccountProfile {
  version: string
  input_sha256: string
  account: { id: number; display_name: string; platform: string }
  window: { start: number; end: number; days: number }
  counts: { eligible: number; excluded_status: number; sampled: number; with_title: number; missing_title: number; truncated: boolean }
  publication: { earliest: number | null; latest: number | null; posts_per_day: number }
  title_length: { mean: number | null; median: number | null; histogram: { label: string; count: number }[]; sample_count: number; excluded_count: number; extraction_version: string; rule: string; evidence: (ProfileEvidence & { extracted_title: string; word_count: number; method: string })[] }
  signals: { key: string; label: string; count: number; evidence: ProfileEvidence[] }[]
  hashtags: { tag: string; post_count: number; evidence: ProfileEvidence[] }[]
  coverage: { observed_posts: number; without_observation: number; invalid_observations: number; lifecycle: { stage: string; posts: number }[] }
  limits: string[]
}

export async function fetchAccountProfile(accountId: number, days: number, signal?: AbortSignal) {
  return (await api.get<AccountProfile>(`/monitor/accounts/${accountId}/profile`, { params: { days }, signal })).data
}
