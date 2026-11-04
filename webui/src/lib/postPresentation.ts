/** Display-only cleanup. Raw collected text is retained in the post object. */
export function splitPostText(value: string | null | undefined) {
  const raw = value || ''
  const topics = [...new Set([...raw.matchAll(/#([^\s#]+)/gu)].map(match => match[1]))]
  const credits: string[] = []
  const creditMarker = /(?:来源|(?:见习|实习)?编辑|责编|编审|采编|记者|摄像|通讯员|主播)\s*[:：/|@]/u
  let text = raw.replace(/（[^（）]*）|\([^()]*\)|【[^【】]*】|\[[^\[\]]*\]/gu, part => {
    if (!creditMarker.test(part)) return part
    credits.push(part.slice(1, -1).trim())
    return ' '
  })
  // Unbracketed trailing credits are separated only at a recognized delimiter.
  const trailing = text.search(/(?:^|[\n。！!？?])\s*(?:来源|(?:见习|实习)?编辑|责编|编审|采编|记者|摄像|通讯员)\s*[:：/|]/u)
  if (trailing >= 0) {
    const cut = /[\n。！!？?]/u.test(text[trailing]) ? trailing + 1 : trailing
    credits.push(text.slice(cut).trim())
    text = text.slice(0, cut)
  }
  text = text.replace(/#[^\s#]+/gu, ' ').replace(/[ \t]+/g, ' ').replace(/\n\s*\n/g, '\n').trim()
  return { text, topics, credits }
}

export function presentPost(post: { title: string; desc: string; aweme_id: string }) {
  const title = splitPostText(post.title)
  const body = splitPostText(post.desc)
  const readable = (text: string) => text && text !== post.aweme_id && !/^\d{12,}$/.test(text)
  const heading = readable(title.text) ? title.text : readable(body.text) ? body.text : '暂无可读标题'
  return {
    title: heading,
    body: readable(body.text) && body.text !== heading ? body.text : '',
    topics: [...new Set([...title.topics, ...body.topics])],
    credits: [...new Set([...title.credits, ...body.credits])],
  }
}
