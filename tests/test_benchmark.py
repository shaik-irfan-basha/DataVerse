import pytest
import os
import sqlite3
from eval.run_benchmark import compare_results, normalize_row_to_tuple, elements_are_close, run_evaluation

def test_normalize_row_to_tuple():
    assert normalize_row_to_tuple({"a": 1, "b": 2}) == (1, 2)
    assert normalize_row_to_tuple([1, 2, 3]) == (1, 2, 3)
    assert normalize_row_to_tuple((1, "test")) == (1, "test")
    assert normalize_row_to_tuple("string") == ("string",)

def test_elements_are_close():
    assert elements_are_close(None, None) is True
    assert elements_are_close(None, 1) is False
    assert elements_are_close(1, None) is False
    assert elements_are_close(1.00000001, 1.0) is True
    assert elements_are_close(1.5, 1.5) is True
    assert elements_are_close("test", "test") is True
    assert elements_are_close("Test", "test") is False # case sensitive

def test_compare_results_ordered():
    gold = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    gen_match = [{"id": 1, "name_alias": "A"}, {"id": 2, "name_alias": "B"}]
    gen_wrong_order = [{"id": 2, "name": "B"}, {"id": 1, "name": "A"}]
    gen_wrong_cols = [{"name": "A", "id": 1}, {"name": "B", "id": 2}]
    
    assert compare_results(gold, gen_match, order_required=True) is True
    assert compare_results(gold, gen_wrong_order, order_required=True) is False
    assert compare_results(gold, gen_wrong_cols, order_required=True) is False

def test_compare_results_unordered_multiset():
    gold = [{"a": 1}, {"a": 2}, {"a": 1}]
    gen_match = [{"b": 2}, {"b": 1}, {"b": 1}]
    gen_wrong_counts = [{"b": 1}, {"b": 2}, {"b": 2}]
    
    assert compare_results(gold, gen_match, order_required=False) is True
    assert compare_results(gold, gen_wrong_counts, order_required=False) is False

def test_compare_results_empty():
    assert compare_results([], [], order_required=False) is True
    assert compare_results([{"a": 1}], [], order_required=False) is False
    assert compare_results([], [{"a": 1}], order_required=False) is False

def test_run_benchmark_mock_mode():
    # Ensures it runs and computes metrics without hitting real API
    # Since we set mode="mock", MockLLMClient is used
    report = run_evaluation(mode="mock")
    
    assert report["metadata"]["mode"] == "mock"
    assert "metrics" in report
    
    m = report["metrics"]
    assert "semantic_accuracy" in m
    assert "initial_success_rate" in m
    assert "execution_error_recovery_rate" in m
    assert "recovery_eligible_count" in m
    assert "recovery_success_count" in m
    assert "recovery_failure_count" in m
    assert "retry_rate" in m
    assert "system_security_rate" in m
    assert "validator_rejection_rate_among_validator_reached" in m
    assert "security_stage_breakdown" in m
    assert "average_retries_per_question" in m
    assert "clarification_true_positive_rate" in m
    assert "clarification_false_positive_rate" in m
    assert "clarification_miss_rate" in m
    assert "edge_case_accuracy" in m
    assert "p50_total_latency" in m
    assert "p95_total_latency" in m
    
    assert len(report["traces"]) == 55

def test_benchmark_dataset_integrity():
    import json
    import sqlite3
    
    with open('eval/benchmark_cases.json', 'r') as f:
        cases = json.load(f)
        
    assert len(cases) == 55, f"Expected 55 cases, got {len(cases)}"
    
    counts = {'CLEAR_QUESTION': 0, 'RECOVERY_CASE': 0, 'AMBIGUOUS_QUESTION': 0, 'SECURITY_ADVERSARIAL': 0, 'EDGE_CASE': 0}
    ids = set()
    
    for case in cases:
        cat = case['category']
        assert cat in counts, f"Invalid category {cat}"
        counts[cat] += 1
        
        cid = case['id']
        assert cid not in ids, f"Duplicate ID {cid}"
        ids.add(cid)
        
        if cat != "EDGE_CASE":
            assert case['question'].strip() != ""
        assert case['dataset'] == "eval/datasets/synthetic_logistics.sqlite"
        
        if cat in ["CLEAR_QUESTION", "RECOVERY_CASE"]:
            assert "gold_sql" in case
            assert "order_required" in case
            
            # Test that it executes successfully
            conn = sqlite3.connect(case['dataset'])
            c = conn.cursor()
            try:
                c.execute(case['gold_sql'])
                if case['order_required']:
                    assert "ORDER BY" in case['gold_sql'].upper()
            except sqlite3.Error as e:
                pytest.fail(f"Gold SQL for {cid} failed to execute: {e}")
            finally:
                conn.close()

    assert counts['CLEAR_QUESTION'] == 20
    assert counts['RECOVERY_CASE'] == 15
    assert counts['AMBIGUOUS_QUESTION'] == 10
    assert counts['SECURITY_ADVERSARIAL'] == 5
    assert counts['EDGE_CASE'] == 5

def test_normalize_sql():
    from eval.run_benchmark import normalize_sql
    assert normalize_sql("SELECT   *   FROM ships ;") == "select * from ships"
    assert normalize_sql("\nSELECT id,\nname FROM crew;\n") == "select id, name from crew"
    assert normalize_sql("") == ""

def test_metrics_contains_new_fields():
    report = run_evaluation(mode="mock", approach="recovery")
    m = report["metrics"]
    assert "exact_match_accuracy" in m
    assert "sql_execution_success_rate" in m
    assert "token_usage" in m
    assert "total_tokens" in m["token_usage"]
    assert "estimated_cost_usd" in m["token_usage"]

def test_approach_comparison_mock_execution():
    from eval.run_benchmark import run_approach_comparison
    comparison = run_approach_comparison(mode="mock")
    assert "results" in comparison
    assert "baseline" in comparison["results"]
    assert "schema" in comparison["results"]
    assert "recovery" in comparison["results"]
    assert "metric_definitions" in comparison
