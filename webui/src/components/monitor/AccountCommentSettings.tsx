import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { commentApi, commentError, type CommentPolicy } from '@/lib/monitorComments'

export function AccountCommentSettings({ accountId, disabled }: { accountId: number; disabled?: boolean }) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['commentPolicy', accountId], queryFn: () => commentApi.policy(accountId), retry: false })
  const [draft, setDraft] = useState<CommentPolicy | null>(null)
  const value = draft || query.data
  const save = useMutation({ mutationFn: (policy: CommentPolicy) => commentApi.savePolicy(accountId, policy), onSuccess: data => { client.setQueryData(['commentPolicy', accountId], data); setDraft(null) } })
  return <details className="rounded-lg border border-cyber-border-subtle p-3 text-cyber-text-primary">
    <summary className="min-h-11 cursor-pointer text-sm font-medium">评论与子评论采集 · {query.data?.enabled ? '已启用' : '未启用'}</summary>
    {query.isPending ? <p role="status">正在读取评论设置…</p> : query.isError ? <p role="alert">{commentError(query.error)}<Button type="button" variant="outline" onClick={() => void query.refetch()}>重新读取</Button></p> : value && <fieldset disabled={disabled || save.isPending} className="space-y-3">
      <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={value.enabled} onChange={e => { save.reset(); setDraft({ ...value, enabled: e.target.checked }) }} />自动采集新作品评论</label>
      <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={value.include_replies} onChange={e => { save.reset(); setDraft({ ...value, include_replies: e.target.checked }) }} />同时采集子评论</label>
      <p className="rounded-lg bg-cyber-bg-secondary p-3 text-sm">不设数量上限 · 分页采集全部平台可见评论</p>
      <p className="text-xs leading-6 text-cyber-text-secondary">保存后生效。新作品发现、快照保存成功后同步更新评论。分页直至无更多，每页保存进度，未完成自动续采。与账号、话题监控分轮共用浏览器，遵循暂停、间隔和风控冷却。近7天作品每6小时额外刷新；更早作品的未完成任务继续补齐。已有作品可在详情中手动补采。</p>
      <Button type="button" variant="outline" className="min-h-11" disabled={!draft || save.isPending} onClick={() => value && save.mutate(value)}>{save.isPending ? '保存中…' : '保存评论设置'}</Button>
      {save.isSuccess && !draft && <p role="status" className="text-sm">评论设置已保存</p>}
      {save.isError && <p role="alert" className="text-sm text-status-warning">{commentError(save.error)}</p>}
    </fieldset>}
  </details>
}
