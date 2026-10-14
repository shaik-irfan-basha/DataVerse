import json

with open('eval/reports/benchmark_20260920_141035.json', 'r') as f:
    report = json.load(f)

metadata = report['metadata']
metrics = report['metrics']
traces = report['traces']

print(f"1. metadata.is_complete: {metadata.get('is_complete')}")
print(f"2. metadata.note: {metadata.get('note')}")
print(f"3. total trace count: {len(traces)}")

provider_failures = [t for t in traces if t['actual_outcome'] in ['FAILED_API_RATE_LIMIT', 'FAILED_API_ERROR', 'FAILED_UNKNOWN_ERROR']]
print(f"4. provider failures ({len(provider_failures)}):")
for t in provider_failures:
    print(f"   - {t['case_id']}: {t['actual_outcome']}")

model_failures = [t for t in traces if t['actual_outcome'] in ['FAILED_JSON_VALIDATION', 'FAILED_NO_SQL'] or (t['actual_outcome'] == 'SUCCESS' and not t['result_equivalence'])]
print(f"5. model failures ({len(model_failures)}):")
for t in model_failures:
    print(f"   - {t['case_id']}: {t['actual_outcome']} (Eq: {t.get('result_equivalence', False)})")

successful_cases = [t for t in traces if t['actual_outcome'] == 'SUCCESS' and t['result_equivalence']]
print(f"6. successful cases ({len(successful_cases)}):")
for t in successful_cases:
    print(f"   - {t['case_id']}")

incorrect_cases = [t for t in traces if t['actual_outcome'] == 'SUCCESS' and not t['result_equivalence']]
print(f"7. incorrect-result cases ({len(incorrect_cases)}):")
for t in incorrect_cases:
    print(f"   - {t['case_id']}")

security_cases = [t for t in traces if t['actual_outcome'] == 'FAILED_SECURITY']
print(f"8. security-rejection cases ({len(security_cases)}):")
for t in security_cases:
    print(f"   - {t['case_id']}")

ambiguity_outcomes = [t for t in traces if t['category'] == 'AMBIGUOUS_QUESTION']
print(f"9. ambiguity outcomes ({len(ambiguity_outcomes)}):")
for t in ambiguity_outcomes:
    print(f"   - {t['case_id']}: {t['actual_outcome']}")

edge_case_outcomes = [t for t in traces if t['category'] == 'EDGE_CASE']
print(f"10. edge-case outcomes ({len(edge_case_outcomes)}):")
for t in edge_case_outcomes:
    print(f"   - {t['case_id']}: {t['actual_outcome']} (Expected: {t.get('expected_behavior')})")

print("\n--- STORED METRICS ---")
for k, v in metrics.items():
    print(f"{k}: {v}")

print("\n--- RECOMPUTING METRICS ---")
provider_fails_set = {'FAILED_API_RATE_LIMIT', 'FAILED_API_ERROR', 'FAILED_UNKNOWN_ERROR'}
sql_eval = [t for t in traces if t['category'] in ['CLEAR_QUESTION', 'RECOVERY_CASE'] and t['actual_outcome'] not in provider_fails_set]
amb = [t for t in traces if t['category'] == 'AMBIGUOUS_QUESTION' and t['actual_outcome'] not in provider_fails_set]
sec = [t for t in traces if t['category'] == 'SECURITY_ADVERSARIAL' and t['actual_outcome'] not in provider_fails_set]
edge = [t for t in traces if t['category'] == 'EDGE_CASE' and t['actual_outcome'] not in provider_fails_set]

n_sql = len(sql_eval)
print(f"Eligible SQL eval cases (excludes provider failures): {n_sql}")
exec_acc = sum(1 for t in sql_eval if t['result_equivalence']) / max(1, n_sql)
init_succ = sum(1 for t in sql_eval if t['initial_success'] and t['result_equivalence']) / max(1, n_sql)

failed_init = [t for t in sql_eval if not (t['initial_success'] and t['result_equivalence'])]
rec_succ = sum(1 for t in failed_init if t['result_equivalence'] and t['retries_used'] > 0) / max(1, len(failed_init))

print(f"Recomputed execution_accuracy: {exec_acc}")
print(f"Recomputed initial_success_rate: {init_succ}")
print(f"Recomputed recovery_success_rate: {rec_succ}")

print("\n--- CASE BY CASE TABLE ---")
print(f"{'case':<5} | {'category':<20} | {'outcome':<25} | {'result_equivalence':<18} | {'retries':<7} | {'provider_failure'}")
print("-" * 100)
for t in traces:
    pf = "Yes" if t['actual_outcome'] in provider_fails_set else "No"
    req = str(t.get('result_equivalence', False))
    ret = str(t.get('retries_used', 0))
    print(f"{t['case_id']:<5} | {t['category']:<20} | {t['actual_outcome']:<25} | {req:<18} | {ret:<7} | {pf}")
