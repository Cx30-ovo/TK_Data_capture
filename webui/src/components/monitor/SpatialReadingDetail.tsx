import { useState } from 'react'
import { ArrowUpRight, Clock3, Flame, Heart, MessageCircle, Share2, Sparkles } from 'lucide-react'
import type { DouyinHotRankItem, MonitorDashboardPost } from '@/lib/api'
import { presentPost } from '@/lib/postPresentation'
import { PostEditorialCorrection, PostEditorialEvidence, PostEditorialTags } from './PostEditorialTags'
import { PostComments } from './PostComments'

export type ReadingSignal = { id: string; title: string; kind: 'post'; post: MonitorDashboardPost }
  | { id: string; title: string; kind: 'rank'; rank: DouyinHotRankItem }
const compact = (value: number | undefined) => value === undefined ? '—' : value >= 10000 ? `${(value / 10000).toFixed(1)}万` : value.toLocaleString('zh-CN')
const stamp = (value: number) => value ? new Date(value * 1000).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '时间未知'

export function SpatialReadingDetail({ signal, post, onOpenData, onOpenTopics }: {
  signal: ReadingSignal; post?: MonitorDashboardPost; onOpenData: (id: string) => void; onOpenTopics: () => void
}) {
  const [titleExpanded, setTitleExpanded] = useState(false)
  const work = signal.kind === 'post' ? post || signal.post : undefined
  const display = work ? presentPost(work) : undefined
  const title = display?.title || signal.title
  const snapshot = work ? [...work.snapshots].sort((a, b) => b.captured_at - a.captured_at)[0] : undefined
  const metrics = signal.kind === 'rank'
    ? [{ icon: Flame, label: '平台热度', value: signal.rank.hot_value }, { icon: Sparkles, label: '相关视频', value: signal.rank.video_count }]
    : [{ icon: Heart, label: '点赞', value: snapshot?.liked_count }, { icon: MessageCircle, label: '评论', value: snapshot?.comment_count }, { icon: Share2, label: '分享', value: snapshot?.share_count }]
  return <div className="spatial-detail-reader" role="region" aria-label="作品阅读正文" tabIndex={0}>
    <div className="spatial-reader-header">
      <div className="spatial-detail-meta"><span>{work ? '抖音 · 账号采集' : '抖音 · 平台热榜'}</span><span><Clock3 aria-hidden="true" />{stamp(work?.create_time || (signal.kind === 'rank' ? signal.rank.event_time : 0))}</span></div>
      <h2 id="spatial-reading-title" className={titleExpanded ? 'is-expanded' : ''}>{title}</h2>
      {title.length > 60 && <button className="spatial-title-expand" aria-expanded={titleExpanded} onClick={() => setTitleExpanded(value => !value)}>{titleExpanded ? '收起标题' : '展开完整标题'}</button>}
      {work && <PostEditorialTags post={work} />}
      <div className="spatial-detail-metrics">{metrics.map(metric => <div key={metric.label}><metric.icon aria-hidden="true" /><strong>{compact(metric.value)}</strong><span>{metric.label}</span></div>)}</div>
    </div>
    <div className="spatial-reader-copy">
      {display?.body && <p className="spatial-detail-copy">{display.body}</p>}
      {!!display?.topics.length && <div className="spatial-reading-topics" aria-label="作品话题">{display.topics.map(topic => <span key={topic}>#{topic}</span>)}</div>}
      {work && <PostEditorialEvidence post={work} />}
      {work && <PostEditorialCorrection post={work} />}
      {work && <PostComments key={work.aweme_id} awemeId={work.aweme_id} />}
      {work ? <details className="spatial-original-copy"><summary>查看原始文案与署名</summary><p>{work.title || '暂无标题'}</p>{work.desc && work.desc !== work.title && <p>{work.desc}</p>}<small>作品 ID：{work.aweme_id}</small></details>
        : <p className="spatial-detail-copy">这条线索来自平台热榜，代表传播热度。请核验原始发布、时间与上下文，再进行编辑判断。</p>}
      <div className="spatial-detail-actions"><a href={work ? work.canonical_url : signal.kind === 'rank' ? signal.rank.search_url : undefined} target="_blank" rel="noopener noreferrer">打开{work ? '原文' : '平台搜索'}<ArrowUpRight aria-hidden="true" /></a><button onClick={() => work ? onOpenData(work.aweme_id) : onOpenTopics()}><Sparkles aria-hidden="true" />{work ? '进入内容分析' : '进入话题监控'}</button></div>
      <p className="spatial-detail-note">{work ? snapshot ? `最新快照 ${stamp(snapshot.captured_at)} · 数据来自实际采集` : '当前尚无互动快照，缺失值以 — 表示。' : '平台热度信号不等同于已核验事实。'}</p>
    </div>
  </div>
}
