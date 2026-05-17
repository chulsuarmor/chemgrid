"""ct_2nd_review.py — Rule EE per-deliverable PASS count checker.

Rule EE (CLAUDE.md):
  Worker 산출물에 audit 3팀 1차 PASS 후 ct_2nd_review.py per-deliverable 카운트.
  5 PASS 미달 시 sonnet 추가 2팀 자동 spawn.
  5팀 전원 PASS 시만 6단계 진입.

This script:
1. Scans docs/reports/audit/ for all audit_*.md files.
2. Groups them by deliverable (M-number or Worker name).
3. Counts PASS verdicts per deliverable (case-insensitive 'PASS' lines).
4. Identifies deliverables with < 5 PASS entries.
5. Returns JSON with per-deliverable counts + overall Rule EE verdict.

Usage:
  python housing/sinktank/ct_2nd_review.py
  python housing/sinktank/ct_2nd_review.py --json  # JSON output only

Rule I: MAGIC numbers annotated.
Rule M: logger.warning on all failures.
Rule N: isinstance() type guards.
"""

import argparse
import glob
import json
import logging
import os
import re
import sys
from datetime import datetime

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [MAGIC: 5] Rule EE — 5 PASS minimum per deliverable before 6단계 진입
_EE_PASS_THRESHOLD = 5

# [MAGIC: 2] Rule EE — sonnet 추가 2팀 spawn when threshold not met
_EE_EXTRA_TEAMS = 2

# Patterns to detect PASS verdicts in audit report files
_PASS_PATTERNS = [
    re.compile(r"\bPASS\b", re.IGNORECASE),
    re.compile(r"verdict\s*[:=]\s*PASS", re.IGNORECASE),
    re.compile(r"결과\s*[:：]\s*PASS", re.IGNORECASE),
    re.compile(r"APPROVED", re.IGNORECASE),
]

# Patterns to detect REJECT verdicts
_REJECT_PATTERNS = [
    re.compile(r"\bREJECT\b", re.IGNORECASE),
    re.compile(r"verdict\s*[:=]\s*REJECT", re.IGNORECASE),
    re.compile(r"\bFAIL\b", re.IGNORECASE),
]

# M-number extraction from filename
_M_NUMBER_RE = re.compile(r"M(\d{3,6})", re.IGNORECASE)

# Worker name extraction from filename
_WORKER_RE = re.compile(r"W(\d{1,4}[a-z]?)", re.IGNORECASE)

# Team name patterns in filename
_TEAM_RE = re.compile(r"audit_(theory|gui|integration)_", re.IGNORECASE)


def _extract_deliverable_key(filename: str) -> str:
    """Extract deliverable key (M-number or Worker name) from audit filename.

    Prefers M-number if present, falls back to Worker designation.
    Returns 'UNKNOWN' if neither found.
    """
    if not isinstance(filename, str):  # Rule N
        return "UNKNOWN"

    basename = os.path.basename(filename)

    # Try M-number first (higher specificity)
    m_match = _M_NUMBER_RE.search(basename)
    if m_match:
        return f"M{m_match.group(1)}"

    # Try Worker designation
    w_match = _WORKER_RE.search(basename)
    if w_match:
        return f"W{w_match.group(1)}"

    # Fall back to date-based grouping (YYYYMMDD)
    date_match = re.search(r"(\d{8})", basename)
    if date_match:
        return f"DATE_{date_match.group(1)}"

    return "UNKNOWN"


def _count_pass_in_file(filepath: str) -> int:
    """Count number of distinct PASS verdicts in an audit report file.

    Each PASS pattern match on a separate line counts as 1.
    Returns -1 on read error.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError as e:
        logger.warning("ct_2nd_review: cannot read %s: %s", filepath, e)
        return -1

    if not isinstance(lines, list):  # Rule N
        logger.warning("ct_2nd_review: unexpected non-list from readlines: %s", filepath)
        return 0

    pass_count = 0
    for line in lines:
        if not isinstance(line, str):  # Rule N
            continue
        for pat in _PASS_PATTERNS:
            if pat.search(line):
                pass_count += 1
                break  # count each line once

    return pass_count


def _count_reject_in_file(filepath: str) -> int:
    """Count REJECT/FAIL verdicts in an audit report file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError as e:
        logger.warning("ct_2nd_review: cannot read %s: %s", filepath, e)
        return -1

    reject_count = 0
    for line in lines:
        if not isinstance(line, str):
            continue
        for pat in _REJECT_PATTERNS:
            if pat.search(line):
                reject_count += 1
                break

    return reject_count


def run_ct_2nd_review() -> dict:
    """Main Rule EE per-deliverable PASS count analysis.

    Returns:
        {
          "deliverables": {
            "M1346": {"pass_count": 3, "reject_count": 0, "files": [...], "verdict": "INSUFFICIENT"},
            "M1347": {"pass_count": 6, "reject_count": 1, "files": [...], "verdict": "PASS"},
            ...
          },
          "summary": {
            "total_deliverables": N,
            "pass_threshold": 5,
            "insufficient": [...],
            "sufficient": [...],
            "rule_ee_action": "WAVE_4_OK" | "SPAWN_2_TEAMS",
          },
          "overall": "PASS" | "INSUFFICIENT",
          "timestamp": "...",
          "audit_files_scanned": N,
        }
    """
    audit_dir = os.path.join(PROJECT_ROOT, "docs", "reports", "audit")
    evidence_dir = os.path.join(PROJECT_ROOT, "docs", "reports")
    housing_evidence = os.path.join(PROJECT_ROOT, "housing", "evidence")

    # Collect all audit_*.md files from audit/ and docs/reports/
    audit_files: list = []
    for search_dir in [audit_dir, evidence_dir]:
        if os.path.isdir(search_dir):
            audit_files += glob.glob(os.path.join(search_dir, "audit_*.md"))

    # Also scan housing/evidence/ for EVIDENCE_*.md with audit verdicts
    if os.path.isdir(housing_evidence):
        audit_files += glob.glob(os.path.join(housing_evidence, "EVIDENCE_*.md"))

    audit_files = sorted(set(audit_files))

    if not audit_files:
        logger.warning("ct_2nd_review: no audit_*.md or EVIDENCE_*.md files found")
        return {
            "deliverables": {},
            "summary": {
                "total_deliverables": 0,
                "pass_threshold": _EE_PASS_THRESHOLD,
                "insufficient": [],
                "sufficient": [],
                "rule_ee_action": "NO_FILES",
            },
            "overall": "INSUFFICIENT",
            "timestamp": datetime.now().isoformat(),
            "audit_files_scanned": 0,
            "error": "no_audit_files",
        }

    # Group files by deliverable key
    deliverable_files: dict = {}
    for fpath in audit_files:
        key = _extract_deliverable_key(fpath)
        if not isinstance(key, str):  # Rule N
            key = "UNKNOWN"
        if key not in deliverable_files:
            deliverable_files[key] = []
        deliverable_files[key].append(fpath)

    # Count PASS per deliverable
    deliverables: dict = {}
    for key, files in deliverable_files.items():
        total_pass = 0
        total_reject = 0
        file_details: list = []

        for fpath in files:
            pass_cnt = _count_pass_in_file(fpath)
            reject_cnt = _count_reject_in_file(fpath)
            rel_path = os.path.relpath(fpath, PROJECT_ROOT).replace("\\", "/")
            file_details.append({
                "file": rel_path,
                "pass_count": pass_cnt,
                "reject_count": reject_cnt,
            })
            if pass_cnt > 0:
                total_pass += pass_cnt
            if reject_cnt > 0:
                total_reject += reject_cnt

        verdict = "PASS" if total_pass >= _EE_PASS_THRESHOLD else "INSUFFICIENT"
        deliverables[key] = {
            "pass_count": total_pass,
            "reject_count": total_reject,
            "files": file_details,
            "file_count": len(files),
            "verdict": verdict,
        }

    # Categorize
    insufficient = [k for k, v in deliverables.items() if v["verdict"] == "INSUFFICIENT"]
    sufficient = [k for k, v in deliverables.items() if v["verdict"] == "PASS"]

    # Rule EE action
    if insufficient:
        rule_ee_action = f"SPAWN_{_EE_EXTRA_TEAMS}_TEAMS"
        overall = "INSUFFICIENT"
        logger.warning(
            "ct_2nd_review: Rule EE — %d deliverable(s) below %d PASS threshold: %s",
            len(insufficient), _EE_PASS_THRESHOLD, insufficient[:10],
        )
        logger.warning(
            "ct_2nd_review: Rule EE action = SPAWN_%d_TEAMS (sonnet 추가 %d팀 spawn 필요)",
            _EE_EXTRA_TEAMS, _EE_EXTRA_TEAMS,
        )
    else:
        rule_ee_action = "WAVE_4_OK"
        overall = "PASS"
        logger.info(
            "ct_2nd_review: Rule EE — all %d deliverable(s) >= %d PASS. WAVE 4 진입 OK.",
            len(sufficient), _EE_PASS_THRESHOLD,
        )

    result = {
        "deliverables": deliverables,
        "summary": {
            "total_deliverables": len(deliverables),
            "pass_threshold": _EE_PASS_THRESHOLD,
            "insufficient_count": len(insufficient),
            "sufficient_count": len(sufficient),
            "insufficient": insufficient,
            "sufficient": sufficient,
            "rule_ee_action": rule_ee_action,
            "extra_teams_if_needed": _EE_EXTRA_TEAMS,
        },
        "overall": overall,
        "timestamp": datetime.now().isoformat(),
        "audit_files_scanned": len(audit_files),
    }
    return result


def main() -> None:
    """CLI entrypoint for ct_2nd_review."""
    parser = argparse.ArgumentParser(
        description="Rule EE per-deliverable PASS count checker"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON only (suppress human-readable summary)"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write JSON result to this file path"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s"
    )

    result = run_ct_2nd_review()

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False, indent=2)
            print(f"[ct_2nd_review] JSON saved to {args.output}")
        except OSError as e:
            logger.warning("ct_2nd_review: failed to write output file: %s", e)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Human-readable summary
    summary = result.get("summary", {})
    print("\n=== ct_2nd_review Rule EE Report ===")
    print(f"Scanned files  : {result.get('audit_files_scanned', 0)}")
    print(f"Deliverables   : {summary.get('total_deliverables', 0)}")
    print(f"PASS threshold : {summary.get('pass_threshold', _EE_PASS_THRESHOLD)}")
    print(f"Sufficient     : {summary.get('sufficient_count', 0)}")
    print(f"Insufficient   : {summary.get('insufficient_count', 0)}")
    print(f"Rule EE action : {summary.get('rule_ee_action', 'N/A')}")
    print(f"Overall        : {result.get('overall', 'N/A')}")

    insufficient_list = summary.get("insufficient", [])
    if insufficient_list:
        print(f"\n5 PASS 미달 deliverables ({len(insufficient_list)}건):")
        for key in insufficient_list:
            d = result["deliverables"].get(key, {})
            print(f"  {key}: pass={d.get('pass_count', 0)}, "
                  f"reject={d.get('reject_count', 0)}, "
                  f"files={d.get('file_count', 0)}")
        print(f"\nRule EE: sonnet 추가 {_EE_EXTRA_TEAMS}팀 spawn 필요 → CT 5차 의뢰")
    else:
        print("\n모든 deliverable >= 5 PASS — WAVE 4 진입 권고")

    print("")


if __name__ == "__main__":
    main()
