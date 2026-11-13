import pytest

from api.services.post_editorial_tags import assess_post, classify_post


@pytest.mark.parametrize("title,desc,channel,region", [
    ("厦门新增公交线路", "", "民生", "本地"),
    ("集美居民停车更方便", "", "民生", "本地"),
    ("福州医院开展健康义诊", "", "健康", "本省"),
    ("福建发布台风预警", "", "应急", "本省"),
    ("福建发布经济发展数据", "", "经济", "本省"),
    ("厦门的动物“居民”，共同守护生物圈和栖息地", "", "环境生态", "本地"),
    ("【厦门中华白海豚，竟然有个千人“后援团”！】从2016年的10人，到如今1116人，这群特别的“粉丝”，把对白海豚的喜欢，变成了一场持续十年的温柔守护💙净滩、科普、守护海洋……", "(采编/静涵 纪腾 责编/又华 编审/贤云 琳煜) #向海而生 #中华白海豚 #海洋生物多样性 #厦门", "环境生态", "本地"),
    ("厦门医学生学习医学知识", "", "健康", "本地"),
    ("厦门航空经济舱服务升级", "", "民生", "本地"),
    ("厦门车管所民警助力车辆查验", "", "民生", "本地"),
    ("泉州游客到厦门旅游", "", "文旅", "本地"),
    ("福建首条航线在厦门启航", "", "民生", "本地"),
    ("跟随厦门广电走进斐济体验旅游", "", "文旅", "国际"),
    ("美国发生火灾 #厦门", "来源：厦门广电", "应急", "国际"),
    ("日本游客到厦门旅游", "", "文旅", "本地"),
    ("厦门迎来日本游客", "", "文旅", "本地"),
    ("台湾启动地震救援", "", "应急", "国内"),
    ("香港举办文化展览", "", "文旅", "国内"),
    ("北京发布管理办法", "", "政策文件", "国内"),
    ("乡村秋收迎丰收", "", "三农", "待判定"),
    ("这一幕令人感动 #厦门", "（来源：厦门广电）", "待判定", "本地"),
    ("突发消息", "泉州开展湿地生态修复", "环境生态", "本省"),
    (None, None, "待判定", "待判定"),
    ("微信输入法支持闽南话识别", "", "科技", "待判定"),
    ("我国新型芯片研发取得突破", "", "科技", "国内"),
    ("国乒包揽WTT冠军赛女单四强", "", "体育", "待判定"),
    ("厦门马拉松鸣枪开跑", "", "体育", "本地"),
    ("厦门公布幼儿园招生安排", "", "教育", "本地"),
    ("大学教师开展教研活动", "", "教育", "待判定"),
    ("男子错过兑奖期起诉索赔被法院驳回", "", "法治", "待判定"),
    ("厦门开展法律援助普法活动", "", "法治", "本地"),
    ("歌手发布新歌和专辑", "", "文娱", "待判定"),
    ("电视剧定档引发关注", "", "文娱", "待判定"),
    ("厦门文博会展示非遗文化", "", "文旅", "本地"),
    ("台湾民众公开集会，抗议右翼势力借影视作品扭曲历史", "", "时政", "国内"),
])
def test_tags(title, desc, channel, region):
    result = classify_post(title, desc)
    assert result["channel"] == channel
    assert result["region"] == region
    assert bool(result["region_evidence"]) == (region != "待判定")


@pytest.mark.parametrize("title,initial_channel", [
    ("妈妈：叫妈妈！宝宝：爸爸！我不仅叫爸，我还字正腔圆", "民生"),
    ("一岁萌娃迈出人生第一步，跌跌撞撞走向父母", "民生"),
    ("厦门幼儿园萌娃向爸爸展示自己的玩具", "民生"),
    ("妈妈带宝宝到厦门医院治疗", "健康"),
    ("厦门幼儿园向父母公布招生安排", "教育"),
    ("厦门法院审理父母抚养权诉讼", "法治"),
    ("电视剧里的妈妈和宝宝迎来大结局", "文娱"),
    ("厦门双十中学的旧日风华，泛黄画里有青春", "文旅"),
    ("厦门中学公开旧照用于历史课堂教学", "教育"),
    ("厦门学校的老照片唤起青春回忆", "文旅"),
    ("野生动物与幼崽相依的亲情", "环境生态"),
])
def test_context_combinations_resolve_without_review(title, initial_channel):
    initial = classify_post(title)
    assessed = assess_post(title)
    assert initial["channel"] == initial_channel
    assert assessed["channel"] == initial_channel
    assert "channel" not in assessed["ambiguous_fields"]
    assert assessed["tag_status"] in ("resolved", "uncertain")
    assert assessed["classification_mode"] == "automatic_rules"


def test_family_words_in_credits_and_trailing_hashtags_do_not_create_review_context():
    assessed = assess_post("厦门新增公交线路", "（编辑/妈妈）#宝宝 #育儿")
    assert assessed["channel"] == "民生"
    assert assessed["ambiguous_fields"] == []


@pytest.mark.parametrize("title,region", [
    ("福建菌草技术在斐济帮助当地种菇", "国际"),
    ("来自福建的菌草，如何在斐济长出一门蘑菇生意？", "国际"),
    ("厦门媒体报道日本地震", "国际"),
    ("日本游客在厦门旅游", "本地"),
    ("厦门迎来日本游客", "本地"),
    ("美国籍游客在厦门游玩", "本地"),
    ("祖籍福建的人士在北京开展活动", "国内"),
    ("中国驻日本大使馆发布消息", "待判定"),
    ("韩国瑜出席活动", "待判定"),
    ("张金华、李明出席活动", "待判定"),
    ("第39届中国电影金鸡奖公布名单", "待判定"),
    ("福建舰完成试验", "待判定"),
    ("中山路开展活动", "待判定"),
    ("环岛路交通管制", "待判定"),
    ("厦门中山路举办活动", "本地"),
    ("北京与上海同步开展招生", "国内"),
    ("厦门与福州同时举办活动", "待判定"),
    ("在厦门举办活动，在斐济同步举行活动", "待判定"),
    ("厦门举行活动，福州同步举办活动", "待判定"),
    ("在厦门举办文化活动", "本地"),
    ("福建厦门新增公交线路", "本地"),
    ("江西卫视报道了这件事", "待判定"),
    ("来源于生活的趣事（来源/看厦门 编辑/小林） #福建", "本省"),
    ("日本首相在北京出席活动", "国内"),
    ("福建籍演员参加活动", "待判定"),
    ("在厦门高崎机场新增航线", "本地"),
    ("微信输入法支持闽南话识别", "待判定"),
])
def test_event_location_background_and_conflict(title,region):
    result=assess_post(title)
    assert result["region"]==region
    assert ("region" in result["ambiguous_fields"])==(region=="待判定")


@pytest.mark.parametrize("title,desc,channel", [
    ("家庭育儿趣事，孩子在家逗父母开心", "", "民生"),
    ("宝宝迈出第一步走向妈妈", "", "民生"),
    ("宠物陪伴家人度过日常", "", "民生"),
    ("妈妈带宝宝到医院治疗", "", "健康"),
    ("父母争夺抚养权，法院作出判决", "", "法治"),
    ("台风预警与医院治疗同为新闻重点", "", "待判定"),
    ("电影演员参加电视剧宣传", "", "文娱"),
    ("一所学校", "", "待判定"),
    ("这一幕", "#教育 #健康", "待判定"),
    ("新闻（来源/体育新闻 编辑/医生）", "", "待判定"),
    ("邻里生活日常（编辑/经济 来源/科技日报）", "", "民生"),
    ("金鸡奖提名者表彰仪式", "", "文娱"),
    ("某演员亮相金鸡生活季", "", "文娱"),
    ("嘉宾哽咽发言 #中国金鸡百花电影节", "", "文娱"),
    ("嘉宾哽咽发言 #民生", "", "民生"),
    ("#中国金鸡百花电影节", "", "文娱"),
    ("男子酒驾上高速被交警查处", "", "法治"),
    ("快递公共服务改善", "", "民生"),
    ("卫星研发取得突破", "", "科技"),
])
def test_scoring_exclusions_and_insufficient_material(title,desc,channel):
    assert assess_post(title,desc)["channel"]==channel


@pytest.mark.parametrize("title,desc", [
    ("日本游客在厦门旅游", "（来源/看厦门 编辑/小陈）"),
    ("妈妈：叫妈妈！宝宝：爸爸！", "家庭育儿日常"),
    ("厦门与福州同步举办活动", "旅游活动"),
    ("新闻（来源/国外媒体）", "健康科普，医院医生介绍治疗过程"),
])
def test_every_rule_hit_is_verbatim_and_versioned(title,desc):
    result=assess_post(title,desc)
    for hit in result["tag_rule_hits"]:
        assert hit["snippet"] in {"title":title,"desc":desc}[hit["field"]]
        assert hit["rule_id"] and hit["score"]>=0
    assert result["tag_rule_version"] and result["tag_confidence"]=={}
    assert result["tag_status"]!="pending"


def test_repetition_and_cache_mutation_do_not_change_decision():
    sample="厦门新增公交线路"
    before=assess_post(sample)
    mutated=assess_post(sample)
    mutated["tag_scores"]["channel"]["民生"]=999
    mutated["tag_rule_hits"].clear()
    assert assess_post(sample)==before
    assert assess_post(sample*10)["tag_scores"]["channel"]==before["tag_scores"]["channel"]


@pytest.mark.parametrize("title,channel,region", [
    ("据报道，#美国总统特朗普 今天发表讲话。#国际新闻", "时政", "国际"),
    ("他接替前任出任#白宫新闻秘书。扎卡里亚今天发布声明。", "时政", "待判定"),
    ("当地传来消息，#日本 发生地震，救援正在进行。#厦门", "应急", "国际"),
    ("今天在#厦门 医院开展治疗。#福建#北京", "健康", "本地"),
    ("#教育#健康", "待判定", "待判定"),
    ("这一幕令人感动 #经济#厦门#国际新闻", "经济", "本地"),
    ("这一幕令人感动 #经济 #健康 （见习编辑/医生 责编/福建）", "待判定", "待判定"),
    ("新闻（画面来源/厦门医院 见习编辑/经济）", "待判定", "待判定"),
    ("投洽会回顾首次在厦门国际博览中心举办的盛况", "经济", "本地"),
    ("历九弥新！探展进博会的老朋友", "经济", "待判定"),
    ("主播探自贸！走进厦门自贸片区", "经济", "本地"),
    ("高市内阁全体阁僚辞职", "时政", "待判定"),
    ("国防部回应祖国统一问题", "时政", "待判定"),
    ("台湾光复，铭记抗争岁月", "时政", "国内"),
    ("军营迎来入伍女兵", "时政", "待判定"),
    ("围棋冠军讲围棋", "体育", "待判定"),
    ("闽超甲级组决赛精彩进行", "体育", "待判定"),
    ("跳水队运动员获奖", "体育", "待判定"),
    ("机票价格跳水！厦门出发航线降价", "民生", "本地"),
    ("退休后考研成功录取", "教育", "待判定"),
    ("研发传感器和物联网创新技术", "科技", "待判定"),
    ("全球将停止插入闰秒", "科技", "待判定"),
    ("人类幼崽默契日常，弟弟展示垃圾桶头盔，哥哥配合", "民生", "待判定"),
    ("橘猫把消防员当猫爬架", "民生", "待判定"),
    ("儿童眼镜标价1980元，岂能收割育儿焦虑", "民生", "待判定"),
    ("男子落水被困，民警抢回一命", "应急", "待判定"),
    ("蒙古国火情逼近，正在堵截", "应急", "国际"),
    ("列车相撞发生事故，多人受伤", "应急", "待判定"),
    ("猫科物种增加，命名蒂尔卡约虎猫", "环境生态", "待判定"),
    ("产品铅超标被召回，提醒立即停用", "健康", "待判定"),
    ("美术作品展展示厦门经济特区建设历程", "文旅", "本地"),
    ("翔安花海浪漫上线，定格秋日氛围", "文旅", "本地"),
    ("从古老的海上商路，了解文化交汇印记", "文旅", "待判定"),
    ("温柔开唱，现场热闹", "文娱", "待判定"),
    ("观影团活动开始", "文娱", "待判定"),
    ("某嘉宾侧颜出镜 #中国金鸡百花电影节", "文娱", "待判定"),
    ("某嘉宾侧颜出镜 #民生", "民生", "待判定"),
    ("某嘉宾 #中国金鸡百花电影节", "文娱", "待判定"),
    ("投洽会上中医特色诊疗受到欢迎", "健康", "待判定"),
    ("投洽会亮相多款机器人", "科技", "待判定"),
    ("国台办回应投洽会两岸融合发展", "时政", "待判定"),
    ("厦门交警为投洽会进行交通管控", "民生", "本地"),
    ("空袭引发爆炸，战斗机发动攻势", "时政", "待判定"),
    ("斐济开展珊瑚种植，修复珊瑚礁生态", "环境生态", "国际"),
    ("厦门医院举办医学模拟教育大会", "教育", "本地"),
    ("台风导致厦门客运航线停航", "应急", "本地"),
    ("厦门海关在出口包裹中查获文物", "法治", "本地"),
    ("中国研发新型无人机取得进展", "科技", "国内"),
    ("俄军无人机袭击目标", "时政", "待判定"),
    ("无人机战术与战争局势", "时政", "待判定"),
    ("发生空袭，随后传出爆炸声", "时政", "待判定"),
    ("厦门经济特区建设拉开序幕", "经济", "本地"),
    ("投洽会逛展吃遍八闽美食", "文旅", "待判定"),
    ("暴雨导致山体滑坡，交通瘫痪", "应急", "待判定"),
])
def test_coverage_extensions_preserve_boundaries_and_raw_evidence(title,channel,region):
    result=assess_post(title)
    assert result["channel"]==channel
    assert result["region"]==region
    assert result["tag_rule_version"]=="editorial-rules-v4.0"
    assert all(hit["snippet"] in title for hit in result["tag_rule_hits"])
    assert not result["ai_reviewed_fields"]


def test_inline_topic_keeps_following_prose_and_original_offsets():
    from api.services.post_editorial_tags import _body
    title="据报道，#美国总统特朗普 今天发文。#日本 当地发生火灾。#厦门#北京"
    body=_body(title)
    assert len(body)==len(title)
    assert "美国总统特朗普 今天发文" in body
    assert "日本 当地发生火灾" in body
    assert "厦门" not in body and "北京" not in body
    for hit in assess_post(title)["tag_rule_hits"]:
        assert hit["snippet"] in title


def test_unknown_inputs_remain_unknown_without_filling_categories():
    for title in ("这一幕太感动了", "他今天说出了心里话", "来了来了", "#厦门广电看金鸡#媒体原创", "新闻（见习记者/医生 来源/健康厦门）"):
        result=assess_post(title)
        assert result["channel"]==result["region"]=="待判定"


@pytest.mark.parametrize("title,desc,channel,region", [
    ("一切看见皆有回响！生日快乐！#2026年中国金鸡百花电影节 #厦门", "", "文娱", "本地"),
    ("一起来看现场 #投洽会 #厦门", "", "经济", "本地"),
    ("青春笑容 #闽超 #福州", "", "体育", "本省"),
    ("温柔日常 #萌娃 #育儿趣事", "", "民生", "待判定"),
    ("最新消息 #俄乌冲突 #俄罗斯", "", "时政", "国际"),
    ("这一幕 #落水救援 #同安", "", "应急", "本地"),
    ("新进展", "#芯片 #厦门", "科技", "本地"),
    ("一起关注 #高考 #福建", "", "教育", "本省"),
    ("最新消息 #酒驾 #厦门", "", "法治", "本地"),
    ("发现美好 #厦门周末去哪玩", "", "文旅", "待判定"),
    ("#金鸡奖#厦门", "", "文娱", "本地"),
    ("#台湾光复 #台湾", "", "时政", "国内"),
    ("#健康", "", "健康", "待判定"),
    ("#民生 #国际新闻", "", "民生", "国际"),
    ("#乡村振兴 #福建", "", "三农", "本省"),
    ("#白海豚 #厦门", "", "环境生态", "本地"),
    ("#政策解读 #中国", "", "政策文件", "国内"),
    ("#文娱#健康", "", "待判定", "待判定"),
    ("#电影 #高考", "", "待判定", "待判定"),
    ("#厦门#福州", "", "待判定", "待判定"),
    ("#厦门#美国", "", "待判定", "待判定"),
    ("#福建#厦门", "", "待判定", "本地"),
    ("#中国#福建#泉州", "", "待判定", "本省"),
    ("#厦门中山路", "", "待判定", "本地"),
    ("#中山路", "", "待判定", "待判定"),
    ("#福建厦门", "", "待判定", "本地"),
    ("#厦门广电看金鸡 #媒体原创 #光影时尚潮鹭岛群星耀", "", "待判定", "待判定"),
    ("新闻（来源/#高考 编辑/#福州）", "", "待判定", "待判定"),
    ("看看这一幕 #中国国际短视频大赛", "", "待判定", "待判定"),
    ("美国发生地震 #厦门", "", "应急", "国际"),
    ("厦门和福州同步举办活动 #厦门", "", "待判定", "待判定"),
    ("#国际新闻#厦门", "", "待判定", "本地"),
])
def test_caption_topics_classify_with_explicit_provenance(title,desc,channel,region):
    result=assess_post(title,desc)
    assert result['channel']==channel
    assert result['region']==region
    for hit in result['tag_rule_hits']:
        assert hit['snippet'] in {'title':title,'desc':desc}[hit['field']]
        if ':topic-' in hit['rule_id']:
            assert hit['snippet'].startswith('#')


def test_conflicting_topics_do_not_replace_clear_body_and_explain_disagreement():
    result=assess_post('在厦门医院进行治疗 #金鸡奖 #美国')
    assert result['channel']=='健康' and result['region']=='本地'
    assert '话题标签与正文' in result['tag_reason']
    assert '地域标签与正文' in result['tag_reason']
    rejected=[hit for hit in result['tag_rule_hits'] if hit['rule_id']=='region:topic-conflict']
    assert rejected and rejected[0]['snippet']=='#美国' and rejected[0]['score']==0


def test_topic_variations_and_duplicate_fields_cannot_accumulate_unlimited_weight():
    one=assess_post('最新消息 #电影')
    repeated=assess_post('最新消息 #电影 #金鸡奖 #演员 #电影节 #电影','另外的文案 #电影')
    assert one['tag_scores']['channel']['文娱']==repeated['tag_scores']['channel']['文娱']==4
    assert len([h for h in repeated['tag_rule_hits'] if h['rule_id']=='channel:topic-文娱'])==1
    assert assess_post('妈妈带宝宝到医院治疗 #电影 #演员 #电影节')['channel']=='健康'


@pytest.mark.parametrize('title,channel,region', [
    ('美国中期选举，两党政要助选', '时政', '国际'),
    ('全会精神引发党代表热议 #厦门市第十四次党代会', '时政', '待判定'),
    ('白宫任命新闻秘书', '时政', '待判定'),
    ('法国罢工引发抗议游行', '时政', '国际'),
    ('缅北犯罪集团案一审宣判，三人被判死刑', '法治', '国际'),
    ('泰国住持贪污获刑', '法治', '国际'),
    ('小心AI诈骗，亲友借钱先核实 #AI诈骗', '法治', '待判定'),
    ('#AI诈骗', '法治', '待判定'),
    ('#人工智能电影', '文娱', '待判定'),
    ('#两岸美食 #厦门', '文旅', '本地'),
    ('#两岸一味 #文博会', '文旅', '待判定'),
    ('#两岸关系', '时政', '待判定'),
    ('#两岸', '时政', '待判定'),
    ('#国防教育', '时政', '待判定'),
    ('#医学模拟教育', '教育', '待判定'),
    ('#体育经济', '经济', '待判定'),
    ('#文旅产业', '经济', '待判定'),
    ('厦门一中建校120周年，校友回家', '教育', '本地'),
    ('厦门特教老师为特需学生改课桌椅', '教育', '本地'),
    ('台湾课纲和课本选文引发争议', '教育', '国内'),
    ('军训学子拉练', '教育', '待判定'),
    ('刀郎线上音乐会定档 #刀郎线上音乐会', '文娱', '待判定'),
    ('第六届中国歌剧节开幕 #中国歌剧节', '文娱', '待判定'),
    ('飞机上宝宝哭闹，空姐帮忙哄娃', '民生', '待判定'),
    ('厦金大桥厦门段合龙', '民生', '本地'),
    ('社区博饼活动邀请志愿者参与', '民生', '待判定'),
    ('工间操大赛齐聚厦门', '体育', '本地'),
    ('厦门酒店推荐，高空景观适合度假', '文旅', '本地'),
    ('属于厦门的曼哈顿悬日 #落日', '文旅', '本地'),
    ('创新创业大赛举办园区考察和项目对接', '经济', '待判定'),
    ('车型销量排行榜公布', '经济', '待判定'),
    ('灼伤皮肤后正确处理避免留疤', '健康', '待判定'),
    ('厦门外科手术直播展示科技进化', '健康', '本地'),
    ('红树林树木生长受影响，增加围挡 #红树林', '环境生态', '待判定'),
    ('塞尔维亚总统宣布辞职 #塞尔维亚', '时政', '国际'),
    ('在巴布亚新几内亚开展活动 #巴布亚新几内亚', '待判定', '国际'),
    ('西班牙事故后宣布全国哀悼三天', '应急', '国际'),
    ('厦门队与福州队将在北京进行闽超决赛', '体育', '国内'),
    ('厦门队VS福州队，谁能获胜？ #闽超', '体育', '待判定'),
    ('厦门点亮中华情中国梦，灯光秀打卡', '待判定', '本地'),
])
def test_refined_subject_rules_and_geographic_background(title,channel,region):
    result=assess_post(title)
    assert (result['channel'],result['region'])==(channel,region)
    assert all(h['snippet'] in title for h in result['tag_rule_hits'])


@pytest.mark.parametrize('title', [
    '特朗普今天来了 #特朗普',
    '热闹起来 #新闻联播 #精选主播说',
    '节日快乐 #中秋 #国庆',
    '这一幕令人感动 #正能量 #暖心',
    '邀请大家前来参加 #全球看点 #热点新闻事件',
    '她讲了一段故事 #厦门广电看金鸡',
])
def test_names_columns_and_emotions_are_not_standalone_subjects(title):
    assert assess_post(title)['channel']=='待判定'


@pytest.mark.parametrize('title,channel', [
    ('党代表许女士：推动医疗资源下沉，守护健康 #厦门市第十四次党代会', '健康'),
    ('党代表张先生：深耕智能体研发 #厦门市第十四次党代会', '科技'),
    ('市委报告部署改革开放工作 #厦门市第十四次党代会', '时政'),
    ('孕妇羊水破裂，厦门交警开道护送抵达医院', '民生'),
    ('素人免费探店？当心新型刷单骗局 #探店 #诈骗', '法治'),
    ('台风将迎来大风阵雨 #天气 #台风', '应急'),
    ('厦门降温降雨并发布最新预警 #天气', '应急'),
    ('最新气温预报，冷空气带来降温 #天气', '民生'),
    ('电影节中的AI短片创作 #两岸AI影像计划 #AI短片', '文娱'),
    ('文博会美食集市 #两岸一味 #台湾夜市', '文旅'),
    ('陌生来电要留心 #AI诈骗 #财产安全', '法治'),
    ('研发反诈骗算法与人工智能芯片', '科技'),
    ('医院开展医学模拟教育大会', '教育'),
    ('太极队参加比赛', '体育'),
])
def test_subject_priority_does_not_follow_venue_tools_or_roles(title,channel):
    assert assess_post(title)['channel']==channel


@pytest.mark.parametrize('title,region', [
    ('在巴布亚新几内亚采访，回忆厦门的老朋友', '国际'),
    ('巴布亚新几内亚与厦门同步举办活动', '待判定'),
    ('#塞尔维亚', '国际'),
    ('#巴布亚新几内亚', '国际'),
    ('#中东', '国际'),
    ('#五缘湾', '本地'),
    ('厦门点亮“中华情·中国梦”灯光秀', '本地'),
    ('西班牙宣布全国哀悼', '国际'),
    ('中国宣布全国哀悼', '国内'),
    ('厦门队将到福州比赛', '本省'),
    ('中国选手战胜日本队，比赛在法国举办', '国际'),
    ('来自福建的游客在塞尔维亚游玩', '国际'),
    ('在五缘湾举办活动', '本地'),
])
def test_expanded_places_do_not_infer_event_location_from_people_or_teams(title,region):
    result=assess_post(title)
    assert result['region']==region
    assert all(h['snippet'] in title for h in result['tag_rule_hits'])
