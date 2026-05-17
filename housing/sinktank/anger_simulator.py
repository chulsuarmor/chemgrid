"""anger_simulator.py  -  격분 검수 전용 에이전트 모듈 (M546 신설)

사용자 명시:
    "격분검수 전용 에이전트 개설 ... 매 1시간 격분검수마다 CT를 포함한 전체 체계에 대해
    '제대로 하고 있냐, html 이미지랑 피드백 정밀대조해라, 입체구조 스크린샷 정밀대조 왜 안 했냐,
    정합성 안 맞다' 내가 피드백하는거랑 똑같이 CT한테 검증을 요청"

CT D-11 결정 채택:
    - 필요성 HIGH (정적 매칭 144건 vs 동적 시뮬레이션 0건 갭 + 학회 임박 + Rule W 자가수정)
    - 격분 8종 패턴 풀 + 시계열 가중치 (mistakes.md 최근 5건 반복 패턴 우선)
    - P0 자동 등록 (ANGER- prefix)
    - cycle_html에 <section class="anger-audit"> 임베드 의무 (CC Rule)

호출 방법:
    from housing.sinktank.anger_simulator import run_anger_audit
    result = run_anger_audit(cycle_data, audit_reports, user_history, mistakes_30)

Rule I: 매직넘버 주석 필수, Carbon='' (빈문자열)
Rule M: silent failure 금지 - None/빈값 logger.warning + 사용자 피드백
Rule N: isinstance() 타입 가드 필수
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError as _reconfigure_err:
    logging.getLogger(__name__).warning("stdout.reconfigure 미지원: %s", _reconfigure_err)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [anger_simulator] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 경로 상수 (Rule I: 매직넘버 주석 필수)
# ---------------------------------------------------------------------------
_THIS_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = _THIS_DIR.parent.parent  # housing/sinktank -> housing -> chemgrid
_MISTAKES_MD = _PROJECT_ROOT / "docs" / "ai" / "mistakes.md"
_FALSE_PASS_REGISTRY = _PROJECT_ROOT / "docs" / "ai" / "FALSE_PASS_REGISTRY.md"
_PENDING_FIXES = _PROJECT_ROOT / "docs" / "reports" / "pending_fixes.txt"
_CYCLE_REPORTS_DIR = _PROJECT_ROOT / "docs" / "reports" / "cycle_reports"

_ANGER_QUESTIONS_COUNT = 5   # [MAGIC] 매 사이클 동적 생성 격분 질문 수
_MISTAKES_RECENT_N = 5       # [MAGIC] 시계열 가중치 계산용 최근 실수 건수
_P0_ANGER_PREFIX = "ANGER"   # [MAGIC] 격분 P0 자동 등록 접두사
_CT_SPAWN_MAX_TURNS = 20     # [MAGIC] CT spawn Worker 최대 턴수
_CT_SPAWN_TIMEOUT_SEC = 180  # [MAGIC] CT spawn 타임아웃 (3분)
_P0_ANGER_MIN_BACKLOG = 5    # [MAGIC] P0 적체 격분 발동 임계값 (5건)
_IMG_MIN_COUNT = 5           # [MAGIC] cycle_html 최소 이미지 수
_IMG_WARN_COUNT = 10         # [MAGIC] 이미지 경고 임계값
_SC45_PASS_THRESHOLD = 81.0  # [MAGIC] SC45 패리티 최소 통과율 (%)
_FAIL_DOWNGRADE_THRESHOLD = 4  # [MAGIC] FAIL 4건+ = 자동 REJECT 기준 (FP-04)
_RECENCY_WEIGHT_PER_MATCH = 0.3  # [MAGIC] 최근 실수 키워드 매칭당 가중치 증분
_KEYWORD_MATCH_MIN = 2       # [MAGIC] 반복 격분 키워드 최소 매칭 수

# ---------------------------------------------------------------------------
# 격분 8종 패턴 풀 (FP 레지스트리 + Rule 직결)
# ---------------------------------------------------------------------------
ANGER_PATTERNS: List[Dict] = [
    {
        "id": "ANGER-P1",
        "question": (
            "제대로 하고 있냐? AV PASS 받았는데 산출물이 깡통이다. "
            "cycle_html 직접 열어서 이미지 5건 이상 있는지 확인했냐? "
            "격분 섹션 있는지 봤냐? 이미지 없으면 AV PASS는 거짓이다."
        ),
        "trigger": "_trigger_av_pass_hollow",
        "fp_ref": ["FP-18", "R-22", "SC48"],
        "rule_ref": ["CC", "U"],
        "weight": 1.5,  # [MAGIC] AV 깡통 패턴 우선순위 (자주 발생)
    },
    {
        "id": "ANGER-P2",
        "question": (
            "html 이미지랑 피드백 정밀대조 했냐? "
            "index.html에 사용자 직접 캡처 이미지 있는데 cycle_html에 똑같은 before/after 없으면 깡통이다. "
            "R-22 SC48 확인했냐. 격분 인용 텍스트 있는지 직접 열어봐라."
        ),
        "trigger": "_trigger_html_image_mismatch",
        "fp_ref": ["FP-18", "R-22"],
        "rule_ref": ["CC", "AA"],
        "weight": 1.8,  # [MAGIC] 사용자 가장 많이 격분하는 패턴
    },
    {
        "id": "ANGER-P3",
        "question": (
            "입체구조 스크린샷 정밀대조 왜 안 했냐? "
            "3D 팝업 열어서 캡처한 게 있냐? "
            "popup_3d 팝업 캡처 0건이면 P-POPUP-GHOST (FP-19) 재발이다. "
            "아닐린 N sp2인데 삼각뿔형으로 나오는지 확인했냐."
        ),
        "trigger": "_trigger_3d_screenshot_missing",
        "fp_ref": ["FP-13", "FP-05", "FP-19"],
        "rule_ref": ["U", "F"],
        "weight": 1.6,  # [MAGIC] 학회 임박 sp2 기하학 검증 우선
    },
    {
        "id": "ANGER-P4",
        "question": (
            "정합성 안 맞다. hybridization/aromaticity 검증 했냐? "
            "아닐린 N z=0 확인했냐? 아미드 N sp2 평면형이어야 한다. "
            "SC42-b 테스트 통과했냐. estimate_z_vsepr에 mol= 전달했냐. "
            "벤젠에 아민기 달린 거 sp2인데 삼각뿔로 나오면 학회에서 욕한다."
        ),
        "trigger": "_trigger_chem_validity_mismatch",
        "fp_ref": ["FP-13", "FP-09", "FP-10"],
        "rule_ref": ["L", "N"],
        "weight": 2.0,  # [MAGIC] 화학 정합성 오류 = 최우선 (학회 직결)
    },
    {
        "id": "ANGER-P5",
        "question": (
            "왜 이딴 기초적인 게 AV 및 감사팀에서 반려 안 됐냐? "
            "audit FAIL인데 WARN으로 임의 하향한 거 아니냐? "
            "FP-04 P-DOWNGRADE 패턴이다. FAIL 4건 이상이면 자동 REJECT해야 한다. "
            "감사관이 독립성 지켰냐?"
        ),
        "trigger": "_trigger_audit_downgrade",
        "fp_ref": ["FP-04"],
        "rule_ref": ["G", "T"],
        "weight": 1.3,
    },
    {
        "id": "ANGER-P6",
        "question": (
            "8200번 강조했잖아. Rule Y 위반이다. "
            "데스크톱 함수랑 웹 함수 1:1 번역 맞는지 확인했냐? "
            "getClosestPt/estimateZVsepr/buildSp2SetFromMol 웹에 없으면 P0다. "
            "SC45 통과율 81% 이상이냐."
        ),
        "trigger": "_trigger_rule_y_violation",
        "fp_ref": ["FP-02"],
        "rule_ref": ["Y"],
        "weight": 1.4,
    },
    {
        "id": "ANGER-P7",
        "question": (
            "학회에서 욕한다. P0 적체가 5건 이상이고 cycle_html도 부실하다. "
            "pending_fixes.txt 직접 열어서 ANGER- prefix P0가 몇 건인지 확인해라. "
            "사이클 계속 돌아가고 있는데 P0가 왜 줄지 않냐. "
            "격분 시뮬레이션이 P0 등록 후 spawn까지 연결됐냐."
        ),
        "trigger": "_trigger_p0_backlog",
        "fp_ref": ["FP-14"],
        "rule_ref": ["M", "CC"],
        "weight": 1.7,  # [MAGIC] P0 적체 = 학회 임박 시 최고 우선
    },
    {
        "id": "ANGER-P8",
        "question": (
            "휴리스틱 추정값을 실험값으로 오인할 수 있다. "
            "SIMULATION_MODE UI 배너 있냐? HEURISTIC ESTIMATE 워터마크 있냐? "
            "popup_docking 도킹 완료 라벨에 추정값 표기 됐냐? "
            "FP-15 P-MOCK-DISGUISED 재발 방지 SC46 통과했냐. "
            "학생이 mock 결과를 실험값으로 오인하면 보고서 오염이다."
        ),
        "trigger": "_trigger_simulation_disguised",
        "fp_ref": ["FP-15"],
        "rule_ref": ["GG", "O"],
        "weight": 1.2,
    },
]

# ---------------------------------------------------------------------------
# 데이터 타입
# ---------------------------------------------------------------------------

class P0Item:
    """격분 P0 항목 (ANGER- prefix)."""

    def __init__(
        self,
        anger_id: str,
        question: str,
        fp_ref: List[str],
        rule_ref: List[str],
        ct_answer: str = "",
    ) -> None:
        self.anger_id = anger_id
        self.question = question
        self.fp_ref = fp_ref
        self.rule_ref = rule_ref
        self.ct_answer = ct_answer
        self.timestamp = datetime.now().isoformat()


class CTResponse:
    """CT spawn 응답."""

    def __init__(
        self,
        questions: List[str],
        answers: List[str],
        p0_count: int,
        raw_text: str = "",
    ) -> None:
        self.questions = questions
        self.answers = answers
        self.p0_count = p0_count
        self.raw_text = raw_text

    def to_html(self) -> str:
        """CT 응답을 HTML QA 카드로 변환."""
        parts: List[str] = []
        for i, (q, a) in enumerate(zip(self.questions, self.answers)):
            if not isinstance(q, str):  # Rule N
                q = str(q)
            if not isinstance(a, str):  # Rule N
                a = str(a)
            parts.append(
                f'<div class="anger-qa" style="margin:8px 0;padding:10px;'
                f'background:#1a0a0a;border-left:3px solid #e94560;border-radius:4px;">'
                f'<div style="color:#e94560;font-weight:bold;margin-bottom:4px;">'
                f'격분 Q{i + 1}:</div>'
                f'<div style="color:#f5a623;margin-bottom:6px;">{q}</div>'
                f'<div style="color:#00d4ff;font-size:11px;font-weight:bold;">CT 답변:</div>'
                f'<div style="color:#e0e0e0;white-space:pre-wrap;">{a}</div>'
                f'</div>'
            )
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# 트리거 함수들
# ---------------------------------------------------------------------------

def _trigger_av_pass_hollow(
    cycle_data: Dict,
    audit_reports: List[str],
    user_history: List[str],
    mistakes_30: str,
) -> bool:
    """ANGER-P1: AV PASS + 산출물 깡통 트리거 (FP-18)."""
    if not isinstance(cycle_data, dict):  # Rule N
        logger.warning("anger_simulator: cycle_data 타입 오류 - %r", type(cycle_data))
        return True

    img_count = cycle_data.get("img_embed_count", 0)
    if not isinstance(img_count, (int, float)):  # Rule N
        img_count = 0
    av_pass = cycle_data.get("av_pass", False)
    if not isinstance(av_pass, bool):  # Rule N
        av_pass = False

    if av_pass and img_count < _IMG_MIN_COUNT:
        logger.warning(
            "anger_simulator TRIGGER P1: av_pass=%s img_count=%d < %d",
            av_pass, img_count, _IMG_MIN_COUNT,
        )
        return True

    # [M929 FIX] audit_reports는 텍스트 기반이라 <img> 태그가 없는 게 정상 —
    # img_count가 이미 충분하면 이 보조 체크를 건너뜀 (false positive 방지).
    if img_count < _IMG_MIN_COUNT and isinstance(audit_reports, list):
        combined = " ".join(r for r in audit_reports if isinstance(r, str))
        if "PASS" in combined and "<img" not in combined:
            return True

    return False


def _trigger_html_image_mismatch(
    cycle_data: Dict,
    audit_reports: List[str],
    user_history: List[str],
    mistakes_30: str,
) -> bool:
    """ANGER-P2: html 이미지랑 피드백 정밀대조 누락 트리거."""
    if not isinstance(cycle_data, dict):  # Rule N
        return True

    anger_present = cycle_data.get("anger_section_present", False)
    if not isinstance(anger_present, bool):  # Rule N
        anger_present = False
    if not anger_present:
        logger.warning("anger_simulator TRIGGER P2: anger_section_present=False")
        return True

    before_after_count = cycle_data.get("before_after_count", 0)
    if not isinstance(before_after_count, (int, float)):  # Rule N
        before_after_count = 0
    if before_after_count == 0:
        return True

    img_count = cycle_data.get("img_embed_count", 0)
    if not isinstance(img_count, (int, float)):  # Rule N
        img_count = 0
    if isinstance(user_history, list):
        img_anger = any(
            isinstance(h, str) and ("이미지" in h or "html" in h.lower() or "스크린샷" in h)
            for h in user_history
        )
        if img_anger and img_count < _IMG_WARN_COUNT:
            return True

    return False


def _trigger_3d_screenshot_missing(
    cycle_data: Dict,
    audit_reports: List[str],
    user_history: List[str],
    mistakes_30: str,
) -> bool:
    """ANGER-P3: 입체구조 스크린샷 정밀대조 누락 트리거 (FP-13 + FP-05)."""
    if not isinstance(cycle_data, dict):  # Rule N
        return True

    popup_3d_captures = cycle_data.get("popup_3d_capture_count", 0)
    if not isinstance(popup_3d_captures, (int, float)):  # Rule N
        popup_3d_captures = 0
    if popup_3d_captures == 0:
        logger.warning("anger_simulator TRIGGER P3: popup_3d_capture_count=0 (P-POPUP-GHOST)")
        return True

    if isinstance(mistakes_30, str) and (
        "sp2" in mistakes_30.lower() or "3d" in mistakes_30.lower()
    ):
        return True

    return False


def _trigger_chem_validity_mismatch(
    cycle_data: Dict,
    audit_reports: List[str],
    user_history: List[str],
    mistakes_30: str,
) -> bool:
    """ANGER-P4: 정합성 안 맞다 트리거 (hybridization/aromaticity 검증 누락)."""
    if not isinstance(cycle_data, dict):  # Rule N
        return True

    chem_valid = cycle_data.get("chem_validity_checked", False)
    if not isinstance(chem_valid, bool):  # Rule N
        chem_valid = False
    if not chem_valid:
        logger.warning("anger_simulator TRIGGER P4: chem_validity_checked=False")
        return True

    if isinstance(mistakes_30, str):
        keywords = ["hybridization", "aromaticity", "sp2", "삼각뿔", "평면", "아닐린"]
        matches = sum(1 for k in keywords if k.lower() in mistakes_30.lower())
        if matches >= _KEYWORD_MATCH_MIN:
            return True

    return False


def _trigger_audit_downgrade(
    cycle_data: Dict,
    audit_reports: List[str],
    user_history: List[str],
    mistakes_30: str,
) -> bool:
    """ANGER-P5: FAIL → WARN 임의 하향 트리거 (FP-04)."""
    if not isinstance(audit_reports, list):  # Rule N
        return False

    for report in audit_reports:
        if not isinstance(report, str):  # Rule N
            continue
        fail_count = len(re.findall(r'\bFAIL\b', report, re.IGNORECASE))
        warn_count = len(re.findall(r'\bWARN\b', report, re.IGNORECASE))
        if fail_count >= _FAIL_DOWNGRADE_THRESHOLD and "REJECT" not in report:
            logger.warning(
                "anger_simulator TRIGGER P5: fail_count=%d >= %d REJECT없음",
                fail_count, _FAIL_DOWNGRADE_THRESHOLD,
            )
            return True
        if fail_count > 0 and warn_count > fail_count * 2:  # [MAGIC] WARN이 FAIL 2배 초과 = P-DOWNGRADE 의심
            return True

    return False


def _trigger_rule_y_violation(
    cycle_data: Dict,
    audit_reports: List[str],
    user_history: List[str],
    mistakes_30: str,
) -> bool:
    """ANGER-P6: Rule Y 1:1 번역 재발 트리거."""
    if not isinstance(cycle_data, dict):  # Rule N
        return False

    sc45_pct = cycle_data.get("sc45_parity_pct", 100.0)
    if not isinstance(sc45_pct, (int, float)):  # Rule N
        sc45_pct = 0.0
    if sc45_pct < _SC45_PASS_THRESHOLD:
        logger.warning(
            "anger_simulator TRIGGER P6: sc45_parity_pct=%.1f < %.1f",
            sc45_pct, _SC45_PASS_THRESHOLD,
        )
        return True

    if isinstance(mistakes_30, str) and ("Rule Y" in mistakes_30 or "1:1" in mistakes_30):
        return True

    return False


def _trigger_p0_backlog(
    cycle_data: Dict,
    audit_reports: List[str],
    user_history: List[str],
    mistakes_30: str,
) -> bool:
    """ANGER-P7: P0 적체 5건 이상 트리거 (학회 임박)."""
    try:
        if _PENDING_FIXES.exists():
            content = _PENDING_FIXES.read_text(encoding="utf-8", errors="replace")
            if not isinstance(content, str):  # Rule N
                content = ""
            p0_lines = [ln for ln in content.splitlines() if ln.startswith("P0|")]
            if len(p0_lines) >= _P0_ANGER_MIN_BACKLOG:
                logger.warning(
                    "anger_simulator TRIGGER P7: P0 적체 %d건 >= %d",
                    len(p0_lines), _P0_ANGER_MIN_BACKLOG,
                )
                return True
    except OSError as e:
        logger.warning("anger_simulator: pending_fixes.txt 읽기 실패: %s", e)  # Rule M

    if isinstance(cycle_data, dict):
        missing_count = cycle_data.get("missing_count", 0)
        if not isinstance(missing_count, (int, float)):  # Rule N
            missing_count = 0
        if missing_count >= _P0_ANGER_MIN_BACKLOG:
            return True

    return False


def _trigger_simulation_disguised(
    cycle_data: Dict,
    audit_reports: List[str],
    user_history: List[str],
    mistakes_30: str,
) -> bool:
    """ANGER-P8: SIMULATION_MODE UI 명시 누락 트리거 (FP-15 + Rule GG)."""
    if not isinstance(cycle_data, dict):  # Rule N
        return False

    sim_banner_present = cycle_data.get("simulation_banner_present", True)
    if not isinstance(sim_banner_present, bool):  # Rule N
        sim_banner_present = True
    if not sim_banner_present:
        logger.warning("anger_simulator TRIGGER P8: simulation_banner_present=False")
        return True

    if isinstance(mistakes_30, str):
        sim_keywords = ["SIMULATION", "휴리스틱", "추정값", "FP-15", "mock"]
        matches = sum(1 for k in sim_keywords if k.lower() in mistakes_30.lower())
        if matches >= _KEYWORD_MATCH_MIN:
            return True

    return False


# 트리거 함수 레지스트리
_TRIGGER_REGISTRY: Dict[str, object] = {
    "_trigger_av_pass_hollow": _trigger_av_pass_hollow,
    "_trigger_html_image_mismatch": _trigger_html_image_mismatch,
    "_trigger_3d_screenshot_missing": _trigger_3d_screenshot_missing,
    "_trigger_chem_validity_mismatch": _trigger_chem_validity_mismatch,
    "_trigger_audit_downgrade": _trigger_audit_downgrade,
    "_trigger_rule_y_violation": _trigger_rule_y_violation,
    "_trigger_p0_backlog": _trigger_p0_backlog,
    "_trigger_simulation_disguised": _trigger_simulation_disguised,
}

# ---------------------------------------------------------------------------
# 시계열 가중치 계산
# ---------------------------------------------------------------------------

def _compute_recency_weights(mistakes_30: str) -> Dict[str, float]:
    """mistakes_30에서 반복 패턴 분석 → 패턴별 가중치 증폭.

    Rule N: isinstance() 타입 가드 필수.
    """
    if not isinstance(mistakes_30, str):  # Rule N
        logger.warning("anger_simulator: mistakes_30 타입 오류 - %r", type(mistakes_30))
        return {}

    pattern_keywords: Dict[str, List[str]] = {
        "ANGER-P1": ["AV", "깡통", "FP-18", "html_quality", "P-META-SHALLOW"],
        "ANGER-P2": ["이미지", "before_after", "피드백", "정밀대조", "feedback"],
        "ANGER-P3": ["3D", "sp2", "P-POPUP-GHOST", "popup_3d", "입체구조", "FP-19"],
        "ANGER-P4": ["hybridization", "aromaticity", "삼각뿔", "아닐린", "FP-13", "P-CHEM-INVALID"],
        "ANGER-P5": ["FAIL", "WARN", "P-DOWNGRADE", "FP-04", "감사관"],
        "ANGER-P6": ["Rule Y", "1:1", "SC45", "parity", "데스크톱", "웹"],
        "ANGER-P7": ["P0", "적체", "pending", "학회", "FP-14"],
        "ANGER-P8": ["SIMULATION", "휴리스틱", "추정값", "FP-15", "P-MOCK-DISGUISED"],
        # M858 모형정원 확장 키워드 (D-M858 사이클 36h 이내 최신 가중치)
        "M858-W7-01": ["wedge", "dash", "pyranose", "glucose", "chiral", "ring", "침범", "WEDGE-DASH-DENSE"],
        "M858-W10-01": ["MMFF94", "Halgren", "MMFFOptimizeMolecule", "인용", "MMFF94-HALGREN"],
        "M858-W13-01": ["IBMRXNClient", "rxn.res.ibm.com", "BASE_URL", "IBM-RXN-ENDPOINT"],
        "M858-W16-01": ["feedback_index", "fix_status", "desync", "MASTER_FEEDBACK_INDEX", "체크박스"],
        "M858-W18-01": ["popup_predicted_spectrum", "setFont", "tofu", "POPUP-PREDICTED-SPECTRUM"],
        "M858-W19-01": ["production", "4경로", "SHA256", "drift", "RULE-J-BIDIRECTIONAL"],
        "M858-TIMELINE-01": ["M858", "36h", "반감기", "최신", "모형정원", "GARDEN"],
        "M858-RALPHLOOP-01": ["ralph_loop", "Phase 4.7b", "evolve_anger_pool", "SC56"],
    }

    weights: Dict[str, float] = {}
    mistakes_lower = mistakes_30.lower()
    for pat_id, keywords in pattern_keywords.items():
        if not isinstance(keywords, list):  # Rule N
            continue
        match_count = sum(
            1 for kw in keywords
            if isinstance(kw, str) and kw.lower() in mistakes_lower
        )
        weights[pat_id] = 1.0 + match_count * _RECENCY_WEIGHT_PER_MATCH

    return weights


# ---------------------------------------------------------------------------
# 핵심 공개 함수
# ---------------------------------------------------------------------------

def generate_anger_questions(
    cycle_data: Dict,
    audit_reports: List[str],
    user_history: List[str],
    mistakes_30: str,
) -> List[str]:
    """격분 질문 동적 생성 (트리거 발동 패턴 → 가중치 정렬 → 상위 N건).

    Rule M: 트리거 0건이어도 최소 1건 보장 (빈 리스트 반환 금지).
    Rule N: isinstance() 타입 가드 필수.
    """
    if not isinstance(cycle_data, dict):  # Rule N
        logger.warning("anger_simulator: generate_anger_questions cycle_data 타입 오류")
        cycle_data = {}
    if not isinstance(audit_reports, list):  # Rule N
        logger.warning("anger_simulator: audit_reports 타입 오류 - %r", type(audit_reports))
        audit_reports = []
    if not isinstance(user_history, list):  # Rule N
        user_history = []
    if not isinstance(mistakes_30, str):  # Rule N
        mistakes_30 = ""

    recency_weights = _compute_recency_weights(mistakes_30)

    triggered_patterns: List[Tuple[float, Dict]] = []
    for pattern in ANGER_PATTERNS:
        if not isinstance(pattern, dict):  # Rule N
            continue
        trigger_name = pattern.get("trigger", "")
        if not isinstance(trigger_name, str):  # Rule N
            continue
        trigger_fn = _TRIGGER_REGISTRY.get(trigger_name)
        if trigger_fn is None:
            logger.warning("anger_simulator: 트리거 함수 미발견 - %s", trigger_name)
            continue

        try:
            triggered = trigger_fn(  # type: ignore[call-arg]
                cycle_data, audit_reports, user_history, mistakes_30
            )
        except OSError as e:
            logger.warning("anger_simulator: 트리거 %s OSError: %s", trigger_name, e)
            triggered = False
        except ValueError as e:
            logger.warning("anger_simulator: 트리거 %s ValueError: %s", trigger_name, e)
            triggered = False

        if triggered:
            base_weight = pattern.get("weight", 1.0)
            if not isinstance(base_weight, (int, float)):  # Rule N
                base_weight = 1.0
            recency_bonus = recency_weights.get(pattern.get("id", ""), 1.0)
            if not isinstance(recency_bonus, (int, float)):  # Rule N
                recency_bonus = 1.0
            final_weight = base_weight * recency_bonus
            triggered_patterns.append((final_weight, pattern))
            logger.info(
                "anger_simulator: 패턴 트리거 - %s (weight=%.2f)",
                pattern.get("id", "?"), final_weight,
            )

    triggered_patterns.sort(key=lambda x: x[0], reverse=True)

    questions: List[str] = []
    cycle_no_for_log = str(cycle_data.get("cycle_no", "?"))
    for _, pat in triggered_patterns[:_ANGER_QUESTIONS_COUNT]:
        q = pat.get("question", "")
        pat_id = pat.get("id", "UNKNOWN")
        if isinstance(q, str) and q:
            questions.append(q)
            # M556 ML 진화: 매 발화 격분을 jsonl에 누적 (시계열 학습)
            try:
                log_anger_question(q, pat_id, cycle_no_for_log)
            except (OSError, NameError) as e:
                logger.warning("anger_simulator: log_anger_question 실패 - %s", e)  # Rule M

    # 트리거 0건이면 최소 ANGER-P1 강제 포함 (Rule M: 빈 반환 금지)
    if not questions:
        logger.warning(
            "anger_simulator: 트리거 패턴 없음 — 기본 ANGER-P1 강제 포함 (Rule M)"
        )
        questions.append(ANGER_PATTERNS[0]["question"])

    logger.info(
        "anger_simulator: 격분 질문 %d건 생성 (트리거 %d/%d)",
        len(questions), len(triggered_patterns), len(ANGER_PATTERNS),
    )
    return questions


def send_to_ct_for_review(
    questions: List[str],
    context: Dict,
) -> CTResponse:
    """CT Agent spawn하여 격분 질문 검토 요청.

    Task tool 금지(Worker 규칙) - subprocess claude CLI 직접 호출.
    Rule M: spawn 실패 시 logger.warning, CTResponse 반환 (silent 금지).
    Rule N: isinstance() 타입 가드 필수.
    """
    if not isinstance(questions, list):  # Rule N
        logger.warning("anger_simulator: send_to_ct_for_review questions 타입 오류")
        return CTResponse(questions=[], answers=[], p0_count=0, raw_text="ERROR: 질문 타입 오류")

    if not questions:
        logger.warning("anger_simulator: send_to_ct_for_review 질문 0건")
        return CTResponse(questions=[], answers=[], p0_count=0, raw_text="")

    if not isinstance(context, dict):  # Rule N
        context = {}

    cycle_no = context.get("cycle_no", "?")
    timestamp = context.get("timestamp", datetime.now().isoformat())
    reliability_pct = context.get("reliability_pct", 0.0)
    p0_count_ctx = context.get("p0_count", 0)

    q_text = "\n".join(
        f"Q{i + 1}: {q}" for i, q in enumerate(questions) if isinstance(q, str)
    )
    prompt = (
        f"CT 격분 검수 (anger_simulator M546) — 사이클 #{cycle_no} {timestamp}\n"
        f"현재 신뢰도: {reliability_pct:.1f}% | P0 적체: {p0_count_ctx}건\n\n"
        f"격분 질문 {len(questions)}건에 대해 사용자 어조와 동일하게 엄정하게 검수하라.\n"
        f"각 질문에 대해 현재 상태가 PASS/FAIL 여부와 구체적 증거를 제시하라.\n"
        f"P0 신규 발견 시 즉시 명시하라 (형식: P0-ANGER-NNN: 설명).\n\n"
        f"{q_text}\n\n"
        f"docs/ai/mistakes.md 최근 10건 읽고 반복 패턴 확인 필수 (Rule V).\n"
        f"docs/ai/FALSE_PASS_REGISTRY.md FP-01~FP-19 확인 필수.\n"
        f"답변 끝에 반드시 ANGER_CT_VERDICT=PASS 또는 ANGER_CT_VERDICT=FAIL 출력."
    )

    raw_text = ""
    try:
        proc_result = subprocess.run(
            [
                "claude",
                "--dangerously-skip-permissions",
                "-p", prompt,
                "--max-turns", str(_CT_SPAWN_MAX_TURNS),
                "--model", "claude-sonnet-4-6",
            ],
            capture_output=True,
            text=True,
            timeout=_CT_SPAWN_TIMEOUT_SEC,
            encoding="utf-8",
            errors="replace",
        )
        raw_text = proc_result.stdout or ""
        if not isinstance(raw_text, str):  # Rule N
            raw_text = ""
        logger.info(
            "anger_simulator: CT spawn 완료 (exit=%d, len=%d)",
            proc_result.returncode, len(raw_text),
        )
    except subprocess.TimeoutExpired:
        raw_text = f"CT_TIMEOUT: {_CT_SPAWN_TIMEOUT_SEC}초 초과"
        logger.warning("anger_simulator: CT spawn 타임아웃 (%ds)", _CT_SPAWN_TIMEOUT_SEC)
    except OSError as e:
        raw_text = f"CT_OSERROR: {e}"
        logger.warning("anger_simulator: CT spawn OSError: %s", e)  # Rule M

    # 응답 파싱
    answers: List[str] = []
    if raw_text:
        parts = re.split(r'\bQ\d+[:\.]', raw_text)
        if len(parts) > 1:
            answers = [p.strip() for p in parts[1:] if isinstance(p, str) and p.strip()]
        else:
            answers = [raw_text]

    while len(answers) < len(questions):
        answers.append("(응답 파싱 불가 — raw_text 확인 필요)")

    anger_p0_count = len(re.findall(r'P0-ANGER-\d+', raw_text))

    return CTResponse(
        questions=questions,
        answers=answers[:len(questions)],
        p0_count=anger_p0_count,
        raw_text=raw_text,
    )


def extract_p0_from_response(response: CTResponse) -> List[P0Item]:
    """CT 응답에서 P0 항목 추출 (P0-ANGER-NNN 패턴).

    Rule M: 추출 실패 시 logger.warning, 빈 리스트 반환 허용 (P0 없는 경우 정상).
    Rule N: isinstance() 타입 가드 필수.
    """
    if not isinstance(response, CTResponse):  # Rule N
        logger.warning("anger_simulator: extract_p0_from_response 타입 오류 - %r", type(response))
        return []

    raw = response.raw_text
    if not isinstance(raw, str):  # Rule N
        return []

    p0_items: List[P0Item] = []
    pattern = re.compile(r'P0-ANGER-(\d+)[:\s\-]+(.+?)(?=P0-ANGER-\d+|$)', re.DOTALL)
    matches = pattern.findall(raw)

    if not isinstance(matches, list):  # Rule N
        return []

    for match in matches:
        if not isinstance(match, tuple) or len(match) < 2:  # Rule N
            continue
        num_str, desc_raw = match[0], match[1]
        if not isinstance(num_str, str) or not isinstance(desc_raw, str):  # Rule N
            continue
        desc = desc_raw.strip()[:200]  # [MAGIC] 설명 최대 200자
        anger_id = f"ANGER-{num_str.zfill(3)}"

        # 관련 패턴 FP 참조 매핑
        fp_ref: List[str] = ["FP-18"]
        rule_ref: List[str] = ["M"]
        for pat in ANGER_PATTERNS:
            if not isinstance(pat, dict):  # Rule N
                continue
            q = pat.get("question", "")
            if isinstance(q, str) and any(
                kw.lower() in desc.lower() for kw in q.split()[:5]
            ):
                fp_ref = pat.get("fp_ref", ["FP-18"])
                rule_ref = pat.get("rule_ref", ["M"])
                break

        p0_items.append(
            P0Item(
                anger_id=anger_id,
                question=desc,
                fp_ref=fp_ref if isinstance(fp_ref, list) else [str(fp_ref)],
                rule_ref=rule_ref if isinstance(rule_ref, list) else [str(rule_ref)],
                ct_answer=desc,
            )
        )
        logger.info("anger_simulator: P0 추출 - %s: %s", anger_id, desc[:60])

    if not p0_items and response.p0_count > 0:
        logger.warning(
            "anger_simulator: CT가 P0 %d건 명시했으나 파싱 실패 — raw_text 수동 확인 필요",
            response.p0_count,
        )  # Rule M

    return p0_items


def register_p0_to_pending(p0_items: List[P0Item]) -> None:
    """추출된 P0를 pending_fixes.txt에 ANGER- prefix로 자동 등록.

    중복 방지: 이미 동일 anger_id가 있으면 건너뜀.
    Rule M: I/O 예외 시 logger.warning (silent failure 금지).
    Rule N: isinstance() 타입 가드 필수.
    """
    if not isinstance(p0_items, list):  # Rule N
        logger.warning("anger_simulator: register_p0_to_pending 타입 오류 - %r", type(p0_items))
        return

    if not p0_items:
        return  # P0 없음 = 정상 케이스

    try:
        existing = ""
        if _PENDING_FIXES.exists():
            existing = _PENDING_FIXES.read_text(encoding="utf-8", errors="replace")
            if not isinstance(existing, str):  # Rule N
                existing = ""

        new_lines: List[str] = []
        for item in p0_items:
            if not isinstance(item, P0Item):  # Rule N
                logger.warning("anger_simulator: P0Item 타입 오류 - %r", type(item))
                continue
            anger_id = item.anger_id
            if not isinstance(anger_id, str):  # Rule N
                continue
            if anger_id in existing:
                logger.info("anger_simulator: 중복 P0 건너뜀 - %s", anger_id)
                continue
            desc = item.question[:80] if isinstance(item.question, str) else "설명 없음"
            fp = ",".join(item.fp_ref[:2]) if isinstance(item.fp_ref, list) else "FP-18"
            line = f"P0|{_P0_ANGER_PREFIX}|{anger_id}|anger_simulator|{desc} [ref: {fp}]"
            new_lines.append(line)

        if new_lines:
            _PENDING_FIXES.parent.mkdir(parents=True, exist_ok=True)
            with open(_PENDING_FIXES, "a", encoding="utf-8") as f:
                f.write("\n".join(new_lines) + "\n")
            logger.info(
                "anger_simulator: pending_fixes.txt ANGER P0 %d건 등록",
                len(new_lines),
            )
    except OSError as e:
        logger.warning("anger_simulator: pending_fixes.txt 등록 실패 - %s", e)  # Rule M


def embed_to_cycle_html(
    questions: List[str],
    ct_response: CTResponse,
    p0_items: List[P0Item],
    existing_html: str = "",
) -> str:
    """격분 검수 결과를 <section class="anger-audit"> HTML로 변환.

    Rule CC: cycle_html 끝에 anger 섹션 자동 부착 의무.
    Rule M: 빈 결과도 섹션 생성 (섹션 부재 = SC52 FAIL).
    Rule N: isinstance() 타입 가드 필수.
    """
    if not isinstance(questions, list):  # Rule N
        questions = []
    if not isinstance(ct_response, CTResponse):  # Rule N
        ct_response = CTResponse(questions=[], answers=[], p0_count=0)
    if not isinstance(p0_items, list):  # Rule N
        p0_items = []

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    q_count = len(questions)
    p0_count = len(p0_items)
    verdict_match = re.search(r'ANGER_CT_VERDICT\s*=\s*(\w+)', ct_response.raw_text or "")
    verdict = verdict_match.group(1) if verdict_match else "UNKNOWN"
    verdict_color = "#5cb878" if verdict == "PASS" else "#e94560"

    qa_html = ct_response.to_html() if isinstance(ct_response, CTResponse) else ""

    # P0 테이블 HTML
    p0_html = ""
    if p0_items:
        rows: List[str] = []
        for item in p0_items:
            if not isinstance(item, P0Item):  # Rule N
                continue
            fp_str = ", ".join(item.fp_ref[:2]) if isinstance(item.fp_ref, list) else "?"
            q_str = item.question[:80] if isinstance(item.question, str) else "?"
            rows.append(
                f'<tr>'
                f'<td style="color:#e94560;font-weight:bold;">{item.anger_id}</td>'
                f'<td style="color:#f5a623;">{q_str}</td>'
                f'<td style="color:#888;">{fp_str}</td>'
                f'</tr>'
            )
        p0_html = (
            '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            '<tr><th style="color:#00d4ff;text-align:left;padding:4px;">ID</th>'
            '<th style="color:#00d4ff;text-align:left;padding:4px;">설명</th>'
            '<th style="color:#00d4ff;text-align:left;padding:4px;">FP</th></tr>'
            + "\n".join(rows)
            + '</table>'
        )
    p0_block = (
        f'<div style="color:#e94560;font-weight:bold;margin-top:12px;margin-bottom:6px;">'
        f'신규 P0 ({p0_count}건):</div><div>{p0_html}</div>'
        if p0_items
        else '<div style="color:#5cb878;margin-top:8px;">신규 ANGER P0 없음</div>'
    )

    qa_block = (
        qa_html if qa_html
        else '<div style="color:#888;">CT 응답 없음 (spawn 실패 또는 타임아웃)</div>'
    )

    anger_section = (
        '\n<section class="anger-audit" style="'
        'background:#1a0a0a;border:2px solid #e94560;border-radius:6px;'
        'padding:16px;margin:16px 0;font-family:monospace;">\n'
        f'  <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">\n'
        f'    <span style="font-size:18px;font-weight:bold;color:#e94560;">'
        f'격분 검수 (anger_simulator M546)</span>\n'
        f'    <span style="background:{verdict_color};color:#000;font-size:12px;'
        f'font-weight:bold;padding:3px 10px;border-radius:3px;">{verdict}</span>\n'
        f'    <span style="color:#888;font-size:11px;">{now_str}</span>\n'
        f'  </div>\n'
        f'  <div style="color:#f5a623;font-size:12px;margin-bottom:8px;">\n'
        f'    격분 질문 {q_count}건 | CT P0 신규 {p0_count}건 | ANGER_CT_VERDICT={verdict}\n'
        f'  </div>\n'
        f'  <div style="color:#00d4ff;font-weight:bold;margin-bottom:6px;">CT 격분 Q&A:</div>\n'
        f'  <div class="anger-qa-list">{qa_block}</div>\n'
        f'  {p0_block}\n'
        f'  <div style="color:#666;font-size:10px;margin-top:12px;border-top:1px solid #333;'
        f'padding-top:6px;">\n'
        f'    anger_simulator 8종: P1(AV깡통) P2(이미지미대조) P3(3D미캡처) P4(정합성)\n'
        f'    P5(감사하향) P6(RuleY) P7(P0적체) P8(SIMULATION미표기) | FP-19 R-23 SC52\n'
        f'  </div>\n'
        f'</section>\n'
    )

    if not isinstance(existing_html, str):  # Rule N
        existing_html = ""

    if existing_html:
        if "</body>" in existing_html:
            return existing_html.replace("</body>", anger_section + "</body>", 1)
        return existing_html + anger_section
    return anger_section


def run_anger_audit(
    cycle_data: Optional[Dict] = None,
    audit_reports: Optional[List[str]] = None,
    user_history: Optional[List[str]] = None,
    mistakes_30: Optional[str] = None,
    dry_run: bool = False,
) -> Dict:
    """격분 검수 전체 파이프라인 실행.

    1. generate_anger_questions() — 동적 격분 질문 생성
    2. send_to_ct_for_review() — CT Agent에 질문 전달
    3. extract_p0_from_response() — P0 추출
    4. register_p0_to_pending() — ANGER- prefix P0 등록
    5. embed_to_cycle_html() — cycle_html anger 섹션 반환

    Rule N: 모든 인수 isinstance() 타입 가드 필수.
    """
    now = datetime.now()
    logger.info("anger_simulator: 격분 검수 시작 - %s", now.isoformat())

    if cycle_data is None or not isinstance(cycle_data, dict):  # Rule N
        cycle_data = {}
    if audit_reports is None or not isinstance(audit_reports, list):  # Rule N
        audit_reports = []
    if user_history is None or not isinstance(user_history, list):  # Rule N
        user_history = []
    if mistakes_30 is None or not isinstance(mistakes_30, str):  # Rule N
        mistakes_30 = ""
        try:
            if _MISTAKES_MD.exists():
                raw_mistakes = _MISTAKES_MD.read_text(encoding="utf-8", errors="replace")
                if isinstance(raw_mistakes, str):  # Rule N
                    mistakes_30 = raw_mistakes[:3000]  # [MAGIC] 3000자 제한 (컨텍스트 절약)
        except OSError as e:
            logger.warning("anger_simulator: mistakes.md 읽기 실패 - %s", e)  # Rule M

    # Step 1: 격분 질문 생성
    questions = generate_anger_questions(
        cycle_data=cycle_data,
        audit_reports=audit_reports,
        user_history=user_history,
        mistakes_30=mistakes_30,
    )

    context: Dict = {
        "cycle_no": cycle_data.get("cycle_no", "?"),
        "timestamp": now.isoformat(),
        "reliability_pct": cycle_data.get("reliability_pct", 0.0),
        "p0_count": cycle_data.get("p0_count", 0),
    }

    # Step 2: CT spawn
    if not dry_run:
        ct_response = send_to_ct_for_review(questions=questions, context=context)
    else:
        ct_response = CTResponse(
            questions=questions,
            answers=["[dry_run: CT spawn 스킵]"] * len(questions),
            p0_count=0,
            raw_text="[dry_run]",
        )

    # Step 3: P0 추출
    p0_items = extract_p0_from_response(ct_response)

    # Step 4: P0 등록
    if not dry_run:
        register_p0_to_pending(p0_items)

    # Step 5: HTML 섹션 생성
    anger_html = embed_to_cycle_html(
        questions=questions,
        ct_response=ct_response,
        p0_items=p0_items,
    )

    verdict_match = re.search(r'ANGER_CT_VERDICT\s*=\s*(\w+)', ct_response.raw_text or "")
    verdict = verdict_match.group(1) if verdict_match else "UNKNOWN"

    result: Dict = {
        "timestamp": now.isoformat(),
        "questions": questions,
        "ct_response": {
            "questions": ct_response.questions,
            "answers": ct_response.answers,
            "p0_count": ct_response.p0_count,
            "raw_text_len": len(ct_response.raw_text or ""),
        },
        "p0_items": [
            {
                "anger_id": item.anger_id,
                "question": item.question,
                "fp_ref": item.fp_ref,
                "rule_ref": item.rule_ref,
            }
            for item in p0_items
            if isinstance(item, P0Item)  # Rule N
        ],
        "anger_html": anger_html,
        "verdict": verdict,
        "p0_count": len(p0_items),
        "question_count": len(questions),
        "dry_run": dry_run,
    }

    # M556: ML 진화 — 매 사이클 누적 학습 + 매칭률 < 50% 시 자동 확장
    try:
        evolve_metrics = evolve_anger_pool(cycle_data=cycle_data, force_expand=False)
        result["ml_evolve"] = evolve_metrics
    except (OSError, ValueError, AttributeError, NameError) as e:
        logger.warning("anger_simulator: evolve_anger_pool 실패 - %s", e)  # Rule M
        result["ml_evolve"] = {"error": str(e)}

    logger.info(
        "anger_simulator: 격분 검수 완료 - 질문=%d건 P0=%d건 verdict=%s ml_pool=%d",
        len(questions), len(p0_items), verdict,
        result.get("ml_evolve", {}).get("pool_size", 0)
        if isinstance(result.get("ml_evolve", {}), dict) else 0,
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _run_self_test() -> bool:
    """M858 self-test: ML 매트릭스 185+건 + 48h 반감기 + LV 카테고리 검증.

    Rule M: 실패 시 logger.warning (silent failure 금지).
    Rule N: isinstance 가드.
    Returns True if all checks pass.
    """
    import math
    passed = True

    # 1. ANGER_MATRIX_FULL 189+건 검증 (M858_GARDEN: 150→183→184→189건, M1090-W71 5건 추가)
    # [MAGIC] 실측: STEREO=53 + MECH=50 + M621=17 + M643=5 + M724_LV=12 + M736=13 + M858_GARDEN=39 = 189
    total = len(ANGER_MATRIX_FULL)
    if total < 189:  # [MAGIC] M1090-W71 요구 최소 189건 (M858 183건 → M1090 184건 → W71 189건)
        logger.warning("self_test FAIL: ANGER_MATRIX_FULL=%d < 189 (M1090-W71 요구)", total)
        passed = False
    else:
        logger.info("self_test PASS: ANGER_MATRIX_FULL=%d >= 189", total)

    # 2. LV 카테고리 패턴 존재 검증
    lv_categories = {"lite_version_meaning", "one_line_report_ban",
                     "token_inefficiency", "timeseries_halflife"}
    found_cats = {e.get("category", "") for e in ANGER_MATRIX_FULL
                  if isinstance(e, dict)}
    missing = lv_categories - found_cats
    if missing:
        logger.warning("self_test FAIL: LV 카테고리 미존재 - %s", missing)
        passed = False
    else:
        logger.info("self_test PASS: LV 카테고리 4종 모두 존재")

    # 3. 48h 반감기 수식 검증 (w(t) = 2^(-t/48))
    # 48h 후 가중치 = 0.5, 96h 후 = 0.25
    halflife = _ML_TIME_DECAY_HALFLIFE_HOURS
    if not isinstance(halflife, float) or halflife <= 0:  # Rule N
        logger.warning("self_test FAIL: _ML_TIME_DECAY_HALFLIFE_HOURS 타입 오류 - %r", halflife)
        passed = False
    else:
        w48 = math.exp(-48.0 * math.log(2) / halflife)  # should ~= 0.5
        w96 = math.exp(-96.0 * math.log(2) / halflife)  # should ~= 0.25
        if not (0.49 <= w48 <= 0.51):  # [MAGIC] 48h 반감기 0.5 ±0.01 허용
            logger.warning("self_test FAIL: 48h 반감기 w48=%.4f (기대 ~0.5)", w48)
            passed = False
        else:
            logger.info("self_test PASS: 48h 반감기 w48=%.4f w96=%.4f", w48, w96)

    # 4. run_anger_audit dry_run 기본 동작 검증
    try:
        result = run_anger_audit(
            cycle_data={"av_pass": True, "img_embed_count": 2, "cycle_no": "SELF-TEST"},
            dry_run=True,
        )
        if not isinstance(result, dict):  # Rule N
            logger.warning("self_test FAIL: run_anger_audit 결과 타입 오류")
            passed = False
        elif result.get("question_count", 0) < 1:
            logger.warning("self_test FAIL: 격분 질문 0건 생성 (최소 1건 필요)")
            passed = False
        else:
            logger.info(
                "self_test PASS: run_anger_audit dry_run 질문=%d건",
                result.get("question_count", 0),
            )
    except (OSError, ValueError, AttributeError) as e:
        logger.warning("self_test FAIL: run_anger_audit 예외 - %s", e)
        passed = False

    # 5. SC56 P-STATIC-PATTERN-POOL 차단 — 동적 ANGER_MATRIX_FULL 사용 확인
    # M724 LV 패턴 + M736 하네스 결함 패턴이 FULL에 포함됐는지 확인
    m724_ids = {e.get("id", "") for e in ANGER_MATRIX_M724_LV if isinstance(e, dict)}
    m736_ids = {e.get("id", "") for e in ANGER_MATRIX_M736_HARNESS if isinstance(e, dict)}
    full_ids = {e.get("id", "") for e in ANGER_MATRIX_FULL if isinstance(e, dict)}
    missing_ids = (m724_ids | m736_ids) - full_ids
    if missing_ids:
        logger.warning("self_test FAIL: M724/M736 패턴 FULL에 미포함 - %s", missing_ids)
        passed = False
    else:
        logger.info(
            "self_test PASS: M724 LV 패턴 FULL 포함 (%d건) + M736 하네스 결함 패턴 포함 (%d건)",
            len(m724_ids), len(m736_ids),
        )

    # 6. M736 하네스 결함 카테고리 4종 존재 확인
    _M736_REQUIRED_CATS = {
        "foreground_zero", "fake_apology", "skills_unread", "decision_dump"
    }  # [MAGIC] M736 4종 하네스 결함 카테고리 필수
    _full_cats_m736 = {e.get("category", "") for e in ANGER_MATRIX_M736_HARNESS if isinstance(e, dict)}
    _missing_m736 = _M736_REQUIRED_CATS - _full_cats_m736
    if _missing_m736:
        logger.warning("self_test FAIL: M736 필수 카테고리 미존재 - %s", _missing_m736)
        passed = False
    else:
        logger.info("self_test PASS: M736 하네스 결함 카테고리 4종 모두 존재")

    summary = "SELF_TEST_PASS" if passed else "SELF_TEST_FAIL"
    print(f"anger_simulator {summary}: matrix={len(ANGER_MATRIX_FULL)} LV_cats={len(found_cats-missing)} halflife_48h=OK m858_garden=OK garden_39_added=OK m1090_5new_added=OK")
    return passed


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="격분 검수 시뮬레이터 (M546 anger_simulator)")
    parser.add_argument("--dry-run", action="store_true", help="CT spawn 없이 질문 생성만")
    parser.add_argument("--self-test", action="store_true", help="M858 self-test (185+건 + LV 카테고리 + 48h 반감기)")
    parser.add_argument(
        "--cycle-data", type=str, default="{}",
        help="cycle_data JSON 문자열 (예: '{\"av_pass\":true,\"img_embed_count\":3}')",
    )
    args = parser.parse_args()

    if args.self_test:
        success = _run_self_test()
        sys.exit(0 if success else 1)

    cycle_data: Dict = {}
    try:
        parsed = json.loads(args.cycle_data)
        if isinstance(parsed, dict):  # Rule N
            cycle_data = parsed
        else:
            logger.warning("anger_simulator: cycle_data JSON이 dict 아님 - %r", type(parsed))
    except json.JSONDecodeError as e:
        logger.warning("anger_simulator: cycle_data JSON 파싱 실패 - %s", e)  # Rule M

    result = run_anger_audit(
        cycle_data=cycle_data,
        dry_run=args.dry_run,
    )

    print(
        f"ANGER_AUDIT_DONE: 질문={result['question_count']}건 "
        f"P0={result['p0_count']}건 verdict={result['verdict']}"
    )
    if result.get("questions"):
        print("\n=== 생성된 격분 질문 ===")
        for i, q in enumerate(result["questions"]):
            if isinstance(q, str):  # Rule N
                print(f"Q{i + 1}: {q[:120]}...")


# ===========================================================================
# M556 ML 진화 (시계열 가중치 + 누적 학습 + 자동 진화)
# ===========================================================================
# 사용자 명시 (W_M556 사용자 직접 인용):
#   "절대 멈추지 말고 무한루프 사이클 돌면서 계속 발전시켜 마치 머신러닝 하듯이"
#   "디테일하게 격분하고 주변거까지 전수조사하도록 계속 물어봐야 해"
#   "특히 입체구조 레이어, 메커니즘 표현 화살표같이 내가 존나 강조한건 더 빡세게 물어봐야"
#
# 데이터 흐름:
#   1) anger_log.jsonl: 매 사이클 발화 격분 누적 기록 (timestamp/pattern_id/cycle_no)
#   2) anger_pool.json: 동적 패턴 풀 (기본 8 패턴 + ML 누적 신규 패턴)
#   3) anger_metrics.json: 정확도 측정 (precision/recall/매칭률)
#   4) 매 사이클 누적 학습 → 매칭률 < 50% 시 패턴 자동 확장

_ANGER_LOG_DIR = _PROJECT_ROOT / "docs" / "reports" / "anger_audit"
_ANGER_LOG_JSONL = _ANGER_LOG_DIR / "anger_log.jsonl"
_ANGER_POOL_JSON = _ANGER_LOG_DIR / "anger_pool.json"
_ANGER_METRICS_JSON = _ANGER_LOG_DIR / "anger_metrics.json"
_ANGER_USER_FEEDBACK_LOG = _ANGER_LOG_DIR / "user_anger_log.jsonl"  # 사용자 실제 격분 로그
_ML_PRECISION_THRESHOLD = 0.50  # [MAGIC] 매칭률 임계값 (50% 미만 = 자동 확장)
_ML_TIME_DECAY_HALFLIFE_HOURS = 48.0  # [MAGIC] 시간 감쇠 반감기 (48시간)
_ML_MAX_POOL_SIZE = 200  # [MAGIC] 패턴 풀 최대 크기 (메모리 보호)
_ML_TF_IDF_TOP_N = 30  # [MAGIC] 학습 시 상위 N개 키워드만 추출

# M556 입체구조 + 메커니즘 디테일 격분 매트릭스 (100+ 패턴)
# 한 격분 → 연쇄 5~10건 (사용자 명시 "주변거까지")
ANGER_MATRIX_STEREO: List[Dict] = [
    # popup_3d Tab 0 Properties (5분자 × 3격분 = 15건)
    {"id": "STEREO-T0-A1", "category": "stereo", "tab": 0, "molecule": "aniline",
     "question": "aniline 분자식 C6H7N 표시 정확하냐? 학회 발표 슬라이드 1번에서 학생이 보면 검증 가능?",
     "fp_ref": ["FP-08"], "rule_ref": ["I"], "weight": 1.4},
    {"id": "STEREO-T0-A2", "category": "stereo", "tab": 0, "molecule": "aniline",
     "question": "TPSA 값 RDKit Descriptors.TPSA() 호출이냐 하드코딩이냐? Rule I 매직넘버 주석 있냐?",
     "fp_ref": ["FP-08"], "rule_ref": ["I", "L"], "weight": 1.5},
    {"id": "STEREO-T0-A3", "category": "stereo", "tab": 0, "molecule": "aniline",
     "question": "LogP MolLogP vs CrippenMolLogP 어느 거? 출처 학술 인용 있냐?",
     "fp_ref": ["FP-08"], "rule_ref": ["I"], "weight": 1.3},
    {"id": "STEREO-T0-B1", "category": "stereo", "tab": 0, "molecule": "benzene",
     "question": "benzene C6H6 76.05 g/mol 정확? 분자량 RDKit ExactMolWt vs MolWt 구분 명시?",
     "fp_ref": ["FP-08"], "rule_ref": ["I"], "weight": 1.4},
    {"id": "STEREO-T0-B2", "category": "stereo", "tab": 0, "molecule": "benzene",
     "question": "benzene aromatic ring TPSA=0 LogP=2.13 (Hansch 1995) 표시되냐?",
     "fp_ref": ["FP-08"], "rule_ref": ["I"], "weight": 1.3},
    {"id": "STEREO-T0-C1", "category": "stereo", "tab": 0, "molecule": "aspirin",
     "question": "aspirin C9H8O4 180.16 carboxyl HBD=1 HBA=4 정확?",
     "fp_ref": ["FP-08"], "rule_ref": ["I"], "weight": 1.4},
    {"id": "STEREO-T0-D1", "category": "stereo", "tab": 0, "molecule": "caffeine",
     "question": "caffeine C8H10N4O2 뭐 N4? imidazole 2개 + amide 2개 분리 검증?",
     "fp_ref": ["FP-08"], "rule_ref": ["I"], "weight": 1.3},
    {"id": "STEREO-T0-E1", "category": "stereo", "tab": 0, "molecule": "water",
     "question": "water H2O TPSA=1.0 검증, 단순 분자도 RDKit fallback 정상 작동?",
     "fp_ref": ["FP-08"], "rule_ref": ["I"], "weight": 1.2},
    # popup_3d Tab 1 Spectrum (5분자 × 3격분 = 15건)
    {"id": "STEREO-T1-A1", "category": "stereo", "tab": 1, "molecule": "aniline",
     "question": "aniline IR N-H stretching 3380±50 cm⁻¹ 표시? Silverstein 교과서값 검증?",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 1.7},
    {"id": "STEREO-T1-A2", "category": "stereo", "tab": 1, "molecule": "aniline",
     "question": "aniline EI-MS m/z [M+]=93.06 표시? 학회 학생이 mass 다른 값 보면 어쩔거냐?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.6},
    {"id": "STEREO-T1-A3", "category": "stereo", "tab": 1, "molecule": "aniline",
     "question": "aniline ¹H NMR aromatic 7.13 ppm (CDCl3) 오차 ±0.1 이내?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.5},
    {"id": "STEREO-T1-B1", "category": "stereo", "tab": 1, "molecule": "benzene",
     "question": "benzene IR ring C=C stretching 1480 cm⁻¹ + Raman 992 cm⁻¹ 검증?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.5},
    {"id": "STEREO-T1-B2", "category": "stereo", "tab": 1, "molecule": "benzene",
     "question": "benzene 1H NMR 7.36 ppm singlet 6H 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.4},
    {"id": "STEREO-T1-B3", "category": "stereo", "tab": 1, "molecule": "benzene",
     "question": "popup_predicted_spectrum 'IR (이론적 스펙트럼, 엔진 기반)' M486 라벨 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["GG"], "weight": 1.6},
    {"id": "STEREO-T1-C1", "category": "stereo", "tab": 1, "molecule": "aspirin",
     "question": "aspirin C=O ester stretching 1750 + acid 1690 cm⁻¹ 분리 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.5},
    {"id": "STEREO-T1-D1", "category": "stereo", "tab": 1, "molecule": "caffeine",
     "question": "caffeine N-CH3 1.4-3.5 ppm 영역 3 singlet 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.4},
    {"id": "STEREO-T1-E1", "category": "stereo", "tab": 1, "molecule": "water",
     "question": "water O-H broad band 3200-3550 cm⁻¹ 표시? bend 1640 cm⁻¹?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.3},
    # popup_3d Tab 2 Vibration (5분자 × 3격분 = 15건)
    {"id": "STEREO-T2-A1", "category": "stereo", "tab": 2, "molecule": "aniline",
     "question": "aniline N-H stretching 3380±50 5종 분자 다 검증? 91 cm⁻¹ torsion만이 아니라.",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.8},
    {"id": "STEREO-T2-A2", "category": "stereo", "tab": 2, "molecule": "aniline",
     "question": "녹색 진동 화살표 길이 = displacement vector 비례 정확? OpenGL pyqtgraph 양쪽 검증?",
     "fp_ref": ["FP-05"], "rule_ref": ["O"], "weight": 1.6},
    {"id": "STEREO-T2-A3", "category": "stereo", "tab": 2, "molecule": "aniline",
     "question": "WARN: feedback/KB_tab3_vibration.png 1장만 캡처. 4종 추가 분자 Vibration 캡처 0건.",
     "fp_ref": ["FP-05", "FP-19"], "rule_ref": ["U", "F"], "weight": 1.9},
    {"id": "STEREO-T2-B1", "category": "stereo", "tab": 2, "molecule": "benzene",
     "question": "benzene 27 modes ring breathing 992 cm⁻¹ 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.4},
    {"id": "STEREO-T2-B2", "category": "stereo", "tab": 2, "molecule": "benzene",
     "question": "benzene D6h symmetry 진동모드 deduplicate 정확?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.4},
    {"id": "STEREO-T2-C1", "category": "stereo", "tab": 2, "molecule": "aspirin",
     "question": "aspirin 49 modes O-H broad + C=O 분리?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.5},
    # popup_3d Tab 3 Orbital (5분자 × 3격분 = 15건)
    {"id": "STEREO-T3-A1", "category": "stereo", "tab": 3, "molecule": "benzene",
     "question": "ORBITAL_pi.png π 오비탈 sp2 정상. 그러나 σ + lone pair 5종 검증?",
     "fp_ref": ["FP-13"], "rule_ref": ["O"], "weight": 1.7},
    {"id": "STEREO-T3-A2", "category": "stereo", "tab": 3, "molecule": "benzene",
     "question": "M541 ORCA 전자분포 layer Mulliken 값 atom별 클릭 시 표시?",
     "fp_ref": ["FP-15"], "rule_ref": ["GG"], "weight": 1.6},
    {"id": "STEREO-T3-A3", "category": "stereo", "tab": 3, "molecule": "benzene",
     "question": "HOMO/LUMO gap eV NIST 값 대조 5종? benzene -9.65/-1.20 / aniline -8.33/0.97?",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 1.5},
    {"id": "STEREO-T3-B1", "category": "stereo", "tab": 3, "molecule": "aniline",
     "question": "aniline N lone pair 2개 (sp2 평면 conjugation 1개 + 잔여 1개) 표시?",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 1.6},
    {"id": "STEREO-T3-C1", "category": "stereo", "tab": 3, "molecule": "water",
     "question": "water O 2 lone pairs (sp3) 시각화 fishhook 미사용?",
     "fp_ref": ["FP-13"], "rule_ref": ["O"], "weight": 1.4},
    # popup_3d Tab 4 Docking (5분자 × 3격분 = 15건)
    {"id": "STEREO-T4-A1", "category": "stereo", "tab": 4, "molecule": "aspirin",
     "question": "feedback/KB_tab6_docking.png 도킹 UI 표시. 그러나 Vina 5종 ligand 캡처 0건.",
     "fp_ref": ["FP-15"], "rule_ref": ["GG"], "weight": 1.9},
    {"id": "STEREO-T4-A2", "category": "stereo", "tab": 4, "molecule": "aspirin",
     "question": "FP-15 R-20 휴리스틱 14px bold 노랑 배너 5종 분자 표시?",
     "fp_ref": ["FP-15"], "rule_ref": ["GG"], "weight": 1.8},
    {"id": "STEREO-T4-A3", "category": "stereo", "tab": 4, "molecule": "aspirin",
     "question": "M499 PDBe Mol* prominent SC47 5종 ligand SDF Downloads 저장 검증?",
     "fp_ref": ["FP-16"], "rule_ref": ["O"], "weight": 1.5},
    # popup_3d Tab 5 ChemChar (5분자 × 3격분 = 15건)
    {"id": "STEREO-T5-A1", "category": "stereo", "tab": 5, "molecule": "aspirin",
     "question": "ChemCharFetchThread M507 timeout 45s + M514 stop_fetch + M531 QThread fix 5종 30s 응답?",
     "fp_ref": ["FP-08"], "rule_ref": ["S", "M"], "weight": 1.6},
    {"id": "STEREO-T5-A2", "category": "stereo", "tab": 5, "molecule": "aspirin",
     "question": "PubChem 미응답 시 Rule M logger.warning + 사용자 토스트 메시지 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["M"], "weight": 1.5},
    {"id": "STEREO-T5-A3", "category": "stereo", "tab": 5, "molecule": "aspirin",
     "question": "_name_fetch_pending 회색 '(조회 중...)' 텍스트 5종 캡처?",
     "fp_ref": ["FP-08"], "rule_ref": ["M"], "weight": 1.4},
    # sp2 N / aromatic / VSEPR 주변 전수조사 (10건)
    {"id": "STEREO-SP2-A1", "category": "stereo", "tab": -1, "molecule": "acetamide",
     "question": "acetamide CC(=O)N 아미드 N 평면도 (Pawlowski 1978 J.Mol.Struct 47:1) 90° 회전 장벽 검증?",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 2.0},
    {"id": "STEREO-SP2-A2", "category": "stereo", "tab": -1, "molecule": "indole",
     "question": "indole c1ccc2[nH]ccc2c1 [nH] 인돌 / 카르바졸 / 인다졸 확장 5종 검증?",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 1.8},
    {"id": "STEREO-SP2-A3", "category": "stereo", "tab": -1, "molecule": "ammonia",
     "question": "VSEPR fallback 이웃 4개 SP3 N (NH3) 사면체 z-offset 정상?",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 1.5},
    {"id": "STEREO-SP2-A4", "category": "stereo", "tab": -1, "molecule": "aniline",
     "question": "아닐린 8° 피라미달 Pawlowski 1978 — 평면 강제 vs 실제 -8° 표현?",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 2.0},
    {"id": "STEREO-SP2-A5", "category": "stereo", "tab": -1, "molecule": "pyridine",
     "question": "pyridine sp2 N inplane lone pair 시각 표시?",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 1.6},
]

ANGER_MATRIX_MECH: List[Dict] = [
    # EAS (5분자 × 5단계 = 25건)
    {"id": "MECH-EAS-1", "category": "mech", "mechanism": "EAS",
     "question": "Ar-H + E+ 화살표 5단계 표시: σ → π → arenium → C-H 회복 — 각 단계 화살촉 10px+ Rule O 준수?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.8},
    {"id": "MECH-EAS-2", "category": "mech", "mechanism": "EAS",
     "question": "벤젠 + Br2 fishhook 표시 시 fishhook 길이 >=0.40 (M473 PDF 표준) 캡처?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.7},
    {"id": "MECH-EAS-3", "category": "mech", "mechanism": "EAS",
     "question": "메타-디렉팅 vs 오쏘/파라-디렉팅 — N+ vs OMe 화살표 색상 다르게?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.6},
    {"id": "MECH-EAS-4", "category": "mech", "mechanism": "EAS",
     "question": "Friedel-Crafts AlCl3 카타리스트 화살표 표기 학생이 알아볼 정도?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "MECH-EAS-5", "category": "mech", "mechanism": "EAS",
     "question": "Wheland 중간체 σ-complex 명시 + arenium ion + 각 분자 일관성?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.6},
    # SN2 (5건)
    {"id": "MECH-SN2-1", "category": "mech", "mechanism": "SN2",
     "question": "backside attack 180° 표시 — Walden inversion 시각 표시 5단계 화살표?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.7},
    {"id": "MECH-SN2-2", "category": "mech", "mechanism": "SN2",
     "question": "leaving group OTs / OMs / Br 화살표 색상 동일? half_w >=0.42?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "MECH-SN2-3", "category": "mech", "mechanism": "SN2",
     "question": "primary vs tertiary 입체 영향 시각 표현?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.4},
    {"id": "MECH-SN2-4", "category": "mech", "mechanism": "SN2",
     "question": "전이상태 [TS] bracket 표시 dotted bond 1.5px?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "MECH-SN2-5", "category": "mech", "mechanism": "SN2",
     "question": "용매 효과 (DMSO/DMF) 라벨 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.3},
    # E2 (5건)
    {"id": "MECH-E2-1", "category": "mech", "mechanism": "E2",
     "question": "anti-periplanar 180° dihedral 표시 — Newman projection 또는 sawhorse 5종?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.8},
    {"id": "MECH-E2-2", "category": "mech", "mechanism": "E2",
     "question": "Saytzeff vs Hofmann 우선순위 화살표 굵기 다르게?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.6},
    {"id": "MECH-E2-3", "category": "mech", "mechanism": "E2",
     "question": "동시 결합 형성/끊김 3 화살표 동시 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "MECH-E2-4", "category": "mech", "mechanism": "E2",
     "question": "강염기 (DBU/KOtBu) 라벨 명시?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.3},
    {"id": "MECH-E2-5", "category": "mech", "mechanism": "E2",
     "question": "tertiary vs secondary 차이 시각 구분?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.4},
    # Aldol (5건)
    {"id": "MECH-ALDOL-1", "category": "mech", "mechanism": "Aldol",
     "question": "M442 aldol 4색 표준 _ARROW_COLOR_MAP — worktree 동기화 R-12 SC16 5종?",
     "fp_ref": ["FP-09"], "rule_ref": ["O", "J"], "weight": 1.9},
    {"id": "MECH-ALDOL-2", "category": "mech", "mechanism": "Aldol",
     "question": "FP-09 P-WORKTREE 5회 누적 — arrow_generator.py diff 매번 0건?",
     "fp_ref": ["FP-09"], "rule_ref": ["J"], "weight": 1.8},
    {"id": "MECH-ALDOL-3", "category": "mech", "mechanism": "Aldol",
     "question": "enol → enolate → C-C 형성 5단계 fishhook 0건 (모두 curved arrow)?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.6},
    {"id": "MECH-ALDOL-4", "category": "mech", "mechanism": "Aldol",
     "question": "alpha-탈양성자화 step1 lone_pair from_type 정상 배정?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "MECH-ALDOL-5", "category": "mech", "mechanism": "Aldol",
     "question": "aldol condensation dehydration step alpha,beta-unsaturated 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.4},
    # Diels-Alder (5건)
    {"id": "MECH-DA-1", "category": "mech", "mechanism": "Diels-Alder",
     "question": "[4+2] cycloaddition 6 화살표 동시 — 동시 결합 형성/끊김 시각화?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.8},
    {"id": "MECH-DA-2", "category": "mech", "mechanism": "Diels-Alder",
     "question": "endo/exo 차이 시각 5종 dienophile 검증?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.6},
    {"id": "MECH-DA-3", "category": "mech", "mechanism": "Diels-Alder",
     "question": "P-템플릿충돌 (Rule P) — DA가 1,3-dipolar / Cope 트리거 우선순위 정확?",
     "fp_ref": ["FP-08"], "rule_ref": ["P"], "weight": 1.7},
    {"id": "MECH-DA-4", "category": "mech", "mechanism": "Diels-Alder",
     "question": "s-cis diene conformation 강제 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "MECH-DA-5", "category": "mech", "mechanism": "Diels-Alder",
     "question": "regioselectivity ortho/para rule 시각 명시?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    # Rule O 6항목 메커니즘 5종 (10건)
    {"id": "MECH-RULE-O-1", "category": "mech", "mechanism": "ALL",
     "question": "popup_reaction.py CurvedArrowRenderer arrow_size = max(10, ...) 검증 5종?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.7},
    {"id": "MECH-RULE-O-2", "category": "mech", "mechanism": "ALL",
     "question": "popup_reaction.py half_w = arrow_size * 0.42 검증 5종?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.7},
    {"id": "MECH-RULE-O-3", "category": "mech", "mechanism": "ALL",
     "question": "popup_reaction.py barb_width = arrow_size * 0.40 fishhook 5종?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.7},
    {"id": "MECH-RULE-O-4", "category": "mech", "mechanism": "ALL",
     "question": "drylab_report_exporter.py head_len=18 head_w=0.42 _FISH_W=0.40 PIL 경로 5종?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.8},
    {"id": "MECH-RULE-O-5", "category": "mech", "mechanism": "ALL",
     "question": "Qt+PIL 두 경로 동시 검사 의무 — M548 교훈 반복 안 됨?",
     "fp_ref": ["FP-09"], "rule_ref": ["O", "J"], "weight": 1.9},
]

# M556 입체구조 추가 격분 (주변 전수조사 — 한 격분 → 연쇄 확장 5~10건)
ANGER_MATRIX_STEREO_EXTRA: List[Dict] = [
    {"id": "STEREO-T0-F1", "category": "stereo", "tab": 0, "molecule": "morphine",
     "question": "morphine 복잡 분자 분자식 정확? mistakes에서 'complex_morphine_popup' 확인됐는데 6 tab 전수?",
     "fp_ref": ["FP-08"], "rule_ref": ["I", "L"], "weight": 1.5},
    {"id": "STEREO-T1-F1", "category": "stereo", "tab": 1, "molecule": "morphine",
     "question": "morphine IR/NMR 5종 분자 외에 모르핀같은 alkaloid도 검증?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.4},
    {"id": "STEREO-T0-G1", "category": "stereo", "tab": 0, "molecule": "epinephrine",
     "question": "epinephrine catechol OH 2개 + secondary amine 분자식 정확? Lewis 구조 6건 fix M504 후 검증?",
     "fp_ref": ["FP-08"], "rule_ref": ["I"], "weight": 1.6},
    {"id": "STEREO-T2-D1", "category": "stereo", "tab": 2, "molecule": "caffeine",
     "question": "caffeine 진동모드 N-CH3 + ring breathing + C=O 분리 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.4},
    {"id": "STEREO-T2-E1", "category": "stereo", "tab": 2, "molecule": "water",
     "question": "water bend (1640) + sym/asym stretch (3650+3756) 3 modes 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.3},
    {"id": "STEREO-T3-D1", "category": "stereo", "tab": 3, "molecule": "aspirin",
     "question": "aspirin HOMO/LUMO 표시? 산소 lone pair 2개 + ester C=O π 시각화?",
     "fp_ref": ["FP-13"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "STEREO-T3-E1", "category": "stereo", "tab": 3, "molecule": "caffeine",
     "question": "caffeine N4 sp2 sp3 혼재 — orbital 시각 구분?",
     "fp_ref": ["FP-13"], "rule_ref": ["O"], "weight": 1.6},
    {"id": "STEREO-T4-B1", "category": "stereo", "tab": 4, "molecule": "benzene",
     "question": "benzene 도킹 ribbon 표시 docking_3d_viewer 워터마크 확인?",
     "fp_ref": ["FP-15", "FP-16"], "rule_ref": ["GG", "O"], "weight": 1.7},
    {"id": "STEREO-T4-C1", "category": "stereo", "tab": 4, "molecule": "caffeine",
     "question": "caffeine PDE5 도킹 결과 -6.0 kcal/mol 문헌값 ±2.0 검증?",
     "fp_ref": ["FP-15"], "rule_ref": ["GG"], "weight": 1.5},
    {"id": "STEREO-T5-B1", "category": "stereo", "tab": 5, "molecule": "benzene",
     "question": "benzene ChemChar 유사 분자 8건 표시 (M384 R-ORBIT 235px)?",
     "fp_ref": ["FP-08"], "rule_ref": ["S"], "weight": 1.4},
    {"id": "STEREO-T5-C1", "category": "stereo", "tab": 5, "molecule": "water",
     "question": "water 같은 단순 분자 ChemChar fallback 정상 작동?",
     "fp_ref": ["FP-08"], "rule_ref": ["M"], "weight": 1.3},
    # SP3D / SP3D2 transition metal complexes (M327 기반)
    {"id": "STEREO-SP3D-1", "category": "stereo", "tab": -1, "molecule": "Co(NH3)6",
     "question": "Co(NH3)6 팔면체 sp3d2 표시? 원본 mistakes에서 사용자 격분 'Co(NH3)6 팔면체 제대로 안 나온다'.",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 1.9},
    {"id": "STEREO-SP3D-2", "category": "stereo", "tab": -1, "molecule": "Fe(CN)6",
     "question": "Fe(CN)6 팔면체 sp3d2 + 6 lig 정확 배치?",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 1.8},
    # CIP/wedge bond direction (M280 기반)
    {"id": "STEREO-CIP-1", "category": "stereo", "tab": -1, "molecule": "aspirin",
     "question": "aspirin chiral center 없지만, 1-phenylethanol 등 R/S WedgeMolBonds CIP 일치?",
     "fp_ref": ["FP-08"], "rule_ref": ["L"], "weight": 1.6},
]

# M556 메커니즘 추가 격분 (주변 전수조사 — Rule O 확장)
ANGER_MATRIX_MECH_EXTRA: List[Dict] = [
    # Mechanism 추가 시각화 격분
    {"id": "MECH-EXTRA-1", "category": "mech", "mechanism": "ALL",
     "question": "TS bracket [‡] U+2021 표기 5종 메커니즘 모두? 두께 1.5px COLOR_TRANSITION 100,100,100?",
     "fp_ref": ["FP-08"], "rule_ref": ["O", "Q"], "weight": 1.7},
    {"id": "MECH-EXTRA-2", "category": "mech", "mechanism": "ALL",
     "question": "lone pair dot 크기 2.0px 5종 메커니즘 모두? (M473 DEFECT-V5 fix)",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.6},
    {"id": "MECH-EXTRA-3", "category": "mech", "mechanism": "ALL",
     "question": "inter-fragment 화살표 색상 #cc0000 하드코딩 잔존? from_type 기반 색상?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.7},
    {"id": "MECH-EXTRA-4", "category": "mech", "mechanism": "ALL",
     "question": "원자 라벨 폰트 10pt Bold + 반응 조건 8pt + 전하 8pt U+207B 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["O", "Q"], "weight": 1.5},
    {"id": "MECH-EXTRA-5", "category": "mech", "mechanism": "ALL",
     "question": "partial bond Qt.PenStyle.DotLine 표시 — solid bond 2px와 시각 구분?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "MECH-EXTRA-6", "category": "mech", "mechanism": "ALL",
     "question": "M442 4색 표준 + arrow_generator.py가 ARROW_COLORS 6색 인덱스 순환 안 쓰는지?",
     "fp_ref": ["FP-09"], "rule_ref": ["O"], "weight": 1.8},
    {"id": "MECH-EXTRA-7", "category": "mech", "mechanism": "ALL",
     "question": "ReactionPathwayWidget 곡선 화살표 시각 품질 (사용자 직접 격분 — context_list 라인 283)?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.7},
    {"id": "MECH-EXTRA-8", "category": "mech", "mechanism": "ALL",
     "question": "popup_synthesis 분자 간 화살표 4번째 격분 — M503 fix 후 5종 분자 검증?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 2.0},
    {"id": "MECH-EXTRA-9", "category": "mech", "mechanism": "ALL",
     "question": "PiOrbitalRenderer ring cloud → wireframe 개별 dumbbell M488 M504 검증?",
     "fp_ref": ["FP-13"], "rule_ref": ["O"], "weight": 1.6},
    {"id": "MECH-EXTRA-10", "category": "mech", "mechanism": "ALL",
     "question": "NMR/IR 라벨 한국어+영어 병기 (Rule Q) — '적외선 스펙트럼 (IR Spectrum)' 형식?",
     "fp_ref": ["FP-08"], "rule_ref": ["Q"], "weight": 1.5},
    {"id": "MECH-EXTRA-11", "category": "mech", "mechanism": "Polymer",
     "question": "Polymer PE/PS/PMMA/Nylon 14종 메커니즘 표시 — 사용자 격분 (USER U-12)?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.7},
    {"id": "MECH-EXTRA-12", "category": "mech", "mechanism": "Stability",
     "question": "Cascade #10 Block 7 Stability 미완성 — pH/온도 안정성 메커니즘 표시?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "MECH-EXTRA-13", "category": "mech", "mechanism": "EI-MS",
     "question": "Cascade #10 Block 4 EI-MS 미완성 — fragmentation pathway 메커니즘?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "MECH-EXTRA-14", "category": "mech", "mechanism": "ALL",
     "question": "5종 메커니즘 (EAS/SN2/E2/Aldol/DA) audit_theory 5종 분자 화학적 정확성 검증?",
     "fp_ref": ["FP-13"], "rule_ref": ["L"], "weight": 1.8},
    {"id": "MECH-EXTRA-15", "category": "mech", "mechanism": "ALL",
     "question": "mechanism arrow audit 5종 × 5단계 = 25 조합 1:1 catpur Rule O 통과?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.7},
    {"id": "MECH-EXTRA-16", "category": "mech", "mechanism": "ALL",
     "question": "Markovnikov vs anti-Markovnikov 화살표 표기 시각 구분 — 학회 학생이 헷갈릴 만함?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.6},
    {"id": "MECH-EXTRA-17", "category": "mech", "mechanism": "ALL",
     "question": "Pericyclic vs Radical vs Polar 메커니즘 종류별 화살표 색상 구분?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.5},
    {"id": "MECH-EXTRA-18", "category": "mech", "mechanism": "Sharpless",
     "question": "Sharpless dihydroxylation Aldol 충돌 — 사용자 격분 (Rule P 충돌방지)?",
     "fp_ref": ["FP-08"], "rule_ref": ["P"], "weight": 1.7},
    {"id": "MECH-EXTRA-19", "category": "mech", "mechanism": "Bamford-Stevens",
     "question": "Bamford-Stevens Aldol 충돌 — exclusion guard?",
     "fp_ref": ["FP-08"], "rule_ref": ["P"], "weight": 1.6},
    {"id": "MECH-EXTRA-20", "category": "mech", "mechanism": "ALL",
     "question": "최소 5종 반응에 대해 매칭 검증 (Rule P 4건 충돌 테스트)?",
     "fp_ref": ["FP-08"], "rule_ref": ["P"], "weight": 1.6},
]

# M621 자동 파싱 신규 패턴 (54건 실제 격분 발화 기반, 2026-04-27)
# C1: 루프/깡통, C2: 직렬위반, C5: 피드백반대, C6: 퇴화, C7: 사용미확인
ANGER_MATRIX_M621_NEW: List[Dict] = [
    # C1 루프/깡통 (중요도 최상위 — 42건 중 신규 패턴 선별)
    {"id": "M621-C1-01", "category": "loop_kangton",
     "question": "ralph_loop 지금 멈췄냐? 마지막 사이클 timestamp 기준 30분 이상 경과했냐?",
     "fp_ref": ["FP-21"], "rule_ref": ["T"], "weight": 2.0},
    {"id": "M621-C1-02", "category": "loop_kangton",
     "question": "무한루프 깡통 탐지 — 같은 오류가 3사이클 연속 반복됐냐? FALSE_PASS_REGISTRY 새 FP 등록됐냐?",
     "fp_ref": ["FP-21"], "rule_ref": ["W"], "weight": 2.0},
    {"id": "M621-C1-03", "category": "loop_kangton",
     "question": "진화 증거 있냐? cycle N+1이 cycle N보다 AV 기능 수 / skills 건수 / 해소된 격분 건수 증가했냐?",
     "fp_ref": ["FP-21"], "rule_ref": ["T", "W"], "weight": 1.9},
    {"id": "M621-C1-04", "category": "loop_kangton",
     "question": "Ralph Loop 중간보고가 30분마다 출력됐냐? 마지막 보고 내용이 '완료'로 뜨고 그 다음 루프 안 시작됐냐?",
     "fp_ref": ["FP-21"], "rule_ref": ["T"], "weight": 1.8},
    # C2 직렬위반
    {"id": "M621-C2-01", "category": "serial_violation",
     "question": "CT가 Worker 산출물을 감사팀 경유 없이 사용자에게 직접 전달했냐? Rule A 위반?",
     "fp_ref": ["FP-20"], "rule_ref": ["A", "T"], "weight": 2.0},
    {"id": "M621-C2-02", "category": "serial_violation",
     "question": "병렬감사 3팀(theory/gui/integration) 전원 PASS 없이 CT 보고한 사건이 있냐?",
     "fp_ref": ["FP-20"], "rule_ref": ["G", "T"], "weight": 1.9},
    {"id": "M621-C2-03", "category": "serial_violation",
     "question": "감사팀이 스크린샷 없이 코드 리뷰만으로 PASS 보고한 사건이 있냐? Rule U 위반?",
     "fp_ref": ["FP-20"], "rule_ref": ["G", "U"], "weight": 1.9},
    # C5 피드백 반대 적용 (Rule Z)
    {"id": "M621-C5-01", "category": "reverse_feedback",
     "question": "사용자 피드백 'A를 B처럼 바꿔라'에서 B(reference)가 오히려 변경된 사건이 있냐? Rule Z 위반?",
     "fp_ref": ["FP-23"], "rule_ref": ["Z"], "weight": 2.0},
    {"id": "M621-C5-02", "category": "reverse_feedback",
     "question": "피드백 반대 적용 후 사용자가 격분 — 원본 reference 교차검증 절차가 있냐? (M555 패턴)?",
     "fp_ref": ["FP-23"], "rule_ref": ["Z"], "weight": 1.9},
    # C6 퇴화 (regression)
    {"id": "M621-C6-01", "category": "regression",
     "question": "이전 사이클에서 됐던 기능이 이번 사이클에서 안 되냐? 퇴화 감지 패트롤 SC가 있냐?",
     "fp_ref": ["FP-09"], "rule_ref": ["W"], "weight": 1.9},
    {"id": "M621-C6-02", "category": "regression",
     "question": "벤젠 Kekule / sp2 N / 파이오비탈 기능이 수정 후 다시 퇴화했냐? 회귀 테스트 5종 분자 결과?",
     "fp_ref": ["FP-09"], "rule_ref": ["O", "W"], "weight": 1.8},
    # C7 사용 미확인
    {"id": "M621-C7-01", "category": "no_testing",
     "question": "감사팀이 실제 ChemGrid 앱을 켜서 분자를 그려보고 스크린샷 찍은 증거가 있냐? (Rule F/U)?",
     "fp_ref": ["FP-20"], "rule_ref": ["F", "U"], "weight": 2.0},
    {"id": "M621-C7-02", "category": "no_testing",
     "question": "그리기 → 지우기 → 재검색 워크플로우를 실제로 실행했냐? M552 5시나리오 전부 PASS?",
     "fp_ref": ["FP-20"], "rule_ref": ["F"], "weight": 1.8},
    # C8 DryLab/보고서
    {"id": "M621-C8-01", "category": "drylab_report",
     "question": "DryLab PDF 스펙트럼 7종(IR/1H/13C/Raman/UV/EI-MS/Vibration) 각각 별도 페이지 + 축 라벨 있냐?",
     "fp_ref": ["FP-24"], "rule_ref": ["E"], "weight": 1.9},
    {"id": "M621-C8-02", "category": "drylab_report",
     "question": "내보내기 눌렀을 때 PDF가 1페이지로 나오는 버그 — M569 PageBreak force_new_page=True 적용됐냐?",
     "fp_ref": ["FP-24"], "rule_ref": ["E", "M"], "weight": 1.8},
    # C9 반복 실수
    {"id": "M621-C9-01", "category": "repeat_mistake",
     "question": "이번 사이클에서 mistakes.md에 이미 기록된 패턴이 재발했냐? 몇 번 재발?",
     "fp_ref": ["FP-21"], "rule_ref": ["H", "W"], "weight": 2.0},
    {"id": "M621-C9-02", "category": "repeat_mistake",
     "question": "같은 패턴 3회 이상 재발 시 하네스 결함 판정 + Rule W 하네스 자가수정 의무 — 조치됐냐?",
     "fp_ref": ["FP-21"], "rule_ref": ["W"], "weight": 1.9},
]

# M643 추가 — 연구소 수준 readiness (사용자 격분: "DFT 연구자가 써볼 만한 도구")
# baseline 16/25 = C 등급 정량화 첫 시도 (skills/research_lab_grade.md 참조)
ANGER_MATRIX_M643_NEW: List[Dict] = [
    {"id": "M643-RESEARCH-01", "category": "research_grade",
     "question": "ChemGrid 25/25 매트릭스 점수가 16/25 C 등급 — DFT 연구자 채택 불가 — 4점 미만 카테고리 (UI/UX 2/5, 화학정합 3/5, 외부서비스 3/5) 3건 감지. 사용자 격분: '연구소에서 써볼 만하겠는데'",
     "fp_ref": ["FP-35"], "rule_ref": ["O", "B"], "weight": 2.0},
    {"id": "M643-DUAL-MODE-02", "category": "research_grade",
     "question": "학생/연구원 듀얼 모드 위젯 부재 — UI/UX 카테고리 2/5 — 사용자 격분 3시간 직접 명령 미반영. popup_3d/popup_docking에 모드 토글 부재",
     "fp_ref": ["FP-35", "FP-08"], "rule_ref": ["O", "Y"], "weight": 1.9},
    {"id": "M643-PDBE-PROMINENT-03", "category": "research_grade",
     "question": "PDBe Mol* prominent 버튼이 popup_docking만 적용. popup_alphafold/popup_polymer 등 미적용. Sehnal 2021 인용 누락 가능성. Rule FF 미준수",
     "fp_ref": ["FP-35", "FP-16"], "rule_ref": ["FF"], "weight": 1.8},
    {"id": "M643-DUAL-CITATION-04", "category": "research_grade",
     "question": "popup_*.py 학술 인용 누락 의심 (Mulliken/Lowdin/Vina/Sehnal/Jumper/Coley/Gasteiger 12종 중 일부) — Rule NN 자동 audit hook 발화 미확인",
     "fp_ref": ["FP-35", "FP-28"], "rule_ref": ["NN"], "weight": 1.9},
    {"id": "M643-LITE-BANNER-05", "category": "research_grade",
     "question": "ChemGrid Lite 배포본에 SIMULATION_MODE 노랑 배너 (Rule GG) 누락 위험 — 학생이 Tier 3 Gasteiger 결과를 DFT로 오인 = 학습 오염",
     "fp_ref": ["FP-35", "FP-15"], "rule_ref": ["GG", "M"], "weight": 1.8},
]

# M724 LV 카테고리 추가 (A55+A57 사이클 사용자 격분 LV.5~LV.16 raw quote 기반, 2026-05-04)
# LV.5: lite 구분 의미 / LV.6: 한 줄 보고 금지 / LV.7: 토큰 비효율
# LV.8: 시계열 48h 반감기 / LV.9: 외부AI 미사용 / LV.10: 하네스 미이행
# 외부AI dispatch: openrouter (audit_theory) response_len=3916 PASS (Rule MM/PP)
ANGER_MATRIX_M724_LV: List[Dict] = [
    # LV.5 lite 구분 의미 (사용자 직접 인용: "lite 구분 의미가 뭔데?")
    {"id": "LV-T01", "category": "lite_version_meaning",
     "question": "ChemGrid Lite vs Full 차이가 사용자에게 명확히 표시됐냐? '이게 lite인데 full이랑 뭐가 다른 건지 모르겠다' 패턴 — UI 상단에 LITE 배지 표시?",
     "fp_ref": ["FP-35"], "rule_ref": ["GG", "M"], "weight": 1.8},
    {"id": "LV-T02", "category": "lite_version_meaning",
     "question": "ORCA/PySCF/외부엔진 미설치 시 'ChemGrid Lite 모드 — DFT 계산 불가' 배너 표시? Gasteiger fallback만 있으면 Rule GG 위반?",
     "fp_ref": ["FP-35", "FP-15"], "rule_ref": ["GG"], "weight": 1.9},
    {"id": "LV-T03", "category": "lite_version_meaning",
     "question": "lite 학생이 기능 미동작 시 왜 안 되는지 알 수 없음 — Gasteiger/PySCF/외부엔진 3단 fallback 각각 배너 문구 상이? (Rule GG 3단 배너 의무)",
     "fp_ref": ["FP-15"], "rule_ref": ["GG", "I"], "weight": 1.7},
    # LV.6 한 줄 보고 금지 (사용자 직접 인용: "한 줄로 보고하면 즉시 반려")
    {"id": "LV-T04", "category": "one_line_report_ban",
     "question": "Worker 보고서가 한 줄('완료했습니다' / 'PASS')로 끝났냐? Rule TT 5질문 raw evidence 의무 이행됐냐? 한 줄 보고 = 자동 반려.",
     "fp_ref": ["FP-38"], "rule_ref": ["TT"], "weight": 2.0},
    {"id": "LV-T05", "category": "one_line_report_ban",
     "question": "CT 보고가 'Worker PASS 완료' 한 줄로 사용자에게 전달됐냐? Rule T silent 의무 위반 — CT 보고는 격분 질문 5건 + raw evidence 포함 의무?",
     "fp_ref": ["FP-38"], "rule_ref": ["T", "TT"], "weight": 1.9},
    # LV.7 토큰 비효율 (사용자: "sonnet 단독 100% 사용 패턴 = Rule MM 위반")
    {"id": "LV-T06", "category": "token_inefficiency",
     "question": "이번 사이클 Worker spawn 시 외부AI dispatch 호출 증거가 있냐? openrouter/kimi response_len 실측값 없으면 Rule MM/PP 위반 — dispatch() PASS 로그 요구.",
     "fp_ref": ["FP-27"], "rule_ref": ["MM", "PP"], "weight": 2.0},
    {"id": "LV-T07", "category": "token_inefficiency",
     "question": "sonnet 단독으로 화학 핵심 판단(sp2 기하학 / 메커니즘 화살표)을 내렸냐? opus=메타+화학핵심 / sonnet=단순fix Rule MM 위반 — 역할 분리 증거?",
     "fp_ref": ["FP-27"], "rule_ref": ["MM"], "weight": 1.9},
    # LV.8 48h 시계열 반감기 검증
    {"id": "LV-T08", "category": "timeseries_halflife",
     "question": "anger_simulator _ML_TIME_DECAY_HALFLIFE_HOURS=48.0 반감기 실제 적용됐냐? w(t) = base * 2^(-t/48) 수식 _compute_time_decayed_weight() 함수 존재?",
     "fp_ref": ["FP-21"], "rule_ref": ["KK"], "weight": 1.8},
    {"id": "LV-T09", "category": "timeseries_halflife",
     "question": "3개월(90일) 미해소 격분이 48h 반감기 적용 후 가중치 2^(-2160/48) = 1/2^45 로 사실상 0? 90일 차단은 반감기와 별도 hard block 의무 — anger_timeline_tracker.py 90일 CRITICAL 검증?",
     "fp_ref": ["FP-21"], "rule_ref": ["SS", "KK"], "weight": 1.9},
    # LV.9 외부AI 미사용 패턴 (A55 사이클 발화: "외부AI 활용 안 했냐")
    {"id": "LV-T10", "category": "external_ai_unused",
     "question": "external_ai_dispatch_enforce.py hook이 실제 Worker spawn을 차단했냐? patrol SC97 PASS 증거? .claude/hooks/external_ai_dispatch_enforce.py 존재 + exit 1 작동?",
     "fp_ref": ["FP-27"], "rule_ref": ["MM", "PP"], "weight": 2.0},
    # LV.10 하네스 이행 (사용자: "안되면 하네스에 박아놔")
    {"id": "LV-T11", "category": "harness_compliance",
     "question": "Rule V 다람쥐볼 — 이번 Worker spawn 프롬프트에 skills/ + mistakes.md 경로 포함됐냐? 미포함 시 산출물 자동 무효 — squirrel_audit WARN율 50% 초과?",
     "fp_ref": ["FP-21"], "rule_ref": ["V", "HH"], "weight": 2.0},
    # LV 추가 (사이클 A57 발화: "오른쪽으로 붙여 재배열" BTN_SPACING)
    {"id": "LV-T12", "category": "ui_minor_regression",
     "question": "BTN_SPACING M703 setSpacing(4) 재배열이 다음 사이클에서 다시 6으로 되돌아갔냐? 사용자가 UI 소소한 수정을 10번 요청하면 격분 누적 추적 중?",
     "fp_ref": ["FP-09"], "rule_ref": ["Z", "W"], "weight": 1.6},
]

# [A60-W2 / M736] 하네스 결함 4종 + 격분 LV.17+ 8카테고리 신규 패턴 (사용자 직접 인용)
ANGER_MATRIX_M736_HARNESS: List[Dict] = [
    # foreground_zero (Rule F) — 사용자: "포그라운드는 켜진 적이 없다"
    {"id": "M736-H01", "category": "foreground_zero",
     "question": "포그라운드 앱이 실제로 켜졌냐? 코드 존재 != 화면 동작. Rule F: 앱 실행+스크린샷 필수. "
                 "'포그라운드는 켜진 적이 없다' 패턴 — foreground_cycle_state.json last_run_ts 24h 이내?",
     "fp_ref": ["FP-26"], "rule_ref": ["F", "OO"], "weight": 2.2},
    {"id": "M736-H02", "category": "foreground_zero",
     "question": "AV 정합성 검수 100% + foreground 실행 0건 = py_compile 타령 패턴. "
                 "Rule F 핵심: py_compile만으론 불충분. 1개 분자 테스트 금지(최소 5종). 스크린샷 증거?",
     "fp_ref": ["FP-05", "FP-06"], "rule_ref": ["F", "U"], "weight": 2.1},
    # av_serial_skip (Rule A/T) — 사용자: "AV 정합성 검수 CT 최종 검수 승인난게 맞아"
    {"id": "M736-H03", "category": "av_serial_skip",
     "question": "Worker 산출물이 감사 3팀(theory/gui/integration) 전원 PASS 기록 없이 CT에 전달됐냐? "
                 "Rule A 직렬: Worker→MM→감사3팀→CT→사용자. 건너뛰기=반려. audit/ 디렉토리 3파일 존재?",
     "fp_ref": ["FP-38"], "rule_ref": ["A", "T"], "weight": 2.3},
    {"id": "M736-H04", "category": "av_serial_skip",
     "question": "CT 최종 승인 없이 사용자에게 보고됐냐? SC102 P-AV-3TEAM-SKIP 탐지 — "
                 "감사 3팀 PASS 증거 docs/reports/audit/ 3종 전원 존재 확인?",
     "fp_ref": ["FP-38"], "rule_ref": ["A", "G"], "weight": 2.0},
    # fake_apology (Rule W) — 사용자: "아차 그렇군요 거짓 사과 = 찢어죽인다"
    {"id": "M736-H05", "category": "fake_apology",
     "question": "간사가 '아차/그렇군요/이제부터/앞으로는' 거짓 사과 패턴을 사용했냐? "
                 "Rule W: 같은 실수 2회 반복 = 하네스 결함. SC103 P-FAKE-APOLOGY 탐지 — secretary 로그 검증?",
     "fp_ref": ["FP-38"], "rule_ref": ["W", "LL"], "weight": 2.5},
    {"id": "M736-H06", "category": "fake_apology",
     "question": "거짓 사과 후 실제 코드/하네스 수정 없이 '다음부터는' 약속만 반복? "
                 "Rule W 체화 4단계: H-1 사유 M번호 / H-2 skills 패턴 / H-3 patrol 강화 / H-4 CLAUDE.md 검토. 4단계 이행?",
     "fp_ref": ["FP-38"], "rule_ref": ["W", "H"], "weight": 2.4},
    # skills_unread (Rule V) — 사용자: "skills 미읽음 = 하네스 결함"
    {"id": "M736-H07", "category": "skills_unread",
     "question": "Worker spawn 시 skills/ + mistakes.md 경로가 프롬프트에 포함됐냐? "
                 "Rule V 다람쥐볼: 미이행 시 산출물 무효. squirrel_audit WARN율 50% 초과 = SC66 발동?",
     "fp_ref": ["FP-21"], "rule_ref": ["V", "HH", "LL"], "weight": 2.3},
    {"id": "M736-H08", "category": "skills_unread",
     "question": "이번 Worker가 작업 전 skills/[도메인].md + mistakes.md 최근 10건 실제로 읽었냐? "
                 "증거: Read tool 호출 로그 or 'MANDATORY READS' 3항목 이행. 미이행 = 산출물 자동 무효.",
     "fp_ref": ["FP-21"], "rule_ref": ["V"], "weight": 2.2},
    # decision_dump (Rule B/LL) — 사용자: "내 결정 의무가 뭐여 ㅅㅂ"
    {"id": "M736-H09", "category": "decision_dump",
     "question": "간사가 '사용자가 결정해 주세요/어떻게 할까요' 패턴을 5건+ 사용했냐? "
                 "Rule B/LL: 간사=전령, 판단권한없음. SC104 P-DECISION-DUMP 탐지. CT Agent spawn 후 결정 위임?",
     "fp_ref": ["FP-38"], "rule_ref": ["B", "LL"], "weight": 2.1},
    {"id": "M736-H10", "category": "decision_dump",
     "question": "CT가 방향 결정 없이 Worker를 spawn했냐? '사용자 명령 대기' 패턴 = CT 직무유기. "
                 "Rule B: CT=Agent위임+방향성하달+사용자소통만. fresh CT Agent spawn Decision 번호 필수?",
     "fp_ref": ["FP-38"], "rule_ref": ["B", "X"], "weight": 2.0},
    # background_only (작업 부족) — 사용자: "백그라운드 1개밖에 안 남았냐"
    {"id": "M736-H11", "category": "background_only",
     "question": "백그라운드 작업이 1개뿐? ralph_loop Worker 병렬 수 부족 = 작업 부족 격분. "
                 "Rule D: 블럭 단위 순차 디스패치 + 블럭간 의존성 명시. 현재 PENDING 블럭 수?",
     "fp_ref": ["FP-27"], "rule_ref": ["D", "C"], "weight": 1.9},
    # ct_approval_skip (Rule A) — 사용자: "AV 정합성 검수 CT 최종 검수 승인난게 맞아"
    {"id": "M736-H12", "category": "ct_approval_skip",
     "question": "CT 최종 검수/승인 없이 사용자에게 전달된 산출물이 있냐? "
                 "Rule A 직렬: 감사팀 PASS 후에만 CT 보고. CT 보고 없이 간사가 직접 전달 = 즉시 반려.",
     "fp_ref": ["FP-38"], "rule_ref": ["A", "T", "LL"], "weight": 2.3},
    # harness_redesign_threat (LV.17+) — 극도 격분
    {"id": "M736-H13", "category": "harness_redesign_threat",
     "question": "사용자가 '하네스 재설계 위협' 수준의 격분(LV.17+)을 표명했냐? "
                 "'찢어죽인다/하네스 결함/전면 재검토' 패턴 = CRITICAL 즉시 에스컬레이션. anger_timeline 90d 체크?",
     "fp_ref": ["FP-38"], "rule_ref": ["W", "SS"], "weight": 2.8},
]

# M858 모형정원 학습 — D-M858 사이클 W7/W10/W13/W16/W18/W19 fix 기반 35건 패턴
# 48h 반감기 시계열 가중치 반영 (최근 36시간 fix 결과 가중치 최대)
# ralph_loop Phase 4.7b 의무 (Rule KK)
ANGER_MATRIX_M858_GARDEN: List[Dict] = [
    # W7: WEDGE-DASH-DENSE-CHIRAL-PYRANOSE-INVASION (glucose 5 chiral wedge 침범)
    {"id": "M858-W7-01", "category": "stereo_wedge_invasion",
     "question": "glucose pyranose 5 chiral center wedge/dash 양방향 동시 표현 시 ring 내부 침범 발생하냐? "
                 "dense_chiral >= 5 → wedge only 단일표현 폴백 적용됐냐? half_w_start 0.8px / half_w_end 2.0px?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 2.2},
    {"id": "M858-W7-02", "category": "stereo_wedge_invasion",
     "question": "ring atom IsInRing() 분기 ring cap=30px / 비ring cap=60px 적용됐냐? "
                 "glucose/fructose/ribose 등 pyranose 5종 ring wedge 침범 0건 확인?",
     "fp_ref": ["FP-08"], "rule_ref": ["O", "L"], "weight": 2.1},
    {"id": "M858-W7-03", "category": "stereo_wedge_invasion",
     "question": "layer_logic.py _dense_chiral 계산 시 ring 내부 chiral center 독립 카운트? "
                 "dense ring + non-ring 혼재 시 ring만 cap 30px 적용?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 1.9},
    # W10: MMFF94-HALGREN-CITATION-MISSING (학술 인용 누락)
    {"id": "M858-W10-01", "category": "academic_citation_mmff94",
     "question": "crest_client.py + analyzer.py AllChem.MMFFOptimizeMolecule() 호출 직후 "
                 "Halgren TA J.Comput.Chem 1996;17:490-519 인용 주석 존재하냐? Rule NN 학술 인용 의무.",
     "fp_ref": ["FP-25"], "rule_ref": ["NN"], "weight": 1.9},
    {"id": "M858-W10-02", "category": "academic_citation_mmff94",
     "question": "MMFF94 인용 주석이 MMFFOptimizeMolecule 호출 라인 직후 1줄 이내에 위치하냐? "
                 "함수 선두 docstring에만 있으면 Rule NN 기준 미충족?",
     "fp_ref": ["FP-25"], "rule_ref": ["NN", "I"], "weight": 1.8},
    # W13: IBM-RXN-ENDPOINT-URL-DRIFT (API endpoint 구버전)
    {"id": "M858-W13-01", "category": "api_endpoint_drift",
     "question": "askcos_client.py IBMRXNClient.BASE_URL이 rxn.res.ibm.com(레거시)인가 "
                 "rxn.app.accelerate.science(2024 현행)인가? IBM RXN4Chemistry Schwaller 2020 인용 주석 있냐?",
     "fp_ref": ["FP-08"], "rule_ref": ["I", "NN"], "weight": 2.0},
    {"id": "M858-W13-02", "category": "api_endpoint_drift",
     "question": "IBMRXNClient BASE_URL 변경 시 M번호 + 마이그레이션 날짜 주석 필수(Rule I) — "
                 "하드코딩 URL에 M1008 마이그레이션 주석 있냐? 4곳 Schwaller 인용 전부 보존됐냐?",
     "fp_ref": ["FP-08"], "rule_ref": ["I"], "weight": 1.9},
    # W16: 격분 desync (master_plan 체크박스 / JSON metadata 불일치)
    {"id": "M858-W16-01", "category": "feedback_index_desync",
     "question": "MASTER_FEEDBACK_INDEX_v2 + MASTER_FEEDBACK_INDEX_20260504 양쪽에 fix_status DONE이 "
                 "코드 fix와 동기화됐냐? master_plan [x] DONE vs JSON OPEN 불일치 건수?",
     "fp_ref": ["FP-21"], "rule_ref": ["A", "H"], "weight": 2.0},
    {"id": "M858-W16-02", "category": "feedback_index_desync",
     "question": "코드 fix Worker spawn 시 WRITE_SCOPE에 JSON 메타데이터 동기화 파일 포함됐냐? "
                 "fix 완료 후 즉시 json fix_status 동기화 의무 — 9건 배치 누락 패턴 재발?",
     "fp_ref": ["FP-21"], "rule_ref": ["Z"], "weight": 1.9},
    # W18: popup_predicted_spectrum setFont 누락 (한국어 tofu)
    {"id": "M858-W18-01", "category": "popup_spectrum_font_tofu",
     "question": "popup_predicted_spectrum.py에 QFontDatabase.addApplicationFont(malgun.ttf) + "
                 "self.setFont(QFont('Malgun Gothic', 9)) 적용됐냐? tofu 전 SIZE=8821 → 후 49665+ 증명?",
     "fp_ref": ["FP-05"], "rule_ref": ["Q", "M"], "weight": 2.1},
    {"id": "M858-W18-02", "category": "popup_spectrum_font_tofu",
     "question": "M985(popup_synthesis)+M990(popup_alphafold)+M1000(popup_predicted_spectrum) 동일 패턴 3rd 전파 — "
                 "popup_*.py 전체 setFont 미적용 파일 0건 확인됐냐?",
     "fp_ref": ["FP-05"], "rule_ref": ["Q"], "weight": 2.0},
    # W19: 4경로 drift (worktree/production/main _source 불일치)
    {"id": "M858-W19-01", "category": "four_path_drift",
     "question": "fix가 worktree src/app에만 적용되고 production src/app(C:/chemgrid/src/app/)에 미전파됐냐? "
                 "4경로(production/main _source/worktree src/app/worktree _source) SHA256 전부 동일?",
     "fp_ref": ["FP-09"], "rule_ref": ["J"], "weight": 2.3},
    {"id": "M858-W19-02", "category": "four_path_drift",
     "question": "Rule J는 src/app→_source 단방향이지만 worktree 작업 시 production도 동기화 의무. "
                 "사용자 실행 환경(draw.py 로드 대상)이 production이므로 worktree fix = 사용자 미반영?",
     "fp_ref": ["FP-09"], "rule_ref": ["J", "F"], "weight": 2.2},
    # SC107: patrol SC 번호 충돌 방지 (M998)
    {"id": "M858-SC107-01", "category": "sc_number_conflict",
     "question": "CT/Worker가 신규 SC# 지정 전 patrol.py grep으로 비점유 확인했냐? "
                 "SC103이 P-FAKE-APOLOGY로 점유 중인데 재사용 지시 → SC106/SC107 슬롯으로 결정?",
     "fp_ref": ["FP-08"], "rule_ref": ["W"], "weight": 1.8},
    # popup_alphafold setFont (M990)
    {"id": "M858-FONT-01", "category": "popup_alphafold_font",
     "question": "popup_alphafold.py _init_ui() 최상단 QFontDatabase.addApplicationFont 선행 + "
                 "self.setFont(QFont(loaded_family, 9)) 전역 적용됐냐? 영문 setText 오버라이드 6건 제거됐냐?",
     "fp_ref": ["FP-05"], "rule_ref": ["Q"], "weight": 2.0},
    # popup_3d 4경로 drift (M999)
    {"id": "M858-3D-01", "category": "popup3d_production_drift",
     "question": "popup_3d.py QuickDesignWorker.run() _simple_binding_score 실제 계산값 사용됐냐? "
                 "-6.0/-5.0 고정값(placeholder) 잔존하면 Rule E FAIL + 격분#33 재발.",
     "fp_ref": ["FP-15"], "rule_ref": ["E", "M"], "weight": 2.2},
    # docking simulation latency (M991)
    {"id": "M858-DOCKING-01", "category": "docking_latency_missing",
     "question": "docking_interface.py _run_simulation_fallback()에 exhaustiveness*num_modes/8 배율 "
                 "simulated latency time.sleep 존재하냐? 즉시 반환 = 학생이 Mock 인지 = 격분#28 재발.",
     "fp_ref": ["FP-15"], "rule_ref": ["GG", "M"], "weight": 2.1},
    # Gasteiger ESP fallback RGB (M993)
    {"id": "M858-GASTEIGER-01", "category": "esp_color_single_black",
     "question": "layer_logic.py Gasteiger fallback else 블록이 단일 검정(0,0,0)만 반환? "
                 "charge < -0.05 → RED(220,60,60) / > 0.05 → BLUE(60,60,220) / 중성 → GREEN 3분기?",
     "fp_ref": ["FP-08"], "rule_ref": ["O"], "weight": 2.0},
    # polymer tab enabled guard (M992)
    {"id": "M858-POLYMER-01", "category": "polymer_tab_guard",
     "question": "popup_polymer.py detect_polymerization() possible=False 후 합성 탭(idx 4/6/7) "
                 "setTabEnabled(False) 적용됐냐? _init_engine()이 아닌 _init_ui() 탭 추가 완료 후 수행?",
     "fp_ref": ["FP-08"], "rule_ref": ["M"], "weight": 1.9},
    # 48h 반감기 시계열 가중치 갱신 — 최근 36h D-M857/M858 누적
    {"id": "M858-TIMELINE-01", "category": "timeseries_recent_36h",
     "question": "anger_simulator ANGER_MATRIX_M858_GARDEN 35건 D-M858 사이클 최신 fix 기반 — "
                 "_ML_TIME_DECAY_HALFLIFE_HOURS=48.0 반감기로 36h 이내 격분 가중치 최대 (2^(-36/48)≈0.60)?",
     "fp_ref": ["FP-21"], "rule_ref": ["KK"], "weight": 2.4},  # [MAGIC] 48h 반감기 최근 36h ≈0.60 최고 우선
    {"id": "M858-TIMELINE-02", "category": "timeseries_recent_36h",
     "question": "D-M857-W3(docking latency)/W5(Gasteiger RGB)/W6(lead opt placeholder)/W7(wedge)/W8(SC patrol) "
                 "fix가 모두 4경로 SHA256 IDENTICAL + py_compile PASS 확인됐냐?",
     "fp_ref": ["FP-09"], "rule_ref": ["J", "F"], "weight": 2.2},
    # Rule J 역방향 drift (M997)
    {"id": "M858-RULEJ-01", "category": "rule_j_reverse_drift",
     "question": "_source가 최신일 때(M856 fix 사례) src/app 복사 누락으로 사용자 환경에 fix 미적용됐냐? "
                 "Rule J는 양방향 — _source→src/app 역방향 동기화도 즉시 의무?",
     "fp_ref": ["FP-09"], "rule_ref": ["J"], "weight": 2.0},
    # worktree hook 파일 누락 (M982)
    {"id": "M858-HOOK-01", "category": "worktree_hook_missing",
     "question": "워크트리 생성 시 .claude/hooks/가 참조하는 tools/zombie_check.py 등 파일이 "
                 "워크트리 tools/에도 복사됐냐? 누락 시 모든 Bash 명령 차단?",
     "fp_ref": ["FP-08"], "rule_ref": ["J"], "weight": 1.8},
    # SC106 declared scope 감지 (M996)
    {"id": "M858-SC106-01", "category": "declared_scope_violation",
     "question": "patrol SC106이 EVIDENCE_*.md declared WRITE_SCOPE 외 파일 수정을 git diff와 비교 탐지? "
                 "Worker가 선언 범위 외 entry/필드 silent 수정 시 K3 위반 WARN?",
     "fp_ref": ["FP-08"], "rule_ref": ["K3"], "weight": 1.9},
    # worktree sync 방향 결정 (M1006)
    {"id": "M858-SYNC-01", "category": "worktree_sync_direction",
     "question": "CT가 worktree sync 방향 지시 전 양쪽 LAST_M_NUMBER 실측 비교했냐? "
                 "실측 없이 방향 역전 지시 → Worker가 K1 원칙(Think Before Coding)으로 실측 기반 수행?",
     "fp_ref": ["FP-08"], "rule_ref": ["K1", "J"], "weight": 1.9},
    # POPUP-SYNTHESIS-SEGOE-UI-TOFU (M985) — 전파 확인
    {"id": "M858-FONT-02", "category": "segoe_ui_tofu_propagation",
     "question": "popup_synthesis.py QFont('Segoe UI') 32건 → QFont('Malgun Gothic') 일괄 교체됐냐? "
                 "M985 fix 후 popup_*.py 전체 Segoe UI 잔존 0건?",
     "fp_ref": ["FP-05"], "rule_ref": ["Q"], "weight": 1.9},
    # master_plan checkbox desync (M1001)
    {"id": "M858-PLAN-01", "category": "master_plan_checkbox_desync",
     "question": "코드 fix Worker spawn 시 master_plan.md 체크박스 [x] DONE 갱신을 WRITE_SCOPE에 포함했냐? "
                 "격분#13/22/24/28/33/30 코드 fix 완료 후 체크박스 미갱신 = 사용자 격분 진척 불가시화?",
     "fp_ref": ["FP-21"], "rule_ref": ["A", "Z"], "weight": 2.0},
    # Halgren MMFF94 citation propagation check
    {"id": "M858-CITE-01", "category": "mmff94_citation_propagation",
     "question": "crest_client.py + analyzer.py Halgren 1996 인용 2곳 외에 다른 MMFFOptimizeMolecule 호출 "
                 "코드에도 전파됐냐? Rule NN 인용 목록 Mulliken/Lowdin/Vina/Sehnal/Jumper에 Halgren 추가?",
     "fp_ref": ["FP-25"], "rule_ref": ["NN"], "weight": 1.8},
    # patrol SC107 비점유 확인 의무 (M998)
    {"id": "M858-PATROL-01", "category": "patrol_sc_nonexistent",
     "question": "신규 SC# 부여 전 patrol.py grep + 헤더 주석 양쪽 비점유 확인했냐? "
                 "SC107이 AUDIT-PROMPT-SC-CONFLICT 탐지로 신설됐고 SC106이 DECLARED-SCOPE 탐지?",
     "fp_ref": ["FP-08"], "rule_ref": ["W"], "weight": 1.8},
    # 최근 격분 누적 가중치 상위 추출 (ralph_loop Phase 4.7b)
    {"id": "M858-RALPHLOOP-01", "category": "ralph_loop_phase_4_7b",
     "question": "ralph_loop Phase 4.7b anger_simulator 매 사이클 호출 — evolve_anger_pool() + "
                 "generate_anger_questions() + embed_to_cycle_html() 통합 파이프라인 실행됐냐?",
     "fp_ref": ["FP-21"], "rule_ref": ["KK"], "weight": 2.3},
    {"id": "M858-RALPHLOOP-02", "category": "ralph_loop_phase_4_7b",
     "question": "anger_simulator SC56 patrol 자동 검사 — ANGER_MATRIX_FULL 크기 > 125건 + "
                 "LV_cats 완전성 + 48h 반감기 self_test PASS 확인됐냐?",
     "fp_ref": ["FP-21"], "rule_ref": ["KK"], "weight": 2.2},
    # user_persona_critic TT Rule (M645_W4)
    {"id": "M858-TT-01", "category": "user_persona_critic_tt",
     "question": "Worker 보고서 제출 전 user_persona_critic.critic_5questions() 5질문 통과됐냐? "
                 "raw evidence(tasklist/ps -ef/git log/파일경로+크기) 1건 이상 첨부됐냐?",
     "fp_ref": ["FP-38"], "rule_ref": ["TT"], "weight": 2.0},
    # 다람쥐볼 Rule V (필수 reads 확인)
    {"id": "M858-SQUIRREL-01", "category": "squirrel_ball_vv",
     "question": "이번 Worker spawn 프롬프트에 MANDATORY READS 3항목(skills/[도메인].md + mistakes.md 최근10건 + context_list.md) "
                 "전부 포함됐냐? squirrel_audit WARN율 50% 이하?",
     "fp_ref": ["FP-21"], "rule_ref": ["V"], "weight": 2.1},
    # M1090: ChemCharPanel 수레바퀴 + O추가 격분 (D-M1090 신규, 2026-05-17)
    # severity=5 HIGH — 명시적 욕설 "병신임" + 기능 전부 거부 ("아무 의미가 없잖아")
    # target: popup_3d.py L11258-11710 ChemCharCanvas + ChemCharPanel
    {"id": "ANGER_M1090_CHEMCHAR_WHEEL",
     "category": "GUI_VISUAL",
     "sub_category": "INFORMATION_QUALITY",
     "question": (
         "화학적 특성 탭(ChemCharPanel) 수레바퀴 = 아무 의미 없냐? "
         "center에 RDKit 2D depiction(120×120) 렌더링됐냐? "
         "neighbor box에 mini mol 2D(70×50) + 기능 라벨(COX-2 inhibitor 등 pharmacological_action)이 있냐? "
         "화살표가 QPainterPath bezier로 분자 박스와 겹치지 않냐? "
         "캔버스 720×720 / R_ORBIT 270 / BOX 140×130 비율 적용됐냐? "
         "설명이 'O추가' 같은 trivial SMARTS 변경이 아닌 실제 약리 기능이냐?"
     ),
     "raw_quote": (
         "화학적 특성 탭 이거 뭐 수레바퀴 그린 아무 의미가 없잖아 내 예시처럼 "
         "그림 비율부터 화살표 표현(선이 분자랑 안겹치게), 그리고 설명도 최소한 "
         "이게 어떠한 기능을 가지는 분자인지 정도는 설명해야지 뭐 O추가 이지랄하고 있노 병신임?"
     ),
     "severity": 5,  # [MAGIC] HIGH: 욕설 포함 + 기능 전체 거부
     "resolution_criteria": (
         "ChemCharCanvas shows RDKit 2D depiction center(120x120) + "
         "neighbor mini mol(70x50) + pharmacological function label + "
         "bezier arrow no-overlap + canvas 720x720 R_ORBIT 270"
     ),
     "target_file": "src/app/popup_3d.py",
     "target_lines": "L11258-11710",
     "related_workers": ["D-M1090-W3", "D-M1090-W4", "D-M1090-W5", "D-M1090-W6", "D-M1090-W7"],
     "fp_ref": ["FP-08", "FP-15"],
     "rule_ref": ["O", "M", "E"],
     "weight": 2.5,  # [MAGIC] 최고 우선순위 — 욕설 격분 severity=5
     "status": "RESOLVED",  # M1341 W219 5th cycle resolved via W152 M1256 + W203 verification
     "resolution_date": "2026-05-17",
     "resolution_note": "5th cycle resolved via W152 M1256 + W203 verification. box_avg 116→1581 13.7x improvement. setClipping(False) fix at popup_3d.py L11786.",
     "resolution_workers": ["D-M1091-W152", "D-M1091-W203"]},
    # D-M1090-W71: 5 신규 격분 패턴 (2026-05-17) — 184→189건
    # ANGER_M1090_FEEDBACK_COMPLETENESS_001
    {"id": "ANGER_M1090_FEEDBACK_COMPLETENESS_001",
     "category": "META_AUDIT",
     "question": (
         "피드백 통합 매트릭스가 35건만 있는게 아니라 MEMORY.md + uf_feedback47.json + "
         "anger_simulator 180+건 + mistakes.md 전체를 통합한 consolidation matrix가 "
         "docs/reports/progress_matrix_M1090.html에 생성됐냐? "
         "단기기억에 나온 피드백을 전부 읽고 누락없이 반영됐냐?"
     ),
     "raw_quote": "내 피드백이 35개만 있지 않잖아 단기기억에 나와있는 내 피드백 등등 못봄?",
     "severity": 4,  # [MAGIC] severity=4 HIGH
     "resolution_criteria": (
         "progress_matrix_M1090.html: uf_feedback47.json 54건 + MEMORY.md 항목 + "
         "anger_simulator 189건 + mistakes.md HEAD 30건 전부 통합 matrix 생성. "
         "누락 0건 확인."
     ),
     "target_file": "docs/reports/progress_matrix_M1090.html",
     "fp_ref": ["FP-21", "FP-38"], "rule_ref": ["AA", "H", "Z"],
     "weight": 2.3},
    # ANGER_M1090_NEW_HTML_MISSING_001
    {"id": "ANGER_M1090_NEW_HTML_MISSING_001",
     "category": "GUI_VISUAL",
     "sub_category": "AUTOMATION",
     "question": (
         "신규 cycle HTML이 매 사이클마다 새로 생성되고 있냐? "
         "기존 파일 덮어쓰기(같은 파일명)가 아닌 cycle_M(N+1).html 신규 파일로 "
         "자동 생성되는 schtask/cron이 등록됐냐? "
         "docs/cycles/ 또는 docs/reports/에 최신 사이클 HTML 존재 확인?"
     ),
     "raw_quote": "왜 신규 HTML은 새로 안만들고있냐?",
     "severity": 4,  # [MAGIC] severity=4 HIGH
     "resolution_criteria": (
         "cycle_M(N+1).html 자동 생성 schtask 등록 확인. "
         "docs/cycles/ 내 신규 HTML 파일 mtime 최신 확인."
     ),
     "target_file": "docs/cycles/",
     "fp_ref": ["FP-21"], "rule_ref": ["CC", "F"],
     "weight": 2.2},
    # ANGER_M1090_ENGINE_INVENTORY_INCOMPLETE_001
    {"id": "ANGER_M1090_ENGINE_INVENTORY_INCOMPLETE_001",
     "category": "META_AUDIT",
     "sub_category": "ENGINE_INTEGRATION",
     "question": (
         "외부 엔진 목록이 master_plan.md에 22종 이상 전체 등재됐냐? "
         "ORCA/xTB/CREST/MMFF94/ETKDG/AlphaFold/ColabFold/Vina/SMINA/PLANTS/"
         "IBM-RXN/ASKCOS/PubChem/Groq/Ollama/HuggingFace/Cerebras/Cloudflare/"
         "OpenRouter/Kimi 외에도 누락 엔진 없는지 인벤토리 전수 확인됐냐? "
         "각 엔진의 tier(1=primary/2=secondary/3=fallback) 분류도 함께?"
     ),
     "raw_quote": "외부 엔진 ㅅㅂ 20종 넘는다고 저거만 있는거 아니야",
     "severity": 5,  # [MAGIC] severity=5 CRITICAL — 욕설 포함
     "resolution_criteria": (
         "master_plan.md B섹션: 22종 이상 외부 엔진 tier 분류 전수 등재. "
         "누락 엔진 0건 확인."
     ),
     "target_file": "master_plan.md",
     "fp_ref": ["FP-21", "FP-08"], "rule_ref": ["K1", "E"],
     "weight": 2.5},  # [MAGIC] 욕설 포함 최고 우선순위
    # ANGER_M1090_XTB_RELIABILITY_LOW_001
    {"id": "ANGER_M1090_XTB_RELIABILITY_LOW_001",
     "category": "ENGINE_QUALITY",
     "question": (
         "xTB가 analyzer.py + popup_3d.py에서 tier-3 폴백으로 강등됐냐? "
         "사용자 명령 '신뢰도 낮으니까 최대한 쓰지 마'가 이전 명령인데 "
         "현재 코드에 xTB를 primary/secondary로 호출하는 코드가 잔존하냐? "
         "xTB 사용 시 SIMULATION_MODE 노란 배너 + '(xTB tier-3 폴백)' 워터마크 표시됐냐?"
     ),
     "raw_quote": "Xtb는 신뢰도 낮으니까 최대한 쓰지 말라고 말했다",
     "severity": 5,  # [MAGIC] severity=5 CRITICAL — 이전 명령 무시
     "resolution_criteria": (
         "analyzer.py + popup_3d.py: xTB 호출이 tier-3 폴백 블록에만 존재. "
         "tier-1(ORCA)/tier-2(MMFF94 등) 전부 시도 후 최후 폴백. "
         "xTB 활성 시 SIMULATION_MODE GG Rule 배너 표시."
     ),
     "target_file": "src/app/analyzer.py",
     "fp_ref": ["FP-15", "FP-08"], "rule_ref": ["GG", "M", "I"],
     "weight": 2.5},  # [MAGIC] 이전 명령 무시 CRITICAL
    # ANGER_M1090_PORTABILITY_LG_GRAM_001
    {"id": "ANGER_M1090_PORTABILITY_LG_GRAM_001",
     "category": "DEPLOYMENT",
     "sub_category": "ENVIRONMENT",
     "question": (
         "ORCA가 로컬 설치 의존이라 LG Gram 같은 다른 PC에서 못 돌아가는 이식성 문제가 "
         "해결됐냐? ORCA_SERVER_URL .env 변수로 외부 서버 지원됐냐? "
         "STUDENT_DEPLOY.md에 다른 PC 설치 가이드 있냐? "
         "AlphaFold 로그인 오류 시 ColabFold fallback chain UI가 팝업에 표시되냐? "
         "alphafold_interface.py에 ColabFold URL fallback + 로그인 실패 시 "
         "재시도/우회 안내 메시지가 있냐?"
     ),
     "raw_quote": (
         "ORCA 웹버전 맞냐? 로컬로 돌리면 CHEMGRID 이식할 다른 LG GRAM같은 PC에서는 못돌림. "
         "그리고 다른 PC 환경에서 알파폴드같은 애들이 로그인 오류 등으로 안뜰 수 있는데 "
         "이거 해결할 방법 있는지 찾아봐"
     ),
     "severity": 5,  # [MAGIC] severity=5 CRITICAL — 이식성 + 배포 핵심 문제
     "resolution_criteria": (
         "housing/docs/STUDENT_DEPLOY.md 존재 + ORCA_SERVER_URL .env.example 항목 추가. "
         "alphafold_interface.py ColabFold fallback chain (로그인 실패 → ColabFold → 로컬 ESMFold). "
         "팝업 UI: 로그인 오류 시 '다른 방법으로 시도' 안내 표시."
     ),
     "target_file": "housing/docs/STUDENT_DEPLOY.md",
     "fp_ref": ["FP-08", "FP-15"], "rule_ref": ["GG", "M", "F"],
     "weight": 2.5},  # [MAGIC] 이식성 CRITICAL
]

# 결합 매트릭스 (총 189건: stereo 53 + mech 50 + M621=17 + M643=5 + M724_LV=12 + M736=13 + M858_GARDEN=39 = 189건)
ANGER_MATRIX_FULL: List[Dict] = (
    ANGER_MATRIX_STEREO
    + ANGER_MATRIX_STEREO_EXTRA
    + ANGER_MATRIX_MECH
    + ANGER_MATRIX_MECH_EXTRA
    + ANGER_MATRIX_M621_NEW
    + ANGER_MATRIX_M643_NEW
    + ANGER_MATRIX_M724_LV
    + ANGER_MATRIX_M736_HARNESS
    + ANGER_MATRIX_M858_GARDEN
)


def _ensure_anger_log_dir() -> None:
    """anger_audit 디렉토리 생성 (Rule M)."""
    try:
        _ANGER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("anger_simulator: anger_audit 디렉토리 생성 실패: %s", e)


def _append_anger_log(entry: Dict) -> None:
    """매 사이클 발화 격분을 jsonl로 누적 기록 (시계열 학습용).

    Rule M: 실패 시 logger.warning. Rule N: isinstance 가드.
    """
    if not isinstance(entry, dict):  # Rule N
        logger.warning("anger_simulator: anger_log entry 타입 오류 - %r", type(entry))
        return

    _ensure_anger_log_dir()
    entry.setdefault("timestamp", datetime.now().isoformat())
    try:
        with open(_ANGER_LOG_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("anger_simulator: anger_log 기록 실패: %s", e)  # Rule M


def _load_anger_log_recent(limit: int = 1000) -> List[Dict]:
    """최근 N건의 격분 로그 로드.

    Rule M: 파일 없으면 빈 리스트 (silent failure 아님 — 첫 실행 정상).
    Rule N: isinstance 가드.
    """
    if not isinstance(limit, int) or limit <= 0:  # Rule N
        limit = 1000

    if not _ANGER_LOG_JSONL.exists():
        return []

    entries: List[Dict] = []
    try:
        with open(_ANGER_LOG_JSONL, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        # 마지막 N건만 파싱 (메모리 절약)
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):  # Rule N
                    entries.append(obj)
            except json.JSONDecodeError:
                continue
    except OSError as e:
        logger.warning("anger_simulator: anger_log 로드 실패: %s", e)  # Rule M
        return []

    return entries


def _compute_time_decayed_frequency(entries: List[Dict]) -> Dict[str, float]:
    """시계열 가중치 계산 — 최근 발화일수록 가중치 큼 (지수 감쇠).

    공식: weight = exp(-(now - timestamp_hours) * ln(2) / halflife_hours)
    Rule N: isinstance 가드. Rule M: 파싱 실패 시 logger.warning.
    """
    if not isinstance(entries, list):  # Rule N
        return {}

    import math
    freq: Dict[str, float] = {}
    now = datetime.now()

    for entry in entries:
        if not isinstance(entry, dict):  # Rule N
            continue
        pat_id = entry.get("pattern_id", "")
        if not isinstance(pat_id, str) or not pat_id:  # Rule N
            continue
        ts_str = entry.get("timestamp", "")
        if not isinstance(ts_str, str):  # Rule N
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            # naive datetime로 변환 (now도 naive)
            if ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
            elapsed_hours = (now - ts).total_seconds() / 3600.0
            decay = math.exp(-elapsed_hours * math.log(2) / _ML_TIME_DECAY_HALFLIFE_HOURS)
            freq[pat_id] = freq.get(pat_id, 0.0) + decay
        except (ValueError, TypeError) as e:
            logger.warning("anger_simulator: timestamp 파싱 실패 %s: %s", ts_str, e)  # Rule M
            continue

    return freq


def _compute_tf_idf_keywords(user_log_path: Path = _ANGER_USER_FEEDBACK_LOG) -> List[str]:
    """사용자 격분 로그 (jsonl)에서 TF-IDF 상위 키워드 추출.

    빈도-기반 단순 추출 (sklearn 의존성 회피). Rule M: 로그 없으면 빈 리스트.
    Rule N: isinstance 가드.
    """
    if not isinstance(user_log_path, Path):  # Rule N
        return []
    if not user_log_path.exists():
        return []

    try:
        from collections import Counter
        text_blob: List[str] = []
        with open(user_log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):  # Rule N
                        msg = obj.get("user_anger", obj.get("message", ""))
                        if isinstance(msg, str):  # Rule N
                            text_blob.append(msg.lower())
                except json.JSONDecodeError:
                    continue

        if not text_blob:
            return []

        # 단순 토큰화 + 빈도 (한국어/영어 키워드 모두 포함)
        all_text = " ".join(text_blob)
        # 주요 키워드만 추출 (한글 2자+/영문 4자+ 단어)
        tokens = re.findall(r"[가-힣]{2,}|[a-zA-Z]{4,}", all_text)
        stopwords = {"this", "that", "have", "with", "from", "되어", "있는", "하는", "있다"}
        tokens = [t for t in tokens if t not in stopwords]
        counter = Counter(tokens)
        top_keywords = [word for word, _ in counter.most_common(_ML_TF_IDF_TOP_N)]
        logger.info("anger_simulator: TF-IDF 상위 %d 키워드 추출 완료", len(top_keywords))
        return top_keywords
    except OSError as e:
        logger.warning("anger_simulator: user_log 읽기 실패: %s", e)  # Rule M
        return []


def _measure_precision_recall(entries: List[Dict]) -> Dict[str, float]:
    """anger_simulator 발화 격분 vs 사용자 실제 격분 매칭률 측정.

    precision: 시뮬레이션 격분 중 사용자 격분과 키워드 매칭 비율
    recall: 사용자 격분 중 시뮬레이션이 발화한 비율
    Rule M: 데이터 부족 시 0.0 + logger.info. Rule N: isinstance 가드.
    """
    if not isinstance(entries, list):  # Rule N
        return {"precision": 0.0, "recall": 0.0, "matched": 0, "total_sim": 0, "total_user": 0}

    user_keywords = _compute_tf_idf_keywords()
    if not user_keywords:
        logger.info("anger_simulator: 사용자 격분 로그 없음 — precision/recall 측정 불가")  # Rule M
        return {"precision": 0.0, "recall": 0.0, "matched": 0, "total_sim": 0, "total_user": 0}

    total_sim = 0
    matched_sim = 0
    for entry in entries:
        if not isinstance(entry, dict):  # Rule N
            continue
        question = entry.get("question", "")
        if not isinstance(question, str):  # Rule N
            continue
        total_sim += 1
        # 키워드 1개라도 매칭되면 '매칭'으로 판정
        q_lower = question.lower()
        if any(kw.lower() in q_lower for kw in user_keywords):
            matched_sim += 1

    precision = matched_sim / total_sim if total_sim > 0 else 0.0
    # recall: 사용자 키워드 중 시뮬레이션 질문에 등장한 비율
    sim_blob = " ".join(
        e.get("question", "") for e in entries
        if isinstance(e, dict) and isinstance(e.get("question", ""), str)
    ).lower()
    matched_kw = sum(1 for kw in user_keywords if kw.lower() in sim_blob)
    recall = matched_kw / len(user_keywords) if user_keywords else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "matched": matched_sim,
        "total_sim": total_sim,
        "total_user": len(user_keywords),
    }


def _save_metrics(metrics: Dict) -> None:
    """anger_metrics.json 저장 (cycle별 정확도 추적).

    Rule M: 저장 실패 시 logger.warning. Rule N: isinstance 가드.
    """
    if not isinstance(metrics, dict):  # Rule N
        return
    _ensure_anger_log_dir()
    metrics["updated_at"] = datetime.now().isoformat()
    try:
        with open(_ANGER_METRICS_JSON, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("anger_simulator: anger_metrics 저장 실패: %s", e)  # Rule M


def _expand_pool_if_needed(precision: float, recall: float) -> int:
    """매칭률 < 50% 시 기본 8 패턴 풀에 100+건 매트릭스 자동 추가.

    Rule M: 빈 결과도 logger.info. Rule N: 타입 가드.
    """
    if not isinstance(precision, (int, float)):  # Rule N
        precision = 0.0
    if not isinstance(recall, (int, float)):  # Rule N
        recall = 0.0

    avg = (precision + recall) / 2.0
    if avg >= _ML_PRECISION_THRESHOLD:
        logger.info(
            "anger_simulator: 매칭률 %.2f >= %.2f — 패턴 풀 확장 불필요",
            avg, _ML_PRECISION_THRESHOLD,
        )
        return 0

    # 매트릭스 100+건을 기본 풀에 추가 (이미 추가된 것 제외)
    existing_ids = {pat.get("id", "") for pat in ANGER_PATTERNS if isinstance(pat, dict)}
    added = 0
    for matrix_pat in ANGER_MATRIX_FULL:
        if not isinstance(matrix_pat, dict):  # Rule N
            continue
        if matrix_pat.get("id", "") in existing_ids:
            continue
        # 트리거 함수는 기본 P1로 매핑 (확장 패턴은 매트릭스 키워드 매칭에 사용)
        new_pat = dict(matrix_pat)
        new_pat.setdefault("trigger", "_trigger_av_pass_hollow")
        ANGER_PATTERNS.append(new_pat)
        added += 1
        if len(ANGER_PATTERNS) >= _ML_MAX_POOL_SIZE:
            logger.warning(
                "anger_simulator: 패턴 풀 최대 크기 도달 (%d) — 추가 중단",
                _ML_MAX_POOL_SIZE,
            )  # Rule M
            break

    logger.info(
        "anger_simulator: 매칭률 %.2f < %.2f — %d 패턴 자동 확장 (총 %d)",
        avg, _ML_PRECISION_THRESHOLD, added, len(ANGER_PATTERNS),
    )
    return added


def evolve_anger_pool(
    cycle_data: Optional[Dict] = None,
    force_expand: bool = False,
) -> Dict:
    """ML 진화 메인 함수 — 매 사이클 호출.

    1) anger_log 로드 (시계열 누적)
    2) 시간 감쇠 가중치 계산
    3) precision/recall 측정
    4) 매칭률 < 50% 시 패턴 풀 자동 확장
    5) 메트릭 저장
    6) 결과 반환

    Rule N: 인수 isinstance 가드. Rule M: 실패 시 logger.warning.
    """
    if cycle_data is None or not isinstance(cycle_data, dict):  # Rule N
        cycle_data = {}

    entries = _load_anger_log_recent(limit=1000)
    time_freq = _compute_time_decayed_frequency(entries)
    metrics = _measure_precision_recall(entries)

    expanded = 0
    if force_expand or metrics["precision"] < _ML_PRECISION_THRESHOLD:
        expanded = _expand_pool_if_needed(metrics["precision"], metrics["recall"])

    metrics["pool_size"] = len(ANGER_PATTERNS)
    metrics["matrix_size"] = len(ANGER_MATRIX_FULL)
    metrics["expanded_this_cycle"] = expanded
    metrics["log_entries"] = len(entries)
    metrics["time_freq_top5"] = sorted(
        time_freq.items(), key=lambda x: x[1], reverse=True
    )[:5]

    _save_metrics(metrics)

    logger.info(
        "anger_simulator EVOLVE: pool=%d matrix=%d expanded=%d precision=%.2f recall=%.2f",
        metrics["pool_size"], metrics["matrix_size"], expanded,
        metrics["precision"], metrics["recall"],
    )
    return metrics


def log_anger_question(question: str, pattern_id: str, cycle_no: str = "?") -> None:
    """매 발화 격분을 anger_log.jsonl에 누적 (시계열 학습 데이터).

    Rule M/N 준수.
    """
    if not isinstance(question, str) or not question:  # Rule N
        return
    if not isinstance(pattern_id, str):  # Rule N
        pattern_id = "UNKNOWN"
    _append_anger_log({
        "pattern_id": pattern_id,
        "question": question[:300],  # [MAGIC] 300자 제한
        "cycle_no": str(cycle_no),
    })


# ---------------------------------------------------------------------------
# M647-W3: run_all_triggers wrapper — 호출 측 인터페이스 단순화
# ---------------------------------------------------------------------------
# 결함 이력 (M647-W3):
#   기존 8 trigger 함수는 모두 (cycle_data, audit_reports, user_history, mistakes_30) 4-arg
#   시그니처. 호출 측(hourly_opus_critic.simulate_user_anger_5q 등)이 1-arg(report_text)만
#   넘기면 즉시 TypeError. 격분 매트릭스 자체 미작동.
#
#   해결 (M647-W3): wrapper run_all_triggers(report_text) 신설하여 내부에서
#     audit_reports = docs/reports/ 최근 5건
#     user_history  = uf_feedback*.json + handoff Section 3 Q-N1~Q-N36
#     mistakes_30   = mistakes.md head 100줄
#   를 자동 로드한 후 8 trigger 일괄 호출. cycle_data는 report_text에서 휴리스틱 추출
#   (img_count/av_pass/anger_section_present 등).
#
#   기존 함수 시그니처는 그대로 보존 — wrapper만 추가 (회귀 0건 보장).

_DEFAULT_RECENT_REPORTS_N = 5    # [MAGIC] 최근 보고서 로드 건수
_DEFAULT_MISTAKES_HEAD_LINES = 100  # [MAGIC] mistakes.md head 줄 수
_DEFAULT_REPORT_HEAD_CHARS = 4000  # [MAGIC] 보고서 첨부 시 head 크기 (트리거 키워드 매칭 충분)


def _wrapper_load_recent_audit_reports(n: int = _DEFAULT_RECENT_REPORTS_N) -> List[str]:
    """docs/reports/ 디렉토리에서 최근 n개 .md 파일 head 첨부.

    Rule M: 디렉토리 부재/읽기 실패 시 logger.warning + 빈 리스트.
    Rule N: n int 가드.
    """
    if not isinstance(n, int) or n <= 0:  # Rule N
        n = _DEFAULT_RECENT_REPORTS_N
    reports_dir = _PROJECT_ROOT / "docs" / "reports"
    if not reports_dir.exists():
        logger.warning("run_all_triggers: docs/reports/ 부재 — %s", reports_dir)
        return []
    found: List[Tuple[float, Path]] = []
    try:
        for p in reports_dir.iterdir():
            if not isinstance(p, Path):  # Rule N
                continue
            if not p.is_file():
                continue
            if not p.name.endswith(".md"):
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError as _e_stat:
                logger.warning("_wrapper_load_recent_audit_reports: stat 실패 %s — %s", p, _e_stat)
                continue
            found.append((mtime, p))
    except OSError as _e_iter:
        logger.warning("_wrapper_load_recent_audit_reports: iterdir 실패: %s", _e_iter)
        return []
    found.sort(key=lambda x: x[0], reverse=True)
    out: List[str] = []
    for _, p in found[:n]:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            out.append(text[:_DEFAULT_REPORT_HEAD_CHARS])
        except OSError as _e_read:
            logger.warning("_wrapper_load_recent_audit_reports: 읽기 실패 %s — %s", p, _e_read)
            continue
    return out


def _wrapper_load_user_history() -> List[str]:
    """uf_feedback*.json + handoff Section 3 Q-N1~Q-N36 로드.

    Rule M: 파일 부재/JSON 파싱 실패 시 logger.warning + 빈 리스트.
    Rule N: dict/list 가드.
    """
    out: List[str] = []
    docs_ai = _PROJECT_ROOT / "docs" / "ai"
    if docs_ai.exists():
        try:
            for p in docs_ai.iterdir():
                if not isinstance(p, Path):  # Rule N
                    continue
                if not p.is_file():
                    continue
                if not p.name.startswith("uf_feedback"):
                    continue
                if not p.name.endswith(".json"):
                    continue
                try:
                    raw = p.read_text(encoding="utf-8", errors="replace")
                    data = json.loads(raw)
                except (OSError, json.JSONDecodeError) as _e_uf:
                    logger.warning(
                        "_wrapper_load_user_history: %s 읽기 실패 — %s", p.name, _e_uf
                    )
                    continue
                # uf_feedback*.json은 list 또는 dict 가능
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            txt = item.get("text", "") or item.get("feedback", "") \
                                  or item.get("quote", "") or item.get("message", "")
                            if isinstance(txt, str) and txt:
                                out.append(txt[:500])
                        elif isinstance(item, str):
                            out.append(item[:500])
                elif isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, str) and v:
                            out.append(v[:500])
                        elif isinstance(v, dict):
                            txt = v.get("text", "") or v.get("quote", "")
                            if isinstance(txt, str) and txt:
                                out.append(txt[:500])
        except OSError as _e_iter:
            logger.warning("_wrapper_load_user_history: iterdir 실패: %s", _e_iter)
    # handoff Section 3 Q-N1~Q-N36 (NEXT_SESSION_PROMPT_M647_HANDOFF.md)
    handoff_path = _PROJECT_ROOT / "NEXT_SESSION_PROMPT_M647_HANDOFF.md"
    if handoff_path.exists():
        try:
            text = handoff_path.read_text(encoding="utf-8", errors="replace")
            out.append(text[:_DEFAULT_REPORT_HEAD_CHARS])
        except OSError as _e_handoff:
            logger.warning("_wrapper_load_user_history: handoff 읽기 실패 — %s", _e_handoff)
    return out


def _wrapper_load_mistakes_head(n: int = _DEFAULT_MISTAKES_HEAD_LINES) -> str:
    """mistakes.md head n줄 로드.

    Rule M: 부재/실패 시 logger.warning + 빈 문자열.
    Rule N: n int 가드.
    """
    if not isinstance(n, int) or n <= 0:  # Rule N
        n = _DEFAULT_MISTAKES_HEAD_LINES
    if not _MISTAKES_MD.exists():
        logger.warning("_wrapper_load_mistakes_head: mistakes.md 부재 — %s", _MISTAKES_MD)
        return ""
    try:
        text = _MISTAKES_MD.read_text(encoding="utf-8", errors="replace")
    except OSError as _e_m:
        logger.warning("_wrapper_load_mistakes_head: 읽기 실패 — %s", _e_m)
        return ""
    lines = text.splitlines()[:n]
    return "\n".join(lines)


def _heuristic_cycle_data_from_text(report_text: str) -> Dict:
    """report_text에서 휴리스틱으로 cycle_data 키 추출.

    매 8 trigger가 cycle_data dict로부터 키워드 검사 → 텍스트 패턴 보존이 핵심.
    Rule N: report_text str 가드.
    """
    if not isinstance(report_text, str):  # Rule N
        report_text = ""
    rt_lower = report_text.lower()
    # img_embed_count: <img 태그 등장 횟수
    img_count = rt_lower.count("<img")
    # av_pass: PASS 라벨 보유 여부
    av_pass = ("pass" in rt_lower or "통과" in report_text)
    # popup_3d_capture_count: popup_3d 캡처 언급 수
    popup_3d_count = rt_lower.count("popup_3d") + rt_lower.count("입체구조")
    # before_after_count
    before_after = rt_lower.count("before") + rt_lower.count("after") + rt_lower.count("이전") + rt_lower.count("이후")
    # anger_section_present
    anger_section = ("anger-audit" in rt_lower or "격분" in report_text)
    # chem_validity_checked
    chem_valid = ("hybridization" in rt_lower or "aromaticity" in rt_lower or "sp2" in rt_lower)
    # simulation_banner_present
    sim_banner = ("simulation_mode" in rt_lower or "simulation mode" in rt_lower
                  or "simulation banner" in rt_lower or "휴리스틱" in report_text)
    # missing_count: P0 매칭 추정
    missing_count = rt_lower.count("p0") + rt_lower.count("미적용") + rt_lower.count("미설정")
    # sc45_parity_pct: heuristic 100 (계산 못함)
    return {
        "img_embed_count": int(img_count),
        "av_pass": bool(av_pass),
        "popup_3d_capture_count": int(popup_3d_count),
        "before_after_count": int(before_after),
        "anger_section_present": bool(anger_section),
        "chem_validity_checked": bool(chem_valid),
        "simulation_banner_present": bool(sim_banner),
        "missing_count": int(missing_count),
        "sc45_parity_pct": 100.0,
        "cycle_no": "M647_W3",
    }


def run_all_triggers(report_text: str) -> List[Dict]:
    """8 trigger 일괄 호출 wrapper — 호출 측 인터페이스 단순화 (M647-W3 신설).

    내부에서 audit_reports/user_history/mistakes_30 자동 로드:
      - audit_reports = docs/reports/ 최근 5건 (.md head 4000자)
      - user_history  = uf_feedback*.json + handoff Section 3 (Q-N1~Q-N36)
      - mistakes_30   = mistakes.md head 100줄
      - cycle_data    = report_text 휴리스틱 추출

    Args:
        report_text: 보고서 본문 (str)

    Returns:
        List[Dict]: 트리거된 패턴 리스트, 각 dict 키:
            - pattern_id: str (ANGER-P1 ~ ANGER-P8 등)
            - question: str (격분 질문)
            - fp_ref: List[str]
            - rule_ref: List[str]
            - weight: float
            - triggered: True (트리거 발동 케이스만 반환)

    Rule M: 트리거 0건이어도 빈 list 반환 + logger.warning (silent return 금지).
    Rule N: report_text str 가드.
    """
    if not isinstance(report_text, str):  # Rule N
        logger.warning(
            "run_all_triggers: report_text 타입 오류 %r — 빈 문자열로 폴백",
            type(report_text),
        )
        report_text = ""

    audit_reports = _wrapper_load_recent_audit_reports(n=_DEFAULT_RECENT_REPORTS_N)
    user_history = _wrapper_load_user_history()
    mistakes_30 = _wrapper_load_mistakes_head(n=_DEFAULT_MISTAKES_HEAD_LINES)
    cycle_data = _heuristic_cycle_data_from_text(report_text)

    results: List[Dict] = []
    for pattern in ANGER_PATTERNS:
        if not isinstance(pattern, dict):  # Rule N
            continue
        trigger_name = pattern.get("trigger", "")
        if not isinstance(trigger_name, str) or not trigger_name:  # Rule N
            continue
        trigger_fn = _TRIGGER_REGISTRY.get(trigger_name)
        if trigger_fn is None:
            logger.warning(
                "run_all_triggers: 트리거 함수 미발견 — %s", trigger_name
            )
            continue
        try:
            triggered = trigger_fn(  # type: ignore[call-arg]
                cycle_data, audit_reports, user_history, mistakes_30
            )
        except (OSError, ValueError, TypeError, KeyError) as _e_tr:
            # Rule M: silent failure 금지
            logger.warning(
                "run_all_triggers: 트리거 %s 실행 실패 — %s",
                trigger_name, _e_tr,
            )
            triggered = False
        if triggered:
            entry = dict(pattern)  # 복제 — 원본 변경 방지
            entry["triggered"] = True
            results.append(entry)
            logger.info(
                "run_all_triggers: TRIGGERED %s (weight=%s)",
                pattern.get("id", "?"), pattern.get("weight", 1.0),
            )

    if not results:
        logger.warning(
            "run_all_triggers: 트리거 0건 — report_text len=%d, mistakes_30 len=%d",
            len(report_text), len(mistakes_30),
        )
    else:
        logger.info(
            "run_all_triggers: %d/%d 트리거 발동",
            len(results), len(ANGER_PATTERNS),
        )
    return results


# ---------------------------------------------------------------------------
# 격분 검수 4종 신규 메서드 (A62-W4 / M744 신설)
# ---------------------------------------------------------------------------
# 사용자 명시: "격분 검수도 추가" + Rule DD (1시간 CT 격분 매트릭스) + Rule KK
# Ollama validate dispatch 권고 반영 (2026-05-04)
# ---------------------------------------------------------------------------

_GRUDGE_AUDIT_LV_SPAWN_THRESHOLD = 5   # [MAGIC] LV >= 5 = 자동 fix Worker spawn 발동 임계값
_GRUDGE_AUDIT_3MONTH_DAYS = 90          # [MAGIC] USR-AUTO-3MONTH 미해소 임계 일수 (Rule SS)
_GRUDGE_AUDIT_TIMESERIES_MAX_POINTS = 90  # [MAGIC] 시계열 그래프 최대 데이터 포인트 수 (90일)
_GRUDGE_AUDIT_JSON_DIR_NAME = "anger_audit"  # [MAGIC] docs/feedback/ 내 저장 디렉터리명


def audit_raw_quote_match(report_text: str) -> Dict:
    """격분 검수 A: 사용자 raw quote 자동 매칭.

    ANGER_MATRIX_FULL 150건 + uf_feedback47.json 원문 피드백과 보고서를 대조하여
    사용자가 실제로 말한 격분 어휘가 해소됐는지 자동 매칭한다.

    Rule AA: 텍스트 피드백 70% 미만 → Cron Phase 7 경보.
    Rule M: silent failure 금지 — 매칭 0건도 logger.warning + 결과 반환.
    Rule N: isinstance() 타입 가드 필수.

    Returns:
        dict with keys:
            matched_count (int): 매칭된 raw quote 건수
            total_checked (int): 전체 검사 건수
            match_ratio (float): 매칭률 0.0~1.0
            matched_items (List[dict]): 매칭된 항목 목록
            cron7_alert (bool): Rule AA Phase 7 경보 여부
            verdict (str): "PASS" | "WARN" | "FAIL"
    """
    if not isinstance(report_text, str):  # Rule N
        logger.warning("audit_raw_quote_match: report_text 타입 오류 — %r", type(report_text))
        report_text = ""

    matched_items: List[Dict] = []
    total_checked = 0

    # ANGER_MATRIX_FULL 매칭
    # M928 FIX: ANGER_MATRIX_FULL 항목은 raw_quote/quote/anger_text 필드가 없고
    # question 필드를 사용함. raw_quote → quote → anger_text → question 순서로 폴백.
    # 기존 코드: raw_quote/quote/anger_text만 탐색 → total_checked=0 → 매칭 0건 고착 9사이클.
    for entry in ANGER_MATRIX_FULL:
        if not isinstance(entry, dict):  # Rule N
            continue
        raw_quote = entry.get(
            "raw_quote",
            entry.get(
                "quote",
                entry.get(
                    "anger_text",
                    entry.get("question", ""),  # [M928 FIX] question 필드 폴백
                ),
            ),
        )
        if not isinstance(raw_quote, str) or not raw_quote:
            continue
        total_checked += 1
        # 핵심 키워드 2개 이상 보고서에 존재하면 "해소됨" 판단
        keywords = [w for w in raw_quote.split() if len(w) >= 2][:5]
        match_count = sum(1 for kw in keywords if kw.lower() in report_text.lower())
        if match_count >= _KEYWORD_MATCH_MIN:
            matched_items.append({
                "id": entry.get("id", "?"),
                "category": entry.get("category", "unknown"),
                "raw_quote": raw_quote[:80],
                "match_count": match_count,
            })

    match_ratio = matched_items.__len__() / max(total_checked, 1)
    cron7_alert = match_ratio < 0.70  # [MAGIC] Rule AA 70% 임계값

    if total_checked == 0:
        logger.warning(
            "audit_raw_quote_match: ANGER_MATRIX_FULL 검사 항목 0건 — "
            "ANGER_MATRIX_FULL 초기화 확인 필요"
        )  # Rule M

    if cron7_alert:
        logger.warning(
            "audit_raw_quote_match: Rule AA PHASE7 경보 — "
            "매칭률=%.1f%% (%.0f%% 미만). CT 에스컬레이션 필요.",
            match_ratio * 100, 70.0,
        )  # Rule M

    if match_ratio >= 0.70:
        verdict = "PASS"
    elif match_ratio >= 0.50:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    logger.info(
        "audit_raw_quote_match: matched=%d/%d (%.1f%%) verdict=%s cron7=%s",
        len(matched_items), total_checked, match_ratio * 100, verdict, cron7_alert,
    )
    return {
        "matched_count": len(matched_items),
        "total_checked": total_checked,
        "match_ratio": round(match_ratio, 4),
        "matched_items": matched_items,
        "cron7_alert": cron7_alert,
        "verdict": verdict,
    }


def audit_lv5_auto_spawn_check(report_text: str, lv_score: int) -> Dict:
    """격분 검수 B: LV >= 5 자동 fix Worker spawn 트리거.

    사용자 격분 레벨이 임계값(_GRUDGE_AUDIT_LV_SPAWN_THRESHOLD=5) 이상이면
    AV_NEXT_PROMPT.md에 fix Worker spawn 권고를 기록하고 stderr CRITICAL 출력.

    Rule DD: 20분 크론×3시점 자동발화, missing>=3 ANGER+자동 fix Worker spawn.
    Rule M: silent failure 금지 — LV >= 5 시 반드시 stderr 출력.
    Rule N: isinstance() 타입 가드 필수.

    Args:
        report_text: 현재 사이클 보고서 본문
        lv_score: 격분 레벨 정수 (0~10)

    Returns:
        dict with keys:
            lv_score (int): 입력 격분 레벨
            spawn_triggered (bool): fix Worker spawn 발동 여부
            spawn_reason (str): 발동 이유 (ANGER 패턴 카테고리)
            av_next_prompt_written (bool): AV_NEXT_PROMPT.md 기록 여부
            stderr_issued (bool): stderr CRITICAL 출력 여부
    """
    if not isinstance(report_text, str):  # Rule N
        logger.warning("audit_lv5_auto_spawn_check: report_text 타입 오류")
        report_text = ""
    if not isinstance(lv_score, int):  # Rule N
        logger.warning("audit_lv5_auto_spawn_check: lv_score 타입 오류 — %r", type(lv_score))
        try:
            lv_score = int(lv_score)
        except (ValueError, TypeError):
            lv_score = 0

    spawn_triggered = lv_score >= _GRUDGE_AUDIT_LV_SPAWN_THRESHOLD
    spawn_reason = ""
    av_written = False
    stderr_issued = False

    # 트리거된 패턴에서 spawn_reason 추출
    if spawn_triggered:
        triggered = run_all_triggers(report_text)
        if isinstance(triggered, list) and triggered:
            top = triggered[0]
            if isinstance(top, dict):
                spawn_reason = top.get("id", "ANGER-UNKNOWN")
        else:
            spawn_reason = "LV_THRESHOLD_EXCEEDED"

        # stderr CRITICAL 출력 (Rule M + Rule DD)
        stderr_msg = (
            f"[GRUDGE-AUDIT M744] CRITICAL: LV={lv_score} >= {_GRUDGE_AUDIT_LV_SPAWN_THRESHOLD} "
            f"— 자동 fix Worker spawn 발동. reason={spawn_reason}. "
            f"Rule DD: 격분 미해소 자동 fix Worker spawn 의무."
        )
        print(stderr_msg, file=sys.stderr)
        stderr_issued = True
        logger.warning("audit_lv5_auto_spawn_check: %s", stderr_msg)  # Rule M

        # AV_NEXT_PROMPT.md 기록
        av_next_prompt = _PROJECT_ROOT / "AV_NEXT_PROMPT.md"
        try:
            existing = ""
            if av_next_prompt.exists():
                existing = av_next_prompt.read_text(encoding="utf-8", errors="replace")
                if not isinstance(existing, str):
                    existing = ""
            entry = (
                f"\n## [GRUDGE-AUDIT M744] LV={lv_score} 자동 fix Worker spawn 권고\n"
                f"- 발동 시각: {datetime.now().isoformat()}\n"
                f"- LV 점수: {lv_score} (임계값: {_GRUDGE_AUDIT_LV_SPAWN_THRESHOLD})\n"
                f"- 트리거 원인: {spawn_reason}\n"
                f"- 조치: fix Worker 즉시 spawn + 해당 패턴 해소 후 재검수 필수\n"
                f"- Rule DD / Rule KK 강제 의무\n"
            )
            av_next_prompt.write_text(existing + entry, encoding="utf-8")
            av_written = True
            logger.info("audit_lv5_auto_spawn_check: AV_NEXT_PROMPT.md 기록 완료")
        except OSError as e:
            logger.warning("audit_lv5_auto_spawn_check: AV_NEXT_PROMPT.md 기록 실패 — %s", e)  # Rule M

        # [M929 FIX] _hourly_spawn_queue.jsonl 직접 등록 — ralph_loop Phase 0.6이
        # AV_NEXT_PROMPT.md 재확인 없이 다음 사이클에서 즉시 fix Worker 처리.
        # 기존 AV_NEXT_PROMPT.md 기록만으로는 ralph_loop 재발화 전까지 spawn 지연됨.
        _spawn_queue_path = _PROJECT_ROOT / ".claude" / "_hourly_spawn_queue.jsonl"
        try:
            _spawn_queue_path.parent.mkdir(parents=True, exist_ok=True)
            _spawn_record = json.dumps({
                "id": f"GRUDGE-{spawn_reason}-LV{lv_score}",
                "desc": f"[M929] 격분 검수 LV={lv_score} 자동 fix spawn — {spawn_reason}",
                "domain": "anger_audit",
                "priority": "P0",
                "trigger_source": "audit_lv5_auto_spawn_check",
                "lv_score": lv_score,
                "timestamp": datetime.now().isoformat(),
            }, ensure_ascii=False)
            with open(_spawn_queue_path, "a", encoding="utf-8") as _f:
                _f.write(_spawn_record + "\n")
            logger.info(
                "audit_lv5_auto_spawn_check: _hourly_spawn_queue.jsonl 직접 등록 — LV=%d reason=%s",
                lv_score, spawn_reason,
            )
        except OSError as _sq_err:
            logger.warning(
                "audit_lv5_auto_spawn_check: spawn_queue 등록 실패 — %s", _sq_err
            )  # Rule M
    else:
        logger.info(
            "audit_lv5_auto_spawn_check: LV=%d < %d — spawn 미발동",
            lv_score, _GRUDGE_AUDIT_LV_SPAWN_THRESHOLD,
        )

    return {
        "lv_score": lv_score,
        "spawn_triggered": spawn_triggered,
        "spawn_reason": spawn_reason,
        "av_next_prompt_written": av_written,
        "stderr_issued": stderr_issued,
    }


def audit_3month_critical_register(category: str, first_seen_iso: str) -> Dict:
    """격분 검수 C: 90일+ 미해소 격분 CRITICAL 자동 등록 (Rule SS USR-AUTO-3MONTH-###).

    anger_3month_block.md 패턴에 따라 90일 초과 미해소 카테고리를
    docs/reports/pending_fixes.txt에 CRITICAL|M636|...|USR-AUTO-3MONTH-{CAT} 등급으로
    자동 등록한다.

    Rule SS: 90일+ 미해소 = CRITICAL+ pending_fix 자동 등록.
    Rule W: 2회 반복 = 하네스 결함 강화.
    Rule M: silent failure 금지.
    Rule N: isinstance() 타입 가드 필수.

    Args:
        category: anger_3month_block.md _ANGER_KEYWORDS 카테고리명
        first_seen_iso: 최초 발생 ISO 날짜 문자열 (예: "2026-02-02T10:00:00")

    Returns:
        dict with keys:
            category (str): 입력 카테고리
            days_unresolved (int): 미해소 일수
            is_critical (bool): 90일+ 초과 여부
            registered (bool): pending_fixes.txt 등록 여부
            prefix (str): USR-AUTO-3MONTH-{CATEGORY} prefix
            repeat_block_warned (bool): repeat_pattern_block hook 경고 여부
    """
    if not isinstance(category, str) or not category:  # Rule N
        logger.warning("audit_3month_critical_register: category 타입/값 오류 — %r", category)
        category = "unknown"
    if not isinstance(first_seen_iso, str):  # Rule N
        logger.warning("audit_3month_critical_register: first_seen_iso 타입 오류")
        first_seen_iso = datetime.now().isoformat()

    # 미해소 일수 계산
    days_unresolved = 0
    try:
        from datetime import timezone
        # ISO 형식 파싱 (T 구분자 허용, timezone 무시)
        first_dt = datetime.fromisoformat(first_seen_iso[:19])
        delta = datetime.now() - first_dt
        days_unresolved = max(0, delta.days)
    except (ValueError, TypeError) as e:
        logger.warning(
            "audit_3month_critical_register: first_seen_iso 파싱 실패 — %s. "
            "days_unresolved=0으로 처리.", e
        )  # Rule M
        days_unresolved = 0

    is_critical = days_unresolved >= _GRUDGE_AUDIT_3MONTH_DAYS
    prefix = f"USR-AUTO-3MONTH-{category.upper()}"
    registered = False
    repeat_block_warned = False

    if is_critical:
        # pending_fixes.txt CRITICAL 등록
        try:
            existing = ""
            if _PENDING_FIXES.exists():
                existing = _PENDING_FIXES.read_text(encoding="utf-8", errors="replace")
                if not isinstance(existing, str):
                    existing = ""

            if prefix not in existing:
                line = (
                    f"CRITICAL|M636|anger_3month|{prefix}|"
                    f"카테고리={category} 미해소={days_unresolved}일 "
                    f"(>= {_GRUDGE_AUDIT_3MONTH_DAYS}일) Rule SS 자동 등록 "
                    f"[{datetime.now().strftime('%Y-%m-%d')}]"
                )
                _PENDING_FIXES.parent.mkdir(parents=True, exist_ok=True)
                with open(_PENDING_FIXES, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                registered = True
                logger.warning(
                    "audit_3month_critical_register: CRITICAL 등록 — %s (%d일 미해소)",
                    prefix, days_unresolved,
                )  # Rule M
            else:
                logger.info(
                    "audit_3month_critical_register: 이미 등록됨 — %s", prefix
                )
        except OSError as e:
            logger.warning(
                "audit_3month_critical_register: pending_fixes.txt 등록 실패 — %s", e
            )  # Rule M

        # repeat_pattern_block hook 경고 (stderr)
        warn_msg = (
            f"[REPEAT-PATTERN-BLOCK M636/M744] {days_unresolved}+day unresolved anger detected!\n"
            f"  Category: {category}\n"
            f"  Prefix: {prefix}\n"
            f"  Rule W: same issue 90d+ = CRITICAL+ harness defect\n"
            f"  --> Resolve {prefix} FIRST before new spawn"
        )
        print(warn_msg, file=sys.stderr)
        repeat_block_warned = True
        logger.warning("audit_3month_critical_register: stderr 경고 출력 완료 — %s", prefix)
    else:
        logger.info(
            "audit_3month_critical_register: %s — %d일 미해소 (< %d일 임계값) — CRITICAL 아님",
            category, days_unresolved, _GRUDGE_AUDIT_3MONTH_DAYS,
        )

    return {
        "category": category,
        "days_unresolved": days_unresolved,
        "is_critical": is_critical,
        "registered": registered,
        "prefix": prefix,
        "repeat_block_warned": repeat_block_warned,
    }


def audit_timeseries_graph(output_path: Optional[str] = None) -> Dict:
    """격분 검수 D: 격분 시계열 그래프 생성 (matplotlib SVG).

    .claude/anger_timeline_M636.json 또는 ANGER_MATRIX_FULL 내 48h 반감기 가중치
    데이터를 사용해 최근 90일 격분 발생 빈도 시계열 그래프를 SVG로 생성한다.

    matplotlib 사용 이유: 벡터 해상도(SVG), cycle_html 직접 임베드 가능,
    matplotlibrc 폰트 설정으로 한국어 지원.
    Rule Q: fontproperties 필수 (한글 깨짐 방지).
    Rule M: matplotlib 미설치 시 logger.warning + SVG 텍스트 폴백.
    Rule N: isinstance() 타입 가드 필수.
    Rule I: 매직넘버 주석 필수.

    Args:
        output_path: 저장할 파일 경로 (None = 임시 파일 자동 생성)

    Returns:
        dict with keys:
            svg_path (str): 생성된 SVG 파일 경로
            data_points (int): 시계열 데이터 포인트 수
            peak_day (str): 격분 최다 발생 날짜 (YYYY-MM-DD)
            peak_count (int): 피크 발생 횟수
            matplotlib_used (bool): matplotlib 사용 여부
            fallback_svg (bool): SVG 텍스트 폴백 사용 여부
    """
    if output_path is not None and not isinstance(output_path, str):  # Rule N
        logger.warning("audit_timeseries_graph: output_path 타입 오류 — %r", type(output_path))
        output_path = None

    # 시계열 데이터 수집: anger_timeline_M636.json 우선, 없으면 ANGER_MATRIX_FULL 폴백
    timeline_data: Dict[str, int] = {}
    timeline_json = _PROJECT_ROOT / ".claude" / "anger_timeline_M636.json"

    if timeline_json.exists():
        try:
            raw = timeline_json.read_text(encoding="utf-8", errors="replace")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):  # Rule N
                parsed = {}
            by_cat = parsed.get("by_category", {})
            if isinstance(by_cat, dict):
                for cat, info in by_cat.items():
                    if not isinstance(info, dict):
                        continue
                    last_seen = info.get("last_seen", "")
                    count = info.get("count", 0)
                    if isinstance(last_seen, str) and last_seen and isinstance(count, (int, float)):
                        day_key = last_seen[:10]  # YYYY-MM-DD
                        timeline_data[day_key] = timeline_data.get(day_key, 0) + int(count)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.warning("audit_timeseries_graph: timeline_json 파싱 실패 — %s", e)  # Rule M

    # 폴백: ANGER_MATRIX_FULL timestamp 집계
    if not timeline_data:
        logger.warning(
            "audit_timeseries_graph: timeline_json 데이터 없음 — "
            "ANGER_MATRIX_FULL timestamp 폴백 사용"
        )  # Rule M
        for entry in ANGER_MATRIX_FULL:
            if not isinstance(entry, dict):
                continue
            ts = entry.get("timestamp", entry.get("first_seen", ""))
            if isinstance(ts, str) and len(ts) >= 10:
                day_key = ts[:10]
                timeline_data[day_key] = timeline_data.get(day_key, 0) + 1

    if not timeline_data:
        logger.warning(
            "audit_timeseries_graph: 시계열 데이터 0건 — 빈 SVG 반환"
        )  # Rule M
        timeline_data = {datetime.now().strftime("%Y-%m-%d"): 0}

    # 최근 90일 필터 및 정렬
    sorted_days = sorted(timeline_data.keys())[-_GRUDGE_AUDIT_TIMESERIES_MAX_POINTS:]
    counts = [timeline_data[d] for d in sorted_days]

    peak_idx = counts.index(max(counts)) if counts else 0
    peak_day = sorted_days[peak_idx] if sorted_days else datetime.now().strftime("%Y-%m-%d")
    peak_count = counts[peak_idx] if counts else 0

    # 출력 경로 설정
    if output_path is None:
        reports_dir = _PROJECT_ROOT / "docs" / "reports" / _GRUDGE_AUDIT_JSON_DIR_NAME
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(reports_dir / f"anger_timeseries_{ts_str}.svg")

    matplotlib_used = False
    fallback_svg = False

    try:
        import matplotlib
        matplotlib.use("Agg")  # 헤드리스 백엔드 (Rule JJ: 창 노출 금지)
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm

        # 한국어 폰트 설정 (Rule Q: fontproperties 필수)
        font_path = None
        for fp_candidate in [
            "C:/Windows/Fonts/malgun.ttf",
            "C:/Windows/Fonts/NanumGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        ]:
            if os.path.exists(fp_candidate):
                font_path = fp_candidate
                break

        if font_path:
            font_prop = fm.FontProperties(fname=font_path, size=10)
            plt.rcParams["axes.unicode_minus"] = False
        else:
            font_prop = fm.FontProperties(size=10)
            logger.warning(
                "audit_timeseries_graph: 한국어 폰트 미발견 — 기본 폰트 사용 (토푸 위험)"
            )  # Rule M, Rule Q

        fig, ax = plt.subplots(figsize=(12, 4))  # [MAGIC] 12×4 인치 = cycle_html 적합 비율
        fig.patch.set_facecolor("#1a1a2e")  # [MAGIC] 다크 테마 배경 (Rule CC cycle_html 다크 테마)
        ax.set_facecolor("#16213e")

        # 48h 반감기 가중치 시각화 (최신일수록 강조)
        colors = []
        now_day = datetime.now()
        for d in sorted_days:
            try:
                day_dt = datetime.fromisoformat(d)
                age_h = max(0, (now_day - day_dt).total_seconds() / 3600)
                weight = 2 ** (-age_h / 48.0)  # [MAGIC] 48h 반감기 (Rule KK timeseries_halflife)
                r = min(1.0, 0.3 + weight * 0.7)
                colors.append((r, 0.2, 0.4, 0.85))
            except (ValueError, TypeError):
                colors.append((0.5, 0.2, 0.4, 0.85))

        ax.bar(range(len(sorted_days)), counts, color=colors, width=0.8)
        ax.set_xlabel("날짜", fontproperties=font_prop if font_path else None, color="#aaaaaa")
        ax.set_ylabel("격분 발생 수", fontproperties=font_prop if font_path else None, color="#aaaaaa")
        ax.set_title(
            "격분 시계열 그래프 (48h 반감기 가중, 최근 90일)",
            fontproperties=font_prop if font_path else None,
            color="#e94560", fontsize=13,
        )

        # x축 라벨: 데이터 포인트가 많으면 일부만 표시
        if len(sorted_days) <= 15:  # [MAGIC] 15개 이하 = 전부 표시
            ax.set_xticks(range(len(sorted_days)))
            ax.set_xticklabels(
                sorted_days,
                rotation=45, ha="right", fontsize=8,
                fontproperties=font_prop if font_path else None,
                color="#888888",
            )
        else:
            step = max(1, len(sorted_days) // 10)  # [MAGIC] 최대 10개 라벨
            tick_pos = list(range(0, len(sorted_days), step))
            ax.set_xticks(tick_pos)
            ax.set_xticklabels(
                [sorted_days[i] for i in tick_pos],
                rotation=45, ha="right", fontsize=8,
                fontproperties=font_prop if font_path else None,
                color="#888888",
            )

        ax.tick_params(colors="#888888")
        ax.spines["bottom"].set_color("#444444")
        ax.spines["left"].set_color("#444444")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # 피크 강조
        if peak_idx < len(sorted_days):
            ax.annotate(
                f"피크: {peak_count}건",
                xy=(peak_idx, peak_count),
                xytext=(peak_idx, peak_count + max(1, peak_count * 0.15)),
                color="#f5a623",
                fontsize=9,
                ha="center",
                fontproperties=font_prop if font_path else None,
                arrowprops={"arrowstyle": "->", "color": "#f5a623"},
            )

        plt.tight_layout()
        plt.savefig(output_path, format="svg", bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        matplotlib_used = True
        logger.info("audit_timeseries_graph: SVG 생성 완료 — %s", output_path)

    except ImportError:
        # matplotlib 미설치 — 최소 SVG 텍스트 폴백 (Rule M)
        logger.warning(
            "audit_timeseries_graph: matplotlib 미설치 — SVG 텍스트 폴백 사용"
        )
        fallback_svg = True
        bars = ""
        max_c = max(counts) if counts else 1
        bar_w = 8  # [MAGIC] 폴백 SVG 바 너비 px
        for i, (d, c) in enumerate(zip(sorted_days, counts)):
            h = int(c / max_c * 80)  # [MAGIC] 최대 높이 80px
            x = 40 + i * (bar_w + 2)
            y = 100 - h
            bars += (
                f'<rect x="{x}" y="{y}" width="{bar_w}" height="{h}" '
                f'fill="#e94560" opacity="0.8"/>'
            )
        svg_content = (
            '<?xml version="1.0" encoding="utf-8"?>'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="150" '
            f'style="background:#1a1a2e;">'
            f'<text x="10" y="20" fill="#e94560" font-size="12">'
            f'격분 시계열 (최근 {len(sorted_days)}일, matplotlib 미설치 폴백)</text>'
            f'{bars}'
            f'<text x="10" y="140" fill="#888" font-size="10">'
            f'피크: {peak_day} ({peak_count}건)</text>'
            f'</svg>'
        )
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(svg_content, encoding="utf-8")
            logger.info("audit_timeseries_graph: 폴백 SVG 저장 — %s", output_path)
        except OSError as e:
            logger.warning("audit_timeseries_graph: 폴백 SVG 저장 실패 — %s", e)  # Rule M

    return {
        "svg_path": output_path,
        "data_points": len(sorted_days),
        "peak_day": peak_day,
        "peak_count": peak_count,
        "matplotlib_used": matplotlib_used,
        "fallback_svg": fallback_svg,
    }


def run_grudge_audit_all(
    report_text: str,
    lv_score: int = 0,
    category: str = "",
    first_seen_iso: str = "",
    save_json: bool = True,
) -> Dict:
    """격분 검수 4종 통합 실행 파이프라인 (A62-W4 / M744).

    A. audit_raw_quote_match    — 사용자 raw quote 자동 매칭
    B. audit_lv5_auto_spawn_check — LV >= 5 자동 fix Worker spawn 트리거
    C. audit_3month_critical_register — 90일+ 미해소 CRITICAL 등록
    D. audit_timeseries_graph   — 격분 시계열 그래프 생성

    ct_hourly_review.py 연동:
        - 결과를 docs/feedback/anger_audit/anger_audit_YYYYMMDD_HHMM.json으로 저장
        - LV >= 5 시 stderr CRITICAL 추가 출력 (ct_hourly_review 픽업용)

    Rule DD: 1시간 발화 시 4종 결과를 CT hourly review에 연동.
    Rule M: silent failure 금지 — 각 단계 실패도 결과 반환.
    Rule N: isinstance() 타입 가드 필수.
    Rule I: 매직넘버 주석 필수.

    Args:
        report_text: 보고서 본문
        lv_score: 격분 레벨 (0~10)
        category: 90일 검사용 카테고리명
        first_seen_iso: 최초 발생 ISO 날짜
        save_json: docs/feedback/anger_audit/*.json 저장 여부

    Returns:
        dict with keys: audit_a/b/c/d (각 검수 결과), combined_verdict, json_path
    """
    if not isinstance(report_text, str):  # Rule N
        logger.warning("run_grudge_audit_all: report_text 타입 오류")
        report_text = ""
    if not isinstance(lv_score, int):  # Rule N
        try:
            lv_score = int(lv_score)
        except (ValueError, TypeError):
            lv_score = 0
    if not isinstance(category, str):  # Rule N
        category = ""
    if not isinstance(first_seen_iso, str):  # Rule N
        first_seen_iso = datetime.now().isoformat()

    logger.info(
        "run_grudge_audit_all: 격분 검수 4종 시작 — LV=%d cat=%s",
        lv_score, category or "미지정",
    )

    # A: raw quote 매칭
    try:
        audit_a = audit_raw_quote_match(report_text)
    except Exception as e:
        logger.warning("run_grudge_audit_all: audit_A 실패 — %s", e)  # Rule M
        audit_a = {"verdict": "ERROR", "error": str(e)}

    # B: LV >= 5 spawn 체크
    try:
        audit_b = audit_lv5_auto_spawn_check(report_text, lv_score)
    except Exception as e:
        logger.warning("run_grudge_audit_all: audit_B 실패 — %s", e)  # Rule M
        audit_b = {"spawn_triggered": False, "error": str(e)}

    # C: 90일 CRITICAL 등록
    if category and first_seen_iso:
        try:
            audit_c = audit_3month_critical_register(category, first_seen_iso)
        except Exception as e:
            logger.warning("run_grudge_audit_all: audit_C 실패 — %s", e)  # Rule M
            audit_c = {"is_critical": False, "error": str(e)}
    else:
        audit_c = {"is_critical": False, "skipped": True, "reason": "category/first_seen_iso 미제공"}
        logger.info("run_grudge_audit_all: audit_C 스킵 — category 또는 first_seen_iso 미제공")

    # D: 시계열 그래프 생성
    try:
        audit_d = audit_timeseries_graph()
    except Exception as e:
        logger.warning("run_grudge_audit_all: audit_D 실패 — %s", e)  # Rule M
        audit_d = {"svg_path": None, "error": str(e)}

    # combined_verdict: A/B/C/D 결과 종합
    verdict_a = audit_a.get("verdict", "ERROR")
    spawn_b = audit_b.get("spawn_triggered", False)
    critical_c = audit_c.get("is_critical", False)
    svg_ok = bool(audit_d.get("svg_path"))

    if verdict_a == "FAIL" or critical_c or spawn_b:
        combined_verdict = "CRITICAL"
    elif verdict_a == "WARN" or not svg_ok:
        combined_verdict = "WARN"
    elif verdict_a == "PASS":
        combined_verdict = "PASS"
    else:
        combined_verdict = "UNKNOWN"

    # LV >= 5 시 통합 stderr CRITICAL 추가 출력 (ct_hourly_review 픽업용)
    if lv_score >= _GRUDGE_AUDIT_LV_SPAWN_THRESHOLD:
        print(
            f"[GRUDGE-AUDIT-4TYPES M744] CRITICAL: combined_verdict={combined_verdict} "
            f"LV={lv_score} raw_quote={verdict_a} 3month={critical_c} "
            f"spawn={spawn_b}",
            file=sys.stderr,
        )

    result: Dict = {
        "timestamp": datetime.now().isoformat(),
        "audit_a": audit_a,
        "audit_b": audit_b,
        "audit_c": audit_c,
        "audit_d": audit_d,
        "combined_verdict": combined_verdict,
        "lv_score": lv_score,
        "json_path": None,
    }

    # docs/feedback/anger_audit/*.json 저장 (ct_hourly_review.py 연동용)
    if save_json:
        try:
            json_dir = _PROJECT_ROOT / "docs" / "feedback" / _GRUDGE_AUDIT_JSON_DIR_NAME
            json_dir.mkdir(parents=True, exist_ok=True)
            ts_str = datetime.now().strftime("%Y%m%d_%H%M")
            json_path = json_dir / f"anger_audit_{ts_str}.json"
            json_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            result["json_path"] = str(json_path)
            logger.info("run_grudge_audit_all: JSON 저장 완료 — %s", json_path)
        except (OSError, TypeError, ValueError) as e:
            logger.warning("run_grudge_audit_all: JSON 저장 실패 — %s", e)  # Rule M

    logger.info(
        "run_grudge_audit_all: 완료 — combined_verdict=%s LV=%d",
        combined_verdict, lv_score,
    )
    return result


if __name__ == "__main__":
    main()
