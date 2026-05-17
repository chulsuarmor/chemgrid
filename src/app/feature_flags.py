# feature_flags.py — ChemGrid v1.0 Feature Enable/Disable Matrix
# Rule I: 매직넘버 없음. 모든 flag는 환경변수 CHEMGRID_ENABLE_<NAME>=1 로 오버라이드 가능.
# Rule M685: Cascade #10 미완 3블럭 (EI-MS Block4, Polymer-PDI Block5, Stability Block7)
# 비활성화 기준: 기능이 UI에 노출되어 있으나 학술적으로 미검증 or 구현 미완성

import os
import logging

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
# v1.0 완성 기능 (ENABLED)
# ────────────────────────────────────────────────────────────────────────────
FEATURES: dict[str, bool] = {
    # 핵심 분자 그리기 + 렌더링
    "DRAW_CANVAS": True,
    "LEWIS_LAYER": True,
    "THEORY_LAYER": True,
    "ESP_CLOUD": True,

    # 분광 분석 (자체 엔진 기반)
    "SPECTRUM_IR": True,
    "SPECTRUM_NMR": True,
    "SPECTRUM_UVVIS": True,
    "SPECTRUM_RAMAN": True,

    # 3D 뷰어 + 도킹
    "POPUP_3D": True,
    "DOCKING_SCORING": True,

    # 반응 메커니즘 + 합성
    "REACTION_POPUP": True,
    "SYNTHESIS_POPUP": True,
    "REACTION_ANIMATION": True,

    # 약물 설계
    "ADMET_PREDICTOR": True,
    "LEAD_OPTIMIZER": True,
    "DRUG_SCREENING": True,
    "ALPHAFOLD_POPUP": True,

    # DryLab 보고서 (PDF 출력)
    "DRYLAB_REPORT": True,

    # 고분자 분석 (PDI/Mn/Mw 포함 — popup_polymer.py 완성)
    "POLYMER_POPUP": True,

    # ────────────────────────────────────────────────────────────────────────
    # v1.0 제한 기능 (DISABLED — Cascade #10 미완)
    # M685: Block4 EI-MS 독립팝업 미완 (drylab PDF 내에는 포함됨)
    "SPECTRUM_EI_MS_STANDALONE": False,

    # M685: Block7 분자안정성(Stability) 탭 — popup_stability.py 미구현
    "STABILITY_ANALYSIS": False,

    # 실험적 기능 — 학술 검증 미완
    "MOLECULAR_DYNAMICS_FULL": False,  # popup_md.py 기본만 구현됨
}


def is_enabled(name: str) -> bool:
    """Return True if feature flag is enabled.

    환경변수 CHEMGRID_ENABLE_<NAME>=1 로 오버라이드 가능 (개발/테스트 전용).
    배포 빌드에서는 환경변수가 설정되지 않으므로 FEATURES dict 기본값이 사용됨.

    Rule M: False 반환 시 호출부에서 logger.warning 필수 — silent return 금지.
    """
    if not isinstance(name, str):
        logger.warning("[feature_flags.is_enabled] name is not str: %s", type(name))
        return False

    env_override = os.environ.get(f"CHEMGRID_ENABLE_{name.upper()}", "").strip()
    if env_override == "1":
        logger.warning("[feature_flags] 환경변수 오버라이드: %s=ENABLED", name)
        return True

    result = FEATURES.get(name, False)
    if not result:
        logger.warning("[feature_flags] 비활성화된 기능 접근: %s", name)
    return result


def get_disabled_features() -> list[str]:
    """Return list of disabled feature names (RELEASE_NOTES 생성용)."""
    return [k for k, v in FEATURES.items() if not v]
