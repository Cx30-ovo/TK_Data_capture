import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import ts from 'typescript'

async function load(name) {
  const code = ts.transpileModule(readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
const { splitPostText, presentPost, attributionFacets, matchesAttributionFilter } = await load('postPresentation')
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

// Source labels and staff credits are separate metadata, never work-type claims.
const attributionCases = [
  ['新闻。（来源/看厦门）', [['source', '来源', '看厦门']]],
  ['新闻。（视频来源：央视新闻 编辑/小陈 责编/小林 编审/小李）', [
    ['source', '视频来源', '央视新闻'], ['staff', '编辑', '小陈'], ['staff', '责编', '小林'], ['staff', '编审', '小李']]],
  ['新闻。(采编/廖航 黄鹤 包装/廖航 责编/林振明 梁含雪 编审/王群 许晓露)#媒体原创', [
    ['staff', '采编', '廖航 黄鹤'], ['staff', '包装', '廖航'], ['staff', '责编', '林振明 梁含雪'], ['staff', '编审', '王群 许晓露']]],
  ['新闻。【见习编辑／小王 实习编辑：小陈 责任编辑/小林】', [
    ['staff', '见习编辑', '小王'], ['staff', '实习编辑', '小陈'], ['staff', '责任编辑', '小林']]],
  ['新闻。\n来源：看厦门\n记者：小张\n摄像：小李 #新闻', [
    ['source', '来源', '看厦门'], ['staff', '记者', '小张'], ['staff', '摄像', '小李']]],
  ['新闻（供稿/某机构）（摄影/小张）', [['source', '供稿', '某机构'], ['staff', '摄影', '小张']]],
  ['新闻（来源@看厦门 ）', [['source', '来源', '看厦门']]],
  ['新闻（来源/甲）（来源/乙）', [['source', '来源', '甲'], ['source', '来源', '乙']]],
  ['新闻（来源/甲、乙 责编/小李）', [['source', '来源', '甲、乙'], ['staff', '责编', '小李']]],
  ['新闻（编辑/小张）（编辑/小李）', [['staff', '编辑', '小张'], ['staff', '编辑', '小李']]],
  ['新闻（来源： 编辑/小张）', [['staff', '编辑', '小张']]],
  ['新闻（来源：）', []],
  ['记者介绍编辑、责编和编审的职责。', []],
  ['政策（试行）今日实施，来源广泛。', []],
  ['新闻（请编辑：注意排版）', []],
  ['如何识别来源？不要把编辑当成原创证明。#媒体原创', []],
  ['', []],
  [null, []],
]
for (const [caption, expected] of attributionCases) {
  const result = splitPostText(caption)
  assert.deepEqual(result.attributions.map(({ category, role, value }) => [category, role, value]), expected, caption)
  for (const item of result.attributions) assert.ok(caption.includes(item.snippet))
  assert.equal('work_type' in result, false)
}
const sameCredit = '新闻（来源/看厦门 编辑/小陈）'
const samePost = { aweme_id: '456', title: sameCredit, desc: sameCredit }
const grouped = presentPost(samePost)
assert.equal(grouped.attributions.length, 2)
assert.deepEqual(grouped.attributions[0].references.map(ref => ref.field), ['title', 'desc'])
assert.equal(samePost.title, sameCredit)
assert.equal(samePost.desc, sameCredit)
assert.deepEqual(presentPost({ ...samePost, title: '新闻', desc: '文案（责编/小陈）' }).attributions[0].references,
  [{ field: 'desc', snippet: '责编/小陈' }])
assert.equal(splitPostText('新闻（请编辑：注意排版）').text, '新闻（请编辑：注意排版）')
assert.equal(splitPostText('新闻（剪辑/小陈 包装/小张 制作/小李）').text, '新闻')
assert.deepEqual(presentPost({ ...samePost, title: '新闻（来源/看厦门）', desc: '文案（来源/另一机构）' }).attributions.map(item => item.value), ['看厦门', '另一机构'])
assert.equal(presentPost({ ...samePost, title: '新采集作品（来源/看厦门）', desc: '' }).attributions[0].role, '来源')

// Source and role/name filters intersect; the name cannot match a different role.
const creditedWorks = [
  presentPost({ aweme_id: 'a', title: '甲（来源/看厦门 编辑/小陈 责编/小林）', desc: '甲（来源/看厦门）' }).attributions,
  presentPost({ aweme_id: 'b', title: '乙（来源/另一机构 编辑/小林 摄像/小陈）', desc: '' }).attributions,
  presentPost({ aweme_id: 'c', title: '丙（来源/看厦门 采编/记者甲 记者乙）', desc: '' }).attributions,
  presentPost({ aweme_id: 'd', title: '未标注来源，正文提到小陈和看厦门', desc: '' }).attributions,
]
const idsMatching = filter => creditedWorks.flatMap((entries, i) => matchesAttributionFilter(entries, { source:'', role:'', staff:'', ...filter }) ? [i] : [])
assert.deepEqual(idsMatching({}), [0, 1, 2, 3])
assert.deepEqual(idsMatching({ source:'看厦门' }), [0, 2])
assert.deepEqual(idsMatching({ source:'看厦' }), [])
assert.deepEqual(idsMatching({ role:'编辑' }), [0, 1])
assert.deepEqual(idsMatching({ staff:'小陈' }), [0, 1])
assert.deepEqual(idsMatching({ role:'编辑', staff:'小陈' }), [0])
assert.deepEqual(idsMatching({ role:'编辑', staff:'小林' }), [1])
assert.deepEqual(idsMatching({ source:'看厦门', role:'编辑', staff:'小林' }), [])
assert.deepEqual(idsMatching({ staff:' 记者乙 ' }), [2])
assert.deepEqual(idsMatching({ staff:'   ' }), [0, 1, 2, 3])
assert.deepEqual(idsMatching({ source:'无此来源' }), [])
const facets = attributionFacets(creditedWorks)
assert.deepEqual(Object.fromEntries(facets.sources.map(item => [item.value, item.count])), { '看厦门':2, '另一机构':1 })
assert.deepEqual(Object.fromEntries(facets.roles.map(item => [item.value, item.count])), { '编辑':2, '责编':1, '采编':1, '摄像':1 })
assert.deepEqual(attributionFacets([]), { sources:[], roles:[] })
assert.deepEqual(attributionFacets([[...creditedWorks[0], ...creditedWorks[0]]]).sources, [{value:'看厦门',count:1}])
assert.equal(matchesAttributionFilter([{category:'staff',role:'编辑',value:'Alice',snippet:'编辑/Alice'}], {source:'',role:'编辑',staff:'alice'}), true)

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
