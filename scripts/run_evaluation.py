from __future__ import annotations

import json
from pathlib import Path

from src.evaluation import mean, precision_at_k, recall_at_k, reciprocal_rank

TEST_SET = Path(__file__).resolve().parents[1] / "tests" / "evaluation_set.json"


def main() -> None:
    cases = json.loads(TEST_SET.read_text(encoding="utf-8"))
    reviewed_cases = [case for case in cases if case.get("reviewed") is True]
    if not reviewed_cases:
        print(
            f"Evaluation cases: {len(cases)} (none marked as reviewed). "
            "No metrics calculated."
        )
        return
    recall_scores = []
    mrr_scores = []
    precision_scores = []
    answer_relevance = []
    faithfulness = []
    citation_correctness = []
    abstention_accuracy = []
    for case in reviewed_cases:
        retrieved = case.get("retrieved_document_ids", [])
        expected = set(case["expected_document_ids"])
        recall_scores.append(recall_at_k(retrieved, expected, k=4))
        precision_scores.append(precision_at_k(retrieved, expected, k=4))
        mrr_scores.append(reciprocal_rank(retrieved, expected))
        if isinstance(case.get("answer_relevant"), bool):
            answer_relevance.append(float(case["answer_relevant"]))
        if isinstance(case.get("answer_faithful"), bool):
            faithfulness.append(float(case["answer_faithful"]))
        if isinstance(case.get("citations_correct"), bool):
            citation_correctness.append(float(case["citations_correct"]))
        if isinstance(case.get("abstained"), bool):
            abstention_accuracy.append(
                float(case["abstained"] == case["should_abstain"])
            )
    print(f"Reviewed evaluation cases: {len(reviewed_cases)}")
    print(f"Recall@4: {mean(recall_scores):.3f}")
    print(f"Precision@4: {mean(precision_scores):.3f}")
    print(f"MRR: {mean(mrr_scores):.3f}")
    for label, annotations in (
        ("Answer relevance", answer_relevance),
        ("Faithfulness", faithfulness),
        ("Citation correctness", citation_correctness),
        ("Abstention accuracy", abstention_accuracy),
    ):
        if annotations:
            print(f"{label} ({len(annotations)} reviewed): {mean(annotations):.3f}")
        else:
            print(f"{label}: not annotated")
    print("Answer metrics are human annotations, not automated model scores.")


if __name__ == "__main__":
    main()
