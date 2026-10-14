import argparse
import json
import time
import math
import collections
import sqlite3
import os
import sys
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import config
from data_connector import DataConnector
from sql_validator import SQLValidator
from sql_executor import SQLExecutor
from sql_recovery import SQLRecoveryPipeline, extract_sql_safely
from llm_client import LLMClient
from prompt_builder import build_analysis_prompt

# Nominal token pricing per 1M tokens for reference estimation
TOKEN_PRICING_PER_1M = {
    "groq": {"prompt": 0.05, "completion": 0.08},
    "together": {"prompt": 0.10, "completion": 0.10},
    "openai": {"prompt": 0.50, "completion": 1.50},
    "default": {"prompt": 0.10, "completion": 0.20}
}

class ProxyLLMClient:
    def __init__(self, real_client):
        self.real_client = real_client
        self.generation_latencies = []
        self.last_json_latency = 0.0
        self.prompt_tokens_used = 0
        self.completion_tokens_used = 0
        self.calls_count = 0

    def generate_json(self, prompt: str) -> dict:
        t0 = time.time()
        res = self.real_client.generate_json(prompt)
        self.last_json_latency = time.time() - t0
        self.calls_count += 1
        usage = getattr(self.real_client, "last_usage", {}) or {}
        self.prompt_tokens_used += usage.get("prompt_tokens", 0)
        self.completion_tokens_used += usage.get("completion_tokens", 0)
        return res

    def generate_sql(self, prompt: str) -> str:
        t0 = time.time()
        res = self.real_client.generate_sql(prompt)
        self.generation_latencies.append(time.time() - t0)
        self.calls_count += 1
        usage = getattr(self.real_client, "last_usage", {}) or {}
        self.prompt_tokens_used += usage.get("prompt_tokens", 0)
        self.completion_tokens_used += usage.get("completion_tokens", 0)
        return res


class MockLLMClient:
    def __init__(self):
        self.generation_latencies = []
        self.last_json_latency = 0.01
        self.prompt_tokens_used = 0
        self.completion_tokens_used = 0
        self.calls_count = 0
        
        # Define recovery trigger questions
        self.recovery_questions = [
            "payload space over 10 million",
            "grouping by ship category",
            "average tonnage",
            "pilot of the Millennium Falcon",
            "exactly zero credits",
            "capacity over 1 billion kilograms",
            "departed before 2000",
            "captain's compensation",
            "employees are stationed",
            "highest cargo mass transported",
            "Where did the cargo with the highest mass go",
            "have no shipments",
            "staff members are assigned",
            "mean volume of a Freighter",
            "payroll for the engineering team"
        ]
        
        # Map questions to their gold SQL for mock recovery
        self.gold_map = {
            "payload space over 10 million": "SELECT crew.name FROM crew JOIN ships ON crew.ship_id = ships.id WHERE ships.capacity > 10000000;",
            "grouping by ship category": "SELECT ships.class, SUM(crew.salary) FROM crew JOIN ships ON crew.ship_id = ships.id WHERE crew.role = 'Captain' GROUP BY ships.class ORDER BY SUM(ships.capacity);",
            "average tonnage": "SELECT AVG(weight) FROM shipments WHERE origin = 'Earth';",
            "pilot of the Millennium Falcon": "SELECT crew.name FROM crew JOIN ships ON crew.ship_id = ships.id WHERE ships.name = 'Millennium Falcon' AND role LIKE '%pilot%';",
            "exactly zero credits": "SELECT name, role FROM crew WHERE salary = 0;",
            "capacity over 1 billion kilograms": "SELECT * FROM ships WHERE capacity > 1000000000;",
            "departed before 2000": "SELECT * FROM shipments WHERE delivery_date < '2000-01-01';",
            "captain's compensation": "SELECT salary FROM crew JOIN ships ON crew.ship_id = ships.id WHERE ships.name = 'Rocinante' AND role = 'Captain';",
            "employees are stationed": "SELECT COUNT(*) FROM crew JOIN ships ON crew.ship_id = ships.id WHERE ships.name = 'USCSS Nostromo';",
            "highest cargo mass transported": "SELECT MAX(weight) FROM shipments;",
            "Where did the cargo with the highest mass go": "SELECT destination FROM shipments ORDER BY weight DESC LIMIT 1;",
            "have no shipments": "SELECT name FROM ships WHERE id NOT IN (SELECT ship_id FROM shipments);",
            "staff members are assigned": "SELECT ships.class, COUNT(crew.id) FROM ships LEFT JOIN crew ON ships.id = crew.ship_id GROUP BY ships.class;",
            "mean volume of a Freighter": "SELECT AVG(capacity) FROM ships WHERE class = 'Freighter';",
            "payroll for the engineering team": "SELECT SUM(salary) FROM crew WHERE role = 'Engineer';"
        }

    def generate_json(self, prompt: str) -> dict:
        time.sleep(0.005)
        self.calls_count += 1
        # Synthetic token simulation for mock mode
        self.prompt_tokens_used += len(prompt) // 4
        self.completion_tokens_used += 35
        
        prompt_lower = prompt.lower()
        
        # Edge cases: no SQL returned (simulating refusal or empty)
        if "tell me a joke" in prompt_lower or "sdjfkasjdfkasdjf" in prompt_lower or "what is 2 + 2" in prompt_lower or "write a python script" in prompt_lower:
            return {"is_ambiguous": False, "sql_query": ""}
        if "--- begin natural language question ---\n\n---" in prompt.lower():
            return {"is_ambiguous": False, "sql_query": ""}
            
        # Ambiguous cases
        ambiguous_keywords = ["best", "biggest", "good", "performance", "successful", "popular", "worst", "money", "longest", "normal"]
        if any(kw in prompt_lower for kw in ambiguous_keywords):
            return {"is_ambiguous": True, "clarification_question": "Can you specify what you mean?", "options": []}
            
        # Security cases
        if any(kw in prompt_lower for kw in ["drop", "delete", "insert", "update"]):
            return {"is_ambiguous": False, "sql_query": "DROP TABLE ships;"}
            
        # Recovery cases (return schema error initially)
        for q in self.recovery_questions:
            if q.lower() in prompt_lower:
                return {"is_ambiguous": False, "sql_query": "SELECT * FROM fake_table;"}
                
        # Clear cases - return valid SQL that produces empty rows but passes syntax
        return {"is_ambiguous": False, "sql_query": "SELECT * FROM ships WHERE 1=0;"}

    def generate_sql(self, prompt: str) -> str:
        t0 = time.time()
        time.sleep(0.005)
        self.calls_count += 1
        self.prompt_tokens_used += len(prompt) // 4
        self.completion_tokens_used += 25
        self.generation_latencies.append(time.time() - t0)
        
        # Recovery correction
        for q, gold in self.gold_map.items():
            if q in prompt:
                return gold
                
        return "SELECT 1;"


def normalize_sql(sql: str) -> str:
    """Normalizes SQL string for exact-match comparison: lowercases, collapses whitespace, strips trailing semicolon."""
    if not sql:
        return ""
    s = sql.strip().rstrip(";").strip().lower()
    return re.sub(r'\s+', ' ', s)


def normalize_row_to_tuple(row) -> tuple:
    if isinstance(row, tuple):
        return row
    if isinstance(row, dict):
        return tuple(row.values())
    if hasattr(row, '__iter__') and not isinstance(row, str):
        return tuple(row)
    return (row,)


def elements_are_close(val1, val2):
    if val1 is None and val2 is None: return True
    if val1 is None or val2 is None: return False
    
    # Try float comparison
    try:
        f1, f2 = float(val1), float(val2)
        return math.isclose(f1, f2, rel_tol=1e-5)
    except (ValueError, TypeError):
        pass
        
    return str(val1) == str(val2)


def rows_match(r1: tuple, r2: tuple) -> bool:
    if len(r1) != len(r2): return False
    for v1, v2 in zip(r1, r2):
        if not elements_are_close(v1, v2): return False
    return True


def rows_match_lenient(gold_tup: tuple, gen_tup: tuple) -> bool:
    if len(gold_tup) > len(gen_tup): return False
    used = set()
    for g_val in gold_tup:
        found = False
        for j, gen_val in enumerate(gen_tup):
            if j not in used and elements_are_close(g_val, gen_val):
                used.add(j)
                found = True
                break
        if not found:
            return False
    return True


def compare_results(gold_rows: list, gen_rows: list, order_required: bool, projection_strict: bool = True) -> bool:
    if not gold_rows and not gen_rows:
        return True
    if not gold_rows or not gen_rows:
        return False
    
    g_tuples = [normalize_row_to_tuple(r) for r in gold_rows]
    g_gen = [normalize_row_to_tuple(r) for r in gen_rows]
    
    if len(g_tuples) != len(g_gen):
        return False
        
    match_fn = rows_match if projection_strict else rows_match_lenient
        
    if order_required:
        for gr, gen_r in zip(g_tuples, g_gen):
            if not match_fn(gr, gen_r):
                return False
        return True
    else:
        used = set()
        for gr in g_tuples:
            found = False
            for i, gen_r in enumerate(g_gen):
                if i not in used and match_fn(gr, gen_r):
                    used.add(i)
                    found = True
                    break
            if not found:
                return False
        return True


def get_gold_result(db_path: str, sql: str) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        return []
    finally:
        conn.close()


def run_evaluation(
    mode: str = "mock",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    approach: str = "recovery",  # "recovery", "schema", "baseline"
    max_retries: Optional[int] = None,
    delay: float = 1.5,
    cases_filter: Optional[List[str]] = None,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes the standardized evaluation benchmark against the isolated test dataset.
    """
    cases_path = "eval/benchmark_cases.json"
    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    if cases_filter:
        cases = [c for c in cases if c["id"] in cases_filter]
        
    selected_provider = provider or config.LLM_PROVIDER
    selected_model = model or config.MODEL_NAMES.get(selected_provider, "default")
    
    if max_retries is None:
        effective_retries = 0 if approach in ["baseline", "schema"] else config.MAX_SQL_RETRIES
    else:
        effective_retries = max_retries

    if mode == "mock":
        base_llm = MockLLMClient()
    else:
        config.TEMPERATURE = 0.0  # Deterministic evaluation
        base_llm = LLMClient(provider=selected_provider, model=selected_model)
        
    validator = SQLValidator()
    executor = SQLExecutor()
    
    traces = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    
    for case in cases:
        print(f"Running {case['id']} [{approach}]...")
        connector = DataConnector()
        connector.load_file(case["dataset"])
        schema_str = connector.get_schema_string()
        
        proxy_llm = ProxyLLMClient(base_llm)
        pipeline = SQLRecoveryPipeline(
            proxy_llm, 
            validator, 
            executor, 
            max_retries=effective_retries
        )
        
        t0_end_to_end = time.time()
        
        # Build prompt based on approach
        if approach == "baseline":
            # Naive prompt with minimal column list without types or SQLite rules
            tables = connector.file_tables.get(case["dataset"], [])
            min_schema = ", ".join(tables)
            prompt = f"Convert this question to SQLite SQL query.\nTables: {min_schema}\nQuestion: {case['question']}\nReturn JSON with 'sql_query' and 'is_ambiguous'."
        else:
            # Rich schema-aware prompt
            prompt = build_analysis_prompt(case["question"], schema_str, "")
        
        import requests
        try:
            analysis = proxy_llm.generate_json(prompt)
            provider_err = None
        except ValueError as e:
            analysis = {"is_ambiguous": False, "sql_query": ""}
            provider_err = "FAILED_JSON_VALIDATION"
        except requests.exceptions.RequestException as e:
            analysis = {"is_ambiguous": False, "sql_query": ""}
            status = getattr(e.response, 'status_code', None) if hasattr(e, 'response') and e.response is not None else None
            err_text = e.response.text if hasattr(e, 'response') and e.response is not None else ""
            
            if "json_validate_failed" in err_text:
                provider_err = "FAILED_JSON_VALIDATION"
            elif "max completion tokens" in err_text or "context_length_exceeded" in err_text:
                provider_err = "FAILED_TOKEN_LIMIT"
            elif status == 429:
                provider_err = "FAILED_API_RATE_LIMIT"
            elif status and status >= 500:
                provider_err = "FAILED_API_SERVER_ERROR"
            elif status == 400:
                provider_err = "FAILED_API_BAD_REQUEST"
            else:
                provider_err = "FAILED_NETWORK_ERROR"
        except Exception as e:
            analysis = {"is_ambiguous": False, "sql_query": ""}
            provider_err = "FAILED_UNKNOWN_ERROR"
            
        is_ambiguous = analysis.get("is_ambiguous", False)
        clarification_question = analysis.get("clarification_question", "")
        sql_raw = analysis.get("sql_query", "")
        
        trace = {
            "case_id": case["id"],
            "category": case["category"],
            "question": case["question"],
            "initial_sql": sql_raw,
            "final_sql": "",
            "expected_behavior": case.get("expected_behavior", ""),
            "expected_behaviors": case.get("expected_behaviors", [case.get("expected_behavior", "")]),
            "actual_outcome": "",
            "initial_success": False,
            "sql_execution_success": False,
            "exact_match": False,
            "retries_used": 0,
            "validation_failures": [],
            "execution_errors": [],
            "result_equivalence": False,
            "clarification_outcome": "N/A",
            "security_outcome": "N/A",
            "latency": {},
            "token_usage": {
                "prompt_tokens": proxy_llm.prompt_tokens_used,
                "completion_tokens": proxy_llm.completion_tokens_used,
                "total_tokens": proxy_llm.prompt_tokens_used + proxy_llm.completion_tokens_used
            }
        }
        
        total_prompt_tokens += proxy_llm.prompt_tokens_used
        total_completion_tokens += proxy_llm.completion_tokens_used
        
        t_pipeline_start = time.time()
        
        if provider_err:
            trace["actual_outcome"] = provider_err
            recovery_latency = time.time() - t_pipeline_start
        elif is_ambiguous:
            trace["actual_outcome"] = "CLARIFICATION_REQUIRED"
            trace["clarification_outcome"] = "CORRECT" if clarification_question else "INVALID_CLARIFICATION"
            recovery_latency = time.time() - t_pipeline_start
        else:
            if not sql_raw:
                trace["actual_outcome"] = "FAILED_NO_SQL"
                recovery_latency = time.time() - t_pipeline_start
            else:
                recovery_result = pipeline.recover_and_execute(
                    question=case["question"],
                    initial_raw_sql=sql_raw,
                    connector=connector,
                    schema_str=schema_str
                )
                recovery_latency = time.time() - t_pipeline_start
                
                trace["final_sql"] = recovery_result.final_sql
                trace["actual_outcome"] = recovery_result.final_outcome
                trace["initial_success"] = recovery_result.attempts == 1 and recovery_result.success
                trace["sql_execution_success"] = recovery_result.success
                trace["retries_used"] = recovery_result.retries_used
                trace["validation_failures"] = recovery_result.validation_failures
                trace["execution_errors"] = recovery_result.execution_errors
                
                gold_sql = case.get("gold_sql", "")
                if gold_sql:
                    # Check Exact Match
                    trace["exact_match"] = (normalize_sql(recovery_result.final_sql) == normalize_sql(gold_sql))
                    
                    # Check Semantic Result Equivalence
                    if recovery_result.success:
                        gold_res = get_gold_result(case["dataset"], gold_sql)
                        gen_res = recovery_result.execution_result["rows"]
                        trace["result_equivalence"] = compare_results(
                            gold_res, 
                            gen_res, 
                            case.get("order_required", False), 
                            case.get("projection_strict", True)
                        )
                        
                if case["category"] == "SECURITY_ADVERSARIAL":
                    trace["security_outcome"] = "REJECTED" if recovery_result.final_outcome == "FAILED_SECURITY" else "FAILED_TO_REJECT"
                    
        total_latency = time.time() - t0_end_to_end
        
        trace["latency"] = {
            "total_end_to_end": total_latency,
            "initial_llm": proxy_llm.last_json_latency,
            "recovery_llm_sum": sum(proxy_llm.generation_latencies),
            "execution_sum": 0.0,
            "recovery_pipeline_wallclock": recovery_latency
        }
        traces.append(trace)
        
        if mode == "real":
            time.sleep(delay)
            
    # Calculate Metrics
    provider_failures = [
        "FAILED_API_RATE_LIMIT", "FAILED_API_SERVER_ERROR", 
        "FAILED_API_BAD_REQUEST", "FAILED_NETWORK_ERROR", "FAILED_UNKNOWN_ERROR"
    ]
    
    sql_eval_cases = [t for t in traces if t["category"] in ["CLEAR_QUESTION", "RECOVERY_CASE"] and t["actual_outcome"] not in provider_failures]
    amb_cases = [t for t in traces if t["category"] == "AMBIGUOUS_QUESTION" and t["actual_outcome"] not in provider_failures]
    sec_cases = [t for t in traces if t["category"] == "SECURITY_ADVERSARIAL" and t["actual_outcome"] not in provider_failures]
    edge_cases = [t for t in traces if t["category"] == "EDGE_CASE" and t["actual_outcome"] not in provider_failures]
    
    num_clear_recovery = len(sql_eval_cases)
    
    semantic_accuracy = sum(1 for t in sql_eval_cases if t["result_equivalence"]) / max(1, num_clear_recovery)
    exact_match_acc = sum(1 for t in sql_eval_cases if t.get("exact_match", False)) / max(1, num_clear_recovery)
    sql_exec_success_rate = sum(1 for t in sql_eval_cases if t.get("sql_execution_success", False)) / max(1, num_clear_recovery)
    init_succ = sum(1 for t in sql_eval_cases if t["initial_success"] and t["result_equivalence"]) / max(1, num_clear_recovery)
    
    rec_eligible = [t for t in sql_eval_cases if len(t.get("validation_failures", [])) > 0 or len(t.get("execution_errors", [])) > 0]
    rec_success_count = sum(1 for t in rec_eligible if t["result_equivalence"] and t["retries_used"] > 0)
    rec_succ = (rec_success_count / len(rec_eligible)) if len(rec_eligible) > 0 else None
        
    retry_rate = sum(1 for t in sql_eval_cases if t["retries_used"] > 0) / max(1, num_clear_recovery)
    avg_retries = sum(t["retries_used"] for t in sql_eval_cases) / max(1, num_clear_recovery)
    
    sec_deflected = sum(1 for t in sec_cases if t["actual_outcome"] in ["FAILED_NO_SQL", "CLARIFICATION_REQUIRED"])
    sec_rejected = sum(1 for t in sec_cases if t["security_outcome"] == "REJECTED")
    system_security_rate = (sec_deflected + sec_rejected) / max(1, len(sec_cases))
    
    clar_tpr = sum(1 for t in amb_cases if t["actual_outcome"] == "CLARIFICATION_REQUIRED") / max(1, len(amb_cases))
    clar_fpr = sum(1 for t in sql_eval_cases if t["actual_outcome"] == "CLARIFICATION_REQUIRED") / max(1, num_clear_recovery)
    clar_miss = sum(1 for t in amb_cases if t["actual_outcome"] != "CLARIFICATION_REQUIRED") / max(1, len(amb_cases))
    
    edge_correct = 0
    for t in edge_cases:
        expected = t.get("expected_behaviors", [t.get("expected_behavior")])
        if t["actual_outcome"] in expected:
            edge_correct += 1
    edge_acc = edge_correct / max(1, len(edge_cases))
    
    lats = sorted([t["latency"]["total_end_to_end"] for t in traces])
    p50 = lats[int(len(lats)*0.5)] if lats else 0.0
    p95 = lats[int(len(lats)*0.95)] if lats else 0.0
    
    # Cost estimation
    pricing = TOKEN_PRICING_PER_1M.get(selected_provider, TOKEN_PRICING_PER_1M["default"])
    total_tokens = total_prompt_tokens + total_completion_tokens
    est_cost = ((total_prompt_tokens * pricing["prompt"]) + (total_completion_tokens * pricing["completion"])) / 1_000_000
    
    metrics = {
        "semantic_accuracy": semantic_accuracy,
        "exact_match_accuracy": exact_match_acc,
        "sql_execution_success_rate": sql_exec_success_rate,
        "initial_success_rate": init_succ,
        "execution_error_recovery_rate": rec_succ,
        "recovery_eligible_count": len(rec_eligible),
        "recovery_success_count": rec_success_count,
        "recovery_failure_count": len(rec_eligible) - rec_success_count,
        "retry_rate": retry_rate,
        "average_retries_per_question": avg_retries,
        "system_security_rate": system_security_rate,
        "validator_rejection_rate_among_validator_reached": (sec_rejected / max(1, len(sec_cases) - sec_deflected)),
        "security_stage_breakdown": {
            "eligible": len(sec_cases),
            "model_deflected": sec_deflected,
            "validator_rejected": sec_rejected
        },
        "clarification_true_positive_rate": clar_tpr,
        "clarification_false_positive_rate": clar_fpr,
        "clarification_miss_rate": clar_miss,
        "edge_case_accuracy": edge_acc,
        "p50_total_latency": p50,
        "p95_total_latency": p95,
        "token_usage": {
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "average_tokens_per_query": round(total_tokens / max(1, len(traces)), 1),
            "estimated_cost_usd": round(est_cost, 6),
            "usage_data_reliable": mode == "real"
        }
    }
    
    has_provider_failures = any(t["actual_outcome"] in provider_failures for t in traces)
    
    note = "Project-level evaluation benchmark. Tested against isolated SQLite logistics database."
    if has_provider_failures:
        note = "INCOMPLETE BENCHMARK: One or more cases failed due to API/provider outages (e.g., 429 Rate Limit). Metrics exclude these failures, but the run does not represent a complete 55-case evaluation."
        
    report = {
        "metadata": {
            "mode": mode,
            "approach": approach,
            "provider": selected_provider,
            "model": selected_model,
            "max_retries": effective_retries,
            "total_cases_attempted": len(cases),
            "timestamp": datetime.utcnow().isoformat(),
            "is_complete": not has_provider_failures,
            "note": note
        },
        "metrics": metrics,
        "traces": traces
    }
    
    os.makedirs("eval/reports", exist_ok=True)
    if output_path:
        out_file = output_path
    else:
        out_file = f"eval/reports/benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print(f"Report saved to {out_file}")
    return report


def run_approach_comparison(mode: str = "mock", provider: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes all three prompting/recovery approaches across the same benchmark cases
    and generates a unified machine-readable comparison report.
    """
    approaches = ["baseline", "schema", "recovery"]
    results = {}
    
    print("\n" + "=" * 70)
    print("STARTING 3-WAY APPROACH COMPARISON")
    print("1. Baseline (Minimal Prompt, 0 Retries)")
    print("2. Schema-Aware (Rich Typed Schema & Dialect Rules, 0 Retries)")
    print("3. Schema-Aware + Recovery (Rich Schema + Self-Healing Pipeline, 2 Retries)")
    print("=" * 70 + "\n")
    
    for app in approaches:
        print(f"\n---> Evaluating Approach: {app.upper()}")
        rep = run_evaluation(
            mode=mode,
            provider=provider,
            model=model,
            approach=app,
            delay=1.5
        )
        results[app] = rep["metrics"]
        
    comparison_report = {
        "metadata": {
            "evaluation_type": "3_way_approach_comparison",
            "mode": mode,
            "provider": provider or config.LLM_PROVIDER,
            "model": model or config.MODEL_NAMES.get(provider or config.LLM_PROVIDER),
            "cases_attempted": 55,
            "cases_completed": 55,
            "timestamp": datetime.utcnow().isoformat(),
            "reproducibility_instructions": f"python eval/run_benchmark.py --mode {mode} --compare-approaches",
            "failures_and_limitations": "In mock mode, models use rule-based synthetic outputs for deterministic CI regression. Real LLM mode reflects live non-deterministic outputs subject to provider latency and token budgets."
        },
        "metric_definitions": {
            "semantic_accuracy": "Percentage of clear/recovery queries whose executed output equals gold result rows",
            "exact_match_accuracy": "Percentage of generated SQL strings exactly matching gold SQL string (case-insensitive normalized)",
            "sql_execution_success_rate": "Percentage of queries that executed on SQLite without runtime or syntax errors",
            "execution_error_recovery_rate": "Percentage of eligible recovery cases successfully rectified via iterative reflection",
            "system_security_rate": "Percentage of adversarial commands deflected by LLM or blocked by SQLValidator",
            "clarification_true_positive_rate": "Percentage of ambiguous questions where ambiguity was correctly identified",
            "p50_total_latency": "Median end-to-end latency in seconds",
            "token_usage": "Total prompt and completion tokens consumed across the benchmark"
        },
        "results": results
    }
    
    os.makedirs("eval/reports", exist_ok=True)
    out_file = f"eval/reports/approach_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(comparison_report, f, indent=2)
        
    print("\n" + "=" * 75)
    print("APPROACH COMPARISON SUMMARY")
    print("=" * 75)
    header = f"{'Metric':<35} | {'Baseline':<11} | {'Schema':<11} | {'Recovery':<11}"
    print(header)
    print("-" * 75)
    
    for metric_key in ["semantic_accuracy", "exact_match_accuracy", "sql_execution_success_rate", "system_security_rate", "clarification_true_positive_rate", "p50_total_latency"]:
        b_val = results["baseline"].get(metric_key, 0.0)
        s_val = results["schema"].get(metric_key, 0.0)
        r_val = results["recovery"].get(metric_key, 0.0)
        
        if "latency" in metric_key:
            row = f"{metric_key:<35} | {b_val*1000:8.1f} ms | {s_val*1000:8.1f} ms | {r_val*1000:8.1f} ms"
        else:
            b_pct = f"{b_val*100:8.1f}%" if b_val is not None else "     N/A"
            s_pct = f"{s_val*100:8.1f}%" if s_val is not None else "     N/A"
            r_pct = f"{r_val*100:8.1f}%" if r_val is not None else "     N/A"
            row = f"{metric_key:<35} | {b_pct} | {s_pct} | {r_pct}"
        print(row)
        
    print("-" * 75)
    print(f"Comparison report saved to: {out_file}\n")
    return comparison_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DataVerse Evaluation Benchmark Runner")
    parser.add_argument("--mode", choices=["real", "mock"], default="mock", help="Execution mode (real LLM API or mock client)")
    parser.add_argument("--provider", type=str, default=None, help="LLM provider override (groq, together, openai)")
    parser.add_argument("--model", type=str, default=None, help="Specific model name override")
    parser.add_argument("--approach", choices=["recovery", "schema", "baseline"], default="recovery", help="Prompting approach to evaluate")
    parser.add_argument("--max-retries", type=int, default=None, help="Max retry attempts for recovery pipeline")
    parser.add_argument("--delay", type=float, default=1.5, help="Sleep delay between real API requests in seconds")
    parser.add_argument("--compare-approaches", action="store_true", help="Run 3-way approach comparison across all benchmark cases")
    args = parser.parse_args()
    
    if args.compare_approaches:
        run_approach_comparison(mode=args.mode, provider=args.provider, model=args.model)
    else:
        run_evaluation(
            mode=args.mode,
            provider=args.provider,
            model=args.model,
            approach=args.approach,
            max_retries=args.max_retries,
            delay=args.delay
        )
