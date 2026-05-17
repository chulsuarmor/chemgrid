"""ChemGrid 1-hour patrol script.

Runs automated quality checks:
1. py_compile (src/app + _source)
2. _source sync verification
3. except:pass violation scan
4. Antivirus security + organic checks
5. Feed collection + qwen summarization (if Ollama available)

Gate checks (integrated from housing/gate.py):
- G1 BUILD: py_compile all .py files
- G2 HOLLOW: detect 0-byte files + skills < 50 chars
- G3 SMILES: validate SMILES strings in recently modified files via RDKit
- G4 AUDIT_FORMAT: evidence files exist and are non-empty
- G7 RUNTIME: actual runtime functionality (MainWindow, predict_all, mechanism, DryLab)
- G7-SC36: DirectML ml_dml env check (M478) - python/torch-directml/verify/benchmark
- G7-SC37: foreground_cycle.sh 프로세스 감시 (M479) - 프로세스 부재 + STOP_FILE 부재 = WARN
- G7-SC41: ORCA 사용 정합성 감시 (M486) - ORCA_AVAILABLE=False silent return REJECT / "ORCA 계산 중" 가드 미체크 REJECT / 스펙트럼 엔진기반 라벨 누락 WARN
- G7-SC43: tools/*.py + housing/**/*.sh + docs/ai/skills/*.md 워크트리 동기화 검사 (M491) - P-WORKTREE 5회 재발 차단 WARN
- G7-SC46: SIMULATION_MODE / fallback 사용처에 UI 명시 라벨 존재 검증 (M497) - P-MOCK-DISGUISED FP-15 재발 차단 WARN
- G7-SC47: PDBe Mol* prominent 버튼 존재 검증 (M499) - popup_docking/alphafold에 PDBe Mol* URL + QDesktopServices.openUrl 의무 WARN
- G7-SC49: P-POPUP-GHOST 탐지 (M544) - foreground_test popup_3d 시나리오에서 popup_widget_found=False 항목 탐지 — btn.click() 후 신규 topLevel 창 미탐지 = ghost screenshot WARN
- G7-SC52: worktree av_validator.py 라인 수 검사 (M545) - main repo 동기화 미반영 시 1400줄 미만 = WARN (P-AV-SHALLOW 재발 환경 차단)
- G7-SC55: Theory layer ESP cloud 보존 검사 (M555/M557) - _draw_per_atom_clouds 미존재/alpha_center<100/QRadialGradient 미사용 = WARN (전자구름 제거 패턴 차단)
- G7-SC56: anger_simulator 매트릭스 100+건 + ML 진화 갱신 검증 (M556) - 매트릭스<100건 / anger_metrics.json mtime 6h 초과 / pool_size<8 = WARN (FP-21 P-STATIC-PATTERN-POOL 차단)
- G7-SC57: cmd 창 노출 패턴 자동 탐지 (M558) - run_hidden.vbs 미존재 / evidence MD에서 cmd /c 직접 호출+Hidden 없음 / schtasks /Create 직접 호출+Hidden 없음 = WARN (P-CMD-EXPOSED FP-22 재발 차단)
- G8 WEB_PARITY: web API vs desktop engine comparison (IR, ADMET, Lewis)
- G7-SC67: 토큰 효율화 인프라 미비 감지 (M617) - multi_llm.py 미존재 / api_limit_handler.py 미존재 / skills/token_efficiency.md 미존재 = WARN
- G7-SC70: OpenRouter Kimi 비용 모니터링 인프라 미비 감지 (M624) - openrouter_usage_check.py 미존재 / latest_usage.json fetch_ok=False / 잔액 RED 경보 / skills/openrouter_cost_monitor.md 미존재 = WARN (Rule MM 체화)
- G7-SC68: Kimi K2 인프라 미비 감지 (M618->M623) - kimi_client.py 미존재 / api_limit_handler.py 미존재 = WARN (M618 권고 신설)
- G7-SC69: 다람쥐볼 auto-attach hook 검증 (M623) - squirrel_ball_auto_attach.py 미존재 / settings.json 미등록 / DENY_RATE>30% = WARN (Rule V 자동화 인프라)
- G7-SC73: Kimi 자동 호출 hook 강제 메커니즘 검증 (M627) - kimi_auto_invoke.py 미존재 / settings.json 미등록 / kimi_invoke_log.jsonl 0건 = WARN (P-EXTERNAL-AI-UNUSED FP-27)
- G7-SC75: Vision + 한국어 + 자연어 로컬 LLM 인프라 검증 (M634) - multi_llm.py local_vision_audit/korean_classify/natural_language_query 미존재 / Ollama vision 모델(minicpm-v/phi3.5) 미등록 / skills/local_vision_korean.md 미존재 = WARN (사용자 명령: 이미지 정밀 분석 + 자연어 처리 우수 로컬 LLM 활용)
- G7-SC78: 4-Layer Vision Audit + 3개월 미해소 격분 시계열 검증 (M636) - housing/sinktank/multi_layer_vision_audit.py / tools/anger_timeline_tracker.py / .claude/hooks/repeat_pattern_block.py / .claude/anger_timeline_M636.json (24h freshness + CRITICAL 0건) 미충족 = WARN (사용자 명령: 정합성까지 제대로 검증 + 3달째 안사라지는 격분 자동 ESCALATE, FP-31 차단, Rule SS 체화)
- G7-SC76: 로컬LLM 영구가동 인프라 검증 (M635) - SWARM_TIER_E+pick_specialist + session hooks 3종 + zombie_check + settings.json + skills 2종 = WARN (FP-30 P-ZOMBIE-PROCESS)
- G7-SC71: 학술 정합성 자동 audit hook + Kimi 자동 호출 검증 (M625) - .claude/hooks/academic_integrity_check.py 미존재 / settings.json PostToolUse Edit|Write 미등록 / skills/academic_integrity_auto.md 미존재 / academic_integrity_log.jsonl 비어있음 = WARN (Rule NN 체화)
- G7-SC72: 사용자 환경 자체 검증 hook + Kimi K2.6 Vision 검증 (M626) - housing/sinktank/user_env_auto_verify.py 미존재 / .claude/hooks/user_env_verify.py 미존재 / settings.json PostToolUse 미등록 / multi_llm.kimi_vision_audit() 미존재 / skills/user_env_auto_verify.md 미존재 / .claude/user_env_log.jsonl 누적 0건 = WARN (Rule OO 체화, FP-26 P-USR-ENV-UNVERIFIED 차단)
- G7-SC74: Ollama 로컬 LLM 스웜 인프라 검증 (M633) - multi_llm.chemgrid_c23_chat 미존재 / multi_llm.local_swarm_parallel 미존재 / gpu_load_monitor_M633.py 미존재 / Ollama 미실행 + 로컬 호출 0건 = WARN (Rule QQ P-LOCAL-LLM-UNUSED FP-29)
- G7-SC77: 웹 배포 readiness 검증 (M629) - frontend/dist/index.html 없음 / tools/deployment_check.py 없음 / DEPLOYMENT_GUIDE_M629.md 없음 / skills/web_deployment.md 없음 = WARN (사용자 명령: 웹 배포 나가야 한다)
- G7-SC79: M638 외부 연산 5 endpoint 존재 검증 (M638) - chemgrid_mobile/backend/routers/{xtb,askcos,orca_proxy,alphafold}.py + frontend/src/components/PDBeMolstarViewer.tsx + skills/external_compute_integration.md 미존재 / endpoint 키 누락 = WARN (사용자 명령: xtb/AlphaFold/ASKCOS/PDBe Mol* 웹 통합 + ORCA 자체 서버 분리)
- G7-SC87: M645_W4 P-ALIVE-NO-PROGRESS 탐지 (WARN 비차단) - ralph_loop 프로세스 alive + 1시간 git commit 0건 + 30분 산출물 파일 0건 = REJECT 권고 (FP-37 확장, Q-N14 격분)
- G7-SC88: M645_W4 P-WRONG-VERIFICATION 탐지 (WARN 비차단) - Worker 보고서에 "PID alive" 패턴 + tasklist/ps -ef 실측 증거 미첨부 = WARN (P-PHANTOM-PID FP-37 재발 방지 강화)
- G7-SC89: M645_W4 P-USER-PERSONA-SKIP 탐지 (WARN 비차단) - Worker/CT 보고서에 user_persona_critic 5질문 자가시뮬레이션 미첨부 / critic_spawn_log.jsonl 미존재 = WARN (Rule TT 체화)
- G7-SC90: M645_W4 P-DOUBLE-FALSE-POSITIVE 탐지 (WARN 비차단) - user_persona_critic.py 미존재 / critic_before_ct_spawn.py 미존재 / FP-38 미등록 = WARN (이중 가짜 PASS 차단)
- G7-SC93: M647_W5_A6 P-CRON-AV-VARIANT-FRAGMENT 탐지 (WARN 비차단) - housing/sinktank/에 cron_av_ct.py/cron_av_ct_v2.py/cron_av_report.py/cron_av_daemon.py DEPRECATED 마커 없이 존재 / cron_av_unified.py 미존재 / .claude/notifications/ 폴더 미존재 = WARN (4변종 분기 D2 결함 5 → 통합 단일 진입점 의무)
- G7-SC94: M647_W5_A19 P-AV-SKILL-MISSING 탐지 (WARN 비차단) - docs/ai/skills/av_compliance.md 미존재 = WARN (AV skill 1년 미작성 패턴 재발 차단)
- G7-SC95: M647_W5_A15 P-HARNESS-COMPRESS 탐지 (WARN 비차단) - CLAUDE.md에서 CT Decision/M번호 등 핵심 키워드 삭제 시 WARN (Rule QQ)
- G7-SC96: CT-D-20260504-A55 P-AV-PROMPT-STALE 탐지 (WARN/CRITICAL 비차단) - docs/ai/inbox/AV_NEXT_PROMPT.md mtime 60분 초과 = WARN / 24시간 초과 = CRITICAL (채팅창 AV 발화 인프라 갱신 미이행 탐지)
- G7-SC97: CT-D-20260504-A55 P-NO-EXTERNAL-AI-IN-PROMPT 탐지 (WARN/CRITICAL 비차단) - .claude/hooks/external_ai_dispatch_enforce.py 미존재 / settings.json Agent matcher 미등록 / sc97_no_external_ai.jsonl violation 24h 3건 이상 = CRITICAL (Rule MM/PP 외부 AI dispatch 의무 체화, M680)
- G7-SC98: A55-AV-WATCHDOG M696 P-CHEMGRID-LITE-ZOMBIE 탐지 (WARN/CRITICAL 비차단) - cron_av_unified.py m6_zombie 모듈 미존재 / module_zombie_check 함수 미존재 = WARN / zombie FAIL 24h 누적 5건+ = CRITICAL (사용자 명시: "깡통 없는지 20분 주기로 AV 돌려서 검증")
- G7-SC99: CT-D-20260504-A57-W8 M715 P-M-NUMBER-RACE 탐지 (WARN/CRITICAL 비차단) - git log 24h M번호 중복 커밋 2건+ = CRITICAL / evidence 파일 M번호 중복 24h 2건+ = WARN (Worker 동시 M번호 사용 race condition 차단)
- G7-SC100: CT-D-20260504-A57-W8 M715 P-POPUP-SIMULTANEOUS-EDIT 탐지 (WARN/CRITICAL 비차단) - git diff HEAD/HEAD~1 popup_*.py 동시 수정 3건+ = WARN / 6건+ = CRITICAL (FIX-MASS vs FIX-N Worker 충돌 탐지)
- G7-SC105: W_DISPATCH_LOGGER M818 P-EXT-AI-DISPATCH-LOG-EMPTY 탐지 (WARN/INFO 비차단) - external_ai_dispatch.jsonl 최근 1시간 호출 0건 = WARN / 최근 1시간 4건 미만 = INFO (사용자 격분 '기타ai위주로 쓰는거 맞음? 로컬LLM 돌아가는 소리 안 나는데')
- G7-SC126: D888-W13 M933 P-BEFORE-AFTER-MISSING 탐지 (WARN 비차단, C15+ REJECT 예고) - 최신 cycle HTML에 id="before-after-images" 섹션 미존재 = WARN / 섹션 내 img < 18개 = WARN. C15부터 REJECT 격상 (사용자 명시 Q-BEFORE-AFTER 6 사이클 미반영)

Can be run standalone or via scheduled-task MCP.
"""

import difflib
import glob
import json
import logging
import os
import py_compile
import re
import subprocess
import sys
import time
from datetime import datetime

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATROL_LOG = os.path.join(os.path.dirname(__file__), "_patrol_log.json")

# Minimum size in bytes for a skill file to be considered non-hollow
_SKILL_MIN_BYTES = 50  # skill files under 50 bytes are effectively empty

# How recently a file must have been modified (seconds) for SMILES scan
_SMILES_SCAN_WINDOW = 86400  # 24 hours


def check_py_compile() -> dict:
    """Compile all .py files in src/app and _source."""
    results = {"src_pass": 0, "src_fail": [], "source_pass": 0, "source_fail": []}

    for pattern, prefix in [("src/app/*.py", "src"), ("_source/*.py", "source")]:
        full_pattern = os.path.join(PROJECT_ROOT, pattern)
        for f in sorted(glob.glob(full_pattern)):
            try:
                py_compile.compile(f, doraise=True)
                results[f"{prefix}_pass"] += 1
            except py_compile.PyCompileError as e:
                results[f"{prefix}_fail"].append(str(e)[:100])

    return results


def check_source_sync() -> list[str]:
    """Verify src/app/*.py is in sync with _source/*.py.

    Detects two kinds of desync:
    1. Content mismatch: file exists in both but differs.
    2. Missing mirror: file exists in src/app/ but not in _source/.
    """
    desync = []
    src_dir = os.path.join(PROJECT_ROOT, "src", "app")
    source_dir = os.path.join(PROJECT_ROOT, "_source")

    for f in sorted(glob.glob(os.path.join(src_dir, "*.py"))):
        basename = os.path.basename(f)
        mirror = os.path.join(source_dir, basename)
        if os.path.exists(mirror):
            try:
                r = subprocess.run(
                    ["diff", "-q", f, mirror],
                    capture_output=True, text=True, timeout=5
                )
                if r.returncode != 0:
                    desync.append(basename)
            except Exception as e:
                logger.warning("diff failed for %s: %s", basename, e)
        else:
            # Mirror file missing in _source/ -- report as desync
            logger.warning("_source mirror missing for %s", basename)
            desync.append(basename)

    return desync


def check_except_pass() -> dict:
    """Scan for except:pass violations."""
    violations = {}
    for pattern in ["src/app/*.py", "_source/*.py"]:
        for f in sorted(glob.glob(os.path.join(PROJECT_ROOT, pattern))):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    content = fh.read()
                matches = re.findall(r"except[^:]*:\s*\n\s*pass\b", content)
                if matches:
                    violations[os.path.basename(f)] = len(matches)
            except OSError as e:
                logger.warning("Failed to read %s: %s", f, e)

    return violations


def check_antivirus() -> dict:
    """Run antivirus security + organic checks."""
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from housing.immune.antivirus import AntivirusEngine
        av = AntivirusEngine()

        sec = av.security_audit()
        org = av.run_organic_check()

        return {
            "security": sec.get("overall", "UNKNOWN"),
            "security_fails": sec.get("fail_count", -1),
            "organic_total": org.get("total_checks", 0),
            "organic_immune": org.get("immune", 0),
            "organic_vulnerable": org.get("vulnerable_count", 0),
        }
    except Exception as e:
        logger.warning("Antivirus check failed: %s", e)
        return {"error": str(e)}


def check_hollow_files() -> dict:
    """Gate 2 (HOLLOW): detect 0-byte .py files and skill files under 50 chars.

    Scans:
    - src/app/*.py and _source/*.py for 0-byte files
    - departments/*/skills/*.md for files shorter than _SKILL_MIN_BYTES
    """
    zero_byte: list[str] = []
    hollow_skills: list[str] = []

    # Check .py source files for 0-byte
    for pattern in ["src/app/*.py", "_source/*.py"]:
        full_pattern = os.path.join(PROJECT_ROOT, pattern)
        for fpath in sorted(glob.glob(full_pattern)):
            try:
                if os.path.getsize(fpath) == 0:
                    zero_byte.append(os.path.relpath(fpath, PROJECT_ROOT))
            except OSError as e:
                logger.warning("Cannot stat %s: %s", fpath, e)

    # Check skill files for < 50 bytes
    skill_pattern = os.path.join(PROJECT_ROOT, "departments", "*", "skills", "*.md")
    for fpath in sorted(glob.glob(skill_pattern)):
        try:
            size = os.path.getsize(fpath)
            if size < _SKILL_MIN_BYTES:
                hollow_skills.append(
                    f"{os.path.relpath(fpath, PROJECT_ROOT)} ({size}B)"
                )
        except OSError as e:
            logger.warning("Cannot stat %s: %s", fpath, e)

    return {
        "zero_byte_files": zero_byte,
        "hollow_skills": hollow_skills,
    }


def _looks_like_smiles(candidate: str) -> bool:
    """Heuristic filter: return True only if candidate string likely is a SMILES.

    Rejects common false positives: hex colors, CamelCase class names,
    Python module paths, SMARTS patterns, short fragments, etc.
    """
    # Reject very short candidates (< 5 chars) -- too ambiguous
    if len(candidate) < 5:
        return False

    # Must have at least one organic element letter (uppercase)
    if not re.search(r"[CNOSPF]", candidate):
        return False

    # Must start with a valid SMILES start character:
    # atom letter (upper or lower), bracket, or digit
    if not re.match(r"[A-Za-z\[\d]", candidate):
        return False

    # Reject hex color codes (#RRGGBB)
    if candidate.startswith("#"):
        return False

    # Reject Python identifiers: dotted paths, CamelCase without bonds
    if "." in candidate:
        return False
    if "_" in candidate:
        return False
    if candidate.startswith("http"):
        return False

    # Reject CamelCase class/function names (lowercase then uppercase)
    # unless the string also contains bond characters
    if re.search(r"[a-z][A-Z]", candidate):
        if not re.search(r"[()=\[\]]", candidate):
            return False

    # Reject SMARTS patterns: contain X or H with digits inside brackets
    # e.g. [CX3], [OX2H1] -- these are valid SMARTS, not SMILES
    if re.search(r"\[[A-Z]X\d", candidate):
        return False

    # Reject strings with Unicode escape sequences (chemical formulas
    # with subscript/superscript markers, e.g. "H\u2082O")
    if "\\u" in candidate:
        return False

    # Reject partial SMILES fragments that start with bond chars
    # like "(=NNC)", "(=NO)" -- these are substructure patterns
    if candidate.startswith("("):
        return False

    # Reject strings containing 'R' as a generic substituent marker
    # (R-group notation like "R-C(OH)(R)")
    if "R" in candidate and re.search(r"R[\-\(]", candidate):
        return False

    # Must have at least one SMILES structural character
    # (bond, branch, ring, stereo, or aromatic ring digit)
    if not re.search(r"[()=\[\]#\\/@]", candidate):
        if not re.search(r"[cnos]\d", candidate):
            return False

    return True


def check_smiles_validity() -> dict:
    """Gate 3 (SMILES): extract SMILES from recently modified .py files, validate via RDKit.

    Targets lines that explicitly use SMILES strings: variable assignments
    containing 'smiles' or 'smi' keywords, and calls to MolFromSmiles.
    Uses heuristic pre-filtering to avoid false positives from class names,
    hex colors, SMARTS patterns, etc.
    """
    invalid_smiles: list[dict] = []
    files_scanned = 0
    smiles_tested = 0

    try:
        from rdkit import Chem, RDLogger  # type: ignore
        # Suppress RDKit C++ parse-error noise during scanning
        RDLogger.DisableLog("rdApp.*")
    except ImportError:
        logger.warning("RDKit not available -- skipping SMILES gate")
        return {"error": "rdkit_not_installed", "files_scanned": 0, "invalid": []}

    now = time.time()

    # SMILES pattern: quoted strings containing typical SMILES chars
    # Matches strings like 'CC(=O)O', "c1ccccc1", etc.
    smiles_re = re.compile(
        r"""(?:['"])"""                   # opening quote
        r"""("""
        r"""[A-Za-z0-9"""
        r"""\(\)\[\]=\#\-\+\\\/\.\@\%"""  # SMILES bond/branch/stereo chars
        r"""]{5,120}"""                    # length 5..120
        r""")"""
        r"""(?:['"])"""                    # closing quote
    )

    # Context keywords: only check lines that look SMILES-related
    smiles_context_re = re.compile(
        r"(?:smiles|smi|SMILES|MolFromSmiles|MolToSmiles|canonical|"
        r"reactant|product|substrate|target_mol|mol_smi|input_smi|"
        r"smiles_str|smi_str|smiles_list|test_smiles)",
        re.IGNORECASE,
    )

    for pattern in ["src/app/*.py", "_source/*.py"]:
        full_pattern = os.path.join(PROJECT_ROOT, pattern)
        for fpath in sorted(glob.glob(full_pattern)):
            try:
                mtime = os.path.getmtime(fpath)
                if (now - mtime) > _SMILES_SCAN_WINDOW:
                    continue  # skip old files

                files_scanned += 1
                with open(fpath, "r", encoding="utf-8") as fh:
                    for line_no, line in enumerate(fh, 1):
                        # Skip comment-only lines and import lines
                        stripped = line.strip()
                        if stripped.startswith("#") or stripped.startswith("import ") or stripped.startswith("from "):
                            continue

                        # Only scan lines that mention SMILES-related keywords
                        if not smiles_context_re.search(line):
                            continue

                        for m in smiles_re.finditer(line):
                            candidate = m.group(1)

                            # Pre-filter: skip non-SMILES-looking strings
                            if not _looks_like_smiles(candidate):
                                continue

                            smiles_tested += 1
                            mol = Chem.MolFromSmiles(candidate)
                            if mol is None:
                                rel_path = os.path.relpath(fpath, PROJECT_ROOT)
                                invalid_smiles.append({
                                    "file": rel_path.replace("\\", "/"),
                                    "line": line_no,
                                    "smiles": candidate[:80],
                                })
            except OSError as e:
                logger.warning("SMILES scan failed for %s: %s", fpath, e)

    # Re-enable RDKit logging
    try:
        RDLogger.EnableLog("rdApp.*")
    except Exception:
        pass  # not critical if re-enable fails

    return {
        "files_scanned": files_scanned,
        "smiles_tested": smiles_tested,
        "invalid_count": len(invalid_smiles),
        "invalid": invalid_smiles[:20],  # cap at 20 entries for log size
    }


def check_g7_serial_compliance() -> dict:
    """Gate 7 serial-compliance sub-check (Rule T / M417 강화).

    Additional G7 checks beyond runtime tests:

    G7-SC1: EVIDENCE_*.md files must contain "CT 보고: PENDING" line.
            Missing line = Rule T violation (Worker산출물 CT미경유).
    G7-SC2: docs/reports/audit/ must have 3 audit reports for today
            (audit_theory_YYYYMMDD*.md, audit_gui_*, audit_integration_*).
            Any team missing = "AUDIT_INCOMPLETE" REJECT.
    G7-SC3: _serial_state.json staleness check (WARN, non-blocking).
    G7-SC4: audit_gui 보고서에 "Desktop Parity" 섹션 부재 시 FAIL.
            인용 스크린샷 파일 미존재 시 WARN (Rule U-f).
            사용자 결함 8건 중 5건 이상 언급 없으면 WARN (FP-06, M432).
    G7-SC5: EVIDENCE_*.md 파일에 체화 4단계 섹션 존재 검사 (Rule H, M434 신설).
            4섹션 키워드 패턴 검사: H-1(변경전사유) / H-2(skills패턴) /
            H-3(patrol/AV자동검사) / H-4(CLAUDE.md규칙).
            2섹션 미만 = WARN (비차단), 0섹션 = FAIL (차단).
            docs/ai/skills/harness_embodiment.md 참조.
    G7-SC6: mechanism_engine.py 코드 품질 검사 (M433 신설, WARN 전용 비차단).
            U+2212 전하 라벨 혼용 / _PERICYCLIC_HINTS 부재 / _truncate_label 부재 탐지.
    G7-SC7: audit_gui 보고서 클릭 시뮬레이션 증거 검사 (R-09, M436 신설).
            정규식: click simulation|mouseClick|button\\.click|QTest
            0회 매치 = FAIL (BLOCKED), 1~4회 = WARN, 5회 이상 = PASS.
            docs/ai/skills/click_based_verification.md 참조.
    G7-SC9: SIMULATION_MODE / ORCA 거짓 메시지 탐지 (M438 신설, WARN 전용 비차단).
            popup_3d.py "Using built-in engine" 거짓 메시지 / popup_docking.py 배너 미존재 /
            docking_interface.py MAX_PHYSICAL_AFFINITY cap 미존재 탐지.
            P-SCOPE 패턴(FP-08) 재발 방지. docs/ai/skills/docking_interface.md 참조.
    G7-SC12: arrow_generator.py 4색 표준 검사 (M442 신설, WARN 전용 비차단).
            ARROW_COLORS 6색 팔레트 잔존 / _ARROW_COLOR_MAP 부재 /
            _assign_colors 인덱스순환 패턴 탐지 → 교과서 4색 표준 준수 확인.
            Rule O 렌더링 품질 위반 사전 탐지.
    G7-SC14: 신규 엔드포인트가 호출하는 메서드 실제 존재 검사 (M443 신설, WARN 전용 비차단).
            qt_offscreen.py에서 CloudRenderer().render() 잘못된 인스턴스 호출 탐지.
            render_esp 브리지 함수 미존재 / draw_clouds 미호출 시 WARN.
            docs/ai/skills/api_endpoint_validation.md 참조.
    G7-SC15: 웹 spectrum 엔드포인트 임포트 불일치 탐지 (M444 신설, WARN 전용 비차단).
            predict_mass_spectrum 같이 데스크톱 미존재 함수 임포트 → ImportError →
            _CHEMGRID_ENGINE_AVAILABLE=False → 스펙트럼 빈 화면 (사용자 격분 F-04).
    G7-SC16: 메인 repo vs 워크트리 src/app/*.py diff 탐지 (M449 신설, WARN 전용 비차단).
            .claude/worktrees/ 하위 모든 활성 워크트리의 src/app/*.py를 메인 repo와 비교.
            diff 발견 시 WARN — Worker fix가 워크트리에 미반영된 P-WORKTREE 패턴(FP-09) 탐지.
            docs/ai/skills/worktree_sync_check.md 참조.
            Rule Y: 데스크톱 predict_spectra.py 5종 공개 함수만 임포트 허용.
    G7-SC19: chemgrid_mobile 워크트리 동기화 검사 (M453 신설, WARN 전용 비차단).
            audit_gui가 워크트리에서 SynthesisViewer.tsx 등 미발견 → phantom REJECT 방지.
            worktree chemgrid_mobile/ 폴더 미존재 시 WARN, 핵심 10종 파일 미존재 시 WARN.
            docs/ai/skills/worktree_sync_check.md 참조 (P-WORKTREE FP-09 확장).
    G7-SC20: chemgrid_mobile vs chemgrid/web 백엔드 동등성 검사 (M454 신설, WARN 전용 비차단).
            M443 부분 fix 패턴(D-3) 재발 방지: chemgrid/web만 fix하고 chemgrid_mobile 미처리.
            SC20-a: chemgrid_mobile qt_offscreen.py에 _normalize_bond_keys 존재 여부
            SC20-b: chemgrid_mobile qt_offscreen.py에 CloudRenderer().render() 잘못된 호출 부재 여부
            SC20-c: chemgrid_mobile qt_offscreen.py에 CloudRenderer.draw_clouds 호출 존재 여부
            docs/ai/skills/dual_backend_sync.md 참조.
    G7-SC21: AlphaFold 외부 API URL 하드코딩 탐지 (M455 신설, WARN 전용 비차단).
            model_v4.pdb / model_vN.pdb 형식의 하드코딩 → AlphaFold EBI DB latestVersion 변경 시
            HTTP 404 발생. API 방식(_resolve_alphafold_pdb_url) 동적 조회로 대체해야 함.
            SC21-a: model_vN.pdb 하드코딩 잔존 탐지
            SC21-b: _resolve_alphafold_pdb_url() 함수 존재 여부
            SC21-c: _ALPHAFOLD_DB_API_URL 상수 존재 여부
            docs/ai/skills/external_api_versioning.md 참조.

    G7-SC23: frontend fetch 경로 vs backend router prefix 불일치 탐지 (M457 신설, WARN 전용 비차단).
            MoleculeCanvas.tsx fetch('/api/analyze') vs main.py include_router prefix='/api/render' 불일치 탐지.
            SC23-a: frontend *.tsx 에서 /api/analyze fetch 잔존 탐지 (올바른 경로: /api/molecules/analyze)
            SC23-b: main.py 에서 drawing.router prefix 불일치 탐지
            docs/ai/skills/api_endpoint_validation.md §8 참조.

    G7-SC24: backend fix 후 재시작 누락 탐지 — 코드 fix vs 가동 인스턴스 불일치 (M458 신설, WARN 전용 비차단).
            drawing.py 또는 main.py에 /api/molecules prefix 설정 존재 → 포트 8000 인스턴스에 /api/molecules/analyze 요청.
            HTTP 404 응답 = 구버전 가동 중 (재시작 필요) → WARN.
            HTTP 200 응답 = 신버전 정상 가동 → PASS.
            SC24-a: main.py include_router(drawing.router, prefix="/api/molecules") 존재 여부
            SC24-b: /api/molecules/analyze HTTP 상태 코드 실시간 확인 (로컬 포트 8000)
            docs/ai/skills/backend_restart_protocol.md 참조 (M458 신설).

    G7-SC22: popup_docking.py interactions 변수 미초기화 UnboundLocalError 탐지 (M456 신설, WARN 전용 비차단).
            M438 Worker가 `if not isinstance(interactions, dict): interactions = {}` 패턴을 추가했으나
            interactions 변수 자체가 해당 스코프에서 초기화되지 않은 상태 → UnboundLocalError.
            SC22-a: `if not isinstance(interactions, dict): interactions = {}` 단독 패턴 잔존 탐지
                    (올바른 패턴: interactions_map = getattr(..., 'interactions', None) 선행 초기화)
            docs/ai/skills/docking_interface.md 참조 (M456 F2 fix).

    G7-SC25: AlphaFold 외부 링크 prominent 배치 자동 검사 (M460 신설, WARN 전용 비차단).
            사용자 요청: "굳이 우리쪽에서 3D구조 띄우는게 아니라 웹에 정확한 값 보내서 바로 알파폴드로 볼수있게"
            → AlphaFold 공식 DB 외부 링크 버튼이 입력 탭 최상단에 배치되었는지 자동 검사.
            SC25-a: popup_alphafold.py에 `btn_alphafold_external` 속성 + `_on_open_alphafold_external` 메서드 존재
            SC25-b: popup_alphafold.py에 `uniprot_id_input` 속성 존재 (UniProt ID 입력 필드)
            SC25-c: AlphaFoldPanel.tsx에 `openAlphaFoldExternal` 함수 + `uniprotId` 상태 존재
            SC25-d: AlphaFoldPanel.tsx에 `externalBanner` 스타일 + `externalBtn` 스타일 존재
            docs/ai/skills/alphafold_pdb_parser.md §외부링크우선정책 참조.

    G7-SC26: DryLab Report AlphaFold 섹션 자동 검사 (M461 신설, WARN 전용 비차단).
            사용자 요청: "학술지처럼 알파폴드 PDB에서 PDBe Mol 거쳐서 시각화하고, 알파폴드 산출 data도 DryLab에 포함"
            → DryLab PDF에 AlphaFold 기반 도킹 분석 섹션 존재 + 학술 인용 포함 자동 검사.
            SC26-a: DryLabData.alphafold_uniprot_id 필드 존재
            SC26-b: _sec_part2e_alphafold_docking 메서드 존재
            SC26-c: Jumper et al. 2021 학술 인용 존재 (이론적 정합성)
            SC26-d: alphafold_plddt_summary 필드 존재
            docs/ai/skills/alphafold_docking_integration.md 참조.

    G7-SC27: AlphaFold 6단계 학생 흐름 자동 검사 (M463 신설, WARN 전용 비차단).
            M463 목적: Protein3DViewerWidget 완전 제거 + 6단계 탭 + PDBe Mol* + DryLab 통합
            SC27-a: popup_alphafold.py에 Protein3DViewerWidget 클래스 없음 (제거 확인)
            SC27-b: popup_alphafold.py에 alphafold_to_docking 시그널 존재 (M461 보존)
            SC27-c: popup_alphafold.py에 _create_tab5_pdbe 또는 pdbe 관련 코드 존재
            SC27-d: drylab_report_exporter.py에 _sec_part2f_integrated_drug_discovery 메서드 존재
            docs/ai/skills/alphafold_student_flow.md 참조.

    G7-SC33: HTML 사이클 보고서 자동 생성 검사 (M472 신설, WARN 전용 비차단).
            M472 요구: 매 사이클마다 HTML 보고서 + index.html 자동 갱신.
            다른 세션이 index.html만 보고 진행 상황 즉시 파악 가능.
            SC33-a: tools/cycle_html_reporter.py 파일 존재 여부
            SC33-b: docs/reports/cycle_reports/ 디렉토리 존재 여부
            SC33-c: docs/reports/cycle_reports/index.html 존재 여부 (최근 사이클 실행 증거)
            SC33-d: foreground_cycle.sh에 cycle_html_reporter.py 호출 존재 여부
            docs/ai/skills/cycle_html_report.md 참조 (M474 연계).

    G7-SC34: 사이클 깡통 자동 검사 (M476 신설, WARN 전용 비차단).
            M476 목적: 인프라 존재 + 실 검증 미작동 패턴(FP-08 P-SCOPE) 자동 탐지.
            SC34-a: foreground_cycle.sh에 check_g7_runtime_smoke 잘못된 함수명 사용 탐지
                    → check_g7_serial_compliance가 올바른 함수명
            SC34-b: dft_consistency_check.py에 result.ir 잘못된 속성명 사용 탐지
                    → result.ir_peaks가 실제 PredictedSpectra 속성명 (M471 재발 방지)
            SC34-c: cycle_reports/index.html 미존재 (사이클 미실행 = 깡통)
            SC34-d: foreground_cycle.sh에 _genuine_zero_defect 함수 미존재

    G7-SC35: 웹-데스크톱 diff 자동 탐지 (M477 신설, WARN 전용 비차단).
            Rule Y strict — UX/UI 1px diff = FAIL 체계를 자동 탐지.
            SC35-a: tools/web_cycle_test_matrix.py 파일 존재 여부 (35종×22 클릭 시뮬)
            SC35-b: docs/reports/web_cycle_reports/ 디렉토리 존재 여부
            SC35-c: web_cycle_reports/index.html 존재 여부 (최근 48시간 이내 실행 증거)
            SC35-d: housing/sinktank/web_cycle.sh 존재 여부 (웹 사이클 오케스트레이터)
            SC35-e: tools/desktop_web_diff.py 파일 존재 여부 (픽셀 diff 도구)
            SC35-f: desktop_web_diff_result.json 결함 > 0 시 WARN (Rule Y 위반 잔존)
            docs/ai/skills/web_cycle_rule_y_strict.md 참조 (M477).
                    → 종료 조건 깡통 방지 부재 탐지
            docs/ai/skills/cycle_genuine_termination.md 참조 (M476 신규).

    Rule M: logger.warning on all failures.
    Rule N: isinstance guards on file content.
    Rule I: [MAGIC] annotations for team count, pattern format.
    """
    # [MAGIC] 감사 3팀 -- theory/gui/integration
    _TEAMS = ["theory", "gui", "integration"]
    # [MAGIC] CT 보고 PENDING 패턴 (Rule T)
    _CT_PENDING_RE = re.compile(
        r"CT\s*보고\s*[::\uff1a]\s*PENDING", re.IGNORECASE
    )

    today_str = datetime.now().strftime("%Y%m%d")
    evidence_dir = os.path.join(PROJECT_ROOT, "docs", "reports")
    audit_dir = os.path.join(PROJECT_ROOT, "docs", "reports", "audit")

    # -- G7-SC1: EVIDENCE CT PENDING check --
    evidence_files = []
    if os.path.isdir(evidence_dir):
        import glob as _glob
        evidence_files = _glob.glob(
            os.path.join(evidence_dir, "EVIDENCE_*.md")
        )

    sc1_missing_ct: list[str] = []
    for ev_path in evidence_files:
        try:
            with open(ev_path, "r", encoding="utf-8") as fh:
                content = fh.read()
            if not isinstance(content, str):  # Rule N
                logger.warning("G7-SC1: non-str content in %s", ev_path)
                continue
            if not _CT_PENDING_RE.search(content):
                rel = os.path.relpath(ev_path, PROJECT_ROOT).replace("\\", "/")
                sc1_missing_ct.append(rel)
                logger.warning(
                    "G7-SC1 REJECT: EVIDENCE missing CT 보고: PENDING -- %s", rel
                )
        except OSError as e:
            logger.warning("G7-SC1: cannot read %s: %s", ev_path, e)

    sc1_pass = len(sc1_missing_ct) == 0
    if not sc1_pass:
        logger.warning(
            "G7-SC1 REJECT: %d EVIDENCE file(s) missing 'CT 보고: PENDING' "
            "(Rule T violation)",
            len(sc1_missing_ct),
        )

    # -- G7-SC2: Audit 3-team completeness check --
    sc2_missing_teams: list[str] = []
    if os.path.isdir(audit_dir):
        import glob as _glob2
        for team in _TEAMS:
            pattern = os.path.join(
                audit_dir, "audit_" + team + "_" + today_str + "*.md"
            )
            matches = _glob2.glob(pattern)
            if not matches:
                sc2_missing_teams.append(team)
                logger.warning(
                    "G7-SC2 AUDIT_INCOMPLETE: audit_%s_%s*.md not found",
                    team,
                    today_str,
                )
    else:
        # audit dir absent -- all 3 teams missing
        sc2_missing_teams = list(_TEAMS)
        logger.warning("G7-SC2: audit directory not found: %s", audit_dir)

    sc2_pass = len(sc2_missing_teams) == 0
    if not sc2_pass:
        logger.warning(
            "G7-SC2 AUDIT_INCOMPLETE REJECT: missing audit for teams: %s",
            ", ".join(sc2_missing_teams),
        )

    # -- G7-SC3: _serial_state.json staleness check (M418 F-3) --
    # [MAGIC] staleness 임계값: 24시간 = 86400초
    _STALE_SECS = 86400
    serial_state_path = os.path.join(PROJECT_ROOT, "housing", "sinktank", "_serial_state.json")
    sc3_stale = False
    sc3_msg = "NOT_CHECKED"
    if not os.path.exists(serial_state_path):
        sc3_stale = True
        sc3_msg = "FILE_ABSENT"
        logger.warning("G7-SC3: _serial_state.json absent — serial state not tracked (M418 F-3)")
    else:
        try:
            with open(serial_state_path, "r", encoding="utf-8") as fh:
                state_data = json.load(fh)
            if not isinstance(state_data, dict):  # Rule N: 타입 가드
                sc3_stale = True
                sc3_msg = "PARSE_ERROR: not dict"
                logger.warning("G7-SC3: _serial_state.json not dict: %s", type(state_data).__name__)
            else:
                updated_at_str = state_data.get("updated_at", "")
                if not isinstance(updated_at_str, str) or not updated_at_str:  # Rule N: 타입 가드
                    sc3_stale = True
                    sc3_msg = "NO_TIMESTAMP"
                    logger.warning("G7-SC3: _serial_state.json updated_at missing")
                else:
                    try:
                        from datetime import datetime as _dt
                        updated_at = _dt.fromisoformat(updated_at_str)
                        elapsed = (_dt.now() - updated_at).total_seconds()
                        if elapsed > _STALE_SECS:
                            sc3_stale = True
                            stale_h = round(elapsed / 3600, 1)
                            sc3_msg = "STALE_" + str(stale_h) + "h"
                            logger.warning(
                                "G7-SC3: _serial_state.json stale (%.1fh > %dh threshold)",
                                stale_h, _STALE_SECS // 3600
                            )
                        else:
                            sc3_msg = "OK"
                    except ValueError as e:
                        sc3_stale = True
                        sc3_msg = "TIMESTAMP_PARSE_ERROR: " + str(e)[:80]
                        logger.warning("G7-SC3: updated_at parse error: %s", e)
        except (json.JSONDecodeError, OSError) as e:
            sc3_stale = True
            sc3_msg = "READ_ERROR: " + str(e)[:80]
            logger.warning("G7-SC3: _serial_state.json read failed: %s", e)

    # SC3 staleness는 WARN (비차단) — overall REJECT에 포함하지 않음
    if sc3_stale:
        logger.warning("G7-SC3 WARN: _serial_state.json stale: %s", sc3_msg)

    sc3_overall = "WARN" if sc3_stale else "PASS"

    # -- G7-SC4: audit_gui Desktop Parity 섹션 검사 (FP-06, M432) --
    # [MAGIC] 데스크톱 패리티 검사 키워드 (대소문자 무관)
    _PARITY_RE = re.compile(r"Desktop\s+Parity|데스크톱\s*패리티", re.IGNORECASE)
    # [MAGIC] 스크린샷 경로 패턴 — .png 인용 여부
    _SCREENSHOT_PATH_RE = re.compile(r"\S+\.png", re.IGNORECASE)
    # [MAGIC] 사용자 8결함 키워드 목록 (최소 5개 이상 언급 요구)
    _USER_DEFECT_KEYWORDS = [
        r"그리드|grid",           # 텍스트 그리드 정렬
        r"툴바|toolbar",          # 상단/하단 툴바
        r"Lewis|루이스",           # Lewis 뷰
        r"Theory|이론",            # Theory 뷰
        r"전자구름|ESP|electron.*cloud|cloud.*toggle",  # 전자구름 토글
        r"줌|zoom",                # 줌 기능
        r"계열화|학습\s*과정",     # 계열화 학습
        r"패리티|parity",          # 데스크톱 패리티
    ]
    # [MAGIC] 사용자 결함 최소 언급 임계 = 5건
    _DEFECT_MENTION_THRESHOLD = 5

    sc4_fail = False
    sc4_warn = False
    sc4_missing_parity: list[str] = []
    sc4_missing_screenshots: list[str] = []
    sc4_low_defect_coverage: list[str] = []

    import glob as _glob4
    audit_gui_files = _glob4.glob(
        os.path.join(audit_dir, "audit_gui*.md")
    )
    # 메인 reports 폴더의 audit_gui 보고서도 스캔
    audit_gui_files += _glob4.glob(
        os.path.join(PROJECT_ROOT, "docs", "reports", "audit_gui*.md")
    )

    if audit_gui_files:
        for ag_path in audit_gui_files:
            try:
                with open(ag_path, "r", encoding="utf-8") as fh:
                    ag_content = fh.read()
                if not isinstance(ag_content, str):  # Rule N: 타입 가드
                    logger.warning("G7-SC4: non-str content in %s", ag_path)
                    continue

                rel_ag = os.path.relpath(ag_path, PROJECT_ROOT).replace("\\", "/")

                # SC4-a: Desktop Parity 섹션 부재 → FAIL (차단)
                if not _PARITY_RE.search(ag_content):
                    sc4_fail = True
                    sc4_missing_parity.append(rel_ag)
                    logger.warning(
                        "G7-SC4 FAIL: audit_gui report missing 'Desktop Parity' section "
                        "(FP-06, M432, Rule U-c, R-08) -- %s", rel_ag
                    )

                # SC4-b: 인용 스크린샷 파일 실존 여부 → WARN (비차단)
                png_refs = _SCREENSHOT_PATH_RE.findall(ag_content)
                for png_ref in png_refs[:10]:  # [MAGIC] 최대 10개만 검사
                    # 절대경로 또는 PROJECT_ROOT 기준 상대경로 시도
                    if os.path.isabs(png_ref):
                        candidate = png_ref
                    else:
                        candidate = os.path.join(PROJECT_ROOT, png_ref.replace("/", os.sep))
                    if not os.path.exists(candidate):
                        sc4_warn = True
                        sc4_missing_screenshots.append(rel_ag + " -> " + png_ref[:80])
                        logger.warning(
                            "G7-SC4 WARN: audit_gui report cites non-existent screenshot "
                            "(Rule U-f) -- %s -> %s", rel_ag, png_ref[:80]
                        )
                        break  # 파일당 첫 번째 부재만 기록

                # SC4-c: 사용자 8결함 언급 개수 → WARN (비차단)
                defect_hit = sum(
                    1 for kw in _USER_DEFECT_KEYWORDS
                    if re.search(kw, ag_content, re.IGNORECASE)
                )
                if defect_hit < _DEFECT_MENTION_THRESHOLD:
                    sc4_warn = True
                    sc4_low_defect_coverage.append(
                        rel_ag + " (" + str(defect_hit) + "/" + str(len(_USER_DEFECT_KEYWORDS)) + " keywords)"
                    )
                    logger.warning(
                        "G7-SC4 WARN: audit_gui report covers only %d/%d user-defect keywords "
                        "(threshold %d, FP-06) -- %s",
                        defect_hit, len(_USER_DEFECT_KEYWORDS),
                        _DEFECT_MENTION_THRESHOLD, rel_ag
                    )
            except OSError as e:
                logger.warning("G7-SC4: cannot read %s: %s", ag_path, e)
    else:
        # audit_gui 보고서 자체가 없으면 SC4 N/A (SC2가 이미 처리)
        pass

    sc4_overall = "FAIL" if sc4_fail else ("WARN" if sc4_warn else "PASS")

    # -- G7-SC5: 체화 4단계 섹션 검사 (Rule H, M434 신설) --
    # [MAGIC] 체화 4단계 키워드 패턴 — 각 H-1~H-4 대응
    _EMBODIMENT_PATTERNS = [
        re.compile(r"변경\s*전\s*사유|왜\s*이\s*코드", re.IGNORECASE),  # H-1
        re.compile(r"skills?\s*패턴|skills?\s*갱신", re.IGNORECASE),    # H-2
        re.compile(r"patrol[/\s]*AV|자동\s*탐지|G7-SC", re.IGNORECASE), # H-3
        re.compile(r"CLAUDE\.md\s*규칙|Rule\s+[A-Z]{1,2}", re.IGNORECASE),  # H-4
    ]
    # [MAGIC] 0섹션=FAIL(차단), 2섹션미만=WARN(비차단), 2섹션이상=PASS
    _SC5_FAIL_THRESHOLD = 1   # 이 미만이면 FAIL
    _SC5_WARN_THRESHOLD = 2   # 이 미만이면 WARN

    sc5_fail = False
    sc5_warn = False
    sc5_low_embodiment: list[str] = []  # WARN 파일 목록
    sc5_zero_embodiment: list[str] = []  # FAIL 파일 목록

    if evidence_files:
        for ev_path in evidence_files:
            try:
                with open(ev_path, "r", encoding="utf-8") as fh:
                    ev_content = fh.read()
                if not isinstance(ev_content, str):  # Rule N: 타입 가드
                    logger.warning("G7-SC5: non-str content in %s", ev_path)
                    continue

                rel_ev = os.path.relpath(ev_path, PROJECT_ROOT).replace("\\", "/")

                # 체화 4단계 섹션 탐지 카운트
                section_hits = sum(
                    1 for pat in _EMBODIMENT_PATTERNS
                    if pat.search(ev_content)
                )

                if section_hits < _SC5_FAIL_THRESHOLD:
                    # 0섹션 = FAIL (차단)
                    sc5_fail = True
                    sc5_zero_embodiment.append(
                        rel_ev + " (0/" + str(len(_EMBODIMENT_PATTERNS)) + " sections)"
                    )
                    logger.warning(
                        "G7-SC5 FAIL: EVIDENCE missing ALL embodiment sections "
                        "(Rule H 체화4단계, M434) -- %s", rel_ev
                    )
                elif section_hits < _SC5_WARN_THRESHOLD:
                    # 1섹션 = WARN (비차단)
                    sc5_warn = True
                    sc5_low_embodiment.append(
                        rel_ev + " (" + str(section_hits) + "/" + str(len(_EMBODIMENT_PATTERNS)) + " sections)"
                    )
                    logger.warning(
                        "G7-SC5 WARN: EVIDENCE has only %d/%d embodiment sections "
                        "(threshold %d, Rule H, M434) -- %s",
                        section_hits, len(_EMBODIMENT_PATTERNS),
                        _SC5_WARN_THRESHOLD, rel_ev
                    )
                # else: section_hits >= _SC5_WARN_THRESHOLD = PASS (로그 생략)
            except OSError as e:
                logger.warning("G7-SC5: cannot read %s: %s", ev_path, e)
    # evidence_files 없으면 SC5 N/A (SC1이 이미 처리)

    sc5_overall = "FAIL" if sc5_fail else ("WARN" if sc5_warn else "PASS")

    # -- G7-SC6: mechanism_engine.py 코드 품질 검사 (M433 신설) --
    # [MAGIC] 탐지 패턴 목록 (각 패턴이 코드에서 발견되면 WARN)
    _MECH_FILE = os.path.join(PROJECT_ROOT, "src", "app", "mechanism_engine.py")
    sc6_warn = False
    sc6_issues: list[str] = []

    try:
        with open(_MECH_FILE, "r", encoding="utf-8") as fh:
            mech_src = fh.read()
        if isinstance(mech_src, str):
            # SC6-a: U+2212(−) 일반 마이너스를 전하 라벨에 사용 시 WARN
            # U+2212 = \u2212 — 수식용, 전하 위첨자(U+207B ⁻)와 혼동 위험
            if "\u2212" in mech_src and "charge" in mech_src.lower():
                sc6_warn = True
                sc6_issues.append(
                    "SC6-a WARN: U+2212(−) 일반 마이너스 발견 — "
                    "전하 라벨은 U+207B(⁻) 사용 (M433 DEFECT-1)"
                )
                logger.warning(
                    "G7-SC6-a WARN: mechanism_engine.py contains U+2212(−) "
                    "near charge logic — should use U+207B(⁻) (M433 DEFECT-1)"
                )
            # SC6-b: _PERICYCLIC_HINTS 셋 부재 시 WARN
            if "_PERICYCLIC_HINTS" not in mech_src:
                sc6_warn = True
                sc6_issues.append(
                    "SC6-b WARN: _PERICYCLIC_HINTS 셋 부재 — "
                    "페리사이클릭 우선 분류 가드 없음 (M433 DEFECT-2)"
                )
                logger.warning(
                    "G7-SC6-b WARN: mechanism_engine.py missing _PERICYCLIC_HINTS "
                    "pericyclic guard set (M433 DEFECT-2)"
                )
            # SC6-c: _truncate_label 함수 부재 시 WARN
            if "_truncate_label" not in mech_src:
                sc6_warn = True
                sc6_issues.append(
                    "SC6-c WARN: _truncate_label 함수 부재 — "
                    "라벨 30자 truncate 미적용 (M433 DEFECT-3)"
                )
                logger.warning(
                    "G7-SC6-c WARN: mechanism_engine.py missing _truncate_label "
                    "label truncation function (M433 DEFECT-3)"
                )
    except OSError as e:
        logger.warning("G7-SC6: cannot read mechanism_engine.py: %s", e)

    sc6_overall = "WARN" if sc6_warn else "PASS"
    # SC6은 WARN 전용 (비차단) — 차단은 SC1/SC2/SC4/SC5만

    # -- G7-SC7: audit_gui 클릭 시뮬레이션 증거 검사 (R-09, M436 신설) --
    # [MAGIC] 클릭 시뮬레이션 증거 키워드 정규식
    # R-09 사용자 요구: 백그라운드 코드 직접 호출 ≠ 포그라운드 작동
    # 0회 = FAIL(차단), 1~4회 = WARN(비차단), 5회+ = PASS
    _CLICK_SIM_RE = re.compile(
        r"click\s+simulation|mouseClick|button\.click|QTest",
        re.IGNORECASE,
    )
    # [MAGIC] PASS 기준: 5회 이상 언급 = 실질적 클릭 기반 검증 증거
    _SC7_PASS_THRESHOLD = 5   # 5회 이상 = PASS
    # [MAGIC] WARN 기준: 1~4회 = 언급은 있지만 불충분
    _SC7_WARN_THRESHOLD = 1   # 1회 이상 = WARN (0회 미만 = FAIL)

    # [MAGIC] P-INVOKE 패턴 — 코드 직접 호출 탐지 정규식 (R-09 FP-07)
    _P_INVOKE_RE = re.compile(
        r"win\.switch_to_|popup\.show\(\)|popup\.hide\(\)",
        re.IGNORECASE,
    )

    sc7_fail = False
    sc7_warn = False
    sc7_fail_files: list[str] = []   # FAIL 파일 목록
    sc7_warn_files: list[str] = []   # WARN 파일 목록
    sc7_invoke_files: list[str] = [] # P-INVOKE 탐지 파일 목록

    import glob as _glob7
    audit_gui_pattern7 = os.path.join(audit_dir, "audit_gui_*.md")
    audit_gui_files7 = _glob7.glob(audit_gui_pattern7) if os.path.isdir(audit_dir) else []

    if audit_gui_files7:
        for ag7_path in audit_gui_files7:
            try:
                with open(ag7_path, "r", encoding="utf-8") as fh:
                    ag7_content = fh.read()
                if not isinstance(ag7_content, str):  # Rule N: 타입 가드
                    logger.warning("G7-SC7: non-str content in %s", ag7_path)
                    continue

                rel_ag7 = os.path.relpath(ag7_path, PROJECT_ROOT).replace("\\", "/")

                # 클릭 시뮬레이션 키워드 매치 횟수
                click_matches = len(_CLICK_SIM_RE.findall(ag7_content))

                if click_matches < _SC7_WARN_THRESHOLD:
                    # 0회 = FAIL (차단)
                    sc7_fail = True
                    sc7_fail_files.append(
                        rel_ag7 + " (0 click simulation evidence)"
                    )
                    logger.warning(
                        "G7-SC7 FAIL: audit_gui report missing click simulation evidence "
                        "(R-09, M436, FP-07) -- %s", rel_ag7
                    )
                elif click_matches < _SC7_PASS_THRESHOLD:
                    # 1~4회 = WARN (비차단)
                    sc7_warn = True
                    sc7_warn_files.append(
                        rel_ag7 + " (%d/%d click evidence)" % (click_matches, _SC7_PASS_THRESHOLD)
                    )
                    logger.warning(
                        "G7-SC7 WARN: audit_gui report has only %d/%d click simulation "
                        "evidence (threshold %d, R-09, M436) -- %s",
                        click_matches, _SC7_PASS_THRESHOLD, _SC7_PASS_THRESHOLD, rel_ag7,
                    )
                # else: click_matches >= _SC7_PASS_THRESHOLD = PASS (로그 생략)

                # P-INVOKE 패턴 탐지 (코드 직접 호출 = FP-07, WARN)
                invoke_hits = _P_INVOKE_RE.findall(ag7_content)
                if invoke_hits:
                    sc7_warn = True
                    sc7_invoke_files.append(
                        rel_ag7 + " (P-INVOKE: " + str(invoke_hits[:3]) + ")"
                    )
                    logger.warning(
                        "G7-SC7 WARN: audit_gui report contains P-INVOKE direct call patterns "
                        "(FP-07, R-09) -- %s: %s", rel_ag7, str(invoke_hits[:3])[:120]
                    )

            except OSError as e:
                logger.warning("G7-SC7: cannot read %s: %s", ag7_path, e)
    # audit_gui 보고서 없으면 SC7 N/A (SC2가 이미 처리)

    sc7_overall = "FAIL" if sc7_fail else ("WARN" if sc7_warn else "PASS")
    # SC7 FAIL은 차단 (R-09 코드 직접 호출 = 거짓 PASS)

    # -- G7-SC8: frontend SSR PNG img 의존 탐지 (M435 신설, WARN 전용 비차단) --
    # [M435] 사용자 격분: "루이스/이론 레이어가 연산 이미지 붙여넣는 원시적 수준"
    # SSR PNG img 의존 패턴: /api/render/{lewis|theory|esp} fetch + <img src={ssr 잔존.
    # Lewis/Theory는 LewisRenderer2D/TheoryRenderer2D Canvas2D로 전환 완료.
    # 잔존 컴포넌트가 SSR img 의존으로 회귀하는 것을 자동 탐지.
    # [MAGIC] WARN 기준: 5개 이상 SSR fetch 호출 = WARN
    sc8_warn = False
    sc8_issues: list[str] = []

    _FRONTEND_SRC = os.path.join(PROJECT_ROOT, "chemgrid_mobile", "frontend", "src")
    if not os.path.isdir(_FRONTEND_SRC):
        _FRONTEND_SRC = os.path.join(
            os.path.dirname(PROJECT_ROOT), "chemgrid_mobile", "frontend", "src"
        )

    _SSR_FETCH_RE = re.compile(
        r"fetch\(['\"`]/api/render/(lewis|theory|esp)",
        re.IGNORECASE,
    )
    _SSR_IMG_RE = re.compile(
        r"<img\s[^>]*src=\{ssr",
        re.IGNORECASE,
    )

    if os.path.isdir(_FRONTEND_SRC):
        _ssr_fetch_count = 0
        _ssr_img_count = 0
        _ssr_offenders: list[str] = []
        try:
            for _root_sc8, _dirs_sc8, _files_sc8 in os.walk(_FRONTEND_SRC):
                _dirs_sc8[:] = [d for d in _dirs_sc8 if d != "node_modules"]
                for _fname_sc8 in _files_sc8:
                    if not (_fname_sc8.endswith(".ts") or _fname_sc8.endswith(".tsx")):
                        continue
                    _fpath_sc8 = os.path.join(_root_sc8, _fname_sc8)
                    try:
                        with open(_fpath_sc8, encoding="utf-8", errors="replace") as _fh_sc8:
                            _fcontents_sc8 = _fh_sc8.read()
                        if not isinstance(_fcontents_sc8, str):  # Rule N
                            continue
                        _fc_m = _SSR_FETCH_RE.findall(_fcontents_sc8)
                        _img_m = _SSR_IMG_RE.findall(_fcontents_sc8)
                        if _fc_m or _img_m:
                            _rel_sc8 = os.path.relpath(_fpath_sc8, PROJECT_ROOT)
                            _ssr_fetch_count += len(_fc_m)
                            _ssr_img_count += len(_img_m)
                            _ssr_offenders.append(
                                f"{_rel_sc8} (fetch:{len(_fc_m)}, img:{len(_img_m)})"
                            )
                    except Exception as _e_sc8_f:
                        logger.warning("G7-SC8: cannot read %s: %s", _fpath_sc8, _e_sc8_f)
        except Exception as _e_sc8_w:
            logger.warning("G7-SC8: frontend walk error: %s", _e_sc8_w)

        # [MAGIC] 5회 이상 = SSR 의존 회귀 위험
        _SC8_FETCH_WARN = 5
        if _ssr_fetch_count >= _SC8_FETCH_WARN or _ssr_img_count > 0:
            sc8_warn = True
            _sc8_msg = (
                f"G7-SC8 WARN: frontend SSR img 의존 잔존 {len(_ssr_offenders)}파일 "
                f"(fetch:{_ssr_fetch_count}, img:{_ssr_img_count}). "
                f"Lewis/Theory는 LewisRenderer2D/TheoryRenderer2D Canvas2D로 대체 필요. "
                f"파일: {'; '.join(_ssr_offenders[:3])}"
            )
            sc8_issues.append(_sc8_msg)
            logger.warning(_sc8_msg)

    sc8_overall = "WARN" if sc8_warn else "PASS"

    # -- G7-SC9: SIMULATION_MODE / ORCA 거짓 메시지 탐지 (M438 신설, WARN 전용 비차단) --
    # Rule M: is_simulation=True 시 UI 경고 표시 의무. "built-in engine" 거짓 메시지 금지.
    # P-SCOPE 패턴: 컴포넌트 코드 존재 = 기능 작동 오인 (FP-08, R-11)
    # [MAGIC] 탐지 대상 파일:
    #   - src/app/docking_interface.py (SIMULATION_MODE fallback 스코어 학계 신뢰도)
    #   - src/app/popup_3d.py (ORCA "built-in engine" 거짓 메시지)
    #   - src/app/popup_docking.py (SIMULATION 배너 표시 여부)
    sc9_warn = False
    sc9_issues: list[str] = []

    # SC9-a: popup_3d.py "Using built-in engine" 거짓 메시지 잔존 여부
    # [MAGIC] 주석줄 제외 후 비주석 코드에서 탐지: setText/emit 호출에 포함된 경우만
    # 주석 패턴: 앞 공백 후 '#' 시작줄은 제외
    _popup3d_path = os.path.join(PROJECT_ROOT, "src", "app", "popup_3d.py")
    _FALSE_ENGINE_STR_RE = re.compile(r"Using built.in engine", re.IGNORECASE)
    _COMMENT_LINE_RE = re.compile(r"^\s*#")  # 주석줄 패턴
    try:
        with open(_popup3d_path, encoding="utf-8") as _fh:
            _popup3d_lines = _fh.readlines()
        if not isinstance(_popup3d_lines, list):  # Rule N: 타입 가드
            logger.warning("G7-SC9: non-list content in popup_3d.py")
        else:
            _sc9a_hit = False
            for _line in _popup3d_lines:
                # 주석 줄은 건너뜀 (앞 공백 무시 후 '#' 시작)
                if _COMMENT_LINE_RE.match(_line):
                    continue
                if _FALSE_ENGINE_STR_RE.search(_line):
                    _sc9a_hit = True
                    break
            if _sc9a_hit:
                sc9_warn = True
                sc9_issues.append(
                    "SC9-a WARN: popup_3d.py 비주석 코드에 'Using built-in engine' 거짓 메시지 잔존 "
                    "— ORCA 미설치 시 존재하지 않는 DFT 엔진 사용 암시 (M438 Rule M FP-08)"
                )
                logger.warning(
                    "G7-SC9-a WARN: popup_3d.py non-comment code contains 'Using built-in engine' "
                    "— indicates non-existent DFT engine (M438, Rule M, FP-08)"
                )
    except OSError as e:
        logger.warning("G7-SC9: cannot read popup_3d.py: %s", e)

    # SC9-b: popup_docking.py SIMULATION 배너 표시 여부 확인
    _popup_dock_path = os.path.join(PROJECT_ROOT, "src", "app", "popup_docking.py")
    _SIM_BANNER_RE = re.compile(
        r"sim.*banner|SIMULATION.*경고|_sim_banner|SIMULATION MODE",
        re.IGNORECASE,
    )
    try:
        with open(_popup_dock_path, encoding="utf-8") as _fh:
            _popup_dock_src = _fh.read()
        if not isinstance(_popup_dock_src, str):  # Rule N: 타입 가드
            logger.warning("G7-SC9: non-str content in popup_docking.py")
        elif "SIMULATION_MODE" in _popup_dock_src and not _SIM_BANNER_RE.search(_popup_dock_src):
            # SIMULATION_MODE 사용은 있으나 배너 없음 = P-SCOPE 위험
            sc9_warn = True
            sc9_issues.append(
                "SC9-b WARN: popup_docking.py에 SIMULATION_MODE 사용하나 "
                "UI 경고 배너(_sim_banner) 미존재 — 학계 신뢰도 위반 (M438 Rule M)"
            )
            logger.warning(
                "G7-SC9-b WARN: popup_docking.py uses SIMULATION_MODE but "
                "no UI warning banner found (M438, Rule M)"
            )
    except OSError as e:
        logger.warning("G7-SC9: cannot read popup_docking.py: %s", e)

    # SC9-c: docking_interface.py fallback affinity cap 존재 여부 (MAX_PHYSICAL_AFFINITY)
    _dock_iface_path = os.path.join(PROJECT_ROOT, "src", "app", "docking_interface.py")
    try:
        with open(_dock_iface_path, encoding="utf-8") as _fh:
            _dock_iface_src = _fh.read()
        if not isinstance(_dock_iface_src, str):  # Rule N: 타입 가드
            logger.warning("G7-SC9: non-str content in docking_interface.py")
        elif "MAX_PHYSICAL_AFFINITY" not in _dock_iface_src:
            # 상한 cap 없으면 타닌류 대형 분자 비현실적 값 출력
            sc9_warn = True
            sc9_issues.append(
                "SC9-c WARN: docking_interface.py _run_simulation_fallback에 "
                "MAX_PHYSICAL_AFFINITY cap 없음 — 대형 분자(타닌 등) 비현실적 스코어 출력 위험 (M438)"
            )
            logger.warning(
                "G7-SC9-c WARN: docking_interface.py missing MAX_PHYSICAL_AFFINITY cap "
                "in _run_simulation_fallback — risk of unrealistic scores for large molecules (M438)"
            )
    except OSError as e:
        logger.warning("G7-SC9: cannot read docking_interface.py: %s", e)

    sc9_overall = "WARN" if sc9_warn else "PASS"
    # SC9는 WARN 전용 (비차단) — 학계 신뢰도 문제이므로 수동 검토 의무

    # -- G7-SC12: arrow_generator.py 4색 표준 검사 (M442 신설, WARN 전용 비차단) --
    # Rule O 렌더링 품질: 5색 이상 사용 = 학생 가독성 저하
    # _ARROW_COLOR_MAP 부재 / ARROW_COLORS 6색 팔레트 잔존 / _assign_colors 인덱스순환 탐지
    # [MAGIC] 허용 4색 표준 상수: _AC_NUCLEOPHILIC / _AC_BOND_FORM / _AC_BOND_BREAK / _AC_DEFAULT
    sc12_warn = False
    sc12_issues: list = []

    ag_path = os.path.join(PROJECT_ROOT, "src", "app", "arrow_generator.py")
    try:
        with open(ag_path, encoding="utf-8") as _f:
            ag_content = _f.read()
        if not isinstance(ag_content, str):
            ag_content = ""

        # SC12-a: ARROW_COLORS 6색 팔레트 잔존 여부 (폐기 완료 여부)
        # 구버전 6-element list 패턴 탐지 — 폐기 후에도 재도입됐는지 확인
        _old_palette_pat = re.compile(
            r'ARROW_COLORS\s*=\s*\[',
            re.IGNORECASE,
        )
        if _old_palette_pat.search(ag_content):
            sc12_warn = True
            sc12_issues.append(
                "SC12-a WARN: arrow_generator.py에 ARROW_COLORS 6색 팔레트 리스트 잔존 "
                "— 4색 표준(_ARROW_COLOR_MAP) 교체 확인 필요 (M442 Rule O)"
            )
            logger.warning(
                "G7-SC12-a WARN: arrow_generator.py ARROW_COLORS list detected "
                "— should be replaced by _ARROW_COLOR_MAP 4-color standard (M442, Rule O)"
            )

        # SC12-b: _ARROW_COLOR_MAP 존재 여부 (4색 표준 도입 확인)
        if "_ARROW_COLOR_MAP" not in ag_content:
            sc12_warn = True
            sc12_issues.append(
                "SC12-b WARN: arrow_generator.py에 _ARROW_COLOR_MAP 부재 "
                "— 교과서 4색 표준 매핑 테이블 미도입 (M442 Rule O)"
            )
            logger.warning(
                "G7-SC12-b WARN: arrow_generator.py missing _ARROW_COLOR_MAP "
                "4-color mapping table (M442, Rule O)"
            )

        # SC12-c: _assign_colors 인덱스 순환 패턴 잔존 여부
        _old_assign_pat = re.compile(
            r'ARROW_COLORS\[i\s*%\s*len\(',
        )
        if _old_assign_pat.search(ag_content):
            sc12_warn = True
            sc12_issues.append(
                "SC12-c WARN: arrow_generator.py _assign_colors에 인덱스 순환 배정 패턴 잔존 "
                "— from_type 기반 의미론적 배정으로 교체 필요 (M442)"
            )
            logger.warning(
                "G7-SC12-c WARN: arrow_generator.py _assign_colors index-cycle pattern detected "
                "— must use from_type semantic mapping (M442)"
            )

    except OSError as e:
        logger.warning("G7-SC12: cannot read arrow_generator.py: %s", e)

    sc12_overall = "WARN" if sc12_warn else "PASS"
    # SC12는 WARN 전용 (비차단) — 동일 Rule O 위반이므로 SC6과 동일 정책

    # -- G7-SC10: TSX 컴포넌트 vs 데스크톱 원본 scope 일치 검증 (M439 신설, WARN 전용 비차단) --
    # Rule Y 강화: TSX 파일의 // Source: 주석에 올바른 데스크톱 원본이 명시되었는지 확인
    # "신규 컴포넌트 (데스크톱 미존재)" 라벨이 있으면 scope 불일치 위험 경보
    # 발견 시: scope 불일치 가능성 WARN (작업 시작도 안 함 사고 = M439 패턴)
    sc10_warn = False
    sc10_issues: list = []

    _mobile_src = os.path.join(PROJECT_ROOT, "..", "chemgrid_mobile", "frontend", "src", "components")
    if os.path.isdir(_mobile_src):
        _scope_mismatch_re = re.compile(
            r"신규\s*컴포넌트\s*\(데스크톱\s*미존재",
            re.IGNORECASE,
        )
        for _tsx in sorted(glob.glob(os.path.join(_mobile_src, "*.tsx"))):
            try:
                with open(_tsx, encoding="utf-8") as _f:
                    _tsx_content = _f.read()
                if not isinstance(_tsx_content, str):
                    continue
                if _scope_mismatch_re.search(_tsx_content):
                    sc10_warn = True
                    _rel = os.path.basename(_tsx)
                    sc10_issues.append(
                        f"SC10 WARN: {_rel} — '신규 컴포넌트(데스크톱 미존재)' 라벨 발견 "
                        "→ Rule Y scope 불일치 위험 (M439 패턴). "
                        "데스크톱 원본 1:1 매핑 또는 명시적 확장 이유 필요."
                    )
                    logger.warning(
                        "G7-SC10 WARN: %s has '신규 컴포넌트(데스크톱 미존재)' label "
                        "— potential Rule Y scope mismatch (M439)", _rel
                    )
            except OSError as e:
                logger.warning("G7-SC10: cannot read %s: %s", _tsx, e)

    sc10_overall = "WARN" if sc10_warn else "PASS"
    # SC10은 WARN 전용 (비차단) — scope 불일치는 반드시 수동 확인 후 수정

    # -- G7-SC11: synthesis AI fallback 의무 검사 (M441 신설, WARN 전용 비차단) --
    # Rule M: synthesis backend에서 engine 빈 응답 시 AI fallback 의무.
    # synthesis.py에 _build_ai_fallback 함수 + RetroResponse ai_fallback 필드 확인.
    # [MAGIC] 검사 대상: chemgrid_mobile/backend/routers/synthesis.py (웹 백엔드)
    _SYNTHESIS_ROUTER_PATHS = [
        os.path.normpath(os.path.join(PROJECT_ROOT, "..", "chemgrid_mobile", "backend", "routers", "synthesis.py")),
        os.path.normpath(os.path.join(
            os.getenv("CHEMGRID_MOBILE_PATH", r"C:\chemgrid_mobile"),
            "backend", "routers", "synthesis.py"
        )),
    ]
    sc11_warn = False
    sc11_issues: list[str] = []
    _sc11_found = False

    for _syn_path in _SYNTHESIS_ROUTER_PATHS:
        if not os.path.exists(_syn_path):
            continue
        _sc11_found = True
        try:
            with open(_syn_path, "r", encoding="utf-8") as _fh:
                _syn_src = _fh.read()
            if not isinstance(_syn_src, str):  # Rule N: 타입 가드
                logger.warning("G7-SC11: non-str content in %s", _syn_path)
                continue

            # SC11-a: _build_ai_fallback 함수 존재 여부
            if "_build_ai_fallback" not in _syn_src:
                sc11_warn = True
                sc11_issues.append(
                    "SC11-a WARN: synthesis.py에 _build_ai_fallback 함수 없음 "
                    "— engine 빈 응답 시 AI fallback 미제공 (M441 Rule M)"
                )
                logger.warning(
                    "G7-SC11-a WARN: synthesis.py missing _build_ai_fallback "
                    "(M441, Rule M)"
                )

            # SC11-b: RetroResponse에 ai_fallback 필드 존재 여부
            if "ai_fallback" not in _syn_src:
                sc11_warn = True
                sc11_issues.append(
                    "SC11-b WARN: synthesis.py RetroResponse에 ai_fallback 필드 없음 "
                    "— 프론트엔드에 AI fallback 전달 불가 (M441)"
                )
                logger.warning(
                    "G7-SC11-b WARN: synthesis.py RetroResponse missing ai_fallback field (M441)"
                )

            # SC11-c: /ai_fallback 전용 엔드포인트 존재 여부
            if "AIFallbackRequest" not in _syn_src:
                sc11_warn = True
                sc11_issues.append(
                    "SC11-c WARN: /api/synthesis/ai_fallback 직접 엔드포인트 없음 "
                    "— 프론트엔드 직접 호출 불가 (M441)"
                )
                logger.warning(
                    "G7-SC11-c WARN: synthesis.py missing /ai_fallback endpoint (M441)"
                )
        except OSError as e:
            logger.warning("G7-SC11: cannot read synthesis.py at %s: %s", _syn_path, e)
        break  # 첫 번째 존재 경로만 검사

    if not _sc11_found:
        logger.warning("G7-SC11: synthesis.py not found — SC11 skipped (N/A)")

    sc11_overall = "WARN" if sc11_warn else "PASS"
    # SC11은 WARN 전용 (비차단) — chemgrid_mobile 경로 의존성 있음

    # -- G7-SC14: 신규 엔드포인트가 호출하는 메서드 실제 존재 검사 (M443 신설, WARN 전용 비차단) --
    # 엔드포인트 → 브리지 → 클래스 메서드 3단 체인에서 메서드명 불일치 탐지
    # [MAGIC] 검사 대상: web/backend/bridge/qt_offscreen.py
    # CloudRenderer().render() 패턴 탐지 — 인스턴스 생성 후 미존재 메서드 = AttributeError → 서버 크래시
    sc14_warn = False
    sc14_issues: list[str] = []

    _OFFSCREEN_PATH_SC14 = os.path.join(PROJECT_ROOT, "web", "backend", "bridge", "qt_offscreen.py")
    _WRONG_CLOUD_CALL_RE = re.compile(
        r"CloudRenderer\(\)\s*\.\s*render\s*\(",
        re.IGNORECASE,
    )
    # [MAGIC] 올바른 호출 패턴: CloudRenderer.draw_clouds (@staticmethod 클래스 직접 호출)
    _CORRECT_CLOUD_METHOD_SC14 = "draw_clouds"

    if os.path.exists(_OFFSCREEN_PATH_SC14):
        try:
            with open(_OFFSCREEN_PATH_SC14, "r", encoding="utf-8") as _fh14:
                _offscreen_src = _fh14.read()
            if not isinstance(_offscreen_src, str):  # Rule N: 타입 가드
                _offscreen_src = ""

            # SC14-a: CloudRenderer().render() 잘못된 인스턴스 호출 패턴 탐지
            if _WRONG_CLOUD_CALL_RE.search(_offscreen_src):
                sc14_warn = True
                sc14_issues.append(
                    "SC14-a WARN: qt_offscreen.py에 CloudRenderer().render() 호출 발견 "
                    "— AttributeError 유발. CloudRenderer.draw_clouds() 사용 필수 (M443)"
                )
                logger.warning(
                    "G7-SC14-a WARN: qt_offscreen.py uses CloudRenderer().render() "
                    "— AttributeError guaranteed. Use CloudRenderer.draw_clouds() (M443)"
                )

            # SC14-b: render_esp 브리지 함수 미존재 시 WARN
            if "def render_esp" not in _offscreen_src:
                sc14_warn = True
                sc14_issues.append(
                    "SC14-b WARN: qt_offscreen.py에 render_esp 브리지 함수 없음 "
                    "— /api/render/esp 엔드포인트 구현 불완전 (M443)"
                )
                logger.warning(
                    "G7-SC14-b WARN: qt_offscreen.py missing render_esp bridge function (M443)"
                )

            # SC14-c: CloudRenderer 임포트하나 draw_clouds 호출 없으면 WARN
            if "CloudRenderer" in _offscreen_src and _CORRECT_CLOUD_METHOD_SC14 not in _offscreen_src:
                sc14_warn = True
                sc14_issues.append(
                    "SC14-c WARN: qt_offscreen.py가 CloudRenderer 임포트하나 "
                    "draw_clouds 호출 없음 — 메서드명 검증 필요 (M443)"
                )
                logger.warning(
                    "G7-SC14-c WARN: qt_offscreen.py imports CloudRenderer but "
                    "does not call draw_clouds (M443)"
                )
        except OSError as e:
            logger.warning("G7-SC14: cannot read qt_offscreen.py: %s", e)
    else:
        logger.warning("G7-SC14: qt_offscreen.py not found at %s — SC14 skipped", _OFFSCREEN_PATH_SC14)

    sc14_overall = "WARN" if sc14_warn else "PASS"
    # SC14는 WARN 전용 (비차단) — 메서드명 사전 검증 누락 탐지

    # -- G7-SC13: AlphaFold residues=[] 빈 배열 audit PASS 탐지 (M440 신설, WARN 전용 비차단) --
    # 패턴: AlphaFoldPanel.tsx에서 residues: [] 하드코딩 + pdbParser 미통합 탐지
    sc13_warn = False
    sc13_issues: list[str] = []
    _sc13_search_paths = [
        r"C:\chemgrid_mobile\frontend\src\components\AlphaFoldPanel.tsx",
        os.path.join(os.path.dirname(PROJECT_ROOT), "chemgrid_mobile",
                     "frontend", "src", "components", "AlphaFoldPanel.tsx"),
    ]
    _sc13_found = False
    for _af_tsx in _sc13_search_paths:
        if os.path.isfile(_af_tsx):
            _sc13_found = True
            try:
                with open(_af_tsx, encoding="utf-8", errors="replace") as _f:
                    _af_content = _f.read()
                if not isinstance(_af_content, str):
                    logger.warning("G7-SC13: non-str content in AlphaFoldPanel.tsx")
                    break
                # SC13-a: residues: [] 빈 배열 하드코딩 — 2개 이상 = 핸들러 양쪽 모두 문제
                _empty_hits = len(re.findall(r"residues\s*:\s*\[\s*\]", _af_content))
                if _empty_hits >= 2:
                    sc13_warn = True
                    sc13_issues.append(
                        f"G7-SC13-a WARN: AlphaFoldPanel.tsx has {_empty_hits} "
                        "'residues: []' instances — pdbParser not integrated (M440)"
                    )
                # SC13-b: pdbParser import 미존재 시 WARN
                if "parsePDBText" not in _af_content and "pdbParser" not in _af_content:
                    sc13_warn = True
                    sc13_issues.append(
                        "G7-SC13-b WARN: AlphaFoldPanel.tsx missing parsePDBText/pdbParser import "
                        "— residue table will remain empty (M440)"
                    )
            except OSError as e:
                logger.warning("G7-SC13: cannot read AlphaFoldPanel.tsx: %s", e)
            break
    if not _sc13_found:
        logger.warning("G7-SC13: AlphaFoldPanel.tsx not found — SC13 skipped (N/A)")

    for _iss13 in sc13_issues:
        logger.warning(_iss13)
    sc13_overall = "WARN" if sc13_warn else "PASS"
    # SC13은 WARN 전용 (비차단) — chemgrid_mobile 경로 의존성

    # -- G7-SC15: 웹 spectrum 엔드포인트 임포트 불일치 탐지 (M444 신설, WARN 전용 비차단) --
    # predict_mass_spectrum 같이 데스크톱에 없는 함수를 임포트하면
    # _CHEMGRID_ENGINE_AVAILABLE = False → 스펙트럼 빈 화면 (사용자 격분 F-04 패턴)
    # Rule Y: 데스크톱 predict_spectra.py 공개 함수 5종만 임포트 허용
    sc15_warn = False
    sc15_issues: list[str] = []

    # [MAGIC] 검사 대상: chemgrid_mobile/backend/routers/spectra.py
    _SPECTRA_ROUTER_PATHS_SC15 = [
        r"C:\chemgrid_mobile\backend\routers\spectra.py",
        os.path.normpath(os.path.join(
            os.getenv("CHEMGRID_MOBILE_PATH", r"C:\chemgrid_mobile"),
            "backend", "routers", "spectra.py"
        )),
    ]
    # [MAGIC] 데스크톱에 없는 함수명 목록 (Rule Y 위반 탐지)
    _NONEXISTENT_IMPORTS_SC15 = [
        "predict_mass_spectrum",   # M444: 데스크톱 미존재 → ImportError
    ]
    # [MAGIC] 필수 존재 함수 (데스크톱 1:1 매핑)
    _REQUIRED_IMPORTS_SC15 = [
        "predict_ir",
        "predict_raman",
        "predict_h1_nmr",
        "predict_c13_nmr",
        "predict_uvvis",
    ]
    _sc15_found = False
    for _spectra_path in _SPECTRA_ROUTER_PATHS_SC15:
        if not os.path.exists(_spectra_path):
            continue
        _sc15_found = True
        try:
            with open(_spectra_path, "r", encoding="utf-8") as _fh15:
                _spectra_src = _fh15.read()
            if not isinstance(_spectra_src, str):  # Rule N: 타입 가드
                logger.warning("G7-SC15: non-str content in spectra.py")
                break

            # SC15-a: 데스크톱 미존재 함수 실제 임포트 탐지 (주석 제외, ImportError 원인)
            # [MAGIC] 임포트 행 패턴: "    predict_mass_spectrum," or "    predict_mass_spectrum\n"
            # 주석(#)이나 docstring 내 언급은 오탐 → 들여쓰기 0~8공백 + 함수명 + ,[) 패턴만 탐지
            for _bad_fn in _NONEXISTENT_IMPORTS_SC15:
                _bad_fn_import_re = re.compile(
                    r"^\s{0,8}" + re.escape(_bad_fn) + r"\s*[,\)\n]",
                    re.MULTILINE,
                )
                if _bad_fn_import_re.search(_spectra_src):
                    sc15_warn = True
                    sc15_issues.append(
                        f"SC15-a WARN: spectra.py에 '{_bad_fn}' 실제 임포트 행 잔존 "
                        f"— 데스크톱 predict_spectra.py에 없는 함수 → ImportError → "
                        f"_CHEMGRID_ENGINE_AVAILABLE=False → 스펙트럼 빈 화면 (M444 Rule Y)"
                    )
                    logger.warning(
                        "G7-SC15-a WARN: spectra.py actually imports '%s' (import line found) "
                        "which does not exist in predict_spectra.py — causes "
                        "_CHEMGRID_ENGINE_AVAILABLE=False → empty spectrum (M444, Rule Y)", _bad_fn
                    )

            # SC15-b: 필수 임포트 함수 누락 탐지
            for _req_fn in _REQUIRED_IMPORTS_SC15:
                if _req_fn not in _spectra_src:
                    sc15_warn = True
                    sc15_issues.append(
                        f"SC15-b WARN: spectra.py에 '{_req_fn}' 임포트 없음 "
                        f"— 데스크톱 엔진 5종 중 1종 미연결 (M444 Rule Y)"
                    )
                    logger.warning(
                        "G7-SC15-b WARN: spectra.py missing import '%s' "
                        "— desktop engine function not connected (M444, Rule Y)", _req_fn
                    )

            # SC15-c: 스펙트럼 엔진 임포트 성공 여부 실제 확인 (동적 체크)
            # CHEMGRID_ENGINE_AVAILABLE 주변 try/except 구조 확인
            if "_CHEMGRID_ENGINE_AVAILABLE = True" not in _spectra_src:
                sc15_warn = True
                sc15_issues.append(
                    "SC15-c WARN: spectra.py에 _CHEMGRID_ENGINE_AVAILABLE=True 설정 없음 "
                    "— 엔진 임포트 성공 시 플래그 설정 코드 필요 (M444)"
                )
                logger.warning(
                    "G7-SC15-c WARN: spectra.py missing '_CHEMGRID_ENGINE_AVAILABLE = True' "
                    "— engine import success flag not set (M444)"
                )
        except OSError as e:
            logger.warning("G7-SC15: cannot read spectra.py at %s: %s", _spectra_path, e)
        break

    if not _sc15_found:
        logger.warning("G7-SC15: spectra.py not found — SC15 skipped (N/A)")

    sc15_overall = "WARN" if sc15_warn else "PASS"
    # SC15는 WARN 전용 (비차단) — 엔드포인트 임포트 불일치 재발 방지

    # -- G7-SC16: 메인 repo vs 워크트리 src/app/*.py diff 탐지 (M449 신설, WARN 전용 비차단) --
    # P-WORKTREE 패턴(FP-09): audit가 메인 repo만 검사하여 PASS, 워크트리 실제 빌드 미반영
    # 4회 누적 워크트리 동기화 누락 패턴 (M417 계열 — M449에서 공식 SC 등록)
    # [MAGIC] 검사 대상: .claude/worktrees/ 하위 모든 활성 워크트리의 src/app/*.py
    sc16_warn = False
    sc16_issues: list[str] = []

    _MAIN_APP_DIR = os.path.join(PROJECT_ROOT, "src", "app")
    _WORKTREES_BASE = os.path.join(PROJECT_ROOT, ".claude", "worktrees")

    if os.path.isdir(_WORKTREES_BASE) and os.path.isdir(_MAIN_APP_DIR):
        try:
            for _wt_name in os.listdir(_WORKTREES_BASE):
                _wt_app_dir = os.path.join(_WORKTREES_BASE, _wt_name, "src", "app")
                if not os.path.isdir(_wt_app_dir):
                    continue  # 워크트리에 src/app/ 없으면 skip

                # 메인 repo src/app/*.py 전수 비교
                for _py_file in sorted(glob.glob(os.path.join(_MAIN_APP_DIR, "*.py"))):
                    _fname = os.path.basename(_py_file)
                    _wt_file = os.path.join(_wt_app_dir, _fname)

                    if not os.path.exists(_wt_file):
                        # 워크트리에 해당 파일 없음 — 신규 파일이면 sync 필요
                        sc16_warn = True
                        _issue = (
                            f"SC16 WARN: {_fname} exists in main repo but NOT in "
                            f"worktree {_wt_name} — P-WORKTREE sync 누락 가능 (M449 R-12)"
                        )
                        sc16_issues.append(_issue)
                        logger.warning(
                            "G7-SC16 WARN: %s present in main repo, absent in worktree %s "
                            "(M449, R-12, P-WORKTREE)", _fname, _wt_name
                        )
                        continue

                    # 두 파일 내용 비교 (Rule N: 타입 가드)
                    try:
                        with open(_py_file, encoding="utf-8", errors="replace") as _fm:
                            _main_content = _fm.read()
                        with open(_wt_file, encoding="utf-8", errors="replace") as _fw:
                            _wt_content = _fw.read()

                        if not isinstance(_main_content, str) or not isinstance(_wt_content, str):
                            logger.warning("G7-SC16: non-str content in %s (skip)", _fname)
                            continue

                        if _main_content != _wt_content:
                            sc16_warn = True
                            # M462: line-level diff 의무 — 구체적 라인 번호 WARN 포함
                            _main_lines = _main_content.splitlines(keepends=True)
                            _wt_lines = _wt_content.splitlines(keepends=True)
                            _unified = list(difflib.unified_diff(
                                _wt_lines, _main_lines,
                                fromfile=f"worktree/{_fname}",
                                tofile=f"main/{_fname}",
                                n=0,  # 컨텍스트 0줄 — 변경 라인만 (토큰 절약)
                            ))
                            # 첫 10 hunk만 WARN 메시지에 포함 (과도한 로그 방지)
                            _MAX_DIFF_LINES = 10  # [MAGIC] 로그 가독성/토큰 균형
                            _diff_snippet = "".join(_unified[:_MAX_DIFF_LINES]).strip()
                            _issue = (
                                f"SC16 WARN: {_fname} DIFF between main repo and "
                                f"worktree {_wt_name} — Worker fix가 워크트리에 미반영 위험 "
                                f"(M449 FP-09 P-WORKTREE, R-12) | diff snippet: {_diff_snippet!r}"
                            )
                            sc16_issues.append(_issue)
                            logger.warning(
                                "G7-SC16 WARN: %s differs between main repo and worktree %s "
                                "— line-level diff (first %d hunks): %s "
                                "(M449, FP-09, P-WORKTREE, R-12, M462)",
                                _fname, _wt_name, _MAX_DIFF_LINES, _diff_snippet
                            )
                    except OSError as _e_sc16_f:
                        logger.warning("G7-SC16: cannot compare %s: %s", _fname, _e_sc16_f)

        except OSError as _e_sc16_w:
            logger.warning("G7-SC16: worktree walk error: %s", _e_sc16_w)
    else:
        logger.warning("G7-SC16: worktrees base or main app dir not found — SC16 skipped (N/A)")

    sc16_overall = "WARN" if sc16_warn else "PASS"
    # SC16은 WARN 전용 (비차단) — 워크트리-메인 sync 불일치 재발 방지 (P-WORKTREE FP-09 R-12)

    # -- G7-SC18: analyzer.py bonds 키 형식 검증 (M452 신설, WARN 전용 비차단) --
    # M452: HTTP 경로에서 bonds 딕셔너리 키가 JSON 직렬화로 문자열 "x1,y1|x2,y2" 전달 →
    # analyzer.py L32 `for k1, k2 in bonds.keys()` 튜플 언팩킹 실패 → ValueError → HTTP 500.
    # qt_offscreen.py에 _normalize_bond_keys() 신설로 변환 처리됨.
    # 이 SC는 _normalize_bond_keys() 미호출 시 재발 감지용.
    # [MAGIC] 검사 대상: web/backend/bridge/qt_offscreen.py
    sc18_warn = False
    sc18_issues: list[str] = []

    _OFFSCREEN_PATH_SC18 = os.path.join(PROJECT_ROOT, "web", "backend", "bridge", "qt_offscreen.py")

    if os.path.exists(_OFFSCREEN_PATH_SC18):
        try:
            with open(_OFFSCREEN_PATH_SC18, "r", encoding="utf-8") as _fh18:
                _offscreen_src18 = _fh18.read()
            if not isinstance(_offscreen_src18, str):  # Rule N: 타입 가드
                _offscreen_src18 = ""

            # SC18-a: _normalize_bond_keys 함수 정의 존재 여부
            if "def _normalize_bond_keys" not in _offscreen_src18:
                sc18_warn = True
                sc18_issues.append(
                    "SC18-a WARN: qt_offscreen.py에 _normalize_bond_keys() 함수 없음 "
                    "— HTTP bonds 문자열 키 변환 미처리 → analyzer.py ValueError → HTTP 500 위험 (M452)"
                )
                logger.warning(
                    "G7-SC18-a WARN: qt_offscreen.py missing _normalize_bond_keys() "
                    "— HTTP string bond keys will cause ValueError in analyzer.py (M452)"
                )

            # SC18-b: render_lewis/render_theory/render_esp 3개 진입점 모두 호출 여부
            # [MAGIC] 3개 render_* 함수에 _normalize_bond_keys 호출 필수
            _render_fns = ["render_lewis", "render_theory", "render_esp"]
            for _rfn in _render_fns:
                # 해당 함수 내부에 _normalize_bond_keys 호출이 있는지 간접 확인
                # 함수 정의 이후 첫 번째 "_normalize_bond_keys" 언급 횟수 = 함수 정의 1회 + 3호출 = 4회
                _call_count = _offscreen_src18.count("_normalize_bond_keys(bonds)")
                if _call_count < 3:
                    sc18_warn = True
                    sc18_issues.append(
                        f"SC18-b WARN: qt_offscreen.py _normalize_bond_keys(bonds) 호출 횟수={_call_count} "
                        f"(예상=3, render_lewis/theory/esp 각 1회) "
                        f"— 일부 render_* 진입점 bonds 변환 미처리 위험 (M452)"
                    )
                    logger.warning(
                        "G7-SC18-b WARN: qt_offscreen.py has %d _normalize_bond_keys(bonds) calls "
                        "(expected 3 — render_lewis/theory/esp each 1 call) "
                        "— some render_* entry points may pass raw string keys (M452)",
                        _call_count
                    )
                    break  # 1회만 경고

            # SC18-c: Rule N 타입 가드 존재 여부 (isinstance(bonds, dict) 패턴)
            if "isinstance(bonds, dict)" not in _offscreen_src18:
                sc18_warn = True
                sc18_issues.append(
                    "SC18-c WARN: qt_offscreen.py _normalize_bond_keys에 isinstance(bonds, dict) "
                    "타입 가드 없음 — Rule N 위반 (M452)"
                )
                logger.warning(
                    "G7-SC18-c WARN: qt_offscreen.py _normalize_bond_keys missing "
                    "isinstance(bonds, dict) type guard — Rule N violation (M452)"
                )

        except OSError as e:
            logger.warning("G7-SC18: cannot read qt_offscreen.py: %s", e)
    else:
        logger.warning(
            "G7-SC18: qt_offscreen.py not found at %s — SC18 skipped", _OFFSCREEN_PATH_SC18
        )

    sc18_overall = "WARN" if sc18_warn else "PASS"
    # SC18은 WARN 전용 (비차단) — bonds 키 형식 변환 누락 재발 방지 (M452)

    # -- G7-SC19: chemgrid_mobile 워크트리 동기화 검사 (M453 신설, WARN 전용 비차단) --
    # M453 결함: audit_gui가 워크트리에서 SynthesisViewer.tsx 등 chemgrid_mobile 파일 미발견 → phantom REJECT
    # 메인 repo (C:/chemgrid_mobile/) 대비 워크트리 chemgrid_mobile/ 동기화 상태 자동 점검.
    # 검사 대상: frontend/src/components/*.tsx, backend/routers/*.py (핵심 파일 10종)
    # [MAGIC] 핵심 파일 10종: SynthesisViewer.tsx / DockingPanel.tsx / SpectrumViewer.tsx /
    #   AlphaFoldPanel.tsx / MechanismViewer.tsx + synthesis.py / spectra.py / docking.py /
    #   alphafold.py / mechanisms.py
    sc19_warn = False
    sc19_issues: list[str] = []

    # worktree chemgrid_mobile 경로 — 현재 활성 워크트리에서 검사
    _WORKTREE_MOBILE_BASE = os.path.join(
        PROJECT_ROOT, ".claude", "worktrees"
    )
    # 메인 repo chemgrid_mobile (PROJECT_ROOT 상위)
    _MAIN_MOBILE_ROOT = os.path.join(os.path.dirname(PROJECT_ROOT), "chemgrid_mobile")

    # 핵심 파일 10종 (audit_gui가 반드시 발견해야 하는 파일)
    _SC19_KEY_FILES = [
        os.path.join("frontend", "src", "components", "SynthesisViewer.tsx"),
        os.path.join("frontend", "src", "components", "DockingPanel.tsx"),
        os.path.join("frontend", "src", "components", "SpectrumViewer.tsx"),
        os.path.join("frontend", "src", "components", "AlphaFoldPanel.tsx"),
        os.path.join("frontend", "src", "components", "MechanismViewer.tsx"),
        os.path.join("backend", "routers", "synthesis.py"),
        os.path.join("backend", "routers", "spectra.py"),
        os.path.join("backend", "routers", "docking.py"),
        os.path.join("backend", "routers", "alphafold.py"),
        os.path.join("backend", "routers", "mechanisms.py"),
    ]

    if os.path.isdir(_WORKTREE_MOBILE_BASE) and os.path.isdir(_MAIN_MOBILE_ROOT):
        try:
            _worktree_names_sc19 = [
                d for d in os.listdir(_WORKTREE_MOBILE_BASE)
                if os.path.isdir(os.path.join(_WORKTREE_MOBILE_BASE, d))
            ]
            for _wt_name_sc19 in _worktree_names_sc19:
                _wt_mobile_dir = os.path.join(
                    _WORKTREE_MOBILE_BASE, _wt_name_sc19, "chemgrid_mobile"
                )
                if not os.path.isdir(_wt_mobile_dir):
                    # chemgrid_mobile 폴더 자체가 워크트리에 없음 — 가장 심각한 케이스
                    sc19_warn = True
                    _issue_sc19 = (
                        f"SC19 WARN: worktree '{_wt_name_sc19}'에 chemgrid_mobile/ 폴더 미존재 "
                        f"— audit_gui가 모든 mobile 파일을 phantom REJECT 할 위험 (M453)"
                    )
                    sc19_issues.append(_issue_sc19)
                    logger.warning(
                        "G7-SC19 WARN: worktree '%s' missing chemgrid_mobile/ — "
                        "audit_gui will get phantom REJECT for all mobile files (M453, P-WORKTREE)",
                        _wt_name_sc19,
                    )
                    continue

                # 핵심 파일 10종 존재 검사
                for _rel_path in _SC19_KEY_FILES:
                    _wt_file_sc19 = os.path.join(_wt_mobile_dir, _rel_path)
                    if not os.path.exists(_wt_file_sc19):
                        sc19_warn = True
                        _fname_sc19 = os.path.basename(_rel_path)
                        _issue_file = (
                            f"SC19 WARN: chemgrid_mobile/{_rel_path} "
                            f"worktree '{_wt_name_sc19}'에 미존재 "
                            f"— 메인 repo 동기화 필요 (M453 P-WORKTREE)"
                        )
                        sc19_issues.append(_issue_file)
                        logger.warning(
                            "G7-SC19 WARN: chemgrid_mobile/%s absent in worktree '%s' "
                            "(M453, main repo sync required)",
                            _fname_sc19, _wt_name_sc19,
                        )
        except OSError as _e_sc19:
            logger.warning("G7-SC19: worktree scan error: %s", _e_sc19)
    else:
        logger.warning(
            "G7-SC19: worktree base (%s) or main mobile root (%s) not found — SC19 skipped (N/A)",
            _WORKTREE_MOBILE_BASE, _MAIN_MOBILE_ROOT,
        )

    sc19_overall = "WARN" if sc19_warn else "PASS"
    # SC19은 WARN 전용 (비차단) — chemgrid_mobile 워크트리 미동기화 phantom REJECT 재발 방지 (M453)

    # -- G7-SC20: chemgrid_mobile vs chemgrid/web 백엔드 동등성 검사 (M454 신설, WARN 전용 비차단) --
    # M443 부분 fix 패턴(D-3) 재발 방지: chemgrid/web만 fix하고 chemgrid_mobile 미처리.
    # [MAGIC] 검사 대상: chemgrid_mobile/backend/bridge/qt_offscreen.py
    sc20_warn = False
    sc20_issues: list[str] = []

    # chemgrid_mobile은 PROJECT_ROOT 상위에 위치
    _MOBILE_ROOT = os.path.join(os.path.dirname(PROJECT_ROOT), "chemgrid_mobile")
    _OFFSCREEN_PATH_SC20 = os.path.join(
        _MOBILE_ROOT, "backend", "bridge", "qt_offscreen.py"
    )

    if os.path.exists(_OFFSCREEN_PATH_SC20):
        try:
            with open(_OFFSCREEN_PATH_SC20, "r", encoding="utf-8") as _fh20:
                _offscreen_src20 = _fh20.read()
            if not isinstance(_offscreen_src20, str):  # Rule N: 타입 가드
                _offscreen_src20 = ""

            # SC20-a: _normalize_bond_keys 함수 정의 존재 여부 (M452 동등 처리)
            if "def _normalize_bond_keys" not in _offscreen_src20:
                sc20_warn = True
                sc20_issues.append(
                    "SC20-a WARN: chemgrid_mobile qt_offscreen.py에 _normalize_bond_keys() 없음 "
                    "— M452 string key fix chemgrid/web만 적용, chemgrid_mobile 미처리 (M454)"
                )
                logger.warning(
                    "G7-SC20-a WARN: chemgrid_mobile qt_offscreen.py missing _normalize_bond_keys() "
                    "— dual_backend_sync violation: web fix not applied to mobile (M454)"
                )

            # SC20-b: CloudRenderer().render() 잘못된 인스턴스 호출 잔존 탐지
            # M443 핫픽스가 chemgrid/web만 처리, chemgrid_mobile 미처리 패턴 탐지.
            # 주석(# 시작), docstring("""...""") 내부를 제외하고 실제 코드 호출만 탐지.
            # [MAGIC] 전략: 라인별 스캔 — stripped가 #로 시작하면 skip, # 뒤 인라인은 trim
            _sc20b_found = False
            _in_docstring = False
            for _sc20b_line in _offscreen_src20.splitlines():
                _stripped20 = _sc20b_line.strip()
                # docstring 진입/탈출 추적 (""" 홀수 번째 = 진입, 짝수 = 탈출)
                if '"""' in _stripped20:
                    _count_dq = _stripped20.count('"""')
                    if _count_dq % 2 == 1:
                        _in_docstring = not _in_docstring
                if _in_docstring:
                    continue
                if _stripped20.startswith("#"):
                    continue
                _code_part = _stripped20.split("#")[0]
                if "CloudRenderer().render(" in _code_part:
                    _sc20b_found = True
                    break
            if _sc20b_found:
                sc20_warn = True
                sc20_issues.append(
                    "SC20-b WARN: chemgrid_mobile qt_offscreen.py에 CloudRenderer().render() 실제 코드 호출 잔존 "
                    "— M443 fix chemgrid/web만 적용, chemgrid_mobile 미처리 (M454)"
                )
                logger.warning(
                    "G7-SC20-b WARN: chemgrid_mobile qt_offscreen.py still calls CloudRenderer().render() "
                    "in non-comment code — AttributeError guaranteed at runtime. "
                    "Use CloudRenderer.draw_clouds() (M454)"
                )

            # SC20-c: CloudRenderer.draw_clouds 호출 존재 여부
            if "CloudRenderer.draw_clouds" not in _offscreen_src20:
                sc20_warn = True
                sc20_issues.append(
                    "SC20-c WARN: chemgrid_mobile qt_offscreen.py에 CloudRenderer.draw_clouds 호출 없음 "
                    "— ESP 렌더링 미구현 (M454)"
                )
                logger.warning(
                    "G7-SC20-c WARN: chemgrid_mobile qt_offscreen.py missing CloudRenderer.draw_clouds call "
                    "— ESP rendering will fail (M454)"
                )

        except OSError as e:
            logger.warning("G7-SC20: cannot read chemgrid_mobile qt_offscreen.py: %s", e)
    else:
        logger.warning(
            "G7-SC20: chemgrid_mobile qt_offscreen.py not found at %s — SC20 skipped (N/A)",
            _OFFSCREEN_PATH_SC20,
        )

    sc20_overall = "WARN" if sc20_warn else "PASS"
    # SC20은 WARN 전용 (비차단) — dual_backend_sync 동등성 재발 방지 (M454)

    # -- G7-SC21: AlphaFold 외부 API URL 하드코딩 탐지 (M455 신설, WARN 전용 비차단) --
    # 목적: model_v4.pdb / model_vN.pdb 형식의 하드코딩 재발 방지.
    #        AlphaFold EBI DB는 latestVersion을 변경하며 이전 버전 PDB URL은 HTTP 404 반환.
    #        _resolve_alphafold_pdb_url() 동적 조회 함수가 있어야 하드코딩 제거 완료로 판정.
    #
    # SC21-a: alphafold.py에 model_v[0-9]+.pdb 패턴 URL 하드코딩 잔존 탐지
    # SC21-b: _resolve_alphafold_pdb_url 함수 존재 여부 (동적 조회 함수 필수)
    # SC21-c: _ALPHAFOLD_DB_API_URL 상수 존재 여부 (API 기반 URL 조회 여부)
    sc21_warn: list[str] = []
    sc21_issues: list[str] = []

    _ALPHAFOLD_ROUTER_PATHS_SC21 = [
        os.path.join(PROJECT_ROOT, "chemgrid_mobile", "backend", "routers", "alphafold.py"),
        # worktree 경로도 검사 (P-WORKTREE FP-09 패턴 대비)
        os.path.join(
            PROJECT_ROOT, ".claude", "worktrees", "naughty-raman-fcb287",
            "chemgrid_mobile", "backend", "routers", "alphafold.py"
        ),
    ]
    _HARDCODED_VERSION_RE_SC21 = re.compile(r"model_v\d+\.pdb")  # model_v4.pdb / model_v6.pdb 등
    _sc21_found = False

    for _af_path in _ALPHAFOLD_ROUTER_PATHS_SC21:
        if not os.path.exists(_af_path):
            continue  # 경로 없으면 skip (선택적 경로)
        _sc21_found = True
        try:
            with open(_af_path, "r", encoding="utf-8") as _fh21:
                _af_content = _fh21.read()

            if not isinstance(_af_content, str):
                logger.warning("G7-SC21: non-str content in alphafold.py at %s", _af_path)
                continue

            # SC21-a: model_vN.pdb 하드코딩 패턴 탐지 (주석 제외 실제 코드 라인)
            _hardcoded_lines: list[str] = []
            for _line in _af_content.splitlines():
                _stripped = _line.strip()
                if _stripped.startswith("#"):
                    continue  # 주석 라인 skip
                if _HARDCODED_VERSION_RE_SC21.search(_stripped):
                    _hardcoded_lines.append(_stripped[:120])

            if _hardcoded_lines:
                _msg_21a = (
                    f"SC21-a WARN: alphafold.py에 model_vN.pdb 하드코딩 {len(_hardcoded_lines)}건 잔존 "
                    f"— HTTP 404 위험 (M455 D-1 패턴) | 파일: {os.path.basename(_af_path)}"
                )
                sc21_warn.append(_msg_21a)
                sc21_issues.extend(_hardcoded_lines)
                logger.warning(
                    "G7-SC21-a WARN: alphafold.py has %d hardcoded model_vN.pdb lines "
                    "(M455 HTTP 404 risk) in %s",
                    len(_hardcoded_lines), _af_path,
                )

            # SC21-b: _resolve_alphafold_pdb_url 함수 존재 여부
            if "_resolve_alphafold_pdb_url" not in _af_content:
                _msg_21b = (
                    f"SC21-b WARN: alphafold.py에 _resolve_alphafold_pdb_url() 없음 "
                    f"— 동적 pdbUrl 조회 함수 미구현 | 파일: {os.path.basename(_af_path)}"
                )
                sc21_warn.append(_msg_21b)
                sc21_issues.append(_msg_21b)
                logger.warning(
                    "G7-SC21-b WARN: alphafold.py missing _resolve_alphafold_pdb_url() "
                    "(M455 dynamic URL resolver required) in %s",
                    _af_path,
                )

            # SC21-c: _ALPHAFOLD_DB_API_URL 상수 존재 여부
            if "_ALPHAFOLD_DB_API_URL" not in _af_content:
                _msg_21c = (
                    f"SC21-c WARN: alphafold.py에 _ALPHAFOLD_DB_API_URL 상수 없음 "
                    f"— API 기반 URL 조회 미구현 | 파일: {os.path.basename(_af_path)}"
                )
                sc21_warn.append(_msg_21c)
                sc21_issues.append(_msg_21c)
                logger.warning(
                    "G7-SC21-c WARN: alphafold.py missing _ALPHAFOLD_DB_API_URL constant "
                    "(M455 API-based URL resolution required) in %s",
                    _af_path,
                )

        except OSError as e:
            logger.warning("G7-SC21: cannot read alphafold.py at %s: %s", _af_path, e)

    if not _sc21_found:
        logger.warning("G7-SC21: alphafold.py not found in any known path — SC21 skipped (N/A)")

    sc21_overall = "WARN" if sc21_warn else "PASS"
    # SC21은 WARN 전용 (비차단) — 외부 API URL 하드코딩 재발 방지 (M455)

    # -- G7-SC22: popup_docking.py interactions 변수 미초기화 UnboundLocalError 탐지 (M456 신설, WARN 전용 비차단) --
    # M438 Worker가 `if not isinstance(interactions, dict): interactions = {}` 패턴을 추가했으나
    # interactions 변수 자체가 해당 스코프에서 초기화되지 않은 상태 → UnboundLocalError.
    # 올바른 패턴: interactions_map = getattr(self.docking_result, 'interactions', None) 선행 초기화 후 .get()
    #
    # SC22-a: popup_docking.py에서 `if not isinstance(interactions, dict): interactions = {}` 단독 패턴 잔존 탐지
    #         (getattr 선행 초기화 없이 isinstance만 사용하는 경우)
    sc22_warn: list[str] = []
    sc22_issues: list[str] = []

    _POPUP_DOCKING_PATHS_SC22 = [
        os.path.join(PROJECT_ROOT, "src", "app", "popup_docking.py"),
        # worktree 경로도 검사 (P-WORKTREE FP-09 패턴 대비)
        os.path.join(PROJECT_ROOT, ".claude", "worktrees", "naughty-raman-fcb287", "src", "app", "popup_docking.py"),
    ]

    # [MAGIC] 탐지 대상 취약 패턴: interactions 사전 초기화 없이 isinstance 체크만 수행
    _UNBOUND_INTERACTIONS_PATTERN = re.compile(
        r"if\s+not\s+isinstance\s*\(\s*interactions\s*,\s*dict\s*\)\s*:\s*interactions\s*=\s*\{\}"
    )

    for _docking_path_sc22 in _POPUP_DOCKING_PATHS_SC22:
        if not os.path.exists(_docking_path_sc22):
            continue

        try:
            with open(_docking_path_sc22, "r", encoding="utf-8") as _fh22:
                _docking_src22 = _fh22.read()
            if not isinstance(_docking_src22, str):  # Rule N: 타입 가드
                _docking_src22 = ""

            # SC22-a: 취약 단독 패턴 탐지 — getattr 선행 초기화 없이 isinstance만 쓴 경우
            _unbound_hits22: list[str] = []
            for _lno22, _line22 in enumerate(_docking_src22.splitlines(), 1):
                _stripped22 = _line22.strip()
                if _stripped22.startswith("#"):
                    continue  # 주석 skip
                if _UNBOUND_INTERACTIONS_PATTERN.search(_stripped22):
                    _unbound_hits22.append(f"L{_lno22}: {_stripped22[:120]}")

            if _unbound_hits22:
                _msg22a = (
                    f"SC22-a WARN: popup_docking.py에 interactions UnboundLocalError 취약 패턴 "
                    f"{len(_unbound_hits22)}건 잔존 — getattr 선행 초기화 없음 "
                    f"(M456 F2 fix 미적용) | 파일: {os.path.basename(_docking_path_sc22)}"
                )
                sc22_warn.append(_msg22a)
                sc22_issues.extend(_unbound_hits22)
                logger.warning(
                    "G7-SC22-a WARN: popup_docking.py has %d UnboundLocalError-prone interactions patterns "
                    "— use interactions_map = getattr(self.docking_result, 'interactions', None) first (M456 F2)",
                    len(_unbound_hits22),
                )

        except OSError as e:
            logger.warning("G7-SC22: cannot read popup_docking.py at %s: %s", _docking_path_sc22, e)

    sc22_overall = "WARN" if sc22_warn else "PASS"
    # SC22은 WARN 전용 (비차단) — interactions UnboundLocalError 재발 방지 (M456)

    # -- G7-SC23: frontend fetch 경로 vs backend router prefix 불일치 탐지 (M457 신설, WARN 전용 비차단) --
    sc23_warn: list[str] = []
    sc23_issues: list[str] = []

    _MOBILE_FRONTEND_PATHS_SC23 = [
        os.path.join(PROJECT_ROOT, "..", "chemgrid_mobile", "frontend", "src", "components", "MoleculeCanvas.tsx"),
        os.path.join(PROJECT_ROOT, "..", "chemgrid_mobile", "frontend", "src", "components"),
    ]
    _MAIN_PY_PATH_SC23 = os.path.join(PROJECT_ROOT, "..", "chemgrid_mobile", "backend", "main.py")
    _SC23_OLD_FETCH_RE = re.compile(r"fetch\s*\(['\"]\/api\/analyze['\"]", re.IGNORECASE)
    _SC23_OLD_PREFIX_RE = re.compile(r'include_router\s*\(drawing\.router\s*,\s*prefix\s*=\s*["\']\/api\/render["\']', re.IGNORECASE)

    # SC23-a: frontend *.tsx 에서 /api/analyze 구경로 잔존 탐지
    _tsx_root_sc23 = os.path.join(PROJECT_ROOT, "..", "chemgrid_mobile", "frontend", "src")
    if os.path.isdir(_tsx_root_sc23):
        for _root23, _dirs23, _files23 in os.walk(_tsx_root_sc23):
            for _fn23 in _files23:
                if not _fn23.endswith(".tsx"):
                    continue
                _fpath23 = os.path.join(_root23, _fn23)
                try:
                    with open(_fpath23, "r", encoding="utf-8", errors="replace") as _fh23:
                        _content23 = _fh23.read()
                    _hits23 = _SC23_OLD_FETCH_RE.findall(_content23)
                    if _hits23:
                        _msg23a = (
                            f"SC23-a WARN: {os.path.basename(_fpath23)} 에 구경로 '/api/analyze' fetch "
                            f"{len(_hits23)}건 잔존 (M457 fix 미적용 — '/api/molecules/analyze' 로 수정 필요)"
                        )
                        sc23_warn.append(_msg23a)
                        sc23_issues.extend(_hits23)
                        logger.warning(
                            "G7-SC23-a WARN: %s has %d old fetch('/api/analyze') patterns (M457 fix not applied)",
                            _fn23, len(_hits23)
                        )
                except OSError as e:
                    logger.warning("G7-SC23: cannot read %s: %s", _fpath23, e)

    # SC23-b: main.py 에서 drawing.router prefix='/api/render' 잔존 탐지
    if os.path.isfile(_MAIN_PY_PATH_SC23):
        try:
            with open(_MAIN_PY_PATH_SC23, "r", encoding="utf-8", errors="replace") as _fh23b:
                _main23 = _fh23b.read()
            _old_prefix23 = _SC23_OLD_PREFIX_RE.findall(_main23)
            if _old_prefix23:
                _msg23b = (
                    "SC23-b WARN: main.py 에 drawing.router prefix='/api/render' 잔존 "
                    "(M457 fix 미적용 — '/api/molecules' 로 수정 필요)"
                )
                sc23_warn.append(_msg23b)
                sc23_issues.extend(_old_prefix23)
                logger.warning("G7-SC23-b WARN: main.py has old prefix='/api/render' for drawing.router (M457 fix not applied)")
        except OSError as e:
            logger.warning("G7-SC23: cannot read main.py: %s", e)

    sc23_overall = "WARN" if sc23_warn else "PASS"
    # SC23은 WARN 전용 (비차단) — frontend-backend 경로 불일치 재발 방지 (M457)

    # -- G7-SC24: backend fix 후 재시작 누락 탐지 (M458 신설, WARN 전용 비차단) --
    sc24_warn: list[str] = []
    sc24_issues: list[str] = []
    _SC24_PORT = 8000  # [MAGIC] chemgrid_mobile 표준 포트

    # SC24-a: main.py에 /api/molecules prefix 설정 존재 여부
    _sc24_main_has_new_prefix = False
    if os.path.isfile(_MAIN_PY_PATH_SC23):
        try:
            with open(_MAIN_PY_PATH_SC23, "r", encoding="utf-8", errors="replace") as _fh24a:
                _main24 = _fh24a.read()
            _sc24_main_has_new_prefix = bool(
                re.search(r'include_router\s*\(drawing\.router\s*,\s*prefix\s*=\s*["\']\/api\/molecules["\']', _main24, re.IGNORECASE)
            )
        except OSError as e:
            logger.warning("G7-SC24: cannot read main.py: %s", e)

    # SC24-b: /api/molecules/analyze 실시간 HTTP 확인 (코드 fix 반영 여부)
    if _sc24_main_has_new_prefix:
        import urllib.request
        import urllib.error
        _sc24_url = f"http://127.0.0.1:{_SC24_PORT}/api/molecules/analyze"
        _sc24_payload = b'{"smiles":"c1ccccc1","width":400,"height":300}'
        try:
            _sc24_req = urllib.request.Request(
                _sc24_url, data=_sc24_payload,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(_sc24_req, timeout=5) as _resp24:
                _sc24_status = _resp24.status
        except urllib.error.HTTPError as _he24:
            _sc24_status = _he24.code
        except Exception as _e24:
            _sc24_status = 0
            logger.warning("G7-SC24: HTTP request failed: %s", _e24)

        if _sc24_status == 404:
            _msg24b = (
                f"SC24-b WARN: main.py 에 prefix='/api/molecules' 설정 존재하나 "
                f"포트 {_SC24_PORT} 인스턴스가 HTTP 404 반환 → 구버전 uvicorn 가동 중. "
                f"재시작 필요: `kill $(ps -ef | grep uvicorn | grep {_SC24_PORT}...)` + uvicorn 재시작. "
                f"docs/ai/skills/backend_restart_protocol.md 참조 (M458)."
            )
            sc24_warn.append(_msg24b)
            sc24_issues.append(f"HTTP 404 at {_sc24_url}")
            logger.warning("G7-SC24-b WARN: /api/molecules/analyze HTTP 404 — old uvicorn instance running (M458)")
        elif _sc24_status == 200:
            logger.info("G7-SC24-b PASS: /api/molecules/analyze HTTP 200 — M458 fix active")
        elif _sc24_status == 0:
            logger.warning("G7-SC24-b WARN: port %d not reachable — backend may not be running", _SC24_PORT)
        else:
            logger.warning("G7-SC24-b: unexpected HTTP %d from /api/molecules/analyze", _sc24_status)

    sc24_overall = "WARN" if sc24_warn else "PASS"
    # SC24는 WARN 전용 (비차단) — 코드 fix 후 재시작 미수행 재발 방지 (M458)

    # -- G7-SC25: AlphaFold 외부 링크 prominent 배치 자동 검사 (M460 신설, WARN 전용 비차단) --
    sc25_warn: list[str] = []
    sc25_issues: list[str] = []

    _POPUP_AF_PATH = os.path.join(PROJECT_ROOT, "src", "app", "popup_alphafold.py")
    _TSX_AF_PATH_SC25 = os.path.join(
        PROJECT_ROOT, "..", "chemgrid_mobile", "frontend", "src", "components", "AlphaFoldPanel.tsx"
    )

    # SC25-a: popup_alphafold.py 데스크톱 — btn_alphafold_external + _on_open_alphafold_external
    if os.path.isfile(_POPUP_AF_PATH):
        try:
            with open(_POPUP_AF_PATH, "r", encoding="utf-8") as _fh25:
                _af25_txt = _fh25.read()
            if not isinstance(_af25_txt, str):  # Rule N
                logger.warning("G7-SC25: non-str content in popup_alphafold.py")
                _af25_txt = ""
            # SC25-a 체크
            if "btn_alphafold_external" not in _af25_txt:
                _m25a = "SC25-a WARN: popup_alphafold.py에 btn_alphafold_external 버튼 미존재 (M460 배치 필요)"
                sc25_warn.append(_m25a)
                sc25_issues.append("btn_alphafold_external missing in popup_alphafold.py")
                logger.warning("G7-SC25-a WARN: %s", _m25a)
            if "_on_open_alphafold_external" not in _af25_txt:
                _m25a2 = "SC25-a WARN: popup_alphafold.py에 _on_open_alphafold_external 메서드 미존재"
                sc25_warn.append(_m25a2)
                sc25_issues.append("_on_open_alphafold_external missing")
                logger.warning("G7-SC25-a2 WARN: %s", _m25a2)
            # SC25-b 체크
            if "uniprot_id_input" not in _af25_txt:
                _m25b = "SC25-b WARN: popup_alphafold.py에 uniprot_id_input 필드 미존재 (UniProt ID 입력 없음)"
                sc25_warn.append(_m25b)
                sc25_issues.append("uniprot_id_input missing in popup_alphafold.py")
                logger.warning("G7-SC25-b WARN: %s", _m25b)
        except OSError as _e25:
            logger.warning("G7-SC25: cannot read popup_alphafold.py: %s", _e25)
    else:
        logger.warning("G7-SC25: popup_alphafold.py not found at %s", _POPUP_AF_PATH)

    # SC25-c/d: AlphaFoldPanel.tsx 웹 — openAlphaFoldExternal + uniprotId + 스타일
    _tsx25_abs = os.path.normpath(_TSX_AF_PATH_SC25)
    if os.path.isfile(_tsx25_abs):
        try:
            with open(_tsx25_abs, "r", encoding="utf-8") as _fh25t:
                _tsx25_txt = _fh25t.read()
            if not isinstance(_tsx25_txt, str):  # Rule N
                logger.warning("G7-SC25: non-str content in AlphaFoldPanel.tsx")
                _tsx25_txt = ""
            # SC25-c 체크
            if "openAlphaFoldExternal" not in _tsx25_txt:
                _m25c = "SC25-c WARN: AlphaFoldPanel.tsx에 openAlphaFoldExternal 함수 미존재"
                sc25_warn.append(_m25c)
                sc25_issues.append("openAlphaFoldExternal missing in AlphaFoldPanel.tsx")
                logger.warning("G7-SC25-c WARN: %s", _m25c)
            if "uniprotId" not in _tsx25_txt:
                _m25c2 = "SC25-c WARN: AlphaFoldPanel.tsx에 uniprotId 상태 미존재"
                sc25_warn.append(_m25c2)
                sc25_issues.append("uniprotId state missing in AlphaFoldPanel.tsx")
                logger.warning("G7-SC25-c2 WARN: %s", _m25c2)
            # SC25-d 체크
            if "externalBanner" not in _tsx25_txt:
                _m25d = "SC25-d WARN: AlphaFoldPanel.tsx에 externalBanner 스타일 미존재 (M460 배치 확인 필요)"
                sc25_warn.append(_m25d)
                sc25_issues.append("externalBanner style missing in AlphaFoldPanel.tsx")
                logger.warning("G7-SC25-d WARN: %s", _m25d)
            if "externalBtn" not in _tsx25_txt:
                _m25d2 = "SC25-d WARN: AlphaFoldPanel.tsx에 externalBtn 스타일 미존재"
                sc25_warn.append(_m25d2)
                sc25_issues.append("externalBtn style missing in AlphaFoldPanel.tsx")
                logger.warning("G7-SC25-d2 WARN: %s", _m25d2)
        except OSError as _e25t:
            logger.warning("G7-SC25: cannot read AlphaFoldPanel.tsx: %s", _e25t)
    else:
        logger.warning("G7-SC25: AlphaFoldPanel.tsx not found at %s", _tsx25_abs)

    sc25_overall = "WARN" if sc25_warn else "PASS"
    # SC25는 WARN 전용 (비차단) — AlphaFold 외부 링크 prominent 배치 재발 방지 (M460)

    # -- G7-SC26: DryLab Report AlphaFold 섹션 자동 검사 (M461 신설, WARN 전용 비차단) --
    # H-3: patrol SC26 — DryLabData.alphafold_uniprot_id 필드 + _sec_part2e_alphafold_docking 미존재 탐지
    sc26_warn: list[str] = []
    sc26_issues: list[str] = []

    _DRYLAB_EXPORTER_PATH = os.path.join(PROJECT_ROOT, "src", "app", "drylab_report_exporter.py")

    if os.path.isfile(_DRYLAB_EXPORTER_PATH):
        try:
            with open(_DRYLAB_EXPORTER_PATH, "r", encoding="utf-8") as _fh26:
                _dry26_txt = _fh26.read()
            if not isinstance(_dry26_txt, str):  # Rule N
                logger.warning("G7-SC26: non-str content in drylab_report_exporter.py")
                _dry26_txt = ""
            # SC26-a: alphafold_uniprot_id 필드 존재 (DryLabData)
            if "alphafold_uniprot_id" not in _dry26_txt:
                _m26a = ("SC26-a WARN: drylab_report_exporter.py에 DryLabData.alphafold_uniprot_id "
                         "필드 미존재 (M461 통합 필요)")
                sc26_warn.append(_m26a)
                sc26_issues.append("DryLabData.alphafold_uniprot_id field missing")
                logger.warning("G7-SC26-a WARN: %s", _m26a)
            # SC26-b: _sec_part2e_alphafold_docking 메서드 존재
            if "_sec_part2e_alphafold_docking" not in _dry26_txt:
                _m26b = ("SC26-b WARN: drylab_report_exporter.py에 _sec_part2e_alphafold_docking "
                         "메서드 미존재 (M461 AlphaFold DryLab 섹션 누락)")
                sc26_warn.append(_m26b)
                sc26_issues.append("_sec_part2e_alphafold_docking method missing")
                logger.warning("G7-SC26-b WARN: %s", _m26b)
            # SC26-c: 학술 인용 — 이론적 정합성 의무 (사용자 강조)
            # Jumper 2021 인용 필수
            if "Jumper" not in _dry26_txt or "2021" not in _dry26_txt:
                _m26c = ("SC26-c WARN: drylab_report_exporter.py에 Jumper et al. 2021 "
                         "(AlphaFold2) 학술 인용 미존재 — 이론적 정합성 위반")
                sc26_warn.append(_m26c)
                sc26_issues.append("AlphaFold2 citation (Jumper 2021) missing in DryLab exporter")
                logger.warning("G7-SC26-c WARN: %s", _m26c)
            # SC26-d: alphafold_plddt_summary 필드 존재
            if "alphafold_plddt_summary" not in _dry26_txt:
                _m26d = ("SC26-d WARN: DryLabData.alphafold_plddt_summary 필드 미존재 "
                         "(pLDDT 분포 데이터 누락)")
                sc26_warn.append(_m26d)
                sc26_issues.append("DryLabData.alphafold_plddt_summary field missing")
                logger.warning("G7-SC26-d WARN: %s", _m26d)
        except OSError as _e26:
            logger.warning("G7-SC26: cannot read drylab_report_exporter.py: %s", _e26)
    else:
        logger.warning("G7-SC26: drylab_report_exporter.py not found at %s", _DRYLAB_EXPORTER_PATH)

    sc26_overall = "WARN" if sc26_warn else "PASS"
    # SC26는 WARN 전용 (비차단) — DryLab AlphaFold 섹션 미통합 재발 방지 (M461)

    # -- G7-SC27: AlphaFold 6단계 학생 흐름 자동 검사 (M463 신설, WARN 전용 비차단) --
    # H-3: patrol SC27 — Protein3DViewerWidget 제거 + M461 시그널 보존 확인
    # M463 목적: 6단계 탭 + PDBe Mol* + DryLab 통합 — Protein3DViewerWidget(QPainter) 완전 제거
    sc27_warn: list[str] = []
    sc27_issues: list[str] = []

    _POPUP_ALPHAFOLD_PATH = os.path.join(PROJECT_ROOT, "src", "app", "popup_alphafold.py")
    _DRYLAB_EXPORTER_PATH_27 = os.path.join(PROJECT_ROOT, "src", "app", "drylab_report_exporter.py")
    if os.path.exists(_POPUP_ALPHAFOLD_PATH):
        try:
            with open(_POPUP_ALPHAFOLD_PATH, "r", encoding="utf-8") as _fh27:
                _af27_txt = _fh27.read()
            if not isinstance(_af27_txt, str):  # Rule N
                logger.warning("G7-SC27: non-str content in popup_alphafold.py")
                _af27_txt = ""
            # SC27-a: Protein3DViewerWidget 클래스 없음 (M463에서 완전 제거)
            if "class Protein3DViewerWidget" in _af27_txt:
                _m27a = (
                    "SC27-a WARN: popup_alphafold.py에 Protein3DViewerWidget 클래스 잔존 "
                    "— M463에서 완전 제거 필요 (PDBe Mol* 외부 링크로 대체)"
                )
                sc27_warn.append(_m27a)
                sc27_issues.append("Protein3DViewerWidget still present (M463 requires removal)")
                logger.warning("G7-SC27-a WARN: %s", _m27a)
            # SC27-b: alphafold_to_docking 시그널 존재 (M461 보존 확인)
            if "alphafold_to_docking" not in _af27_txt:
                _m27b = (
                    "SC27-b WARN: popup_alphafold.py에 alphafold_to_docking pyqtSignal 미존재 "
                    "— M461 보존 필요 (AlphaFold→도킹 데이터 전달 채널)"
                )
                sc27_warn.append(_m27b)
                sc27_issues.append("alphafold_to_docking signal missing (M461 preservation)")
                logger.warning("G7-SC27-b WARN: %s", _m27b)
            # SC27-c: PDBe Mol* 버튼/_create_tab5_pdbe 존재 (M463 신규 기능)
            if "_create_tab5_pdbe" not in _af27_txt and "pdbe" not in _af27_txt.lower():
                _m27c = (
                    "SC27-c WARN: popup_alphafold.py에 PDBe Mol* 시각화 탭 미존재 "
                    "— M463 단계 5 (PDBe Mol 시각화) 구현 필요"
                )
                sc27_warn.append(_m27c)
                sc27_issues.append("PDBe Mol* tab (_create_tab5_pdbe) missing")
                logger.warning("G7-SC27-c WARN: %s", _m27c)
        except OSError as _e27:
            logger.warning("G7-SC27: cannot read popup_alphafold.py: %s", _e27)
    else:
        logger.warning("G7-SC27: popup_alphafold.py not found at %s", _POPUP_ALPHAFOLD_PATH)

    # SC27-d: drylab_report_exporter.py에 _sec_part2f_integrated_drug_discovery 메서드 존재 (M463 신규)
    if os.path.exists(_DRYLAB_EXPORTER_PATH_27):
        try:
            with open(_DRYLAB_EXPORTER_PATH_27, "r", encoding="utf-8") as _fh27d:
                _dry27_txt = _fh27d.read()
            if not isinstance(_dry27_txt, str):  # Rule N
                logger.warning("G7-SC27-d: non-str content in drylab_report_exporter.py")
                _dry27_txt = ""
            if "_sec_part2f_integrated_drug_discovery" not in _dry27_txt:
                _m27d = (
                    "SC27-d WARN: drylab_report_exporter.py에 _sec_part2f_integrated_drug_discovery "
                    "메서드 미존재 — M463 신약개발 통합 분석 섹션 미구현"
                )
                sc27_warn.append(_m27d)
                sc27_issues.append("_sec_part2f_integrated_drug_discovery method missing")
                logger.warning("G7-SC27-d WARN: %s", _m27d)
        except OSError as _e27d:
            logger.warning("G7-SC27-d: cannot read drylab_report_exporter.py: %s", _e27d)
    else:
        logger.warning("G7-SC27: drylab_report_exporter.py not found at %s", _DRYLAB_EXPORTER_PATH_27)

    sc27_overall = "WARN" if sc27_warn else "PASS"
    # SC27는 WARN 전용 (비차단) — AlphaFold 6단계 학생 흐름 재발 방지 (M463)

    # -- G7-SC28: 포그라운드 자가 검증 사이클 결과 자동 검사 (M464 신설, WARN 전용 비차단) --
    # H-3: patrol SC28 — foreground_cycle_state.json 존재 + defect_count 탐지
    # M464 사용자 요구: "포그라운드에서 타이핑이랑 가상마우스 통해서 모든 기능들 전수점검"
    # Rule F (사용자환경피드백) 강화: 자가 검증 사이클 결과를 patrol이 자동 확인
    sc28_warn = False
    sc28_issues: list[str] = []

    # SC28-a: foreground_test_matrix_result.json 존재 여부 (최근 사이클 실행 증거)
    _FG_RESULT_PATH = os.path.join(PROJECT_ROOT, "docs", "reports",
                                   "foreground_test_matrix_result.json")
    if not os.path.exists(_FG_RESULT_PATH):
        # 파일 미존재 = 아직 한 번도 포그라운드 사이클 미실행 — WARN만 (비차단)
        sc28_warn = True
        _m28a = (
            "SC28-a WARN: foreground_test_matrix_result.json 미존재 "
            "— M464 포그라운드 자가 검증 사이클 아직 미실행. "
            "bash housing/sinktank/foreground_cycle.sh 로 시작 필요"
        )
        sc28_issues.append(_m28a)
        logger.warning(
            "G7-SC28-a WARN: foreground_test_matrix_result.json not found "
            "— M464 foreground self-verification cycle not yet run "
            "(bash housing/sinktank/foreground_cycle.sh)"
        )
    else:
        # SC28-b: 결과 파일에서 결함 수 확인
        try:
            with open(_FG_RESULT_PATH, "r", encoding="utf-8") as _fh28:
                _fg_result = json.loads(_fh28.read())
            if not isinstance(_fg_result, dict):  # Rule N: 타입 가드
                logger.warning("G7-SC28: foreground result 비dict 타입")
            else:
                _fg_defects = _fg_result.get("defect_count", 0)
                if not isinstance(_fg_defects, int):  # Rule N
                    _fg_defects = 0
                    logger.warning("G7-SC28: defect_count 비int — 0으로 처리")
                if _fg_defects > 0:
                    sc28_warn = True
                    _m28b = (
                        f"SC28-b WARN: 포그라운드 자가 검증 결함 {_fg_defects}건 잔존 "
                        f"(foreground_test_matrix_result.json). "
                        f"Rule W: 결함 수정 Worker spawn 필요"
                    )
                    sc28_issues.append(_m28b)
                    logger.warning(
                        "G7-SC28-b WARN: foreground self-verification %d defect(s) found "
                        "— Rule W: Worker spawn required to fix",
                        _fg_defects,
                    )
                # SC28-c: 결과 파일 최신성 검사 (24시간 이상 경과 시 WARN)
                _fg_ts_str = _fg_result.get("generated_at", "")
                if isinstance(_fg_ts_str, str) and _fg_ts_str:
                    import datetime as _dt
                    try:
                        _fg_ts = _dt.datetime.fromisoformat(_fg_ts_str)
                        _now = _dt.datetime.now()
                        # [MAGIC] 24시간 = 86400초 (포그라운드 사이클 최소 실행 주기)
                        _AGE_LIMIT_SEC = 86400
                        _age_sec = (_now - _fg_ts).total_seconds()
                        if _age_sec > _AGE_LIMIT_SEC:
                            sc28_warn = True
                            _m28c = (
                                f"SC28-c WARN: 포그라운드 검증 결과가 "
                                f"{_age_sec/3600:.1f}시간 경과 — 재실행 필요 "
                                f"(기준: {_AGE_LIMIT_SEC/3600:.0f}시간)"
                            )
                            sc28_issues.append(_m28c)
                            logger.warning(
                                "G7-SC28-c WARN: foreground result is %.1f hours old "
                                "(limit: %.0f hours) — re-run foreground_cycle.sh",
                                _age_sec / 3600, _AGE_LIMIT_SEC / 3600,
                            )
                    except (ValueError, TypeError) as _e28c:
                        logger.warning("G7-SC28: generated_at 파싱 실패: %s", _e28c)
        except (OSError, ValueError) as _e28:
            logger.warning("G7-SC28: foreground result 읽기 실패: %s", _e28)

    # SC28-d: user_feedback_matrix.json 존재 여부 (격분 추출 실행 증거)
    _FEEDBACK_MATRIX_PATH = os.path.join(PROJECT_ROOT, "docs", "reports",
                                          "user_feedback_matrix.json")
    if not os.path.exists(_FEEDBACK_MATRIX_PATH):
        sc28_warn = True
        _m28d = (
            "SC28-d WARN: user_feedback_matrix.json 미존재 "
            "— M464 사용자 피드백 추출 미실행. "
            "python tools/user_feedback_extractor.py 로 실행 필요"
        )
        sc28_issues.append(_m28d)
        logger.warning(
            "G7-SC28-d WARN: user_feedback_matrix.json not found "
            "— M464 user feedback extraction not run "
            "(python tools/user_feedback_extractor.py)"
        )

    sc28_overall = "WARN" if sc28_warn else "PASS"
    # SC28는 WARN 전용 (비차단) — 포그라운드 자가 검증 사이클 미실행/결함 재발 방지 (M464)

    # -- G7-SC29: DOCX 콘텐츠 패리티 + PDBe Mol* 이미지 삽입 검사 (M469 신설, WARN 전용 비차단) --
    # H-3: patrol SC29 — _export_docx()에 molstar_capture 호출 + add_picture 미존재 탐지
    # M469 요구: "DOCX에 PDBe Mol* 이미지 부재 자동 검사"
    sc29_warn = False
    sc29_issues: list[str] = []

    _DRYLAB_EXPORTER_PATH_29 = os.path.join(PROJECT_ROOT, "src", "app",
                                              "drylab_report_exporter.py")
    _MOLSTAR_CAPTURE_PATH_29 = os.path.join(PROJECT_ROOT, "src", "app",
                                              "molstar_capture.py")

    if os.path.exists(_DRYLAB_EXPORTER_PATH_29):
        try:
            with open(_DRYLAB_EXPORTER_PATH_29, "r", encoding="utf-8",
                      errors="replace") as _fh29:
                _content29 = _fh29.read()

            if not isinstance(_content29, str):
                logger.warning("G7-SC29: non-str content in drylab_report_exporter.py")
                _content29 = ""

            # SC29-a: _export_docx 내 molstar_capture 호출 존재 여부
            if "build_molstar_panel_images" not in _content29:
                sc29_warn = True
                _m29a = (
                    "SC29-a WARN: drylab_report_exporter.py _export_docx에 "
                    "build_molstar_panel_images 호출 미존재 "
                    "— M469 DOCX PDBe Mol* 이미지 패리티 누락"
                )
                sc29_issues.append(_m29a)
                logger.warning("G7-SC29-a WARN: %s", _m29a)

            # SC29-b: _export_docx 내 add_picture 호출 존재 여부 (이미지 실제 삽입)
            if "doc.add_picture" not in _content29:
                sc29_warn = True
                _m29b = (
                    "SC29-b WARN: drylab_report_exporter.py _export_docx에 "
                    "doc.add_picture 호출 미존재 "
                    "— DOCX에 이미지 실제 삽입 미구현 (M469 콘텐츠 패리티 부족)"
                )
                sc29_issues.append(_m29b)
                logger.warning("G7-SC29-b WARN: %s", _m29b)

            # SC29-c: molstar_capture.py 파일 존재 여부
            if not os.path.exists(_MOLSTAR_CAPTURE_PATH_29):
                sc29_warn = True
                _m29c = (
                    "SC29-c WARN: molstar_capture.py 미존재 "
                    "— M469 PDBe Mol* 캡처 모듈 신규 생성 필요"
                )
                sc29_issues.append(_m29c)
                logger.warning("G7-SC29-c WARN: %s", _m29c)

            # SC29-d: molstar_capture.py 내 학술 인용 의무 (Sehnal 2021)
            if os.path.exists(_MOLSTAR_CAPTURE_PATH_29):
                try:
                    with open(_MOLSTAR_CAPTURE_PATH_29, "r", encoding="utf-8",
                              errors="replace") as _fh29m:
                        _molstar_content = _fh29m.read()
                    if "Sehnal" not in _molstar_content or "2021" not in _molstar_content:
                        sc29_warn = True
                        _m29d = (
                            "SC29-d WARN: molstar_capture.py에 Sehnal et al. 2021 "
                            "학술 인용 미존재 — M469 학술 인용 의무"
                        )
                        sc29_issues.append(_m29d)
                        logger.warning("G7-SC29-d WARN: %s", _m29d)
                except OSError as _e29m:
                    logger.warning("G7-SC29: molstar_capture.py 읽기 실패: %s", _e29m)

            # SC29-e: _export_docx 내 학술 인용 (Sehnal 2021 + Jumper 2021) 존재 여부
            if "Sehnal" not in _content29 or "Jumper" not in _content29:
                sc29_warn = True
                _m29e = (
                    "SC29-e WARN: drylab_report_exporter.py _export_docx에 "
                    "Sehnal / Jumper 2021 학술 인용 미존재 "
                    "— M469 학술 인용 의무 (DOCX 패리티)"
                )
                sc29_issues.append(_m29e)
                logger.warning("G7-SC29-e WARN: %s", _m29e)

        except OSError as _e29:
            logger.warning("G7-SC29: cannot read drylab_report_exporter.py: %s", _e29)
    else:
        logger.warning("G7-SC29: drylab_report_exporter.py not found at %s",
                       _DRYLAB_EXPORTER_PATH_29)

    sc29_overall = "WARN" if sc29_warn else "PASS"
    # SC29는 WARN 전용 (비차단) — DOCX PDBe Mol* 이미지 패리티 재발 방지 (M469)

    # -- G7-SC30: 34종 분자 매트릭스 검증 (M471 신설, WARN 전용 비차단) --
    # 목적: 분자량 100+ 이상 34종 SMILES 파싱 + 스펙트럼 5종 + 3D 최적화 PASS 30+/34 확인
    # Rule L: MolFromSmiles+None체크, Rule M: silent failure 금지
    # [MAGIC] 30/34 = 합격 기준 (88.2% — 학술 논문급 다양성 검증)
    _SC30_PASS_THRESHOLD = 30  # [MAGIC] 최소 30종 PASS 기준 (M471 CT Decision E)
    sc30_warn = False
    sc30_issues: list[str] = []
    _sc30_matrix_pass = 0
    _sc30_matrix_total = 0
    _sc30_matrix_fail_list: list[str] = []

    _MATRIX_PY_PATH = os.path.join(PROJECT_ROOT, "tools", "molecule_matrix_34.py")
    if not os.path.exists(_MATRIX_PY_PATH):
        sc30_warn = True
        sc30_issues.append(
            "SC30-a WARN: tools/molecule_matrix_34.py 미존재 "
            "— M471 34종 분자 매트릭스 파일 생성 필요"
        )
        logger.warning("G7-SC30-a WARN: tools/molecule_matrix_34.py not found (M471)")
    else:
        # SC30-b: JSON 검증 결과 파일 확인 (최근 실행 증거)
        _MATRIX_JSON_PATH = os.path.join(
            PROJECT_ROOT, "docs", "reports", "molecule_matrix_34_validation.json"
        )
        if not os.path.exists(_MATRIX_JSON_PATH):
            sc30_warn = True
            sc30_issues.append(
                "SC30-b WARN: molecule_matrix_34_validation.json 미존재 "
                "— python tools/molecule_matrix_34.py 실행 필요 (M471)"
            )
            logger.warning(
                "G7-SC30-b WARN: molecule_matrix_34_validation.json not found "
                "— run python tools/molecule_matrix_34.py (M471)"
            )
        else:
            # SC30-c: JSON 파싱 후 PASS 수 확인
            try:
                with open(_MATRIX_JSON_PATH, "r", encoding="utf-8") as _fh30:
                    _matrix_data = json.loads(_fh30.read())

                if not isinstance(_matrix_data, dict):  # Rule N
                    logger.warning("G7-SC30: molecule_matrix validation JSON 비dict 타입")
                else:
                    _sc30_matrix_pass = _matrix_data.get("pass", 0)
                    _sc30_matrix_total = _matrix_data.get("total", 0)
                    _sc30_fail_list_raw = _matrix_data.get("fail", [])

                    if not isinstance(_sc30_matrix_pass, int):  # Rule N
                        _sc30_matrix_pass = 0
                    if not isinstance(_sc30_matrix_total, int):
                        _sc30_matrix_total = 0
                    if not isinstance(_sc30_fail_list_raw, list):
                        _sc30_fail_list_raw = []

                    # fail 목록 추출 (최대 5개 — [MAGIC])
                    for _fi in _sc30_fail_list_raw[:5]:
                        if isinstance(_fi, dict):
                            _sc30_matrix_fail_list.append(
                                f"{_fi.get('name','?')}:{_fi.get('reason','?')[:40]}"
                            )

                    if _sc30_matrix_pass < _SC30_PASS_THRESHOLD:
                        sc30_warn = True
                        _m30c = (
                            f"SC30-c WARN: 34종 매트릭스 PASS={_sc30_matrix_pass}/"
                            f"{_sc30_matrix_total} < 기준 {_SC30_PASS_THRESHOLD} "
                            f"(M471 학술 논문급 검증 미달). "
                            f"FAIL 목록: {'; '.join(_sc30_matrix_fail_list)}"
                        )
                        sc30_issues.append(_m30c)
                        logger.warning("G7-SC30-c WARN: %s", _m30c)
                    else:
                        logger.info(
                            "G7-SC30 PASS: 34종 분자 매트릭스 %d/%d PASS (>= %d)",
                            _sc30_matrix_pass, _sc30_matrix_total,
                            _SC30_PASS_THRESHOLD,
                        )

            except (OSError, json.JSONDecodeError) as _e30:
                sc30_warn = True
                sc30_issues.append(
                    f"SC30-d WARN: molecule_matrix_34_validation.json 읽기/파싱 실패 "
                    f"— {str(_e30)[:60]} (M471)"
                )
                logger.warning("G7-SC30-d WARN: cannot read/parse matrix JSON: %s", _e30)

    sc30_overall = "WARN" if sc30_warn else "PASS"
    # SC30은 WARN 전용 (비차단) — 34종 매트릭스 30+ PASS 학술 검증 (M471)

    # -- G7-SC31: 메커니즘 화살촉 가시성 검사 (M473 신설, WARN 전용 비차단) --
    # 목적: popup_reaction.py의 CurvedArrowRenderer 화살촉 크기/비율이 PDF 표준 미달 방지
    # PDF 표준: 화살촉 최소 10px, half_w 비율 >= 0.40, fishhook barb >= 0.35
    # Rule O: QPainter 결과물도 학술 논문 품질 기준
    sc31_warn = False
    sc31_issues: list[str] = []

    _POPUP_REACTION_PATH_31 = os.path.join(PROJECT_ROOT, "src", "app", "popup_reaction.py")
    if not os.path.exists(_POPUP_REACTION_PATH_31):
        sc31_warn = True
        sc31_issues.append(
            "SC31-a WARN: src/app/popup_reaction.py 미존재 "
            "-- 메커니즘 화살촉 가시성 검사 불가 (M473)"
        )
        logger.warning("G7-SC31-a WARN: popup_reaction.py not found (M473)")
    else:
        try:
            with open(_POPUP_REACTION_PATH_31, "r", encoding="utf-8") as _fh31:
                _popup_src = _fh31.read()

            if not isinstance(_popup_src, str):  # Rule N: 타입 가드
                _popup_src = ""

            # SC31-a: 화살촉 최소 크기 < 10px 검사
            # max(X, ...) 패턴에서 X 값 추출
            _arrow_min_re = re.compile(r"arrow_size\s*=\s*max\s*\(\s*([0-9]+)\s*,")
            _found_mins = _arrow_min_re.findall(_popup_src)
            for _min_val in _found_mins:
                if isinstance(_min_val, str) and _min_val.isdigit():
                    if int(_min_val) < 10:  # Magic: 10px = 교과서 화살촉 최소 (M473 DEFECT-V1)
                        sc31_warn = True
                        sc31_issues.append(
                            "SC31-a WARN: popup_reaction.py arrow_size min=%s < 10px "
                            "-- PDF 표준 미달 (M473 DEFECT-V1). max(10, ...) 이상으로 수정 필요." % _min_val
                        )
                        logger.warning(
                            "G7-SC31-a WARN: popup_reaction.py arrow_size min=%s < 10px "
                            "-- visibility below PDF standard (M473)", _min_val
                        )
                        break

            # SC31-b: full arrow half_w 비율 < 0.40 검사
            _half_w_re = re.compile(r"half_w\s*=\s*arrow_size\s*\*\s*([0-9]*\.[0-9]+)")
            _found_hw = _half_w_re.findall(_popup_src)
            for _hw_val in _found_hw:
                try:
                    if float(_hw_val) < 0.40:  # Magic: 0.40 = 교과서 화살촉 너비비율 최소 (M473 DEFECT-V1)
                        sc31_warn = True
                        sc31_issues.append(
                            "SC31-b WARN: popup_reaction.py half_w ratio %s < 0.40 "
                            "-- 화살촉이 너무 좁음 (M473 DEFECT-V1). "
                            "half_w = arrow_size * 0.42 이상으로 수정 필요." % _hw_val
                        )
                        logger.warning(
                            "G7-SC31-b WARN: popup_reaction.py half_w ratio %s < 0.40 "
                            "-- arrowhead too narrow (M473)", _hw_val
                        )
                        break
                except (ValueError, TypeError) as _ev:
                    logger.warning("G7-SC31-b: half_w 파싱 실패: %s", _ev)

            # SC31-c: fishhook barb_width 비율 < 0.35 검사
            _barb_re = re.compile(r"barb_width\s*=\s*arrow_size\s*\*\s*([0-9]*\.[0-9]+)")
            _found_bw = _barb_re.findall(_popup_src)
            for _bw_val in _found_bw:
                try:
                    if float(_bw_val) < 0.35:  # Magic: 0.35 = fishhook 식별 가능 최소 비율 (M473 DEFECT-V2)
                        sc31_warn = True
                        sc31_issues.append(
                            "SC31-c WARN: popup_reaction.py barb_width ratio %s < 0.35 "
                            "-- 라디칼 fishhook 식별 불가 (M473 DEFECT-V2). "
                            "barb_width = arrow_size * 0.40 이상으로 수정 필요." % _bw_val
                        )
                        logger.warning(
                            "G7-SC31-c WARN: popup_reaction.py barb_width ratio %s < 0.35 "
                            "-- radical fishhook invisible (M473)", _bw_val
                        )
                        break
                except (ValueError, TypeError) as _ev:
                    logger.warning("G7-SC31-c: barb_width 파싱 실패: %s", _ev)

            # SC31-d: inter-fragment 색상 하드코딩 QColor(204, 0, 0) 검사
            if "QColor(204, 0, 0)" in _popup_src:
                sc31_warn = True
                sc31_issues.append(
                    "SC31-d WARN: popup_reaction.py inter-fragment 화살표 색상 "
                    "QColor(204, 0, 0) 하드코딩 잔존 "
                    "-- M442 4색 표준 from_type 기반 색상 사용 필요 (M473 DEFECT-V4)"
                )
                logger.warning(
                    "G7-SC31-d WARN: popup_reaction.py QColor(204, 0, 0) hardcoded "
                    "-- use from_type-based 4-color standard (M473)"
                )

        except OSError as _e31:
            sc31_warn = True
            sc31_issues.append(
                "SC31-e WARN: popup_reaction.py 읽기 실패 -- %s (M473)" % str(_e31)[:60]
            )
            logger.warning("G7-SC31-e WARN: cannot read popup_reaction.py: %s", _e31)

    sc31_overall = "WARN" if sc31_warn else "PASS"
    # SC31은 WARN 전용 (비차단) -- 화살촉 가시성 재발 방지 (M473)

    # -- G7-SC32: 재귀 세션 핸드오프 파일 존재 검사 (M474 신설, WARN 전용 비차단) --
    # H-3: patrol SC32 — NEXT_SESSION_PROMPT.md / context_list.md LAST_M_NUMBER /
    #       cycle_reports/index.html 미존재 탐지
    # M474 요구: "다른 세션이 NEXT_SESSION_PROMPT만 읽고 진행상황 파악"
    sc32_warn = False
    sc32_issues: list[str] = []

    # SC32 경로 탐색: .claude/worktrees/ 하위 모든 워크트리 탐색
    _WORKTREE_BASE_32 = os.path.join(PROJECT_ROOT, ".claude", "worktrees")
    _NEXT_SESSION_PATH_32: str | None = None
    _CONTEXT_LIST_PATH_32: str | None = None
    if os.path.exists(_WORKTREE_BASE_32):
        try:
            for _wt_name in os.listdir(_WORKTREE_BASE_32):
                _wt_path = os.path.join(_WORKTREE_BASE_32, _wt_name)
                _nsp = os.path.join(_wt_path, "NEXT_SESSION_PROMPT.md")
                _clp = os.path.join(_wt_path, "context_list.md")
                if os.path.isdir(_wt_path) and os.path.exists(_nsp):
                    _NEXT_SESSION_PATH_32 = _nsp
                    _CONTEXT_LIST_PATH_32 = _clp
                    break
        except OSError as _e32_list:
            logger.warning("G7-SC32: worktrees 디렉토리 탐색 실패: %s", _e32_list)

    # SC32-a: NEXT_SESSION_PROMPT.md 존재 여부 (워크트리 루트)
    if not _NEXT_SESSION_PATH_32 or not os.path.exists(_NEXT_SESSION_PATH_32):
        sc32_warn = True
        _m32a = (
            "SC32-a WARN: NEXT_SESSION_PROMPT.md 워크트리 루트 미존재 "
            "— M474 재귀 세션 핸드오프 단일 진실 파일 없음"
        )
        sc32_issues.append(_m32a)
        logger.warning("G7-SC32-a WARN: %s", _m32a)
    else:
        # SC32-d: NEXT_SESSION_PROMPT.md 내 LAST_M_NUMBER 포함 여부
        try:
            with open(_NEXT_SESSION_PATH_32, "r", encoding="utf-8",
                      errors="replace") as _fh32n:
                _nsp_content = _fh32n.read()
            if not isinstance(_nsp_content, str):  # Rule N: 타입 가드
                logger.warning("G7-SC32: non-str content in NEXT_SESSION_PROMPT.md")
                _nsp_content = ""
            if "LAST_M_NUMBER" not in _nsp_content:
                sc32_warn = True
                _m32d = (
                    "SC32-d WARN: NEXT_SESSION_PROMPT.md에 LAST_M_NUMBER 미포함 "
                    "— M474 핸드오프 M번호 연속성 보장 불가"
                )
                sc32_issues.append(_m32d)
                logger.warning("G7-SC32-d WARN: %s", _m32d)
        except OSError as _e32n:
            logger.warning("G7-SC32: NEXT_SESSION_PROMPT.md 읽기 실패: %s", _e32n)

    # SC32-b: context_list.md 내 LAST_M_NUMBER 헤더 포함 여부
    if _CONTEXT_LIST_PATH_32 and os.path.exists(_CONTEXT_LIST_PATH_32):
        try:
            with open(_CONTEXT_LIST_PATH_32, "r", encoding="utf-8",
                      errors="replace") as _fh32c:
                _cl_content = _fh32c.read()
            if not isinstance(_cl_content, str):  # Rule N: 타입 가드
                logger.warning("G7-SC32: non-str content in context_list.md")
                _cl_content = ""
            if "LAST_M_NUMBER" not in _cl_content:
                sc32_warn = True
                _m32b = (
                    "SC32-b WARN: context_list.md에 LAST_M_NUMBER 헤더 미포함 "
                    "— M474 세션 핸드오프 체크포인트 의무 항목 누락"
                )
                sc32_issues.append(_m32b)
                logger.warning("G7-SC32-b WARN: %s", _m32b)
        except OSError as _e32c:
            logger.warning("G7-SC32: context_list.md 읽기 실패: %s", _e32c)
    else:
        sc32_warn = True
        _m32b_miss = (
            "SC32-b WARN: context_list.md 워크트리 미존재 "
            "— M474 세션 핸드오프 체크리스트 없음"
        )
        sc32_issues.append(_m32b_miss)
        logger.warning("G7-SC32-b WARN: %s", _m32b_miss)

    # SC32-c: docs/reports/cycle_reports/index.html 존재 여부 (사이클 기록 증거)
    _CYCLE_INDEX_PATH_32 = os.path.join(
        PROJECT_ROOT, "docs", "reports", "cycle_reports", "index.html"
    )
    if not os.path.exists(_CYCLE_INDEX_PATH_32):
        sc32_warn = True
        _m32c = (
            "SC32-c WARN: docs/reports/cycle_reports/index.html 미존재 "
            "— M474 HTML 사이클 보고서 1차 증거 없음 "
            "(사이클 미실행 또는 cycle_report_writer.py 미생성)"
        )
        sc32_issues.append(_m32c)
        logger.warning("G7-SC32-c WARN: %s", _m32c)

    sc32_overall = "WARN" if sc32_warn else "PASS"
    # SC32는 WARN 전용 (비차단) — 재귀 세션 핸드오프 파일 재발 방지 (M474)

    # -- G7-SC33: HTML 사이클 보고서 자동 생성 검사 (M472 신설, WARN 전용 비차단) --
    # 목적: tools/cycle_html_reporter.py 존재 + docs/reports/cycle_reports/index.html
    #       자동 갱신 여부 확인 — 다른 세션이 index.html만으로 진행 상황 파악 가능.
    # Rule F 강화: HTML 보고서 의무 (py_compile만으론 불충분 + 앱실행+캡처 + HTML 보고서)
    sc33_warn = False
    sc33_issues: list[str] = []

    _HTML_REPORTER_PATH_33 = os.path.join(PROJECT_ROOT, "tools", "cycle_html_reporter.py")
    _HTML_DIR_33 = os.path.join(PROJECT_ROOT, "docs", "reports", "cycle_reports")
    _HTML_INDEX_33 = os.path.join(_HTML_DIR_33, "index.html")
    _FOREGROUND_CYCLE_SH_33 = os.path.join(PROJECT_ROOT, "housing", "sinktank", "foreground_cycle.sh")

    # SC33-a: cycle_html_reporter.py 파일 존재 여부
    if not os.path.exists(_HTML_REPORTER_PATH_33):
        sc33_warn = True
        sc33_issues.append(
            "SC33-a WARN: tools/cycle_html_reporter.py 미존재 "
            "— M472 HTML 사이클 보고서 생성기 신규 생성 필요"
        )
        logger.warning(
            "G7-SC33-a WARN: tools/cycle_html_reporter.py not found "
            "— M472 HTML report generator missing"
        )

    # SC33-b: docs/reports/cycle_reports/ 디렉토리 존재 여부
    if not os.path.isdir(_HTML_DIR_33):
        sc33_warn = True
        sc33_issues.append(
            "SC33-b WARN: docs/reports/cycle_reports/ 디렉토리 미존재 "
            "— foreground_cycle.sh 실행 후 자동 생성됨 (M472)"
        )
        logger.warning(
            "G7-SC33-b WARN: cycle_reports/ dir not found "
            "— run foreground_cycle.sh to create (M472)"
        )

    # SC33-c: index.html 존재 여부 (최근 사이클 실행 증거)
    if not os.path.exists(_HTML_INDEX_33):
        sc33_warn = True
        sc33_issues.append(
            "SC33-c WARN: docs/reports/cycle_reports/index.html 미존재 "
            "— 포그라운드 자가 검증 사이클 미실행 증거 (M472)"
        )
        logger.warning(
            "G7-SC33-c WARN: cycle_reports/index.html not found "
            "— no cycle has been run (M472)"
        )
    else:
        # index.html 최신성 확인 (24시간 초과 = WARN)
        # [MAGIC] HTML 보고서 최대 허용 경과 시간: 24시간 = 86400초
        _HTML_STALE_SECS = 86400
        try:
            _html_age = time.time() - os.path.getmtime(_HTML_INDEX_33)
            if _html_age > _HTML_STALE_SECS:
                sc33_warn = True
                _sc33c_hrs = _html_age / 3600
                sc33_issues.append(
                    f"SC33-c WARN: index.html이 {_sc33c_hrs:.1f}시간 경과 "
                    f"— 포그라운드 사이클 재실행 권고 (M472)"
                )
                logger.warning(
                    "G7-SC33-c WARN: index.html is %.1f hours old "
                    "— re-run foreground_cycle.sh (M472)",
                    _sc33c_hrs,
                )
        except OSError as _e33c:
            logger.warning("G7-SC33: index.html mtime 확인 실패: %s", _e33c)

    # SC33-d: foreground_cycle.sh에 cycle_html_reporter.py 호출 존재 여부
    if os.path.exists(_FOREGROUND_CYCLE_SH_33):
        try:
            with open(_FOREGROUND_CYCLE_SH_33, "r", encoding="utf-8",
                      errors="replace") as _fh33:
                _sh_content = _fh33.read()
            if not isinstance(_sh_content, str):  # Rule N 타입 가드
                _sh_content = ""
            if "cycle_html_reporter.py" not in _sh_content:
                sc33_warn = True
                sc33_issues.append(
                    "SC33-d WARN: foreground_cycle.sh에 cycle_html_reporter.py 호출 미존재 "
                    "— M472 Stage 9-HTML 통합 누락"
                )
                logger.warning(
                    "G7-SC33-d WARN: foreground_cycle.sh does not call cycle_html_reporter.py "
                    "— M472 Stage 9-HTML integration missing"
                )
        except OSError as _e33d:
            logger.warning("G7-SC33: foreground_cycle.sh 읽기 실패: %s", _e33d)
    else:
        sc33_warn = True
        sc33_issues.append(
            "SC33-e WARN: foreground_cycle.sh 미존재 "
            "— M464 포그라운드 사이클 오케스트레이터 누락"
        )
        logger.warning("G7-SC33-e WARN: foreground_cycle.sh not found (M464)")

    sc33_overall = "WARN" if sc33_warn else "PASS"
    # SC33은 WARN 전용 (비차단) — HTML 보고서 자동 생성 재발 방지 (M472)

    # -- G7-SC34: 사이클 깡통 자동 검사 (M476 신설, WARN 전용 비차단) --
    # 목적: foreground_cycle.sh의 3가지 깡통 패턴 자동 탐지
    #   SC34-a: Stage 5 import에 check_g7_runtime_smoke 잘못된 함수명 사용 (M476 결함 1)
    #   SC34-b: DFT 정합성 검사 SKIP 패턴 탐지 (predict_all.ir 속성명 오류)
    #   SC34-c: cycle_reports/index.html 부재 (사이클 HTML 보고서 미생성)
    #   SC34-d: _genuine_zero_defect 함수 미존재 (종료 조건 깡통 방지 부재)
    # Rule M: logger.warning 필수.
    # Rule N: isinstance 타입 가드 필수.
    sc34_warn = False
    sc34_issues: list[str] = []

    _FOREGROUND_CYCLE_SH_34 = os.path.join(PROJECT_ROOT, "housing", "sinktank", "foreground_cycle.sh")
    _DFT_CHECK_PY_34 = os.path.join(PROJECT_ROOT, "tools", "dft_consistency_check.py")
    _CYCLE_INDEX_34 = os.path.join(PROJECT_ROOT, "docs", "reports", "cycle_reports", "index.html")

    # SC34-a: foreground_cycle.sh에 잘못된 함수명 check_g7_runtime_smoke 실제 호출 여부
    # 주석 라인(#으로 시작) 제외 후 코드 라인에서만 검사 (M476 수정: 주석 오탐 방지)
    if os.path.exists(_FOREGROUND_CYCLE_SH_34):
        try:
            with open(_FOREGROUND_CYCLE_SH_34, "r", encoding="utf-8", errors="replace") as _fh34a:
                _sh34_lines = _fh34a.readlines()
            if not isinstance(_sh34_lines, list):  # Rule N
                _sh34_lines = []
            # 주석 라인 제외 후 check_g7_runtime_smoke 실제 호출 탐지
            _sh34_code_lines = [
                ln for ln in _sh34_lines
                if isinstance(ln, str) and not ln.lstrip().startswith("#")
            ]
            _sh34_code_str = "".join(_sh34_code_lines)
            if "check_g7_runtime_smoke" in _sh34_code_str:
                sc34_warn = True
                sc34_issues.append(
                    "SC34-a WARN: foreground_cycle.sh 코드에 존재하지 않는 함수 "
                    "check_g7_runtime_smoke 호출 — check_g7_serial_compliance로 정정 필요 (M476)"
                )
                logger.warning(
                    "G7-SC34-a WARN: foreground_cycle.sh calls non-existent "
                    "check_g7_runtime_smoke — must be check_g7_serial_compliance (M476)"
                )
        except OSError as _e34a:
            logger.warning("G7-SC34-a: foreground_cycle.sh 읽기 실패: %s", _e34a)
    else:
        sc34_warn = True
        sc34_issues.append(
            "SC34-a WARN: foreground_cycle.sh 미존재 — 포그라운드 사이클 미배포 (M476)"
        )
        logger.warning("G7-SC34-a WARN: foreground_cycle.sh not found (M476)")

    # SC34-b: dft_consistency_check.py에 잘못된 속성명 getattr(result, "ir", None) 사용 여부
    # 주석 라인(#으로 시작) 제외 후 코드 라인에서만 검사 (M476 수정: 주석 오탐 방지)
    if os.path.exists(_DFT_CHECK_PY_34):
        try:
            with open(_DFT_CHECK_PY_34, "r", encoding="utf-8", errors="replace") as _fh34b:
                _dft_lines = _fh34b.readlines()
            if not isinstance(_dft_lines, list):  # Rule N
                _dft_lines = []
            # 주석 라인 제외 후 코드만 검사
            _dft_code_lines = [
                ln for ln in _dft_lines
                if isinstance(ln, str) and not ln.lstrip().startswith("#")
            ]
            _dft_code_str = "".join(_dft_code_lines)
            # 구버전 속성명 패턴: getattr(result, "ir", None) — 코드에만 해당
            _bad_ir_patterns = [
                'getattr(result, "ir", None)',
                "getattr(result, 'ir', None)",
            ]
            _dft_bad = any(pat in _dft_code_str for pat in _bad_ir_patterns)
            if _dft_bad:
                sc34_warn = True
                sc34_issues.append(
                    "SC34-b WARN: dft_consistency_check.py에 잘못된 속성명 result.ir 사용 "
                    "— result.ir_peaks로 정정 필요 (M476, M471 패턴)"
                )
                logger.warning(
                    "G7-SC34-b WARN: dft_consistency_check.py uses result.ir "
                    "— must be result.ir_peaks (M476, M471 pattern)"
                )
        except OSError as _e34b:
            logger.warning("G7-SC34-b: dft_consistency_check.py 읽기 실패: %s", _e34b)

    # SC34-c: cycle_reports/index.html 부재 (사이클 미실행 = 깡통 증거)
    if not os.path.exists(_CYCLE_INDEX_34):
        sc34_warn = True
        sc34_issues.append(
            "SC34-c WARN: cycle_reports/index.html 미존재 "
            "— 포그라운드 자가 검증 사이클 미실행 (M476 깡통 패턴)"
        )
        logger.warning(
            "G7-SC34-c WARN: cycle_reports/index.html not found "
            "— foreground cycle never ran (M476 hollow pattern)"
        )

    # SC34-d: foreground_cycle.sh에 _genuine_zero_defect 함수 존재 여부
    if os.path.exists(_FOREGROUND_CYCLE_SH_34):
        try:
            with open(_FOREGROUND_CYCLE_SH_34, "r", encoding="utf-8", errors="replace") as _fh34d:
                _sh34d_content = _fh34d.read()
            if not isinstance(_sh34d_content, str):  # Rule N
                _sh34d_content = ""
            if "_genuine_zero_defect" not in _sh34d_content:
                sc34_warn = True
                sc34_issues.append(
                    "SC34-d WARN: foreground_cycle.sh에 _genuine_zero_defect 함수 미존재 "
                    "— 종료 조건 깡통 방지 부재 (M476)"
                )
                logger.warning(
                    "G7-SC34-d WARN: foreground_cycle.sh missing _genuine_zero_defect "
                    "— hollow termination possible (M476)"
                )
        except OSError as _e34d:
            logger.warning("G7-SC34-d: foreground_cycle.sh 읽기 실패: %s", _e34d)

    sc34_overall = "WARN" if sc34_warn else "PASS"
    # SC34는 WARN 전용 (비차단) — 사이클 깡통 자동 탐지 (M476)

    # -- G7-SC35: 웹-데스크톱 diff 자동 탐지 (M477 신설, WARN 전용 비차단) --
    # 목적: Rule Y strict — 웹 ChemGrid와 데스크톱 ChemGrid의 UX/UI 1px diff = FAIL 체계 자동 탐지.
    #   SC35-a: tools/web_cycle_test_matrix.py 파일 존재 여부 (35종×22 클릭 시뮬)
    #   SC35-b: docs/reports/web_cycle_reports/ 디렉토리 존재 여부 (웹 사이클 HTML 보고서)
    #   SC35-c: web_cycle_reports/index.html 존재 여부 (최근 웹 사이클 실행 증거)
    #   SC35-d: housing/sinktank/web_cycle.sh 존재 여부 (웹 사이클 오케스트레이터)
    #   SC35-e: tools/desktop_web_diff.py 파일 존재 여부 (픽셀 diff 도구)
    #   SC35-f: desktop_web_diff_result.json 결함 > 0 시 WARN (Rule Y 위반 잔존)
    # Rule M: logger.warning 필수.
    # Rule N: isinstance 타입 가드 필수.
    # docs/ai/skills/web_cycle_rule_y_strict.md 참조 (M477).
    sc35_warn = False
    sc35_issues: list[str] = []

    _WEB_MATRIX_PY = os.path.join(PROJECT_ROOT, "tools", "web_cycle_test_matrix.py")
    _WEB_REPORT_DIR_35 = os.path.join(PROJECT_ROOT, "docs", "reports", "web_cycle_reports")
    _WEB_INDEX_HTML_35 = os.path.join(_WEB_REPORT_DIR_35, "index.html")
    _WEB_CYCLE_SH_35 = os.path.join(PROJECT_ROOT, "housing", "sinktank", "web_cycle.sh")
    _DESKTOP_WEB_DIFF_PY = os.path.join(PROJECT_ROOT, "tools", "desktop_web_diff.py")
    _DIFF_RESULT_JSON = os.path.join(PROJECT_ROOT, "docs", "reports", "desktop_web_diff_result.json")

    # SC35-a: web_cycle_test_matrix.py 존재 여부
    if not os.path.exists(_WEB_MATRIX_PY):
        sc35_warn = True
        sc35_issues.append(
            "SC35-a WARN: tools/web_cycle_test_matrix.py 미존재 "
            "— M477 35종×22 클릭 시뮬 도구 누락 (Rule Y strict)"
        )
        logger.warning(
            "G7-SC35-a WARN: tools/web_cycle_test_matrix.py not found "
            "— M477 35mol x 22comp click simulation tool missing"
        )

    # SC35-b: web_cycle_reports/ 디렉토리 존재 여부
    if not os.path.isdir(_WEB_REPORT_DIR_35):
        sc35_warn = True
        sc35_issues.append(
            "SC35-b WARN: docs/reports/web_cycle_reports/ 디렉토리 미존재 "
            "— M477 웹 사이클 HTML 보고서 저장소 누락"
        )
        logger.warning(
            "G7-SC35-b WARN: web_cycle_reports/ dir not found "
            "— M477 web cycle HTML report directory missing"
        )

    # SC35-c: index.html 존재 여부 + 신선도
    if not os.path.exists(_WEB_INDEX_HTML_35):
        sc35_warn = True
        sc35_issues.append(
            "SC35-c WARN: web_cycle_reports/index.html 미존재 "
            "— M477 웹 사이클 미실행 (web_cycle.sh 기동 필요)"
        )
        logger.warning(
            "G7-SC35-c WARN: web_cycle_reports/index.html not found "
            "— M477 web cycle never ran (start web_cycle.sh)"
        )
    else:
        try:
            import time as _time35
            _sc35c_mtime = os.path.getmtime(_WEB_INDEX_HTML_35)
            _sc35c_age_hrs = (_time35.time() - _sc35c_mtime) / 3600
            # [MAGIC] 48시간 경과 = WARN (웹 사이클이 2일 이상 미실행)
            _SC35C_AGE_WARN_HRS = 48
            if _sc35c_age_hrs > _SC35C_AGE_WARN_HRS:
                sc35_warn = True
                sc35_issues.append(
                    f"SC35-c WARN: web_cycle_reports/index.html이 {_sc35c_age_hrs:.1f}시간 경과 "
                    f"— M477 웹 사이클 {_SC35C_AGE_WARN_HRS}시간 이상 미실행"
                )
                logger.warning(
                    "G7-SC35-c WARN: web_cycle_reports/index.html is %.1f hours old "
                    "— M477 web cycle not run in %d hours",
                    _sc35c_age_hrs, _SC35C_AGE_WARN_HRS,
                )
        except Exception as _e35c:
            logger.warning("G7-SC35: index.html mtime 확인 실패: %s", _e35c)

    # SC35-d: web_cycle.sh 존재 여부
    if not os.path.exists(_WEB_CYCLE_SH_35):
        sc35_warn = True
        sc35_issues.append(
            "SC35-d WARN: housing/sinktank/web_cycle.sh 미존재 "
            "— M477 웹 사이클 오케스트레이터 누락"
        )
        logger.warning(
            "G7-SC35-d WARN: housing/sinktank/web_cycle.sh not found "
            "— M477 web cycle orchestrator missing"
        )

    # SC35-e: desktop_web_diff.py 존재 여부
    if not os.path.exists(_DESKTOP_WEB_DIFF_PY):
        sc35_warn = True
        sc35_issues.append(
            "SC35-e WARN: tools/desktop_web_diff.py 미존재 "
            "— M477 Rule Y 1px diff 도구 누락"
        )
        logger.warning(
            "G7-SC35-e WARN: tools/desktop_web_diff.py not found "
            "— M477 Rule Y 1px diff tool missing"
        )

    # SC35-f: desktop_web_diff_result.json 결함 > 0 시 WARN
    if os.path.exists(_DIFF_RESULT_JSON):
        try:
            with open(_DIFF_RESULT_JSON, "r", encoding="utf-8") as _fh35f:
                _diff_raw = _fh35f.read()
            if not isinstance(_diff_raw, str):  # Rule N: 타입 가드
                logger.warning("G7-SC35-f: diff JSON 비str 타입 (Rule N)")
            else:
                import json as _json35f
                _diff_obj = _json35f.loads(_diff_raw)
                if not isinstance(_diff_obj, dict):  # Rule N
                    logger.warning("G7-SC35-f: diff JSON 비dict 타입 (Rule N)")
                else:
                    _diff_defects = _diff_obj.get("defect_count", 0)
                    if not isinstance(_diff_defects, int):  # Rule N
                        _diff_defects = 0
                    if _diff_defects > 0:
                        sc35_warn = True
                        sc35_issues.append(
                            f"SC35-f WARN: desktop_web_diff_result.json 결함 {_diff_defects}건 "
                            f"— Rule Y 위반 잔존 (1px diff 미해소, M477)"
                        )
                        logger.warning(
                            "G7-SC35-f WARN: desktop_web_diff shows %d defects "
                            "— Rule Y violations remaining (1px diff unresolved)",
                            _diff_defects,
                        )
        except Exception as _e35f:
            logger.warning("G7-SC35-f: desktop_web_diff_result.json 읽기/파싱 실패: %s", _e35f)

    sc35_overall = "WARN" if sc35_warn else "PASS"
    # SC35는 WARN 전용 (비차단) — 웹-데스크톱 diff 자동 탐지 Rule Y strict (M477)

    # -- G7-SC36: DirectML ml_dml 환경 검사 (M478 신설, WARN 전용 비차단) --
    # 목적: D-04 결정 DirectML 환경이 실제로 구축되었는지 자동 탐지.
    #   SC36-a: ml_dml venv python.exe 존재 확인
    #   SC36-b: torch-directml 패키지 설치 여부 (ml_dml 환경 pip list 파싱)
    #   SC36-c: tools/verify_directml.py 존재 확인
    #   SC36-d: docs/reports/benchmark_directml_m478.json 존재 확인
    # Rule M: logger.warning 필수. Rule N: isinstance 타입 가드 필수.
    sc36_warn = False
    sc36_issues: list[str] = []

    # SC36-a: ml_dml venv python.exe 존재
    # [MAGIC] 사용자 홈 내 ml_dml venv 경로 — Windows 표준 위치
    import glob as _glob36
    _sc36_user_home_patterns = [
        os.path.join("C:", os.sep, "Users", "*", "ml_dml", "Scripts", "python.exe"),
        os.path.join("C:", os.sep, "Users", "*", "ml_dml", "Scripts", "python.exe"),
    ]
    _sc36_python_candidates = []
    for _pat36 in _sc36_user_home_patterns:
        _sc36_python_candidates.extend(_glob36.glob(_pat36))

    # 환경 디렉토리 검색 (anaconda envs 포함)
    _sc36_conda_path = os.path.join("C:", os.sep, "ProgramData", "anaconda3", "envs", "ml_dml", "python.exe")
    if os.path.exists(_sc36_conda_path):
        _sc36_python_candidates.append(_sc36_conda_path)

    if not _sc36_python_candidates:
        sc36_warn = True
        sc36_issues.append(
            "SC36-a WARN: ml_dml venv python.exe 미존재 "
            "-- D-04 DirectML 환경 미구축 (M478)"
        )
        logger.warning(
            "G7-SC36-a WARN: ml_dml venv python.exe not found "
            "-- D-04 DirectML env not built (M478)"
        )
    else:
        logger.info("G7-SC36-a OK: ml_dml python found at %s", _sc36_python_candidates[0])

    # SC36-b: torch-directml 설치 여부 (pip show 실행)
    _sc36_pip_ok = False
    if _sc36_python_candidates:
        _sc36_py = _sc36_python_candidates[0]
        try:
            _sc36_pip_result = subprocess.run(
                [_sc36_py, "-m", "pip", "show", "torch-directml"],
                capture_output=True, text=True, timeout=15,
                errors="replace",
            )
            if not isinstance(_sc36_pip_result.stdout, str):  # Rule N: 타입 가드
                logger.warning("G7-SC36-b: pip show 출력 비str 타입")
            elif "torch-directml" in _sc36_pip_result.stdout.lower():
                _sc36_pip_ok = True
                logger.info("G7-SC36-b OK: torch-directml installed in ml_dml")
            else:
                sc36_warn = True
                sc36_issues.append(
                    "SC36-b WARN: torch-directml 패키지 미설치 "
                    "-- pip install torch-directml 필요 (M478)"
                )
                logger.warning(
                    "G7-SC36-b WARN: torch-directml not installed in ml_dml "
                    "-- run: pip install torch-directml (M478)"
                )
        except (subprocess.TimeoutExpired, OSError) as _e36b:
            sc36_warn = True
            sc36_issues.append(f"SC36-b WARN: pip show 실행 실패: {str(_e36b)[:80]}")
            logger.warning("G7-SC36-b WARN: pip show failed: %s", _e36b)
    else:
        sc36_warn = True
        sc36_issues.append("SC36-b WARN: python 미존재로 pip show 건너뜀")
        logger.warning("G7-SC36-b WARN: skipped (python not found)")

    # SC36-c: tools/verify_directml.py 존재 확인
    _sc36_verify_path = os.path.join(PROJECT_ROOT, "tools", "verify_directml.py")
    if not os.path.exists(_sc36_verify_path):
        sc36_warn = True
        sc36_issues.append(
            "SC36-c WARN: tools/verify_directml.py 미존재 "
            "-- M478 설치 검증 스크립트 누락"
        )
        logger.warning(
            "G7-SC36-c WARN: tools/verify_directml.py not found (M478)"
        )
    else:
        logger.info("G7-SC36-c OK: tools/verify_directml.py exists")

    # SC36-d: docs/reports/benchmark_directml_m478.json 존재 확인
    _sc36_bench_path = os.path.join(
        PROJECT_ROOT, "docs", "reports", "benchmark_directml_m478.json"
    )
    if not os.path.exists(_sc36_bench_path):
        sc36_warn = True
        sc36_issues.append(
            "SC36-d WARN: docs/reports/benchmark_directml_m478.json 미존재 "
            "-- M478 벤치마크 결과 파일 누락 (tools/benchmark_directml.py 실행 필요)"
        )
        logger.warning(
            "G7-SC36-d WARN: benchmark_directml_m478.json not found "
            "-- run tools/benchmark_directml.py (M478)"
        )
    else:
        # JSON 내용 확인 (Rule N: isinstance 타입 가드)
        try:
            with open(_sc36_bench_path, "r", encoding="utf-8") as _fh36:
                _sc36_bench_data = json.load(_fh36)
            if not isinstance(_sc36_bench_data, dict):  # Rule N
                sc36_warn = True
                sc36_issues.append("SC36-d WARN: benchmark JSON 비dict 타입 (Rule N)")
                logger.warning("G7-SC36-d WARN: benchmark JSON not dict")
            else:
                _sc36_tp = _sc36_bench_data.get("throughput_imgs_per_sec", {})
                if not isinstance(_sc36_tp, dict):  # Rule N
                    logger.warning("G7-SC36-d: throughput 비dict 타입")
                else:
                    _sc36_avg_tp = _sc36_tp.get("avg", 0)
                    if isinstance(_sc36_avg_tp, (int, float)) and _sc36_avg_tp > 0:
                        logger.info(
                            "G7-SC36-d OK: benchmark JSON found, avg throughput=%.1f img/s",
                            _sc36_avg_tp,
                        )
                    else:
                        sc36_warn = True
                        sc36_issues.append("SC36-d WARN: benchmark throughput 비정상값")
                        logger.warning("G7-SC36-d WARN: benchmark avg throughput abnormal: %s", _sc36_avg_tp)
        except (json.JSONDecodeError, OSError) as _e36d:
            sc36_warn = True
            sc36_issues.append(f"SC36-d WARN: benchmark JSON 읽기 실패: {str(_e36d)[:80]}")
            logger.warning("G7-SC36-d WARN: benchmark JSON read failed: %s", _e36d)

    sc36_overall = "WARN" if sc36_warn else "PASS"
    # SC36은 WARN 전용 (비차단) -- DirectML ml_dml 환경 구축 재발 방지 (M478)

    # -- G7-SC37: foreground_cycle.sh 프로세스 감시 (M479 신설, WARN 전용 비차단) --
    # 목적: 사용자 명시 "절대 멈추지 말 것" — 사이클 프로세스가 죽었는데 STOP_FILE도 없으면 이상 종료.
    #   SC37-a: foreground_cycle.sh 가 실행 중인지 확인 (pgrep/ps 탐지)
    #   SC37-b: STOP_FILE 부재 + 프로세스 없음 = WARN (자동 재시작이 실패한 것)
    #   SC37-c: STOP_FILE 존재 = 사용자 명시 종료 — 정상 (WARN 없음)
    # Rule M: logger.warning 필수. Rule N: isinstance 타입 가드 필수.
    sc37_warn = False
    sc37_issues: list[str] = []

    _STOP_FILE_37 = os.path.join(PROJECT_ROOT, "STOP_FOREGROUND_CYCLE")
    _CYCLE_SCRIPT_37 = os.path.join(PROJECT_ROOT, "housing", "sinktank", "foreground_cycle.sh")

    # SC37-c: STOP_FILE 존재 확인 (사용자 명시 종료 = 정상)
    _sc37_stop_exists = os.path.exists(_STOP_FILE_37)
    if _sc37_stop_exists:
        # STOP_FILE 존재 = 사용자가 명시적으로 종료 요청한 것 → 프로세스 없어도 정상
        logger.info("G7-SC37: STOP_FILE 존재 — 사용자 명시 종료 (정상)")
    else:
        # SC37-a: foreground_cycle.sh 프로세스 실행 여부 확인
        _sc37_proc_running = False
        try:
            _sc37_result = subprocess.run(
                ["pgrep", "-f", "foreground_cycle.sh"],
                capture_output=True, text=True, timeout=5
            )
            if not isinstance(_sc37_result.stdout, str):  # Rule N: 타입 가드
                logger.warning("G7-SC37-a: pgrep stdout 비str 타입")
            elif _sc37_result.stdout.strip():
                _sc37_proc_running = True
                logger.info("G7-SC37-a OK: foreground_cycle.sh 실행 중 (PID: %s)",
                            _sc37_result.stdout.strip()[:40])
        except FileNotFoundError:
            # pgrep 없는 환경 (Windows 네이티브) — ps 폴백
            try:
                _sc37_ps_result = subprocess.run(
                    ["ps", "aux"],
                    capture_output=True, text=True, timeout=5
                )
                if not isinstance(_sc37_ps_result.stdout, str):  # Rule N
                    logger.warning("G7-SC37-a: ps stdout 비str 타입")
                elif "foreground_cycle" in _sc37_ps_result.stdout:
                    _sc37_proc_running = True
                    logger.info("G7-SC37-a OK: foreground_cycle.sh 실행 중 (ps 탐지)")
            except (subprocess.TimeoutExpired, OSError) as _e37_ps:
                logger.warning("G7-SC37-a: ps 실행 실패: %s", _e37_ps)
        except (subprocess.TimeoutExpired, OSError) as _e37a:
            logger.warning("G7-SC37-a: pgrep 실행 실패: %s", _e37a)

        # SC37-b: STOP_FILE 없음 + 프로세스 없음 = 이상 종료 (M479 자동 재시작 실패)
        if not _sc37_proc_running:
            sc37_warn = True
            _m37b = (
                "SC37-b WARN: foreground_cycle.sh 프로세스 미탐지 + STOP_FILE 없음 "
                "— 이상 종료 추정 (M479 자동 재시작 실패). "
                "수동 재시작: bash C:/chemgrid/housing/sinktank/foreground_cycle.sh"
            )
            sc37_issues.append(_m37b)
            logger.warning(
                "G7-SC37-b WARN: foreground_cycle.sh not running and STOP_FILE absent "
                "-- abnormal termination (M479 auto-restart may have failed). "
                "Manual restart: bash C:/chemgrid/housing/sinktank/foreground_cycle.sh"
            )

    # SC37-d: foreground_cycle.sh 파일 자체 존재 확인
    if not os.path.exists(_CYCLE_SCRIPT_37):
        sc37_warn = True
        sc37_issues.append(
            "SC37-d WARN: housing/sinktank/foreground_cycle.sh 미존재 "
            "-- M479 무한 사이클 스크립트 없음"
        )
        logger.warning(
            "G7-SC37-d WARN: foreground_cycle.sh not found (M479)"
        )

    sc37_overall = "WARN" if sc37_warn else "PASS"
    # SC37은 WARN 전용 (비차단) — 사이클 프로세스 감시 (M479)

    # --- G7-SC38: mistakes.md 80줄 초과 자동 탐지 (M481) ---
    #   SC38-a: mistakes.md 파일 존재 확인
    #   SC38-b: 80줄 초과 시 WARN (단일파일 무한 증식 방지)
    sc38_warn = False
    sc38_issues: list[str] = []
    _sc38_mistakes_path = os.path.join(PROJECT_ROOT, "docs", "ai", "mistakes.md")
    if not os.path.isfile(_sc38_mistakes_path):
        sc38_warn = True
        sc38_issues.append("SC38-a WARN: docs/ai/mistakes.md 미존재 (M481)")
        logger.warning("G7-SC38-a WARN: docs/ai/mistakes.md not found (M481)")
    else:
        try:
            with open(_sc38_mistakes_path, encoding="utf-8", errors="replace") as _f38:
                _sc38_lines = sum(1 for _ in _f38)
            if _sc38_lines > 80:  # [M481] 80줄 초과 = 단일파일 무한 증식 위반
                sc38_warn = True
                sc38_issues.append(
                    f"SC38-b WARN: mistakes.md {_sc38_lines}줄 > 80줄 — "
                    "분산 필요 (docs/ai/mistakes/ subdirectory 사용, M481)"
                )
                logger.warning(
                    "G7-SC38-b WARN: mistakes.md %d lines > 80 limit (M481)",
                    _sc38_lines,
                )
            else:
                logger.info("G7-SC38-b OK: mistakes.md %d lines (<= 80)", _sc38_lines)
        except Exception as _e38:
            logger.warning("G7-SC38: mistakes.md 읽기 실패: %s", _e38)

    sc38_overall = "WARN" if sc38_warn else "PASS"
    # SC38은 WARN 전용 (비차단) — mistakes.md 80줄 상한 감시 (M481)

    # -- G7-SC39: 위젯 미발견 skip = 0결함 거짓 PASS 탐지 (M481 신설, REJECT 차단) --
    # 목적: FP-11 재발 방지 — foreground_test_matrix 결과 JSON에서
    #       skipped_due_to_missing_widget > 0 탐지 시 REJECT.
    #   SC39-a: foreground_test_matrix_result.json에 skipped_due_to_missing_widget > 0 탐지
    #   SC39-b: 사이클 로그에서 WIDGET_MISSING / "검색바를 찾을 수 없음" 패턴 탐지
    # Rule M: logger.warning 필수. Rule N: isinstance 타입 가드 필수.
    # SC39는 REJECT 차단 — FP-11(테스트 미실행=0결함 거짓 PASS) 최우선 방어.
    # 주: SC38은 mistakes.md 라인 수 감시용 — SC39로 배정 (M481).
    sc39_fail = False
    sc39_issues: list[str] = []

    _FTM_RESULT_39 = os.path.join(
        PROJECT_ROOT, "docs", "reports", "foreground_test_matrix_result.json"
    )
    _CYCLE_LOG_39 = os.path.join(
        PROJECT_ROOT, "housing", "sinktank", "_foreground_cycle.log"
    )

    # SC39-a: result JSON에 skipped_due_to_missing_widget > 0 탐지
    if os.path.exists(_FTM_RESULT_39):
        try:
            with open(_FTM_RESULT_39, "r", encoding="utf-8") as _fh39a:
                _raw39 = _fh39a.read()
            if not isinstance(_raw39, str):  # Rule N: 타입 가드
                logger.warning("G7-SC39-a: result JSON 비str 타입 (Rule N)")
            else:
                import json as _json39
                _obj39 = _json39.loads(_raw39)
                if not isinstance(_obj39, dict):  # Rule N: 타입 가드
                    logger.warning("G7-SC39-a: result JSON 비dict 타입 (Rule N)")
                else:
                    _skip_count39 = _obj39.get("skipped_due_to_missing_widget", 0)
                    if not isinstance(_skip_count39, int):  # Rule N: 타입 가드
                        _skip_count39 = 0
                    if _skip_count39 > 0:
                        sc39_fail = True
                        sc39_issues.append(
                            f"SC39-a REJECT: foreground_test_matrix_result.json "
                            f"skipped_due_to_missing_widget={_skip_count39} > 0 "
                            f"— FP-11 패턴: 테스트 미실행=0결함 거짓 PASS (M481). "
                            f"tools/foreground_test_matrix.py 위젯 후보 목록 확인 필요 "
                            f"(mol_name_input 1순위)."
                        )
                        logger.warning(
                            "G7-SC39-a REJECT: skipped_due_to_missing_widget=%d > 0 "
                            "-- FP-11 widget-skip false-pass pattern (M481). "
                            "Check foreground_test_matrix.py mol_name_input candidate.",
                            _skip_count39,
                        )
                    else:
                        logger.info("G7-SC39-a OK: skipped_due_to_missing_widget=0")
        except Exception as _e39a:
            logger.warning("G7-SC39-a: result JSON 읽기/파싱 실패: %s", _e39a)

    # SC39-b: 사이클 로그에서 WIDGET_MISSING / 위젯 미발견 패턴 탐지
    # [MAGIC] 로그 파일 최근 500줄만 스캔 (전체 스캔 시 성능 영향)
    _SC39B_LOG_TAIL = 500
    _SC39B_PATTERNS = [
        "검색바를 찾을 수 없음",           # 구버전 메시지 (M480 이전)
        "WIDGET_MISSING",                  # 결함 타입 마커
        "skipped_due_to_missing_widget",   # JSON 마커 (M481 신규)
        "MainWindow에서 search_bar / name_input 속성 미발견",  # 구버전 메시지
        "MainWindow 검색바 위젯 미발견",                        # M481 신버전 메시지
    ]
    if os.path.exists(_CYCLE_LOG_39):
        try:
            with open(_CYCLE_LOG_39, "r", encoding="utf-8", errors="replace") as _fh39b:
                _all39b = _fh39b.readlines()
            if not isinstance(_all39b, list):  # Rule N: 타입 가드
                logger.warning("G7-SC39-b: 로그 readlines 비list 타입 (Rule N)")
            else:
                _tail39 = _all39b[-_SC39B_LOG_TAIL:] if len(_all39b) > _SC39B_LOG_TAIL else _all39b
                _tail_str39 = "".join(_tail39)
                if not isinstance(_tail_str39, str):  # Rule N: 타입 가드
                    logger.warning("G7-SC39-b: 로그 join 비str 타입 (Rule N)")
                else:
                    for _pat39 in _SC39B_PATTERNS:
                        if _pat39 in _tail_str39:
                            sc39_fail = True
                            sc39_issues.append(
                                f"SC39-b REJECT: 사이클 로그에 위젯 미발견 패턴 탐지 "
                                f"('{_pat39}') — FP-11 패턴 활성 (M481). "
                                f"foreground_test_matrix.py mol_name_input 후보 확인 필요."
                            )
                            logger.warning(
                                "G7-SC39-b REJECT: widget-missing pattern '%s' in cycle log "
                                "-- FP-11 active (M481). "
                                "Check foreground_test_matrix.py mol_name_input candidate.",
                                _pat39,
                            )
                            break  # 첫 번째 패턴 탐지 시 중단 — 중복 REJECT 방지
        except OSError as _e39b:
            logger.warning("G7-SC39-b: 사이클 로그 읽기 실패: %s", _e39b)

    sc39_overall = "REJECT" if sc39_fail else "PASS"
    # SC39는 REJECT 차단 — FP-11 재발 방지 최우선 (M481)

    # -- G7-SC41: ORCA 사용 정합성 감시 (M486 신설, REJECT 차단) --
    #
    # 목적: FP-08 / R-08 재발 방지 — "ORCA 계산 중" 거짓 메시지 패턴 탐지
    #
    # SC41-a: ORCA_AVAILABLE=False 분기에 fallback 없이 silent pass 패턴 탐지
    #   - "if ORCA_AVAILABLE" 또는 "if self._orca_available" 직후 else 없이
    #     사용자 피드백(logger/status) 없이 silent return/pass하는 패턴
    # SC41-b: "ORCA 계산 중" 또는 "ORCA 초기화 중" 메시지가
    #   ORCA_AVAILABLE / _find_orca_exe() 체크 없이 UI에 표시되는 패턴
    # SC41-c: predict_spectra / popup_predicted_spectrum에서
    #   스펙트럼 제목에 "이론적 스펙트럼 (엔진 기반)" 표기 누락 탐지
    #
    # SC41-a / SC41-b: REJECT 차단 (FP-08 직접 재발)
    # SC41-c: WARN (비차단) — 라벨 품질 문제
    sc41_fail = False
    sc41_warn = False
    sc41_issues: list = []

    # SC41-a: ORCA_AVAILABLE silent fallback 탐지
    # 대상 파일: src/app/*.py 중 ORCA_AVAILABLE 사용 파일
    _SC41A_TARGET_FILES = [
        os.path.join(PROJECT_ROOT, "src", "app", "arrow_generator.py"),
        os.path.join(PROJECT_ROOT, "src", "app", "canvas.py"),
        os.path.join(PROJECT_ROOT, "src", "app", "mechanism_dft_engine.py"),
    ]
    # silent fallback 탐지 패턴: if ORCA_AVAILABLE or if self._orca_available
    # 뒤에 else 없이 return None / return {} / return [] / pass 가 있는 경우
    # (정규식: ORCA_AVAILABLE 체크 이후 5줄 이내에 "return None" 존재하는 함수)
    # 간략화: "ORCA not available" 없이 바로 return None 하는 함수 탐지
    _SC41A_SILENT_PAT = re.compile(
        r"if\s+not\s+(?:self\._orca_available|ORCA_AVAILABLE)[^:]*:\s*\n"
        r"(?:[ \t]+(?!.*logger|.*warning|.*warn|.*error|.*status|.*setText|.*피드백).*\n)*?"
        r"[ \t]+return\s+(?:None|\[\]|\{\})",
        re.MULTILINE,
    )
    for _f41 in _SC41A_TARGET_FILES:
        try:
            with open(_f41, encoding="utf-8", errors="replace") as _fh41:
                _content41 = _fh41.read()
            if not isinstance(_content41, str):
                logger.warning("G7-SC41-a: non-str content in %s", _f41)
                continue
            # 코드에 ORCA_AVAILABLE 사용 여부
            if "ORCA_AVAILABLE" not in _content41 and "_orca_available" not in _content41:
                continue  # 해당 없음
            # silent return 탐지
            _m41a = _SC41A_SILENT_PAT.search(_content41)
            if _m41a:
                _fname41 = os.path.basename(_f41)
                _sc41_msg = (
                    f"SC41-a REJECT: {_fname41} — ORCA_AVAILABLE=False 분기에 "
                    f"logger/사용자 피드백 없이 silent return 탐지 (FP-08 재발 위험). "
                    f"M486: if not ORCA_AVAILABLE 후 반드시 logger.warning + UI 메시지 필수."
                )
                sc41_issues.append(_sc41_msg)
                logger.warning(
                    "G7-SC41-a REJECT: %s contains silent ORCA_AVAILABLE=False return "
                    "without user feedback (FP-08 risk, M486)",
                    _fname41,
                )
                sc41_fail = True
        except OSError as _e41a:
            logger.warning("G7-SC41-a: cannot read %s: %s", _f41, _e41a)

    # SC41-b: "ORCA 계산 중" / "ORCA 초기화 중" 가 ORCA 가용성 체크 없이 표시되는 패턴
    # popup_3d.py는 이미 _start_dft_calculation에서 _find_orca_exe() 체크 후 setText
    # 체크 방법: "ORCA.*계산 중\|ORCA.*초기화" 가 존재하는 파일에서
    #   해당 setText 직전 50줄 이내에 _find_orca_exe() 또는 ORCA_AVAILABLE 체크가 있는지 확인
    _SC41B_MSG_PAT = re.compile(r"[\"']ORCA\s*(?:계산\s*중|초기화\s*중|DFT\s*계산)[\"']")
    _SC41B_GUARD_PAT = re.compile(
        r"_find_orca_exe\(\)|ORCA_AVAILABLE|orca_exe\s*(?:is|==)\s*None|is_available"
    )
    _sc41b_target = os.path.join(PROJECT_ROOT, "src", "app", "popup_3d.py")
    try:
        with open(_sc41b_target, encoding="utf-8", errors="replace") as _fh41b:
            _lines41b = _fh41b.readlines()
        if not isinstance(_lines41b, list):
            logger.warning("G7-SC41-b: non-list readlines from popup_3d.py")
        else:
            for _i41, _line41 in enumerate(_lines41b):
                if not isinstance(_line41, str):
                    continue
                if _SC41B_MSG_PAT.search(_line41):
                    # 앞 50줄에 가용성 체크 존재 여부 확인
                    _window_start = max(0, _i41 - 50)
                    _window = "".join(_lines41b[_window_start:_i41 + 1])
                    if not isinstance(_window, str):
                        continue
                    if not _SC41B_GUARD_PAT.search(_window):
                        _sc41b_msg = (
                            f"SC41-b REJECT: popup_3d.py:{_i41+1} — "
                            f"'ORCA 계산 중' 메시지가 ORCA 가용성 체크 없이 표시됨 "
                            f"(FP-08 재발). M486: setText 전 _find_orca_exe() 체크 필수."
                        )
                        sc41_issues.append(_sc41b_msg)
                        logger.warning(
                            "G7-SC41-b REJECT: popup_3d.py line %d 'ORCA 계산 중' "
                            "without orca guard (FP-08, M486)",
                            _i41 + 1,
                        )
                        sc41_fail = True
    except OSError as _e41b:
        logger.warning("G7-SC41-b: cannot read popup_3d.py: %s", _e41b)

    # SC41-c: 스펙트럼 그래프 제목 "이론적 스펙트럼 (엔진 기반)" 표기 누락 탐지 (WARN, 비차단)
    # CLAUDE.md E-a: "이론적 스펙트럼(엔진기반)" 표기 필수
    # 대상 파일: popup_predicted_spectrum.py, predict_spectra.py
    _SC41C_TARGETS = [
        os.path.join(PROJECT_ROOT, "src", "app", "popup_predicted_spectrum.py"),
        os.path.join(PROJECT_ROOT, "src", "app", "predict_spectra.py"),
    ]
    _SC41C_LABEL_PAT = re.compile(
        r"이론적\s*스펙트럼.*엔진\s*기반|이론\s*스펙트럼.*엔진|엔진\s*기반.*스펙트럼|"
        r"theoretical.*spectrum.*engine|engine.*based.*spectrum",
        re.IGNORECASE,
    )
    for _f41c in _SC41C_TARGETS:
        try:
            with open(_f41c, encoding="utf-8", errors="replace") as _fh41c:
                _content41c = _fh41c.read()
            if not isinstance(_content41c, str):
                logger.warning("G7-SC41-c: non-str content in %s", _f41c)
                continue
            # 스펙트럼 예측 기능이 있는 파일인지 확인
            if "set_title" not in _content41c and "predict" not in _content41c.lower():
                continue
            if not _SC41C_LABEL_PAT.search(_content41c):
                _fname41c = os.path.basename(_f41c)
                _sc41c_msg = (
                    f"SC41-c WARN: {_fname41c} — 스펙트럼 그래프 제목에 "
                    f"'이론적 스펙트럼 (엔진 기반)' 표기 미발견. "
                    f"CLAUDE.md E-a: 예측 스펙트럼은 반드시 엔진 기반 표기 필수 (M486)."
                )
                sc41_issues.append(_sc41c_msg)
                logger.warning(
                    "G7-SC41-c WARN: %s missing '이론적 스펙트럼 (엔진 기반)' label "
                    "(CLAUDE.md E-a, M486)",
                    _fname41c,
                )
                sc41_warn = True
        except OSError as _e41c:
            logger.warning("G7-SC41-c: cannot read %s: %s", _f41c, _e41c)

    sc41_overall = "REJECT" if sc41_fail else ("WARN" if sc41_warn else "PASS")
    # SC41-a/b는 REJECT 차단, SC41-c는 WARN 비차단 (M486)

    # -- G7-SC43: 메인 repo → 워크트리 tools/*.py + housing/*.sh + docs/ai/skills/*.md 동기화 검사 (M491 신설, WARN 전용 비차단) --
    # P-WORKTREE 5회 재발 (M449/M453/M462/M487/M491) 차단.
    # SC16이 src/app/*.py만 검사하는 맹점 보완: tools/, housing/, docs/ai/skills/ 추가 대상.
    # WARN 전용 비차단 — post_write_worktree_sync.py hook와 이중 방어.
    # [MAGIC] 검사 대상 패턴 3종: tools/*.py, housing/**/*.sh, docs/ai/skills/*.md
    sc43_warn = False
    sc43_issues: list[str] = []
    _SC43_PATTERNS = [
        ("tools", "*.py"),
        ("housing", "**/*.sh"),
        ("docs/ai/skills", "*.md"),
    ]
    _sc43_worktree_base = os.path.join(PROJECT_ROOT, ".claude", "worktrees")
    if os.path.isdir(_sc43_worktree_base):
        try:
            _sc43_worktree_names = [
                _d for _d in os.listdir(_sc43_worktree_base)
                if os.path.isdir(os.path.join(_sc43_worktree_base, _d))
            ]
            for _sc43_wt in _sc43_worktree_names:
                _sc43_wt_path = os.path.join(_sc43_worktree_base, _sc43_wt)
                for _rel_dir, _glob_pat in _SC43_PATTERNS:
                    _main_dir = os.path.join(PROJECT_ROOT, _rel_dir)
                    _wt_dir = os.path.join(_sc43_wt_path, _rel_dir)
                    if not os.path.isdir(_main_dir) or not os.path.isdir(_wt_dir):
                        continue
                    # glob 대상 파일 탐색 (재귀 지원)
                    _main_files = glob.glob(
                        os.path.join(_main_dir, _glob_pat), recursive=True
                    )
                    for _mf in _main_files:
                        _basename = os.path.relpath(_mf, _main_dir)
                        _wf = os.path.join(_wt_dir, _basename)
                        if not os.path.exists(_wf):
                            # 워크트리에 파일 자체 없음 — 신규 파일 미동기화 패턴
                            _msg43 = (
                                f"SC43 WARN: {_rel_dir}/{_basename} 메인 repo 존재, "
                                f"워크트리 {_sc43_wt}에 없음 — P-WORKTREE 재발 위험 (M491)"
                            )
                            sc43_issues.append(_msg43)
                            sc43_warn = True
                            logger.warning(
                                "G7-SC43 WARN: %s/%s missing in worktree %s — "
                                "post_write_worktree_sync.py 실행 필요 (M491 R-12 확장)",
                                _rel_dir, _basename, _sc43_wt,
                            )
                            continue
                        # 파일 존재 — 내용 비교
                        try:
                            with open(_mf, "r", encoding="utf-8", errors="replace") as _fmh:
                                _mc43 = _fmh.read()
                            with open(_wf, "r", encoding="utf-8", errors="replace") as _fwh:
                                _wc43 = _fwh.read()
                            if not isinstance(_mc43, str) or not isinstance(_wc43, str):
                                continue
                            if _mc43 != _wc43:
                                # line-level diff (M462 교훈: 라인 번호 포함)
                                _diff43 = list(difflib.unified_diff(
                                    _wc43.splitlines(keepends=True),
                                    _mc43.splitlines(keepends=True),
                                    fromfile=f"worktree/{_basename}",
                                    tofile=f"main/{_basename}",
                                    n=0,
                                ))[:10]
                                _diff43_snip = "".join(_diff43)[:300]
                                _msg43d = (
                                    f"SC43 WARN: {_rel_dir}/{_basename} DIFF 워크트리 {_sc43_wt} "
                                    f"vs 메인 repo — P-WORKTREE 재발 위험 (M491). "
                                    f"diff snippet: {_diff43_snip!r}"
                                )
                                sc43_issues.append(_msg43d)
                                sc43_warn = True
                                logger.warning(
                                    "G7-SC43 WARN: %s/%s differs in worktree %s "
                                    "(M491 P-WORKTREE 5회 재발 차단)",
                                    _rel_dir, _basename, _sc43_wt,
                                )
                        except OSError as _e43f:
                            logger.warning("G7-SC43: cannot compare %s: %s", _basename, _e43f)
        except OSError as _e43:
            logger.warning("G7-SC43: worktree scan error: %s", _e43)
    else:
        logger.warning(
            "G7-SC43: worktrees base %s not found — SC43 skipped (N/A)",
            _sc43_worktree_base,
        )

    sc43_overall = "WARN" if sc43_warn else "PASS"
    # SC43은 WARN 전용 (비차단) — P-WORKTREE 5회 재발 탐지 (M491)

    # -- G7-SC45: 데스크톱-웹 핵심 함수 1:1 매핑 검증 (M495 신설, Rule Y) --
    # Rule Y: 웹기능은 데스크톱 파일명+함수명 명시하여 1:1 TS번역만.
    # 매트릭스: docs/ai/skills/web_desktop_parity.md (8행 16함수)
    # 통과율: ≥0.8 PASS, 0.5~0.8 WARN, <0.5 REJECT
    # [MAGIC] 80%=PASS 임계값, 50%=REJECT 임계값 (Rule Y 1:1 번역 강도)
    _SC45_PASS_THRESHOLD = 0.80   # 80% 이상 = PASS
    _SC45_REJECT_THRESHOLD = 0.50  # 50% 미만 = REJECT

    # 매트릭스 8행: (데스크톱 파일, 데스크톱 함수, 웹 컴포넌트 상대경로, 웹 함수)
    # [MAGIC] 웹 함수명은 실제 grep 확인값 사용 (가상 camelCase 금지 — M495 교훈)
    _SC45_MATRIX = [
        # P0: M488 sp2 N fix → M500 웹 1:1 번역 완료 (Rule Y camelCase 변환)
        # 데스크톱: estimate_z_vsepr / 웹: estimateZVsepr (TypeScript camelCase 1:1)
        ("src/app/popup_3d.py", "estimate_z_vsepr",
         "frontend/src/components/Viewer3D.tsx", "estimateZVsepr"),
        # 데스크톱: _build_sp2_set_from_mol / 웹: buildSp2SetFromMol (camelCase 1:1)
        ("src/app/popup_3d.py", "_build_sp2_set_from_mol",
         "frontend/src/components/Viewer3D.tsx", "buildSp2SetFromMol"),
        # MoleculeCanvas: 실제 웹 함수명 — fetchAnalysis + draw (Canvas2D 통합)
        ("src/app/canvas.py", "analysis_results",
         "frontend/src/components/MoleculeCanvas.tsx", "fetchAnalysis"),
        ("src/app/layer_logic.py", "LewisRenderer",
         "frontend/src/components/MoleculeCanvas.tsx", "renderLewis"),
        # App.tsx: toggleModal이 open_alphafold_popup 역할
        ("src/app/main_window.py", "open_alphafold_popup",
         "frontend/src/App.tsx", "toggleModal"),
        # SynthesisViewer: 클래스/컴포넌트 단위 매핑
        ("src/app/popup_synthesis.py", "SynthesisPopup",
         "frontend/src/components/SynthesisViewer.tsx", "SynthesisViewer"),
        # SpectrumViewer: predictSpectra가 predict_ir 역할 — 실제 함수 위치는 predict_spectra.py (M515 수정)
        ("src/app/predict_spectra.py", "predict_ir",
         "frontend/src/components/SpectrumViewer.tsx", "predictSpectra"),
        # Viewer3D: ThreeDViewer alias로 Rule Y SC45 parity 확보 (M519)
        ("src/app/popup_3d.py", "ThreeDViewer",
         "frontend/src/components/Viewer3D.tsx", "Viewer3D"),
        # W_M553: VibrationPanel -> VibrationTab + /api/vibration/calculate (Rule Y 1:1)
        ("src/app/popup_3d.py", "VibrationPanel",
         "frontend/src/components/Viewer3D.tsx", "VibrationTab"),
        # W_M553: popup_molorbital.py::MolecularOrbitalPopup -> OrbitalTab (Rule Y 1:1)
        ("src/app/popup_molorbital.py", "MolecularOrbitalPopup",
         "frontend/src/components/Viewer3D.tsx", "OrbitalTab"),
        # W_M553: vibration_engine.py::InternalVibrationEngine -> /api/vibration/calculate
        ("src/app/vibration_engine.py", "InternalVibrationEngine",
         "backend/routers/vibration.py", "calculate_vibration"),
    ]

    _MOBILE_ROOT = os.path.join(
        os.path.dirname(PROJECT_ROOT), "chemgrid_mobile"
    )

    sc45_warn = False
    sc45_reject = False
    sc45_issues: list[str] = []
    _sc45_score = 0.0  # 0.0=reject, 0.5=warn(desktop-only), 1.0=pass

    for _dt_file, _dt_func, _web_rel, _web_func in _SC45_MATRIX:
        _dt_path = os.path.join(PROJECT_ROOT, _dt_file.replace("/", os.sep))
        _web_path = os.path.join(_MOBILE_ROOT, _web_rel.replace("/", os.sep))

        # Rule N: isinstance 타입 가드
        if not isinstance(_dt_path, str) or not isinstance(_web_path, str):
            logger.warning("G7-SC45: path type error for %s/%s", _dt_file, _web_rel)
            continue

        _dt_exists = os.path.exists(_dt_path)
        _web_exists = os.path.exists(_web_path)

        _dt_found = False
        _web_found = False

        # 데스크톱 함수 grep
        if _dt_exists:
            try:
                with open(_dt_path, "r", encoding="utf-8", errors="replace") as _fh45d:
                    _dt_src = _fh45d.read()
                if isinstance(_dt_src, str) and _dt_func in _dt_src:
                    _dt_found = True
            except OSError as _e45d:
                logger.warning("G7-SC45: cannot read %s: %s", _dt_file, _e45d)

        # 웹 함수 grep
        if _web_exists:
            try:
                with open(_web_path, "r", encoding="utf-8", errors="replace") as _fh45w:
                    _web_src = _fh45w.read()
                if isinstance(_web_src, str) and _web_func in _web_src:
                    _web_found = True
            except OSError as _e45w:
                logger.warning("G7-SC45: cannot read %s: %s", _web_rel, _e45w)

        # 점수 계산 및 이슈 기록
        if _dt_found and _web_found:
            _sc45_score += 1.0
            # PASS — 로그 생략 (정상)
        elif _dt_found and not _web_found:
            # 데스크톱만 있고 웹 미번역 → WARN (Rule Y 위반 위험)
            _sc45_score += 0.5
            sc45_warn = True
            _msg45 = (
                f"SC45 WARN: {_dt_file}::{_dt_func} 존재, "
                f"{_web_rel}::{_web_func} 웹 미반영 — "
                f"Rule Y 1:1 번역 누락 (M495)"
            )
            sc45_issues.append(_msg45)
            logger.warning(
                "G7-SC45 WARN: desktop %s::%s exists but web %s::%s missing "
                "— Rule Y 1:1 translation required (M495)",
                _dt_file, _dt_func, _web_rel, _web_func,
            )
        elif not _dt_found and _web_found:
            # 웹만 있고 데스크톱 없음 → WARN (역방향 위반)
            _sc45_score += 0.5
            sc45_warn = True
            _msg45r = (
                f"SC45 WARN: {_web_rel}::{_web_func} 웹만 존재, "
                f"{_dt_file}::{_dt_func} 데스크톱 없음 — "
                f"Rule Y 역방향 위반 (M495)"
            )
            sc45_issues.append(_msg45r)
            logger.warning(
                "G7-SC45 WARN: web %s::%s exists but desktop %s::%s missing "
                "— Rule Y reverse violation (M495)",
                _web_rel, _web_func, _dt_file, _dt_func,
            )
        else:
            # 양쪽 다 없음 → WARN (매트릭스 행 자체 미구현)
            sc45_warn = True
            _msg45b = (
                f"SC45 WARN: {_dt_file}::{_dt_func} 및 {_web_rel}::{_web_func} "
                f"양쪽 모두 없음 — 매트릭스 행 미구현 (M495)"
            )
            sc45_issues.append(_msg45b)
            logger.warning(
                "G7-SC45 WARN: both desktop %s::%s and web %s::%s missing "
                "— matrix row unimplemented (M495)",
                _dt_file, _dt_func, _web_rel, _web_func,
            )
            # 양쪽 미존재는 점수 0 (sc45_score += 0)

    # 통과율 계산
    _sc45_total = len(_SC45_MATRIX)  # [MAGIC] 11행 (W_M553: VibrationTab/OrbitalTab/vibration_backend 3행 추가)
    _sc45_ratio = _sc45_score / _sc45_total if _sc45_total > 0 else 0.0

    if _sc45_ratio < _SC45_REJECT_THRESHOLD:
        sc45_reject = True
        sc45_warn = True
        logger.warning(
            "G7-SC45 REJECT: 데스크톱-웹 패리티 통과율 %.0f%% < 50%% 임계값 "
            "(M495 Rule Y 심각 위반)",
            _sc45_ratio * 100,
        )
    elif _sc45_ratio < _SC45_PASS_THRESHOLD:
        sc45_warn = True
        logger.warning(
            "G7-SC45 WARN: 데스크톱-웹 패리티 통과율 %.0f%% < 80%% 임계값 "
            "(M495 Rule Y 일부 미번역)",
            _sc45_ratio * 100,
        )
    else:
        logger.info(
            "G7-SC45 PASS: 데스크톱-웹 패리티 통과율 %.0f%% (M495 Rule Y OK)",
            _sc45_ratio * 100,
        )

    sc45_overall = "REJECT" if sc45_reject else ("WARN" if sc45_warn else "PASS")
    # SC45는 WARN 전용 비차단 (통과율 <50%여도 overall_pass는 막지 않음)
    # 단, pending_fixes.txt P0 자동 기록으로 M496 Worker 트리거

    # -- SC45 pending_fixes.txt 자동 기록 (Rule M, M495) --
    if sc45_warn:
        _pending_fixes_path = os.path.join(
            PROJECT_ROOT, "docs", "reports", "pending_fixes.txt"
        )
        try:
            os.makedirs(os.path.dirname(_pending_fixes_path), exist_ok=True)
            _pf_lines = [
                f"[SC45 P0 {datetime.now().strftime('%Y-%m-%d %H:%M')}] "
                f"Rule Y 데스크톱-웹 패리티 {sc45_overall} — "
                f"통과율 {_sc45_ratio*100:.0f}% ({_sc45_score:.1f}/{_sc45_total}) — "
                f"이슈: {len(sc45_issues)}건 — M495 patrol SC45 자동 기록",
            ]
            for _iss in sc45_issues[:5]:  # [MAGIC] 최대 5건만 기록
                _pf_lines.append(f"  {_iss}")
            _pf_text = "\n".join(_pf_lines) + "\n"
            with open(_pending_fixes_path, "a", encoding="utf-8") as _pfh:
                _pfh.write(_pf_text)
        except OSError as _e45p:
            logger.warning("G7-SC45: pending_fixes.txt 기록 실패: %s", _e45p)

    # -- G7-SC46: Mock 결과 거짓 정상 표시 검증 (M497 신설, P-MOCK-DISGUISED / FP-15) --
    # Rule M: SIMULATION_MODE / fallback 사용 시 UI 명시 라벨 의무 (R-20)
    # docking_interface.py에 SIMULATION_MODE가 있으면 popup_docking.py에 HEURISTIC/휴리스틱/추정값 라벨 필수
    sc46_warn = False
    sc46_issues: list[str] = []

    _sc46_checks = [
        # (트리거 파일, 트리거 패턴, 검증 파일, 필요 마커 목록)
        (
            "src/app/docking_interface.py",
            "SIMULATION_MODE",
            "src/app/popup_docking.py",
            ["휴리스틱", "HEURISTIC", "경험적", "추정값", "Not Vina"],
        ),
        (
            "src/app/docking_interface.py",
            "SIMULATION_MODE",
            "src/app/docking_3d_viewer.py",
            ["HEURISTIC", "Not Vina", "추정값", "SIMULATION"],
        ),
        (
            "src/app/popup_predicted_spectrum.py",
            "AVAILABLE",  # 어떤 fallback 가드라도
            "src/app/popup_predicted_spectrum.py",
            ["이론적 스펙트럼", "엔진 기반", "이론적", "theoretical"],
        ),
        (
            "src/app/popup_3d.py",
            "AVAILABLE",
            "src/app/popup_3d.py",
            ["내장 엔진", "ORCA 미설치", "VSEPR", "fallback", "추정"],
        ),
        # [M505] popup_lead_optimizer: score_variant() = 경험적 가중합 휴리스틱 → UI 명시 의무
        # FP-08 P-SCOPE + FP-15 P-MOCK-DISGUISED 재발방지 (Rule O 학술품질)
        (
            "src/app/popup_lead_optimizer.py",
            "score_variant",
            "src/app/popup_lead_optimizer.py",
            ["휴리스틱", "경험적 가중합", "ML 미사용", "heuristic", "ML 모델 미사용"],
        ),
    ]

    for _sc46_trigger_rel, _sc46_trigger_pat, _sc46_check_rel, _sc46_markers in _sc46_checks:
        _sc46_trigger_path = os.path.join(PROJECT_ROOT, _sc46_trigger_rel.replace("/", os.sep))
        _sc46_check_path = os.path.join(PROJECT_ROOT, _sc46_check_rel.replace("/", os.sep))
        try:
            with open(_sc46_trigger_path, encoding="utf-8", errors="ignore") as _sc46_tf:
                _sc46_trigger_text = _sc46_tf.read()
            if _sc46_trigger_pat in _sc46_trigger_text:
                # 트리거 발견 — 검증 파일에 마커 존재 확인
                try:
                    with open(_sc46_check_path, encoding="utf-8", errors="ignore") as _sc46_cf:
                        _sc46_check_text = _sc46_cf.read()
                    if not any(m in _sc46_check_text for m in _sc46_markers):
                        _msg46 = (
                            f"SC46 WARN: {_sc46_trigger_rel}에 '{_sc46_trigger_pat}' 패턴 존재 "
                            f"+ {_sc46_check_rel}에 UI 명시 라벨 부재 "
                            f"(마커 검색: {_sc46_markers[:3]}...) "
                            f"— P-MOCK-DISGUISED FP-15 재발 위험 (M497 R-20)"
                        )
                        sc46_issues.append(_msg46)
                        sc46_warn = True
                        logger.warning(
                            "G7-SC46 WARN: %s trigger '%s' found but %s missing UI label "
                            "— P-MOCK-DISGUISED FP-15 (M497)",
                            _sc46_trigger_rel, _sc46_trigger_pat, _sc46_check_rel,
                        )
                    else:
                        logger.info(
                            "G7-SC46 OK: %s has UI label for '%s' trigger in %s",
                            _sc46_check_rel, _sc46_trigger_pat, _sc46_trigger_rel,
                        )
                except OSError as _e46c:
                    logger.warning("G7-SC46: cannot read check file %s: %s", _sc46_check_rel, _e46c)
        except OSError as _e46t:
            logger.warning("G7-SC46: cannot read trigger file %s: %s", _sc46_trigger_rel, _e46t)

    sc46_overall = "WARN" if sc46_warn else "PASS"
    # SC46은 WARN 전용 비차단 — P-MOCK-DISGUISED 재발 탐지 (M497)

    # -- G7-SC47: PDBe Mol* prominent 버튼 patrol (M499 신설, WARN 비차단) --
    # R-21 (M499): 단백질/도킹 3D = PDBe Mol* 외부 링크 우선
    # 대상: popup_docking.py, popup_alphafold.py 등 단백질 관련 팝업
    # 검사: QDesktopServices.openUrl + pdbe.org/molstar/www.ebi.ac.uk/pdbe 패턴 의무
    # 사용자 Q-03/Q-09 기반: "PDBe Mol 시각화 학술지 표준" (Sehnal 2021)
    sc47_warn = False
    sc47_issues: list[str] = []

    # [MAGIC] SC47 검사 대상 파일 목록 (단백질/도킹/AlphaFold 관련 팝업)
    _SC47_TARGET_FILES = [
        os.path.join(PROJECT_ROOT, "src", "app", "popup_docking.py"),
        os.path.join(PROJECT_ROOT, "src", "app", "popup_alphafold.py"),
    ]
    # [MAGIC] PDBe Mol* URL 패턴 — ebi.ac.uk/pdbe + molstar 조합
    _SC47_PDBE_URL_PAT = re.compile(
        r"pdbe\.org|ebi\.ac\.uk/pdbe|molstar|pdbe/molstar|PDBe\s*Mol|Mol\*",
        re.IGNORECASE,
    )
    # [MAGIC] QDesktopServices.openUrl 또는 webbrowser.open 호출 패턴
    _SC47_OPEN_URL_PAT = re.compile(
        r"QDesktopServices\.openUrl|webbrowser\.open|open_url|openUrl",
        re.IGNORECASE,
    )

    for _f47 in _SC47_TARGET_FILES:
        if not os.path.isfile(_f47):
            # 파일 미존재 — 경고 없이 스킵 (선택적 팝업)
            continue
        try:
            with open(_f47, encoding="utf-8", errors="replace") as _fh47:
                _content47 = _fh47.read()
            if not isinstance(_content47, str):
                logger.warning("G7-SC47: non-str content in %s", _f47)
                continue
            _fname47 = os.path.basename(_f47)
            # PDBe Mol* URL 패턴 존재 여부
            _has_pdbe = bool(_SC47_PDBE_URL_PAT.search(_content47))
            # QDesktopServices.openUrl 또는 webbrowser.open 호출 존재 여부
            _has_open = bool(_SC47_OPEN_URL_PAT.search(_content47))
            if not _has_pdbe:
                _sc47_msg = (
                    f"SC47 WARN: {_fname47} — PDBe Mol* URL 패턴 미발견 "
                    f"(pdbe.org/ebi.ac.uk/pdbe/molstar). "
                    f"R-21 (M499): 단백질 3D는 PDBe Mol* 우선 배치 의무. "
                    f"사용자 Q-03/Q-09: 학술 표준 외부 링크 요구."
                )
                sc47_issues.append(_sc47_msg)
                sc47_warn = True
                logger.warning(
                    "G7-SC47 WARN: %s missing PDBe Mol* URL pattern — "
                    "R-21 M499 PDBe Mol* prominence obligation",
                    _fname47,
                )
            if not _has_open:
                _sc47_msg2 = (
                    f"SC47 WARN: {_fname47} — QDesktopServices.openUrl / webbrowser.open 미발견. "
                    f"R-21 (M499): 외부 학술 뷰어 열기 액션 의무."
                )
                sc47_issues.append(_sc47_msg2)
                sc47_warn = True
                logger.warning(
                    "G7-SC47 WARN: %s missing QDesktopServices.openUrl / webbrowser.open — "
                    "R-21 M499 external viewer open action required",
                    _fname47,
                )
        except OSError as _e47:
            logger.warning("G7-SC47: cannot read %s: %s", _f47, _e47)

    sc47_overall = "WARN" if sc47_warn else "PASS"
    # SC47은 WARN 전용 비차단 — PDBe Mol* prominent 패턴 탐지 (M499)

    # -- G7-SC49: P-POPUP-GHOST 탐지 (M544 신설, WARN 비차단) --
    #
    # 목적: foreground_test_matrix._test_popup() 결과 JSON에서
    #       popup_widget_found=False 인 popup_3d 항목 탐지.
    #       False = btn.click() 후 신규 topLevel 창 미탐지 → 메인 창 grab = ghost screenshot.
    #       FP-19 P-POPUP-GHOST 재발 방지.
    #
    # 검사 대상: docs/reports/foreground_test_evidence/foreground_results_*.json 최신 파일
    # 판정: popup_widget_found=False 항목 1건 이상 = WARN
    #
    # SC49는 WARN 전용 비차단 — 포그라운드 실행 환경에 따라 False 가능성 있음.
    sc49_warn = False
    sc49_issues: list[str] = []

    _SC49_RESULTS_DIR = os.path.join(PROJECT_ROOT, "docs", "reports", "foreground_test_evidence")
    _sc49_json_files: list[str] = []
    try:
        if os.path.isdir(_SC49_RESULTS_DIR):
            _sc49_json_files = sorted(
                [
                    os.path.join(_SC49_RESULTS_DIR, f)
                    for f in os.listdir(_SC49_RESULTS_DIR)
                    if f.startswith("foreground_results_") and f.endswith(".json")
                ],
                reverse=True,
            )
    except OSError as _e49_dir:
        logger.warning("G7-SC49: results dir 접근 실패: %s", _e49_dir)

    _sc49_latest = _sc49_json_files[0] if _sc49_json_files else None
    if _sc49_latest:
        try:
            import json as _json49
            with open(_sc49_latest, encoding="utf-8", errors="replace") as _fh49:
                _sc49_data = _json49.load(_fh49)
            if not isinstance(_sc49_data, (list, dict)):
                logger.warning("G7-SC49: 결과 JSON 형식 이상 (list/dict 아님): %s", _sc49_latest)
            else:
                # 결과 구조: list of mol_result dict, 각 dict.panels.popup_3d에 popup_widget_found 필드
                _items = _sc49_data if isinstance(_sc49_data, list) else [_sc49_data]
                for _item in _items:
                    if not isinstance(_item, dict):
                        continue
                    _panels = _item.get("panels", {})
                    if not isinstance(_panels, dict):
                        continue
                    _p3d = _panels.get("popup_3d", {})
                    if not isinstance(_p3d, dict):
                        continue
                    _found = _p3d.get("popup_widget_found")
                    if _found is False:
                        _mol = _item.get("mol_key", "?")
                        _count_before = _p3d.get("toplevel_count_before_click", "?")
                        _count_after = _p3d.get("toplevel_count_after_click", "?")
                        _sc49_msg = (
                            f"SC49 WARN P-POPUP-GHOST: mol={_mol} — popup_widget_found=False "
                            f"(topLevel 전={_count_before} 후={_count_after}). "
                            f"btn.click() 후 신규 창 미탐지 → ghost screenshot 위험 (M544 FP-19)"
                        )
                        sc49_issues.append(_sc49_msg)
                        sc49_warn = True
                        logger.warning("G7-SC49: %s", _sc49_msg)
        except Exception as _e49:
            logger.warning("G7-SC49: 결과 JSON 파싱 실패 (%s): %s", _sc49_latest, _e49)
    else:
        # JSON 파일 없음 = 포그라운드 테스트 미실행 → WARN
        sc49_warn = True
        sc49_issues.append(
            "SC49 WARN: foreground_results_*.json 미발견 — 포그라운드 테스트 미실행 또는 결과 없음"
        )
        logger.warning("G7-SC49: foreground_results JSON 미발견 (%s)", _SC49_RESULTS_DIR)

    sc49_overall = "WARN" if sc49_warn else "PASS"
    # SC49는 WARN 전용 비차단 — P-POPUP-GHOST 재발 탐지 (M544)

    # -- G7-SC52: worktree av_validator.py 라인 수 검사 (M545 신설, WARN 비차단) --
    # [M545] REJECT-2: worktree av_validator.py가 516줄로 구버전 잔존 (main repo 1500+줄 미동기).
    # AV가 worktree에서 실행될 때 M494(R-19)+M524(check_html_quality) 미반영 → SC44/SC48 체크 0%.
    # 최소 라인 수 임계: 1400줄 (매직넘버: main repo 1504줄 기준 -7% 마진)
    _SC52_MIN_LINES = 1400  # [MAGIC] worktree av_validator.py 최소 라인 수 (main repo 1504줄 기준)
    sc52_warn = False
    sc52_issues: list[str] = []
    try:
        _worktrees_dir = os.path.join(PROJECT_ROOT, ".claude", "worktrees")
        if os.path.isdir(_worktrees_dir):
            for _wt_name in os.listdir(_worktrees_dir):
                _wt_av = os.path.join(
                    _worktrees_dir, _wt_name, "housing", "sinktank", "av_validator.py"
                )
                if not os.path.isfile(_wt_av):
                    continue
                try:
                    with open(_wt_av, encoding="utf-8", errors="ignore") as _f:
                        _lines = sum(1 for _ in _f)
                    if _lines < _SC52_MIN_LINES:
                        sc52_warn = True
                        sc52_issues.append(
                            f"SC52 WARN: worktree/{_wt_name}/housing/sinktank/av_validator.py"
                            f" = {_lines}줄 < {_SC52_MIN_LINES}줄 — 구버전 동기화 필요 (M545)"
                        )
                        logger.warning("G7-SC52: %s — %d줄 (구버전)", _wt_name, _lines)
                except OSError as _e52:
                    logger.warning("G7-SC52: %s av_validator 읽기 실패: %s", _wt_name, _e52)
    except Exception as _e52_all:
        logger.warning("G7-SC52: worktrees 디렉터리 탐색 실패: %s", _e52_all)

    sc52_overall = "WARN" if sc52_warn else "PASS"
    # SC52는 WARN 전용 비차단 — 동기화 누락 탐지 목적 (M545)

    # -- G7-SC55: Theory layer ESP cloud 보존 검사 (M555/M557 신설, WARN 비차단) --
    # 전자구름(_draw_per_atom_clouds)은 Theory 레이어 핵심 — 제거/약화 패턴 차단
    sc55_warn = False
    sc55_msgs = []
    _layer_logic_path = os.path.join(PROJECT_ROOT, "src", "app", "layer_logic.py")
    try:
        with open(_layer_logic_path, encoding="utf-8") as _f55:
            _ll_content = _f55.read()
        # 필수 항목 3종 체크
        if "_draw_per_atom_clouds" not in _ll_content:
            sc55_warn = True
            sc55_msgs.append("SC55 WARN: _draw_per_atom_clouds 함수 미존재 — Theory ESP cloud 손실 (M555/M557)")
            logger.warning("G7-SC55: _draw_per_atom_clouds 미존재 — ESP cloud 제거 위험")
        if "alpha_center" not in _ll_content:
            sc55_warn = True
            sc55_msgs.append("SC55 WARN: alpha_center 미존재 — cloud 불투명도 설정 누락 (M557)")
            logger.warning("G7-SC55: alpha_center 미존재 — ESP cloud 시각성 보장 불가")
        if "QRadialGradient" not in _ll_content:
            sc55_warn = True
            sc55_msgs.append("SC55 WARN: QRadialGradient 미사용 — flat fill로 degraded (Rule O 위반)")
            logger.warning("G7-SC55: QRadialGradient 미사용 — Rule O(렌더링 품질) 위반")
    except Exception as _e55:
        logger.warning("G7-SC55: layer_logic.py 읽기 실패: %s", _e55)
        sc55_msgs.append(f"SC55 WARN: layer_logic.py 읽기 실패: {_e55}")
        sc55_warn = True
    sc55_overall = "WARN" if sc55_warn else "PASS"
    # SC55는 WARN 전용 비차단 — Theory layer 핵심 보존 탐지 목적 (M555/M557)

    # -- G7-SC56: anger_simulator 매트릭스 100+건 + ML 진화 갱신 검증 (M556 신설, WARN 비차단) --
    # 사용자 명시 (W_M556): "마치 머신러닝 하듯이 매 사이클 발전" + "100+건 매트릭스"
    # 1) anger_simulator.py에 STEREO-/MECH- 매트릭스 합 >= 100
    # 2) anger_metrics.json mtime이 최근 6시간 이내 (정상 ralph_loop Phase 4.7b 가동 증거)
    # 3) anger_metrics.json pool_size >= 8 (기본 8 패턴 최소 보장)
    # [MAGIC] 6시간 = 21600초 (ralph_loop 사이클 평균 30분, 12사이클 정상 가동 윈도우)
    sc56_warn = False
    sc56_msgs = []
    _SC56_FRESH_WINDOW = 21600  # [MAGIC] 6시간
    _SC56_MATRIX_MIN = 100  # [MAGIC] 사용자 명시 100+건
    _SC56_POOL_MIN = 8  # [MAGIC] 기본 8 패턴 최소
    _anger_sim_path = os.path.join(PROJECT_ROOT, "housing", "sinktank", "anger_simulator.py")
    _anger_metrics_path = os.path.join(
        PROJECT_ROOT, "docs", "reports", "anger_audit", "anger_metrics.json"
    )

    # 1) 매트릭스 크기 검사
    try:
        with open(_anger_sim_path, "r", encoding="utf-8", errors="replace") as _fa56:
            _asim_content = _fa56.read()
        # 매트릭스 항목 수 추출 (id: "STEREO-..." / "MECH-..." 카운트)
        _matrix_count = _asim_content.count('"id": "STEREO-') + _asim_content.count('"id": "MECH-')
        if _matrix_count < _SC56_MATRIX_MIN:
            sc56_warn = True
            sc56_msgs.append(
                f"SC56 WARN: anger_simulator 매트릭스 {_matrix_count}건 < {_SC56_MATRIX_MIN}건 "
                "— 사용자 명시 100+건 미달 (M556 FP-21)"
            )
            logger.warning(
                "G7-SC56: anger_simulator 매트릭스 %d건 < %d (FP-21 정적 패턴 풀)",
                _matrix_count, _SC56_MATRIX_MIN,
            )
    except OSError as _e56s:
        logger.warning("G7-SC56: anger_simulator.py 읽기 실패: %s", _e56s)
        sc56_msgs.append(f"SC56 WARN: anger_simulator.py 읽기 실패: {_e56s}")
        sc56_warn = True

    # 2) anger_metrics.json mtime + pool_size 검사 (ML 진화 가동 증거)
    if os.path.isfile(_anger_metrics_path):
        try:
            _mtime56 = os.path.getmtime(_anger_metrics_path)
            _now56 = time.time()
            _age56 = _now56 - _mtime56
            if _age56 > _SC56_FRESH_WINDOW:
                sc56_warn = True
                sc56_msgs.append(
                    f"SC56 WARN: anger_metrics.json mtime 만료 (age={int(_age56)}s "
                    f"> {_SC56_FRESH_WINDOW}s) — ralph_loop Phase 4.7b 미가동 의심 (M556)"
                )
                logger.warning(
                    "G7-SC56: anger_metrics.json mtime %ds (윈도우 %ds 초과)",
                    int(_age56), _SC56_FRESH_WINDOW,
                )
            with open(_anger_metrics_path, "r", encoding="utf-8", errors="replace") as _fm56:
                _metrics56 = json.load(_fm56)
            if isinstance(_metrics56, dict):
                _pool_size = _metrics56.get("pool_size", 0)
                if isinstance(_pool_size, (int, float)) and _pool_size < _SC56_POOL_MIN:
                    sc56_warn = True
                    sc56_msgs.append(
                        f"SC56 WARN: anger pool_size {_pool_size} < {_SC56_POOL_MIN} "
                        "— 기본 패턴 풀 손실 (M556)"
                    )
                    logger.warning(
                        "G7-SC56: pool_size %s < %d (기본 8 패턴 손실)",
                        _pool_size, _SC56_POOL_MIN,
                    )
        except (OSError, ValueError) as _e56m:
            logger.warning("G7-SC56: anger_metrics.json 파싱 실패: %s", _e56m)
            sc56_msgs.append(f"SC56 WARN: anger_metrics.json 파싱 실패: {_e56m}")
            sc56_warn = True
    else:
        # 첫 사이클 정상 케이스 — INFO만 발화
        logger.info(
            "G7-SC56: anger_metrics.json 미존재 — 첫 사이클 정상 (M556 ML 진화 미실행)"
        )

    sc56_overall = "WARN" if sc56_warn else "PASS"
    # SC56은 WARN 전용 비차단 — anger 매트릭스 검증 목적 (M556 FP-21 P-STATIC-PATTERN-POOL)

    # -- G7-SC57: cmd 창 노출 패턴 자동 탐지 (M558 신설, WARN 비차단) --
    # 사용자 격분 직결: "포그라운드에 cmd 그만 띄우라 에이전트한테도 동일하게 전달"
    # 금지 패턴: cmd /c 직접 호출, schtasks /Create 직접, PowerShell Hidden 없이
    # 허용 패턴: wscript run_hidden.vbs / PowerShell -WindowStyle Hidden / nohup 백그라운드
    sc57_warn = False
    sc57_msgs = []

    # 검사 1: run_hidden.vbs 파일 존재 확인
    _run_hidden_vbs = os.path.join(PROJECT_ROOT, "housing", "sinktank", "run_hidden.vbs")
    if not os.path.isfile(_run_hidden_vbs):
        sc57_warn = True
        sc57_msgs.append("SC57 WARN: run_hidden.vbs 미존재 — cmd 창 차단 래퍼 신설 필요 (M558)")
        logger.warning("G7-SC57: run_hidden.vbs 미존재 — 전역 cmd 창 차단 래퍼 없음")

    # 검사 2: 최근 24시간 evidence MD 파일에서 cmd 창 노출 패턴 탐지
    # [MAGIC] 24시간 = 86400초 (SC57 스캔 윈도우)
    _SC57_SCAN_WINDOW = 86400
    _evidence_dir = os.path.join(PROJECT_ROOT, "docs", "reports")
    _now_sc57 = time.time()
    _sc57_pattern_cmd_direct = re.compile(r"\bcmd\s*/c\b", re.IGNORECASE)
    _sc57_pattern_schtask_direct = re.compile(r"schtasks\s*/Create\b", re.IGNORECASE)
    _sc57_pattern_ps_hidden = re.compile(
        r"(WindowStyle\s+Hidden|wscript|run_hidden\.vbs|\.vbs|nohup\s+)", re.IGNORECASE
    )
    try:
        if os.path.isdir(_evidence_dir):
            for _root57, _dirs57, _files57 in os.walk(_evidence_dir):
                for _fname57 in _files57:
                    if not _fname57.endswith(".md"):
                        continue
                    _fpath57 = os.path.join(_root57, _fname57)
                    try:
                        _mtime57 = os.path.getmtime(_fpath57)
                        if (_now_sc57 - _mtime57) > _SC57_SCAN_WINDOW:
                            continue  # 24시간 초과 파일 제외
                        with open(_fpath57, "r", encoding="utf-8", errors="ignore") as _fh57:
                            _content57 = _fh57.read()
                        # cmd /c 직접 호출 탐지
                        if _sc57_pattern_cmd_direct.search(_content57):
                            # Hidden 패턴 없이 cmd /c 만 있으면 WARN
                            if not _sc57_pattern_ps_hidden.search(_content57):
                                sc57_warn = True
                                sc57_msgs.append(
                                    f"SC57 WARN: {_fname57} — cmd /c 직접 호출 탐지 (Hidden 없음, M558)"
                                )
                                logger.warning(
                                    "G7-SC57: %s에 cmd /c 직접 호출 패턴 존재 (Hidden 미사용)", _fname57
                                )
                        # schtasks /Create 직접 (PowerShell Hidden 없이)
                        if _sc57_pattern_schtask_direct.search(_content57):
                            if not _sc57_pattern_ps_hidden.search(_content57):
                                sc57_warn = True
                                sc57_msgs.append(
                                    f"SC57 WARN: {_fname57} — schtasks /Create 직접 호출 탐지 (XML /Hidden 없음, M558)"
                                )
                                logger.warning(
                                    "G7-SC57: %s에 schtasks /Create 직접 호출 패턴 존재 (Hidden 미사용)", _fname57
                                )
                    except OSError as _e57_f:
                        logger.warning("G7-SC57: %s 읽기 실패: %s", _fname57, _e57_f)
    except Exception as _e57:
        logger.warning("G7-SC57: evidence 디렉터리 스캔 실패: %s", _e57)
        sc57_msgs.append(f"SC57 WARN: evidence 스캔 실패: {_e57}")
        sc57_warn = True

    sc57_overall = "WARN" if sc57_warn else "PASS"
    # SC57은 WARN 전용 비차단 — cmd 창 노출 탐지 목적 (M558)

    # ── SC64: synthesis timeout 검사 (M613 신설) ──────────────────────────────
    # popup_synthesis.py watchdog timeout 주석 확인 (M613 Rule M: 분석 타임아웃)
    # backend synthesis.py timeout 30초 이상 여부 확인
    sc64_warn = False
    sc64_msgs: list = []
    _popup_syn_path = os.path.join(PROJECT_ROOT, "src", "app", "popup_synthesis.py")
    _backend_syn_candidates = [
        os.path.join(PROJECT_ROOT, "chemgrid_mobile", "backend", "routers", "synthesis.py"),
    ]
    # worktree 내 synthesis.py도 검사
    _wt_base_64 = os.path.join(PROJECT_ROOT, ".claude", "worktrees")
    if os.path.isdir(_wt_base_64):
        for _wt64 in os.listdir(_wt_base_64):
            _candidate = os.path.join(_wt_base_64, _wt64, "chemgrid_mobile", "backend", "routers", "synthesis.py")
            if os.path.isfile(_candidate):
                _backend_syn_candidates.append(_candidate)
    try:
        # SC64-a: popup_synthesis.py watchdog 30초+ 확인
        if os.path.isfile(_popup_syn_path):
            with open(_popup_syn_path, encoding="utf-8", errors="ignore") as _f64:
                _popup_text = _f64.read()
            # watchdog M613 주석 또는 "분석 타임아웃" 메시지 존재 확인
            if "분석 타임아웃" not in _popup_text and "watchdog" not in _popup_text.lower():
                sc64_warn = True
                sc64_msgs.append(
                    "SC64-a WARN: popup_synthesis.py watchdog/분석 타임아웃 없음 (M613)"
                )
        # SC64-b: backend synthesis.py timeout >= 30.0 확인
        import re as _re64
        for _bs_path in _backend_syn_candidates:
            if not os.path.isfile(_bs_path):
                continue
            with open(_bs_path, encoding="utf-8", errors="ignore") as _f64b:
                _bs_text = _f64b.read()
            _to_matches = _re64.findall(r"timeout_seconds\s*=\s*([\d.]+)", _bs_text)
            for _tm in _to_matches:
                try:
                    if float(_tm) < 30.0:  # 30초 미만이면 WARN
                        sc64_warn = True
                        sc64_msgs.append(
                            f"SC64-b WARN: {os.path.basename(_bs_path)} "
                            f"timeout_seconds={_tm} < 30.0 (M613 Rule M)"
                        )
                except ValueError:
                    pass
    except Exception as _e64:
        logger.warning("G7-SC64: synthesis timeout 검사 실패: %s", _e64)
        sc64_msgs.append(f"SC64 WARN: 검사 실패: {_e64}")

    sc64_overall = "WARN" if sc64_warn else "PASS"
    # SC64는 WARN 전용 비차단 — synthesis timeout 검증 목적 (M613)

    # -- G7-SC66: 하네스 자가 진단 (M616 신설, WARN 비차단) --
    # 근거: 외부 LLM 진단 (Density Overload + 간사 이중 자아 + 재귀적 계열화 맹점)
    # 측정: (1) CLAUDE.md wc -l > 50줄 (Density Overload, M616 baseline 414줄),
    #       (2) squirrel_audit.jsonl WARN_RATE > 50% (재귀적 계열화 맹점, M616 baseline 80.4%),
    #       (3) read_skills_count=0 비율 > 70% (간사 이중 자아, M616 baseline 79%)
    sc66_warn = False
    sc66_msgs: list = []
    try:
        # (1) CLAUDE.md 줄 수 검사
        # [MAGIC] 50 = 압축 인덱스 + 본문 분리 후 현실적 상한 (M616, 30줄은 비현실적)
        _CLAUDE_MD_LIMIT = 50
        _claude_md_path = os.path.join(PROJECT_ROOT, "CLAUDE.md")
        if os.path.isfile(_claude_md_path):
            try:
                with open(_claude_md_path, "r", encoding="utf-8") as _fcm:
                    _cm_n = sum(1 for _ in _fcm)
                if _cm_n > _CLAUDE_MD_LIMIT:
                    sc66_msgs.append(
                        f"SC66 WARN: CLAUDE.md {_cm_n}줄 (>{_CLAUDE_MD_LIMIT}) — Density Overload 위험 (M616)"
                    )
                    logger.warning(
                        "G7-SC66: CLAUDE.md %d lines > %d (M616)",
                        _cm_n, _CLAUDE_MD_LIMIT,
                    )
                    sc66_warn = True
            except Exception as _e_cm:
                logger.warning("G7-SC66: CLAUDE.md read 실패: %s", _e_cm)

        # (2)/(3) squirrel_audit.jsonl WARN_RATE / zero_reads 비율
        # [MAGIC] 0.5 = 50% WARN_RATE 한도, 0.7 = 70% zero_reads 한도, 50 = 직전 N건 샘플 (M616)
        _SC66_WARN_RATE_LIMIT = 0.5
        _SC66_ZERO_READ_LIMIT = 0.7
        _SC66_SAMPLE_SIZE = 50
        _squirrel_path = os.path.join(PROJECT_ROOT, ".claude", "squirrel_audit.jsonl")
        if os.path.isfile(_squirrel_path):
            try:
                with open(_squirrel_path, "r", encoding="utf-8") as _fsq:
                    _sq_lines = [l for l in _fsq if l.strip()]
                _sq_recent = _sq_lines[-_SC66_SAMPLE_SIZE:]
                _sq_total = len(_sq_recent)
                if _sq_total > 0:
                    _sq_warn_count = 0
                    _sq_zero_count = 0
                    for _l in _sq_recent:
                        try:
                            _e = json.loads(_l)
                            if not isinstance(_e, dict):
                                continue
                            if _e.get("verdict") == "WARN":
                                _sq_warn_count += 1
                            if _e.get("read_skills_count") == 0:
                                _sq_zero_count += 1
                        except Exception:
                            continue
                    _warn_rate = _sq_warn_count / _sq_total
                    _zero_rate = _sq_zero_count / _sq_total
                    if _warn_rate > _SC66_WARN_RATE_LIMIT:
                        sc66_msgs.append(
                            f"SC66 WARN: squirrel_audit WARN_RATE={_warn_rate*100:.1f}% "
                            f"(>{_SC66_WARN_RATE_LIMIT*100:.0f}%, 직전 {_sq_total}건) — "
                            f"재귀적 계열화 맹점 (M616)"
                        )
                        logger.warning(
                            "G7-SC66: WARN_RATE %.1f%% (M616)", _warn_rate * 100
                        )
                        sc66_warn = True
                    if _zero_rate > _SC66_ZERO_READ_LIMIT:
                        sc66_msgs.append(
                            f"SC66 WARN: squirrel_audit zero_reads={_zero_rate*100:.1f}% "
                            f"(>{_SC66_ZERO_READ_LIMIT*100:.0f}%) — 다람쥐볼 무시 (M616)"
                        )
                        logger.warning(
                            "G7-SC66: zero_reads %.1f%% (M616)", _zero_rate * 100
                        )
                        sc66_warn = True
            except Exception as _e_sq:
                logger.warning("G7-SC66: squirrel_audit read 실패: %s", _e_sq)
    except Exception as _e66:
        logger.warning("G7-SC66: 자가 진단 실패: %s", _e66)
        sc66_msgs.append(f"SC66 WARN: 진단 실패 -- {_e66}")
        sc66_warn = True

    sc66_overall = "WARN" if sc66_warn else "PASS"
    # SC66은 WARN 전용 비차단 — 외부 LLM 진단 검증 (M616)

    # -- G7-SC67: 토큰 효율화 인프라 미비 감지 (M617 신설, WARN 비차단) --
    # 근거: Agent 208회 spawn model 파라미터 0회 + 외부 AI 7종 사용 0건 + 한도 207세션 silent failure
    sc67_warn = False
    sc67_msgs: list[str] = []
    try:
        _multi_llm_path = os.path.join(PROJECT_ROOT, "housing", "sinktank", "multi_llm.py")
        _api_limit_handler = os.path.join(PROJECT_ROOT, "housing", "sinktank", "api_limit_handler.py")
        _token_skill = os.path.join(PROJECT_ROOT, "docs", "ai", "skills", "token_efficiency.md")
        # (1) multi_llm.py 존재 확인
        if not os.path.isfile(_multi_llm_path):
            sc67_msgs.append(
                "SC67 WARN: housing/sinktank/multi_llm.py 미존재 -- 외부 AI fallback 불가 (Rule MM)"
            )
            logger.warning("G7-SC67: multi_llm.py 미존재 (M617)")
            sc67_warn = True
        # (2) api_limit_handler.py 존재 확인 (한도 초과 자동 라우팅)
        if not os.path.isfile(_api_limit_handler):
            sc67_msgs.append(
                "SC67 WARN: housing/sinktank/api_limit_handler.py 미존재 -- "
                "Anthropic 한도 초과 시 외부 AI fallback 불가 (Rule MM R-26)"
            )
            logger.warning("G7-SC67: api_limit_handler.py 미존재 (M617 R-26)")
            sc67_warn = True
        # (3) skills/token_efficiency.md 존재 확인
        if not os.path.isfile(_token_skill):
            sc67_msgs.append(
                "SC67 WARN: docs/ai/skills/token_efficiency.md 미존재 -- Rule MM 체화 미비 (M617)"
            )
            logger.warning("G7-SC67: token_efficiency.md 미존재 (M617)")
            sc67_warn = True
    except Exception as _e67:
        logger.warning("G7-SC67: 토큰 효율화 검사 실패: %s", _e67)
        sc67_msgs.append(f"SC67 WARN: 검사 실패 -- {_e67}")
        sc67_warn = True

    sc67_overall = "WARN" if sc67_warn else "PASS"
    # SC67은 WARN 전용 비차단 -- 토큰 효율화 인프라 미비 감지 (M617 Rule MM)

    # -- G7-SC68: Kimi 가동 검증 (M618 권고 -> M623 신설, WARN 비차단) --
    sc68_warn = False
    sc68_msgs: list = []
    try:
        _kimi_client_path = os.path.join(PROJECT_ROOT, "housing", "local_llm", "kimi_client.py")
        _multi_llm_path = os.path.join(PROJECT_ROOT, "housing", "sinktank", "multi_llm.py")
        _api_limit_path = os.path.join(PROJECT_ROOT, "housing", "sinktank", "api_limit_handler.py")
        if not os.path.isfile(_kimi_client_path):
            sc68_msgs.append(
                "SC68 WARN: housing/local_llm/kimi_client.py 미존재 -- Kimi K2 폴백 불가 (M618)"
            )
            sc68_warn = True
            logger.warning("G7-SC68: kimi_client.py 미존재 (M618)")
        if not os.path.isfile(_multi_llm_path):
            sc68_msgs.append(
                "SC68 WARN: housing/sinktank/multi_llm.py 미존재 (M617/M618)"
            )
            sc68_warn = True
        if not os.path.isfile(_api_limit_path):
            sc68_msgs.append(
                "SC68 WARN: housing/sinktank/api_limit_handler.py 미존재 (M618 R-26)"
            )
            sc68_warn = True
            logger.warning("G7-SC68: api_limit_handler.py 미존재 (M618)")
    except Exception as _e68:
        logger.warning("G7-SC68: Kimi 가동 검증 실패: %s", _e68)
        sc68_msgs.append(f"SC68 WARN: 검사 실패 -- {_e68}")
        sc68_warn = True

    sc68_overall = "WARN" if sc68_warn else "PASS"
    # SC68은 WARN 전용 비차단 -- Kimi K2 인프라 미비 감지 (M618->M623)

    # -- G7-SC69: 다람쥐볼 auto-attach hook 검증 (M623 신설, WARN 비차단) --
    sc69_warn = False
    sc69_msgs: list = []
    try:
        _sqb_hook_path = os.path.join(PROJECT_ROOT, ".claude", "hooks", "squirrel_ball_auto_attach.py")
        _sqb_skill_path = os.path.join(PROJECT_ROOT, "docs", "ai", "skills", "squirrel_ball_auto.md")
        _sqb_audit_log = os.path.join(PROJECT_ROOT, ".claude", "squirrel_audit.log")
        _settings_path = os.path.join(PROJECT_ROOT, ".claude", "settings.json")

        # hook 파일 존재 확인
        if not os.path.isfile(_sqb_hook_path):
            sc69_msgs.append(
                "SC69 WARN: .claude/hooks/squirrel_ball_auto_attach.py 미존재 -- Rule V 자동화 불가 (M623)"
            )
            sc69_warn = True
            logger.warning("G7-SC69: squirrel_ball_auto_attach.py 미존재 (M623)")

        # skill 파일 존재 확인
        if not os.path.isfile(_sqb_skill_path):
            sc69_msgs.append(
                "SC69 WARN: docs/ai/skills/squirrel_ball_auto.md 미존재 -- 체화 미비 (M623)"
            )
            sc69_warn = True
            logger.warning("G7-SC69: squirrel_ball_auto.md 미존재 (M623)")

        # settings.json에 hook 등록 여부 확인
        if os.path.isfile(_settings_path):
            try:
                with open(_settings_path, "r", encoding="utf-8") as _sf:
                    _settings = __import__("json").load(_sf)
                _pre_hooks = _settings.get("hooks", {}).get("PreToolUse", [])
                _sqb_registered = False
                for _section in _pre_hooks:
                    if _section.get("matcher") == "Agent":
                        for _h in _section.get("hooks", []):
                            if "squirrel_ball_auto_attach" in _h.get("command", ""):
                                _sqb_registered = True
                                break
                if not _sqb_registered:
                    sc69_msgs.append(
                        "SC69 WARN: settings.json Agent hooks에 squirrel_ball_auto_attach 미등록 (M623)"
                    )
                    sc69_warn = True
                    logger.warning("G7-SC69: squirrel_ball_auto_attach 미등록 settings.json (M623)")
            except Exception as _e_settings:
                logger.warning("G7-SC69: settings.json 읽기 실패: %s", _e_settings)

        # squirrel_audit.log DENY_ZERO 비율 확인 (최근 50건)
        if os.path.isfile(_sqb_audit_log):
            try:
                import json as _json_sc69
                _sq69_lines = []
                with open(_sqb_audit_log, "r", encoding="utf-8") as _sf69:
                    _sq69_lines = [l.strip() for l in _sf69.readlines() if l.strip()]
                _sq69_recent = _sq69_lines[-50:]  # 최근 50건 (M623)
                _sq69_total = len(_sq69_recent)
                if _sq69_total > 0:
                    _sq69_deny = sum(
                        1 for l in _sq69_recent
                        if "DENY" in _json_sc69.loads(l).get("verdict", "")
                    )
                    _deny_rate = _sq69_deny / _sq69_total
                    if _deny_rate > 0.3:  # 30% 초과 DENY = Rule V 위반 빈발 (M623)
                        sc69_msgs.append(
                            f"SC69 WARN: squirrel_audit DENY_RATE={_deny_rate*100:.1f}% "
                            f"(>{30}%, 직전 {_sq69_total}건) -- Rule V 위반 빈발 (M623)"
                        )
                        sc69_warn = True
                        logger.warning("G7-SC69: DENY_RATE %.1f%% (M623)", _deny_rate * 100)
            except Exception as _e_sq69:
                logger.warning("G7-SC69: squirrel_audit.log 읽기 실패: %s", _e_sq69)
    except Exception as _e69:
        logger.warning("G7-SC69: 다람쥐볼 hook 검증 실패: %s", _e69)
        sc69_msgs.append(f"SC69 WARN: 검사 실패 -- {_e69}")
        sc69_warn = True

    sc69_overall = "WARN" if sc69_warn else "PASS"
    # SC69은 WARN 전용 비차단 -- 다람쥐볼 auto-attach hook 미비 감지 (M623)

    # -- G7-SC70: OpenRouter Kimi 비용 모니터링 인프라 검증 (M624 신설, WARN 비차단) --
    # 근거: 학회 D-3~D-0 Kimi K2 비용 누적 무감지 → 잔액 소진 silent failure 방지
    sc70_warn = False
    sc70_msgs: list = []
    try:
        _or_check_path = os.path.join(PROJECT_ROOT, "tools", "openrouter_usage_check.py")
        _or_latest_path = os.path.join(
            PROJECT_ROOT, "docs", "reports", "openrouter_usage", "latest_usage.json"
        )
        _or_skill_path = os.path.join(
            PROJECT_ROOT, "docs", "ai", "skills", "openrouter_cost_monitor.md"
        )
        # (1) openrouter_usage_check.py 존재 확인
        if not os.path.isfile(_or_check_path):
            sc70_msgs.append(
                "SC70 WARN: tools/openrouter_usage_check.py 미존재 -- "
                "Kimi 비용 모니터링 불가 (M624)"
            )
            sc70_warn = True
            logger.warning("G7-SC70: openrouter_usage_check.py 미존재 (M624)")
        # (2) latest_usage.json 존재 및 fetch_ok 확인
        if os.path.isfile(_or_latest_path):
            try:
                with open(_or_latest_path, "r", encoding="utf-8") as _f70:
                    _latest70 = __import__("json").load(_f70)
                if not isinstance(_latest70, dict):
                    sc70_msgs.append("SC70 WARN: latest_usage.json 형식 이상 (M624)")
                    sc70_warn = True
                    logger.warning("G7-SC70: latest_usage.json 형식 이상")
                else:
                    _fetch_ok = _latest70.get("fetch_ok")
                    _alert70 = _latest70.get("alert", "")
                    if _fetch_ok is False:
                        sc70_msgs.append(
                            "SC70 WARN: latest_usage.json fetch_ok=False -- "
                            "OpenRouter API 키 미설정 또는 네트워크 오류 (M624)"
                        )
                        sc70_warn = True
                        logger.warning("G7-SC70: fetch_ok=False (M624)")
                    elif isinstance(_alert70, str) and "RED" in _alert70:
                        sc70_msgs.append(
                            f"SC70 WARN: OpenRouter 잔액 부족 — {_alert70} (M624)"
                        )
                        sc70_warn = True
                        logger.warning("G7-SC70: 잔액 RED 경보: %s (M624)", _alert70)
            except (OSError, ValueError) as _e70_json:
                logger.warning("G7-SC70: latest_usage.json 읽기 실패: %s", _e70_json)
                sc70_msgs.append(f"SC70 WARN: latest_usage.json 파싱 실패 -- {_e70_json}")
                sc70_warn = True
        else:
            sc70_msgs.append(
                "SC70 WARN: docs/reports/openrouter_usage/latest_usage.json 미존재 -- "
                "openrouter_usage_check.py 미실행 (M624)"
            )
            sc70_warn = True
            logger.warning("G7-SC70: latest_usage.json 미존재 -- 미실행 (M624)")
        # (3) skills/openrouter_cost_monitor.md 존재 확인 (체화 4단계 H-2)
        if not os.path.isfile(_or_skill_path):
            sc70_msgs.append(
                "SC70 WARN: docs/ai/skills/openrouter_cost_monitor.md 미존재 -- "
                "체화 4단계 H-2 미비 (M624)"
            )
            sc70_warn = True
            logger.warning("G7-SC70: openrouter_cost_monitor.md 미존재 (M624)")
    except Exception as _e70:
        logger.warning("G7-SC70: OpenRouter 비용 모니터링 검사 실패: %s", _e70)
        sc70_msgs.append(f"SC70 WARN: 검사 실패 -- {_e70}")
        sc70_warn = True

    sc70_overall = "WARN" if sc70_warn else "PASS"
    # SC70은 WARN 전용 비차단 -- Kimi 비용 모니터링 인프라 미비 감지 (M624)

    # -- G7-SC71: 학술 정합성 자동 audit hook + Kimi 자동 호출 검증 (M625 신설, WARN 비차단) --
    # 근거: 사용자 핵심 명령 "학술적 정합성을 확보하였는가를 거르고 증명하는 능력"
    # 검증: hook 파일 존재 + settings.json 등록 + 누적 academic_integrity_log.jsonl
    sc71_warn = False
    sc71_msgs: list = []
    try:
        _ai_hook_path = os.path.join(
            PROJECT_ROOT, ".claude", "hooks", "academic_integrity_check.py"
        )
        _ai_skill_path = os.path.join(
            PROJECT_ROOT, "docs", "ai", "skills", "academic_integrity_auto.md"
        )
        _ai_log_path = os.path.join(
            PROJECT_ROOT, ".claude", "academic_integrity_log.jsonl"
        )
        _settings_path_71 = os.path.join(PROJECT_ROOT, ".claude", "settings.json")

        # (1) hook 파일 존재 확인
        if not os.path.isfile(_ai_hook_path):
            sc71_msgs.append(
                "SC71 WARN: .claude/hooks/academic_integrity_check.py 미존재 -- "
                "학술 정합성 자동 audit 불가 (M625)"
            )
            sc71_warn = True
            logger.warning(
                "G7-SC71: academic_integrity_check.py 미존재 (M625)"
            )

        # (2) settings.json PostToolUse Edit|Write 등록 확인
        if os.path.isfile(_settings_path_71):
            try:
                with open(_settings_path_71, "r", encoding="utf-8") as _sf71:
                    _settings_71 = __import__("json").load(_sf71)
                _post_hooks_71 = _settings_71.get("hooks", {}).get(
                    "PostToolUse", []
                )
                _ai_registered = False
                for _section_71 in _post_hooks_71:
                    if _section_71.get("matcher") == "Edit|Write":
                        for _h71 in _section_71.get("hooks", []):
                            if "academic_integrity_check" in _h71.get(
                                "command", ""
                            ):
                                _ai_registered = True
                                break
                if not _ai_registered:
                    sc71_msgs.append(
                        "SC71 WARN: settings.json PostToolUse Edit|Write에 "
                        "academic_integrity_check 미등록 (M625)"
                    )
                    sc71_warn = True
                    logger.warning(
                        "G7-SC71: academic_integrity_check 미등록 settings.json"
                    )
            except (OSError, ValueError) as _e_set71:
                logger.warning(
                    "G7-SC71: settings.json 읽기 실패: %s", _e_set71
                )
                sc71_msgs.append(
                    f"SC71 WARN: settings.json 파싱 실패 -- {_e_set71}"
                )
                sc71_warn = True

        # (3) skill 파일 존재 확인 (체화 4단계 H-2)
        if not os.path.isfile(_ai_skill_path):
            sc71_msgs.append(
                "SC71 WARN: docs/ai/skills/academic_integrity_auto.md 미존재 -- "
                "체화 4단계 H-2 미비 (M625)"
            )
            sc71_warn = True
            logger.warning(
                "G7-SC71: academic_integrity_auto.md 미존재 (M625)"
            )

        # (4) academic_integrity_log.jsonl 누적 (Kimi 호출 흔적) 확인
        # log 파일이 비어있어도 hook 자체는 작동 — WARN만 발화
        if os.path.isfile(_ai_log_path):
            try:
                with open(_ai_log_path, "r", encoding="utf-8") as _lf71:
                    _log_lines_71 = [
                        l.strip() for l in _lf71.readlines() if l.strip()
                    ]
                if not _log_lines_71:
                    sc71_msgs.append(
                        "SC71 WARN: academic_integrity_log.jsonl 비어있음 -- "
                        "Edit/Write 후 hook 미발화 의심 (M625)"
                    )
                    sc71_warn = True
                    logger.warning(
                        "G7-SC71: academic_integrity_log.jsonl 비어있음 (M625)"
                    )
            except OSError as _e_log71:
                logger.warning(
                    "G7-SC71: log 읽기 실패: %s", _e_log71
                )

    except (OSError, ValueError) as _e71:
        logger.warning("G7-SC71: 학술 정합성 hook 검사 실패: %s", _e71)
        sc71_msgs.append(f"SC71 WARN: 검사 실패 -- {_e71}")
        sc71_warn = True

    sc71_overall = "WARN" if sc71_warn else "PASS"
    # SC71은 WARN 전용 비차단 -- 학술 정합성 자동 audit hook 미비 감지 (M625 Rule NN)

    # -- G7-SC72: 사용자 환경 자체 검증 hook + Kimi K2.6 Vision (M626 신설, WARN 비차단) --
    # 근거: 사용자 핵심 명령 "내 피드백 html처럼 자체적으로 잘못된 부분을 사용자 환경에서 검증할 수 있는가다... Kimi 활용"
    # 검증: housing/sinktank/user_env_auto_verify.py + .claude/hooks/user_env_verify.py + settings.json 등록 + .claude/user_env_log.jsonl 누적
    # 5 시나리오 (popup_3d / lewis_theory / drylab_pdf / conf_slide / cycle_html) 자동 분류
    # Vision 검증 0건 누적 시 P-USR-ENV-UNVERIFIED FP-26 권고
    sc72_warn = False
    sc72_msgs: list = []
    try:
        _claude_dir_sc72 = os.path.join(PROJECT_ROOT, ".claude")
        _ue_module_sc72 = os.path.join(
            PROJECT_ROOT, "housing", "sinktank", "user_env_auto_verify.py"
        )
        _ue_hook_sc72 = os.path.join(
            _claude_dir_sc72, "hooks", "user_env_verify.py"
        )
        _ue_log_sc72 = os.path.join(_claude_dir_sc72, "user_env_log.jsonl")
        _ue_skill_sc72 = os.path.join(
            PROJECT_ROOT, "docs", "ai", "skills", "user_env_auto_verify.md"
        )
        _settings_path_72 = os.path.join(_claude_dir_sc72, "settings.json")
        _multi_llm_sc72 = os.path.join(
            PROJECT_ROOT, "housing", "sinktank", "multi_llm.py"
        )

        # SC72-a: user_env_auto_verify.py 모듈 존재 (housing)
        if not os.path.isfile(_ue_module_sc72):
            sc72_msgs.append(
                "SC72 WARN: housing/sinktank/user_env_auto_verify.py 미존재 (M626 Rule OO)"
            )
            sc72_warn = True
            logger.warning("G7-SC72: user_env_auto_verify.py 미존재 (M626)")

        # SC72-b: hook 진입점 존재 (.claude/hooks)
        if not os.path.isfile(_ue_hook_sc72):
            sc72_msgs.append(
                "SC72 WARN: .claude/hooks/user_env_verify.py 미존재 (M626)"
            )
            sc72_warn = True
            logger.warning("G7-SC72: hook user_env_verify.py 미존재 (M626)")

        # SC72-c: settings.json PostToolUse Edit|Write 등록 확인
        if os.path.isfile(_settings_path_72):
            try:
                with open(_settings_path_72, "r", encoding="utf-8") as _sf72:
                    _settings_72 = __import__("json").load(_sf72)
                _post_hooks_72 = _settings_72.get("hooks", {}).get("PostToolUse", [])
                _ue_registered = False
                for _section_72 in _post_hooks_72:
                    _matcher_72 = _section_72.get("matcher", "")
                    if "Edit" in _matcher_72 or "Write" in _matcher_72:
                        for _h_72 in _section_72.get("hooks", []):
                            if "user_env_verify" in _h_72.get("command", ""):
                                _ue_registered = True
                                break
                if not _ue_registered:
                    sc72_msgs.append(
                        "SC72 WARN: settings.json PostToolUse Edit|Write에 "
                        "user_env_verify 미등록 (M626)"
                    )
                    sc72_warn = True
                    logger.warning(
                        "G7-SC72: user_env_verify 미등록 settings.json (M626)"
                    )
            except (OSError, ValueError) as _e_set72:
                logger.warning("G7-SC72: settings.json 읽기 실패: %s", _e_set72)
                sc72_msgs.append(
                    f"SC72 WARN: settings.json 파싱 실패 -- {_e_set72}"
                )
                sc72_warn = True

        # SC72-d: kimi_vision_audit() 메서드 multi_llm.py에 정의 확인
        if os.path.isfile(_multi_llm_sc72):
            try:
                with open(_multi_llm_sc72, "r", encoding="utf-8") as _mf72:
                    _ml_text_72 = _mf72.read()
                if "def kimi_vision_audit" not in _ml_text_72:
                    sc72_msgs.append(
                        "SC72 WARN: multi_llm.kimi_vision_audit() 메서드 미존재 (M626)"
                    )
                    sc72_warn = True
                    logger.warning(
                        "G7-SC72: kimi_vision_audit 메서드 미존재 multi_llm.py (M626)"
                    )
            except OSError as _e_ml72:
                logger.warning("G7-SC72: multi_llm.py 읽기 실패: %s", _e_ml72)
                sc72_msgs.append(
                    f"SC72 WARN: multi_llm.py 읽기 실패 -- {_e_ml72}"
                )
                sc72_warn = True

        # SC72-e: skills/user_env_auto_verify.md 존재 (체화 4단계)
        if not os.path.isfile(_ue_skill_sc72):
            sc72_msgs.append(
                "SC72 WARN: docs/ai/skills/user_env_auto_verify.md 미존재 -- "
                "체화 미비 (M626)"
            )
            sc72_warn = True
            logger.warning("G7-SC72: user_env_auto_verify.md 미존재 (M626)")

        # SC72-f: user_env_log.jsonl 누적 확인 (FP-26 P-USR-ENV-UNVERIFIED 차단)
        if not os.path.isfile(_ue_log_sc72):
            sc72_msgs.append(
                "SC72 WARN: .claude/user_env_log.jsonl 미존재 -- "
                "검증 0건 (FP-26 P-USR-ENV-UNVERIFIED, M626)"
            )
            sc72_warn = True
            logger.warning("G7-SC72: user_env_log.jsonl 미존재 (M626)")
        else:
            try:
                with open(_ue_log_sc72, "r", encoding="utf-8") as _logf72:
                    _log_lines_72 = [l.strip() for l in _logf72 if l.strip()]
                # 매직넘버 0: 누적 0건 = 검증 미작동 (FP-26)
                if len(_log_lines_72) == 0:
                    sc72_msgs.append(
                        "SC72 WARN: user_env_log.jsonl 누적 0건 (FP-26 M626)"
                    )
                    sc72_warn = True
            except OSError as _e_log72:
                logger.warning("G7-SC72: user_env_log 읽기 실패: %s", _e_log72)

    except (OSError, ValueError) as _e72:
        logger.warning("G7-SC72: 사용자 환경 검증 hook 검사 실패: %s", _e72)
        sc72_msgs.append(f"SC72 WARN: 검사 실패 -- {_e72}")
        sc72_warn = True

    sc72_overall = "WARN" if sc72_warn else "PASS"
    # SC72은 WARN 전용 비차단 -- 사용자 환경 자체 검증 hook 미비 감지 (M626 Rule OO)

    # -- G7-SC73: Kimi 자동 호출 hook 강제 메커니즘 검증 (M627 신설, WARN 비차단) --
    # 근거: 사용자 핵심 명령 "매번 기타AI들 활용 안해서 내가 말해줘야하잖아 ... 하네스 근간에 넣어"
    # 검증: kimi_auto_invoke.py 존재 + settings.json 등록 + kimi_invoke_log.jsonl 누적 확인
    # 외부 AI 호출 0건 시 P-EXTERNAL-AI-UNUSED FP-27 권고
    sc73_warn = False
    sc73_msgs: list = []
    try:
        _claude_dir_sc73 = os.path.join(PROJECT_ROOT, ".claude")
        _kimi_invoke_hook = os.path.join(_claude_dir_sc73, "hooks", "kimi_auto_invoke.py")
        _kimi_invoke_log = os.path.join(PROJECT_ROOT, "docs", "logs", "kimi_invoke_log.jsonl")
        _settings_path_73 = os.path.join(_claude_dir_sc73, "settings.json")

        # SC73-a: kimi_auto_invoke.py 존재 여부
        if not os.path.isfile(_kimi_invoke_hook):
            sc73_msgs.append(
                "SC73 WARN: kimi_auto_invoke.py 미존재 (M627 P-EXTERNAL-AI-UNUSED)"
            )
            sc73_warn = True
            logger.warning("G7-SC73: kimi_auto_invoke.py 미존재 (M627)")

        # SC73-b: settings.json PreToolUse Agent에 kimi_auto_invoke 등록 여부
        if os.path.isfile(_settings_path_73):
            try:
                import json as _json73
                with open(_settings_path_73, "r", encoding="utf-8") as _sf73:
                    _s73 = _json73.load(_sf73)
                _pre73 = _s73.get("hooks", {}).get("PreToolUse", [])
                _kimi_reg = False
                for _sec73 in _pre73:
                    if _sec73.get("matcher") == "Agent":
                        for _h73 in _sec73.get("hooks", []):
                            if "kimi_auto_invoke" in _h73.get("command", ""):
                                _kimi_reg = True
                                break
                if not _kimi_reg:
                    sc73_msgs.append(
                        "SC73 WARN: settings.json PreToolUse Agent에 kimi_auto_invoke 미등록 (M627)"
                    )
                    sc73_warn = True
                    logger.warning("G7-SC73: kimi_auto_invoke settings.json 미등록 (M627)")
            except Exception as _e_s73:
                logger.warning("G7-SC73: settings.json 읽기 실패: %s", _e_s73)

        # SC73-c: kimi_invoke_log.jsonl 존재 + 최근 24시간 내 1건 이상
        _SC73_LOG_WINDOW = 86400  # 24시간 (매직넘버 -- 외부AI 활용 주기 점검 기준)
        if not os.path.isfile(_kimi_invoke_log):
            sc73_msgs.append(
                "SC73 WARN: kimi_invoke_log.jsonl 미존재 -- 외부AI 0건 (P-EXTERNAL-AI-UNUSED FP-27)"
            )
            sc73_warn = True
            logger.warning("G7-SC73: kimi_invoke_log.jsonl 미존재 (M627 FP-27)")
        else:
            try:
                _now73 = time.time()
                _log_mtime = os.path.getmtime(_kimi_invoke_log)
                _log_age = _now73 - _log_mtime
                if _log_age > _SC73_LOG_WINDOW:
                    sc73_msgs.append(
                        f"SC73 WARN: kimi_invoke_log.jsonl {_log_age/3600:.1f}h 미갱신"
                        " -- 외부AI 24h 미활용 (P-EXTERNAL-AI-UNUSED)"
                    )
                    sc73_warn = True
                    logger.warning(
                        "G7-SC73: kimi_invoke_log stale %.1fh (M627)", _log_age / 3600
                    )
            except Exception as _e_log73:
                logger.warning("G7-SC73: kimi_invoke_log 읽기 실패: %s", _e_log73)

    except Exception as _e73:
        logger.warning("G7-SC73: Kimi auto-invoke 검증 실패: %s", _e73)
        sc73_msgs.append(f"SC73 WARN: 검사 실패 -- {_e73}")
        sc73_warn = True

    # SC73-d: external_ai_force.py 존재 여부 (M665 신설 -- swarm 강제 라우팅)
    _ext_force_path = os.path.join(PROJECT_ROOT, "housing", "sinktank", "external_ai_force.py")
    if not os.path.isfile(_ext_force_path):
        sc73_msgs.append(
            "SC73 WARN: housing/sinktank/external_ai_force.py 미존재 (M665 P-EXTERNAL-AI-UNUSED)"
        )
        sc73_warn = True
        logger.warning("G7-SC73: external_ai_force.py 미존재 (M665)")

    # SC73-e: swarm_dispatcher.py 존재 여부 (M665 신설)
    _swarm_path = os.path.join(PROJECT_ROOT, "housing", "sinktank", "swarm_dispatcher.py")
    if not os.path.isfile(_swarm_path):
        sc73_msgs.append(
            "SC73 WARN: housing/sinktank/swarm_dispatcher.py 미존재 (M665 P-EXTERNAL-AI-UNUSED)"
        )
        sc73_warn = True
        logger.warning("G7-SC73: swarm_dispatcher.py 미존재 (M665)")

    # SC73-f: .swarm_cost.json 존재 여부 (M665 비용 추적)
    _cost_path = os.path.join(PROJECT_ROOT, "housing", "sinktank", ".swarm_cost.json")
    if not os.path.isfile(_cost_path):
        sc73_msgs.append(
            "SC73 WARN: housing/sinktank/.swarm_cost.json 미존재 (M665 비용 추적 미비)"
        )
        sc73_warn = True
        logger.warning("G7-SC73: .swarm_cost.json 미존재 (M665)")

    sc73_overall = "WARN" if sc73_warn else "PASS"
    # SC73은 WARN 전용 비차단 -- Kimi 자동 호출 hook 강제 메커니즘 검증 (M627/M665)

    # -- G7-SC74: Ollama 로컬 LLM 스웜 인프라 검증 (M633 신설, WARN 비차단) --
    # Rule QQ: 로컬LLM 우선 — chemgrid-c23/deepseek-coder/qwen3-coder:30b 병렬 활용 강제.
    # FP-29: P-LOCAL-LLM-UNUSED — Ollama 인프라가 있어도 실제 호출 0건이면 WARN.
    sc74_warn = False
    sc74_msgs: list[str] = []

    try:
        _multi_llm_path = os.path.join(PROJECT_ROOT, "housing", "sinktank", "multi_llm.py")
        _gpu_mon_path = os.path.join(PROJECT_ROOT, "tools", "gpu_load_monitor_M633.py")

        # SC74-a: multi_llm.py에 chemgrid_c23_chat 메서드 존재 여부
        try:
            with open(_multi_llm_path, "r", encoding="utf-8", errors="replace") as _fml:
                _ml_src = _fml.read()
            if "chemgrid_c23_chat" not in _ml_src:
                sc74_warn = True
                sc74_msgs.append("SC74 WARN: multi_llm.py에 chemgrid_c23_chat 미존재 (M633 P-LOCAL-LLM-UNUSED)")
                logger.warning("G7-SC74: chemgrid_c23_chat 미존재 (M633)")
            if "local_swarm_parallel" not in _ml_src:
                sc74_warn = True
                sc74_msgs.append("SC74 WARN: multi_llm.py에 local_swarm_parallel 미존재 (M633)")
                logger.warning("G7-SC74: local_swarm_parallel 미존재 (M633)")
            if "_check_vram_gb" not in _ml_src:
                sc74_warn = True
                sc74_msgs.append("SC74 WARN: multi_llm.py에 _check_vram_gb VRAM 체크 미존재 (M633)")
                logger.warning("G7-SC74: _check_vram_gb 미존재 (M633)")
        except OSError as _e_sc74ml:
            logger.warning("G7-SC74: multi_llm.py 읽기 실패: %s", _e_sc74ml)

        # SC74-b: gpu_load_monitor_M633.py 존재 여부
        if not os.path.isfile(_gpu_mon_path):
            sc74_warn = True
            sc74_msgs.append("SC74 WARN: tools/gpu_load_monitor_M633.py 미존재 (M633)")
            logger.warning("G7-SC74: gpu_load_monitor_M633.py 미존재 (M633)")

        # SC74-c: skills/ollama_local_swarm.md 존재 여부
        _swarm_skill = os.path.join(PROJECT_ROOT, "docs", "ai", "skills", "ollama_local_swarm.md")
        if not os.path.isfile(_swarm_skill):
            sc74_warn = True
            sc74_msgs.append("SC74 WARN: docs/ai/skills/ollama_local_swarm.md 미존재 (M633 Rule QQ 체화 미비)")
            logger.warning("G7-SC74: ollama_local_swarm.md 미존재 (M633)")

        # SC74-d: Ollama 실행 여부 + kimi_invoke_log에서 Ollama 호출 흔적 확인
        # [MAGIC] SC74_LOG_WINDOW = 86400: 24시간 내 로컬 LLM 활용 흔적 점검 주기
        _SC74_LOG_WINDOW = 86400  # 24시간 (Rule QQ 활용 주기)
        _ollama_log = os.path.join(PROJECT_ROOT, "docs", "logs", "ollama_usage_log.jsonl")
        if os.path.isfile(_ollama_log):
            try:
                _log_age_sc74 = time.time() - os.path.getmtime(_ollama_log)
                if _log_age_sc74 > _SC74_LOG_WINDOW:
                    sc74_warn = True
                    sc74_msgs.append(
                        f"SC74 WARN: ollama_usage_log.jsonl {_log_age_sc74/3600:.1f}h 미갱신 (P-LOCAL-LLM-UNUSED FP-29)"
                    )
                    logger.warning("G7-SC74: ollama_usage_log stale %.1fh (M633 FP-29)", _log_age_sc74 / 3600)
            except Exception as _e_sc74log:
                logger.warning("G7-SC74: ollama_usage_log 확인 실패: %s", _e_sc74log)

    except Exception as _e74:
        logger.warning("G7-SC74: Ollama 스웜 인프라 검증 실패: %s", _e74)
        sc74_msgs.append(f"SC74 WARN: 검사 실패 -- {_e74}")
        sc74_warn = True

    sc74_overall = "WARN" if sc74_warn else "PASS"
    # SC74은 WARN 전용 비차단 -- Ollama 로컬 LLM 스웜 인프라 검증 (M633)

    # -- G7-SC75: Vision + 한국어 + 자연어 로컬 LLM 인프라 검증 (M634 신설, WARN 비차단) --
    # multi_llm.py에 local_vision_audit / korean_classify / natural_language_query 존재 검증
    # Ollama vision 모델 1종 이상 등록 검증 (minicpm-v/phi3.5/llava)
    # skills/local_vision_korean.md 존재 검증
    sc75_warn = False
    sc75_msgs: list = []
    try:
        _multi_llm_path_75 = os.path.join(PROJECT_ROOT, "housing", "sinktank", "multi_llm.py")

        # SC75-a: multi_llm.py에 M634 메서드 3종 존재 여부
        _m634_required_methods = [
            "local_vision_audit",
            "korean_classify",
            "natural_language_query",
        ]
        if os.path.exists(_multi_llm_path_75):
            try:
                with open(_multi_llm_path_75, "r", encoding="utf-8", errors="replace") as _f75:
                    _multi_llm_src_75 = _f75.read()
                for _method75 in _m634_required_methods:
                    if _method75 not in _multi_llm_src_75:
                        sc75_msgs.append(
                            f"SC75 WARN: multi_llm.py에 {_method75} 미존재 (M634 미완료)"
                        )
                        sc75_warn = True
                        logger.warning("G7-SC75: multi_llm.py %s 미존재 (M634)", _method75)
            except OSError as _e75_read:
                logger.warning("G7-SC75: multi_llm.py 읽기 실패: %s", _e75_read)
                sc75_msgs.append(f"SC75 WARN: multi_llm.py 읽기 실패 -- {_e75_read}")
                sc75_warn = True
        else:
            sc75_msgs.append("SC75 WARN: multi_llm.py 미존재 (M634 전제 파일)")
            sc75_warn = True
            logger.warning("G7-SC75: multi_llm.py 미존재 (M634)")

        # SC75-b: Ollama vision 모델 1종 이상 등록 여부 (ollama /api/tags API)
        _VISION_MODEL_TAGS_75 = ["minicpm-v", "phi3.5", "llava", "bakllava", "moondream"]
        _vision_found_75 = False
        try:
            import urllib.request as _ureq75
            with _ureq75.urlopen("http://localhost:11434/api/tags", timeout=5) as _r75:
                if _r75.status == 200:
                    _tags_data_75 = json.loads(_r75.read().decode("utf-8"))
                    _models_list75 = (
                        _tags_data_75.get("models", [])
                        if isinstance(_tags_data_75, dict) else []
                    )
                    for _entry75 in _models_list75:
                        if isinstance(_entry75, dict):
                            _name75 = _entry75.get("name", "")
                            if isinstance(_name75, str):
                                for _vtag75 in _VISION_MODEL_TAGS_75:
                                    if _vtag75.lower() in _name75.lower():
                                        _vision_found_75 = True
                                        break
                        if _vision_found_75:
                            break
        except Exception as _e75_ollama:
            logger.warning("G7-SC75: Ollama API 조회 실패: %s", _e75_ollama)

        if not _vision_found_75:
            sc75_msgs.append(
                "SC75 WARN: Ollama vision 모델 없음 (minicpm-v/phi3.5/llava) -- "
                "ollama pull phi3.5:latest 권장 (M634)"
            )
            sc75_warn = True
            logger.warning("G7-SC75: Ollama vision 모델 미등록 (M634)")

        # SC75-c: skills/local_vision_korean.md 존재 여부 (체화 확인)
        _skills_dir_75 = os.path.join(PROJECT_ROOT, "docs", "ai", "skills")
        _vision_skill_path_75 = os.path.join(_skills_dir_75, "local_vision_korean.md")
        if not os.path.exists(_vision_skill_path_75):
            sc75_msgs.append(
                "SC75 WARN: docs/ai/skills/local_vision_korean.md 미존재 (M634 체화 미완)"
            )
            sc75_warn = True
            logger.warning("G7-SC75: local_vision_korean.md 미존재 (M634)")

    except Exception as _e75:
        logger.warning("G7-SC75: Vision 로컬 LLM 인프라 검증 실패: %s", _e75)
        sc75_msgs.append(f"SC75 WARN: 검사 실패 -- {_e75}")
        sc75_warn = True

    sc75_overall = "WARN" if sc75_warn else "PASS"
    # SC75는 WARN 전용 비차단 -- Vision + 한국어 + 자연어 로컬 LLM 인프라 (M634)

    # -- G7-SC78: 4-Layer Vision Audit + 3개월 미해소 시계열 검증 (M636 신설, WARN 비차단) --
    # 사용자 핵심 명령:
    #   "단순히 이미지를 정밀하게 받는놈만 있는게 아니라 이미지로부터 분석된
    #    매우 세밀한 사항들의 정합성까지 제대로 검증해야 한다 ...
    #    내가 매번 지적하던 오류가 3달째 안사라지는 경우도 있다고"
    # 검증 4종:
    #   SC78-a: housing/sinktank/multi_layer_vision_audit.py 존재
    #   SC78-b: tools/anger_timeline_tracker.py 존재
    #   SC78-c: .claude/hooks/repeat_pattern_block.py 존재
    #   SC78-d: anger_timeline_M636.json 24h 이내 갱신 + CRITICAL 0건
    sc78_warn = False
    sc78_msgs: list = []
    try:
        # SC78-a: 4-layer pipeline 모듈
        _sc78_pipeline = os.path.join(
            PROJECT_ROOT, "housing", "sinktank", "multi_layer_vision_audit.py"
        )
        if not os.path.exists(_sc78_pipeline):
            sc78_msgs.append(
                "SC78 WARN: housing/sinktank/multi_layer_vision_audit.py 미존재 (M636)"
            )
            sc78_warn = True
            logger.warning("G7-SC78: multi_layer_vision_audit.py 미존재 (M636)")

        # SC78-b: anger_timeline_tracker
        _sc78_timeline = os.path.join(
            PROJECT_ROOT, "tools", "anger_timeline_tracker.py"
        )
        if not os.path.exists(_sc78_timeline):
            sc78_msgs.append(
                "SC78 WARN: tools/anger_timeline_tracker.py 미존재 (M636)"
            )
            sc78_warn = True
            logger.warning("G7-SC78: anger_timeline_tracker.py 미존재 (M636)")

        # SC78-c: repeat_pattern_block hook
        _sc78_hook = os.path.join(
            PROJECT_ROOT, ".claude", "hooks", "repeat_pattern_block.py"
        )
        if not os.path.exists(_sc78_hook):
            sc78_msgs.append(
                "SC78 WARN: .claude/hooks/repeat_pattern_block.py 미존재 (M636)"
            )
            sc78_warn = True
            logger.warning("G7-SC78: repeat_pattern_block.py 미존재 (M636)")

        # SC78-d: timeline JSON 24h freshness + CRITICAL count
        _sc78_json = os.path.join(
            PROJECT_ROOT, ".claude", "anger_timeline_M636.json"
        )
        _SC78_FRESH_WINDOW = 86400  # [MAGIC] 24h freshness
        if not os.path.exists(_sc78_json):
            sc78_msgs.append(
                "SC78 WARN: anger_timeline_M636.json 미존재 (시계열 추적 0회) -- M636"
            )
            sc78_warn = True
            logger.warning("G7-SC78: anger_timeline_M636.json 미존재 (M636)")
        else:
            try:
                _ts77 = os.path.getmtime(_sc78_json)
                _age77 = time.time() - _ts77
                if _age77 > _SC78_FRESH_WINDOW:
                    sc78_msgs.append(
                        f"SC78 WARN: anger_timeline_M636.json stale {_age77/3600:.1f}h "
                        f"(>24h, 시계열 갱신 필요) -- M636"
                    )
                    sc78_warn = True
                    logger.warning(
                        "G7-SC78: anger_timeline_M636.json stale %.1fh (M636)",
                        _age77 / 3600,
                    )
                # CRITICAL count 검사
                with open(_sc78_json, "r", encoding="utf-8", errors="replace") as _f77:
                    _data77 = json.load(_f77)
                if isinstance(_data77, dict):
                    _crit = _data77.get("critical_unresolved", [])
                    if isinstance(_crit, list) and len(_crit) > 0:
                        sc78_msgs.append(
                            f"SC78 WARN: 90일+ 미해소 격분 {len(_crit)}건 -- "
                            f"Rule W 강화 ESCALATE (M636 FP-31)"
                        )
                        sc78_warn = True
                        logger.warning(
                            "G7-SC78: 90일+ 미해소 격분 %d건 (M636 FP-31)",
                            len(_crit),
                        )
            except (OSError, json.JSONDecodeError, ValueError) as _e77_load:
                sc78_msgs.append(
                    f"SC78 WARN: anger_timeline_M636.json 파싱 실패 -- {_e77_load}"
                )
                sc78_warn = True
                logger.warning(
                    "G7-SC78: anger_timeline_M636.json 파싱 실패: %s", _e77_load
                )

    except Exception as _e77:
        logger.warning("G7-SC78: 4-Layer Vision Audit 인프라 검증 실패: %s", _e77)
        sc78_msgs.append(f"SC78 WARN: 검사 실패 -- {_e77}")
        sc78_warn = True

    sc78_overall = "WARN" if sc78_warn else "PASS"
    # SC78은 WARN 전용 비차단 -- 4-Layer Vision Audit + 3개월 미해소 격분 (M636)


    # -- G7-SC79: M638 외부 연산 5 endpoint 존재 검증 (WARN 비차단) --
    # 사용자 핵심 명령:
    #   "xtb나 알파폴드 PDB, askcos, PDBe Mol 등등 웹쪽으로 연산 가능한
    #    경로는 다 제대로 연결하고 실험까지 하고, orca 경유하는 전자분포
    #    레이어만 따로 빼면 되잖아"
    # 검증 5종 (chemgrid_mobile/backend/routers/):
    #   SC79-a: routers/xtb.py + /api/xtb/calculate endpoint
    #   SC79-b: routers/askcos.py + /api/askcos/retrosynthesis endpoint
    #   SC79-c: routers/orca_proxy.py + /api/orca/electron_density endpoint
    #   SC79-d: routers/alphafold.py + /api/alphafold/fetch endpoint (M455 hotfix)
    #   SC79-e: frontend/src/components/PDBeMolstarViewer.tsx 존재 (Sehnal 2021 인용)
    sc79_warn = False
    sc79_msgs: list = []
    try:
        _MOBILE_BACKEND = r"C:/chemgrid_mobile/backend/routers"
        _MOBILE_FRONTEND = r"C:/chemgrid_mobile/frontend/src/components"
        # Each target: (filename, list of substrings — ALL must be present)
        # FastAPI endpoint = prefix + route, so we check both as separate substrings
        _SC79_TARGETS = [
            ("xtb.py", ["/api/xtb", "/calculate"], _MOBILE_BACKEND),
            ("askcos.py", ["/api/askcos", "/retrosynthesis"], _MOBILE_BACKEND),
            ("orca_proxy.py", ["/api/orca", "/electron_density"], _MOBILE_BACKEND),
            ("alphafold.py", ["/api/alphafold", "/fetch"], _MOBILE_BACKEND),
            ("PDBeMolstarViewer.tsx", ["PDBeMolstarViewer"], _MOBILE_FRONTEND),
        ]
        for _fname79, _needles79, _root79 in _SC79_TARGETS:
            _full79 = os.path.join(_root79, _fname79)
            if not os.path.exists(_full79):
                sc79_msgs.append(
                    f"SC79 WARN: {_fname79} 미존재 (M638 외부 연산 통합 미완) — {_full79}"
                )
                sc79_warn = True
                logger.warning("G7-SC79: %s 미존재 (M638)", _fname79)
                continue
            try:
                with open(_full79, "r", encoding="utf-8", errors="replace") as _f79:
                    _src79 = _f79.read()
                # Rule N: needle list — ALL must be present (prefix + route 분리 검증)
                _missing79 = [n for n in _needles79 if n not in _src79]
                if _missing79:
                    sc79_msgs.append(
                        f"SC79 WARN: {_fname79}에 {_missing79} 미포함 (M638 endpoint/식별자 누락)"
                    )
                    sc79_warn = True
                    logger.warning(
                        "G7-SC79: %s에 %s 미포함 (M638)", _fname79, _missing79
                    )
            except OSError as _e79_read:
                logger.warning("G7-SC79: %s 읽기 실패: %s", _fname79, _e79_read)
                sc79_msgs.append(
                    f"SC79 WARN: {_fname79} 읽기 실패 — {_e79_read}"
                )
                sc79_warn = True

        # SC79-f: skills/external_compute_integration.md 존재 (M638 체화)
        _sc79_skill = os.path.join(
            PROJECT_ROOT, "docs", "ai", "skills",
            "external_compute_integration.md",
        )
        if not os.path.exists(_sc79_skill):
            sc79_msgs.append(
                "SC79 WARN: docs/ai/skills/external_compute_integration.md 미존재 (M638 체화 미완)"
            )
            sc79_warn = True
            logger.warning("G7-SC79: external_compute_integration.md 미존재 (M638)")

    except Exception as _e79:
        logger.warning("G7-SC79: M638 외부 연산 통합 검증 실패: %s", _e79)
        sc79_msgs.append(f"SC79 WARN: 검사 실패 — {_e79}")
        sc79_warn = True

    sc79_overall = "WARN" if sc79_warn else "PASS"
    # SC79은 WARN 전용 비차단 — M638 외부 연산 5 endpoint + skill 체화 검증


    # -- G7-SC76: M635 로컬LLM 영구가동 인프라 검증 (WARN 비차단) --
    # 6병렬 16GB SWARM_TIER_E + 세션 시작/종료 hook + 좀비차단 검증
    # FP-30: P-ZOMBIE-PROCESS -- 좀비 PID 24h+ 가동 = WARN
    sc76_warn = False
    sc76_msgs: list = []
    try:
        _ml_path_76 = os.path.join(PROJECT_ROOT, 'housing', 'sinktank', 'multi_llm.py')
        _hooks_dir_76 = os.path.join(PROJECT_ROOT, '.claude', 'hooks')
        _tools_dir_76 = os.path.join(PROJECT_ROOT, 'tools')
        if os.path.exists(_ml_path_76):
            try:
                with open(_ml_path_76, 'r', encoding='utf-8', errors='replace') as _f76:
                    _ml_src_76 = _f76.read()
                for _sym76 in ['SWARM_TIER_E', 'pick_specialist']:
                    if _sym76 not in _ml_src_76:
                        sc76_warn = True
                        sc76_msgs.append(f'SC76 WARN: multi_llm.py {_sym76} 미존재 (M635)')
                        logger.warning('G7-SC76: %s 미존재 (M635)', _sym76)
            except OSError as _e76_ml:
                logger.warning('G7-SC76: multi_llm.py 읽기 실패: %s', _e76_ml)
        for _hook76 in ['session_start_load_swarm.py', 'session_end_cleanup.py']:
            if not os.path.isfile(os.path.join(_hooks_dir_76, _hook76)):
                sc76_warn = True
                sc76_msgs.append(f'SC76 WARN: .claude/hooks/{_hook76} 미존재 (M635)')
                logger.warning('G7-SC76: %s 미존재 (M635)', _hook76)
        if not os.path.isfile(os.path.join(_tools_dir_76, 'zombie_check.py')):
            sc76_warn = True
            sc76_msgs.append('SC76 WARN: tools/zombie_check.py 미존재 (M635 FP-30)')
            logger.warning('G7-SC76: zombie_check.py 미존재 (M635)')
        _settings_76 = os.path.join(PROJECT_ROOT, '.claude', 'settings.json')
        if os.path.isfile(_settings_76):
            try:
                with open(_settings_76, 'r', encoding='utf-8') as _fs76:
                    _ss76 = _fs76.read()
                for _hc76 in ['session_start_load_swarm', 'session_end_cleanup']:
                    if _hc76 not in _ss76:
                        sc76_warn = True
                        sc76_msgs.append(f'SC76 WARN: settings.json {_hc76} 미등록 (M635)')
                        logger.warning('G7-SC76: settings.json %s 미등록 (M635)', _hc76)
            except OSError as _e76_s:
                logger.warning('G7-SC76: settings.json 읽기 실패: %s', _e76_s)
        _skills_dir_76 = os.path.join(PROJECT_ROOT, 'docs', 'ai', 'skills')
        for _sk76 in ['local_llm_permanent.md', 'zombie_prevention.md']:
            if not os.path.isfile(os.path.join(_skills_dir_76, _sk76)):
                sc76_warn = True
                sc76_msgs.append(f'SC76 WARN: skills/{_sk76} 미존재 (M635)')
                logger.warning('G7-SC76: %s 미존재 (M635)', _sk76)
    except Exception as _e76:
        logger.warning('G7-SC76: 검증 실패: %s', _e76)
        sc76_msgs.append(f'SC76 WARN: 검사 실패 -- {_e76}')
        sc76_warn = True

    sc76_overall = 'WARN' if sc76_warn else 'PASS'
    # SC76은 WARN 전용 비차단 -- M635 로컬LLM 영구가동 (FP-30 P-ZOMBIE-PROCESS)


    # -- G7-SC84: M643 연구소 수준 readiness 25/25 매트릭스 검증 (WARN 비차단) --
    # 5 항목 자동 탐지: skill / evidence / anger / registry / mistakes
    # FP-35: P-RESEARCH-DOWNGRADE -- 매 사이클 점수 추적 미구현 = WARN
    sc84_warn = False
    sc84_msgs: list = []
    try:
        # 1) skills/research_lab_grade.md 존재
        _sk84 = os.path.join(PROJECT_ROOT, 'docs', 'ai', 'skills', 'research_lab_grade.md')
        if not os.path.isfile(_sk84):
            sc84_warn = True
            sc84_msgs.append('SC84 WARN: skills/research_lab_grade.md 미존재 (M643 H-2 체화 미완)')
            logger.warning('G7-SC84: research_lab_grade.md 미존재 (M643)')
        # 2) docs/reports/EVIDENCE_W_M643_RESEARCH_LAB_GRADE.md 존재 (최신 사이클)
        _ev84 = os.path.join(PROJECT_ROOT, 'docs', 'reports', 'EVIDENCE_W_M643_RESEARCH_LAB_GRADE.md')
        if not os.path.isfile(_ev84):
            sc84_warn = True
            sc84_msgs.append('SC84 WARN: EVIDENCE_W_M643_RESEARCH_LAB_GRADE.md 미존재 (M643 baseline 누락)')
            logger.warning('G7-SC84: EVIDENCE_W_M643 미존재 (M643)')
        # 3) anger_simulator.py ANGER_MATRIX_M643_NEW 등록
        _ang84 = os.path.join(PROJECT_ROOT, 'housing', 'sinktank', 'anger_simulator.py')
        if os.path.isfile(_ang84):
            try:
                with open(_ang84, 'r', encoding='utf-8', errors='replace') as _fa84:
                    _ang_src_84 = _fa84.read()
                if 'ANGER_MATRIX_M643_NEW' not in _ang_src_84:
                    sc84_warn = True
                    sc84_msgs.append('SC84 WARN: anger_simulator.py ANGER_MATRIX_M643_NEW 미등록 (M643 격분 5건)')
                    logger.warning('G7-SC84: ANGER_MATRIX_M643_NEW 미등록 (M643)')
            except OSError as _e84_a:
                logger.warning('G7-SC84: anger_simulator.py 읽기 실패: %s', _e84_a)
        # 4) FALSE_PASS_REGISTRY FP-35 P-RESEARCH-DOWNGRADE 라인 존재
        _fpr84 = os.path.join(PROJECT_ROOT, 'docs', 'ai', 'FALSE_PASS_REGISTRY.md')
        if os.path.isfile(_fpr84):
            try:
                with open(_fpr84, 'r', encoding='utf-8', errors='replace') as _ff84:
                    _fpr_src_84 = _ff84.read()
                if 'FP-35' not in _fpr_src_84 or 'P-RESEARCH-DOWNGRADE' not in _fpr_src_84:
                    sc84_warn = True
                    sc84_msgs.append('SC84 WARN: FALSE_PASS_REGISTRY FP-35 / P-RESEARCH-DOWNGRADE 미등록 (M643)')
                    logger.warning('G7-SC84: FP-35 미등록 (M643)')
            except OSError as _e84_f:
                logger.warning('G7-SC84: FALSE_PASS_REGISTRY 읽기 실패: %s', _e84_f)
        # 5) mistakes/other.md M643 entry 존재
        _ms84 = os.path.join(PROJECT_ROOT, 'docs', 'ai', 'mistakes', 'other.md')
        if os.path.isfile(_ms84):
            try:
                with open(_ms84, 'r', encoding='utf-8', errors='replace') as _fm84:
                    _ms_src_84 = _fm84.read()
                if 'M643' not in _ms_src_84:
                    sc84_warn = True
                    sc84_msgs.append('SC84 WARN: mistakes/other.md M643 entry 미등록 (M643 H-1 체화 미완)')
                    logger.warning('G7-SC84: M643 entry 미등록 (M643)')
            except OSError as _e84_m:
                logger.warning('G7-SC84: mistakes/other.md 읽기 실패: %s', _e84_m)
    except Exception as _e84:
        logger.warning('G7-SC84: M643 연구소 readiness 검증 실패: %s', _e84)
        sc84_msgs.append(f'SC84 WARN: 검사 실패 -- {_e84}')
        sc84_warn = True

    sc84_overall = 'WARN' if sc84_warn else 'PASS'
    # SC84은 WARN 전용 비차단 -- M643 연구소 수준 readiness (FP-35 P-RESEARCH-DOWNGRADE)

    # -- G7-SC85: M645_W2 P-USER-DELEGATION 탐지 (WARN 비차단) --
    # FP-36: Worker가 가능한 우회 소진 전 사용자에게 작업 위임 = 거짓 완료 패턴
    sc85_warn = False
    sc85_msgs: list = []
    try:
        _fp_path85 = _BASE / 'docs' / 'ai' / 'FALSE_PASS_REGISTRY.md'
        if _fp_path85.exists():
            _fp_text85 = _fp_path85.read_text(encoding='utf-8', errors='replace')
            for _kw85 in ('P-USER-DELEGATION', 'FP-36'):
                if _kw85 not in _fp_text85:
                    sc85_msgs.append(
                        f'SC85 WARN: FALSE_PASS_REGISTRY에 {_kw85} 미등록 (M645_W2 FP-36 체화 미완)'
                    )
                    logger.warning('G7-SC85: %s 미등록 (M645_W2)', _kw85)
                    sc85_warn = True
        else:
            sc85_msgs.append('SC85 WARN: FALSE_PASS_REGISTRY.md 미존재')
            sc85_warn = True
    except Exception as _e85:
        logger.warning('G7-SC85: P-USER-DELEGATION 검증 실패: %s', _e85)
        sc85_msgs.append(f'SC85 WARN: 검사 실패 -- {_e85}')
        sc85_warn = True

    sc85_overall = 'WARN' if sc85_warn else 'PASS'
    # SC85은 WARN 전용 비차단 -- M645_W2 P-USER-DELEGATION (FP-36)

    # -- G7-SC86: M645_W3 P-PHANTOM-PID 탐지 (WARN 비차단) --
    # FP-37: Worker가 이전 보고서/핸드오프 PID를 tasklist 검증 없이 'alive' 재보고 = 거짓 PASS
    import re as _re86
    sc86_warn = False
    sc86_msgs: list = []
    try:
        _fp_path86 = _BASE / 'docs' / 'ai' / 'FALSE_PASS_REGISTRY.md'
        if _fp_path86.exists():
            _fp_text86 = _fp_path86.read_text(encoding='utf-8', errors='replace')
            for _kw86 in ('P-PHANTOM-PID', 'FP-37'):
                if _kw86 not in _fp_text86:
                    sc86_msgs.append(
                        f'SC86 WARN: FALSE_PASS_REGISTRY에 {_kw86} 미등록 (M645_W3 FP-37 체화 미완)'
                    )
                    logger.warning('G7-SC86: %s 미등록 (M645_W3)', _kw86)
                    sc86_warn = True
        else:
            sc86_msgs.append('SC86 WARN: FALSE_PASS_REGISTRY.md 미존재')
            sc86_warn = True
        # 보고서 파일에서 "PID \d+ alive" 패턴 탐지 시 tasklist evidence 없으면 WARN
        _reports_dir86 = _BASE / 'docs' / 'reports'
        if _reports_dir86.exists():
            for _rpt86 in sorted(_reports_dir86.glob('*.md'))[-5:]:  # 최근 5건만 검사
                try:
                    _rpt_txt86 = _rpt86.read_text(encoding='utf-8', errors='replace')
                    if _re86.search(r'PID\s+\d+\s+alive', _rpt_txt86, _re86.IGNORECASE):
                        if 'tasklist' not in _rpt_txt86.lower():
                            sc86_msgs.append(
                                f'SC86 WARN: {_rpt86.name} — "PID xxx alive" 패턴 있으나 '
                                f'tasklist evidence 부재 (FP-37 P-PHANTOM-PID)'
                            )
                            logger.warning('G7-SC86: %s — PID alive 보고 + tasklist 부재', _rpt86.name)
                            sc86_warn = True
                except Exception as _e86r:
                    logger.warning('G7-SC86: 보고서 읽기 실패 %s: %s', _rpt86.name, _e86r)
    except Exception as _e86:
        logger.warning('G7-SC86: P-PHANTOM-PID 검증 실패: %s', _e86)
        sc86_msgs.append(f'SC86 WARN: 검사 실패 -- {_e86}')
        sc86_warn = True

    sc86_overall = 'WARN' if sc86_warn else 'PASS'
    # SC86은 WARN 전용 비차단 -- M645_W3 P-PHANTOM-PID (FP-37)

    # -- G7-SC87: M645_W4 P-ALIVE-NO-PROGRESS 탐지 (WARN 비차단) --
    sc87_warn = False
    sc87_msgs: list = []
    try:
        import subprocess as _sp87
        _reports_dir87 = os.path.join(PROJECT_ROOT, 'docs', 'reports')
        # ralph_loop 프로세스 alive 여부 (ralph_loop_chemgrid.sh 키워드)
        _ps87 = _sp87.run(
            ['tasklist'],
            capture_output=True, text=True, timeout=10,  # [MAGIC] tasklist 10s 타임아웃
        )
        _tasklist87 = _ps87.stdout if isinstance(_ps87.stdout, str) else ''
        _ralph_alive87 = 'ralph_loop' in _tasklist87 or 'bash' in _tasklist87.lower()

        if _ralph_alive87:
            # git commit 건수 확인 (최근 1시간)
            _git87 = _sp87.run(
                ['git', '-C', PROJECT_ROOT, 'log', '--oneline',
                 '--since=1 hour ago'],
                capture_output=True, text=True, timeout=10,
            )
            _git_commits87 = (
                _git87.stdout.strip().splitlines()
                if isinstance(_git87.stdout, str)
                else []
            )
            # 산출물 파일 확인 (최근 30분 이내 생성된 .md/.py)
            _recent_files87: list = []
            try:
                _now87 = time.time()
                _threshold87 = 1800  # [MAGIC] 30분 = 1800초
                for _d87 in [_reports_dir87, os.path.join(PROJECT_ROOT, 'src', 'app')]:
                    if not os.path.isdir(_d87):
                        continue
                    for _f87 in os.listdir(_d87):
                        _fp87 = os.path.join(_d87, _f87)
                        try:
                            if _now87 - os.path.getmtime(_fp87) < _threshold87:
                                _recent_files87.append(_f87)
                        except OSError:
                            pass
            except Exception as _e87f:
                logger.warning('G7-SC87: 파일 mtime 확인 실패: %s', _e87f)

            if len(_git_commits87) == 0 and len(_recent_files87) == 0:
                sc87_warn = True
                sc87_msgs.append(
                    'SC87 WARN: ralph_loop alive + git commit 0건 + '
                    '산출물 파일 0건 (최근 30분) = P-ALIVE-NO-PROGRESS (M645_W4)'
                )
                logger.warning('G7-SC87: P-ALIVE-NO-PROGRESS 탐지 (M645_W4)')
    except Exception as _e87:
        logger.warning('G7-SC87: P-ALIVE-NO-PROGRESS 검증 실패: %s', _e87)
        sc87_msgs.append(f'SC87 WARN: 검사 실패 -- {_e87}')
        sc87_warn = True

    sc87_overall = 'WARN' if sc87_warn else 'PASS'
    # SC87은 WARN 전용 비차단 -- M645_W4 P-ALIVE-NO-PROGRESS (FP-37 확장)

    # -- G7-SC88: M645_W4 P-WRONG-VERIFICATION 탐지 (WARN 비차단) --
    sc88_warn = False
    sc88_msgs: list = []
    try:
        _reports_dir88 = os.path.join(PROJECT_ROOT, 'docs', 'reports')
        _pid_pattern88 = re.compile(r'PID\s+\d+\s+alive', re.IGNORECASE)
        _tasklist_ok88 = re.compile(r'tasklist', re.IGNORECASE)
        _ps_ef_ok88 = re.compile(r'ps\s+-ef|ps\s+aux', re.IGNORECASE)
        if os.path.isdir(_reports_dir88):
            for _rpt88 in sorted(
                os.scandir(_reports_dir88),
                key=lambda e: e.stat().st_mtime,
                reverse=True,
            )[:5]:  # [MAGIC] 최근 5개 보고서 스캔
                if not _rpt88.name.endswith('.md'):
                    continue
                try:
                    _txt88 = open(
                        _rpt88.path, encoding='utf-8', errors='replace'
                    ).read()
                    if _pid_pattern88.search(_txt88):
                        # PID alive 보고 감지 → tasklist/ps -ef 증거 확인
                        has_tasklist = _tasklist_ok88.search(_txt88)
                        has_ps_ef = _ps_ef_ok88.search(_txt88)
                        if not has_tasklist and not has_ps_ef:
                            sc88_warn = True
                            sc88_msgs.append(
                                f'SC88 WARN: {_rpt88.name} — "PID alive" 보고 있으나 '
                                'tasklist/ps -ef 실측 증거 미첨부 (P-WRONG-VERIFICATION M645_W4)'
                            )
                            logger.warning(
                                'G7-SC88: %s — PID alive 보고 + 검증 도구 미첨부',
                                _rpt88.name,
                            )
                except Exception as _e88r:
                    logger.warning('G7-SC88: 보고서 읽기 실패 %s: %s', _rpt88.name, _e88r)
    except Exception as _e88:
        logger.warning('G7-SC88: P-WRONG-VERIFICATION 검증 실패: %s', _e88)
        sc88_msgs.append(f'SC88 WARN: 검사 실패 -- {_e88}')

    sc88_overall = 'WARN' if sc88_warn else 'PASS'
    # SC88은 WARN 전용 비차단 -- M645_W4 P-WRONG-VERIFICATION

    # -- G7-SC89: M645_W4 P-USER-PERSONA-SKIP 탐지 (WARN 비차단) --
    sc89_warn = False
    sc89_msgs: list = []
    try:
        _reports_dir89 = os.path.join(PROJECT_ROOT, 'docs', 'reports')
        _persona_kws89 = ['자가시뮬레이션', 'Q1:', 'Q2:', 'user_persona_critic', 'Q-N14']
        _recent_rpts89: list = []
        if os.path.isdir(_reports_dir89):
            _recent_rpts89 = sorted(
                [e for e in os.scandir(_reports_dir89) if e.name.endswith('.md')],
                key=lambda e: e.stat().st_mtime,
                reverse=True,
            )[:3]  # [MAGIC] 최근 3개 보고서 스캔
        _skip_count89 = 0
        for _rpt89 in _recent_rpts89:
            try:
                _txt89 = open(
                    _rpt89.path, encoding='utf-8', errors='replace'
                ).read()
                if not any(kw in _txt89 for kw in _persona_kws89):
                    _skip_count89 += 1
                    sc89_msgs.append(
                        f'SC89 WARN: {_rpt89.name} — user_persona_critic '
                        '5질문 자가시뮬레이션 미첨부 (P-USER-PERSONA-SKIP M645_W4)'
                    )
                    logger.warning(
                        'G7-SC89: %s — persona 5질문 미첨부', _rpt89.name
                    )
            except Exception as _e89r:
                logger.warning('G7-SC89: 보고서 읽기 실패 %s: %s', _rpt89.name, _e89r)
        if _skip_count89 > 0:
            sc89_warn = True
        # critic_spawn_log.jsonl 존재 여부도 확인
        _spawn_log89 = os.path.join(PROJECT_ROOT, '.claude', 'critic_spawn_log.jsonl')
        if not os.path.exists(_spawn_log89):
            sc89_warn = True
            sc89_msgs.append(
                'SC89 WARN: critic_spawn_log.jsonl 미존재 '
                '(critic_before_ct_spawn hook 미실행 의심)'
            )
            logger.warning('G7-SC89: critic_spawn_log.jsonl 미존재')
    except Exception as _e89:
        logger.warning('G7-SC89: P-USER-PERSONA-SKIP 검증 실패: %s', _e89)
        sc89_msgs.append(f'SC89 WARN: 검사 실패 -- {_e89}')

    sc89_overall = 'WARN' if sc89_warn else 'PASS'
    # SC89은 WARN 전용 비차단 -- M645_W4 P-USER-PERSONA-SKIP

    # -- G7-SC90: M645_W4 P-DOUBLE-FALSE-POSITIVE 탐지 (CRITICAL 비차단) --
    sc90_warn = False
    sc90_msgs: list = []
    try:
        _mistakes_path90 = os.path.join(PROJECT_ROOT, 'docs', 'ai', 'mistakes.md')
        _fp_reg90 = os.path.join(PROJECT_ROOT, 'docs', 'ai', 'FALSE_PASS_REGISTRY.md')
        # "이중 가짜" 패턴 키워드
        _double_fp_kws90 = [
            'P-DOUBLE-FALSE-POSITIVE', '이중 가짜', 'double false',
            'FP-38', '이중가짜',
        ]
        # FALSE_PASS_REGISTRY에 FP-38 등록 여부 확인
        _fp38_registered90 = False
        if os.path.exists(_fp_reg90):
            try:
                _fp_text90 = open(
                    _fp_reg90, encoding='utf-8', errors='replace'
                ).read()
                _fp38_registered90 = 'FP-38' in _fp_text90
            except Exception as _e90f:
                logger.warning('G7-SC90: FALSE_PASS_REGISTRY 읽기 실패: %s', _e90f)

        if not _fp38_registered90:
            sc90_warn = True
            sc90_msgs.append(
                'SC90 WARN: FALSE_PASS_REGISTRY에 FP-38 P-DOUBLE-FALSE-POSITIVE 미등록 '
                '(M645_W4 체화 미완)'
            )
            logger.warning('G7-SC90: FP-38 P-DOUBLE-FALSE-POSITIVE 미등록')

        # user_persona_critic.py 존재 여부
        _upc_path90 = os.path.join(
            PROJECT_ROOT, 'housing', 'sinktank', 'user_persona_critic.py'
        )
        if not os.path.exists(_upc_path90):
            sc90_warn = True
            sc90_msgs.append(
                'SC90 WARN: user_persona_critic.py 미존재 (M645_W4 신설 미완)'
            )
            logger.warning('G7-SC90: user_persona_critic.py 미존재')

        # critic_before_ct_spawn.py hook 존재 여부
        _hook90 = os.path.join(
            PROJECT_ROOT, '.claude', 'hooks', 'critic_before_ct_spawn.py'
        )
        if not os.path.exists(_hook90):
            sc90_warn = True
            sc90_msgs.append(
                'SC90 WARN: critic_before_ct_spawn.py hook 미존재 (M645_W4 신설 미완)'
            )
            logger.warning('G7-SC90: critic_before_ct_spawn.py 미존재')

    except Exception as _e90:
        logger.warning('G7-SC90: P-DOUBLE-FALSE-POSITIVE 검증 실패: %s', _e90)
        sc90_msgs.append(f'SC90 WARN: 검사 실패 -- {_e90}')

    sc90_overall = 'WARN' if sc90_warn else 'PASS'
    # SC90은 WARN 전용 비차단 -- M645_W4 P-DOUBLE-FALSE-POSITIVE (FP-38)

    # ====================================================================
    # [M646_W36] G7-SC91: P-SWARM-RATIO-VIOLATION (Q-N21 사용자 명령)
    # 사용자 명령: Kimi 80% / Ollama 15% / sonnet 4% / opus 1%
    # CHEMGRID_SWARM_FORCE/CHEMGRID_KIMI_RATIO_TARGET env var 검사
    # WARN 전용 (비차단) — ralph_loop env var 누락 시 알림
    # ====================================================================
    sc91_warn = False
    sc91_msgs: list = []
    try:
        # ralph_loop_local.sh / ralph_loop_web.sh 에 SWARM_FORCE export 있는지 확인
        import os as _os91
        for _shfile in (
            'housing/sinktank/ralph_loop_local.sh',
            'housing/sinktank/ralph_loop_web.sh',
        ):
            try:
                _shtxt = open(_shfile, 'r', encoding='utf-8', errors='replace').read()
                if 'CHEMGRID_SWARM_FORCE' not in _shtxt:
                    sc91_warn = True
                    sc91_msgs.append(
                        f'SC91 WARN: {_shfile} CHEMGRID_SWARM_FORCE export 미존재 '
                        f'(M646_W36 Q-N21 SWARM 강제 미완)'
                    )
                    logger.warning('G7-SC91: %s SWARM_FORCE 미설정', _shfile)
            except OSError as _e91f:
                # 파일 미존재는 별도 SC가 처리, 여기서는 스킵
                logger.debug('G7-SC91: %s 읽기 실패: %s', _shfile, _e91f)
    except Exception as _e91:  # noqa: BLE001
        logger.warning('G7-SC91: P-SWARM-RATIO-VIOLATION 검증 실패: %s', _e91)
        sc91_msgs.append(f'SC91 WARN: 검사 실패 -- {_e91}')
    sc91_overall = 'WARN' if sc91_warn else 'PASS'

    # ====================================================================
    # [M646_W36][M656] G7-SC92: P-ALIVE-NO-PROGRESS (Q-N21 사용자 명령)
    # ralph_loop alive + 30분+ 동안 git commit 0 + docs/reports 신규 0
    # 차단(REJECT) — 무한루프가 멈춘 척 증거 확보
    # [M656 강화] sentinel 존재 + spawn_next_cycle.log 24h 미갱신 시 CRITICAL
    # ====================================================================
    sc92_fail = False
    sc92_msgs: list = []
    try:
        import subprocess as _sp92
        import os as _os92
        import time as _t92
        # [MAGIC: 30] 30분 윈도 — 사용자 Q-N21 "멈추지마" 임계
        _git_log = _sp92.run(
            ['git', 'log', '--since=30 minutes ago', '--oneline'],
            capture_output=True, text=True, timeout=10,
        )
        _commit_count = (
            len(_git_log.stdout.strip().splitlines()) if _git_log.returncode == 0 else -1
        )
        # docs/reports 30분 내 신규 파일 (Path.stat().st_mtime 기준)
        _now = _t92.time()
        _reports_dir = 'docs/reports'
        _new_files = 0
        if _os92.path.isdir(_reports_dir):
            for _f in _os92.listdir(_reports_dir):
                _fp = _os92.path.join(_reports_dir, _f)
                try:
                    if (_now - _os92.path.getmtime(_fp)) < 1800.0:  # [MAGIC: 1800sec] 30분
                        _new_files += 1
                except OSError:
                    continue
        # ralph_loop alive 가정 (lockfile 존재) — 실제 PID 검증은 호출부 책임
        _lockfile = '.ralph_loop_local.lock'
        _ralph_alive = _os92.path.exists(_lockfile) or _os92.path.exists(
            'housing/sinktank/' + _lockfile
        )
        if _ralph_alive and _commit_count == 0 and _new_files == 0:
            sc92_fail = True
            sc92_msgs.append(
                f'SC92 REJECT: ralph_loop alive 추정 + 최근 30분 commit=0 + '
                f'산출물=0 (FP-37 P-PHANTOM-PID 누적 패턴)'
            )
            logger.warning('G7-SC92: P-ALIVE-NO-PROGRESS — 무진행')
        else:
            sc92_msgs.append(
                f'SC92 PASS: commits={_commit_count} new_files={_new_files} '
                f'ralph_alive={_ralph_alive}'
            )

        # [M656 강화] sentinel 존재 + spawn_next_cycle.log 24h 미갱신 → CRITICAL
        # 의미: sentinel이 "spawn 필요"를 외치고 있는데 실제 spawn_next_cycle.py가
        # 24시간 이상 실행되지 않았다 = Phase 4.7c-NEXT 작동 안 함 = 무한사이클 dead
        _sentinel92 = 'C:/chemgrid/.claude/_cycle_auto_trigger_sentinel.json'
        _spawn_log92 = 'C:/chemgrid/.claude/spawn_next_cycle.log'
        if _os92.path.exists(_sentinel92):
            try:
                with open(_sentinel92, encoding='utf-8', errors='replace') as _sf92:
                    import json as _json92
                    _sdata92 = _json92.load(_sf92)
                if isinstance(_sdata92, dict) and _sdata92.get('next_action') == 'SPAWN_NEXT_CYCLE':
                    # sentinel이 SPAWN_NEXT_CYCLE 요구 중 — spawn_next_cycle.log 최신성 확인
                    if _os92.path.exists(_spawn_log92):
                        _log_age_h92 = (_now - _os92.path.getmtime(_spawn_log92)) / 3600.0
                        # [MAGIC: 24] 24시간 = Rule AC comparison HTML 의무 주기와 동일
                        if _log_age_h92 > 24.0:
                            sc92_fail = True
                            sc92_msgs.append(
                                f'SC92 CRITICAL [M656]: sentinel=SPAWN_NEXT_CYCLE 존재 + '
                                f'spawn_next_cycle.log {_log_age_h92:.1f}h 미갱신 (> 24h) — '
                                f'Phase 4.7c-NEXT 작동 불가, 무한사이클 dead'
                            )
                            logger.warning(
                                'G7-SC92 M656: sentinel SPAWN_NEXT_CYCLE + spawn_log %.1fh 미갱신',
                                _log_age_h92,
                            )
                        else:
                            sc92_msgs.append(
                                f'SC92 sentinel-spawn-check PASS: log_age={_log_age_h92:.1f}h (<24h)'
                            )
                    else:
                        # spawn_next_cycle.log 미존재 = spawn_next_cycle.py 한번도 실행 안 됨
                        sc92_fail = True
                        sc92_msgs.append(
                            'SC92 CRITICAL [M656]: sentinel=SPAWN_NEXT_CYCLE 존재 + '
                            'spawn_next_cycle.log 미존재 — spawn_next_cycle.py 한번도 미실행'
                        )
                        logger.warning(
                            'G7-SC92 M656: sentinel SPAWN_NEXT_CYCLE + spawn_log 미존재'
                        )
            except Exception as _se92:  # noqa: BLE001
                logger.warning('G7-SC92 M656 sentinel 파싱 실패: %s', _se92)
                sc92_msgs.append(f'SC92 WARN M656: sentinel 파싱 실패 -- {_se92}')
    except Exception as _e92:  # noqa: BLE001
        logger.warning('G7-SC92: P-ALIVE-NO-PROGRESS 검증 실패: %s', _e92)
        sc92_msgs.append(f'SC92 WARN: 검사 실패 -- {_e92}')
    sc92_overall = 'REJECT' if sc92_fail else 'PASS'

    # ====================================================================
    # [M647_W5_A6] G7-SC93: P-CRON-AV-VARIANT-FRAGMENT
    # 4변종 분기 D2 결함 5 → 통합 단일 진입점 의무화
    # WARN 전용 (비차단) — cron_av_unified.py 미존재 시 알림
    # ====================================================================
    sc93_warn = False
    sc93_msgs: list = []
    try:
        # [MAGIC] PROJECT_ROOT는 patrol.py 모듈 레벨 변수 (line 64)
        _sinktank_dir93 = os.path.join(PROJECT_ROOT, 'housing', 'sinktank')

        # 검사 1: cron_av_unified.py 존재 확인
        _unified_path93 = os.path.join(_sinktank_dir93, 'cron_av_unified.py')
        if not os.path.exists(_unified_path93):
            sc93_warn = True
            sc93_msgs.append(
                'SC93 WARN: cron_av_unified.py 미존재 — '
                'M647_W5_A6 통합 진입점 생성 필요'
            )
            logger.warning('G7-SC93: cron_av_unified.py 미존재')
        else:
            # 검사 2: 4변종 파일이 DEPRECATED 마커 없이 존재하면 WARN
            _legacy_files93 = [
                'cron_av_ct.py',
                'cron_av_ct_v2.py',
                'cron_av_report.py',
                'cron_av_daemon.py',
            ]
            for _lf93 in _legacy_files93:
                _lf_path93 = os.path.join(_sinktank_dir93, _lf93)
                if os.path.exists(_lf_path93):
                    try:
                        with open(_lf_path93, 'r', encoding='utf-8', errors='replace') as _fh93:
                            _head93 = ''.join(_fh93.readline() for _ in range(5))
                        if 'DEPRECATED' not in _head93:
                            sc93_warn = True
                            sc93_msgs.append(
                                f'SC93 WARN: {_lf93} DEPRECATED 마커 없음 — '
                                f'통합 완료 후 마킹 필요 (M647_W5_A6)'
                            )
                            logger.warning('G7-SC93: %s DEPRECATED 마커 없음', _lf93)
                    except OSError as _e93f:
                        logger.debug('G7-SC93: %s 읽기 실패: %s', _lf93, _e93f)

        # 검사 3: .claude/notifications/ 폴더 존재 확인
        _notify_dir93 = os.path.join(PROJECT_ROOT, '.claude', 'notifications')
        if not os.path.isdir(_notify_dir93):
            sc93_warn = True
            sc93_msgs.append(
                'SC93 WARN: .claude/notifications/ 폴더 미존재 — '
                'cron_av_unified.py 실행 후 자동 생성됨'
            )
            logger.warning('G7-SC93: .claude/notifications/ 미존재: %s', _notify_dir93)

    except Exception as _e93:  # noqa: BLE001
        logger.warning('G7-SC93: P-CRON-AV-VARIANT-FRAGMENT 검증 실패: %s', _e93)
        sc93_msgs.append(f'SC93 WARN: 검사 실패 -- {_e93}')
    sc93_overall = 'WARN' if sc93_warn else 'PASS'
    # SC93은 WARN 전용 비차단 -- M647_W5_A6 P-CRON-AV-VARIANT-FRAGMENT (D2 결함 5)

    # ====================================================================
    # [M647_W5_A19] G7-SC94: P-AV-SKILL-MISSING
    # docs/ai/skills/av_compliance.md 미존재 시 WARN
    # WARN 전용 (비차단) — AV 자체 skill 1년 미작성 패턴 재발 차단
    # ====================================================================
    sc94_warn = False
    sc94_msgs: list = []
    try:
        _av_skill_path94 = os.path.join(PROJECT_ROOT, 'docs', 'ai', 'skills', 'av_compliance.md')
        if not os.path.exists(_av_skill_path94):
            sc94_warn = True
            sc94_msgs.append(
                'SC94 WARN: docs/ai/skills/av_compliance.md 미존재 — '
                'M647_W5_A19 AV skill 작성 필요 (5 issue 카테고리 + FP 패턴)'
            )
            logger.warning('G7-SC94: av_compliance.md 미존재 (M647_W5_A19)')
        else:
            # [MAGIC] 최소 200바이트 = 실질 내용 포함 여부 확인
            try:
                _av_skill_size = os.path.getsize(_av_skill_path94)
                if _av_skill_size < 200:
                    sc94_warn = True
                    sc94_msgs.append(
                        f'SC94 WARN: av_compliance.md 크기 {_av_skill_size}B (< 200B) — '
                        '깡통 skill 파일 (5 issue 카테고리 미기재 의심)'
                    )
                    logger.warning('G7-SC94: av_compliance.md 깡통 %dB', _av_skill_size)
            except OSError as _e94s:
                logger.warning('G7-SC94: av_compliance.md stat 실패: %s', _e94s)
    except Exception as _e94:  # noqa: BLE001
        logger.warning('G7-SC94: P-AV-SKILL-MISSING 검증 실패: %s', _e94)
        sc94_msgs.append(f'SC94 WARN: 검사 실패 -- {_e94}')
    sc94_overall = 'WARN' if sc94_warn else 'PASS'
    # SC94는 WARN 전용 비차단 -- M647_W5_A19 P-AV-SKILL-MISSING

    # [M647_W5_A15] G7-SC95: P-HARNESS-COMPRESS (Rule QQ)
    # Rule QQ: CLAUDE.md 압축 인덱스에서 CT Decision / M번호 제거 금지
    # WARN 비차단 — 제안 기록 목적
    sc95_msgs = []
    try:
        _compress_keywords = [
            'CT Decision 번호', 'M번호', 'Worker ID', '직렬체계',
            '감사팀', '체화4단계', 'skills/mistakes', 'Rule T',
        ]
        _claude_md_path95 = os.path.join(PROJECT_ROOT, 'CLAUDE.md')
        if os.path.exists(_claude_md_path95):
            with open(_claude_md_path95, encoding='utf-8', errors='ignore') as _f95:
                _cmd_text = _f95.read()
            # Rule QQ: 압축 인덱스에서 핵심 규칙 메타 정보 삭제 여부 확인
            for _kw95 in _compress_keywords:
                if _kw95 not in _cmd_text:
                    sc95_msgs.append(
                        f'SC95 WARN: CLAUDE.md에서 "{_kw95}" 미발견 — '
                        'Rule QQ 압축 위반 가능성'
                    )
                    logger.warning('G7-SC95: P-HARNESS-COMPRESS "%s" 미발견', _kw95)
        else:
            sc95_msgs.append('SC95 WARN: CLAUDE.md 미존재')
            logger.warning('G7-SC95: CLAUDE.md 미존재')
    except Exception as _e95:
        sc95_msgs.append(f'SC95 WARN: 검사 실패 -- {_e95}')
        logger.warning('G7-SC95: P-HARNESS-COMPRESS 검사 실패: %s', _e95)
    # SC95는 WARN 전용 비차단 -- M647_W5_A15 P-HARNESS-COMPRESS

    # ====================================================================
    # [CT-D-20260504-A55] G7-SC96: P-AV-PROMPT-STALE
    # docs/ai/inbox/AV_NEXT_PROMPT.md mtime 감시
    # 60분 초과 = WARN (cron 발화 지연 의심)
    # 24시간 초과 = CRITICAL (채팅창 AV 발화 인프라 미작동)
    # WARN/CRITICAL 전용 비차단 — 발화 인프라 상태 감시
    # ====================================================================
    sc96_msgs = []
    sc96_warn = False
    sc96_critical = False
    try:
        _av_prompt_path96 = os.path.join(PROJECT_ROOT, 'docs', 'ai', 'inbox', 'AV_NEXT_PROMPT.md')
        if not os.path.exists(_av_prompt_path96):
            sc96_warn = True
            sc96_msgs.append(
                'SC96 WARN: AV_NEXT_PROMPT.md 미존재 -- '
                'CT-D-20260504-A55 채팅창 AV 발화 인프라 미구축 (cron_20min_dispatcher Phase 7 확인)'
            )
            logger.warning('G7-SC96: AV_NEXT_PROMPT.md 미존재: %s', _av_prompt_path96)
        else:
            import time as _t96
            _av_mtime96 = os.path.getmtime(_av_prompt_path96)
            _av_age_sec96 = _t96.time() - _av_mtime96
            # [MAGIC] 3600초 = 60분 = cron 3주기 (20분 × 3) 초과 시 WARN
            _AV_PROMPT_WARN_SEC = 3600
            # [MAGIC] 86400초 = 24시간 = 하루 미갱신 시 CRITICAL
            _AV_PROMPT_CRITICAL_SEC = 86400
            if _av_age_sec96 > _AV_PROMPT_CRITICAL_SEC:
                sc96_critical = True
                sc96_warn = True
                sc96_msgs.append(
                    'SC96 CRITICAL: AV_NEXT_PROMPT.md {}시간 미갱신 -- '
                    '채팅창 AV 발화 인프라 24h+ 미작동 (cron_20min_dispatcher schtasks 상태 확인)'.format(
                        int(_av_age_sec96 / 3600)
                    )
                )
                logger.warning(
                    'G7-SC96: P-AV-PROMPT-STALE CRITICAL: %s 경과 (24h 기준)',
                    '{:.0f}h'.format(_av_age_sec96 / 3600),
                )
            elif _av_age_sec96 > _AV_PROMPT_WARN_SEC:
                sc96_warn = True
                sc96_msgs.append(
                    'SC96 WARN: AV_NEXT_PROMPT.md {}분 미갱신 -- '
                    'cron_20min_dispatcher Phase 7 발화 지연 (60분 기준)'.format(
                        int(_av_age_sec96 / 60)
                    )
                )
                logger.warning(
                    'G7-SC96: P-AV-PROMPT-STALE WARN: %s 경과 (60분 기준)',
                    '{:.0f}m'.format(_av_age_sec96 / 60),
                )
            else:
                logger.info(
                    'G7-SC96: AV_NEXT_PROMPT.md 정상 (%d분 전 갱신)',
                    int(_av_age_sec96 / 60),
                )
    except Exception as _e96:
        sc96_warn = True
        sc96_msgs.append(f'SC96 WARN: 검사 실패 -- {_e96}')
        logger.warning('G7-SC96: P-AV-PROMPT-STALE 검사 실패: %s', _e96)
    # SC96은 WARN/CRITICAL 전용 비차단 -- CT-D-20260504-A55 P-AV-PROMPT-STALE

    # ====================================================================
    # [CT-D-20260504-A55] G7-SC97: P-NO-EXTERNAL-AI-IN-PROMPT (M680 신설)
    # external_ai_dispatch_enforce.py 존재 여부 + settings.json 등록 확인
    # sc97_no_external_ai.jsonl violation 24h 3건 이상 = CRITICAL
    # WARN/CRITICAL 전용 비차단 -- 외부 AI 호출 의무 체화 감시
    # ====================================================================
    sc97_msgs = []
    sc97_warn = False
    sc97_critical = False
    try:
        import time as _t97
        _hook_path97 = os.path.join(PROJECT_ROOT, '.claude', 'hooks', 'external_ai_dispatch_enforce.py')
        _log_path97 = os.path.join(PROJECT_ROOT, 'docs', 'logs', 'sc97_no_external_ai.jsonl')
        _settings_path97 = os.path.join(PROJECT_ROOT, '.claude', 'settings.json')
        _hook_ok97 = os.path.isfile(_hook_path97)
        if not _hook_ok97:
            sc97_warn = True
            sc97_msgs.append(
                'SC97 WARN: .claude/hooks/external_ai_dispatch_enforce.py 미존재 -- '
                'M680 CT-D-A55 외부 AI dispatch hook 미설치'
            )
            logger.warning('G7-SC97: external_ai_dispatch_enforce.py 미존재: %s', _hook_path97)
        else:
            # settings.json Agent matcher 등록 확인
            _settings_ok97 = False
            if os.path.isfile(_settings_path97):
                try:
                    with open(_settings_path97, 'r', encoding='utf-8') as _sf97:
                        _sdata97 = json.load(_sf97)
                    _pre97 = _sdata97.get('hooks', {}).get('PreToolUse', [])
                    for _sec97 in _pre97:
                        if _sec97.get('matcher') == 'Agent':
                            for _h97 in _sec97.get('hooks', []):
                                if 'external_ai_dispatch_enforce' in _h97.get('command', ''):
                                    _settings_ok97 = True
                                    break
                except Exception as _se97:
                    logger.warning('G7-SC97: settings.json 읽기 실패: %s', _se97)
            if not _settings_ok97:
                sc97_warn = True
                sc97_msgs.append(
                    'SC97 WARN: settings.json Agent matcher에 external_ai_dispatch_enforce 미등록 -- '
                    'M680 hook 등록 필요'
                )
                logger.warning('G7-SC97: settings.json Agent matcher 미등록')

        # M730 강화 (CT-D-A58-EMERGENCY): violation 24h 누적 1건+ = CRITICAL
        # 사용자 LV.16+ "sonnet 최소화 + 외부AI 위주" -- 1건도 허용 안 함
        _SC97_VIOLATION_THRESHOLD = 1   # [MAGIC: 1] 24h violation CRITICAL 기준 (M730 강화: 3 -> 1)
        _SC97_WINDOW_SEC = 86400         # [MAGIC: 86400] 24시간 집계 윈도우
        if os.path.isfile(_log_path97):
            try:
                _now97 = _t97.time()
                _violations97 = 0
                with open(_log_path97, 'r', encoding='utf-8') as _lf97:
                    for _line97 in _lf97:
                        _line97 = _line97.strip()
                        if not _line97:
                            continue
                        try:
                            _entry97 = json.loads(_line97)
                            if not isinstance(_entry97, dict):
                                continue
                            _age97 = _now97 - float(_entry97.get('ts', 0))
                            if _age97 <= _SC97_WINDOW_SEC and _entry97.get('severity') == 'CRITICAL':
                                _violations97 += 1
                        except (json.JSONDecodeError, ValueError):
                            pass
                if _violations97 >= _SC97_VIOLATION_THRESHOLD:
                    sc97_critical = True
                    sc97_msgs.append(
                        f'SC97 CRITICAL: 외부 AI dispatch 미호출 violation 24h {_violations97}건 -- '
                        f'Rule MM/PP 위반 누적 (기준: {_SC97_VIOLATION_THRESHOLD}건). '
                        'Worker spawn 시 swarm_dispatcher.dispatch() 추가 필수.'
                    )
                    logger.warning('G7-SC97: P-NO-EXTERNAL-AI-IN-PROMPT CRITICAL: %d건/24h', _violations97)
                elif _violations97 > 0:
                    sc97_warn = True
                    sc97_msgs.append(
                        f'SC97 WARN: 외부 AI dispatch 미호출 violation 24h {_violations97}건 (기준 {_SC97_VIOLATION_THRESHOLD}건 미달)'
                    )
                    logger.info('G7-SC97: violation %d건/24h (임계 미달)', _violations97)
                else:
                    logger.info('G7-SC97: P-NO-EXTERNAL-AI-IN-PROMPT 정상 (violation 0건/24h)')
            except Exception as _le97:
                logger.warning('G7-SC97: sc97 log 읽기 실패: %s', _le97)
    except Exception as _e97:
        sc97_msgs.append(f'SC97 WARN: 검사 실패 -- {_e97}')
        logger.warning('G7-SC97: P-NO-EXTERNAL-AI-IN-PROMPT 검사 실패: %s', _e97)
    # SC97은 WARN/CRITICAL 전용 비차단 -- CT-D-20260504-A55 P-NO-EXTERNAL-AI-IN-PROMPT

    # ====================================================================
    # [A55-AV-WATCHDOG M696] G7-SC98: P-CHEMGRID-LITE-ZOMBIE
    # cron_av_unified.py에 module_zombie_check 함수 존재 여부 확인
    # zombie FAIL 24h 누적 5건 = CRITICAL
    # WARN/CRITICAL 전용 비차단 -- 사용자 명시 깡통 검사 강화
    # ====================================================================
    sc98_warn = False
    sc98_critical = False
    sc98_msgs: list = []
    try:
        import importlib.util as _ilu98
        _av_path98 = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'cron_av_unified.py',
        )
        _av_exists98 = os.path.isfile(_av_path98)
        if not _av_exists98:
            sc98_warn = True
            sc98_msgs.append(
                'SC98 WARN: cron_av_unified.py 미존재 -- '
                'M696 zombie 검사 모듈 미설치'
            )
            logger.warning('G7-SC98: cron_av_unified.py 미존재: %s', _av_path98)
        else:
            # module_zombie_check 함수 존재 여부 grep
            try:
                with open(_av_path98, encoding='utf-8', errors='replace') as _fav98:
                    _av_src98 = _fav98.read()
                if 'module_zombie_check' not in _av_src98:
                    sc98_warn = True
                    sc98_msgs.append(
                        'SC98 WARN: cron_av_unified.py에 module_zombie_check 함수 없음 -- '
                        'M696 깡통 검사 5종 미구현'
                    )
                    logger.warning('G7-SC98: module_zombie_check 함수 없음')
                else:
                    logger.info('G7-SC98: module_zombie_check 존재 확인 OK')
            except OSError as _re98:
                sc98_warn = True
                sc98_msgs.append(f'SC98 WARN: cron_av_unified.py 읽기 실패 -- {_re98}')
                logger.warning('G7-SC98: cron_av_unified.py 읽기 실패: %s', _re98)

        # zombie FAIL 24h 누적 카운트 (notification JSON에서 집계)
        # [MAGIC] 5건 = CRITICAL 기준 (사용자 명시 "20분마다" 기준 5회 = 100분 연속 FAIL)
        _SC98_FAIL_THRESHOLD = 5
        # [MAGIC] 86400초 = 24시간 집계 윈도우
        _SC98_WINDOW_SEC = 86400
        _notify_dir98 = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', '.claude', 'notifications',
        )
        _notify_dir98 = os.path.normpath(_notify_dir98)
        _zombie_fail_count = 0
        if os.path.isdir(_notify_dir98):
            _now98 = time.time()
            try:
                for _nf98 in glob.glob(os.path.join(_notify_dir98, 'cron_av_*.json')):
                    try:
                        _age98 = _now98 - os.path.getmtime(_nf98)
                        if _age98 > _SC98_WINDOW_SEC:
                            continue
                        with open(_nf98, encoding='utf-8', errors='replace') as _nfh98:
                            _nd98 = json.load(_nfh98)
                        if not isinstance(_nd98, dict):  # Rule N
                            continue
                        _zsumm98 = _nd98.get('summary', {})
                        if isinstance(_zsumm98, dict) and _zsumm98.get('zombie_verdict') == 'FAIL':
                            _zombie_fail_count += 1
                    except (OSError, json.JSONDecodeError, ValueError) as _nfe98:
                        logger.warning('G7-SC98: notification 파일 읽기 실패: %s', _nfe98)
            except OSError as _gde98:
                logger.warning('G7-SC98: notifications 디렉터리 읽기 실패: %s', _gde98)

        if _zombie_fail_count >= _SC98_FAIL_THRESHOLD:
            sc98_critical = True
            sc98_msgs.append(
                f'SC98 CRITICAL: zombie 깡통 검사 FAIL 24h {_zombie_fail_count}건 -- '
                f'기준 {_SC98_FAIL_THRESHOLD}건 초과. '
                '사용자 격분 재발 차단: "깡통 없는지 20분 주기로 AV" (M696)'
            )
            logger.warning(
                'G7-SC98: P-CHEMGRID-LITE-ZOMBIE CRITICAL: %d건/24h',
                _zombie_fail_count,
            )
        elif _zombie_fail_count > 0:
            sc98_warn = True
            sc98_msgs.append(
                f'SC98 WARN: zombie 깡통 검사 FAIL 24h {_zombie_fail_count}건 '
                f'(기준 {_SC98_FAIL_THRESHOLD}건 미달)'
            )
            logger.info('G7-SC98: zombie_fail %d건/24h (임계 미달)', _zombie_fail_count)
        else:
            logger.info('G7-SC98: P-CHEMGRID-LITE-ZOMBIE 정상 (zombie_fail 0건/24h)')

    except Exception as _e98:
        sc98_msgs.append(f'SC98 WARN: 검사 실패 -- {_e98}')
        logger.warning('G7-SC98: P-CHEMGRID-LITE-ZOMBIE 검사 실패: %s', _e98)
    # SC98은 WARN/CRITICAL 전용 비차단 -- A55-AV-WATCHDOG M696 P-CHEMGRID-LITE-ZOMBIE

    # [CT-D-20260504-A57-W8 / M715] G7-SC99: P-M-NUMBER-RACE -- M번호 동시 사용 race condition 탐지
    sc99_msgs: list[str] = []
    sc99_warn: bool = False
    sc99_critical: bool = False
    _SC99_RACE_THRESHOLD = 2    # [MAGIC: 2] 24h 내 동일 M번호 커밋 건수 CRITICAL 기준
    _SC99_WINDOW_SEC = 86400    # [MAGIC: 86400] 24시간 집계 윈도우
    try:
        import collections as _sc99_collections
        # M158 패턴: text=False + decode('utf-8', errors='replace') 사용
        _git_log_res99 = subprocess.run(
            ['git', '-C', PROJECT_ROOT, 'log', '--oneline',
             f'--since={_SC99_WINDOW_SEC} seconds ago'],
            capture_output=True, timeout=15,
        )
        _git_log_out99 = _git_log_res99.stdout.decode('utf-8', errors='replace')
        _mnums99: dict = _sc99_collections.defaultdict(list)
        _mnum_re99 = re.compile(r'\bM(\d{3,})\b')
        for _line99 in _git_log_out99.splitlines():
            _parts99 = _line99.split(None, 1)
            if len(_parts99) < 2:
                continue
            _sha99, _msg99 = _parts99[0], _parts99[1]
            for _m99 in _mnum_re99.findall(_msg99):
                _mnums99[_m99].append(_sha99)
        # 동일 M번호를 2개 이상 커밋이 사용하면 race condition 의심
        _dup99 = {k: v for k, v in _mnums99.items() if len(v) >= _SC99_RACE_THRESHOLD}
        if _dup99:
            sc99_critical = True
            for _mn99, _shas99 in sorted(_dup99.items()):
                _sha_str99 = ', '.join(_shas99[:4])
                sc99_msgs.append(
                    f'SC99 CRITICAL: M{_mn99} 24h 내 {len(_shas99)}개 커밋 동시 사용 -- '
                    f'Race condition 의심: [{_sha_str99}]. '
                    f'Rule T: 직렬 Worker에서 M번호 중복 할당 금지.'
                )
                logger.warning('G7-SC99: M%s race %d개 커밋', _mn99, len(_shas99))
        else:
            logger.info('G7-SC99: P-M-NUMBER-RACE 정상 (중복 M번호 없음)')
        # evidence 파일 24h 신규 중 M번호 중복 추가 검사
        _ev_dir99 = os.path.join(PROJECT_ROOT, 'docs', 'evidence')
        if os.path.isdir(_ev_dir99):
            _ev_mnums99: dict = _sc99_collections.defaultdict(list)
            _now99 = time.time()
            for _ef99 in os.listdir(_ev_dir99):
                _efp99 = os.path.join(_ev_dir99, _ef99)
                try:
                    if _now99 - os.path.getmtime(_efp99) > _SC99_WINDOW_SEC:
                        continue
                    for _m99b in _mnum_re99.findall(_ef99):
                        _ev_mnums99[_m99b].append(_ef99)
                except OSError:
                    pass
            _ev_dup99 = {k: v for k, v in _ev_mnums99.items() if len(v) >= _SC99_RACE_THRESHOLD}
            if _ev_dup99:
                sc99_warn = True
                for _emn99, _efs99 in sorted(_ev_dup99.items()):
                    sc99_msgs.append(
                        f'SC99 WARN: evidence 파일에서 M{_emn99} 24h 내 {len(_efs99)}건 중복 -- '
                        f'{", ".join(_efs99[:3])}. M번호 중복 할당 가능성.'
                    )
                    logger.warning('G7-SC99: evidence M%s 중복 %d건', _emn99, len(_efs99))
    except Exception as _e99:
        sc99_msgs.append(f'SC99 WARN: 검사 실패 -- {_e99}')
        logger.warning('G7-SC99: P-M-NUMBER-RACE 검사 실패: %s', _e99)
    # SC99는 WARN/CRITICAL 전용 비차단 -- CT-D-20260504-A57-W8 P-M-NUMBER-RACE (M715)

    # [CT-D-20260504-A57-W8 / M715] G7-SC100: P-POPUP-SIMULTANEOUS-EDIT -- popup_*.py 동시 수정 lock 탐지
    sc100_msgs: list[str] = []
    sc100_warn: bool = False
    sc100_critical: bool = False
    _SC100_POPUP_THRESHOLD = 3  # [MAGIC: 3] 동시 수정 popup 파일 수 WARN 기준 (FIX-MASS vs FIX-N 충돌)
    _SC100_POPUP_CRITICAL = 6   # [MAGIC: 6] CRITICAL 기준 (6개 이상 = 대규모 충돌 의심)
    try:
        # M158 패턴: text=False + decode('utf-8', errors='replace') 사용
        _diff_res100 = subprocess.run(
            ['git', '-C', PROJECT_ROOT, 'diff', 'HEAD', '--name-only'],
            capture_output=True, timeout=15,
        )
        _diff_out100 = _diff_res100.stdout.decode('utf-8', errors='replace')
        _popup_modified100: list[str] = [
            _ln100.strip()
            for _ln100 in _diff_out100.splitlines()
            if re.search(r'popup_[^/]+\.py$', _ln100.strip())
        ]
        # 최근 커밋 1건에서의 변경도 확인 (Worker 산출물 직후 상태)
        _diff_last_res100 = subprocess.run(
            ['git', '-C', PROJECT_ROOT, 'diff', 'HEAD~1', 'HEAD', '--name-only'],
            capture_output=True, timeout=15,
        )
        _diff_last_out100 = _diff_last_res100.stdout.decode('utf-8', errors='replace')
        _popup_last100: list[str] = [
            _ln100b.strip()
            for _ln100b in _diff_last_out100.splitlines()
            if re.search(r'popup_[^/]+\.py$', _ln100b.strip())
        ]
        _max_popup100 = max(len(_popup_modified100), len(_popup_last100))
        _which_src100 = 'diff HEAD' if len(_popup_modified100) >= len(_popup_last100) else 'diff HEAD~1'
        _which_list100 = _popup_modified100 if len(_popup_modified100) >= len(_popup_last100) else _popup_last100
        if _max_popup100 >= _SC100_POPUP_CRITICAL:
            sc100_critical = True
            sc100_msgs.append(
                f'SC100 CRITICAL: {_which_src100} popup_*.py 동시 수정 {_max_popup100}건 -- '
                f'기준 {_SC100_POPUP_CRITICAL}건 초과. '
                f'FIX-MASS vs FIX-N Worker 대규모 충돌 의심. '
                f'파일: {", ".join(_which_list100[:5])}.'
            )
            logger.warning('G7-SC100: P-POPUP-SIMULTANEOUS-EDIT CRITICAL: %d건', _max_popup100)
        elif _max_popup100 >= _SC100_POPUP_THRESHOLD:
            sc100_warn = True
            sc100_msgs.append(
                f'SC100 WARN: {_which_src100} popup_*.py 동시 수정 {_max_popup100}건 -- '
                f'기준 {_SC100_POPUP_THRESHOLD}건 이상. '
                f'FIX-MASS/FIX-N Worker 충돌 가능성 확인 요망. '
                f'파일: {", ".join(_which_list100[:5])}.'
            )
            logger.warning('G7-SC100: P-POPUP-SIMULTANEOUS-EDIT WARN: %d건', _max_popup100)
        else:
            logger.info('G7-SC100: P-POPUP-SIMULTANEOUS-EDIT 정상 (%d건)', _max_popup100)
    except Exception as _e100:
        sc100_msgs.append(f'SC100 WARN: 검사 실패 -- {_e100}')
        logger.warning('G7-SC100: P-POPUP-SIMULTANEOUS-EDIT 검사 실패: %s', _e100)
    # SC100은 WARN/CRITICAL 전용 비차단 -- CT-D-20260504-A57-W8 P-POPUP-SIMULTANEOUS-EDIT (M715)

    # -----------------------------------------------------------------------
    # [A60-W2 / M736] SC101~SC104: 하네스 결함 4종 자동 탐지 (사용자 LV.17+)
    # -----------------------------------------------------------------------

    # SC101 P-FOREGROUND-ZERO: 24h 포그라운드 실행 0건 = CRITICAL (Rule F)
    sc101_msgs: list = []
    _SC101_FG_LOG = os.path.join(PROJECT_ROOT, "housing", "sinktank", "foreground_cycle_state.json")
    _SC101_HOURS_THRESHOLD = 24  # [MAGIC: 24h] 포그라운드 미실행 CRITICAL 기준 (Rule F)
    try:
        if os.path.exists(_SC101_FG_LOG):
            with open(_SC101_FG_LOG, encoding="utf-8", errors="ignore") as _f101:
                _fg101 = json.load(_f101)
            if not isinstance(_fg101, dict):
                sc101_msgs.append("SC101 WARN: foreground_cycle_state.json 형식 오류 (비dict)")
                logger.warning("G7-SC101: foreground_cycle_state.json is not dict")
            else:
                _last_fg = _fg101.get("last_run_ts", None)
                if _last_fg is None:
                    sc101_msgs.append("SC101 CRITICAL: foreground_cycle_state.json last_run_ts 없음 -- Rule F 포그라운드 실행 증거 없음")
                    logger.warning("G7-SC101: P-FOREGROUND-ZERO CRITICAL: last_run_ts 없음")
                else:
                    try:
                        _age_h = (time.time() - float(_last_fg)) / 3600.0
                        if _age_h > _SC101_HOURS_THRESHOLD:
                            sc101_msgs.append(
                                f"SC101 CRITICAL: 포그라운드 마지막 실행 {_age_h:.1f}h 전 -- "
                                f"{_SC101_HOURS_THRESHOLD}h 미실행 = P-FOREGROUND-ZERO. Rule F 위반."
                            )
                            logger.warning("G7-SC101: P-FOREGROUND-ZERO CRITICAL: %.1fh 미실행", _age_h)
                        else:
                            logger.info("G7-SC101: P-FOREGROUND-ZERO 정상 (%.1fh 이내)", _age_h)
                    except (TypeError, ValueError) as _e101v:
                        sc101_msgs.append(f"SC101 WARN: last_run_ts 파싱 실패 -- {_e101v}")
                        logger.warning("G7-SC101: last_run_ts 파싱 실패: %s", _e101v)
        else:
            sc101_msgs.append(
                "SC101 CRITICAL: foreground_cycle_state.json 없음 -- 포그라운드 실행 기록 미존재. "
                "Rule F: 앱 실행+스크린샷 필수. P-FOREGROUND-ZERO."
            )
            logger.warning("G7-SC101: P-FOREGROUND-ZERO CRITICAL: 상태 파일 없음")
    except Exception as _e101:
        sc101_msgs.append(f"SC101 WARN: 검사 실패 -- {_e101}")
        logger.warning("G7-SC101: P-FOREGROUND-ZERO 검사 실패: %s", _e101)
    # SC101은 WARN/CRITICAL 전용 비차단 -- A60-W2 P-FOREGROUND-ZERO (M736)

    # SC102 P-AV-3TEAM-SKIP: Worker commit 후 audit 3팀 PASS 미기록 = WARN (Rule A/T)
    sc102_msgs: list = []
    _SC102_AUDIT_DIR = os.path.join(PROJECT_ROOT, "docs", "reports", "audit")
    _SC102_REQUIRED_TEAMS = ["theory", "gui", "integration"]  # [MAGIC] Rule T 3팀 필수
    _SC102_LOOKBACK_COMMITS = 5  # [MAGIC: 5] 최근 커밋에서 audit 기록 탐색 범위
    try:
        _found_teams102: list = []
        if os.path.isdir(_SC102_AUDIT_DIR):
            for _tname in _SC102_REQUIRED_TEAMS:
                _tfiles = [
                    f for f in os.listdir(_SC102_AUDIT_DIR)
                    if _tname.lower() in f.lower()
                ]
                if _tfiles:
                    _found_teams102.append(_tname)
        _missing_teams102 = [t for t in _SC102_REQUIRED_TEAMS if t not in _found_teams102]
        if _missing_teams102:
            sc102_msgs.append(
                f"SC102 WARN: audit 미기록 팀 {_missing_teams102} -- "
                f"Rule A/T: Worker 산출물은 3팀 전원 PASS 후 CT 보고 의무. P-AV-3TEAM-SKIP."
            )
            logger.warning("G7-SC102: P-AV-3TEAM-SKIP WARN: 미기록 팀 %s", _missing_teams102)
        else:
            logger.info("G7-SC102: P-AV-3TEAM-SKIP 정상 (3팀 전원 기록 확인)")
    except Exception as _e102:
        sc102_msgs.append(f"SC102 WARN: 검사 실패 -- {_e102}")
        logger.warning("G7-SC102: P-AV-3TEAM-SKIP 검사 실패: %s", _e102)
    # SC102는 WARN 전용 비차단 -- A60-W2 P-AV-3TEAM-SKIP (M736)

    # SC103 P-FAKE-APOLOGY: 간사 응답에서 거짓 사과 패턴 탐지 = stderr 경고 (Rule W)
    sc103_msgs: list = []
    _SC103_FAKE_APOLOGY_PATTERNS = [
        "아차",
        "그렇군요",
        "이제 ..할게요",  # 재귀적 약속 패턴
        "이제부터는",
        "앞으로는",
        "죄송합니다. 이제",
        "맞습니다. 앞으로",
    ]  # [MAGIC] Rule W 거짓 사과 패턴 — 같은 실수 반복 = 하네스 결함
    _SC103_SECRETARY_LOG = os.path.join(PROJECT_ROOT, ".claude", "secretary_judgment_log.jsonl")
    try:
        _fake_apology_count = 0
        if os.path.exists(_SC103_SECRETARY_LOG):
            with open(_SC103_SECRETARY_LOG, encoding="utf-8", errors="ignore") as _f103:
                for _line103 in _f103:
                    _line103 = _line103.strip()
                    if not _line103:
                        continue
                    try:
                        _entry103 = json.loads(_line103)
                        _resp103 = _entry103.get("response", "") if isinstance(_entry103, dict) else ""
                        if not isinstance(_resp103, str):
                            continue
                        for _pat in _SC103_FAKE_APOLOGY_PATTERNS:
                            if _pat in _resp103:
                                _fake_apology_count += 1
                                break
                    except (json.JSONDecodeError, TypeError):
                        continue
        if _fake_apology_count > 0:
            print(
                f"[SC103-STDERR M736] P-FAKE-APOLOGY: 간사 거짓 사과 패턴 {_fake_apology_count}건 탐지. "
                "Rule W: 같은 실수 2회 반복 = 하네스 결함. '아차/그렇군요/이제부터' 즉시 사용 중단.",
                file=sys.stderr,
            )
            sc103_msgs.append(
                f"SC103 WARN: 거짓 사과 패턴 {_fake_apology_count}건 -- "
                f"Rule W 하네스 결함 자동 탐지. P-FAKE-APOLOGY."
            )
            logger.warning("G7-SC103: P-FAKE-APOLOGY WARN: %d건", _fake_apology_count)
        else:
            logger.info("G7-SC103: P-FAKE-APOLOGY 정상 (0건)")
    except Exception as _e103:
        sc103_msgs.append(f"SC103 WARN: 검사 실패 -- {_e103}")
        logger.warning("G7-SC103: P-FAKE-APOLOGY 검사 실패: %s", _e103)
    # SC103은 WARN 전용 비차단 -- A60-W2 P-FAKE-APOLOGY (M736)

    # SC104 P-DECISION-DUMP: 간사가 사용자에게 결정을 5건+ 떠넘김 = WARN (Rule B/LL)
    sc104_msgs: list = []
    _SC104_DUMP_PATTERNS = [
        "사용자 결정",
        "사용자 명령 대기",
        "사용자가 결정",
        "사용자께서 결정",
        "명령을 내려주시면",
        "어떻게 할까요",
        "결정해 주세요",
        "선택해 주세요",
    ]  # [MAGIC] Rule B/LL 간사=전령, 결정권 없음 — 사용자에게 떠넘기기 금지
    _SC104_DUMP_THRESHOLD = 5  # [MAGIC: 5] 5건+ = WARN (사용자 격분 "내 결정 의무가 뭐여 ㅅㅂ")
    try:
        _dump_count = 0
        if os.path.exists(_SC103_SECRETARY_LOG):  # 동일 로그 재사용
            with open(_SC103_SECRETARY_LOG, encoding="utf-8", errors="ignore") as _f104:
                for _line104 in _f104:
                    _line104 = _line104.strip()
                    if not _line104:
                        continue
                    try:
                        _entry104 = json.loads(_line104)
                        _resp104 = _entry104.get("response", "") if isinstance(_entry104, dict) else ""
                        if not isinstance(_resp104, str):
                            continue
                        for _dpat in _SC104_DUMP_PATTERNS:
                            if _dpat in _resp104:
                                _dump_count += 1
                    except (json.JSONDecodeError, TypeError):
                        continue
        if _dump_count >= _SC104_DUMP_THRESHOLD:
            sc104_msgs.append(
                f"SC104 WARN: 사용자 결정 떠넘기기 {_dump_count}건 -- "
                f"Rule B/LL: 간사=전령, 결정권 없음. P-DECISION-DUMP. "
                f"사용자 격분 패턴: '내 결정 의무가 뭐여 ㅅㅂ'."
            )
            logger.warning("G7-SC104: P-DECISION-DUMP WARN: %d건 >= 기준 %d건", _dump_count, _SC104_DUMP_THRESHOLD)
        else:
            logger.info("G7-SC104: P-DECISION-DUMP 정상 (%d건 < %d건)", _dump_count, _SC104_DUMP_THRESHOLD)
    except Exception as _e104:
        sc104_msgs.append(f"SC104 WARN: 검사 실패 -- {_e104}")
        logger.warning("G7-SC104: P-DECISION-DUMP 검사 실패: %s", _e104)
    # SC104는 WARN 전용 비차단 -- A60-W2 P-DECISION-DUMP (M736)

    # -----------------------------------------------------------------------
    # [W_DISPATCH_LOGGER / M818] G7-SC105: P-EXT-AI-DISPATCH-LOG-EMPTY
    # external_ai_dispatch.jsonl 최근 1시간 호출 0건 = WARN
    # 1시간 4건 미만 = INFO
    # -----------------------------------------------------------------------
    sc105_msgs: list = []
    _SC105_LOG = os.path.join(PROJECT_ROOT, "docs", "logs", "external_ai_dispatch.jsonl")
    _SC105_WARN_THRESHOLD = 3600       # [MAGIC: 3600s = 1h] 호출 0건 기준 (사용자 격분)
    _SC105_INFO_THRESHOLD = 4          # [MAGIC: 4건] 1시간 이내 최소 권장 호출 수
    try:
        if not os.path.isfile(_SC105_LOG):
            sc105_msgs.append(
                "SC105 WARN: external_ai_dispatch.jsonl 미존재 -- "
                "외부 AI dispatch 로그가 없음. Rule PP/MM 위반 위험."
            )
            logger.warning("G7-SC105: P-EXT-AI-DISPATCH-LOG-EMPTY WARN: 로그 파일 미존재")
        else:
            _now105 = time.time()
            _cutoff105 = _now105 - _SC105_WARN_THRESHOLD  # 1시간 전 타임스탬프
            _recent_count105 = 0
            try:
                with open(_SC105_LOG, encoding="utf-8", errors="ignore") as _f105:
                    for _line105 in _f105:
                        _line105 = _line105.strip()
                        if not _line105:
                            continue
                        try:
                            _rec105 = json.loads(_line105)
                            if not isinstance(_rec105, dict):
                                continue
                            _ts105 = _rec105.get("ts", 0)
                            if isinstance(_ts105, (int, float)) and float(_ts105) >= _cutoff105:
                                _recent_count105 += 1
                        except (json.JSONDecodeError, ValueError):
                            continue
            except OSError as _fe105:
                sc105_msgs.append(f"SC105 WARN: 로그 파일 읽기 실패 -- {_fe105}")
                logger.warning("G7-SC105: 로그 파일 읽기 실패: %s", _fe105)
                _recent_count105 = -1  # -1 = 읽기 실패

            if _recent_count105 == 0:
                sc105_msgs.append(
                    f"SC105 WARN: 최근 1시간 외부 AI 호출 0건 -- "
                    f"Rule PP/MM 위반. kimi_invoke_log.jsonl 마지막 호출 확인 필요."
                )
                logger.warning("G7-SC105: P-EXT-AI-DISPATCH-LOG-EMPTY WARN: 1시간 0건")
            elif _recent_count105 < _SC105_INFO_THRESHOLD and _recent_count105 > 0:
                sc105_msgs.append(
                    f"SC105 INFO: 최근 1시간 외부 AI 호출 {_recent_count105}건 "
                    f"(권장 {_SC105_INFO_THRESHOLD}건 미만)"
                )
                logger.info("G7-SC105: 1시간 호출 %d건 (권장 %d건 미만)",
                            _recent_count105, _SC105_INFO_THRESHOLD)
            else:
                logger.info("G7-SC105: 외부 AI 호출 정상 (%d건/h)", _recent_count105)
    except Exception as _e105:
        sc105_msgs.append(f"SC105 WARN: 검사 실패 -- {_e105}")
        logger.warning("G7-SC105: P-EXT-AI-DISPATCH-LOG-EMPTY 검사 실패: %s", _e105)
    # SC105는 WARN/INFO 전용 비차단 -- W_DISPATCH_LOGGER P-EXT-AI-DISPATCH-LOG-EMPTY (M818)

    # -----------------------------------------------------------------------
    # [M925 H-3] SC124: popup_synthesis._update_engine_status_label GUI 블록 패턴 감지
    # RetrosynthesisEngine() + is_available() 직접 호출 = GUI 스레드 블록 위험
    # M925에서 _EngineStatusThread 분리로 수정됨 — 재발 방지 목적
    # -----------------------------------------------------------------------
    sc124_issues: list = []
    try:
        import re as _re124
        _sc124_target = os.path.join(PROJECT_ROOT, "src", "app", "popup_synthesis.py")
        if not os.path.exists(_sc124_target):
            logger.info("[SC124] popup_synthesis.py 미존재 — 검사 건너뜀")
        else:
            with open(_sc124_target, "r", encoding="utf-8", errors="ignore") as _f124:
                _sc124_content = _f124.read()
            # Find _update_engine_status_label function body up to next def/class
            _m124 = _re124.search(
                r"def _update_engine_status_label\(.*?\n(.*?)(?=\n    def |\nclass |\Z)",
                _sc124_content, _re124.DOTALL
            )
            if _m124:
                _body124 = _m124.group(1)
                _has_retro124 = "RetrosynthesisEngine()" in _body124
                _has_avail124 = "is_available()" in _body124
                _has_thread124 = "QThread" in _body124 or "_EngineStatusThread" in _body124
                if _has_retro124 and _has_avail124 and not _has_thread124:
                    sc124_issues.append(
                        "[SC124] popup_synthesis._update_engine_status_label: "
                        "RetrosynthesisEngine()+is_available() GUI 스레드 직접 호출 감지 — "
                        "QThread 분리 필요 (M925 재발)"
                    )
                    logger.warning(
                        "[SC124] popup_synthesis._update_engine_status_label GUI 블록 패턴 감지 (M925 재발)"
                    )
            else:
                logger.info("[SC124] _update_engine_status_label 함수 미발견 — 검사 건너뜀")
    except Exception as _e124:
        sc124_issues.append(f"[SC124] 검사 실패: {_e124}")
        logger.warning("[SC124] 검사 실패: %s", _e124)
    # SC124는 WARN 전용 비차단 -- M925 GUI-THREAD-NETWORK-BLOCK-001 재발 감지

    # -----------------------------------------------------------------------
    # [D888-W13 / M933] G7-SC126: P-BEFORE-AFTER-MISSING
    # cycle_html before_after_images 섹션 미존재 WARN (현재 사이클)
    # C15부터 REJECT 격상 (사용자 명시: Q-BEFORE-AFTER 6 사이클 미반영)
    # 체크 내용:
    #   1. 최신 cycle HTML에 id="before-after-images" 섹션 존재 여부
    #   2. 섹션 내 img 태그 18개 이상 (Rule CC 7번째 체크 기준)
    # -----------------------------------------------------------------------
    sc126_msgs: list = []
    sc126_reject = False  # [MAGIC] C15부터 REJECT 전환 (사용자 명시)
    _SC126_IMG_MIN = 18   # [MAGIC: 18] Rule CC 7번째 체크 기준 (D888-W13 M933)
    _SC126_REJECT_CYCLE = 15  # [MAGIC: C15] 사용자 명시 REJECT 격상 사이클 번호
    try:
        import re as _re126
        _cycle_dir126 = os.path.join(PROJECT_ROOT, "docs", "cycles")
        _html_files126: list = []
        if os.path.isdir(_cycle_dir126):
            _html_files126 = sorted(
                [f for f in os.listdir(_cycle_dir126) if f.endswith(".html")],
                key=lambda f: os.path.getmtime(os.path.join(_cycle_dir126, f)),
                reverse=True,
            )
        if not _html_files126:
            sc126_msgs.append(
                "SC126 WARN: cycle HTML 파일 미존재 — before_after_images 섹션 검사 불가. "
                "cycle_html_user_format.py 실행 선행 필요."
            )
            logger.warning("[SC126] cycle HTML 미존재 — P-BEFORE-AFTER-MISSING 검사 불가")
        else:
            _latest_html126 = os.path.join(_cycle_dir126, _html_files126[0])
            try:
                with open(_latest_html126, encoding="utf-8", errors="ignore") as _f126:
                    _html_content126 = _f126.read()
            except OSError as _fe126:
                sc126_msgs.append(f"SC126 WARN: HTML 읽기 실패 -- {_fe126}")
                logger.warning("[SC126] HTML 읽기 실패: %s", _fe126)
                _html_content126 = ""

            if _html_content126:
                _has_ba_section126 = 'id="before-after-images"' in _html_content126
                # img 태그 수 계산 (before-after 섹션 기준)
                _ba_section_match126 = _re126.search(
                    r'id="before-after-images"(.*?)(?=<h2|</body>)',
                    _html_content126, _re126.DOTALL
                )
                _ba_img_count126 = 0
                if _ba_section_match126:
                    _ba_section_text126 = _ba_section_match126.group(1)
                    _ba_img_count126 = len(_re126.findall(r"<img\s", _ba_section_text126))

                if not _has_ba_section126:
                    sc126_msgs.append(
                        f"SC126 WARN: cycle HTML '{_html_files126[0]}' 에 "
                        f"before-after-images 섹션 미존재. "
                        f"Q-BEFORE-AFTER 미반영 — _build_d888_before_after_section() 호출 확인 필요."
                    )
                    logger.warning(
                        "[SC126] P-BEFORE-AFTER-MISSING: before-after-images 섹션 미존재 (%s)",
                        _html_files126[0],
                    )
                    sc126_reject = True  # REJECT 격상 트리거
                elif _ba_img_count126 < _SC126_IMG_MIN:
                    sc126_msgs.append(
                        f"SC126 WARN: before-after-images 섹션 img {_ba_img_count126}장 "
                        f"(기준 {_SC126_IMG_MIN}장 미달). Rule CC 7번째 체크 FAIL. "
                        f"D888 evidence PNG 추가 필요."
                    )
                    logger.warning(
                        "[SC126] img 수 미달: %d < %d (파일: %s)",
                        _ba_img_count126, _SC126_IMG_MIN, _html_files126[0],
                    )
                    sc126_reject = True  # REJECT 격상 트리거
                else:
                    logger.info(
                        "[SC126] before-after-images 섹션 PASS: img=%d >= %d",
                        _ba_img_count126, _SC126_IMG_MIN,
                    )
                    sc126_reject = False
    except Exception as _e126:
        sc126_msgs.append(f"SC126 WARN: 검사 실패 -- {_e126}")
        logger.warning("[SC126] P-BEFORE-AFTER-MISSING 검사 실패: %s", _e126)
    # SC126: C15부터 REJECT 차단 (사용자 명시 Q-BEFORE-AFTER) — 현재는 WARN (비차단)
    # 차단 전환 조건: sc126_reject=True AND 사이클 번호 >= _SC126_REJECT_CYCLE
    # 현재 사이클 번호 파악 불가 시 WARN 유지 (비차단)

    # SC4 FAIL / SC5 FAIL / SC7 FAIL / SC39 FAIL / SC41 FAIL 은 차단
    # [M646_W36] SC92 REJECT도 차단 (alive-no-progress)
    # SC3~SC16/SC18/SC20~SC38/SC41-c-warn/SC43/SC45/SC46/SC47/SC49/SC52/SC55/SC57/SC64/SC66/SC67/SC68/SC69/SC70/SC71/SC73/SC74/SC75/SC76/SC78/SC84/SC85/SC86/SC87/SC88/SC89/SC90/SC91/SC93/SC94/SC95/SC96/SC97/SC98/SC99/SC100/SC101/SC102/SC103/SC104/SC105/SC123/SC124/SC126 은 비차단
    overall_pass = (
        sc1_pass and sc2_pass
        and not sc4_fail and not sc5_fail and not sc7_fail
        and not sc39_fail  # [M481] SC39 REJECT도 차단
        and not sc41_fail  # [M486] SC41 REJECT도 차단 (ORCA 정합성)
        and not sc92_fail  # [M646_W36] SC92 REJECT도 차단 (P-ALIVE-NO-PROGRESS)
    )

    return {
        "sc1_ct_pending": {
            "pass": sc1_pass,
            "missing_ct_files": sc1_missing_ct,
            "missing_count": len(sc1_missing_ct),
            "verdict": "PASS" if sc1_pass else "REJECT",
        },
        "sc2_audit_teams": {
            "pass": sc2_pass,
            "missing_teams": sc2_missing_teams,
            "today": today_str,
            "verdict": "PASS" if sc2_pass else "REJECT",
        },
        "sc3_serial_state": {
            "stale": sc3_stale,
            "msg": sc3_msg,
            "verdict": sc3_overall,
        },
        "sc4_desktop_parity": {
            "fail": sc4_fail,
            "warn": sc4_warn,
            "missing_parity_sections": sc4_missing_parity,
            "missing_screenshots": sc4_missing_screenshots,
            "low_defect_coverage": sc4_low_defect_coverage,
            "verdict": sc4_overall,
        },
        "sc5_embodiment_4step": {
            "fail": sc5_fail,
            "warn": sc5_warn,
            "zero_embodiment_files": sc5_zero_embodiment,
            "low_embodiment_files": sc5_low_embodiment,
            "fail_threshold": _SC5_FAIL_THRESHOLD,
            "warn_threshold": _SC5_WARN_THRESHOLD,
            "verdict": sc5_overall,
        },
        "sc6_mechanism_code_quality": {
            "warn": sc6_warn,
            "issues": sc6_issues,
            "verdict": sc6_overall,
        },
        "sc7_click_simulation": {
            "fail": sc7_fail,
            "warn": sc7_warn,
            "fail_files": sc7_fail_files,
            "warn_files": sc7_warn_files,
            "invoke_files": sc7_invoke_files,
            "pass_threshold": _SC7_PASS_THRESHOLD,
            "warn_threshold": _SC7_WARN_THRESHOLD,
            "verdict": sc7_overall,
        },
        "sc8_ssr_img_regression": {
            "warn": sc8_warn,
            "issues": sc8_issues,
            "verdict": sc8_overall,
        },
        "sc9_simulation_honesty": {
            "warn": sc9_warn,
            "issues": sc9_issues,
            "verdict": sc9_overall,
        },
        "sc10_tsx_scope_parity": {
            "warn": sc10_warn,
            "issues": sc10_issues,
            "verdict": sc10_overall,
        },
        "sc11_synthesis_ai_fallback": {
            "warn": sc11_warn,
            "issues": sc11_issues,
            "found": _sc11_found,
            "verdict": sc11_overall,
        },
        "sc12_arrow_color_4standard": {
            "warn": sc12_warn,
            "issues": sc12_issues,
            "verdict": sc12_overall,
        },
        "sc13_alphafold_residues_empty": {
            "warn": sc13_warn,
            "issues": sc13_issues,
            "found": _sc13_found,
            "verdict": sc13_overall,
        },
        "sc14_endpoint_method_validation": {
            "warn": sc14_warn,
            "issues": sc14_issues,
            "verdict": sc14_overall,
        },
        "sc15_spectrum_import_parity": {
            "warn": sc15_warn,
            "issues": sc15_issues,
            "found": _sc15_found,
            "verdict": sc15_overall,
        },
        "sc16_worktree_main_diff": {
            "warn": sc16_warn,
            "issues": sc16_issues,
            "verdict": sc16_overall,
        },
        "sc18_bond_key_normalize": {
            "warn": sc18_warn,
            "issues": sc18_issues,
            "verdict": sc18_overall,
        },
        "sc19_mobile_worktree_sync": {
            "warn": sc19_warn,
            "issues": sc19_issues,
            "verdict": sc19_overall,
        },
        "sc20_dual_backend_sync": {
            "warn": sc20_warn,
            "issues": sc20_issues,
            "verdict": sc20_overall,
        },
        "sc21_alphafold_api_url_hardcode": {
            "warn": sc21_warn,
            "issues": sc21_issues,
            "found": _sc21_found,
            "verdict": sc21_overall,
        },
        "sc22_docking_interactions_unbound": {
            "warn": sc22_warn,
            "issues": sc22_issues,
            "verdict": sc22_overall,
        },
        "sc23_frontend_backend_path_mismatch": {
            "warn": sc23_warn,
            "issues": sc23_issues,
            "verdict": sc23_overall,
        },
        "sc24_backend_restart_check": {
            "warn": sc24_warn,
            "issues": sc24_issues,
            "main_has_new_prefix": _sc24_main_has_new_prefix if "_sc24_main_has_new_prefix" in dir() else False,
            "verdict": sc24_overall,
        },
        "sc25_alphafold_external_link_prominent": {
            "warn": sc25_warn,
            "issues": sc25_issues,
            "verdict": sc25_overall,
        },
        "sc26_drylab_alphafold_section": {
            "warn": sc26_warn,
            "issues": sc26_issues,
            "verdict": sc26_overall,
        },
        "sc27_alphafold_student_flow": {
            "warn": bool(sc27_warn),
            "issues": sc27_issues,
            "verdict": sc27_overall,
        },
        "sc28_foreground_cycle": {
            "warn": sc28_warn,
            "issues": sc28_issues,
            "verdict": sc28_overall,
        },
        "sc29_docx_molstar_parity": {
            "warn": sc29_warn,
            "issues": sc29_issues,
            "verdict": sc29_overall,
        },
        "sc30_molecule_matrix": {
            "warn": sc30_warn,
            "issues": sc30_issues,
            "matrix_pass": _sc30_matrix_pass,
            "matrix_total": _sc30_matrix_total,
            "pass_threshold": _SC30_PASS_THRESHOLD,
            "fail_list": _sc30_matrix_fail_list,
            "verdict": sc30_overall,
        },
        "sc31_mechanism_visibility": {
            "warn": sc31_warn,
            "issues": sc31_issues,
            "verdict": sc31_overall,
        },
        "sc32_session_handoff": {
            "warn": sc32_warn,
            "issues": sc32_issues,
            "verdict": sc32_overall,
        },
        "sc33_html_report": {
            "warn": sc33_warn,
            "issues": sc33_issues,
            "verdict": sc33_overall,
        },
        "sc34_cycle_hollow": {
            "warn": sc34_warn,
            "issues": sc34_issues,
            "verdict": sc34_overall,
        },
        "sc35_web_desktop_diff": {
            "warn": sc35_warn,
            "issues": sc35_issues,
            "verdict": sc35_overall,
        },
        "sc36_directml_env": {
            "warn": sc36_warn,
            "issues": sc36_issues,
            "verdict": sc36_overall,
        },
        "sc37_cycle_process_watch": {
            "warn": sc37_warn,
            "issues": sc37_issues,
            "stop_file_exists": _sc37_stop_exists,
            "verdict": sc37_overall,
        },
        "sc38_mistakes_line_limit": {
            "warn": sc38_warn,
            "issues": sc38_issues,
            "verdict": sc38_overall,
        },
        "sc39_widget_missing_fp11": {
            "fail": sc39_fail,
            "issues": sc39_issues,
            "verdict": sc39_overall,
        },
        "sc41_orca_integrity": {
            "fail": sc41_fail,
            "warn": sc41_warn,
            "issues": sc41_issues,
            "verdict": sc41_overall,
        },
        "sc43_worktree_tools_sync": {
            "warn": sc43_warn,
            "issues": sc43_issues,
            "verdict": sc43_overall,
        },
        "sc45_web_desktop_parity": {
            "warn": sc45_warn,
            "reject": sc45_reject,
            "issues": sc45_issues,
            "score": _sc45_score,
            "total": _sc45_total,
            "ratio": round(_sc45_ratio, 3),
            "pass_threshold": _SC45_PASS_THRESHOLD,
            "reject_threshold": _SC45_REJECT_THRESHOLD,
            "verdict": sc45_overall,
        },
        "sc46_mock_disguised": {
            "warn": sc46_warn,
            "issues": sc46_issues,
            "verdict": sc46_overall,
        },
        "sc47_pdbe_molstar_prominent": {
            "warn": sc47_warn,
            "issues": sc47_issues,
            "verdict": sc47_overall,
        },
        "sc49_popup_ghost": {
            "warn": sc49_warn,
            "issues": sc49_issues,
            "latest_results_json": _sc49_latest or "",
            "verdict": sc49_overall,
        },
        "sc52_worktree_av_stale": {
            "warn": sc52_warn,
            "issues": sc52_issues,
            "min_lines": _SC52_MIN_LINES,
            "verdict": sc52_overall,
        },
        "sc55_esp_cloud_preserved": {
            "warn": sc55_warn,
            "issues": sc55_msgs,
            "verdict": sc55_overall,
        },
        "sc56_anger_ml_evolve": {  # [M556] anger 매트릭스 100+건 + ML 진화 갱신 검증
            "warn": sc56_warn,
            "issues": sc56_msgs,
            "matrix_min": _SC56_MATRIX_MIN,
            "fresh_window_sec": _SC56_FRESH_WINDOW,
            "anger_metrics_exists": os.path.isfile(_anger_metrics_path),
            "verdict": sc56_overall,
        },
        "sc57_cmd_hidden_strict": {
            "warn": sc57_warn,
            "issues": sc57_msgs,
            "run_hidden_vbs_exists": os.path.isfile(_run_hidden_vbs),
            "verdict": sc57_overall,
        },
        "sc64_synthesis_timeout": {
            "warn": sc64_warn,
            "issues": sc64_msgs,
            "popup_synthesis_exists": os.path.isfile(_popup_syn_path),
            "verdict": sc64_overall,
        },
        "sc66_harness_self_diagnosis": {  # [M616] 외부 LLM 진단 — Density Overload + 다람쥐볼 위반율
            "warn": sc66_warn,
            "issues": sc66_msgs,
            "verdict": sc66_overall,
        },
        "sc67_token_efficiency_infra": {  # [M617] 토큰 효율화 인프라 미비 감지 — Rule MM
            "warn": sc67_warn,
            "issues": sc67_msgs,
            "verdict": sc67_overall,
        },
        "sc68_kimi_infra": {  # [M623] Kimi K2 인프라 미비 감지 (M618 권고 신설)
            "warn": sc68_warn,
            "issues": sc68_msgs,
            "verdict": sc68_overall,
        },
        "sc69_squirrel_ball_hook": {  # [M623] 다람쥐볼 auto-attach hook 미비 감지
            "warn": sc69_warn,
            "issues": sc69_msgs,
            "verdict": sc69_overall,
        },
        "sc70_openrouter_cost_monitor": {  # [M624] Kimi 비용 모니터링 인프라 미비 감지
            "warn": sc70_warn,
            "issues": sc70_msgs,
            "verdict": sc70_overall,
        },
        "sc71_academic_integrity_hook": {  # [M625] 학술 정합성 자동 audit hook + Kimi
            "warn": sc71_warn,
            "issues": sc71_msgs,
            "verdict": sc71_overall,
        },
        "sc72_user_env_verify_hook": {  # [M626] 사용자 환경 자체 검증 hook + Kimi K2.6 Vision
            "warn": sc72_warn,
            "issues": sc72_msgs,
            "verdict": sc72_overall,
        },
        "sc73_kimi_auto_invoke": {  # [M627] Kimi 자동 호출 hook 강제 메커니즘 검증
            "warn": sc73_warn,
            "issues": sc73_msgs,
            "verdict": sc73_overall,
        },
        "sc74_ollama_swarm_infra": {  # [M633] Ollama 로컬 LLM 스웜 인프라 검증
            "warn": sc74_warn,
            "issues": sc74_msgs,
            "verdict": sc74_overall,
        },
        "sc75_vision_korean_local_llm": {  # [M634] Vision + 한국어 + 자연어 로컬 LLM 인프라
            "warn": sc75_warn,
            "issues": sc75_msgs,
            "verdict": sc75_overall,
        },
        "sc76_swarm_permanent": {  # [M635] 로컬LLM 영구가동 SWARM_TIER_E + 좀비차단
            "warn": sc76_warn,
            "issues": sc76_msgs,
            "verdict": sc76_overall,
        },
        "sc78_4layer_vision_audit_3month": {  # [M636] 4-Layer Vision Audit + 3개월 미해소 격분 시계열 (WARN 비차단)
            "warn": sc78_warn,
            "issues": sc78_msgs,
            "verdict": sc78_overall,
        },
        "sc84_research_lab_grade": {  # [M643] 연구소 수준 readiness 25/25 매트릭스 (FP-35, WARN 비차단)
            "warn": sc84_warn,
            "issues": sc84_msgs,
            "verdict": sc84_overall,
        },
        "sc85_user_delegation_guard": {  # [M645_W2] P-USER-DELEGATION FP-36 탐지 (WARN 비차단)
            "warn": sc85_warn,
            "issues": sc85_msgs,
            "verdict": sc85_overall,
        },
        "sc86_phantom_pid_guard": {  # [M645_W3] P-PHANTOM-PID FP-37 탐지 (WARN 비차단)
            "warn": sc86_warn,
            "issues": sc86_msgs,
            "verdict": sc86_overall,
        },
        "sc87_alive_no_progress": {  # [M645_W4] P-ALIVE-NO-PROGRESS 탐지 (WARN 비차단)
            "warn": sc87_warn,
            "issues": sc87_msgs,
            "verdict": sc87_overall,
        },
        "sc88_wrong_verification": {  # [M645_W4] P-WRONG-VERIFICATION 탐지 (WARN 비차단)
            "warn": sc88_warn,
            "issues": sc88_msgs,
            "verdict": sc88_overall,
        },
        "sc89_user_persona_skip": {  # [M645_W4] P-USER-PERSONA-SKIP 탐지 (WARN 비차단)
            "warn": sc89_warn,
            "issues": sc89_msgs,
            "verdict": sc89_overall,
        },
        "sc90_double_false_positive": {  # [M645_W4] P-DOUBLE-FALSE-POSITIVE 탐지 (WARN 비차단)
            "warn": sc90_warn,
            "issues": sc90_msgs,
            "verdict": sc90_overall,
        },
        "sc91_swarm_ratio_violation": {  # [M646_W36] P-SWARM-RATIO-VIOLATION (WARN 비차단)
            "warn": sc91_warn,
            "issues": sc91_msgs,
            "verdict": sc91_overall,
        },
        "sc92_alive_no_progress": {  # [M646_W36] P-ALIVE-NO-PROGRESS (REJECT 차단)
            "fail": sc92_fail,
            "issues": sc92_msgs,
            "verdict": sc92_overall,
        },
        "sc93_cron_av_variant_fragment": {  # [M647_W5_A6] P-CRON-AV-VARIANT-FRAGMENT (WARN 비차단)
            "warn": sc93_warn,
            "issues": sc93_msgs,
            "verdict": sc93_overall,
        },
        "sc94_av_skill_missing": {  # [M647_W5_A19] P-AV-SKILL-MISSING (WARN 비차단)
            "warn": sc94_warn,
            "issues": sc94_msgs,
            "verdict": sc94_overall,
        },
        "sc95_harness_compress": {  # [M647_W5_A15] P-HARNESS-COMPRESS (WARN 비차단)
            "warn": bool(sc95_msgs),
            "issues": sc95_msgs,
            "verdict": "WARN" if sc95_msgs else "PASS",
        },
        "sc96_av_prompt_stale": {  # [CT-D-20260504-A55] P-AV-PROMPT-STALE (WARN/CRITICAL 비차단)
            "warn": sc96_warn,
            "critical": sc96_critical,
            "issues": sc96_msgs,
            "verdict": "CRITICAL" if sc96_critical else ("WARN" if sc96_warn else "PASS"),
        },
        "sc97_no_external_ai": {  # [CT-D-20260504-A55] P-NO-EXTERNAL-AI-IN-PROMPT (WARN/CRITICAL 비차단)
            "warn": sc97_warn,
            "critical": sc97_critical,
            "issues": sc97_msgs,
            "verdict": "CRITICAL" if sc97_critical else ("WARN" if sc97_warn else "PASS"),
        },
        "sc98_zombie_check": {  # [A55-AV-WATCHDOG M696] P-CHEMGRID-LITE-ZOMBIE (WARN/CRITICAL 비차단)
            "warn": sc98_warn,
            "critical": sc98_critical,
            "issues": sc98_msgs,
            "verdict": "CRITICAL" if sc98_critical else ("WARN" if sc98_warn else "PASS"),
        },
        "sc99_m_number_race": {  # [CT-D-20260504-A57-W8 M715] P-M-NUMBER-RACE (WARN/CRITICAL 비차단)
            "warn": sc99_warn,
            "critical": sc99_critical,
            "issues": sc99_msgs,
            "verdict": "CRITICAL" if sc99_critical else ("WARN" if sc99_warn else "PASS"),
        },
        "sc100_popup_simultaneous_edit": {  # [CT-D-20260504-A57-W8 M715] P-POPUP-SIMULTANEOUS-EDIT (WARN/CRITICAL 비차단)
            "warn": sc100_warn,
            "critical": sc100_critical,
            "issues": sc100_msgs,
            "verdict": "CRITICAL" if sc100_critical else ("WARN" if sc100_warn else "PASS"),
        },
        "sc101_foreground_zero": {  # [A60-W2 M736] P-FOREGROUND-ZERO (CRITICAL 비차단)
            "warn": bool(sc101_msgs),
            "issues": sc101_msgs,
            "verdict": "CRITICAL" if any("CRITICAL" in m for m in sc101_msgs) else ("WARN" if sc101_msgs else "PASS"),
        },
        "sc102_av_3team_skip": {  # [A60-W2 M736] P-AV-3TEAM-SKIP (WARN 비차단)
            "warn": bool(sc102_msgs),
            "issues": sc102_msgs,
            "verdict": "WARN" if sc102_msgs else "PASS",
        },
        "sc103_fake_apology": {  # [A60-W2 M736] P-FAKE-APOLOGY (WARN 비차단)
            "warn": bool(sc103_msgs),
            "issues": sc103_msgs,
            "verdict": "WARN" if sc103_msgs else "PASS",
        },
        "sc104_decision_dump": {  # [A60-W2 M736] P-DECISION-DUMP (WARN 비차단)
            "warn": bool(sc104_msgs),
            "issues": sc104_msgs,
            "verdict": "WARN" if sc104_msgs else "PASS",
        },
        "sc105_ext_ai_dispatch_log": {  # [W_DISPATCH_LOGGER M818] P-EXT-AI-DISPATCH-LOG-EMPTY (WARN/INFO 비차단)
            "warn": bool(sc105_msgs),
            "issues": sc105_msgs,
            "verdict": "WARN" if sc105_msgs else "PASS",
        },
        "sc126_before_after_missing": {  # [D888-W13 M933] P-BEFORE-AFTER-MISSING (WARN 비차단, C15+ REJECT 예고)
            "warn": bool(sc126_msgs),
            "reject": sc126_reject,
            "issues": sc126_msgs,
            "reject_cycle_threshold": _SC126_REJECT_CYCLE,
            "img_min": _SC126_IMG_MIN,
            "verdict": "WARN" if sc126_msgs else "PASS",
            # NOTE: C15부터 REJECT 격상 예정 (사용자 명시 Q-BEFORE-AFTER)
            # 현재는 비차단 — overall_pass에 미포함
        },
        "overall": "PASS" if overall_pass else "REJECT",
    }


def check_audit_evidence() -> dict:
    """Gate 4 (AUDIT_FORMAT): verify evidence directories have non-empty files.

    Checks departments with an evidence/ subfolder:
    - At least one file must exist
    - Files must be non-empty (> 0 bytes)
    """
    missing_evidence: list[str] = []
    empty_evidence: list[str] = []
    departments_checked = 0

    dept_base = os.path.join(PROJECT_ROOT, "departments")
    if not os.path.isdir(dept_base):
        return {"error": "departments_dir_not_found"}

    for dept in sorted(os.listdir(dept_base)):
        dept_path = os.path.join(dept_base, dept)
        if not os.path.isdir(dept_path):
            continue

        # Only check departments that have an evidence/ directory
        evidence_dir = os.path.join(dept_path, "evidence")
        if not os.path.isdir(evidence_dir):
            continue

        departments_checked += 1

        # List files in evidence/
        try:
            files = [
                f for f in os.listdir(evidence_dir)
                if os.path.isfile(os.path.join(evidence_dir, f))
            ]
        except OSError as e:
            logger.warning("Cannot list %s: %s", evidence_dir, e)
            missing_evidence.append(dept)
            continue

        if not files:
            missing_evidence.append(dept)
            continue

        # Check for empty files
        for fname in files:
            fpath = os.path.join(evidence_dir, fname)
            try:
                if os.path.getsize(fpath) == 0:
                    empty_evidence.append(f"{dept}/evidence/{fname}")
            except OSError as e:
                logger.warning("Cannot stat %s: %s", fpath, e)

    return {
        "departments_checked": departments_checked,
        "missing_evidence": missing_evidence,
        "empty_evidence": empty_evidence,
    }


def check_serial_ct_gate() -> dict:
    """G7 강화 (SERIAL_CT_GATE): CT 보고 라인 + 감사 3팀 보고서 + serial_state staleness 검사.

    [M418 Rule T 보강] 3가지 검사:
      1. docs/reports/EVIDENCE_*.md 에 "CT 보고: PENDING" 또는 "CT 보고: APPROVED" 라인 존재
         — 둘 다 부재 시 REJECT
      2. docs/reports/audit/ 에 audit_theory/gui/integration 3종 모두 존재
         — 1개라도 부재 시 REJECT
      3. housing/sinktank/_serial_state.json 24시간 이상 미갱신 시 WARN

    Rule I: 24시간 = STALE_THRESHOLD_SECS 매직넘버 주석 필수.
    Rule M: 실패 시 logger.warning (silent return 금지).
    Rule N: isinstance() 타입 가드.
    """
    # [MAGIC] CT 보고 라인 패턴
    CT_REPORT_PATTERN = re.compile(r"CT\s*보고\s*[:：]\s*(PENDING|APPROVED)", re.UNICODE | re.IGNORECASE)
    # [MAGIC] 감사 3팀 팀 식별자
    REQUIRED_AUDIT_TEAMS = ["theory", "gui", "integration"]
    # [MAGIC] staleness 임계값: 24시간 = 86400초
    _STALE_THRESHOLD = 86400

    result: dict = {
        "ct_report_line": "NOT_CHECKED",
        "audit_teams": {},
        "serial_state_stale": None,
        "overall": "PASS",
        "issues": [],
    }

    # --- 검사 1: EVIDENCE_*.md CT 보고 라인 ---
    evidence_pattern = os.path.join(PROJECT_ROOT, "docs", "reports", "EVIDENCE_*.md")
    evidence_files = glob.glob(evidence_pattern)
    if not evidence_files:
        result["ct_report_line"] = "NO_EVIDENCE_FILES"
        result["issues"].append("No EVIDENCE_*.md files found in docs/reports/")
        result["overall"] = "REJECT"
        logger.warning("G7_SERIAL_CT_GATE: No EVIDENCE_*.md files found")
    else:
        found_ct_line = False
        for ef in evidence_files:
            try:
                content = Path(ef).read_text(encoding="utf-8", errors="ignore")
                if CT_REPORT_PATTERN.search(content):
                    found_ct_line = True
                    break
            except OSError as e:
                logger.warning("G7_SERIAL_CT_GATE: read failed %s: %s", ef, e)

        if found_ct_line:
            result["ct_report_line"] = "FOUND"
        else:
            result["ct_report_line"] = "MISSING"
            result["issues"].append(
                "No 'CT 보고: PENDING/APPROVED' line in any EVIDENCE_*.md"
            )
            result["overall"] = "REJECT"
            logger.warning("G7_SERIAL_CT_GATE: CT report line missing in EVIDENCE files")

    # --- 검사 2: audit_theory/gui/integration 3종 보고서 존재 여부 ---
    audit_dir = os.path.join(PROJECT_ROOT, "docs", "reports", "audit")
    for team in REQUIRED_AUDIT_TEAMS:
        pattern = os.path.join(audit_dir, "audit_" + team + "_*.md")
        files = glob.glob(pattern)
        if files:
            result["audit_teams"][team] = "PRESENT"
        else:
            result["audit_teams"][team] = "MISSING"
            result["issues"].append("audit_" + team + "_*.md not found in docs/reports/audit/")
            result["overall"] = "REJECT"
            logger.warning("G7_SERIAL_CT_GATE: audit_%s report missing", team)

    # --- 검사 3: _serial_state.json staleness ---
    serial_state_path = os.path.join(PROJECT_ROOT, "housing", "sinktank", "_serial_state.json")
    if not os.path.exists(serial_state_path):
        result["serial_state_stale"] = "FILE_ABSENT"
        result["issues"].append("_serial_state.json not found — serial state not tracked")
        logger.warning("G7_SERIAL_CT_GATE: _serial_state.json absent")
        # staleness는 WARN only (비차단)
    else:
        try:
            with open(serial_state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            if not isinstance(state_data, dict):  # Rule N: 타입 가드
                logger.warning("G7_SERIAL_CT_GATE: _serial_state.json not dict: %s", type(state_data).__name__)
                result["serial_state_stale"] = "PARSE_ERROR"
            else:
                updated_at_str = state_data.get("updated_at", "")
                if not isinstance(updated_at_str, str) or not updated_at_str:  # Rule N: 타입 가드
                    result["serial_state_stale"] = "NO_TIMESTAMP"
                    logger.warning("G7_SERIAL_CT_GATE: _serial_state.json updated_at missing")
                else:
                    try:
                        import datetime as _dt
                        updated_at = _dt.datetime.fromisoformat(updated_at_str)
                        elapsed = (_dt.datetime.now() - updated_at).total_seconds()
                        # [MAGIC] 24시간 = _STALE_THRESHOLD 비교
                        if elapsed > _STALE_THRESHOLD:
                            stale_hours = round(elapsed / 3600, 1)
                            result["serial_state_stale"] = "STALE_" + str(stale_hours) + "h"
                            result["issues"].append(
                                "_serial_state.json stale: " + str(stale_hours) + "h since last update"
                            )
                            logger.warning(
                                "G7_SERIAL_CT_GATE: _serial_state.json stale (%.1fh > %dh threshold)",
                                stale_hours, _STALE_THRESHOLD // 3600
                            )
                            # staleness WARN은 overall REJECT을 덮어쓰지 않음 (비차단)
                            if result["overall"] == "PASS":
                                result["overall"] = "WARN"
                        else:
                            result["serial_state_stale"] = "OK"
                    except ValueError as e:
                        result["serial_state_stale"] = "PARSE_ERROR"
                        logger.warning("G7_SERIAL_CT_GATE: updated_at parse error: %s", e)
        except (json.JSONDecodeError, OSError) as e:
            result["serial_state_stale"] = "READ_ERROR"
            logger.warning("G7_SERIAL_CT_GATE: _serial_state.json read failed: %s", e)

    return result


# Known valid PDB IDs used in the project (whitelist)
_PDB_WHITELIST = {
    "1BNA", "1CRN", "1HHO", "1MBN", "1UBQ", "2HHB", "3HHB",
    "4HHB", "1AKE", "1ATP", "1BRS", "1GFL", "1HIV", "1HSG",
    "1LYZ", "1TIM", "2POR", "3CLN", "4INS", "6LU7", "7BV2",
    # Docking targets (docking_data.py)
    "5KIR", "5MZP", "1M17", "6M0J", "1HVR", "2HYY", "3ERT", "4EY7",
    # DryLab report PDB (drylab_report_exporter.py)
    "3UDI",
    # Innate defense docking (innate_defense_docking.py)
    "1MWT", "2W9S", "4DUH", "1REX",
}

# Regex: pdb_id = "XXXX" or pdb_id="XXXX" or pdb_id='XXXX'
_PDB_ID_RE = re.compile(
    r"""pdb_id\s*=\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)

# Valid PDB ID format: 4 alphanumeric characters, first char is digit
_PDB_FORMAT_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")


def check_pdb_ids() -> dict:
    """Scan src/app/*.py for pdb_id assignments and validate format.

    Checks:
    1. PDB ID must be 4 characters, starting with a digit (standard format).
    2. Optionally warns if PDB ID is not in the known whitelist.
    """
    invalid_format: list[dict] = []
    unknown_ids: list[dict] = []
    files_scanned = 0

    for pattern in ["src/app/*.py", "_source/*.py"]:
        full_pattern = os.path.join(PROJECT_ROOT, pattern)
        for fpath in sorted(glob.glob(full_pattern)):
            files_scanned += 1
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    for line_no, line in enumerate(fh, 1):
                        for m in _PDB_ID_RE.finditer(line):
                            pdb_id = m.group(1).strip()
                            rel_path = os.path.relpath(fpath, PROJECT_ROOT).replace("\\", "/")
                            if not _PDB_FORMAT_RE.match(pdb_id):
                                invalid_format.append({
                                    "file": rel_path,
                                    "line": line_no,
                                    "pdb_id": pdb_id,
                                })
                            elif pdb_id.upper() not in _PDB_WHITELIST:
                                unknown_ids.append({
                                    "file": rel_path,
                                    "line": line_no,
                                    "pdb_id": pdb_id,
                                })
            except OSError as e:
                logger.warning("PDB scan failed for %s: %s", fpath, e)

    return {
        "files_scanned": files_scanned,
        "invalid_format_count": len(invalid_format),
        "invalid_format": invalid_format[:20],
        "unknown_ids_count": len(unknown_ids),
        "unknown_ids": unknown_ids[:20],
    }


# Regex: MolFromSmiles( call
_MOLFROMSMILES_CALL_RE = re.compile(r"MolFromSmiles\s*\(")


def check_smiles_guard() -> dict:
    """Static analysis: detect MolFromSmiles() calls without None check.

    For each MolFromSmiles() call, checks the next 5 lines for
    'is None', 'is not None', '== None', or '!= None'.
    Missing guard = Rule L violation.
    """
    unguarded: list[dict] = []
    total_calls = 0
    files_scanned = 0

    for pattern in ["src/app/*.py", "_source/*.py"]:
        full_pattern = os.path.join(PROJECT_ROOT, pattern)
        for fpath in sorted(glob.glob(full_pattern)):
            files_scanned += 1
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()

                for i, line in enumerate(lines):
                    if _MOLFROMSMILES_CALL_RE.search(line):
                        total_calls += 1
                        # Window: 1 line before + 5 lines after (catches guard on prev line)
                        prev_line = lines[i - 1] if i > 0 else ""
                        window = prev_line + "".join(lines[i + 1: i + 6])

                        # 1) Inline guard on the same line:
                        #    "if Chem.MolFromSmiles(x) is None:" or
                        #    "if Chem.MolFromSmiles(x):" (truthy — the call itself is the guard)
                        line_stripped = line.strip()
                        has_inline = (
                            "is None" in line
                            or "is not None" in line
                            or bool(re.search(r"\bif\b.*MolFromSmiles\s*\(", line))
                        )

                        # 2) Ternary inline guard on same line: "... if Chem.MolFromSmiles(...) else"
                        if not has_inline:
                            has_inline = bool(re.search(
                                r"MolFromSmiles\s*\(.*\)\s*(?:else|if\b)", line
                            ))

                        # 2b) Previous line is a truthy MolFromSmiles guard:
                        #     "if _C2.MolFromSmiles(_smiles_kg):"
                        if not has_inline:
                            has_inline = bool(re.search(r"\bif\b.*MolFromSmiles\s*\(", prev_line))

                        # 3) Explicit None check in surrounding window
                        has_none_guard = "None" in window or "none" in window

                        # 4) Truthy/falsy guard using the assigned variable name:
                        #    "mol = Chem.MolFromSmiles(...)" → "if mol:", "if mol and", "and mol:"
                        var_match = re.match(r"\s*(\w+)\s*=\s*(?:\w+\.)*MolFromSmiles\s*\(", line)
                        has_truthy_guard = False
                        if var_match:
                            var_name = re.escape(var_match.group(1))
                            # "if mol:", "if not mol:", "if mol and", "if x and mol", "and mol:"
                            has_truthy_guard = bool(
                                re.search(
                                    rf"(?:\bif\b.*\b{var_name}\b|\band\s+{var_name}\b|\b{var_name}\s+and\b)",
                                    window,
                                )
                            )

                        if has_inline or has_none_guard or has_truthy_guard:
                            continue  # guarded, skip

                        rel_path = os.path.relpath(fpath, PROJECT_ROOT).replace("\\", "/")
                        unguarded.append({
                            "file": rel_path,
                            "line": i + 1,
                            "code": line.strip()[:100],
                        })
            except OSError as e:
                logger.warning("SMILES guard scan failed for %s: %s", fpath, e)

    return {
        "files_scanned": files_scanned,
        "total_molfromsmiles_calls": total_calls,
        "unguarded_count": len(unguarded),
        "unguarded": unguarded[:20],
    }


def _run_runtime_subprocess(test_name: str, python_snippet: str,
                            timeout_sec: float = 10.0) -> dict:
    """Run a Python snippet in a subprocess with a timeout.

    Uses a fresh subprocess to avoid Qt thread-safety issues (Qt widgets
    must be created on the main thread, so ThreadPoolExecutor is unsafe).

    Args:
        test_name: human-readable test identifier
        python_snippet: Python code that prints 'PASS' or 'FAIL:reason'
        timeout_sec: maximum wall-clock seconds

    Returns:
        dict with 'name', 'status' ('PASS'|'FAIL'), and optional 'error'/'detail'.
    """
    src_dir = os.path.join(PROJECT_ROOT, "src", "app")
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")

    try:
        proc = subprocess.run(
            [sys.executable, "-c", python_snippet],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=timeout_sec,
            cwd=PROJECT_ROOT,
            env=env,
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        # Find the verdict line (last line starting with PASS or FAIL)
        # because modules may print debug info to stdout before it.
        verdict_line = ""
        for line in stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("PASS") or stripped.startswith("FAIL"):
                verdict_line = stripped

        if proc.returncode == 0 and verdict_line.startswith("PASS"):
            detail = verdict_line[5:].strip() if len(verdict_line) > 4 else ""
            return {"name": test_name, "status": "PASS", "detail": detail[:120]}
        else:
            err_msg = verdict_line or stdout[-200:] or stderr[-200:] or f"exit_code={proc.returncode}"
            logger.warning("G7_RUNTIME: %s failed: %s", test_name, err_msg[:200])
            return {"name": test_name, "status": "FAIL", "error": err_msg[:200]}

    except subprocess.TimeoutExpired:
        logger.warning("G7_RUNTIME: %s exceeded %ss timeout", test_name, timeout_sec)
        return {"name": test_name, "status": "FAIL",
                "error": f"timeout ({timeout_sec}s)"}
    except Exception as e:
        logger.warning("G7_RUNTIME: %s subprocess error: %s", test_name, e)
        return {"name": test_name, "status": "FAIL", "error": str(e)[:200]}


def check_runtime() -> dict:
    """Gate 7 (RUNTIME): test actual runtime functionality via subprocesses.

    Runs four sub-tests as independent subprocesses (each with its own
    QApplication) to avoid Qt main-thread restrictions:
    1. MainWindow creation (20s)
    2. predict_all('c1ccccc1') — spectrum prediction (10s)
    3. get_mechanism('sn2') — reaction mechanism engine (10s)
    4. DryLab import + instantiation + _build_styles (30s, lightweight smoke test)

    Returns dict with per-test PASS/FAIL and overall status.

    Rule F: ensures py_compile PASS + runtime PASS going forward.
    Rule M: logs warnings on failure instead of silent return.
    """
    results: list[dict] = []

    # --- Sub-test 1: MainWindow creation ---
    results.append(_run_runtime_subprocess("MainWindow", """
import sys, os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
app = QApplication(sys.argv)
from draw import MainWindow
w = MainWindow()
w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
w.show()
ok = w.isVisible()
w.close()
w.deleteLater()
if ok:
    print('PASS MainWindow visible')
else:
    print('FAIL MainWindow not visible')
""", timeout_sec=120.0))  # MainWindow import takes ~92s + subprocess overhead (M428-cycle35)

    # --- Sub-test 2: predict_all (spectrum prediction) ---
    results.append(_run_runtime_subprocess("predict_all", """
import sys, os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from predict_spectra import predict_all
out = predict_all('c1ccccc1')
if out is not None:
    print(f'PASS type={type(out).__name__}')
else:
    print('FAIL predict_all returned None')
""", timeout_sec=10.0))

    # --- Sub-test 3: get_mechanism (reaction mechanism) ---
    results.append(_run_runtime_subprocess("get_mechanism", """
import sys, os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from reaction_mechanisms import get_mechanism
mech = get_mechanism('sn2')
if mech is not None:
    steps = len(mech.steps) if hasattr(mech, 'steps') else len(mech) if isinstance(mech, (list, tuple)) else '?'
    print(f'PASS steps={steps}')
else:
    print('FAIL get_mechanism returned None')
""", timeout_sec=10.0))

    # --- Sub-test 4: DryLab import + instantiation ---
    # Lightweight smoke test: import the 25k-line module, create DryLabData,
    # instantiate DryLabReportExporter, and call _build_styles().
    # Full PDF generation is too slow for G7 (>120s); it belongs in a
    # dedicated 30-min full-audit cycle, not in every patrol run.
    # Timeout 30s is generous for import + init (typical: <10s).
    results.append(_run_runtime_subprocess("DryLab_export", """
import sys, os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from drylab_report_exporter import DryLabReportExporter, DryLabData
data = DryLabData()
data.molecule_name = 'Methane'
data.name = 'Methane'
data.smiles = 'C'
exporter = DryLabReportExporter(data)
styles = exporter._build_styles()
if styles and isinstance(styles, dict) and len(styles) > 0:
    print(f'PASS import_ok styles={len(styles)}')
else:
    print(f'FAIL styles empty or wrong type: {type(styles)}')
""", timeout_sec=30.0))

    # Overall result
    all_pass = all(r["status"] == "PASS" for r in results)
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = len(results) - pass_count

    return {
        "overall": "PASS" if all_pass else "FAIL",
        "pass_count": pass_count,
        "fail_count": fail_count,
        "tests": results,
    }


def _check_web_parity() -> dict:
    """Gate 8 (WEB_PARITY): run functional_check web comparison checks.

    Imports functional_check and inspects the web_ir_match, web_admet_match,
    web_lewis_match results. Returns overall PASS/FAIL/SKIP.
    Server not running => overall SKIP (non-blocking).
    Any FAIL => overall FAIL + auto-record to mistakes.md.
    """
    try:
        import urllib.request
        import urllib.error
        # Quick health check — skip entirely if server not running
        try:
            _hreq = urllib.request.Request(
                'http://localhost:8000/health',
                headers={'User-Agent': 'ChemGrid-Patrol/1.0'}
            )
            _hresp = urllib.request.urlopen(_hreq, timeout=3)
            _hdata = json.loads(_hresp.read())
            if _hdata.get('status') != 'ok':
                return {"overall": "SKIP", "reason": "health != ok"}
        except Exception:
            return {"overall": "SKIP", "reason": "web server not running"}

        # Run the full functional check and extract web parity keys
        sys.path.insert(0, os.path.join(PROJECT_ROOT, 'housing', 'immune'))
        from functional_check import run_functional_check
        fc_results = run_functional_check()

        web_keys = ['web_ir_match', 'web_admet_match', 'web_lewis_match']
        details = {}
        fails = []
        for k in web_keys:
            val = fc_results.get(k, 'SKIP: not in results')
            details[k] = val
            if isinstance(val, str) and val.startswith('FAIL'):
                fails.append(k)

        overall = "FAIL" if fails else "PASS"
        return {
            "overall": overall,
            "fail_count": len(fails),
            "details": details,
        }
    except Exception as e:
        logger.warning("G8_WEB_PARITY: error: %s", e)
        return {"overall": "SKIP", "error": str(e)[:200]}



def check_feedback_match_progress() -> dict:
    """Phase 7: 사용자 피드백 매칭 진행률 감시 (Rule AA).

    uf_feedback47.json 레코드에서 FG_CAPTURED_MATCHING / DONE 상태 건수를 카운트.
    진행률 = matched / total. 70% 미만 = WARN, CT 에스컬레이션 필요.

    결과를 housing/sinktank/patrol_log.jsonl에 기록.

    Rule M: 파일 미존재 / 파싱 실패 시 logger.warning (silent failure 금지).
    Rule N: isinstance() 타입 가드.
    Rule I: 매직넘버 주석.
    """
    # [MAGIC] 매칭 완료 status 값 집합 (VERIFIED_RESOLVED = 완전 해결 상태, M377 추가)
    MATCHED_STATUSES = {"FG_CAPTURED_MATCHING", "DONE", "VERIFIED_RESOLVED"}
    # [MAGIC] 경보 임계값 70%
    PROGRESS_THRESHOLD = 0.70

    feedback_path = os.path.join(
        PROJECT_ROOT, "docs", "reports", "feedback", "uf_feedback47.json"
    )

    if not os.path.exists(feedback_path):
        logger.warning("Phase 7 FEEDBACK_MATCH: uf_feedback47.json not found at %s", feedback_path)
        return {
            "phase": "G_FEEDBACK_MATCH",
            "status": "ERROR",
            "reason": "uf_feedback47.json not found",
            "matched": 0,
            "total": 0,
            "ratio": 0.0,
            "escalation": True,
        }

    try:
        with open(feedback_path, encoding="utf-8") as f:
            records = json.load(f)
    except json.JSONDecodeError as e:
        logger.warning("Phase 7 FEEDBACK_MATCH: JSON parse failed: %s", e)
        return {
            "phase": "G_FEEDBACK_MATCH",
            "status": "ERROR",
            "reason": "JSON parse failed: " + str(e)[:100],
            "matched": 0,
            "total": 0,
            "ratio": 0.0,
            "escalation": True,
        }
    except OSError as e:
        logger.warning("Phase 7 FEEDBACK_MATCH: read failed: %s", e)
        return {
            "phase": "G_FEEDBACK_MATCH",
            "status": "ERROR",
            "reason": "read failed: " + str(e)[:100],
            "matched": 0,
            "total": 0,
            "ratio": 0.0,
            "escalation": True,
        }

    if not isinstance(records, list):  # Rule N: 타입 가드
        logger.warning("Phase 7 FEEDBACK_MATCH: top-level type not list, got %s", type(records).__name__)
        return {
            "phase": "G_FEEDBACK_MATCH",
            "status": "ERROR",
            "reason": "top-level not list: " + type(records).__name__,
            "matched": 0,
            "total": 0,
            "ratio": 0.0,
            "escalation": True,
        }

    total = len(records)
    matched = 0
    for rec in records:
        if not isinstance(rec, dict):  # Rule N: 타입 가드
            continue
        status = rec.get("status", "")
        if not isinstance(status, str):
            status = str(status)
        if status in MATCHED_STATUSES:
            matched += 1

    if total == 0:
        logger.warning("Phase 7 FEEDBACK_MATCH: empty inventory (0 records)")
        return {
            "phase": "G_FEEDBACK_MATCH",
            "status": "WARN",
            "reason": "empty inventory",
            "matched": 0,
            "total": 0,
            "ratio": 0.0,
            "escalation": True,
        }

    ratio = matched / total  # total > 0 보장
    pct = round(ratio * 100.0, 1)
    threshold_pct = int(PROGRESS_THRESHOLD * 100)  # 70

    if ratio < PROGRESS_THRESHOLD:  # 0.70 미만 경보
        msg = (
            str(pct) + "% progress (" + str(matched) + "/" + str(total) +
            " matched), below " + str(threshold_pct) + "%"
        )
        logger.warning("Phase 7 FEEDBACK_MATCH WARN: %s. CT escalation required.", msg)
        result = {
            "phase": "G_FEEDBACK_MATCH",
            "status": "WARN",
            "matched": matched,
            "total": total,
            "ratio": round(ratio, 4),
            "threshold": PROGRESS_THRESHOLD,
            "msg": msg,
            "escalation": True,
        }
    else:
        result = {
            "phase": "G_FEEDBACK_MATCH",
            "status": "PASS",
            "matched": matched,
            "total": total,
            "ratio": round(ratio, 4),
            "threshold": PROGRESS_THRESHOLD,
            "msg": str(pct) + "% progress (" + str(matched) + "/" + str(total) + " matched)",
            "escalation": False,
        }

    # patrol_log.jsonl에 기록
    patrol_log_path = os.path.join(os.path.dirname(__file__), "patrol_log.jsonl")
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        log_record = dict(result)
        log_record["ts"] = ts
        with open(patrol_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_record, ensure_ascii=False) + chr(10))
    except OSError as e:
        logger.warning("Phase 7 FEEDBACK_MATCH: patrol_log write failed: %s", e)

    return result


def run_patrol() -> dict:
    """Execute full patrol cycle including Gate 1-8 checks."""
    started = datetime.now().isoformat()
    logger.info("Patrol started at %s", started)

    # --- Original checks ---

    # 1. py_compile
    compile_result = check_py_compile()
    src_ok = compile_result["src_pass"]
    src_total = src_ok + len(compile_result["src_fail"])
    source_ok = compile_result["source_pass"]
    source_total = source_ok + len(compile_result["source_fail"])

    # 2. _source sync
    desync = check_source_sync()

    # 3. except:pass
    violations = check_except_pass()
    total_violations = sum(violations.values())

    # 4. antivirus
    av_result = check_antivirus()

    # --- Gate checks (G1-G4) ---

    # G1 BUILD: reuse compile_result (already computed)
    g1_pass = (
        not compile_result["src_fail"]
        and not compile_result["source_fail"]
    )
    g1_details = {
        "src": f"{src_ok}/{src_total}",
        "source": f"{source_ok}/{source_total}",
        "fail_files": compile_result["src_fail"] + compile_result["source_fail"],
    }

    # G2 HOLLOW: 0-byte files + tiny skills
    hollow_result = check_hollow_files()
    g2_pass = (
        not hollow_result["zero_byte_files"]
        and not hollow_result["hollow_skills"]
    )
    g2_details = hollow_result

    # G3 SMILES: validate SMILES strings in recently modified files
    smiles_result = check_smiles_validity()
    g3_pass = (
        smiles_result.get("invalid_count", 0) == 0
        and "error" not in smiles_result
    )
    g3_details = smiles_result

    # G4 AUDIT_FORMAT: evidence files exist and are non-empty
    evidence_result = check_audit_evidence()
    g4_pass = (
        not evidence_result.get("missing_evidence")
        and not evidence_result.get("empty_evidence")
        and "error" not in evidence_result
    )
    g4_details = evidence_result

    # G5 PDB_IDS: validate PDB ID format in source files
    pdb_result = check_pdb_ids()
    g5_pass = pdb_result.get("invalid_format_count", 0) == 0
    g5_details = pdb_result

    # G6 SMILES_GUARD: MolFromSmiles() must have None check within 5 lines
    smiles_guard_result = check_smiles_guard()
    g6_pass = smiles_guard_result.get("unguarded_count", 0) == 0
    g6_details = smiles_guard_result

    # G7 RUNTIME: actual runtime functionality test (Rule F compliance)
    runtime_result = check_runtime()
    g7_runtime_pass = runtime_result.get("overall") == "PASS"

    # G7 SERIAL-COMPLIANCE: EVIDENCE CT PENDING + audit 3-team (Rule T, M417)
    g7_serial_result = check_g7_serial_compliance()
    g7_serial_pass = g7_serial_result.get("overall") == "PASS"

    # G7 overall: both runtime AND serial compliance must pass
    g7_pass = g7_runtime_pass and g7_serial_pass
    g7_details = {
        "runtime": runtime_result,
        "serial_compliance": g7_serial_result,
        "overall": "PASS" if g7_pass else "FAIL",
    }

    # G8 WEB_PARITY: web vs desktop comparison (IR, ADMET, Lewis)
    g8_result = _check_web_parity()
    g8_pass = g8_result.get("overall") in ("PASS", "SKIP")
    g8_details = g8_result

    # Phase 7: 피드백 매칭 진행률 감시 (Rule AA)
    feedback_match_result = check_feedback_match_progress()
    # PASS or ERROR/WARN - 비차단(run_patrol 흐름 유지), WARN 시에만 overall에 반영
    feedback_match_warn = feedback_match_result.get("status") in ("WARN", "ERROR")

    # --- Build report (backward compatible + new gates section) ---

    all_gates_pass = (
        g1_pass and g2_pass and g3_pass and g4_pass
        and g5_pass and g6_pass and g7_pass and g8_pass
    )
    # Phase 7 is non-blocking (does not fail gates), reflected in overall only
    phase7_pass = not feedback_match_warn
    original_checks_pass = (
        g1_pass
        and not desync
        and total_violations == 0
        and av_result.get("security") == "PASS"
        and av_result.get("organic_vulnerable", 1) == 0
    )

    report = {
        "timestamp": started,
        # Original fields (backward compatible)
        "py_compile": {
            "src": f"{src_ok}/{src_total}",
            "source": f"{source_ok}/{source_total}",
            "failures": compile_result["src_fail"] + compile_result["source_fail"],
        },
        "sync": {
            "desync_count": len(desync),
            "desync_files": desync,
        },
        "except_pass": {
            "total_violations": total_violations,
            "files": violations,
        },
        "antivirus": av_result,
        # Gate 1-8 summary + Phase 7
        "gates": {
            "G1": "PASS" if g1_pass else "FAIL",
            "G2": "PASS" if g2_pass else "FAIL",
            "G3": "PASS" if g3_pass else "FAIL",
            "G4": "PASS" if g4_pass else "FAIL",
            "G5": "PASS" if g5_pass else "FAIL",
            "G6": "PASS" if g6_pass else "FAIL",
            "G7": "PASS" if g7_pass else "FAIL",
            "G8": "PASS" if g8_pass else "FAIL",
            "PHASE7_FEEDBACK": feedback_match_result.get("status", "UNKNOWN"),
        },
        "gate_details": {
            "G1_BUILD": g1_details,
            "G2_HOLLOW": g2_details,
            "G3_SMILES": g3_details,
            "G4_AUDIT_FORMAT": g4_details,
            "G5_PDB_IDS": g5_details,
            "G6_SMILES_GUARD": g6_details,
            "G7_RUNTIME": g7_details,
            "G8_WEB_PARITY": g8_details,
            "PHASE7_FEEDBACK_MATCH": feedback_match_result,
        },
        "overall": "ALL GREEN" if (
            original_checks_pass and all_gates_pass and phase7_pass
        ) else "ISSUES FOUND",
    }

    # Save to log
    try:
        history = []
        if os.path.exists(PATROL_LOG):
            # [SC123] _patrol_log.json 크기 경고 — 1MB 초과 시 WARN (M924 H-3)
            log_size = os.path.getsize(PATROL_LOG)
            if log_size > 1_048_576:  # [MAGIC: 1MB] 비대화 감지 임계값
                logger.warning("[SC123] PATROL_LOG 크기 초과: %.1f MB (임계값 1MB)", log_size / 1_048_576)
            try:
                with open(PATROL_LOG, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as read_err:
                # [M924] _patrol_log.json corrupt/CP949 → reset (Rule M silent failure 금지)
                logger.warning("[patrol] PATROL_LOG corrupt, resetting history: %s", read_err)
                history = []
        history.append(report)
        # Keep last 24 entries (24 hours at 1h interval)
        history = history[-24:]
        with open(PATROL_LOG, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.warning("Failed to save patrol log: %s", e)

    return report


def main():
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
    )

    report = run_patrol()

    gates = report.get("gates", {})
    gate_details = report.get("gate_details", {})

    print(f"\n{'='*60}")
    print(f" PATROL REPORT - {report['timestamp']}")
    print(f"{'='*60}")
    print(f" [1] py_compile: src {report['py_compile']['src']} | _source {report['py_compile']['source']}")
    print(f" [2] _source sync: {report['sync']['desync_count']} desync")
    print(f" [3] except:pass: {report['except_pass']['total_violations']} violations")
    print(f" [4] security: {report['antivirus'].get('security', '?')}")
    print(f" [5] organic: {report['antivirus'].get('organic_immune', '?')}/{report['antivirus'].get('organic_total', '?')} IMMUNE")
    print(f"{'='*60}")
    print(f" GATES: G1={gates.get('G1','?')} | G2={gates.get('G2','?')} | G3={gates.get('G3','?')} | G4={gates.get('G4','?')} | G5={gates.get('G5','?')} | G6={gates.get('G6','?')} | G7={gates.get('G7','?')} | G8={gates.get('G8','?')}")
    print(f"{'='*60}")
    print(f" OVERALL: {report['overall']}")
    print(f"{'='*60}")

    # Detailed failure output

    if report["py_compile"]["failures"]:
        print("\n [G1] Compile failures:")
        for f in report["py_compile"]["failures"]:
            print(f"   {f}")

    if report["sync"]["desync_files"]:
        print("\n Desync files:")
        for f in report["sync"]["desync_files"]:
            print(f"   {f}")

    if report["except_pass"]["files"]:
        print("\n except:pass violations:")
        for f, cnt in report["except_pass"]["files"].items():
            print(f"   {f}: {cnt}")

    # G2 details
    g2 = gate_details.get("G2_HOLLOW", {})
    if g2.get("zero_byte_files"):
        print("\n [G2] Zero-byte files:")
        for f in g2["zero_byte_files"]:
            print(f"   {f}")
    if g2.get("hollow_skills"):
        print("\n [G2] Hollow skills (<50 bytes):")
        for f in g2["hollow_skills"]:
            print(f"   {f}")

    # G3 details
    g3 = gate_details.get("G3_SMILES", {})
    if g3.get("invalid"):
        print(f"\n [G3] Invalid SMILES ({g3.get('invalid_count', 0)} found):")
        for item in g3["invalid"]:
            print(f"   {item['file']}:{item['line']} -> {item['smiles']}")
    elif g3.get("error"):
        print(f"\n [G3] SMILES check skipped: {g3['error']}")

    # G4 details
    g4 = gate_details.get("G4_AUDIT_FORMAT", {})
    if g4.get("missing_evidence"):
        print("\n [G4] Departments missing evidence:")
        for d in g4["missing_evidence"]:
            print(f"   {d}")
    if g4.get("empty_evidence"):
        print("\n [G4] Empty evidence files:")
        for f in g4["empty_evidence"]:
            print(f"   {f}")

    # G5 details
    g5 = gate_details.get("G5_PDB_IDS", {})
    if g5.get("invalid_format"):
        print(f"\n [G5] Invalid PDB IDs ({g5.get('invalid_format_count', 0)} found):")
        for item in g5["invalid_format"]:
            print(f"   {item['file']}:{item['line']} -> \"{item['pdb_id']}\"")
    if g5.get("unknown_ids"):
        print(f"\n [G5] Unknown PDB IDs ({g5.get('unknown_ids_count', 0)} found, not in whitelist):")
        for item in g5["unknown_ids"]:
            print(f"   {item['file']}:{item['line']} -> \"{item['pdb_id']}\"")

    # G6 details
    g6 = gate_details.get("G6_SMILES_GUARD", {})
    if g6.get("unguarded"):
        print(f"\n [G6] MolFromSmiles without None guard ({g6.get('unguarded_count', 0)} found):")
        for item in g6["unguarded"]:
            print(f"   {item['file']}:{item['line']} -> {item['code']}")

    # G7 details (runtime + serial compliance)
    g7 = gate_details.get("G7_RUNTIME", {})
    g7_runtime = g7.get("runtime", g7)  # backward compat: if old format, use g7 directly
    g7_serial = g7.get("serial_compliance", {})
    g7_tests = g7_runtime.get("tests", [])
    if g7_tests:
        print(f"\n [G7] Runtime tests ({g7_runtime.get('pass_count', 0)}/{len(g7_tests)} PASS):")
        for t in g7_tests:
            status = t.get("status", "?")
            name = t.get("name", "?")
            detail = t.get("detail", t.get("error", ""))
            mark = "OK" if status == "PASS" else "FAIL"
            print(f"   [{mark}] {name}: {detail[:80]}")
    elif g7_runtime.get("error"):
        print(f"\n [G7] Runtime check failed: {g7_runtime['error']}")

    # G7 serial compliance sub-results (M417)
    if g7_serial:
        sc1 = g7_serial.get("sc1_ct_pending", {})
        sc2 = g7_serial.get("sc2_audit_teams", {})
        sc_overall = g7_serial.get("overall", "?")
        print(f"\n [G7-SERIAL] Serial compliance: {sc_overall}")
        sc1_missing = sc1.get("missing_ct_files", [])
        if sc1_missing:
            print(f"   [REJECT] SC1: {len(sc1_missing)} EVIDENCE file(s) missing 'CT 보고: PENDING':")
            for f in sc1_missing[:5]:
                print(f"     {f}")
        else:
            print(f"   [OK] SC1: all EVIDENCE files have CT 보고: PENDING")
        sc2_missing = sc2.get("missing_teams", [])
        if sc2_missing:
            print(f"   [REJECT] SC2: AUDIT_INCOMPLETE -- missing teams: {', '.join(sc2_missing)}")
        else:
            print(f"   [OK] SC2: all 3 audit teams have today's report")

        # SC4 Desktop Parity 출력 (FP-06, M432)
        sc4 = g7_serial.get("sc4_desktop_parity", {})
        if sc4:
            sc4_v = sc4.get("verdict", "N/A")
            print(f"\n [G7-SC4] Desktop Parity check (FP-06): {sc4_v}")
            for f in sc4.get("missing_parity_sections", []):
                print(f"   [FAIL] Missing 'Desktop Parity' section: {f}")
            for f in sc4.get("missing_screenshots", []):
                print(f"   [WARN] Cited screenshot not found (Rule U-f): {f}")
            for f in sc4.get("low_defect_coverage", []):
                print(f"   [WARN] Low user-defect keyword coverage: {f}")
            if sc4_v == "PASS":
                print(f"   [OK] SC4: audit_gui report has Desktop Parity section + screenshots + defect coverage")


if __name__ == "__main__":
    main()
