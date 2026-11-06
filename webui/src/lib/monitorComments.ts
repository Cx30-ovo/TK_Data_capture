import api from './api'

export type CommentPolicy = { enabled: boolean; include_replies: boolean }
export type CollectedComment = { comment_id: string; parent_comment_id: string; content: string; nickname: string; create_time: number; like_count: number; reply_count: number; saved_replies: number
  root_comment_id?: string; reply_to_comment_id?: string | null; reply_relation_source?: 'root' | 'platform' | 'unknown' | 'invalid';
  reply_to_nickname?: string; reply_to_creator_hash?: string; reply_object_source?: 'platform' | 'unknown';
  reply_target_display_name?: string; reply_target_display_source?: 'platform' | 'collected_comment' | 'collected_user' | null;
  reply_relation_status?: 'direct' | 'reply' | 'unknown' | 'invalid' | 'missing_target' | 'cross_thread' | 'self_reference' | 'cycle'; saved_direct_replies?: number }
export type CommentPage = { items: CollectedComment[]; total: number; total_saved: number; page: number; page_size: number;
  thread_total?: number; unlinked_count?: number; tree_parent_comment_id?: string;
  collection: { state: string; updated_at: number; message?: string; continuation?: boolean } | null }
export const commentApi = {
  policy: async (id: number) => (await api.get<CommentPolicy>(`/monitor/accounts/${id}/comment-policy`)).data,
  savePolicy: async (id: number, policy: CommentPolicy) => (await api.put<CommentPolicy>(`/monitor/accounts/${id}/comment-policy`, policy)).data,
  list: async (id: string, page = 1, parent = '') => (await api.get<CommentPage>(`/monitor/posts/${id}/comments`, { params: { page, parent_comment_id: parent } })).data,
  tree: async (id: string, root: string, target = '', page = 1) => (await api.get<CommentPage>(`/monitor/posts/${id}/comments`, { params: { page, parent_comment_id: root, view: 'tree', reply_to_comment_id: target } })).data,
  collect: async (id: string) => (await api.post<{ status: string; reason?: string; message?: string }>(`/monitor/posts/${id}/comments/collect`, {}, { timeout: 180000 })).data,
}
export function commentError(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : '操作未完成，请检查服务连接后重试。'
}
