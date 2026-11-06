import { useEffect, useId, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { collectionErrorMessage, monitorApi, type EditorialClassification, type EditorialCorrectionPayload, type MonitorDashboard, type MonitorDashboardPost } from '@/lib/api'

export const editorialChannels = ['推荐', '时政', '民生', '经济', '科技', '教育', '健康', '体育', '文旅', '文娱', '三农', '法治', '政策文件', '应急', '环境生态', '待判定']
export const postChannel = (channel?: string) => channel && channel !== '综合' ? channel : '待判定'
export const editorialRegions = ['全部', '本地', '本省', '国内', '国际', '待判定']
export const regionDescription = (region: string) => ({ 本地: '厦门市', 本省: '福建省级内容及省内其他城市', 国内: '福建省外国内地区（含港澳台）', 国际: '境外地区', 待判定: '现有内容不足以确定主要地域' }[region] || region)

export function PostEditorialTags({ post }: { post: MonitorDashboardPost }) {
  const region = post.region || '待判定'
  const review = post.tag_method === 'manual' ? '人工已纠正'
    : post.tag_status === 'insufficient' ? '内容不足'
    : post.tag_status === 'pending' ? 'AI 复核中'
    : post.tag_status === 'retry' ? 'AI 待重试'
    : post.tag_status === 'deferred' ? '等待 AI 复核'
    : post.tag_status === 'ai_unavailable' ? 'AI 未启用'
    : post.tag_status === 'uncertain' ? '需核实'
    : post.tag_method === 'rules_ai_visual' ? '视觉已复核'
    : post.tag_method === 'rules_ai' ? 'AI 已复核' : ''
  return <span className="post-editorial-tags"><span className="post-channel-tag" title={`${post.tag_method === 'manual' ? '人工纠正，优先于自动分类' : post.tag_method === 'rules_ai_visual' ? '结合当前作品抽样画面或封面复核' : `根据标题与正文${post.tag_method === 'rules_ai' ? '规则初筛及 AI 复核' : '规则初筛'}`}${post.channel_evidence ? ` · 依据：${post.channel_evidence}` : ''}`}>{postChannel(post.channel)}</span><span className="post-region-tag" title={`${regionDescription(region)}${post.region_evidence ? ` · 依据：${post.region_evidence}` : ''}`}>{region}</span>{review && <span className="post-review-tag" data-state={post.tag_status} title={post.tag_reason || '初筛有歧义的标签由 AI 复核；未完成时展示初筛结果。'}>{review}</span>}</span>
}

export function PostEditorialEvidence({ post }: { post: MonitorDashboardPost }) {
  const ai = post.tag_method === 'rules_ai' || post.tag_method === 'rules_ai_visual'
  const confidence = Object.entries(post.tag_confidence || {}).filter(([, value]) => Number.isFinite(value))
  const summary = post.tag_method === 'manual' ? '人工纠正结果，优先展示'
    : post.tag_status === 'insufficient' ? '内容不足，暂不能判定'
    : post.tag_status === 'pending' ? '初筛完成，AI 正在复核歧义'
    : post.tag_status === 'retry' ? '暂用初筛结果，等待 AI 重试'
    : post.tag_status === 'uncertain' ? '已复核，部分标签仍需核实'
    : ai ? '已通过规则初筛与 AI 复核' : '按标题与正文规则归类'
  const origin = (source: MonitorDashboardPost['channel_evidence_source']) => !source || source.kind === 'text' ? '文字'
    : source.kind === 'cover' ? '封面识别' : `视频画面 ${source.timestamp_seconds ?? 0} 秒`
  const references = post.tag_experience_refs || []
  return <details className="post-editorial-evidence"><summary><strong>标签判定</strong><span>{summary}</span><small>查看依据</small></summary><div className="post-evidence-body">
    {post.channel_evidence && <p><span>频道依据 · {origin(post.channel_evidence_source)}</span>{post.channel_evidence}</p>}
    {post.region_evidence && <p><span>地域依据 · {origin(post.region_evidence_source)}</span>{post.region_evidence}</p>}
    {post.visual_status && <p><span>{post.visual_status === 'sampled_video' ? `视频抽样 · ${post.visual_sources?.length || 0} 帧` : post.visual_status === 'cover_only' ? '仅参考封面' : post.visual_status === 'analysis_failed' ? '视觉复核未完成' : '媒体不可用'}</span>{post.visual_limitation}</p>}
    {references.length > 0 && <details className="post-experience-references"><summary>纠错经验参考 · {references.length} 条</summary><small>仅参考分类边界，不是当前作品的事实依据，也不代表模型已经训练。</small>{references.map(ref => <p key={ref.aweme_id}><span>作品 {ref.aweme_id} · 修订 {ref.revision} · {ref.channel} / {ref.region}</span>{ref.reason}</p>)}</details>}
    {post.tag_reason && <p>{post.tag_reason}</p>}{confidence.length > 0 && <small>模型自评：{confidence.map(([field, value]) => `${field === 'channel' ? '频道' : '地域'} ${Math.round(value * 100)}%`).join(' · ')}，仅供复核参考</small>}{post.tag_status === 'insufficient' && <p>缺少可分析的标题正文，补充内容后会重新判定。</p>}</div></details>
}

export function PostEditorialCorrection({ post }: { post: MonitorDashboardPost }) {
  const client = useQueryClient(), id = useId(), trigger = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef(false)
  const [open, setOpen] = useState(false), [loading, setLoading] = useState(false)
  const [current, setCurrent] = useState<EditorialClassification | null>(null)
  const [channel, setChannel] = useState('待判定'), [region, setRegion] = useState('待判定')
  const [reason, setReason] = useState(''), [error, setError] = useState(''), [message, setMessage] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const reasonLength = Array.from(reason).length
  const reasonError = submitted && !reason.trim() ? '请填写纠正依据' : reasonLength > 1000 ? '纠正依据最多 1000 字' : ''
  const close = () => { setOpen(false); setError(''); trigger.current?.focus() }
  const save = useMutation({
    mutationFn: (payload: EditorialCorrectionPayload) => monitorApi.correctEditorialTags(post.aweme_id, payload),
    onSuccess: (response, payload) => {
      returnFocus.current = true
      setMessage(payload.mode === 'manual' ? '人工分类已保存' : '已恢复自动分类')
      close()
      client.setQueriesData<MonitorDashboard>({ queryKey: ['monitorDashboard'] }, old => old && Array.isArray(old.posts)
        ? { ...old, posts: old.posts.map(item => item.aweme_id === post.aweme_id ? { ...item, ...response.data } : item) } : old)
      void client.invalidateQueries({ queryKey: ['monitorDashboard'] })
    },
    onError: caught => setError(collectionErrorMessage(caught)),
  })
  useEffect(() => {
    if (returnFocus.current && !open && !save.isPending) {
      trigger.current?.focus()
      returnFocus.current = false
    }
  }, [open, save.isPending])
  const begin = async () => {
    setOpen(true); setLoading(true); setError(''); setMessage(''); setSubmitted(false); setCurrent(null)
    try {
      const { data } = await monitorApi.getEditorialTags(post.aweme_id)
      setCurrent(data); setChannel(postChannel(data.channel)); setRegion(data.region || '待判定')
      setReason(data.manual_status === 'none' ? '' : data.manual_reason || '')
    } catch (caught) { setError(collectionErrorMessage(caught)) }
    finally { setLoading(false) }
  }
  const submit = (mode: 'manual' | 'automatic') => {
    if (!current || save.isPending) return
    setSubmitted(true)
    if (mode === 'manual' && (!reason.trim() || reasonLength > 1000)) return
    setError('')
    save.mutate({ mode, expected_revision: current.manual_revision, source_sha256: current.classification_source_sha256,
      ...(mode === 'manual' ? { channel, region, reason: reason.trim() } : {}) })
  }
  return <section className="post-editorial-correction" aria-label="人工纠正分类">
    <div className="post-correction-heading"><button ref={trigger} type="button" disabled={save.isPending} aria-expanded={open} aria-controls={`${id}-form`} onClick={() => open ? close() : void begin()}>纠正分类</button><span>人工结果优先，可恢复自动</span></div>
    {message && <p role="status">{message}</p>}
    {!open && post.manual_status === 'outdated' && <p role="status">原文已变化，原人工分类未应用，可重新纠正。</p>}
    {open && <form id={`${id}-form`} aria-label="纠正分类表单" onSubmit={event => { event.preventDefault(); submit('manual') }} onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (!save.isPending) close() } }}>
      {loading && <p role="status">正在读取最新分类…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !current && <button type="button" onClick={() => void begin()}>重新读取分类</button>}
      {current && <>
        {current.manual_status === 'outdated' && <p role="status">原文已变化，请重新检查依据后保存。</p>}
        <div className="post-correction-fields"><div><label htmlFor={`${id}-channel`}>频道</label><select id={`${id}-channel`} value={channel} disabled={save.isPending} onChange={event => setChannel(event.target.value)}>{editorialChannels.filter(item => item !== '推荐').map(item => <option key={item}>{item}</option>)}</select></div><div><label htmlFor={`${id}-region`}>地域</label><select id={`${id}-region`} value={region} disabled={save.isPending} onChange={event => setRegion(event.target.value)}>{editorialRegions.filter(item => item !== '全部').map(item => <option key={item}>{item}</option>)}</select></div></div>
        <label htmlFor={`${id}-reason`}>纠正依据（必填）</label><textarea id={`${id}-reason`} rows={3} value={reason} disabled={save.isPending} aria-invalid={!!reasonError} aria-describedby={`${id}-hint${reasonError ? ` ${id}-error` : ''}`} onChange={event => setReason(event.target.value)} />
        <small id={`${id}-hint`}>说明标题、文案或原作品中的依据；不确定的字段可保留“待判定”。{reasonLength}/1000</small>
        {reasonError && <p id={`${id}-error`} role="alert">{reasonError}</p>}
        <div className="post-correction-actions"><button type="submit" disabled={save.isPending}>{save.isPending ? '正在保存…' : '保存人工分类'}</button>{current.manual_status !== 'none' && <button type="button" disabled={save.isPending} onClick={() => submit('automatic')}>恢复自动分类</button>}<button type="button" disabled={save.isPending} onClick={close}>取消</button></div>
      </>}
      {!current && <button type="button" onClick={close}>取消</button>}
    </form>}
  </section>
}
