import { useEffect, useId, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { commentApi, commentError, type CollectedComment } from '@/lib/monitorComments'

const stamp = (value: number) => value ? new Date(value * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '时间未知'
const shortStamp = (value: number) => value ? new Date(value * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '时间未知'
function CommentRow({ item }: { item: CollectedComment }) {
  const [expanded, setExpanded] = useState(false), [clipped, setClipped] = useState(false)
  const text = useRef<HTMLParagraphElement>(null), contentId = useId()
  useEffect(() => {
    const node = text.current
    if (!node || expanded) return
    const measure = () => setClipped(node.scrollHeight > node.clientHeight + 1)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [item.content, expanded])
  return <div className="min-w-0 space-y-1 py-2">
    <p className="flex flex-wrap items-center gap-x-2 text-xs text-cyber-text-secondary"><span className="max-w-32 truncate">{item.nickname || '匿名用户'}</span><time title={stamp(item.create_time)}>{shortStamp(item.create_time)}</time><span>赞 {item.like_count}</span></p>
    <p ref={text} id={contentId} className={`whitespace-pre-wrap break-words text-sm leading-5 text-cyber-text-primary [overflow-wrap:anywhere] ${expanded ? '' : 'line-clamp-2'}`}>{item.content || '空评论'}</p>
    {clipped && <button type="button" className="min-h-11 rounded px-1 text-xs text-primary focus-visible:outline focus-visible:outline-2" aria-expanded={expanded} aria-controls={contentId} onClick={() => setExpanded(!expanded)}>{expanded ? '收起全文' : '展开全文'}</button>}
  </div>
}
function Replies({ id, parent }: { id: string; parent: string }) {
  const [page, setPage] = useState(1)
  const query = useQuery({ queryKey: ['postComments', id, parent, page], queryFn: () => commentApi.list(id, page, parent), retry: false })
  return <div className="ml-2 border-l-2 border-cyber-border-subtle pl-3 sm:ml-4">{query.isPending ? <p role="status">正在读取回复…</p> : query.isError ? <p role="alert">{commentError(query.error)}</p> : <>{!query.data.items.length && <p className="py-3 text-xs text-cyber-text-secondary">暂无已采集回复</p>}{query.data.items.map(item => <CommentRow key={item.comment_id} item={item} />)}<Paging page={page} total={query.data.total} onChange={setPage} /></>}</div>
}
function Paging({ page, total, onChange }: { page: number; total: number; onChange: (page: number) => void }) {
  return total > 20 ? <div className="flex flex-wrap items-center justify-between gap-2 text-xs"><Button type="button" variant="ghost" disabled={page === 1} onClick={() => onChange(page - 1)}>上一页</Button><span>第 {page} 页 · 共 {total} 条</span><Button type="button" variant="ghost" disabled={page * 20 >= total} onClick={() => onChange(page + 1)}>下一页</Button></div> : null
}
function CommentsBody({ id }: { id: string }) {
  const client = useQueryClient(), [page, setPage] = useState(1), [expanded, setExpanded] = useState<string[]>([])
  const query = useQuery({ queryKey: ['postComments', id, '', page], queryFn: () => commentApi.list(id, page), retry: false,
    refetchInterval: query => ['running', 'partial', 'pending'].includes(query.state.data?.collection?.state || '') ? 15000 : false })
  const collect = useMutation({ mutationFn: () => commentApi.collect(id), onSuccess: () => { void client.invalidateQueries({ queryKey: ['postComments', id] }) } })
  const data = query.data
  return <div className="space-y-2">
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1"><p className="text-xs text-cyber-text-secondary">已保存 <b className="font-semibold text-cyber-text-primary">{data?.total_saved ?? '—'}</b> 条 · 含子评论</p><Button type="button" variant="outline" className="min-h-11" disabled={collect.isPending} onClick={() => collect.mutate()}>{collect.isPending ? '正在采集评论…' : '采集 / 更新评论'}</Button></div>
    {collect.isSuccess && collect.data.status !== 'ok' && <p role="status" className="text-xs">{collect.data.reason || collect.data.message || '评论采集已结束'}{collect.data.status === 'deferred' ? '，请稍后重试。' : ''}</p>}
    {collect.isError && <p role="alert" className="text-sm text-status-warning">{commentError(collect.error)}</p>}
    {query.isPending ? <p role="status">正在读取评论…</p> : query.isError ? <p role="alert">{commentError(query.error)}<Button type="button" variant="ghost" onClick={() => void query.refetch()}>重新读取评论</Button></p> : <>
      {data?.collection && <p role="status" title={data.collection.message} className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 rounded-md bg-cyber-bg-secondary px-2 py-1.5 text-xs leading-5 text-cyber-text-secondary"><span>{({ running: '正在分页采集', partial: '未完成，进度已保存', completed: '本轮可见评论分页已完成', pending: '等待采集' } as Record<string, string>)[data.collection.state] || data.collection.state}</span><time title={stamp(data.collection.updated_at)}>{shortStamp(data.collection.updated_at)}</time></p>}
      {!data?.items.length && <p className="py-4 text-sm text-cyber-text-secondary">暂无已采集评论。此状态不代表平台评论数为零；请先在账号设置中启用评论采集。</p>}
      <div className="max-h-[min(28dvh,12rem)] overflow-y-auto overscroll-contain pr-1 [scrollbar-gutter:stable] focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary" tabIndex={0} role="region" aria-label="已采集评论列表">{data?.items.map(item => <article key={item.comment_id} className="border-b border-cyber-border-subtle last:border-0"><CommentRow item={item} />{(item.reply_count > 0 || item.saved_replies > 0) && <><button type="button" className="min-h-11 rounded px-2 text-xs text-primary focus-visible:outline focus-visible:outline-2" aria-expanded={expanded.includes(item.comment_id)} onClick={() => setExpanded(old => old.includes(item.comment_id) ? old.filter(v => v !== item.comment_id) : [...old, item.comment_id])}>{expanded.includes(item.comment_id) ? '收起回复' : `查看已采集回复（${item.saved_replies} / 平台显示 ${item.reply_count}）`}</button>{expanded.includes(item.comment_id) && <Replies id={id} parent={item.comment_id} />}</>}</article>)}</div>
      {data && <Paging page={page} total={data.total} onChange={setPage} />}
    </>}
    <details className="text-xs text-cyber-text-secondary"><summary className="flex min-h-11 cursor-pointer items-center rounded focus-visible:outline focus-visible:outline-2">采集说明与状态详情</summary><div className="max-h-24 space-y-1 overflow-y-auto overscroll-contain leading-5" tabIndex={0} role="region" aria-label="评论采集说明">{data?.collection?.message && <p>{data.collection.message}</p>}<p>不设数量上限，按平台分页持续采集。长列表在评论区内滚动，长评论可展开全文；隐藏、删除或权限受限的内容无法取得。昵称脱敏，评论不等于已核实事实。</p></div></details>
  </div>
}
export function PostComments({ awemeId }: { awemeId: string }) {
  const [open, setOpen] = useState(false)
  return <section className="min-w-0 rounded-lg border border-cyber-border-subtle px-3 py-1" aria-label="作品评论与子评论"><button type="button" className="min-h-11 w-full rounded text-left text-sm font-semibold text-cyber-text-primary focus-visible:outline focus-visible:outline-2" aria-expanded={open} onClick={() => setOpen(!open)}>评论与子评论{open ? ' · 收起' : ' · 展开'}</button>{open && <CommentsBody key={awemeId} id={awemeId} />}</section>
}
