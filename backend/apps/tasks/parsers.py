"""Parsers for health check and completion check script outputs.

Health check scripts should print JSON like:
    {"status": "ok", "details": {...}}

Completion check scripts should print JSON like:
    {"step1": "ok", "step2": "failed", ...}

Parsers are tolerant: they look for the first JSON object in stdout,
scanning line by line first, then falling back to brace matching.
"""
import json
import re


def extract_json(output: str) -> dict | None:
    """Extract the first JSON object from arbitrary script output."""
    if not output:
        return None
    # Fast path: line-by-line scan
    for line in output.strip().split("\n"):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    # Fallback: brace matching on the whole output
    match = re.search(r"\{.*\}", output, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def parse_health_output(output: str, exit_code: int) -> dict:
    """Parse health check output into a structured result.

    Returns dict with keys: ok (bool), status, details, raw.
    A health check passes when exit_code == 0 and, if JSON was emitted,
    its "status" field is not an explicit failure value.
    """
    parsed = extract_json(output)
    if parsed is None:
        return {
            "ok": exit_code == 0,
            "status": "ok" if exit_code == 0 else "failed",
            "details": {},
            "raw": (output or "")[:2000],
        }
    status = str(parsed.get("status", "ok")).lower()
    ok = exit_code == 0 and status not in ("failed", "fail", "error", "unhealthy")
    return {
        "ok": ok,
        "status": status,
        "details": parsed.get("details", {}),
        "raw": (output or "")[:2000],
    }


def parse_completion_output(output: str, exit_code: int) -> dict:
    """Parse completion check output into a step→status matrix row.

    Returns dict with keys: ok (bool), steps ({name: status}), raw.
    """
    parsed = extract_json(output)
    if parsed is None:
        return {
            "ok": exit_code == 0,
            "steps": {},
            "raw": (output or "")[:2000],
        }
    steps = {k: v for k, v in parsed.items() if k != "status"}
    all_ok = exit_code == 0 and all(
        str(v).lower() in ("ok", "success", "passed", "true") for v in steps.values()
    ) if steps else exit_code == 0
    return {"ok": all_ok, "steps": steps, "raw": (output or "")[:2000]}
