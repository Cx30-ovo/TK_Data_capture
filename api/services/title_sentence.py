"""Deterministic, auditable headline-sentence extraction; never rewrites source text."""

import re


TITLE_SENTENCE_VERSION = "caption-cleaned-title-v4"
TITLE_LENGTH_GROUP_VERSION = "title-length-four-bins-v1"
TITLE_LENGTH_BINS = (("≤20", 1, 20), ("21—30", 21, 30), ("31—40", 31, 40), (">40", 41, float("inf")))
TITLE_SENTENCE_RULE = "保留发布文案完整标题内容及全部句子；正文内话题词保留文字、去掉#，清理尾部话题标签、账号提及和采编署名；不按首句、换行或字数截断。尾部标签按位置识别，歧义需核对原文。每个汉字、字母、数字计一字，不计标点、空格和表情。"
_TOPIC = re.compile(r"#[^\s#，。！？、；：]+")
_MENTION = re.compile(r"@[^\s@，。！？、；：()（）]+")
_CREDIT = re.compile(r"[（(【\[]?\s*(?:见习\s*)?(?:采编|编导|责编|编审|剪辑|摄像|摄影|记者|编辑|来源|审核|制作|主播|包装|通讯员)\s*[/／:：]")


def extract_title_sentence(value: str | None) -> dict:
    raw = value or ""
    text = _MENTION.sub("", raw).strip()
    credit = _CREDIT.search(text)
    if credit:
        text = text[:credit.start()].rstrip()
    # Remove only a trailing run of hashtags. Anything followed by prose is
    # an inline entity, not metadata. Work backwards to support adjacent tags.
    while True:
        topics = list(_TOPIC.finditer(text))
        if not topics:
            break
        last = topics[-1]
        if any(char.isalnum() for char in text[last.end():]):
            break
        text = text[:last.start()].rstrip()
    text = _TOPIC.sub(lambda match: match.group()[1:], text).strip()
    if not text or not any(char.isalnum() for char in text):
        return {"text": "", "word_count": None, "method": "unavailable"}
    sentence = text
    method = "cleaned_full_caption"
    count = sum(char.isalnum() for char in sentence)
    return {"text": sentence if count else "", "word_count": count or None,
            "method": method if count else "unavailable"}
