import api from './api'

export type CommentPolicy = { enabled: boolean; include_replies: boolean }
export type CollectedComment = { comment_id: string; parent_comment_id: string; content: string; nickname: string; create_time: number; like_count: number; reply_count: number; saved_replies: number }
export type CommentPage = { items: CollectedComment[]; total: number; total_saved: number; page: number; page_size: number; collection: { state: string; updated_at: number; message?: string; continuation?: boolean } | null }
export const commentApi = {
  policy: async (id: number) => (await api.get<CommentPolicy>(`/monitor/accounts/${id}/comment-policy`)).data,
  savePolicy: async (id: number, policy: CommentPolicy) => (await api.put<CommentPolicy>(`/monitor/accounts/${id}/comment-policy`, policy)).data,
  list: async (id: string, page = 1, parent = '') => (await api.get<CommentPage>(`/monitor/posts/${id}/comments`, { params: { page, parent_comment_id: parent } })).data,
  collect: async (id: string) => (await api.post<{ status: string; reason?: string; message?: string }>(`/monitor/posts/${id}/comments/collect`, {}, { timeout: 180000 })).data,
}
export function commentError(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : '操作未完成，请检查服务连接后重试。'
}
