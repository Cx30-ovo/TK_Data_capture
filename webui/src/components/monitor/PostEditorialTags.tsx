import type { MonitorDashboardPost } from '@/lib/api'

export const editorialChannels = ['推荐', '时政', '民生', '经济', '科技', '教育', '健康', '体育', '文旅', '文娱', '三农', '法治', '政策文件', '应急', '环境生态', '待判定']
export const postChannel = (channel?: string) => channel && channel !== '综合' ? channel : '待判定'
export const editorialRegions = ['全部', '本地', '本省', '国内', '国际', '待判定']
export const pendingReasonLabels: Record<string, string> = { insufficient_clues: '没有有效线索', rule_conflict: '多个规则冲突', location_role_unclear: '地点角色不明确', lexicon_gap: '题材或地点词典未覆盖' }
export const regionDescription = (region: string) => ({ 本地: '厦门市', 本省: '福建省级内容及省内其他城市', 国内: '福建省外国内地区（含港澳台）', 国际: '境外地区', 待判定: '现有文案不足或存在地域冲突，暂不确定' }[region] || region)

export function PostEditorialTags({ post }: { post: MonitorDashboardPost }) {
  const region = post.region || '待判定'
  return <span className="post-editorial-tags"><span className="post-channel-tag" title={`${post.classification_mode === 'automatic_rules' ? '自动规则分类' : '历史分类，等待后端切换规则分类'}${post.channel_evidence ? ` · 依据：${post.channel_evidence}` : ''}`}>{postChannel(post.channel)}</span>{post.channel_subtopics?.slice(0, 2).map(label => <span className="post-subtopic-tag" key={label}>{label}</span>)}<span className="post-region-tag" title={`${regionDescription(region)}${post.region_evidence ? ` · 依据：${post.region_evidence}` : ''}`}>{region}</span></span>
}

export function PostEditorialEvidence({ post }: { post: MonitorDashboardPost }) {
  if (post.classification_mode !== 'automatic_rules') return <details className="post-editorial-evidence"><summary><strong>标签判定</strong><span>等待后端切换规则分类</span><small>查看说明</small></summary><div className="post-evidence-body"><p>当前后端仍返回历史分类。重启本地后端后，频道与地域将按当前自动规则重新计算。</p></div></details>
  const hits = post.tag_rule_hits || []
  const uncertain = postChannel(post.channel) === '待判定' || !post.region || post.region === '待判定'
  return <details className="post-editorial-evidence"><summary><strong>标签判定</strong><span>{uncertain ? '线索不足或冲突，部分标签待判定' : '自动规则分类'}</span><small>查看依据</small></summary><div className="post-evidence-body">
    {post.channel_evidence && <p><span>频道依据 · {post.channel_evidence.startsWith('#') ? '话题标签' : '文案'}</span>{post.channel_evidence}</p>}
    {post.region_evidence && <p><span>地域依据 · {post.region_evidence.startsWith('#') ? '话题标签' : '文案'}</span>{post.region_evidence}</p>}
    {post.tag_reason && <p>{post.tag_reason}</p>}
    {!!post.tag_pending_reasons?.length && <ul className="post-pending-reasons">{post.tag_pending_reasons.map(reason => <li key={reason.field}>{reason.field === 'channel' ? '频道' : '地域'}：{reason.label}</li>)}</ul>}
    {!!post.channel_subtopic_hits?.length && <details className="post-subtopic-evidence"><summary>细分标签依据 · {post.channel_subtopic_hits.length} 项</summary>{post.channel_subtopic_hits.map(hit => <p key={hit.label}><span>{hit.label} · {hit.snippet.startsWith('#') ? '话题标签' : '文案'}</span><q>{hit.snippet}</q><small>规则：{hit.rule_id}</small></p>)}</details>}
    {!!post.region_locations?.length && <details className="post-location-evidence"><summary>地点角色 · {post.region_locations.length} 条</summary><p>关联地点用于解释，不能代替事件发生地；来源和籍贯不参与地域得分。</p>{post.region_locations.map((place, index) => <p key={`${place.field}-${place.place}-${index}`}><span>{place.role_label} · {place.region} · {place.used ? '参与地域判定' : '不作事件地点依据'}</span><q>{place.snippet}</q><small>规则：{place.rule_id}</small></p>)}</details>}
    {hits.length > 0 && <details className="post-rule-evidence"><summary>规则与命中片段 · {hits.length} 条</summary><small>分数是规则权重，不是准确率或事实核验结果。</small>{hits.map((hit, index) => <p key={`${hit.rule_id}-${hit.field}-${index}`}><span>{hit.rule_id.startsWith('channel:') ? '频道' : '地域'} · {hit.candidate} · {hit.rule_id.includes(':topic-') ? '话题标签' : hit.field === 'title' ? '标题字段' : '文案字段'} · {hit.score > 0 ? `权重 ${hit.score}` : hit.rule_id.includes(':topic-') ? '标签冲突，未采纳' : '背景或歧义，已排除'}</span><q>{hit.snippet}</q><small>规则：{hit.rule_id}</small></p>)}</details>}
    {post.tag_scores && <small>候选得分：{(['channel', 'region'] as const).map(field => `${field === 'channel' ? '频道' : '地域'} ${Object.entries(post.tag_scores![field]).map(([name, score]) => `${name} ${score}`).join('、') || '无线索'}`).join('；')}</small>}
    <small>规则版本：{post.tag_rule_version || '等待后端提供当前规则版本'}。依据发布文案与话题标签；标签不等于事实核验，正文明确线索优先。地点词典未覆盖或上下文不清时保留待判定，不进行 AI 复核或人工纠正。</small>
  </div></details>
}
