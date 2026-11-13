"""Evaluate a fixed, labelled rule fixture; never query databases or models."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.services.post_editorial_tags import RULE_VERSION, classify_post


def evaluate(dataset):
    metrics = {field: Counter(total=0, exact=0, misclassified=0, missed=0,
                              unsupported_resolved=0, conflicts=0) for field in ("channel", "region")}
    failures, confusion = [], {field: Counter() for field in metrics}
    for case in dataset["cases"]:
        tags = classify_post(case["text"], case.get("desc", ""))
        for field, counts in metrics.items():
            expected, actual = case[field], tags[field]
            counts["total"] += 1
            counts["exact"] += expected == actual
            counts["conflicts"] += any(reason["field"] == field and reason["code"] == "rule_conflict"
                                        for reason in tags["tag_pending_reasons"])
            confusion[field][expected + " → " + actual] += 1
            if expected != actual:
                category = ("missed" if actual == "待判定" else "unsupported_resolved"
                            if expected == "待判定" else "misclassified")
                counts[category] += 1
                failures.append(dict(id=case["id"], field=field, expected=expected, actual=actual, category=category))
        if case.get("subtopic") and case["subtopic"] not in tags["channel_subtopics"]:
            failures.append(dict(id=case["id"], field="subtopic", expected=case["subtopic"], actual=tags["channel_subtopics"]))
    return dict(dataset_version=dataset["dataset_version"], rule_version=RULE_VERSION,
                sample_count=len(dataset["cases"]), metrics=metrics, confusion=confusion,
                failures=failures, passed=not failures,
                limitation="固定标注样本的回归结果，不代表全部真实作品的分类准确率；覆盖率与准确率分开。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/fixtures/editorial_classification_golden.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.fixture.read_text(encoding="utf-8")))
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        # Refuse to overwrite previous evidence.
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    print(payload)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
