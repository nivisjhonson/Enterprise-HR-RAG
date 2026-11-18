from src.evaluation import mean, precision_at_k, recall_at_k, reciprocal_rank


def test_retrieval_metrics_and_empty_expected_set():
    retrieved = ["a", "b", "c"]
    assert recall_at_k(retrieved, {"b", "c"}, 2) == 0.5
    assert reciprocal_rank(retrieved, {"b"}) == 0.5
    assert recall_at_k(retrieved, set(), 4) == 1
    assert precision_at_k(retrieved, {"b", "c"}, 2) == 0.5
    assert mean([0.25, 0.75]) == 0.5
