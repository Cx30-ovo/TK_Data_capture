import { useId, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { StatePanel } from '@/components/ui/state-panel'
import { fetchAccountProfile, type ProfileEvidence } from '@/lib/accountProfiles'
import { AccountStyleProfile } from './AccountStyleProfile'
import { BarChart3, Database, Hash, Quote, ArrowUpRight, FileText, CalendarDays, AlignLeft, ChevronLeft, ChevronRight, ScanText } from 'lucide-react'

type ExtractionEvidence = ProfileEvidence & { extracted_title: string; word_count: number; method: string }
const focusStyle = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary'

function SourceMeta({ item }: { item: ProfileEvidence }) {
  return <details className="mt-3 border-t border-cyber-border-subtle pt-1 text-xs text-cyber-text-secondary">
    <summary className={`min-h-11 cursor-pointer py-3 ${focusStyle}`}>来源信息 · {date(item.published_at)}</summary>
    <dl className="grid min-w-0 gap-2 pb-3"><div><dt className="inline">作品 ID：</dt><dd className="inline break-all font-mono">{item.post_id}</dd></div><div><dt className="inline">来源字段：</dt><dd className="inline font-mono">{item.field}</dd></div></dl>
  </details>
}

function SampleNavigation({ index, count, onChange, label }: { index: number; count: number; onChange: (index: number) => void; label: string }) {
  return <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cyber-border-subtle pb-3">
    <span aria-live="polite" aria-atomic="true" className="text-xs text-cyber-text-secondary">样本 <strong className="font-semibold text-cyber-text-primary">{index + 1}</strong> / {count}</span>
    <div className="flex gap-2"><Button type="button" variant="outline" className="min-h-11 px-3" aria-label={`${label}上一条`} disabled={index === 0} onClick={() => onChange(index - 1)}><ChevronLeft aria-hidden="true" className="h-4 w-4" /><span className="text-xs">上一条</span></Button><Button type="button" variant="outline" className="min-h-11 px-3" aria-label={`${label}下一条`} disabled={index >= count - 1} onClick={() => onChange(index + 1)}><span className="text-xs">下一条</span><ChevronRight aria-hidden="true" className="h-4 w-4" /></Button></div>
  </div>
}

function HighlightedEvidence({ text, signal, tag }: { text: string; signal?: string; tag?: string }) {
  const matches: { start: number; end: number }[] = []
  if (tag) {
    // Match complete hashtag tokens, not a prefix such as #厦门 in #厦门新闻.
    for (const match of text.matchAll(/#([^\s#，。！？、；：]+)/gu)) {
      if (match[1] === tag) matches.push({ start: match.index!, end: match.index! + match[0].length })
    }
  } else {
    const pattern = { question: /[?？]/gu, exclamation: /[!！]/gu, numbers: /\d+/gu, quote: /[“”‘’"「」『』]/gu }[signal || '']
    if (pattern) for (const match of text.matchAll(pattern)) matches.push({ start: match.index!, end: match.index! + match[0].length })
  }
  let cursor = 0
  const parts = matches.map(({ start, end }) => {
    const prefix = text.slice(cursor, start)
    cursor = end
    return <span key={start}>{prefix}<mark className="rounded bg-primary/15 px-0.5 font-semibold text-cyber-text-primary underline decoration-primary decoration-2 underline-offset-4">{text.slice(start, end)}</mark></span>
  })
  return <>{parts}{text.slice(cursor)}</>
}

function TitleExtractionReview({ items }: { items: ExtractionEvidence[] }) {
  const [position, setPosition] = useState(0)
  const index = Math.min(position, Math.max(0, items.length - 1))
  const item = items[index]
  if (!item) return <p className="py-3 text-sm text-cyber-text-secondary">暂无可核对的标题样本。</p>
  const start = item.snippet.indexOf(item.extracted_title)
  const prefix = start >= 0 ? item.snippet.slice(0, start) : ''
  const suffix = start >= 0 ? item.snippet.slice(start + item.extracted_title.length) : ''
  return <div className="space-y-3 rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary p-3 sm:p-4">
    <SampleNavigation index={index} count={items.length} onChange={setPosition} label="标题核对" />
    <div className="rounded-lg border border-primary/20 bg-cyber-bg-panel p-3 sm:p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><span className="flex items-center gap-2 text-xs font-medium text-primary"><ScanText aria-hidden="true" className="h-4 w-4" />清理后标题</span><span className="rounded-md bg-primary/10 px-2 py-1 text-sm font-semibold tabular-nums text-primary">{item.word_count} 字</span></div>
      <p tabIndex={0} aria-label="清理后标题全文" className={`h-40 overflow-y-auto whitespace-pre-wrap break-words pr-2 text-sm leading-7 text-cyber-text-primary ${focusStyle}`}><span className="sr-only">提取标题句：</span>{item.extracted_title}</p>
    </div>
    <details className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel px-3">
      <summary className={`min-h-11 cursor-pointer py-3 text-xs text-cyber-text-secondary ${focusStyle}`}>对照原始文案{prefix || suffix ? ' · 已移除附加信息' : start >= 0 ? ' · 内容一致' : ' · 原文保留供核对'}</summary>
      {start >= 0 && (prefix || suffix) && <p className="mb-3 text-xs text-cyber-text-secondary">带删除线：清理时移除的附加内容；无删除线：保留的标题。</p>}
      <p tabIndex={0} aria-label="原始文案对照全文" className={`max-h-40 overflow-y-auto whitespace-pre-wrap break-words pb-3 pr-2 text-sm leading-7 ${focusStyle}`}>{start >= 0 ? <>{prefix && <del className="text-cyber-text-secondary decoration-status-warning">{prefix}</del>}{item.extracted_title}{suffix && <del className="text-cyber-text-secondary decoration-status-warning">{suffix}</del>}</> : item.snippet}</p>
    </details>
    <p className="text-xs leading-5 text-cyber-text-secondary">规则提取，未经人工核验 · 保留多句话，不做定长截断</p>
    <SourceMeta item={item} />
  </div>
}

function percentage(value: number, total: number) {
  return total > 0 ? `${(value / total * 100).toFixed(1)}%` : '—'
}

function CoverageBar({ label, count, total }: { label: string; count: number; total: number }) {
  return <div className="space-y-2"><div className="flex flex-wrap justify-between gap-2 text-sm"><span>{label}</span><span className="tabular-nums text-cyber-text-secondary">{count} 篇 <span className="ml-2 font-medium text-cyber-text-primary">{percentage(count, total)}</span></span></div><div aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-cyber-bg-tertiary"><div className="h-full rounded-full bg-primary/75" style={{ width: `${total ? Math.min(100, count / total * 100) : 0}%` }} /></div></div>
}

function date(value: number | null) {
  return value === null ? '暂无数据' : new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })
}

function Evidence({ items, signal, tag }: { items: ProfileEvidence[]; signal?: string; tag?: string }) {
  const [position, setPosition] = useState(0)
  if (!items.length) return null
  const index = Math.min(position, items.length - 1)
  const item = items[index]
  return <details className="mt-2 text-sm">
    <summary className={`min-h-11 cursor-pointer py-3 text-cyber-text-secondary ${focusStyle}`}>查看原文依据（{items.length}）</summary>
    <div className="space-y-3 rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary p-3">
      <SampleNavigation index={index} count={items.length} onChange={setPosition} label="原文依据" />
      <p className="text-xs text-cyber-text-secondary">原始发布文案 · 加粗下划线标出命中内容</p>
      <p tabIndex={0} aria-label="原文依据全文" className={`h-40 overflow-y-auto whitespace-pre-wrap break-words pr-2 text-sm leading-7 ${focusStyle}`}><HighlightedEvidence text={item.snippet} signal={signal} tag={tag} /></p>
      <SourceMeta item={item} />
    </div>
  </details>
}

export function AccountProfilePanel({ accountId }: { accountId: number }) {
  const [days, setDays] = useState(30)
  const id = useId()
  const query = useQuery({
    queryKey: ['accountProfile', accountId, days],
    queryFn: ({ signal }) => fetchAccountProfile(accountId, days, signal),
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  })
  const data = query.data
  const maxBin = Math.max(1, ...(data?.title_length.histogram.map(item => item.count) || []))
  const topBin = data?.title_length.histogram.reduce<{ label: string; count: number } | undefined>((best, bin) => !best || bin.count > best.count ? bin : best, undefined)
  return <section className="min-w-0 space-y-5 text-cyber-text-primary" aria-labelledby={id}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 id={id} className="flex items-center gap-2 text-lg font-semibold"><BarChart3 className="h-5 w-5 text-primary" aria-hidden="true" />账号档案</h2><p className="mt-1 text-sm text-cyber-text-secondary">了解发布节奏、标题习惯与常见话题</p></div>
      <Button variant="outline" className="min-h-11" disabled={query.isFetching} onClick={() => void query.refetch()}>更新统计</Button>
    </div>
    <div className="flex flex-wrap items-center gap-3">
      <label htmlFor={`${id}-days`} className="text-sm">发布时间窗口</label>
      <select id={`${id}-days`} value={days} onChange={event => setDays(Number(event.target.value))} className="min-h-11 rounded-md border border-cyber-border-subtle bg-cyber-bg-primary px-3 text-sm focus-visible:outline focus-visible:outline-2">
        {[7, 30, 90, 365].map(value => <option key={value} value={value}>最近 {value} 天</option>)}
      </select>
      <span className="text-xs text-cyber-text-secondary">本地统计 · 不触发采集</span>
    </div>
    <AccountStyleProfile key={`${accountId}-${days}`} accountId={accountId} days={days} />
    {query.isFetching && <p role="status" className="text-sm text-cyber-text-secondary">正在读取账号档案…</p>}
    {query.isError ? <div role="alert"><StatePanel variant="error" title="账号档案暂不可用" description="请检查账号是否仍存在，以及本地数据库是否可读；不会回退采集或调用模型。" /></div> : data ? <>
      <p className="break-words text-sm text-cyber-text-secondary">{data.account.display_name} · 截止 {date(data.window.end)} · 最近 {data.window.days} 天</p>
      {data.counts.truncated && <p role="status" className="text-sm text-status-warning">窗口内有 {data.counts.eligible} 篇有效作品，以下标题与观测统计仅取最新 {data.counts.sampled} 篇。</p>}
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { label: '窗口有效作品', value: `${data.counts.eligible}`, unit: '篇', Icon: FileText },
          { label: '标题句平均字数', value: data.title_length.mean ?? '—', unit: '字', Icon: AlignLeft },
          { label: '窗口日均作品', value: data.publication.posts_per_day, unit: '篇 / 天', Icon: CalendarDays },
          { label: '观测覆盖', value: percentage(data.coverage.observed_posts, data.counts.sampled), unit: `${data.coverage.observed_posts} / ${data.counts.sampled} 篇`, Icon: Database },
        ].map(({label, value, unit, Icon}) => <div key={label} className="flex min-h-28 min-w-0 flex-col justify-between rounded-xl border border-cyber-border-subtle bg-cyber-bg-panel p-4"><dt className="flex items-center justify-between gap-2 text-xs text-cyber-text-secondary">{label}<Icon className="h-4 w-4 shrink-0 text-primary/70" aria-hidden="true" /></dt><dd className="mt-3 break-words text-2xl font-semibold tabular-nums tracking-tight">{value}<span className="ml-2 text-xs font-normal tracking-normal text-cyber-text-secondary">{unit}</span></dd></div>)}
      </dl>
      {data.counts.sampled === 0 ? <StatePanel variant="empty" title="该窗口暂无已采集作品" description="可调整时间窗口；这里不会自动采集或生成示例档案。" /> : <>
        <div className="grid gap-4 lg:grid-cols-2">
          <section aria-label="标题长度模块" tabIndex={0} className={`min-w-0 space-y-4 rounded-xl border border-cyber-border-subtle bg-cyber-bg-panel p-4 lg:h-[560px] lg:overflow-y-auto ${focusStyle}`}><h3 className="flex min-h-6 items-center gap-2 font-medium"><BarChart3 className="h-4 w-4 text-primary" aria-hidden="true" />标题句长度分布</h3>
            <div className="flex flex-wrap items-end justify-between gap-3 rounded-lg bg-primary/5 p-3"><div><p className="text-xs text-cyber-text-secondary">最常用长度</p><p className="mt-1 text-xl font-semibold text-primary">{topBin?.count ? `${topBin.label} 字` : '暂无样本'}</p></div><p className="text-sm text-cyber-text-secondary">中位数 <span className="font-semibold text-cyber-text-primary">{data.title_length.median ?? '—'}</span> 字</p></div>
            {data.title_length.histogram.map(bin => <div key={bin.label}>
              <div className="mb-2 flex flex-wrap justify-between gap-2 text-sm"><span>{bin.label} 字</span><span className="tabular-nums">{bin.count} 篇 · {percentage(bin.count, data.title_length.sample_count)}</span></div>
              <div aria-hidden="true" className="h-2.5 overflow-hidden rounded-full bg-cyber-bg-tertiary"><div className={`h-full rounded-full ${bin === topBin ? 'bg-primary' : 'bg-primary/50'}`} style={{ width: `${bin.count / maxBin * 100}%` }} /></div>
            </div>)}
            <p className="text-xs leading-5 text-cyber-text-secondary">{data.title_length.sample_count} 篇标题样本 · 已去署名与标签 · 条长按最大数量缩放</p>
            <details className="min-w-0 text-sm"><summary className={`min-h-11 cursor-pointer py-3 ${focusStyle}`}>核对标题句提取（最新 {data.title_length.evidence.length} 条）</summary><TitleExtractionReview key={`${accountId}-${days}`} items={data.title_length.evidence} /></details>
          </section>
          <section aria-label="文案特征模块" tabIndex={0} className={`min-w-0 rounded-xl border border-cyber-border-subtle bg-cyber-bg-panel p-4 lg:h-[560px] lg:overflow-y-auto ${focusStyle}`}><h3 className="mb-3 flex min-h-6 items-center gap-2 font-medium"><Quote className="h-4 w-4 text-primary" aria-hidden="true" />文案表达特征</h3><p className="mb-3 text-xs text-cyber-text-muted">此处统计原始文案；同一文案可命中多项，比例不相加为 100%。</p>
            {data.signals.map(item => <div key={item.key} className="border-b border-cyber-border-subtle py-3 text-sm last:border-0">
              <CoverageBar label={item.label} count={item.count} total={data.counts.with_title} /><Evidence key={`${accountId}-${days}-${item.key}`} items={item.evidence} signal={item.key} />
            </div>)}
          </section>
        </div>
        <section className="min-w-0 rounded-xl border border-cyber-border-subtle bg-cyber-bg-panel p-4"><h3 className="mb-2 flex items-center gap-2 font-medium"><Hash className="h-4 w-4 text-primary" aria-hidden="true" />原始话题标签</h3><p className="mb-4 text-xs text-cyber-text-secondary">按作品覆盖数排序，最多 12 项；标签不是语义主题，单篇内重复标签只计一次。</p>
          {data.hashtags.length ? <><div className="flex flex-wrap gap-2">{data.hashtags.slice(0, 6).map(item => <span key={item.tag} className="max-w-full break-words rounded-lg bg-primary/5 px-3 py-2 text-sm text-primary">#{item.tag}<span className="ml-2 text-xs text-cyber-text-secondary">{item.post_count} 篇</span></span>)}</div><details className="mt-3"><summary className="flex min-h-11 cursor-pointer items-center gap-2 py-3 text-sm text-cyber-text-secondary">查看全部话题与依据（{data.hashtags.length}）<ArrowUpRight aria-hidden="true" className="h-4 w-4" /></summary><div className="grid items-start gap-x-6 sm:grid-cols-2">{data.hashtags.map((item, index) => <div key={item.tag} className="min-w-0 border-b border-cyber-border-subtle py-3"><CoverageBar label={`${String(index + 1).padStart(2, '0')} · #${item.tag}`} count={item.post_count} total={data.counts.with_title} /><Evidence key={`${accountId}-${days}-${item.tag}`} items={item.evidence} tag={item.tag} /></div>)}</div></details></> : <p className="text-sm text-cyber-text-secondary">文案中未发现话题标签，不能据此判断账号没有主题。</p>}
        </section>
        <details className="rounded-xl border border-cyber-border-subtle bg-cyber-bg-panel p-4"><summary className="min-h-11 cursor-pointer py-2 font-medium">观测覆盖详情 <span className="ml-2 text-sm font-normal text-cyber-text-secondary">{percentage(data.coverage.observed_posts, data.counts.sampled)}</span></summary><p className="my-4 text-sm text-cyber-text-secondary">有观测 {data.coverage.observed_posts} 篇，无观测 {data.coverage.without_observation} 篇；时间不一致观测 {data.coverage.invalid_observations} 条。</p>
          <CoverageBar label="已有有效时间观测" count={data.coverage.observed_posts} total={data.counts.sampled} />
          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">{data.coverage.lifecycle.map(item => <div key={item.stage} className="rounded-lg border border-cyber-border-subtle p-3"><CoverageBar label={`${item.stage} 有效窗口`} count={item.posts} total={data.counts.sampled} /></div>)}</div><p className="mt-4 text-xs text-cyber-text-muted">各阶段均以当前作品样本为分母；作品可能尚未到龄，低覆盖不代表表现差。</p>
        </details>
      </>}
      <details className="border-t border-cyber-border-subtle pt-3 text-sm"><summary className="min-h-11 cursor-pointer py-3 focus-visible:outline focus-visible:outline-2">口径、限制与输入指纹</summary>
        <ul className="list-disc space-y-2 pl-5 text-cyber-text-secondary">{data.limits.map(limit => <li key={limit}>{limit}</li>)}</ul>
        <p className="mt-3 leading-6 text-cyber-text-secondary">{data.title_length.rule} 无法提取 {data.title_length.excluded_count} 篇；非有效状态排除 {data.counts.excluded_status} 篇。样本发布时间：{date(data.publication.earliest)} 至 {date(data.publication.latest)}。</p>
        <p className="mt-3 break-all text-xs text-cyber-text-secondary">{data.version} · SHA-256 {data.input_sha256}</p>
      </details>
    </> : null}
  </section>
}

export function AccountProfileEntry({ accountId, name }: { accountId: number; name: string }) {
  const [open, setOpen] = useState(false)
  return <details className="min-w-0 rounded-xl border border-cyber-border-subtle p-4" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="min-h-11 cursor-pointer py-3 text-sm font-medium text-cyber-text-primary focus-visible:outline focus-visible:outline-2">查看账号档案 · {name}</summary>
    {open && <AccountProfilePanel accountId={accountId} />}
  </details>
}
