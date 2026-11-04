from types import SimpleNamespace

import pytest

from api.services.title_sentence import extract_title_sentence, TITLE_SENTENCE_VERSION
from api.services.account_profile_service import build_profile
from api.services.title_strategy_metrics import build_rows, compute_title_strategy


@pytest.mark.parametrize("caption,expected", [
    ("来自福建的菌草，如何在斐济长出一门蘑菇生意？曾经从事IT工作的人开始种菇。(采编/小王)#菌草", "来自福建的菌草，如何在斐济长出一门蘑菇生意？曾经从事IT工作的人开始种菇。"),
    ("地铁正式开通！市民今天可以乘车。#厦门", "地铁正式开通！市民今天可以乘车。"),
    ("地铁正式开通\n今天开始运营。", "地铁正式开通\n今天开始运营。"),
    ("【地铁正式开通】今天开始运营。", "【地铁正式开通】今天开始运营。"),
    ("#厦门 地铁正式开通！#交通", "厦门 地铁正式开通！"),
    ("地铁正式开通（编辑：小王）", "地铁正式开通"),
    ("地铁正式开通 记者/小王", "地铁正式开通"),
    ("厦门地铁通车！#本地新闻 @记者（编辑：小王）", "厦门地铁通车！"),
    ("“出发！”更多正文。", "“出发！”更多正文。"),
    ("他说“出发！”随后上车。后续正文。", "他说“出发！”随后上车。后续正文。"),
    ("票价2.5元起！后续正文。", "票价2.5元起！后续正文。"),
    ("AI新闻2026", "AI新闻2026"),
    ("#话题 😀！？", ""), (None, ""),
    ("（记者：小王）#新闻", ""),
    ("据央视网报道，#日本 和#美国 19日起举行军演，距#中国台湾 仅110公里。#军演 #国际新闻", "据央视网报道，日本 和美国 19日起举行军演，距中国台湾 仅110公里。"),
    ("#乌克兰 总统#泽连斯基 当地时间21日接受采访。#国际新闻", "乌克兰 总统泽连斯基 当地时间21日接受采访。"),
    ("#厦门 地铁开通。#交通#民生", "厦门 地铁开通。"),
    ("正文。\n#话题 #新闻\n采编：小王", "正文。"),
    ("#日本 和#美国 举行军演。", "日本 和美国 举行军演。"),
    ("正文#厦门", "正文"),
    ("泽连斯基：愿在保留至少75%领土控制权的基础上达成和平协议。（见习编辑/朱海涛 责编/詹昕娉 编审/沈琳煜） #俄乌冲突 #泽连斯基", "泽连斯基：愿在保留至少75%领土控制权的基础上达成和平协议。"),
    ("正文。(见习编辑：小王)", "正文。"),
    ("正文。【见习记者／小王】", "正文。"),
    ("正文。\n见习 编辑/小王", "正文。"),
    ("见习编辑介绍了新闻采编流程。", "见习编辑介绍了新闻采编流程。"),
])
def test_extract_opening_title_sentence(caption, expected):
    result = extract_title_sentence(caption)
    assert result["text"] == expected
    assert result["word_count"] == (sum(c.isalnum() for c in expected) or None)


def test_no_arbitrary_sixty_word_truncation():
    title = "甲" * 70 + "！"
    assert extract_title_sentence(title + "后续正文。")["text"] == title + "后续正文。"


def test_user_confirmed_full_caption_example():
    expected = "来自福建的菌草，如何在斐济长出一门蘑菇生意？曾经从事IT工作的阿什米尔·钱德，借助中国援助的菌草技术，在集装箱里种起了蘑菇。从自己种菇到教别人种菇，他与菌草菇的故事，还在不断解锁新可能。"
    caption = expected + "(采编/廖航 黄鹤 许庆平 林振明 叶嘉莹 林一勇 包装/廖航 责编/林振明 梁含雪 编审/王群 许晓露)#中国草万里行 #菌草 #斐济 #蘑菇 #媒体原创"
    result = extract_title_sentence(caption)
    assert result["text"] == expected
    assert result["word_count"] == 84


def test_both_charts_use_same_title_and_keep_full_cover_sample():
    caption = "菌草如何长出蘑菇生意？" + "正文介绍很多内容。" * 15 + "（采编/小王）#菌草"
    posts = [SimpleNamespace(aweme_id="p1", title=caption, desc=caption, create_time=100),
             SimpleNamespace(aweme_id="p2", title="#厦门 😀", desc="", create_time=101)]
    row = build_rows(posts, {})[0]
    profile = build_profile({"id": 1, "platform": "dy", "display_name": "测试", "sec_user_id": "a"},
                            [vars(p) for p in posts], [], 2, 2, 0, 86400)
    assert row["title"] == "菌草如何长出蘑菇生意？" + "正文介绍很多内容。" * 15
    assert profile["title_length"]["mean"] == row["title_len"]
    assert profile["title_length"]["evidence"][0]["snippet"] == caption
    assert profile["title_length"]["evidence"][0]["extracted_title"] == row["title"]
    metrics = compute_title_strategy(posts, {})
    assert metrics["title_extraction"] == {"version": TITLE_SENTENCE_VERSION,
        "grouping_version": "title-length-four-bins-v1",
        "rule": profile["title_length"]["rule"], "sample_count": 1, "excluded_count": 1}
    assert sum(g["count"] for g in metrics["title_length_groups"]) == 1
    assert len(metrics["all_samples"]) == 2
    assert metrics["all_samples"][1]["title_len"] is None
    assert caption == posts[0].title  # original source not rewritten
