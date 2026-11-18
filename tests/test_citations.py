from __future__ import annotations

from src.citations import retain_valid_citations


def test_only_real_retrieved_sources_survive_citation_validation():
    sources = [{"label": "S1", "filename": "policy.txt"}]
    answer, cited = retain_valid_citations(
        "Submit the request to your manager [S1]. See payroll details [S99].",
        sources,
    )
    assert answer == "Submit the request to your manager [S1]. See payroll details ."
    assert cited == sources
