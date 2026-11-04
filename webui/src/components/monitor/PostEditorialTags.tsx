import type { MonitorDashboardPost } from '@/lib/api'

export const editorialChannels = ['推荐', '时政', '民生', '经济', '科技', '教育', '健康', '体育', '文旅', '文娱', '三农', '法治', '政策文件', '应急', '环境生态', '待判定']
export const postChannel = (channel?: string) => channel && channel !== '综合' ? channel : '待判定'
export const editorialRegions = ['全部', '本地', '本省', '国内', '国际', '待判定']
export const regionDescription = (region: string) => ({ 本地: '厦门市', 本省: '福建省级内容及省内其他城市', 国内: '福建省外国内地区（含港澳台）', 国际: '境外地区', 待判定: '现有内容不足以确定主要地域' }[region] || region)

export function PostEditorialTags({ post }: { post: MonitorDashboardPost }) {
  const region = post.region || '待判定'
  const review = post.tag_status === 'insufficient' ? '内容不足'
    : post.tag_status === 'pending' ? 'AI 复核中'
    : post.tag_status === 'retry' ? 'AI 待重试'
    : post.tag_status === 'deferred' ? '等待 AI 复核'
    : post.tag_status === 'ai_unavailable' ? 'AI 未启用'
    : post.tag_status === 'uncertain' ? '需核实'
    : post.tag_method === 'rules_ai' ? 'AI 已复核' : ''
  return <span className="post-editorial-tags"><span className="post-channel-tag" title={`根据标题与正文${post.tag_method === 'rules_ai' ? '规则初筛及 AI 复核' : '规则初筛'}${post.channel_evidence ? ` · 依据：${post.channel_evidence}` : ''}`}>{postChannel(post.channel)}</span><span className="post-region-tag" title={`${regionDescription(region)}${post.region_evidence ? ` · 依据：${post.region_evidence}` : ''}`}>{region}</span>{review && <span className="post-review-tag" data-state={post.tag_status} title={post.tag_reason || '初筛有歧义的标签由 AI 复核；未完成时展示初筛结果。'}>{review}</span>}</span>
}

export function PostEditorialEvidence({ post }: { post: MonitorDashboardPost }) {
  const ai = post.tag_method === 'rules_ai'
  const confidence = Object.entries(post.tag_confidence || {}).filter(([, value]) => Number.isFinite(value))
  const summary = post.tag_status === 'insufficient' ? '内容不足，暂不能判定'
    : post.tag_status === 'pending' ? '初筛完成，AI 正在复核歧义'
    : post.tag_status === 'retry' ? '暂用初筛结果，等待 AI 重试'
    : post.tag_status === 'uncertain' ? '已复核，部分标签仍需核实'
    : ai ? '已通过规则初筛与 AI 复核' : '按标题与正文规则归类'
  return <details className="post-editorial-evidence"><summary><strong>标签判定</strong><span>{summary}</span><small>查看依据</small></summary><div className="post-evidence-body">{post.channel_evidence && <p><span>频道依据</span>{post.channel_evidence}</p>}{post.region_evidence && <p><span>地域依据</span>{post.region_evidence}</p>}{post.tag_reason && <p>{post.tag_reason}</p>}{confidence.length > 0 && <small>模型自评：{confidence.map(([field, value]) => `${field === 'channel' ? '频道' : '地域'} ${Math.round(value * 100)}%`).join(' · ')}，仅供复核参考</small>}{post.tag_status === 'insufficient' && <p>缺少可分析的标题正文，补充内容后会重新判定。</p>}</div></details>
}
