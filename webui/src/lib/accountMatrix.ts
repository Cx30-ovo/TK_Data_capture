import api from './api'

export type AccountRole = 'unassigned' | 'owned' | 'competitor'
export interface MatrixAccount {
  id: number
  identity_sha256: string
  platform: string
  display_name: string
  enabled: boolean
  snapshots_paused: boolean
  posts: number
  observed_posts: number
  latest_published_at: number | null
  role: AccountRole
  group: string
  group_inference?: GroupSuggestion | null
  competitor_ids: number[]
  unavailable_competitor_ids: number[]
}
export interface AccountMatrixData { version: number; accounts: MatrixAccount[]; limits: string[] }
export interface MatrixDraft {
  expected_version: number
  identity_sha256: string
  role: AccountRole
  group: string
  competitor_ids: number[]
}
export interface GroupSuggestion {
  group: string
  rationale: string
  evidence: { post_id: string; snippet: string; field: string; published_at: number }[]
  limitations: string[]
  model: string
  scope: string
  cached: boolean
  input_titles: number
  input_sha256: string
  generated_at?: number
  matrix?: AccountMatrixData
}
export interface GroupModelStatus { available: boolean; reason: string | null; model: string | null; scope: string }
export const accountMatrixApi = {
  modelStatus: async () => (await api.get<GroupModelStatus>('/monitor/account-matrix/model-status')).data,
  infer: async (id: number) => (await api.post<GroupSuggestion>(`/monitor/account-matrix/${id}/infer-group`, { days: 30 }, { timeout: 100000 })).data,
  read: async () => (await api.get<AccountMatrixData>('/monitor/account-matrix')).data,
  save: async (id: number, draft: MatrixDraft) => (await api.put<AccountMatrixData>(`/monitor/account-matrix/${id}`, draft)).data,
}
