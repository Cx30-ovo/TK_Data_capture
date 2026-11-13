/** Display-only cleanup. Raw collected text is retained in the post object. */
const sourceRoles = ['视频来源', '图片来源', '内容来源', '文章来源', '素材来源', '来源', '供稿']
const staffRoles = ['见习编辑', '实习编辑', '责任编辑', '责任编审', '见习记者', '实习记者', '编辑', '责编', '编审', '采编', '记者', '摄像', '摄影', '通讯员', '主播', '剪辑', '包装', '审核', '制作', '编导', '实习生']
const creditPattern = `(${[...sourceRoles, ...staffRoles].sort((a, b) => b.length - a.length).join('|')})\\s*[:：/／|｜@]\\s*`
export type PostAttribution = {
  category: 'source' | 'staff'
  role: string
  value: string
  snippet: string
}

export type AttributionFilter = { source: string; role: string; staff: string }

/** Role and name must match the same credit; sources match their displayed value. */
export function matchesAttributionFilter(entries: readonly PostAttribution[], filter: AttributionFilter) {
  const staff = filter.staff.trim().toLocaleLowerCase()
  return (!filter.source || entries.some(item => item.category === 'source' && item.value === filter.source))
    && ((!filter.role && !staff) || entries.some(item => item.category === 'staff'
      && (!filter.role || item.role === filter.role)
      && (!staff || item.value.toLocaleLowerCase().includes(staff))))
}

/** Counts represent works, deduplicating repeated title/description metadata. */
export function attributionFacets(works: readonly (readonly PostAttribution[])[]) {
  const sources = new Map<string, number>(), roles = new Map<string, number>()
  for (const entries of works) {
    for (const value of new Set(entries.filter(item => item.category === 'source').map(item => item.value))) sources.set(value, (sources.get(value) || 0) + 1)
    for (const value of new Set(entries.filter(item => item.category === 'staff').map(item => item.role))) roles.set(value, (roles.get(value) || 0) + 1)
  }
  const sorted = (values: Map<string, number>) => [...values].sort(([a], [b]) => a.localeCompare(b, 'zh-CN')).map(([value, count]) => ({ value, count }))
  return { sources: sorted(sources), roles: sorted(roles) }
}

/** Values remain as written: do not infer people, ownership or publication type. */
function parseCredits(value: string): PostAttribution[] {
  const markers = [...value.matchAll(new RegExp(creditPattern, 'gu'))]
  return markers.flatMap((marker, index) => {
    const start = marker.index!
    const end = markers[index + 1]?.index ?? value.length
    const raw = value.slice(start, end).split('#', 1)[0].trim().replace(/[\s，,；;。]+$/u, '')
    const content = raw.slice(marker[0].length).trim()
    return content ? [{ category: sourceRoles.includes(marker[1]) ? 'source' as const : 'staff' as const,
      role: marker[1], value: content, snippet: raw }] : []
  })
}

export function splitPostText(value: string | null | undefined) {
  const raw = value || ''
  const topics = [...new Set([...raw.matchAll(/#([^\s#]+)/gu)].map(match => match[1]))]
  const credits: string[] = []
  const creditMarker = new RegExp(`^\\s*${creditPattern}`, 'u')
  let text = raw.replace(/（[^（）]*）|\([^()]*\)|【[^【】]*】|\[[^\[\]]*\]/gu, part => {
    if (!creditMarker.test(part.slice(1, -1))) return part
    credits.push(part.slice(1, -1).trim())
    return ' '
  })
  // Unbracketed trailing credits are separated only at a recognized delimiter.
  const trailing = text.search(new RegExp(`(?:^|[\\n。！!？?])\\s*${creditPattern}`, 'u'))
  if (trailing >= 0) {
    const cut = /[\n。！!？?]/u.test(text[trailing]) ? trailing + 1 : trailing
    credits.push(text.slice(cut).trim())
    text = text.slice(0, cut)
  }
  text = text.replace(/#[^\s#]+/gu, ' ').replace(/[ \t]+/g, ' ').replace(/\n\s*\n/g, '\n').trim()
  return { text, topics, credits, attributions: credits.flatMap(parseCredits) }
}

export function presentPost(post: { title: string; desc: string; aweme_id: string }) {
  const title = splitPostText(post.title)
  const body = splitPostText(post.desc)
  const readable = (text: string) => text && text !== post.aweme_id && !/^\d{12,}$/.test(text)
  const heading = readable(title.text) ? title.text : readable(body.text) ? body.text : '暂无可读标题'
  const attributions: (PostAttribution & { references: { field: 'title' | 'desc'; snippet: string }[] })[] = []
  for (const [field, result] of [['title', title], ['desc', body]] as const) {
    for (const entry of result.attributions) {
      const existing = attributions.find(item => item.category === entry.category && item.role === entry.role && item.value === entry.value)
      const reference = { field, snippet: entry.snippet }
      if (existing) {
        if (!existing.references.some(item => item.field === field && item.snippet === entry.snippet)) existing.references.push(reference)
      } else attributions.push({ ...entry, references: [reference] })
    }
  }
  return {
    title: heading,
    body: readable(body.text) && body.text !== heading ? body.text : '',
    topics: [...new Set([...title.topics, ...body.topics])],
    credits: [...new Set([...title.credits, ...body.credits])],
    attributions,
  }
}
