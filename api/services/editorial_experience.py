"""Bounded local retrieval of human corrections; no embedding/model requests."""
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache

from .post_editorial_tags import _body


@lru_cache(maxsize=2048)
def tokens(text):
    cleaned = unicodedata.normalize("NFKC", _body(text or "")).lower()
    terms = Counter(re.findall(r"[a-z0-9]{2,}", cleaned))
    for part in re.findall(r"[\u4e00-\u9fff]+", cleaned):
        terms.update(part[i:i + 2] for i in range(len(part) - 1))
    for name, pattern in {
        "child": "宝宝|萌娃|孩子|小孩|幼儿|小朋友",
        "family": "亲子|家庭|亲情|父母|妈妈|爸爸|爸妈",
        "medical": "医院|医生|治疗|疾病|诊疗|看病",
        "education": "招生|教学|考试|学习|课堂",
        "memory": "怀旧|回忆|旧照|旧日|青春|老照片",
    }.items():
        if re.search(pattern, cleaned):
            terms["concept:" + name] = 2
    return terms


def retrieve_examples(item, examples, limit=3):
    query = tokens(item.get("title", "") + "\n" + item.get("desc", ""))
    if not query:
        return []
    ranked = []
    for example in examples:
        if example["aweme_id"] == item["aweme_id"]:
            continue
        terms = tokens(example.get("title", "") + "\n" + example.get("desc", ""))
        shared = query.keys() & terms.keys()
        lexical = [term for term in shared if not term.startswith("concept:")]
        concepts = [term for term in shared if term.startswith("concept:")]
        if not lexical and len(concepts) < 2:
            continue
        dot = sum(query[k] * terms[k] for k in shared)
        norm = math.sqrt(sum(v*v for v in query.values()) * sum(v*v for v in terms.values()))
        score = dot / norm if norm else 0
        if score < .12:
            continue
        ranked.append((score, example))
    ranked.sort(key=lambda value: (-value[0], value[1]["aweme_id"]))
    return [{"aweme_id": example["aweme_id"], "title": _body(example.get("title", ""))[:600],
             "desc": _body(example.get("desc", ""))[:600], "channel": example["channel"],
             "region": example["region"], "reason": example["reason"][:300],
             "revision": example["revision"], "source_sha256": example["source_sha256"],
             "similarity": round(score, 3)} for score, example in ranked[:limit]]
