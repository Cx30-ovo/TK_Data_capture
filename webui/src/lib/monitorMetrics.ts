import type { MonitorDashboardPost, MonitorSnapshot } from '@/lib/api'


export const STAGE_ORDER = ['first_seen', '1h', '6h', '24h', '72h', '7d'] as const

export const THEME_DEFINITIONS = [
  { key: 'xiamenMetro', keywords: ['厦门地铁', '地铁', 'brt'] },
  { key: 'minchao', keywords: ['闽超', '福厦大战', '足球', '联赛', '福建队', '厦门队'] },
  { key: 'investmentFair', keywords: ['投洽会', '九八', '招商', '投资贸易'] },
  { key: 'taiwan', keywords: ['台湾', '台海', '涉台', '两岸', '民进党', '台独'] },
  { key: 'localLife', keywords: ['厦门', '民生', '社区', '交通', '菜价', '天气', '本地'] },
  { key: 'culture', keywords: ['歌剧', '演出', '音乐会', '艺术节', '文化', '音乐会', '剧场'] },
  { key: 'international', keywords: ['国际', '美国', '俄罗斯', '乌克兰', '以色列', '中东', '欧洲'] },
  { key: 'education', keywords: ['教育', '学校', '大学', '军训', '考试', '学生', '教师'] },
  { key: 'health', keywords: ['医疗', '健康', '医院', '医生', '药品', '疾病', '医保'] },
] as const

export const THEME_COLORS: Record<string, string> = {
  xiamenMetro: '#06b6d4',
  minchao: '#3b82f6',
  investmentFair: '#8b5cf6',
  taiwan: '#ef4444',
  localLife: '#22c55e',
  culture: '#eab308',
  international: '#f97316',
  education: '#14b8a6',
  health: '#ec4899',
  other: '#94a3b8',
}

export const GENERIC_TAGS = new Set([
  '媒体原创',
  '原创',
  '厦门',
  '福州',
  '福建',
  '新闻',
  '热点',
  '视频',
  '资讯',
])

const EDITORIAL_WORDS = ['责任编辑', '编辑', '记者', '通讯员', '来源', '摄影', '摄像', '作者', '视频', '图片']
const COMMON_SURNAMES = '赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程邢裴陆荣翁荀羊甄曲封芮储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲台从鄂索咸籍赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公'


function stripEditorialMetadata(text: string): string {
  let cleaned = text.replace(/(责任编辑|编辑|记者|通讯员|来源|摄影|摄像|作者|视频|图片)\s*[：:]\s*[^\s，。！？,.!?]{1,12}/g, ' ')
  EDITORIAL_WORDS.forEach((word) => {
    cleaned = cleaned.split(word).join(' ')
  })
  return cleaned
}


function isLikelyPersonName(word: string): boolean {
  if (word.length < 2 || word.length > 3) return false
  if (!COMMON_SURNAMES.includes(word[0])) return false
  return !THEME_DEFINITIONS.some((theme) => theme.keywords.some((keyword) => keyword.includes(word) || word.includes(keyword)))
}


function isBlockedKeyword(word: string, extraStopWords: string[] = []): boolean {
  return EDITORIAL_WORDS.includes(word)
    || extraStopWords.includes(word)
    || isLikelyPersonName(word)
}


export function snapshotInteraction(snapshot?: MonitorSnapshot): number {
  if (!snapshot) return 0
  return snapshot.liked_count + snapshot.collected_count + snapshot.comment_count + snapshot.share_count
}


export function latestSnapshot(post: MonitorDashboardPost): MonitorSnapshot | undefined {
  return [...post.snapshots].sort((left, right) => right.actual_age_seconds - left.actual_age_seconds)[0]
}


export function interactionByStage(post: MonitorDashboardPost): Map<string, number> {
  return new Map(post.snapshots.map((snapshot) => [snapshot.stage, snapshotInteraction(snapshot)]))
}


export function postInteraction(post: MonitorDashboardPost): number {
  return snapshotInteraction(latestSnapshot(post))
}


export function mean(values: number[]): number {
  return values.length > 0 ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
}


export function median(values: number[]): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle]
}


export function firstSeenDelayHours(post: MonitorDashboardPost): number {
  return Math.max(0, (post.first_seen_at - post.create_time) / 3600)
}


export function classifyTheme(post: MonitorDashboardPost): string {
  const text = stripEditorialMetadata(`${post.title} ${post.desc}`).toLowerCase()
  const matched = THEME_DEFINITIONS.find((theme) => theme.keywords.some((keyword) => text.includes(keyword.toLowerCase())))
  return matched?.key || 'other'
}


export function extractTags(post: MonitorDashboardPost): string[] {
  const source = stripEditorialMetadata(`${post.title} ${post.desc}`)
  const tags = [...source.matchAll(/#([^#\s]+)/g)].map((match) => match[1].replace(/[，。！？,.!?：:；;、]/g, '').trim()).filter((tag) => tag && !isBlockedKeyword(tag))
  return [...new Set(tags)]
}


export function extractKeywords(post: MonitorDashboardPost): string[] {
  const text = stripEditorialMetadata(`${post.title} ${post.desc}`).replace(/#[^#\s]+/g, ' ')
  const words = text.match(/[A-Za-z]{3,}|[\u4e00-\u9fa5]{2,8}/g) || []
  return words.filter((word) => !isBlockedKeyword(word, ['今天', '我们', '他们', '一个', '这个', '就是', '可以', '进行', '已经', '没有']))
}


export function lifecycleMetrics(post: MonitorDashboardPost) {
  const byStage = interactionByStage(post)
  const first = byStage.get('1h')
  const sixHours = byStage.get('6h')
  const day = byStage.get('24h')
  const threeDays = byStage.get('72h')
  return {
    burst: first != null && day ? first / day : null,
    tail: day != null && sixHours ? day / sixHours : null,
    persistence: threeDays != null && day ? threeDays / day : null,
    increment1h: first ?? null,
    increment6h: first != null && sixHours != null ? sixHours - first : null,
    increment24h: sixHours != null && day != null ? day - sixHours : null,
    increment72h: day != null && threeDays != null ? threeDays - day : null,
  }
}


export function lifecycleType(post: MonitorDashboardPost): 'earlyBurst' | 'sustained' | 'longTail' | 'quickDecline' {
  const metrics = lifecycleMetrics(post)
  const increments = [metrics.increment1h, metrics.increment6h, metrics.increment24h, metrics.increment72h]
  if (metrics.persistence != null && metrics.persistence >= 1.15 && (metrics.increment72h || 0) > 0) return 'sustained'
  const dominant = Math.max(...increments.map((value) => value ?? Number.NEGATIVE_INFINITY))
  if (metrics.increment1h === dominant) return 'earlyBurst'
  if (metrics.increment24h === dominant) return 'longTail'
  if (metrics.increment6h === dominant) return 'quickDecline'
  return 'longTail'
}
