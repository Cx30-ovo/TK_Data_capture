"""Conservative, explainable editorial tags derived from collected text.

No publisher location, human correction or model output is used. The pure result
can be computed on read or stored by the separate, disposable rule cache.
"""
import re
from functools import lru_cache
from copy import deepcopy


CHANNEL_RULES = (
    ("政策文件", "政策文件|征求意见|管理办法|实施细则|印发|发布通知|条例|新规|政策解读"),
    ("应急", "预警|台风|地震|火灾|洪水|暴雨|山洪|泥石流|坍塌|应急|救援|溺水|事故|爆炸"),
    ("健康", "健康|医院|医生|医学|医学生|患者|疾病|癌|疫苗|流感|养生|治疗|手术|急救|心梗|疾控"),
    ("三农", "三农|农业|农民|农村|乡村|农田|丰收|春耕|秋收|粮食|种植|养殖|渔业"),
    ("环境生态", "生态|环保|污染|环境保护|垃圾分类|湿地|生物多样性|生物圈|栖息|碳排放|野生动物|候鸟|水质|海洋生物|海洋生态|海洋保护|守护海洋|净滩|白海豚|珊瑚礁|红树林"),
    ("经济", "经济|金融|股市|股价|股票|房价|楼市|消费|投资|外贸|出口|进口|税收|营收|GDP|企业|产业|就业|工资"),
    ("科技", "科技|人工智能|大模型|机器人|航天|卫星|芯片|半导体|量子|算法|软件|操作系统|输入法|科研|科学家|研发|空间站|深空探测|[Aa][Ii](?![A-Za-z])"),
    ("体育", "体育|马拉松|奥运|全运会|世界杯|世锦赛|冠军赛|乒乓|国乒|足球|篮球|羽毛球|网球|游泳赛|联赛|夺冠|女单|男单|女双|男双|四强|八强|晋级|WTT|NBA|CBA"),
    ("教育", "教育|高考|中考|招生|入学|学位|学费|校园|学校|学生|教师|教研|教材|大学|幼儿园|中小学|留学"),
    ("法治", "法院|检察|起诉|诉讼|判刑|判决|刑事|犯罪|诈骗|盗窃|抢劫|贪污|受贿|法律援助|普法|行政处罚|司法|嫌疑人|立案侦查"),
    ("文娱", "文娱|娱乐|电影|电视剧|影视|演员|歌手|演唱会|音乐节|综艺|票房|短剧|新歌|专辑|影星|导演"),
    ("文旅", "文旅|旅游|游客|景区|旅行|非遗|博物馆|文化|美食|古厝|影展|文博会|艺术展|摄影|城市风貌|朝霞|晚霞|悬日|三角梅"),
    ("时政", "习近平|主席|总书记|国务院|总理|外交|两会|人大|政协|国防|军事|军演|导弹|武器|战争|袭击|打击|党代会|全会|民进党|国民党|国台办|总统|首相|联合国|选举|抗议|公开集会|右翼势力|台海|两岸关系"),
    ("民生", "民生|市民|居民|公交|地铁|交通|车管所|民警|养老|社保|医保|住房|物业|停水|停电|停车|警方|交警|寻人|航空|航线|航班|经济舱|公共服务|快递|彩票|中奖"),
)
LOCAL = "厦门|思明|湖里|集美|海沧|同安|翔安|鼓浪屿|鹭岛"
PROVINCE = "福建|福州|泉州|漳州|莆田|三明|南平|龙岩|宁德|平潭|晋江|石狮|南安|惠安|安溪|永春|德化|福清|长乐|连江|闽侯|武夷山|霞浦|福鼎|漳浦|东山岛"
DOMESTIC = "中国|我国|全国|国内|北京|上海|天津|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|江西|山东|河南|湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|内蒙古|广西|西藏|宁夏|新疆|香港|澳门|台湾|台北|高雄|深圳|广州|杭州|南京|成都|武汉|西安|长沙|郑州|济南|青岛|苏州|宁波|温州|合肥|南昌|沈阳|大连|哈尔滨|长春|昆明|贵阳|南宁|海口|兰州|银川|西宁|乌鲁木齐|呼和浩特|拉萨|石家庄|太原|珠海|佛山|东莞|无锡|常州|徐州|洛阳|烟台|潍坊|汕头|温州|绍兴|金华"
INTERNATIONAL = "海外|国外|美国|日本|韩国|朝鲜|俄罗斯|乌克兰|以色列|巴勒斯坦|加沙|伊朗|伊拉克|叙利亚|黎巴嫩|英国|法国|德国|意大利|西班牙|荷兰|瑞士|瑞典|挪威|芬兰|波兰|土耳其|印度|巴基斯坦|泰国|越南|缅甸|柬埔寨|老挝|新加坡|马来西亚|菲律宾|印度尼西亚|印尼|澳大利亚|新西兰|加拿大|墨西哥|巴西|阿根廷|南非|埃及|沙特|阿联酋|斐济|阿富汗|孟加拉|尼泊尔|斯里兰卡|纽约|华盛顿|东京|首尔|伦敦|巴黎|莫斯科"
REGION_RULES = tuple((name, re.compile(pattern, re.I)) for name, pattern in (
    ("本地", LOCAL), ("本省", PROVINCE), ("国内", DOMESTIC), ("国际", INTERNATIONAL)
))

RULE_VERSION = "editorial-rules-v4.0"
_CREDITS = r"(?:(?:见习|实习)?(?:编辑|记者)|视频来源|画面来源|图片来源|内容来源|文章来源|素材来源|来源|供稿|责任编辑|责编|编审|采编|采辑|摄像|摄影|通讯员|剪辑|包装|审核|制作|编导|主播|实习生)\s*[:：/／|｜@]"
_TOPIC = re.compile(r"#[^\s#，。！？、；：,.;:!?（）()【】\[\]]+")


def _blank(match):
    return " " * len(match.group())


def _without_credits(text: str) -> str:
    text = text or ""
    bracket = r"（[^（）]*）|\([^()]*\)|【[^【】]*】|\[[^\[\]]*\]"
    text = re.sub(bracket, lambda m: _blank(m) if re.match(r"\s*" + _CREDITS, m.group()[1:-1]) else m.group(), text)
    text = re.sub(r"(?:^|[\n。！？!?])\s*" + _CREDITS + r"[^\n]*", _blank, text)
    return re.sub(r"@[^\s@]+|https?://\S+", _blank, text)


def _body(text: str) -> str:
    """Mask metadata without shifting offsets; evidence remains a raw substring."""
    text = _without_credits(text)
    # Only a trailing run at a metadata boundary is discarded. Inline marked
    # entities remain words in the sentence; never swallow prose after a period.
    topics = list(_TOPIC.finditer(text))
    if topics and not re.search(r"[\w\u4e00-\u9fff#]", text[topics[-1].end():]):
        start = len(topics) - 1
        while start > 0 and not re.search(r"[\w\u4e00-\u9fff#]", text[topics[start-1].end():topics[start].start()]):
            start -= 1
        prefix = text[:topics[start].start()]
        boundary = not prefix or prefix[-1].isspace() or prefix[-1] in "。！？!?；;）)】]"
        if boundary:
            text = prefix + " " * (len(text) - len(prefix))
    return text.replace("#", " ")


def _parts(title, desc):
    return [(field, raw, _body(raw)) for field, raw in (("title", title or ""), ("desc", desc or ""))
            if raw and (field == "title" or raw != title)]


def _topics(title, desc):
    """Collected caption hashtags, deduplicated and never taken from credits."""
    seen = set()
    for field, raw, _ in _parts(title, desc):
        for match in _TOPIC.finditer(_without_credits(raw)):
            value = match.group()[1:]
            if value in seen or re.search(r"媒体原创|媒体精选|厦门广电|海西晨报|上热门|涨粉|抖音|直击第一线|热点推荐", value):
                continue
            seen.add(value)
            yield field, raw[match.start():match.end()], value


@lru_cache(maxsize=256)
def _pattern(value):
    return re.compile(value, re.I)


# Strong event/action phrases outrank mere entities (e.g. a school or a parent).
# Each expression contributes at most once per work, not once per repetition.
CONTEXT_RULES = (
    ("health-care", "健康", r"医院|医生|医学|医疗|患者|疾病|疫苗|治疗|手术|癌症|流感|心梗|疾控|看病|诊疗", 7),
    ("education-learning", "教育", r"招生|高考|中考|入学|教研|课堂|教学|教材|学费|考试|教育", 7),
    ("law-case", "法治", r"法院|起诉|诉讼|判决|判刑|诈骗|盗窃|刑事|法律援助|普法|立案侦查", 8),
    ("entertainment-work", "文娱", r"电视剧|电影|影视|演员|歌手|演唱会|综艺|票房|短剧|专辑|新歌|影评人|金鸡奖|金像奖|金马奖|百花奖|最佳男主角|最佳女主角|颁奖典礼|献唱", 7),
    ("political-affairs", "时政", r"外交|总书记|国务院|国台办|民进党|国民党|总统|首相|军演|军事|台海|两岸关系|右翼势力|公开集会|联合国|党代会", 8),
    ("policy-document", "政策文件", r"管理办法|实施细则|印发|发布通知|条例|征求意见|政策解读|政策文件", 8),
    ("emergency-event", "应急", r"预警|台风|地震|火灾|洪水|山洪|泥石流|坍塌|救援|溺水|爆炸|事故", 8),
    ("ecology-protection", "环境生态", r"野生动物|白海豚|生物圈|生物多样性|栖息地|生态|环保|湿地|净滩|守护海洋|珊瑚礁|红树林", 7),
    ("agriculture-production", "三农", r"农业|农田|粮食|种植|种菇|菌草|养殖|渔业|春耕|秋收|丰收|乡村", 7),
    ("economy-business", "经济", r"经济(?!舱)|金融|股市|股价|营收|税收|就业|工资|外贸|出口|进口|消费市场|产业", 7),
    ("technology-research", "科技", r"研发|科研|科学家|芯片|半导体|航天|卫星|人工智能|大模型|量子|输入法|操作系统|科技", 7),
    ("sports-competition", "体育", r"体育|足球|篮球|羽毛球|网球|马拉松|奥运|全运会|世界杯|世锦赛|冠军赛|乒乓|国乒|联赛|女单|男单|女双|男双|WTT|NBA|CBA", 7),
    ("tourism-culture", "文旅", r"文旅|旅游|游客|景区|旅行|非遗|博物馆|文博会|古厝|艺术展|城市风貌|晚霞|朝霞|三角梅|文化展览", 7),
    ("livelihood-service", "民生", r"公交|地铁|交通|车管所|停水|停电|停车|物业|养老|社保|住房|航线|航班|经济舱|公共服务|快递|小区.{0,12}(?:修剪|改造|电梯|供水)|邻里.{0,10}(?:互助|生活|日常)", 7),
    ("law-enforcement", "法治", r"酒驾|醉驾|执法|违法|拘留|刑拘|查处", 7),
    ("family-daily", "民生", r"(?:亲子|育儿|萌娃|宝宝|妈妈|爸爸|父母|父亲|母亲|爷爷|奶奶|孩子|家庭|宠物).{0,24}(?:学步|第一步|迈步|走向|叫妈|叫爸|玩具|开心|趣事|日常|陪伴|逗|互动)|(?:学步|亲子互动|家庭生活|育儿趣事)", 7),
    ("family-dialogue", "民生", r"妈妈[：:].{0,16}宝宝[：:]|宝宝[：:].{0,16}爸爸", 7),
    ("campus-memory", "文旅", r"(?:学校|校园|中学|大学|小学).{0,24}(?:旧照|旧日|怀旧|青春|回忆|泛黄|老照片)", 7),
    ("economic-exhibition", "经济", r"进博会|投洽会|投资贸易洽谈会|自贸(?:片区|区|港)|招商引资|供应链|贸易合作|营商环境|财政预算|货币政策", 8),
    ("political-institutions", "时政", r"国防部|祖国统一|台湾光复|两岸统一|内阁|阁僚|白宫|行政命令|停火|空袭|以军|军营|入伍|女兵|抗战|烈士", 8),
    ("political-action", "时政", r"武装.{0,16}(?:攻势|攻占|袭击)|军.{0,8}(?:开火|开枪)|台湾.{0,12}(?:身份认同|统一)|两岸.{0,10}(?:和平|关系|拉近)", 8),
    ("military-operation", "时政", r"战争|战术|俄军|乌军|战斗机|军事行动|前线.{0,12}战斗|无人机.{0,12}(?:袭击|打击)|空袭", 8),
    ("education-admission", "教育", r"考研|录取|支教|开学|研学|毕业生|医学伦理教育|医学模拟教育", 8),
    ("technical-subject", "科技", r"传感器|物联网|智能体|机器人|无人机|无人驾驶|火箭|闰秒|深海探测|核聚变|超导|运载器", 8),
    ("sports-disciplines", "体育", r"围棋|棋手|跳水(?:队|赛|比赛|运动员)|体操|田径|闽超|苏超|中超|中甲|欧冠|足协杯|亚运会|冬奥|残奥|锦标赛", 8),
    ("performing-arts", "文娱", r"音乐剧|舞剧|话剧|戏剧|戏曲|相声|观影|开唱|诗朗诵|舞台表演|钢琴演奏|演绎《|电影节|电影梦", 8),
    ("cultural-exhibition", "文旅", r"文物|美术作品展|书画展|画展|文化遗产|古建筑|海上商路|citywalk", 8),
    ("leisure-scenery", "文旅", r"(?:花海|公园|老城|山野|风景|风光).{0,26}(?:打卡|散步|游玩|赏花|浪漫|惬意|氛围)|(?:赏花|踏青|城市漫步|花海|海上商路)", 7),
    ("food-leisure", "文旅", r"(?:吃遍|品尝|舌尖|逛吃).{0,18}(?:美食|小吃|夜市)|夜市.{0,20}(?:好吃|打卡|炫到爽)|(?:慢生活|松弛).{0,18}(?:游玩|假期|喝茶)", 7),
    ("family-siblings", "民生", r"(?:人类幼崽|弟弟|妹妹|哥哥|姐姐|哥俩|萌宠|小猫|小狗|橘猫).{0,28}(?:日常|配合|趣事|玩具|头盔|猫爬架|陪伴|可爱|互动)", 7),
    ("consumer-livelihood", "民生", r"(?:标价|涨价|价格|收费).{0,20}(?:育儿焦虑|消费维权|投诉)|(?:消费维权|小区改造|社区服务|便民服务)", 7),
    ("emergency-rescue", "应急", r"落水|被困|火情|失联|列车相撞|车祸|泥石流|山体滑坡|山火|失火|起火|灭火|抢回一命", 8),
    ("species-protection", "环境生态", r"新物种|物种.{0,8}(?:发现|命名|保护)|猫科物种|保护动物|濒危|自然保护区|珊瑚.{0,12}(?:修复|种植)", 8),
    ("product-safety", "健康", r"(?:食品|药品|保健品|产品).{0,15}(?:铅超标|有害物|召回停用)|铅超标.{0,12}(?:召回|停用)", 8),
    ("law-seizure", "法治", r"海关.{0,20}(?:查获|暂扣)|(?:走私|非法交易).{0,12}文物", 8),
    ("political-public-affairs", "时政", r"选举|选战|助选|全会|党代表|市委报告|政要|总理|防长|外交部长|财政部长|国债|议会|政党|罢工|抗议游行|军舰|航母|海军|台军|美军|核武器|增兵|军事部署|九一八事变|红军|缅怀先烈|长征胜利", 8),
    ("court-sentencing", "法治", r"宣判|获刑|死刑|抢劫|杀人|贪污|受贿|电诈|防诈|骗局|刷单|毒驾|毒品|监狱|看守所", 8),
    ("education-community", "教育", r"校庆|建校.{0,8}周年|特教|特需学生|课桌椅|课纲|课文|课本|留学|陪读|军训学子|(?:校友|师生).{0,14}(?:重聚|回家|话当年)|(?:孩子|儿童).{0,18}(?:手机成瘾|使用手机|拥有手机)", 8),
    ("music-performance", "文娱", r"歌剧|音乐会|演奏会|交响乐|合唱团|歌舞表演|展演|戏曲表演|京剧|昆曲|钢琴艺术周", 8),
    ("everyday-assistance", "民生", r"哄娃|帮忙哄|护送|交警开道|警车开道|开道护送|免费停车|机场.{0,14}(?:投运|投用|燃油|补给)|(?:大桥|隧道|公路).{0,18}(?:合龙|通车|改造|建设)|社区.{0,24}(?:志愿者|邻里|博饼|活动)", 8),
    ("public-weather", "民生", r"冷空气|天气预报|气温|降温|阵雨|大风|高温天气", 7),
    ("sports-participation", "体育", r"工间操|太极.{0,12}(?:比赛|大赛)|健身比赛|全民健身|竞技比赛", 8),
    ("travel-experience", "文旅", r"(?:酒店|住宿|民宿).{0,24}(?:度假|打卡|推荐|景观)|古早味|探店|美食|悬日|落日|晚霞|艺术创作营|传统文化|闽南文化|城市.{0,8}(?:风貌|景观)", 7),
    ("economic-commercial", "经济", r"创新创业大赛|销量|商用车|产业链|商业化|招商项目|人才项目|新增订单|创业项目", 8),
    ("health-advice", "健康", r"灼伤|皮肤.{0,12}(?:过敏|留疤|损伤)|断指|转院|中毒|致病|传染|疫病|过敏", 8),
)


# A specific topic can supply otherwise absent subject information. Generic
# channel names carry less weight; tag quantity never increases its weight.
TOPIC_CHANNEL_RULES = (
    ("政策文件", r"政策文件|政策解读|实施细则|征求意见|新规"),
    ("应急", r"台风|暴雨|地震|火灾|洪水|消防救援|落水|山火|山体滑坡|炸弹威胁"),
    ("健康", r"健康|医疗|中医|流感|疫苗|疾病|癌症|养生|急救|食品安全|外科手术|名医大讲堂|中毒"),
    ("三农", r"三农|农业|农村|农民|乡村振兴|丰收|春耕|秋收|菌草"),
    ("环境生态", r"生态保护|环境保护|生物多样性|野生动物|海洋保护|白海豚|珊瑚礁|新物种"),
    ("经济", r"进博会|投洽会|投资贸易|招商|自贸|外贸|金融|股市|美股|税收|就业|消费市场"),
    ("科技", r"人工智能|(?<![A-Za-z])AI(?![A-Za-z])|机器人|芯片|航天|卫星|传感器|物联网|科技创新|新质生产力"),
    ("体育", r"足球|篮球|围棋|闽超|苏超|中超|奥运|亚运|乒乓|国乒|马拉松|WTT|世界杯|游泳比赛"),
    ("教育", r"教育|高考|中考|考研|招生|录取|校园生活|大学生活|开学|入学|校庆|校友|建校|特教|特需学生|教师节|课纲|课文|留学|军训"),
    ("法治", r"法治|普法|诈骗|电诈|防诈|犯罪|醉驾|酒驾|法院|判刑|判决|司法|宣判|贪污|获刑|毒品"),
    ("文娱", r"金鸡奖|金鸡百花电影节|电影节|金像奖|影视|电影|电视剧|演员|演唱会|音乐剧|短剧|综艺|歌剧|音乐会|交响乐|歌舞|厦门进入金鸡时间"),
    ("文旅", r"文旅|旅游|非遗|文博会|博物馆|周末去哪玩|美食|citywalk|风景|赏花|艺术周|悬日|落日|探店|酒店推荐"),
    ("时政", r"时政|两岸关系|两岸统一|两岸融合|两岸交流|两岸一家亲|台海|台湾光复|祖国统一|国防|国际局势|国际时讯|俄乌|中东局势|美伊|日本内阁|选举|党代会|改革开放|军事|战争|军舰|航母|美军|台军|中国海警|核武器|长征胜利|缅怀先烈"),
    ("民生", r"育儿|亲子|萌娃|萌宠|人类幼崽|家庭生活|公交|地铁|社保|医保|便民|邻里|免费停车|天气|冷空气|气温|博饼|中奖"),
)

# Match the object/action of a compound topic before its broad modifier.
# AI is a method in AI fraud/films; cross-strait is a location in food/culture.
TOPIC_COMPOUND_RULES = (
    ("法治", r"(?:AI|人工智能|网络|电信).{0,8}(?:诈骗|电诈|防诈)"),
    ("文娱", r"(?:AI|人工智能).{0,8}(?:影视|电影|短片|影像)|两岸.{0,8}(?:影视|电影|影像)"),
    ("文旅", r"两岸.{0,8}(?:美食|一味|文化|文创|非遗)|国防.{0,8}博物馆"),
    ("时政", r"国防教育|党史教育"),
    ("教育", r"医学.{0,8}教育|军训"),
    ("经济", r"(?:体育|文旅|旅游|文化|冰雪)(?:产业|经济)"),
)


def _topic_channel_hits(title, desc):
    best = {}
    for field, snippet, value in _topics(title, desc):
        compound = [(channel, pattern) for channel, pattern in TOPIC_COMPOUND_RULES if _pattern(pattern).search(value)]
        for channel, pattern in compound or TOPIC_CHANNEL_RULES:
            score = 2 if value == channel else 4 if _pattern(pattern).search(value) else 0
            if score > best.get(channel, {}).get("score", 0):
                best[channel] = dict(rule_id="channel:topic-" + channel, field=field,
                                     snippet=snippet, candidate=channel, score=score)
        for channel, _ in CHANNEL_RULES:
            if value == channel and channel not in best:
                best[channel] = dict(rule_id="channel:topic-" + channel, field=field,
                                     snippet=snippet, candidate=channel, score=2)
        if value == "两岸" and "时政" not in best:
            best["时政"] = dict(rule_id="channel:topic-时政", field=field,
                                snippet=snippet, candidate="时政", score=2)
    return list(best.values())


def _channel(title, desc):
    parts = _parts(title, desc)
    hits, scores = [], {}
    context_hits = []
    for rule, channel, pattern, weight in CONTEXT_RULES:
        match = next(((field, raw, m) for field, raw, text in parts
                      if (m := _pattern(pattern).search(re.sub("经济特区", _blank, text)
                          if channel == "经济" and re.search(r"美术作品展|书画展|画展", text) else text))), None)
        if match:
            field, raw, m = match
            context_hits.append(channel)
            hits.append(dict(rule_id="channel:" + rule, field=field, snippet=raw[m.start():m.end()], candidate=channel, score=weight))
            scores[channel] = scores.get(channel, 0) + weight
    # A performance action plus an event topic supplies additional context.
    # Independent topic fallback is handled separately below.
    for field, raw, text in parts:
        action = _pattern(r"亮相|提名|登台|献唱|主持人|表彰|入围|红毯|舞台|哽咽发言|观影|开唱|采风|侧颜|演技|剧组|影迷|主持vlog").search(text)
        topic = _pattern(r"#[^\s#]*(?:金鸡|电影节|影视)[^\s#]*").search(raw)
        if action and topic and "文娱" not in context_hits:
            for rule, m, weight in (("performance-context",action,4),("performance-topic",topic,1)):
                hits.append(dict(rule_id="channel:"+rule,field=field,snippet=raw[m.start():m.end()],candidate="文娱",score=weight))
                scores["文娱"] = scores.get("文娱",0)+weight
            context_hits.append("文娱")
    family = "民生" in context_hits and any(h["rule_id"] in ("channel:family-daily", "channel:family-dialogue") for h in hits)
    memory = any(h["rule_id"] == "channel:campus-memory" for h in hits)
    # More specific reporting contexts exclude superficial competing interpretations.
    excluded = set()
    if family and any(c in context_hits for c in ("健康", "教育", "法治", "文娱", "环境生态")):
        excluded.add("民生")
    if memory and "教育" in context_hits:
        excluded.add("文旅")
    if "时政" in context_hits:
        excluded.add("文娱")
    if "法治" in context_hits:
        excluded.add("民生")
    if "环境生态" in context_hits:
        excluded.add("民生")
    body = "\n".join(text for _, _, text in parts)
    # Compound subjects take precedence over the tool, venue or institution
    # mentioned as background. Exclusions require an explicit relationship.
    anti_fraud_research = bool(re.search(r"(?:研发|研究|开发).{0,14}(?:反诈|反诈骗).{0,8}(?:算法|模型|系统)", body))
    if anti_fraud_research:
        excluded.add("法治")
    if not anti_fraud_research and "法治" in context_hits and re.search(r"(?:AI|人工智能).{0,10}(?:诈骗|防诈)|(?:诈骗|防诈).{0,10}(?:AI|人工智能)", body, re.I):
        excluded.add("科技")
    if "时政" in context_hits and re.search(r"国防教育|军事援助", body):
        excluded.add("教育" if "国防教育" in body else "经济")
    if "健康" in context_hits and re.search(r"外科手术|手术直播|手术.{0,10}科技", body):
        excluded.add("科技")
    if "法治" in context_hits and re.search(r"骗局|刷单", body):
        excluded.add("文旅")
    if "应急" in context_hits and re.search(r"台风|暴雨|洪水|预警|救援", body):
        excluded.add("民生")
    if "环境生态" in context_hits and re.search(r"(?:红树林|栖息地|野生动物).{0,18}(?:围挡|生长受影响|保护)|保护.{0,12}(?:红树林|栖息地|野生动物)", body):
        excluded.add("文旅")
    # Resolve only explicit subject relationships, not every score tie.
    if "环境生态" in context_hits and re.search(r"珊瑚|珊瑚礁", body):
        excluded.add("三农")
    if "应急" in context_hits and re.search(r"台风|暴雨|洪水", body) and re.search(r"停航|停运|停课|停水|停电|交通瘫痪|避难|被淹", body):
        excluded.add("民生")
    if "教育" in context_hits and re.search(r"医学(?:伦理|模拟)?教育|医学.{0,6}教育大会", body):
        excluded.add("健康")
    if "时政" in context_hits and re.search(r"空袭|军演|武装.{0,16}(?:攻势|攻占)|战斗机|以军", body):
        excluded.add("应急")
    if any(h["rule_id"] == "channel:military-operation" for h in hits):
        excluded.add("科技")
    if any(h["rule_id"] == "channel:law-seizure" for h in hits):
        excluded.update(("文旅", "经济"))
    # Exhibitions supply context, but a specific medical/technology/service
    # subject within the exhibition remains the subject of that work.
    if any(c != "经济" for c in context_hits):
        for hit in hits:
            if hit["rule_id"] == "channel:economic-exhibition":
                scores["经济"] -= hit["score"] - 1
                hit["score"] = 1
    # A delegate's occupation, or a hospital reached during a police escort,
    # does not itself change the subject of the story.
    practical_subject = any(c in context_hits for c in ("健康", "科技", "教育", "文旅", "经济"))
    delegate_context = practical_subject and bool(re.search(r"党代表[^：:\n]{0,12}[：:]", body))
    for hit in hits:
        hospital_destination = (hit['rule_id'] == 'channel:health-care'
            and hit['snippet'] == '医院' and re.search(r"开道护送|交警开道|警车开道", body)
            and not re.search(r"治疗|手术|疫苗|疾病|诊疗|患者", body))
        if hospital_destination or delegate_context and hit['rule_id'] == 'channel:political-public-affairs':
            scores[hit['candidate']] -= hit['score'] - 1
            hit['score'] = 1
    # Weak entity matches alone do not classify; two independent clues can.
    for index, (channel, pattern) in enumerate(CHANNEL_RULES):
        if channel in excluded:
            continue
        seen = set()
        for field, raw, text in parts:
            masked = text
            if channel == "经济":
                masked = re.sub(r"经济舱", _blank, masked)
                if re.search(r"美术作品展|书画展|画展", text):
                    masked = re.sub(r"经济特区", _blank, masked)
            if channel == "教育":
                masked = re.sub(r"医学生|大学生物", _blank, masked)
                if family or memory: masked = re.sub(r"学校|幼儿园|中学|小学|大学|校园", _blank, masked)
            if channel == "民生": masked = re.sub(r"动物[‘’“”\s]*居民|医学生", _blank, masked)
            for m in _pattern(pattern).finditer(masked):
                token = m.group().lower()
                if token in seen: continue
                seen.add(token)
                hits.append(dict(rule_id=f"channel:lexicon-{index + 1}", field=field, snippet=raw[m.start():m.end()], candidate=channel, score=1))
                scores[channel] = scores.get(channel, 0) + 1
    hits = [h for h in hits if h["candidate"] not in excluded]
    scores = {name: score for name, score in scores.items() if name not in excluded}
    body_scores = dict(scores)
    topic_hits = _topic_channel_hits(title, desc)
    for hit in topic_hits:
        if delegate_context and hit['candidate'] == '时政' and '党代会' in hit['snippet']:
            hit = {**hit, 'score': 1}
        if hit["candidate"] in excluded:
            hit = {**hit, "score": 0}
        hits.append(hit)
        if hit["score"]:
            scores[hit["candidate"]] = scores.get(hit["candidate"], 0) + hit["score"]
    ranking = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    if not ranking or ranking[0][1] < 2:
        return "待判定", hits, scores, "频道缺少足够的主体、行为或事件线索"
    if len(ranking) > 1 and ranking[1][1] >= ranking[0][1] * .8:
        return "待判定", hits, scores, "多个频道得分接近，无法确定报道核心"
    winner = ranking[0][0]
    conflict = any(hit["candidate"] != winner for hit in topic_hits)
    reason = "话题标签与正文线索不一致，按正文明确线索判定" if conflict and body_scores.get(winner, 0) >= 7 else ""
    return winner, hits, scores, reason


# Explicit, limited aliases; no fuzzy matching of unknown or homonymous names.
PLACE_ALIASES = {"厦门市": "本地", "厦门站": "本地", "厦门北站": "本地", "厦门高崎机场": "本地",
                 "厦门国际会展中心": "本地", "厦门奥体中心": "本地", "环岛路": "待判定", "中山路": "待判定",
                 "中山": "国内", "鼓浪屿": "本地", "高崎机场": "本地", "白鹭洲公园": "本地", "小嶝岛": "本地",
                 "蒙古国": "国际", "坦桑尼亚": "国际", "桑给巴尔": "国际", "也门": "国际", "约旦": "国际",
                 "马尔代夫": "国际", "马德里": "国际", "安达卢西亚": "国际", "名古屋": "国际",
                 "巴布亚新几内亚": "国际", "巴新": "国际", "塞尔维亚": "国际", "保加利亚": "国际",
                 "马里兰州": "国际", "基辅": "国际", "里昂": "国际", "中东": "国际", "缅北": "国际",
                 "厦门翔安国际机场": "本地", "五缘湾": "本地", "筼筜湖": "本地"}
PLACE_GROUPS = {"本地": LOCAL, "本省": PROVINCE, "国内": DOMESTIC, "国际": INTERNATIONAL}
PLACE_LOOKUP = {place: group for group, pattern in PLACE_GROUPS.items() for place in pattern.split('|')} | PLACE_ALIASES
PLACE_PATTERN = _pattern('|'.join(sorted(PLACE_LOOKUP, key=len, reverse=True)))
EVENT_ACTION = r"(?:发生|开展|举办|发布|公布|实施|启动|新增|迎来|迎接|迎|启航|开跑|旅游|地震|火灾|预警|救援|招生|停水|停电|经济|医院|法院|马拉松|生态|居民|游客|动物)"


def _topic_region_hits(title, desc):
    hits = []
    for field, snippet, value in _topics(title, desc):
        matches = list(PLACE_PATTERN.finditer(value))
        remainder = PLACE_PATTERN.sub('', value)
        if not matches or re.sub(r"[省市区县·/／\-\s]", '', remainder):
            # Explicit scope tags are weaker than a place, not event locations.
            if value in ("国际新闻", "国内新闻"):
                hits.append(dict(rule_id="region:topic-scope",field=field,snippet=snippet,
                    candidate="国际" if value == "国际新闻" else "国内",score=1,place=value))
            continue
        known = [m for m in matches if PLACE_LOOKUP[m.group()] != "待判定"]
        for match in known:
            group = PLACE_LOOKUP[match.group()]
            if match.group() in ("福建", "中国", "我国", "全国", "国内") and any(
                PLACE_LOOKUP[other.group()] in (("本地", "本省") if match.group() == "福建" else ("本地", "本省", "国内"))
                for other in known if other != match):
                continue
            hits.append(dict(rule_id="region:topic-place",field=field,snippet=snippet,
                candidate=group,score=2,place=match.group()))
    # Generic parent tags do not compete with an explicitly narrower place.
    return [hit for hit in hits if not (
        hit['place'] == "福建" and any(other['candidate'] in ("本地", "本省") and other['place'] != "福建" for other in hits)
        or hit['place'] in ("中国", "我国", "全国", "国内") and any(other['candidate'] in ("本地", "本省", "国内") and other['place'] not in ("中国", "我国", "全国", "国内") for other in hits)
        or hit['rule_id'] == "region:topic-scope" and any(other['rule_id'] == "region:topic-place" for other in hits))]


def _region(title, desc):
    hits, excluded = [], []
    for field, raw, text in _parts(title, desc):
        text = re.sub(r"厦门(?:广电|卫视)|看厦门|海西晨报", _blank, text)
        text = re.sub(r"韩国瑜|孙中山|金华(?=[、， ]|说)|东山再起|首尔大学|福建舰", _blank, text)
        text = re.sub(r"中国(?:梦|画|风|电影|歌剧节|国际短视频大赛)|爱我国防|全国(?:范围)?(?=.{0,8}(?:哀悼|罢工|抗议))", _blank, text)
        matches = list(PLACE_PATTERN.finditer(text))
        for m in matches:
            place = m.group(); group = PLACE_LOOKUP[place]
            before, after = text[max(0,m.start()-16):m.start()], text[m.end():m.end()+20]
            event_preposition = re.search(r"(?:在|赴|于|到|抵达|来到|走进|事发|发生于|位于)\s*$", before)
            identity = re.search(r"(?:来自|祖籍|籍贯|出生于|生于|产自|源自|援助来自)\s*$", before)
            identity = identity or re.match(r"(?:籍|裔|人(?:士|民)?(?:在|到|赴)|游客|记者(?:在|到|赴|报道)|媒体(?:报道|关注)|驻|援助|技术|首相|总统|国籍|电影金鸡奖|电影节)", after)
            publisher = re.match(r"(?:广电|卫视|日报|晚报|晨报|电视台|新闻网)", after)
            team = re.match(r"(?:队|籍|选手|代表队)", after)
            institution = re.search(r"驻[^，。！？\n]{0,10}$", before) or re.match(r"(?:大使馆|领事馆|大学|中学|小学|企业|公司|银行)(?![，。！？])", after)
            # Universities and firms may be actual locations only with explicit locative cues.
            if identity or publisher or team or institution and not event_preposition:
                role = ("reporting_source" if publisher or re.match(r"(?:记者|媒体)", after)
                        else "institution_location" if institution or re.match(r"驻", after)
                        else "material_origin" if re.match(r"(?:的)?(?:菌草|技术|种子|产品|物产|物资|援助)", after)
                             or re.search(r"(?:产自|源自)\s*$", before)
                        else "person_origin")
                excluded.append(dict(rule_id="region:background",field=field,snippet=place,candidate=group,
                                     score=0,place=place,role=role))
                continue
            if group == "待判定":
                excluded.append(dict(rule_id="region:homonym",field=field,snippet=place,candidate=group,score=0))
                continue
            # A broad province/country immediately qualifying a city is background hierarchy.
            if group in ("本省", "国内") and any(0 <= other.start()-m.end() <= 2
                    and PLACE_LOOKUP[other.group()] in ("本地", "本省") for other in matches if other is not m):
                continue
            # Presence alone is weak; explicit locative cue or event subject is stronger.
            action = re.match(r"(?:市|省|区|县)?[：:，,\s]*" + EVENT_ACTION, after)
            score = 6 if event_preposition else 4 if action else 2
            hits.append(dict(rule_id="region:event-location" if event_preposition else "region:event-subject" if action else "region:place",
                             field=field,snippet=raw[m.start():m.end()],candidate=group,score=score,place=place,
                             role="event_location" if event_preposition or action else "associated_place"))
    topic_hits = _topic_region_hits(title, desc)
    topic_conflict = False
    if not hits:
        hits.extend(topic_hits)
    else:
        body_candidates = {hit['candidate'] for hit in hits}
        for hit in topic_hits:
            if hit['candidate'] not in body_candidates:
                excluded.append({**hit,'rule_id':'region:topic-conflict','score':0})
                topic_conflict = True
    scores = {}
    for hit in hits: scores[hit["candidate"]] = max(scores.get(hit["candidate"],0),hit["score"])
    ranking = sorted(scores.items(),key=lambda pair:(-pair[1],pair[0]))
    if not ranking:
        return "待判定", hits + excluded, scores, "缺少明确事件地点或有效地域标签；来源、署名及人物属性不作地点证明"
    if len(ranking)>1 and ranking[0][1]-ranking[1][1]<3:
        return "待判定", hits + excluded, scores, "涉及多个地域且无法确定主要发生地或影响范围"
    return ranking[0][0], hits + excluded, scores, "地域标签与正文线索不一致，保留正文地域判定" if topic_conflict else ""


@lru_cache(maxsize=8192)
def _classify(title, desc):
    channel, channel_hits, channel_scores, channel_reason = _channel(title, desc)
    region, region_hits, region_scores, region_reason = _region(title, desc)
    fields = [field for field,value in (("channel",channel),("region",region)) if value == "待判定"]
    hits = channel_hits + region_hits
    def evidence(field,value):
        matching = [h for h in hits if h["candidate"]==value and h["rule_id"].startswith(field+':') and h['score']>0]
        return max(matching,key=lambda h:h['score'])['snippet'] if value!='待判定' and matching else ''
    reasons = list(filter(None,(channel_reason,region_reason)))
    result = {"channel":channel,"region":region,"channel_evidence":evidence('channel',channel),
            "region_evidence":evidence('region',region),"tag_method":"rules_v3","tag_status":"uncertain" if fields else "resolved",
            "ambiguous_fields":fields,"tag_reasons":reasons,"tag_reason":"；".join(reasons),
            "tag_rule_version":RULE_VERSION,"tag_scores":{"channel":channel_scores,"region":region_scores},
            "tag_rule_hits":hits,"tag_confidence":{},"classification_mode":"automatic_rules",
            "ai_reviewed_fields":[],"tag_experience_refs":[],"visual_sources":[],"visual_status":None}
    from .editorial_taxonomy import enrich_classification
    return enrich_classification(result, _parts(title, desc), list(_topics(title, desc)),
                                 PLACE_PATTERN, PLACE_LOOKUP, _without_credits)


def classify_post(title: str = "", desc: str = "") -> dict:
    return deepcopy(_classify(title or "", desc or ""))


def assess_post(title: str = "", desc: str = "") -> dict:
    """Compute independent labels; uncertainty is final, never an inference queue."""
    return classify_post(title, desc)
