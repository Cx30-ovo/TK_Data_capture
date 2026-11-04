import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import ts from 'typescript'

async function load(name) {
  const code = ts.transpileModule(readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
const { splitPostText, presentPost } = await load('postPresentation')
const raw = '今天（11月3日），厦门举办（WTT）比赛。（编辑/小陈 责编/小林）#厦门 #体育'
const clean = splitPostText(raw)
assert.equal(clean.text, '今天（11月3日），厦门举办（WTT）比赛。')
assert.deepEqual(clean.topics, ['厦门', '体育'])
assert.equal(clean.credits.length, 1)
assert.equal(splitPostText('新闻内容【采编/小陈 实习生/小王(新闻实践) 责编/小林】').text, '新闻内容')
assert.equal(splitPostText('新闻内容（来源@厦门卫视 ）').text, '新闻内容')
assert.equal(splitPostText('#厦门 今天交通恢复正常 #民生').text, '今天交通恢复正常')
assert.equal(splitPostText('政策（试行）今日实施').text, '政策（试行）今日实施')
assert.equal(splitPostText('新闻内容。\n来源：厦门广电').text, '新闻内容。')
assert.equal(splitPostText('记者采访市民，了解生活变化').text, '记者采访市民，了解生活变化')
assert.deepEqual(splitPostText('#厦门#厦门 #新闻').topics, ['厦门', '新闻'])
const post = { aweme_id: '123456789123456', title: raw, desc: raw }
assert.equal(presentPost(post).body, '')
assert.equal(post.title, raw)
assert.equal(presentPost({ ...post, title: '', desc: '正文新闻 #厦门' }).title, '正文新闻')
assert.equal(presentPost({ ...post, title: '', desc: '正文新闻 #厦门' }).body, '')
assert.equal(presentPost({ ...post, title: post.aweme_id, desc: '' }).title, '暂无可读标题')

const { readHotRankCache, saveHotRankCache, hotRankAge } = await load('hotRankCache')
const now = Date.parse('2026-11-03T08:00:00+08:00')
let saved = null
const storage = { getItem: () => saved, setItem: (_, value) => { saved = value } }
const data = { generated_at: new Date(now - 60000).toISOString(), stale: false, cached: false, source: 'douyin',
  items: [{ word: '测试新闻', search_url: 'https://www.douyin.com/search/test', hot_value: 100 }] }
saveHotRankCache(storage, data, now)
assert.equal(readHotRankCache(storage, now).items[0].word, '测试新闻')
assert.equal(readHotRankCache(storage, now).stale, true)
const before = saved
saveHotRankCache(storage, { ...data, items: [] }, now)
saveHotRankCache(storage, { ...data, stale: true }, now)
assert.equal(saved, before)
assert.equal(readHotRankCache(storage, now + 8 * 86400000), undefined)
assert.equal(hotRankAge(data.generated_at, now), '1分钟前更新')
assert.equal(hotRankAge('invalid', now), '更新时间未知')
saved = '{broken'
assert.equal(readHotRankCache(storage, now), undefined)
assert.doesNotThrow(() => saveHotRankCache({ setItem() { throw new Error('quota') } }, data, now))
saveHotRankCache(storage, { ...data, items: [{ ...data.items[0], search_url: 'javascript:alert(1)' }] }, now)
assert.equal(readHotRankCache(storage, now), undefined)
console.log('Reading cleanup and hot-rank cache checks passed')
