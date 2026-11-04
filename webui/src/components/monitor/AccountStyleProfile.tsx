import { useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlignLeft, ArrowUpRight, ChevronLeft, ChevronRight, Layers3, Loader2, MapPin, MessageSquareText, Sparkles, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { analyzeAccountStyle, fetchAccountStyle, type StyleFinding, type StyleReference } from '@/lib/accountStyle'

const dimensions = [
  { key: 'themes', label: '内容主题', Icon: Layers3 },
  { key: 'title_structure', label: '标题结构', Icon: AlignLeft },
  { key: 'phrasing', label: '表达习惯', Icon: MessageSquareText },
  { key: 'geography', label: '地域定位', Icon: MapPin },
  { key: 'audience', label: '受众推测', Icon: Users },
] as const
type Dimension = typeof dimensions[number]['key']
const focus = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary'
const date = (value: number) => new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })
const errorText = (error: unknown) => (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '风格档案当前不可用，请稍后重试'
const excerpt = (finding: StyleFinding) => finding.summary || (finding.text.length > 56 ? `${finding.text.slice(0, 56)}…` : finding.text)

function Coverage({ analyzed, total }: { analyzed: number; total: number }) {
  const percent = total ? Math.min(100, analyzed / total * 100) : 0
  return <div className="flex min-w-0 items-center gap-3">
    <div className="relative h-16 w-16 shrink-0">
      <svg viewBox="0 0 64 64" aria-hidden="true" className="h-full w-full -rotate-90"><circle cx="32" cy="32" r="27" fill="none" stroke="currentColor" strokeWidth="5" className="text-cyber-border-subtle" /><circle cx="32" cy="32" r="27" fill="none" stroke="currentColor" strokeWidth="5" pathLength="100" strokeDasharray={`${percent} 100`} strokeLinecap="round" className="text-primary" /></svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-semibold tabular-nums text-cyber-text-primary">{percent.toFixed(1)}<span className="text-[10px]">%</span></span>
    </div>
    <div><p className="text-xs text-cyber-text-secondary">样本覆盖</p><p className="mt-1 text-sm text-cyber-text-primary"><strong className="text-xl font-semibold tabular-nums">{analyzed}</strong><span className="text-cyber-text-secondary"> / {total} 篇</span></p></div>
  </div>
}

function Evidence({ items }: { items: StyleReference[] }) {
  const [position, setPosition] = useState(0)
  const index = Math.min(position, items.length - 1)
  const item = items[index]
  if (!item) return <p className="text-sm text-cyber-text-secondary">暂无可引用作品</p>
  return <div className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel p-3 sm:p-4">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><p aria-live="polite" aria-atomic="true" className="text-xs text-cyber-text-secondary">代表作品 {index + 1} / {items.length} · {date(item.published_at)}</p><div className="flex gap-2"><Button type="button" variant="outline" className="h-9 min-w-9 px-2" aria-label="风格依据上一条" disabled={index === 0} onClick={() => setPosition(index-1)}><ChevronLeft aria-hidden="true" className="h-4 w-4" /></Button><Button type="button" variant="outline" className="h-9 min-w-9 px-2" aria-label="风格依据下一条" disabled={index === items.length-1} onClick={() => setPosition(index+1)}><ChevronRight aria-hidden="true" className="h-4 w-4" /></Button></div></div>
    <p className={`max-h-40 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-7 text-cyber-text-primary ${focus}`} tabIndex={0}>{item.snippet}</p>
    <details className="mt-2 text-xs text-cyber-text-secondary"><summary className={`min-h-10 cursor-pointer py-3 ${focus}`}>引用校验信息</summary><p className="break-all leading-6">作品 {item.post_id}<br />字段 {item.field} · 标题级 · SHA-256 {item.snippet_sha256}</p></details>
  </div>
}

export function AccountStyleProfile({ accountId, days }: { accountId: number; days: number }) {
  const id = useId()
  const [selected, setSelected] = useState<number | null>(null)
  const [dimension, setDimension] = useState<Dimension>('themes')
  const [longTerm, setLongTerm] = useState(false)
  const windowDays = longTerm ? 365 : days
  const client = useQueryClient()
  const key = ['accountStyle', accountId, windowDays]
  const query = useQuery({ queryKey: key, queryFn: () => fetchAccountStyle(accountId, windowDays), refetchOnWindowFocus: false, retry: false, refetchInterval: 60000 })
  const mutation = useMutation({ mutationFn: () => analyzeAccountStyle(accountId, windowDays), onSuccess: async () => {
    setSelected(null)
    await client.invalidateQueries({ queryKey: key })
  } })
  const data = query.data
  const snapshot = data?.versions.find(v => v.id === selected) || data?.latest || null
  const upgraded = !!(data?.latest && data.latest.version !== data.analysis_version)
  const current = dimensions.find(d => d.key === dimension)!
  const finding = snapshot?.[dimension]
  const overBatchLimit = !!(data?.scope.batch_count && data.scope.max_batches && data.scope.batch_count > data.scope.max_batches)
  const topics = snapshot?.topics?.filter(topic => topic.count > 0).sort((a,b) => b.count-a.count) || []
  const topicTotal = topics.reduce((sum, item) => sum+item.count, 0)
  return <section aria-labelledby={`${id}-heading`} className="min-w-0 overflow-hidden rounded-xl border border-cyber-border-subtle bg-cyber-bg-panel">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyber-border-subtle px-4 py-4 sm:px-5">
      <div className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary"><Sparkles aria-hidden="true" className="h-4 w-4" /></span><div><h3 id={`${id}-heading`} className="font-semibold text-cyber-text-primary">账号风格档案</h3><p className="mt-0.5 text-xs text-cyber-text-secondary">模型推断 · 仅手动更新</p></div></div>
      <div className="flex max-w-full flex-wrap items-center gap-2">
        <label className="text-xs text-cyber-text-secondary">观察范围 <select aria-label="风格观察范围" disabled={mutation.isPending} value={longTerm ? 'long' : 'recent'} onChange={e => { setLongTerm(e.target.value === 'long'); setSelected(null) }} className={`h-10 rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel px-2 ${focus}`}><option value="recent">近期 {days} 天</option><option value="long">长期 365 天</option></select></label>
        {snapshot && <label className="sr-only" htmlFor={`${id}-version`}>分析记录</label>}
        {snapshot && <select id={`${id}-version`} value={snapshot.id} onChange={event => setSelected(Number(event.target.value))} className={`h-10 min-w-0 max-w-full rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel px-2 text-xs text-cyber-text-secondary ${focus}`}>{data?.versions.map((v,i) => <option key={v.id} value={v.id}>{i === 0 ? '最新' : '历史版本'} · {date(v.generated_at)}</option>)}</select>}
        <Button type="button" variant="outline" className="min-h-10 gap-2" disabled={!data?.model_status.available || mutation.isPending || overBatchLimit || (data?.scope.sampled ?? 0) < 5} onClick={() => mutation.mutate()}>{mutation.isPending && <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" />}{mutation.isPending ? '正在分析…' : upgraded ? '扩大样本并更新' : data?.latest ? '更新风格分析' : '分析账号风格'}</Button>
      </div>
    </div>
    <div className="space-y-4 p-4 sm:p-5">
      {data && <div className="grid gap-4 rounded-lg bg-cyber-bg-secondary/60 p-4 sm:grid-cols-[1fr_1fr_1fr] sm:items-center">
        <Coverage analyzed={snapshot?.scope.sampled ?? 0} total={snapshot?.scope.eligible ?? data.scope.eligible} />
        <div className="border-cyber-border-subtle sm:border-l sm:pl-5"><p className="text-xs text-cyber-text-secondary">本次可分析</p><p className="mt-1 text-xl font-semibold tabular-nums text-cyber-text-primary">{data.scope.sampled}<span className="ml-1 text-xs font-normal text-cyber-text-secondary">篇 / 近 {windowDays} 天</span></p><p className="mt-1 text-xs text-cyber-text-secondary">{data.incremental ? `待分析 ${data.incremental.pending_posts} · 可复用 ${data.incremental.reused_posts} 篇 · 预计 ${data.incremental.planned_model_requests} 次请求` : data.scope.batch_count ? `${data.scope.batch_count} 批分析 + 1 次汇总` : `最多 ${data.scope.sample_limit ?? 500} 篇，受输入预算限制`}</p></div>
        <div className="border-cyber-border-subtle sm:border-l sm:pl-5"><p className="text-xs text-cyber-text-secondary">{snapshot ? '分析时间' : '等待首次分析'}</p><p className="mt-2 text-sm tabular-nums text-cyber-text-primary">{snapshot ? date(snapshot.generated_at) : '尚无分析记录'}</p><p className="mt-1 text-xs text-cyber-text-secondary">{snapshot && snapshot.id !== data.latest?.id ? '正在查看历史版本' : '标题级材料 · 结论待核实'}</p></div>
      </div>}
      <div role="status" className="text-xs leading-6 text-cyber-text-secondary">
        {query.isPending ? '正在读取风格档案…' : query.isError ? errorText(query.error) : data && <>
          {!data.model_status.available && <p>{data.model_status.reason}；已有档案仍可阅读。</p>}
          {data.scope.sampled < 5 && <p>可用标题不足 5 篇，暂不能分析。</p>}
          {overBatchLimit && <p>需要 {data.scope.batch_count} 批，超过 {data.scope.max_batches} 批安全上限，请缩短时间窗口。</p>}
          {mutation.isPending && <p>正在分批分析 {data.scope.sampled} 篇标题并汇总，可能需要数分钟；请勿重复提交。</p>}
          {upgraded && !mutation.isPending && <p>当前为旧版档案。更新后将按模型容量分批分析并汇总。</p>}
          {data.changed && !upgraded && <p>输入已更新：新增 {data.new_posts} 篇，变化或移出窗口 {data.revised_or_removed} 篇。</p>}
          {data.incremental && <p>{data.incremental.reanchor_due ? '本次将从原始材料重新校准。' : data.incremental.update_recommended ? '已达到建议更新条件。' : '增量材料持续积累中。'}新增约 30 篇或有变化且距上次分析满 24 小时提示更新；每 30 天重新校准。仅提示，不自动调用模型；不影响标题生成采用最新已保存档案。</p>}
        </>}
      </div>
      {mutation.isError && <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">{errorText(mutation.error)}</p>}
      {!snapshot && !query.isPending && !query.isError && <p className="py-5 text-center text-sm text-cyber-text-secondary">尚未生成风格档案。规则统计仍可在下方查看。</p>}
      {snapshot && <>
        <div className="grid items-stretch gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <div className="min-w-0 rounded-lg border border-cyber-border-subtle p-4">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-medium text-cyber-text-primary">样本主题分布</h4><span className="text-[11px] text-cyber-text-secondary">模型逐篇归类</span></div>
            {topicTotal > 0 ? <div className="space-y-3">{topics.map(topic => <div key={topic.label}><div className="mb-1.5 flex items-center justify-between gap-2 text-xs"><span className="break-words text-cyber-text-primary">{topic.label}</span><span className="shrink-0 tabular-nums text-cyber-text-secondary">{topic.count} 篇 · {(topic.count/topicTotal*100).toFixed(0)}%</span></div><div aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-cyber-bg-secondary"><div className="h-full rounded-full bg-primary/75" style={{width:`${topic.count/topicTotal*100}%`}} /></div></div>)}<p className="pt-1 text-[11px] leading-5 text-cyber-text-secondary">仅代表本次 {topicTotal} 篇分析样本，非全账号内容占比。</p></div> : <div className="flex min-h-36 flex-col items-center justify-center gap-2 text-center text-xs leading-6 text-cyber-text-secondary"><Layers3 aria-hidden="true" className="h-6 w-6 opacity-50" /><p>该版本未记录逐篇主题分类<br />更新分析后展示真实样本分布</p></div>}
          </div>
          <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">{dimensions.map(({key: dimensionKey,label,Icon}) => {
            const value=snapshot[dimensionKey]
            return <button key={dimensionKey} type="button" aria-pressed={dimension === dimensionKey} aria-controls={`${id}-detail`} onClick={() => setDimension(dimensionKey)} className={`flex min-h-36 min-w-0 flex-col items-start rounded-lg border p-4 text-left transition-colors ${dimensionKey === 'audience' ? 'sm:col-span-2' : ''} ${focus} ${dimension === dimensionKey ? 'border-primary/40 bg-primary/5' : 'border-cyber-border-subtle bg-cyber-bg-panel hover:bg-cyber-bg-secondary/60'}`}>
              <span className="mb-3 flex w-full items-center justify-between gap-2 text-xs font-medium text-cyber-text-secondary"><span className="flex items-center gap-2"><Icon aria-hidden="true" className="h-4 w-4" />{label}</span><ArrowUpRight aria-hidden="true" className={`h-3.5 w-3.5 ${dimension === dimensionKey ? 'text-primary' : 'opacity-40'}`} /></span>
              <span className="line-clamp-2 break-words text-sm font-medium leading-6 text-cyber-text-primary">{excerpt(value)}</span>
              {!!value.labels?.length && <span className="mt-3 flex flex-wrap gap-1.5">{value.labels.map((tag,i) => <span key={`${tag}-${i}`} className="rounded bg-cyber-bg-secondary px-2 py-0.5 text-[11px] text-cyber-text-secondary">{tag}</span>)}</span>}
              {dimensionKey === 'audience' && <span className="mt-auto pt-2 text-[11px] text-cyber-text-secondary">内容推测，非粉丝画像</span>}
            </button>
          })}</div>
        </div>
        {finding && <div id={`${id}-detail`} className="min-w-0 rounded-lg border border-cyber-border-subtle bg-cyber-bg-secondary/40 px-4">
          <details key={`${snapshot.id}-${dimension}`}><summary className={`flex min-h-12 cursor-pointer flex-wrap items-center justify-between gap-2 py-3 text-xs text-cyber-text-secondary ${focus}`}><span><strong className="font-medium text-cyber-text-primary">{current.label}</strong> · 分析详情与依据（{finding.evidence.length}）</span><span>展开查看</span></summary><div className="grid gap-4 border-t border-cyber-border-subtle py-4 lg:grid-cols-2"><div><p className="mb-2 text-xs text-cyber-text-secondary">完整分析 · 未经人工核验</p><p className="whitespace-pre-wrap break-words text-sm leading-7 text-cyber-text-primary">{finding.text}</p></div><Evidence key={`${snapshot.id}-${dimension}`} items={finding.evidence} /></div></details>
        </div>}
        <details className="text-xs leading-6 text-cyber-text-secondary"><summary className={`min-h-10 cursor-pointer py-2 ${focus}`}>输入范围与分析限制</summary><div className="space-y-1 rounded-lg bg-cyber-bg-secondary/50 p-3"><p>{date(snapshot.scope.start)} — {date(snapshot.scope.end)}</p><p>{snapshot.scope.selection}；排除 {snapshot.scope.excluded} 篇{snapshot.scope.scan_truncated ? '；扫描范围已达5000篇上限' : ''}。</p><p>{snapshot.scope.material_level}</p><ul className="list-inside list-disc">{snapshot.limitations.map((line,i) => <li key={i}>{line}</li>)}</ul><p className="break-all">模型：{snapshot.model} · 版本：{snapshot.version}<br />输入 SHA-256：{snapshot.input_sha256}</p><p>显示最近 {data?.history_limit} 份分析记录，更早记录仍保留。</p></div></details>
      </>}
    </div>
  </section>
}
