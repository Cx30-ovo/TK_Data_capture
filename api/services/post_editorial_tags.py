"""Conservative, explainable editorial tags derived from collected text.

No publisher location is used. Tags are computed on read so existing and newly
collected works share the same rules without a database backfill.
"""
import re
from functools import lru_cache


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
INTERNATIONAL = "海外|国外|美国|日本|韩国|朝鲜|俄罗斯|乌克兰|以色列|巴勒斯坦|加沙|伊朗|伊拉克|叙利亚|黎巴嫩|英国|法国|德国|意大利|西班牙|荷兰|瑞士|瑞典|挪威|芬兰|波兰|土耳其|印度|巴基斯坦|泰国|越南|缅甸|柬埔寨|老挝|新加坡|马来西亚|菲律宾|印度尼西亚|印尼|澳大利亚|新西兰|加拿大|墨西哥|巴西|阿根廷|南非|埃及|沙特|阿联酋|斐济|阿富汗|孟加拉|尼泊尔|斯里兰卡|纽约|华盛顿|东京|首尔|伦敦|巴黎|莫斯科|特朗普|普京|泽连斯基|内塔尼亚胡"
REGION_RULES = tuple((name, re.compile(pattern, re.I)) for name, pattern in (
    ("本地", LOCAL), ("本省", PROVINCE), ("国内", DOMESTIC), ("国际", INTERNATIONAL)
))


def _body(text: str) -> str:
    # Credits and publisher hashtags are not evidence of the event's location.
    text = re.split(r"(?:来源|视频来源|记者|编辑|采编|摄像|通讯员|供稿)\s*[:：/|]|[（(](?:来源|记者|编辑|采编)", text)[0]
    text = re.sub(r"厦门(?:广电|卫视)", "", text)
    return re.sub(r"#[^\s#]+|@[^\s@]+|https?://\S+", " ", text).strip()


def _channel_scores(title: str, desc: str):
    # Count complete alternatives once; avoid counting 学生 inside 医学生 or
    # treating animal “residents” and economy-class seats as news categories.
    parts = [(title, 3), (desc if desc != title else "", 1)]
    scores = []
    for name, pattern in CHANNEL_RULES:
        score = 0
        for part, weight in parts:
            if name == "民生":
                part = re.sub(r"医学生|动物[‘’“”\s]*居民", "", part)
            elif name == "经济":
                part = part.replace("经济舱", "")
            elif name == "教育":
                part = re.sub(r"医学生|大学生物", "", part)
            score += len(re.findall(pattern, part, re.I)) * weight
        scores.append((score, name))
    return scores


@lru_cache(maxsize=8192)
def classify_post(title: str = "", desc: str = "") -> dict:
    title_text, desc_text = _body(title or ""), _body(desc or "")
    scored = _channel_scores(title_text, desc_text)
    # No catch-all channel: content without evidence awaits review.
    score, channel = max(scored, key=lambda item: item[0])
    if not score:
        channel = "待判定"
    region, evidence = "待判定", ""
    # Prefer the headline's first explicit location (event subject), then body.
    for part in (title_text, desc_text):
        # Explicit event location beats a visitor's nationality or wider province.
        location = re.search(r"(?:在|到|赴|于|事发|走进)(" + LOCAL + "|" + PROVINCE + "|" + DOMESTIC + "|" + INTERNATIONAL + ")", part)
        if location:
            evidence = location.group(1)
            region = next(name for name, pattern in REGION_RULES if pattern.fullmatch(evidence))
            break
        matches = [(match.start(), -len(match.group()), name, match.group())
                   for name, pattern in REGION_RULES
                   if (match := pattern.search(part))]
        if matches:
            _, _, region, evidence = min(matches)
            break
    return {"channel": channel, "region": region, "region_evidence": evidence,
            "tag_method": "text_rules_v1"}


def assess_post(title: str = "", desc: str = "") -> dict:
    """Identify ambiguity independently for channel and region before AI review."""
    result = dict(classify_post(title, desc))
    parts = list(dict.fromkeys((_body(title or ""), _body(desc or ""))))
    text = "\n".join(parts)
    scores = sorted(_channel_scores(_body(title or ""), _body(desc or "")))
    top, runner = scores[-1][0], scores[-2][0]
    reasons, fields = [], []
    if not top or (runner and runner / top >= .6):
        fields.append("channel")
        reasons.append("频道依据不足或多个频道冲突")
    if re.search(r"经济舱|动物.{0,8}居民|生物圈", text) and not top:
        fields.append("channel")
        reasons.append("频道关键词可能具有其他含义")
    # These words identify context for semantic review, not a forced channel.
    # A school anecdote may be everyday life; a baby's hospital visit is health.
    if re.search(r"家庭|亲子|育儿|萌娃|宝宝|宝妈|宝爸|爸妈|妈妈|爸爸|父母|亲情|学步", text):
        fields.append("channel")
        reasons.append("家庭生活与健康、教育、文娱等频道需要按核心内容区分")
    if (re.search(r"学校|中学|小学|大学|校园", text)
            and re.search(r"旧照|旧日|怀旧|青春|回忆|老照片|泛黄|旧时", text)):
        fields.append("channel")
        reasons.append("校园历史记忆与教学招生需要按核心内容区分")
    if re.search(r"籍贯|祖籍|出生于|来自", text):
        fields.append("region")
        reasons.append("地点可能描述人物属性")
    regions = {name for name, pattern in REGION_RULES if pattern.search(text)}
    if len(regions) != 1:
        fields.append("region")
        reasons.append("缺少明确地点或涉及多个地域")
    # Country names embedded in people's names do not establish event location.
    if re.search(r"韩国瑜|金华[、， ]|驻.{0,12}(?:大使|领事)", text):
        fields.append("region")
        reasons.append("地名可能属于姓名或机构背景")
    fields = list(dict.fromkeys(fields))
    return {**result, "tag_method": "rules_v2", "tag_status": "pending" if fields else "resolved",
            "ambiguous_fields": fields, "tag_reasons": reasons}
