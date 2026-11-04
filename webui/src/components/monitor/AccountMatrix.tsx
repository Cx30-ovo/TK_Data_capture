import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Layers3, Settings2, UsersRound, ArrowUpRight, Check, Radio, Sparkles } from 'lucide-react'
import { accountMatrixApi, type AccountRole, type MatrixAccount, type MatrixDraft } from '@/lib/accountMatrix'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AccountProfileEntry } from './AccountProfilePanel'

const roles: Record<AccountRole, string> = { unassigned: '待分类', owned: '自有账号', competitor: '竞品账号' }
const roleTone: Record<AccountRole, string> = { owned: 'bg-primary/10 text-primary', competitor: 'bg-status-warning/10 text-status-warning', unassigned: 'bg-cyber-bg-tertiary text-cyber-text-secondary' }
const selectStyle = 'min-h-11 w-full rounded-md border border-cyber-border-subtle bg-cyber-bg-panel px-3 text-sm text-cyber-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary'
const message = (error: unknown) => {
  const value = error as { response?: { data?: { detail?: unknown } }; message?: string }
  return typeof value.response?.data?.detail === 'string' ? value.response.data.detail : value.message || '暂不可用，请稍后重试'
}

function AssignmentEditor({ account, accounts, version, onDone, onCancel }: {
  account: MatrixAccount; accounts: MatrixAccount[]; version: number; onDone: () => void; onCancel: () => void
}) {
  const client = useQueryClient()
  // Capture opening version; refreshed data must not silently overwrite another edit.
  const [draft, setDraft] = useState<MatrixDraft>({ expected_version: version,
    identity_sha256: account.identity_sha256, role: account.role, group: account.group,
    competitor_ids: account.competitor_ids })
  const save = useMutation({ mutationFn: () => accountMatrixApi.save(account.id, draft),
    onSuccess: data => { client.setQueryData(['accountMatrix'], data); onDone() } })
  const competitors = accounts.filter(a => a.role === 'competitor' && a.id !== account.id)
  return <form aria-label={`编辑矩阵 · ${account.display_name}`} className="space-y-4 rounded-xl border border-primary/40 bg-cyber-bg-panel p-4" onSubmit={event => { event.preventDefault(); save.mutate() }}>
    <h3 className="text-base font-semibold">业务归属 · {account.display_name || `账号 ${account.id}`}</h3>
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="space-y-2 text-sm"><span className="block">账号身份</span><select aria-label="账号身份" className={selectStyle} value={draft.role} disabled={save.isPending} onChange={event => setDraft({ ...draft, role: event.target.value as AccountRole, competitor_ids: [] })}>{Object.entries(roles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="space-y-2 text-sm"><span className="block">业务分组 · 模型生成</span><p className="rounded-md bg-cyber-bg-tertiary p-3">{account.group || '尚未生成'}</p><p className="text-xs text-cyber-text-muted">在业务详情中生成或更新；无需手动填写。</p></div>
    </div>
    {draft.role === 'owned' && <fieldset className="rounded-lg border border-cyber-border-subtle p-3"><legend className="px-1 text-sm font-medium">关联竞品</legend><p className="mb-2 text-xs text-cyber-text-secondary">先将其他账号标记为竞品，再选择关联。关联关系仅用于账号管理。</p>
      {competitors.length ? competitors.map(item => <label key={item.id} className="flex min-h-11 cursor-pointer items-center gap-3 break-all text-sm"><input type="checkbox" className="h-4 w-4 accent-primary" checked={draft.competitor_ids.includes(item.id)} disabled={save.isPending} onChange={event => setDraft({ ...draft, competitor_ids: event.target.checked ? [...draft.competitor_ids, item.id] : draft.competitor_ids.filter(id => id !== item.id) })} />{item.display_name || `账号 ${item.id}`}</label>) : <p className="py-2 text-sm text-cyber-text-muted">暂无已分类的竞品账号。</p>}
    </fieldset>}
    {save.isError && <p role="alert" className="break-words text-sm text-status-error">{message(save.error)}</p>}
    <div className="flex flex-wrap gap-2"><Button type="submit" className="min-h-11" disabled={save.isPending}>{save.isPending ? '正在保存…' : '保存业务信息'}</Button><Button type="button" variant="outline" className="min-h-11" disabled={save.isPending} onClick={onCancel}>取消</Button></div>
    <p className="text-xs text-cyber-text-muted">仅保存业务信息，不触发采集、不改变监控频率。</p>
  </form>
}

function ModelGrouping({ account, onBusy }: { account: MatrixAccount; onBusy: (busy: boolean) => void }) {
  const client = useQueryClient()
  const model = useQuery({ queryKey: ['accountGroupModelStatus'], queryFn: accountMatrixApi.modelStatus, retry: false })
  const inference = useMutation({ mutationFn: () => accountMatrixApi.infer(account.id),
    onMutate: () => onBusy(true),
    onSuccess: result => { if (result.matrix) client.setQueryData(['accountMatrix'], result.matrix) },
    onSettled: () => onBusy(false) })
  const result = account.group_inference
  return <section aria-label="模型业务分组" className="space-y-2 rounded-xl border border-cyber-border-subtle bg-cyber-bg-panel p-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><div className="min-w-0 flex-1"><h3 className="flex items-center gap-2 text-xs font-medium text-cyber-text-secondary"><Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />业务分组 · 模型生成</h3><p className="mt-2 break-words text-base font-semibold leading-7">{account.group || '尚未生成'}</p></div><Button className="min-h-11 shrink-0" variant="outline" disabled={inference.isPending || !model.data?.available} onClick={() => inference.mutate()}>{inference.isPending ? '模型正在生成…' : result ? '更新模型分组' : '生成业务分组'}</Button></div>
    {(model.isError || !model.data?.available) && <p className="text-xs text-cyber-text-secondary">{model.isError ? '模型状态暂不可用' : model.data?.reason || '正在读取模型状态…'}</p>}
    {inference.isError && <p role="alert" className="text-sm text-status-error">{message(inference.error)}</p>}
    {result && <details className="text-cyber-text-secondary"><summary className="min-h-11 cursor-pointer py-3 text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary">查看推断依据与限制</summary><div className="space-y-3 border-t border-cyber-border-subtle pt-3"><p className="text-sm leading-6">{result.rationale}</p><p className="text-xs">使用模型：{model.data?.model || result.model} · 点击更新后调用，失败保留已有分组。</p><p className="text-xs">{result.scope} · {result.generated_at ? new Date(result.generated_at * 1000).toLocaleString('zh-CN') : ''}</p><ul className="space-y-2 text-sm">{result.evidence.map(e => <li key={e.post_id} className="break-words border-l-2 border-primary pl-3">{e.snippet}<span className="block break-all text-xs">{e.post_id} · {e.field}</span></li>)}</ul><ul className="list-disc pl-5 text-sm">{result.limitations.map((l,i) => <li key={i}>{l}</li>)}</ul><p className="break-all text-xs">输入 SHA：{result.input_sha256}</p></div></details>}
  </section>
}

export function AccountMatrix({ onOpenSettings }: { onOpenSettings: () => void }) {
  const query = useQuery({ queryKey: ['accountMatrix'], queryFn: accountMatrixApi.read, refetchOnWindowFocus: false })
  const [search, setSearch] = useState('')
  const [role, setRole] = useState('all')
  const [group, setGroup] = useState('all')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)
  const [generating, setGenerating] = useState(false)
  const accounts = query.data?.accounts || []
  const groups = [...new Set(accounts.map(a => a.group).filter(Boolean))].sort()
  const filtered = accounts.filter(a => (role === 'all' || a.role === role) &&
    (group === 'all' || (group === 'ungrouped' ? !a.group : `group:${a.group}` === group)) &&
    `${a.display_name} ${a.id}`.toLowerCase().includes(search.trim().toLowerCase()))
  const selected = accounts.find(a => a.id === selectedId)
  const names = new Map(accounts.map(a => [a.id, a.display_name || `账号 ${a.id}`]))
  return <div className="space-y-5 text-cyber-text-primary">
    <header className="workspace-panel flex flex-wrap items-center justify-between gap-4 p-5"><div className="min-w-0"><p className="mb-2 flex items-center gap-2 text-sm text-cyber-text-secondary"><Layers3 className="h-4 w-4" aria-hidden="true" />内容决策工作台</p><h1 className="text-2xl font-semibold">账号矩阵</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-cyber-text-secondary">管理自有账号、竞品与业务分组，查看已采集作品的统计档案。</p></div><Button className="min-h-11" variant="outline" onClick={onOpenSettings}><Settings2 className="h-4 w-4" aria-hidden="true" />添加账号与采集设置</Button></header>
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-cyber-border-subtle bg-cyber-border-subtle lg:grid-cols-4">{[['全部账号', accounts.length], ['自有账号', accounts.filter(a => a.role === 'owned').length], ['竞品账号', accounts.filter(a => a.role === 'competitor').length], ['待分类', accounts.filter(a => a.role === 'unassigned').length]].map(([label, count]) => <div key={label} className="flex items-center justify-between gap-3 bg-cyber-bg-panel px-4 py-5 sm:px-6"><p className="text-sm text-cyber-text-secondary">{label}</p><p className="text-2xl font-semibold tabular-nums tracking-tight">{query.isPending || query.isError ? '—' : count}</p></div>)}</div>
    <div className="workspace-panel space-y-4 p-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="space-y-1 text-sm"><span className="block">搜索账号</span><Input aria-label="搜索矩阵账号" className="min-h-11" placeholder="名称或账号编号" value={search} onChange={e => setSearch(e.target.value)} /></label>
        <label className="space-y-1 text-sm"><span className="block">身份筛选</span><select aria-label="身份筛选" className={selectStyle} value={role} onChange={e => setRole(e.target.value)}><option value="all">全部身份</option>{Object.entries(roles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="space-y-1 text-sm"><span className="block">分组筛选</span><select aria-label="分组筛选" className={selectStyle} value={group} onChange={e => setGroup(e.target.value)}><option value="all">全部分组</option><option value="ungrouped">未分组</option>{groups.map(g => <option key={g} value={`group:${g}`}>{g}</option>)}</select></label>
      </div>
      <Button variant="outline" className="min-h-11" disabled={editing || query.isFetching} onClick={() => query.refetch()}>重新读取矩阵</Button>
      {query.isPending ? <p role="status" className="py-6">正在读取账号矩阵…</p> : query.isError ? <div role="alert" className="space-y-3 py-6"><p>{message(query.error)}</p><Button variant="outline" onClick={() => query.refetch()}>重新读取</Button></div> : <>
        <p className="text-xs text-cyber-text-secondary">显示 {filtered.length} / {accounts.length} 个账号；身份与竞品关系人工设置，业务分组由模型生成。</p>
        {!filtered.length && <div className="py-10 text-center"><UsersRound className="mx-auto mb-3 h-8 w-8 text-cyber-text-muted" aria-hidden="true" /><p>{accounts.length ? '没有符合筛选条件的账号' : '暂无已添加账号'}</p><p className="mt-2 text-sm text-cyber-text-secondary">可在采集设置中添加账号，默认待分类。</p></div>}
        <div className="grid auto-rows-fr gap-4 md:grid-cols-2 xl:grid-cols-3">{filtered.map(account => <article key={account.id} className={`flex min-w-0 flex-col rounded-xl border p-5 transition-colors motion-reduce:transition-none ${selectedId === account.id ? 'border-primary bg-primary/5 ring-1 ring-primary/20' : 'border-cyber-border-subtle bg-cyber-bg-panel hover:border-primary/40'}`}>
          <div className="flex items-start gap-3"><div aria-hidden="true" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-lg font-semibold text-primary">{(account.display_name || String(account.id)).slice(0, 1)}</div><div className="min-w-0 flex-1"><h2 className="break-words text-lg font-semibold">{account.display_name || `账号 ${account.id}`}</h2><p className="mt-1 text-xs text-cyber-text-secondary">{account.platform === 'dy' ? '抖音' : account.platform} · #{account.id}</p></div>{selectedId === account.id && <Check aria-label="当前选中" className="h-5 w-5 shrink-0 text-primary" />}</div>
          <div className="mt-4 flex flex-wrap gap-2"><span className={`rounded-md px-2 py-1 text-xs font-medium ${roleTone[account.role]}`}>{roles[account.role]}</span><span className="max-w-full break-words rounded-md bg-cyber-bg-tertiary px-2 py-1 text-xs text-cyber-text-secondary">{account.group || '未分组'}</span></div>
          <dl className="my-4 grid grid-cols-2 gap-3 rounded-lg bg-cyber-bg-secondary p-3 text-sm"><div><dt className="text-xs text-cyber-text-secondary">已采集有效作品</dt><dd className="mt-1 text-2xl font-semibold tabular-nums">{account.posts}</dd></div><div><dt className="text-xs text-cyber-text-secondary">有观测作品</dt><dd className="mt-1 text-2xl font-semibold tabular-nums">{account.observed_posts}</dd></div></dl>
          <p className="flex flex-wrap items-center gap-2 text-xs text-cyber-text-secondary"><Radio aria-hidden="true" className={`h-3.5 w-3.5 ${account.enabled ? 'text-status-success' : ''}`} />{account.enabled ? '发现已启用' : '发现已暂停'}<span>·</span>{account.snapshots_paused ? '快照已暂停' : '快照按任务执行'}</p><p className="mt-2 text-xs leading-5 text-cyber-text-secondary">最近作品：{account.latest_published_at ? new Date(account.latest_published_at * 1000).toLocaleString('zh-CN') : '暂无'}</p>
          {account.role === 'owned' && <p className="mt-2 break-words text-sm">关联竞品：{account.competitor_ids.map(id => names.get(id)).join('、') || '未设置'}</p>}{account.unavailable_competitor_ids.length > 0 && <p className="mt-2 text-sm text-status-warning">{account.unavailable_competitor_ids.length} 个关联已失效，请编辑确认。</p>}
          <div className="mt-auto pt-4"><Button variant="outline" className="min-h-11 w-full justify-between" disabled={editing || generating} aria-pressed={selectedId === account.id} onClick={() => { setSelectedId(account.id); setSaved(false) }}>查看与管理<ArrowUpRight className="h-4 w-4" aria-hidden="true" /></Button></div>
        </article>)}</div>
      </>}
    </div>
    {selected && !query.isError && <section aria-label="账号业务详情" className="workspace-panel min-w-0 space-y-4 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="break-all text-lg font-semibold">{selected.display_name || `账号 ${selected.id}`} · 业务详情</h2>{!editing && <Button variant="outline" className="min-h-11" onClick={() => { setEditing(true); setSaved(false) }}>编辑业务信息</Button>}</div>
      {saved && <span role="status" className="sr-only">业务信息已保存</span>}
      {!editing && <ModelGrouping key={`group-${selected.id}`} account={selected} onBusy={setGenerating} />}
      {editing && <AssignmentEditor key={`${selected.id}-${selected.identity_sha256}`} account={selected} accounts={accounts} version={query.data!.version} onDone={() => { setEditing(false); setSaved(true) }} onCancel={() => setEditing(false)} />}
      <AccountProfileEntry key={`profile-${selected.id}`} accountId={selected.id} name={selected.display_name} />
    </section>}
    <details className="rounded-xl border border-cyber-border-subtle px-4 text-sm text-cyber-text-secondary"><summary className="min-h-11 cursor-pointer py-3 font-medium">数据边界与说明</summary><ul className="mb-4 list-disc space-y-2 pl-5">{(query.data?.limits || ['只读取已采集数据；业务分类不会触发采集。']).map(limit => <li key={limit}>{limit}</li>)}<li>业务分组已接入模型推断；统计档案不等于风格训练或热点预测结果。</li></ul></details>
  </div>
}
