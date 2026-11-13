import type { ClassificationHealth as Health } from '@/lib/api'
import { pendingReasonLabels } from './PostEditorialTags'

const timeLabel = (value: number | null) => value ? new Date(value * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '尚无缓存更新时间'

export function ClassificationHealth({ health, accountName, reason, onReasonChange }: { health?: Health; accountName: string; reason: string; onReasonChange: (value: string) => void }) {
  if (!health) return null
  const rate = (count: number) => health.total ? `${Math.round(count / health.total * 100)}%` : '—'
  const workerState = { not_started: '后台缓存未启动', rebuilding: '历史分批重算中', incremental: '增量检查中', idle: '等待新增或变化作品', error: '缓存更新异常' }[health.worker.state]
  return <details className="classification-health">
    <summary><strong>分类健康</strong><span>{health.pending_posts ? `${health.pending_posts} 项待判定` : health.total ? '已覆盖全部加载作品' : '暂无作品'}</span><small>展开</small></summary>
    <div className="classification-health-body">
      <p>{accountName} · 已加载 {health.total} 项；覆盖率不代表准确率。</p>
      <dl><div><dt>频道覆盖</dt><dd>{rate(health.channel_resolved)}<small>{health.channel_resolved} / {health.total}</small></dd></div><div><dt>地域覆盖</dt><dd>{rate(health.region_resolved)}<small>{health.region_resolved} / {health.total}</small></dd></div></dl>
      <div className="classification-reason-buttons" role="group" aria-label="按待判定原因筛选">{Object.entries(pendingReasonLabels).map(([code, label]) => <button key={code} aria-pressed={reason === code} onClick={() => onReasonChange(reason === code ? '' : code)}><span>{label}</span><strong>{health.pending_reasons[code] || 0}</strong></button>)}</div>
      <p>原因按字段计数，同一作品可能涉及两项。</p>
      <details className="classification-cache-status"><summary>版本与更新状态</summary><p>{health.rule_version}</p><p>当前账号缓存 {health.cached_posts} / {health.total}；{timeLabel(health.last_updated_at)}</p><p>全部账号后台：{workerState}。本轮已扫描 {health.worker.scanned}，重算 {health.worker.recomputed}，复用 {health.worker.reused}。</p><p>本轮完成：{timeLabel(health.worker.last_completed_at)}</p>{health.worker.last_error && <p role="status">{health.worker.last_error}</p>}<p>缓存未就绪时使用当前规则即时判定，不展示过期分类。</p></details>
    </div>
  </details>
}
