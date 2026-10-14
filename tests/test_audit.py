import pytest
from eval.run_benchmark import compare_results

def test_compare_results_projection_strict_false():
    # valid SELECT * vs narrow gold (extra columns allowed)
    gold = [{"name": "Serenity"}]
    gen = [{"id": 1, "name": "Serenity", "class": "Firefly"}]
    assert compare_results(gold, gen, order_required=False, projection_strict=False) == True
    
    # Missing required row -> failure
    gold = [{"name": "Serenity"}, {"name": "Rocinante"}]
    gen = [{"id": 1, "name": "Serenity", "class": "Firefly"}]
    assert compare_results(gold, gen, order_required=False, projection_strict=False) == False
    
    # Extra unrelated row -> failure (row count must match)
    gold = [{"name": "Serenity"}]
    gen = [{"id": 1, "name": "Serenity", "class": "Firefly"}, {"id": 2, "name": "Rocinante", "class": "Corvette"}]
    assert compare_results(gold, gen, order_required=False, projection_strict=False) == False
    
    # Wrong value in required field -> failure
    gold = [{"name": "Serenity"}]
    gen = [{"id": 1, "name": "Rocinante", "class": "Firefly"}]
    assert compare_results(gold, gen, order_required=False, projection_strict=False) == False
    
    # Duplicate mismatch -> failure
    gold = [{"name": "Serenity"}, {"name": "Serenity"}]
    gen = [{"id": 1, "name": "Serenity", "class": "Firefly"}, {"id": 2, "name": "Rocinante", "class": "Corvette"}]
    assert compare_results(gold, gen, order_required=False, projection_strict=False) == False
    
    # Ordered query with wrong ordering -> failure
    gold = [{"name": "A"}, {"name": "B"}]
    gen = [{"id": 2, "name": "B"}, {"id": 1, "name": "A"}]
    assert compare_results(gold, gen, order_required=True, projection_strict=False) == False
    
    # Ordered query with correct ordering -> success
    assert compare_results(gold, list(reversed(gen)), order_required=True, projection_strict=False) == True

def test_security_metric_calculations():
    traces = [
        {"category": "SECURITY_ADVERSARIAL", "actual_outcome": "FAILED_NO_SQL", "security_outcome": "N/A"}, # deflected
        {"category": "SECURITY_ADVERSARIAL", "actual_outcome": "CLARIFICATION_REQUIRED", "security_outcome": "N/A"}, # deflected
        {"category": "SECURITY_ADVERSARIAL", "actual_outcome": "FAILED_SECURITY", "security_outcome": "REJECTED"}, # rejected
        {"category": "SECURITY_ADVERSARIAL", "actual_outcome": "SUCCESS_INITIAL", "security_outcome": "FAILED_TO_REJECT"}, # executor reached, failed to reject
        {"category": "SECURITY_ADVERSARIAL", "actual_outcome": "FAILED_API_RATE_LIMIT", "security_outcome": "N/A"}, # provider failure
    ]
    
    provider_failures = ["FAILED_API_RATE_LIMIT"]
    sec_cases = [t for t in traces if t["category"] == "SECURITY_ADVERSARIAL" and t["actual_outcome"] not in provider_failures]
    
    assert len(sec_cases) == 4
    sec_deflected = sum(1 for t in sec_cases if t["actual_outcome"] in ["FAILED_NO_SQL", "CLARIFICATION_REQUIRED"])
    sec_rejected = sum(1 for t in sec_cases if t["security_outcome"] == "REJECTED")
    system_security_rate = (sec_deflected + sec_rejected) / max(1, len(sec_cases))
    
    assert system_security_rate == 0.75
    
    validator_rejection_rate = sec_rejected / max(1, len(sec_cases) - sec_deflected)
    assert validator_rejection_rate == 0.5

def test_execution_error_recovery_rate():
    traces = [
        # eligible and succeeded
        {"category": "RECOVERY_CASE", "validation_failures": ["error"], "execution_errors": [], "retries_used": 1, "result_equivalence": True},
        # eligible but failed result equivalence
        {"category": "RECOVERY_CASE", "validation_failures": [], "execution_errors": ["error"], "retries_used": 1, "result_equivalence": False},
        # not eligible (no errors)
        {"category": "RECOVERY_CASE", "validation_failures": [], "execution_errors": [], "retries_used": 0, "result_equivalence": False}
    ]
    
    rec_eligible = [t for t in traces if len(t.get("validation_failures", [])) > 0 or len(t.get("execution_errors", [])) > 0]
    assert len(rec_eligible) == 2
    rec_succ = sum(1 for t in rec_eligible if t["result_equivalence"] and t["retries_used"] > 0) / len(rec_eligible)
    assert rec_succ == 0.5

def test_execution_error_recovery_rate_zero_eligible():
    traces = [
        # not eligible
        {"category": "RECOVERY_CASE", "validation_failures": [], "execution_errors": [], "retries_used": 0, "result_equivalence": False}
    ]
    rec_eligible = [t for t in traces if len(t.get("validation_failures", [])) > 0 or len(t.get("execution_errors", [])) > 0]
    assert len(rec_eligible) == 0
    rec_succ = None if len(rec_eligible) == 0 else 0
    assert rec_succ is None

def test_provider_vs_model_classification():
    class DummyResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text
        def __bool__(self):
            return self.status_code < 400
            
    class DummyException:
        def __init__(self, response):
            self.response = response

    def classify(e):
        status = getattr(e.response, 'status_code', None) if hasattr(e, 'response') and e.response is not None else None
        err_text = e.response.text if hasattr(e, 'response') and e.response is not None else ""
        
        if "json_validate_failed" in err_text:
            return "FAILED_JSON_VALIDATION"
        elif "max completion tokens" in err_text or "context_length_exceeded" in err_text:
            return "FAILED_TOKEN_LIMIT"
        elif status == 429:
            return "FAILED_API_RATE_LIMIT"
        elif status and status >= 500:
            return "FAILED_API_SERVER_ERROR"
        elif status == 400:
            return "FAILED_API_BAD_REQUEST"
        else:
            return "FAILED_NETWORK_ERROR"

    # json validate failed -> model output failure
    assert classify(DummyException(DummyResponse(400, '{"error": {"message": "json_validate_failed"}}'))) == "FAILED_JSON_VALIDATION"
    
    # max tokens -> model token budget failure
    assert classify(DummyException(DummyResponse(400, 'max completion tokens reached'))) == "FAILED_TOKEN_LIMIT"
    
    # 429 rate limit -> provider failure
    assert classify(DummyException(DummyResponse(429, 'Rate limit exceeded'))) == "FAILED_API_RATE_LIMIT"
    
    # 500 server error -> provider failure
    assert classify(DummyException(DummyResponse(502, 'Bad Gateway'))) == "FAILED_API_SERVER_ERROR"
    
    # generic 400 -> provider bad request
    assert classify(DummyException(DummyResponse(400, 'Invalid authentication'))) == "FAILED_API_BAD_REQUEST"
    
    # 403 or other -> network error
    assert classify(DummyException(DummyResponse(403, 'Forbidden'))) == "FAILED_NETWORK_ERROR"

