"""저장된 공식 채점 결과를 Langfuse 데이터셋/실험에 기록한다. 모델은 호출하지 않는다."""

import argparse
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from run import config, langfuse_client, pr_key, save

METRICS = ("grounded_precision", "grounded_recall", "augmented_precision", "augmented_recall")


def load_results(run):
    manifest = json.loads((run / "run.json").read_text())
    if manifest["status"] != "scored":
        raise ValueError("공식 채점이 완료된 실행만 업로드할 수 있습니다.")
    scores = json.loads((run / "scoring/results.json").read_text())
    details_list = json.loads((run / "scoring/results.details.json").read_text())
    dataset = json.loads((run / "dataset.json").read_text())
    expected = set(manifest["expected_prs"])
    per_pr = {item["pr_key"]: item["metrics"] for item in scores["per_pr"]}
    details = {item["pr_key"]: item["candidate_findings"] for item in details_list}
    if (
        set(per_pr) != expected
        or set(details) != expected
        or scores["pr_count"] != len(expected)
        or {p.stem for p in (run / "findings").glob("*.json")} != expected
    ):
        raise ValueError("공식 채점 결과의 PR 커버리지가 요청과 다릅니다.")
    outputs = {}
    for key in expected:
        candidate = json.loads((run / "findings" / f"{key}.json").read_text())
        outputs[key] = {
            "findings": candidate["findings"],
            "judgments": details[key],
            "review_usage": candidate.get("usage", {}),
        }
    return manifest, dataset, scores, per_pr, outputs


def evaluations(metrics, prefix=""):
    """공식 숫자를 그대로 복사한다. 분모가 없어 null인 점수는 0으로 바꾸지 않는다."""
    from langfuse import Evaluation

    return [
        Evaluation(name=prefix + name, value=metrics[name])
        for name in METRICS
        if metrics[name] is not None
    ]


def upload(run: Path):
    cfg = config()
    manifest, dataset, scores, per_pr, outputs = load_results(run)
    receipt_path = run / "langfuse.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        print(f"Already uploaded: {receipt['experiment_url']}")
        return receipt
    client = langfuse_client(cfg, tracing=True)
    try:
        dataset_name = f"reviewbench/{manifest['set']}"
        client.create_dataset(
            name=dataset_name,
            description="ReviewBench 공개 PR과 기준 정답. 채점은 로컬 공식 도구에서 수행합니다.",
            metadata={
                "source": "https://github.com/review-bench/ReviewBench",
                "reviewbench_revision": manifest["reviewbench_revision"],
            },
        )
        selected_items = []
        for item in dataset:
            key = item["pr_key"]
            remote_item = client.create_dataset_item(
                dataset_name=dataset_name,
                id=str(uuid5(NAMESPACE_URL, f"coday/{dataset_name}/{key}")),
                input=item["input"],
                expected_output=item["expected_output"],
                metadata={"pr_key": key, "reviewbench_revision": manifest["reviewbench_revision"]},
            )
            if key in outputs:
                selected_items.append(remote_item)

        def task(*, item, **kwargs):
            return outputs[pr_key(item.input)]

        def item_scores(*, input, **kwargs):
            return evaluations(per_pr[pr_key(input)]["overall"])

        def run_scores(**kwargs):
            # aggregate를 재계산하지 않고 공식 macro/micro 결과를 전송한다.
            return [
                *evaluations(scores["macro"]["overall"], "macro_"),
                *evaluations(scores["micro"]["overall"], "micro_"),
            ]

        metadata = {
            k: json.dumps(manifest[k], ensure_ascii=False)
            if not isinstance(manifest[k], str)
            else manifest[k]
            for k in (
                "run_by",
                "created_at",
                "review_model",
                "judge_model",
                "judge_provider",
                "prompt",
                "coday_revision",
                "coday_dirty",
                "reviewbench_revision",
                "set",
                "expected_prs",
            )
        }
        metadata["eval_config"] = json.dumps(scores.get("eval_config", {}))
        metadata["evaluated_prs"] = str(scores["pr_count"])
        metadata["execution"] = "Imported ReviewBench results; no LLM calls during upload"
        result = client.run_experiment(
            name="CO-DAY ReviewBench",
            run_name=manifest["run_name"],
            description=manifest["description"],
            data=selected_items,
            task=task,
            evaluators=[item_scores],
            run_evaluators=[run_scores],
            max_concurrency=5,
            metadata=metadata,
        )
        client.flush()
        if len(result.item_results) != len(outputs) or any(
            item.output is None for item in result.item_results
        ):
            raise RuntimeError(
                "Langfuse 전송 중 오류가 발생했습니다. 같은 명령으로 업로드를 재시도하세요."
            )
        receipt = {
            "experiment_id": result.experiment_id,
            "experiment_url": result.experiment_url,
            "run_name": manifest["run_name"],
            "dataset_name": dataset_name,
        }
        save(receipt_path, receipt)
        print(f"Langfuse: {result.experiment_url}")
        return receipt
    finally:
        client.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    try:
        upload(args.run_directory.resolve())
    except (ValueError, RuntimeError) as error:
        print(f"Upload: {error}", file=sys.stderr)
        sys.exit(1)
