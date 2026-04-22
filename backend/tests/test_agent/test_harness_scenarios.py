from __future__ import annotations

from app.services.agent.harness import SCENARIOS


def test_harness_scenarios_cover_ten_distinct_bioinformatics_flows():
    assert len(SCENARIOS) == 10
    ids = [scenario["id"] for scenario in SCENARIOS]
    assert len(set(ids)) == 10
    assert all(scenario["prompt"].strip() for scenario in SCENARIOS)
    assert all(scenario["category"].strip() for scenario in SCENARIOS)


def test_harness_scenarios_include_expected_core_use_cases():
    ids = {scenario["id"] for scenario in SCENARIOS}
    assert "rna_seq_differential_expression" in ids
    assert "pubmed_crispr_base_editing" in ids
    assert "clinical_survival_analysis" in ids
    assert "single_cell_10x_analysis" in ids
    assert "virtual_screen_egfr_chembl" in ids
