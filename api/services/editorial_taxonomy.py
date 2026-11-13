"""Secondary labels and diagnostic reasons; no IO and no publisher inference."""
import re


PENDING_REASONS = {
    "insufficient_clues": "没有有效线索",
    "rule_conflict": "多个规则冲突",
    "location_role_unclear": "地点角色不明确",
    "lexicon_gap": "题材或地点词典未覆盖",
}
LOCATION_ROLES = {
    "event_location": "事件发生地", "associated_place": "关联地点",
    "person_origin": "人物籍贯或身份", "institution_location": "机构所在地",
    "material_origin": "技术或物产来源",
    "reporting_source": "报道来源", "ambiguous_place": "地点歧义",
}

# Labels are scoped to the resolved primary channel. A secondary label never
# resolves an uncertain primary, and irrelevant hashtags cannot override prose.
SUBTOPICS = {
    "民生": (("家庭育儿", r"亲子|育儿|萌娃|宝宝|父母|哄娃|人类幼崽|孩子|妈妈|爸爸"),
           ("社区生活", r"社区|邻里|小区|物业|电梯|博饼"),
           ("公共服务", r"公交|地铁|交通|车管所|停水|停电|停车|航班|航线|公共服务|便民"),
           ("社会保障", r"养老|社保|医保|住房"), ("天气生活", r"天气|气温|降温|冷空气|阵雨"),
           ("消费生活", r"快递|消费维权|投诉|收费|彩票|中奖")),
    "时政": (("国内政务", r"总书记|国务院|两会|人大|政协|全会|党代会"),
           ("国际关系", r"外交|总统|首相|联合国|内阁|选举|议会|政党"),
           ("军事国防", r"国防|军事|军演|战争|袭击|导弹|军舰|航母|空袭|国防教育"),
           ("两岸事务", r"两岸|国台办|台海|台湾光复|祖国统一")),
    "经济": (("产业发展", r"产业|企业|商用车|供应链|商业化|创新创业"),
           ("贸易招商", r"外贸|进博会|投洽会|招商|进出口|出口|进口|自贸"),
           ("金融市场", r"金融|股市|股价|股票|国债|货币政策"),
           ("消费就业", r"消费|就业|工资|销量"), ("体育经济", r"体育(?:经济|产业)|冰雪(?:经济|产业)")),
    "科技": (("人工智能", r"人工智能|大模型|机器人|智能体|(?<![A-Za-z])AI(?![A-Za-z])"),
           ("航天探索", r"航天|卫星|火箭|空间站|深空"),
           ("技术研发", r"芯片|半导体|量子|研发|科研|算法|传感器|软件|输入法")),
    "教育": (("招生考试", r"招生|高考|中考|考研|录取|学位|入学"),
           ("校园教学", r"课堂|教学|教材|教师|课桌|课纲|校园|校庆|军训"),
           ("特殊教育", r"特教|特需学生|特殊教育"), ("家庭教育", r"家庭教育|手机成瘾|陪读")),
    "健康": (("诊疗救治", r"医院|医疗|患者|治疗|手术|转院|断指|急救"),
           ("疾病预防", r"疫苗|流感|疾控|传染|疾病|防病"),
           ("健康科普", r"养生|健康|过敏|皮肤|医学知识|科普"),
           ("食品药品", r"食品|药品|保健品|铅超标|中毒")),
    "体育": (("球类赛事", r"足球|篮球|网球|乒乓|国乒|羽毛球|闽超|苏超|联赛|WTT"),
           ("综合赛事", r"奥运|全运会|亚运|世锦赛|锦标赛"),
           ("全民健身", r"健身|马拉松|工间操|太极"), ("棋类竞技", r"围棋|棋手")),
    "文旅": (("旅游休闲", r"旅游|游客|景区|旅行|酒店|民宿|citywalk|打卡"),
           ("文化非遗", r"非遗|文物|博物馆|文化|古建筑|古厝|文博会"),
           ("美食探店", r"美食|探店|古早味|小吃|夜市|两岸一味"),
           ("城市风光", r"朝霞|晚霞|落日|悬日|花海|三角梅|风光|风貌|老照片|旧照")),
    "文娱": (("影视作品", r"电影|影视|电视剧|短剧|短片|票房|导演"),
           ("节展奖项", r"金鸡奖|金像奖|金马奖|电影节|颁奖|提名"),
           ("音乐演出", r"音乐|歌剧|演唱会|演奏|交响乐|歌手|新歌|专辑|戏曲|京剧|舞剧")),
    "三农": (("农业生产", r"农业|农田|粮食|种植|种菇|菌草|养殖|渔业|丰收|春耕|秋收"),
           ("乡村发展", r"乡村|农村|农民|振兴")),
    "法治": (("诈骗防范", r"诈骗|电诈|防诈|骗局|刷单"),
           ("案件司法", r"法院|起诉|诉讼|判决|判刑|宣判|获刑|死刑|刑事"),
           ("执法安全", r"酒驾|醉驾|毒驾|查处|海关|查获|拘留|执法"),
           ("普法服务", r"普法|法律援助|法律服务")),
    "政策文件": (("政策发布", r"印发|发布通知|条例|新规|管理办法"),
             ("政策解读", r"政策解读|实施细则"), ("意见征集", r"征求意见")),
    "应急": (("灾害预警", r"预警|台风|暴雨|洪水|地震|山洪|泥石流"),
           ("事故救援", r"火灾|火情|事故|爆炸|救援|落水|被困|失联|坍塌")),
    "环境生态": (("物种保护", r"物种|野生动物|白海豚|濒危|生物多样性|候鸟"),
             ("生态修复", r"生态|湿地|珊瑚|红树林|栖息地"),
             ("环保行动", r"环保|污染|垃圾分类|净滩|守护海洋|碳排放")),
}


def enrich_classification(result, parts, topics, place_pattern, place_lookup, without_credits):
    sub_hits = []
    for label, pattern in SUBTOPICS.get(result["channel"], ()):
        matches = []
        for field, raw, body in parts:
            match = re.search(pattern, body, re.I)
            if match:
                matches.append(dict(field=field, snippet=raw[match.start():match.end()]))
        # If the primary has explicit prose support, do not add hashtag-only
        # angles. Otherwise a topic-only work may have secondary topic labels.
        body_supported = any(h["score"] >= 7 and not h["rule_id"].startswith("channel:topic-")
                             for h in result["tag_rule_hits"] if h["candidate"] == result["channel"])
        if not matches and not body_supported:
            matches = [dict(field=field, snippet=snippet) for field, snippet, value in topics
                       if re.search(pattern, value, re.I)]
        if matches:
            sub_hits.append(dict(label=label, rule_id=f"subtopic:{result['channel']}:{label}", **matches[0]))
    result["channel_subtopics"] = [hit["label"] for hit in sub_hits]
    result["channel_subtopic_hits"] = sub_hits

    locations = []
    for hit in result["tag_rule_hits"]:
        if not hit["rule_id"].startswith("region:"):
            continue
        role = hit.get("role", "ambiguous_place" if hit["candidate"] == "待判定" else "associated_place")
        locations.append(dict(place=hit.get("place", hit["snippet"]), region=hit["candidate"],
                              role=role, role_label=LOCATION_ROLES[role], field=hit["field"],
                              snippet=hit["snippet"], rule_id=hit["rule_id"], used=hit["score"] > 0))
    # Record an explicit source's geographic name for explanation only; it
    # remains masked from channel/region scoring, as do staff signatures.
    for field, raw, _ in parts:
        masked = without_credits(raw)
        for match in place_pattern.finditer(raw):
            before = raw[max(0, match.start()-24):match.start()]
            if (not masked[match.start():match.end()].strip()
                    and re.search(r"(?:来源|供稿)\s*[:：/／@]\s*[^（）()\n]{0,12}$", before)):
                locations.append(dict(place=match.group(), region=place_lookup[match.group()],
                    role="reporting_source", role_label=LOCATION_ROLES["reporting_source"],
                    field=field, snippet=match.group(), rule_id="region:credit-source", used=False))
    result["region_locations"] = locations
    pending = []
    for field in result["ambiguous_fields"]:
        scores = result["tag_scores"][field]
        if len(scores) > 1 and (field == "region" or max(scores.values(), default=0) >= 2):
            code = "rule_conflict"
        elif field == "region" and any(place["role"] != "reporting_source" for place in locations):
            code = "location_role_unclear"
        else:
            body = " ".join(part[2] for part in parts)
            meaningful = re.sub(r"这一幕|令人感动|一起关注|消息|突发|正能量|暖心|[\W\d_]", "", body)
            # Diagnostic wording is a rule coverage gap, never a fabricated
            # assertion of the actual topic or place.
            gap = len(meaningful) >= 4 if field == "channel" else bool(re.search(r"(?:在|事发|位于)[\u4e00-\u9fff]{2,12}", body))
            code = "lexicon_gap" if gap else "insufficient_clues"
        pending.append(dict(field=field, code=code, label=PENDING_REASONS[code]))
    result["tag_pending_reasons"] = pending
    return result
