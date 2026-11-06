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
    ("这一幕令人感动 #厦门", "（来源：厦门广电）", "待判定", "待判定"),
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
    ("妈妈：叫妈妈！宝宝：爸爸！我不仅叫爸，我还字正腔圆", "待判定"),
    ("一岁萌娃迈出人生第一步，跌跌撞撞走向父母", "待判定"),
    ("厦门幼儿园萌娃向爸爸展示自己的玩具", "教育"),
    ("妈妈带宝宝到厦门医院治疗", "健康"),
    ("厦门幼儿园向父母公布招生安排", "教育"),
    ("厦门法院审理父母抚养权诉讼", "法治"),
    ("电视剧里的妈妈和宝宝迎来大结局", "文娱"),
    ("厦门双十中学的旧日风华，泛黄画里有青春", "待判定"),
    ("厦门中学公开旧照用于历史课堂教学", "待判定"),
    ("厦门学校的老照片唤起青春回忆", "教育"),
    ("野生动物与幼崽相依的亲情", "环境生态"),
])
def test_context_requests_model_review_without_forcing_livelihood(title, initial_channel):
    initial = classify_post(title)
    assessed = assess_post(title)
    assert initial["channel"] == initial_channel
    assert assessed["channel"] == initial_channel
    assert "channel" in assessed["ambiguous_fields"]
    assert assessed["ambiguous_fields"].count("channel") == 1
    assert assessed["tag_status"] == "pending"


def test_family_words_in_credits_and_trailing_hashtags_do_not_create_review_context():
    assessed = assess_post("厦门新增公交线路", "（编辑/妈妈）#宝宝 #育儿")
    assert assessed["channel"] == "民生"
    assert assessed["ambiguous_fields"] == []
