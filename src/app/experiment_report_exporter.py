#!/usr/bin/env python3
"""
실험 보고서 PDF 내보내기 (Experiment Report PDF Exporter).

합성 경로(SynthesisRoute) + AI 분석 결과를 학생용 실험 보고서 양식으로
A4 세로(portrait) PDF 생성.

섹션 구성:
  1. 실험 목적 (auto-filled)
  2. 이론적 배경 (auto-filled)
  3. 실험 준비물 (auto-filled)
  4. 실험 방법/절차 (auto-filled)
  5. 주의사항 (auto-filled)
  6. 결과 및 관찰 (빈칸)
  7. 결과 분석 (빈칸 + 예측 스펙트럼)
  8. 고찰 (빈칸)

Dependencies:
    - reportlab (PDF generation)
    - rdkit (2D structure rendering)
    - PIL/Pillow (image conversion)
    - matplotlib (spectrum graphs)
"""

import io
import logging
import os
import tempfile
from datetime import datetime
from typing import List, Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# ── RDKit ──
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Draw, Descriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# ── reportlab ──
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
        PageBreak, Image as RLImage, KeepTogether, HRFlowable,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    # Fallback stubs for type hints
    ParagraphStyle = type('ParagraphStyle', (), {})
    getSampleStyleSheet = None
    SimpleDocTemplate = None
    Table = None
    TableStyle = None
    Paragraph = None
    Spacer = None
    PageBreak = None
    RLImage = None
    KeepTogether = None
    HRFlowable = None
    colors = None
    A4 = (595.27, 841.89)
    mm = 2.834645669
    cm = 28.346456693
    TA_CENTER = 1
    TA_LEFT = 0
    TA_JUSTIFY = 4
    pdfmetrics = None
    TTFont = None

# ── PIL ──
try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ── matplotlib ──
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# ── Project imports ──
from retrosynthesis_engine import SynthesisRoute, SynthesisStep
from building_blocks import get_building_block_info

# ═══════════════════════════════════════════════════════════
# 한글 폰트 등록
# ═══════════════════════════════════════════════════════════

_KOREAN_FONT_PATHS = [
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/System/Library/Fonts/AppleGothic.ttf",
]

_KOREAN_BOLD_PATHS = [
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/NanumGothicBold.ttf",
]

_FONT_REGISTERED = False
_FONT_NAME = "MalgunReport"
_FONT_BOLD_NAME = "MalgunReportBold"


def _register_fonts():
    """Register Korean fonts for reportlab."""
    global _FONT_REGISTERED
    if _FONT_REGISTERED or not REPORTLAB_AVAILABLE:
        return
    _FONT_REGISTERED = True

    # Regular font
    for fpath in _KOREAN_FONT_PATHS:
        if os.path.isfile(fpath):
            try:
                pdfmetrics.registerFont(TTFont(_FONT_NAME, fpath))
                break
            except Exception as e:
                logger.warning("Font registration failed for %s: %s", fpath, e)
                continue
    else:
        logger.warning("Korean regular font not found, using Helvetica")

    # Bold font
    for fpath in _KOREAN_BOLD_PATHS:
        if os.path.isfile(fpath):
            try:
                pdfmetrics.registerFont(TTFont(_FONT_BOLD_NAME, fpath))
                break
            except Exception as e:
                logger.warning("Bold font registration failed for %s: %s", fpath, e)
                continue
    else:
        # fallback: reuse regular as bold
        try:
            pdfmetrics.registerFont(TTFont(_FONT_BOLD_NAME, _KOREAN_FONT_PATHS[0]))
        except Exception as e:
            logger.warning("Failed to register bold font fallback: %s", e)


# ═══════════════════════════════════════════════════════════
# Helper: SMILES -> PNG bytes
# ═══════════════════════════════════════════════════════════

def _smiles_to_png_bytes(smiles: str, width: int = 250, height: int = 200) -> Optional[bytes]:
    """SMILES -> PNG image bytes via RDKit + PIL. Returns None on failure."""
    if not RDKIT_AVAILABLE or not PIL_AVAILABLE:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("SMILES 파싱 실패: %s", smiles)
            return None
        AllChem.Compute2DCoords(mol)
        img = Draw.MolToImage(mol, size=(width, height))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.debug("SMILES to PNG failed for %s: %s", smiles, e)
        return None


# ═══════════════════════════════════════════════════════════
# Helper: Predicted spectrum graph -> PNG bytes
# ═══════════════════════════════════════════════════════════

def _generate_ir_spectrum_png(smiles: str, width_inch: float = 6.0,
                               height_inch: float = 2.5) -> Optional[bytes]:
    """Generate a simplified predicted IR spectrum from functional groups."""
    if not MATPLOTLIB_AVAILABLE or not RDKIT_AVAILABLE:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("IR 스펙트럼 생성 실패 - SMILES 파싱 불가: %s", smiles)
            return None

        # Functional group -> characteristic IR peaks (cm-1, relative intensity, label)
        peaks: List[Tuple[float, float, str]] = []

        smarts_peaks = [
            ("[OH]", [(3300, 0.85, "O-H str")]),
            ("[NH2]", [(3400, 0.7, "N-H str")]),
            ("[NH]", [(3350, 0.6, "N-H str")]),
            ("C=O", [(1715, 0.95, "C=O str")]),
            ("C(=O)O", [(1710, 0.9, "C=O acid"), (2500, 0.4, "O-H acid broad")]),
            ("C(=O)N", [(1650, 0.85, "Amide C=O")]),
            ("C#N", [(2200, 0.6, "C#N str")]),
            ("C#C", [(2150, 0.5, "C#C str")]),
            ("c1ccccc1", [(3050, 0.4, "Ar C-H"), (1600, 0.5, "Ar C=C"),
                          (1500, 0.45, "Ar C=C")]),
            ("[C-H]", [(2950, 0.5, "C-H str")]),
        ]

        for smarts_str, peak_list in smarts_peaks:
            try:
                pat = Chem.MolFromSmarts(smarts_str)
                if pat and mol.HasSubstructMatch(pat):
                    peaks.extend(peak_list)
            except Exception as e:
                logger.warning("IR SMARTS 매칭 실패 (%s): %s", smarts_str, e)
                continue

        # Always add C-H stretch
        if not any(p[0] > 2900 and p[0] < 3100 for p in peaks):
            peaks.append((2950, 0.45, "C-H str"))

        if not peaks:
            return None

        fig, ax = plt.subplots(figsize=(width_inch, height_inch), dpi=150)
        import numpy as np
        x = np.linspace(400, 4000, 1000)
        y = np.ones_like(x) * 100.0  # transmittance baseline

        for freq, intensity, _label in peaks:
            # Lorentzian dip
            width = 40 + 20 * intensity
            dip = intensity * 100 * (width ** 2) / ((x - freq) ** 2 + width ** 2)
            y -= dip

        y = np.clip(y, 0, 100)
        ax.plot(x, y, color="black", linewidth=0.8)
        ax.set_xlim(4000, 400)
        ax.set_ylim(0, 105)
        ax.set_xlabel("Wavenumber (cm$^{-1}$)", fontsize=8)
        ax.set_ylabel("Transmittance (%)", fontsize=8)
        ax.set_title("Predicted IR Spectrum (reference)", fontsize=9)
        ax.tick_params(labelsize=7)

        # Annotate major peaks
        for freq, intensity, label in peaks:
            if intensity > 0.5:
                y_val = 100 - intensity * 80
                ax.annotate(f"{int(freq)}", xy=(freq, max(y_val, 5)),
                            fontsize=6, ha="center", va="bottom", color="red")

        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="PNG", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.debug("IR spectrum generation failed: %s", e)
        return None


def _generate_nmr_spectrum_png(smiles: str, width_inch: float = 6.0,
                                height_inch: float = 2.5) -> Optional[bytes]:
    """Generate a simplified predicted 1H NMR spectrum."""
    if not MATPLOTLIB_AVAILABLE or not RDKIT_AVAILABLE:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("NMR 스펙트럼 생성 실패 - SMILES 파싱 불가: %s", smiles)
            return None
        mol = Chem.AddHs(mol)

        import numpy as np

        # Simple chemical shift estimation by environment
        peaks: List[Tuple[float, float, str]] = []

        smarts_shifts = [
            ("[CH3]", 0.9, "CH3"),
            ("[CH2]", 1.3, "CH2"),
            ("[CH]([!#1])([!#1])[!#1]", 1.5, "CH"),
            ("C(=O)[CH3]", 2.1, "COCH3"),
            ("[OH]", 3.5, "OH"),
            ("O[CH3]", 3.3, "OCH3"),
            ("O[CH2]", 3.5, "OCH2"),
            ("[NH2]", 2.5, "NH2"),
            ("c[H]", 7.2, "Ar-H"),
            ("C(=O)O[H]", 11.0, "COOH"),
            ("[CH]=O", 9.7, "CHO"),
        ]

        mol_noH = Chem.RemoveHs(mol)
        for smarts_str, shift, label in smarts_shifts:
            try:
                pat = Chem.MolFromSmarts(smarts_str)
                if pat and mol_noH.HasSubstructMatch(pat):
                    matches = mol_noH.GetSubstructMatches(pat)
                    intensity = len(matches) * 0.5
                    peaks.append((shift, min(intensity, 3.0), label))
            except Exception as e:
                logger.warning("NMR SMARTS 매칭 실패 (%s): %s", smarts_str, e)
                continue

        if not peaks:
            peaks.append((1.0, 1.0, "CH"))

        fig, ax = plt.subplots(figsize=(width_inch, height_inch), dpi=150)
        x = np.linspace(-0.5, 13, 2000)
        y = np.zeros_like(x)

        for shift, intensity, _label in peaks:
            # Gaussian peaks
            sigma = 0.05
            y += intensity * np.exp(-((x - shift) ** 2) / (2 * sigma ** 2))

        ax.plot(x, y, color="black", linewidth=0.8)
        ax.fill_between(x, y, alpha=0.1, color="blue")
        ax.set_xlim(13, -0.5)
        ax.set_ylim(0, max(y) * 1.3 if max(y) > 0 else 1)
        ax.set_xlabel("Chemical Shift (ppm)", fontsize=8)
        ax.set_ylabel("Intensity", fontsize=8)
        ax.set_title("Predicted $^1$H NMR Spectrum (reference)", fontsize=9)
        ax.tick_params(labelsize=7)

        for shift, intensity, label in peaks:
            if intensity > 0.3:
                ax.annotate(f"{shift:.1f}", xy=(shift, intensity * 0.9),
                            fontsize=6, ha="center", va="bottom", color="blue")

        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="PNG", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.debug("NMR spectrum generation failed: %s", e)
        return None


# ═══════════════════════════════════════════════════════════
# 안전 정보 추출
# ═══════════════════════════════════════════════════════════

_HAZARD_DB: Dict[str, Tuple[str, str]] = {
    # reagent keyword -> (GHS pictogram description, safety note)
    "h2so4": ("GHS05 부식성, GHS07 유해", "희석 시 반드시 산을 물에 천천히 첨가. 피부/눈 접촉 시 즉시 세척."),
    "h₂so₄": ("GHS05 부식성, GHS07 유해", "희석 시 반드시 산을 물에 천천히 첨가. 피부/눈 접촉 시 즉시 세척."),
    "naoh": ("GHS05 부식성", "피부/눈 접촉 주의. 보호 장갑 및 고글 착용 필수."),
    "nah": ("GHS02 인화성, GHS05 부식성", "물과 격렬히 반응. 반드시 건조 조건에서 취급. 소화기 비치."),
    "n-buli": ("GHS02 인화성, GHS05 부식성", "극인화성 — 공기/물 접촉 금지. Ar 분위기 필수."),
    "n-buli": ("GHS02 인화성, GHS05 부식성", "극인화성 — 공기/물 접촉 금지. Ar 분위기 필수."),
    "thf": ("GHS02 인화성, GHS07 유해", "과산화물 생성 가능. 사용 전 과산화물 테스트 권장."),
    "meoh": ("GHS02 인화성, GHS06 급성독성", "경구 섭취 시 실명/사망 위험. 흄 후드 내 사용."),
    "ch₂cl₂": ("GHS07 유해, GHS08 건강유해", "흡입 시 중추신경 억제. 반드시 흄 후드 내 사용."),
    "ch2cl2": ("GHS07 유해, GHS08 건강유해", "흡입 시 중추신경 억제. 반드시 흄 후드 내 사용."),
    "dmf": ("GHS07 유해, GHS08 건강유해", "생식독성 의심. 피부 흡수 주의. 장갑 착용 필수."),
    "dmso": ("GHS07 유해", "피부 흡수 촉진제 — 오염된 장갑으로 다른 시약 취급 금지."),
    "pd": ("GHS07 유해", "Pd 촉매 — 미세 분말 흡입 주의. 마스크 착용 권장."),
    "alcl₃": ("GHS05 부식성, GHS07 유해", "물과 격렬히 반응. 건조 조건 필수."),
    "alcl3": ("GHS05 부식성, GHS07 유해", "물과 격렬히 반응. 건조 조건 필수."),
    "hbr": ("GHS05 부식성, GHS06 급성독성", "부식성 가스. 반드시 흄 후드 내 사용."),
    "hcl": ("GHS05 부식성, GHS07 유해", "부식성 가스. 반드시 흄 후드 내 사용."),
    "socl₂": ("GHS05 부식성, GHS06 급성독성", "유독 가스(SO2, HCl) 발생. 흄 후드 필수."),
    "socl2": ("GHS05 부식성, GHS06 급성독성", "유독 가스(SO2, HCl) 발생. 흄 후드 필수."),
    "pbr₃": ("GHS05 부식성, GHS06 급성독성", "공기 중 수분과 반응하여 HBr 발생. 건조 조건."),
    "pbr3": ("GHS05 부식성, GHS06 급성독성", "공기 중 수분과 반응하여 HBr 발생. 건조 조건."),
    "nabh₃cn": ("GHS06 급성독성", "시안화 수소 발생 가능. 산성 조건에서 특히 주의."),
    "nabh3cn": ("GHS06 급성독성", "시안화 수소 발생 가능. 산성 조건에서 특히 주의."),
    "nabh4": ("GHS02 인화성, GHS05 부식성", "물/산과 반응하여 H2 발생. 화기 엄금."),
    "lialh4": ("GHS02 인화성, GHS05 부식성", "물과 격렬히 반응. 건조 조건 필수. 소화기 비치."),
}


def _extract_safety_warnings(route: SynthesisRoute) -> List[str]:
    """Extract safety warnings from all steps in a route."""
    warnings: List[str] = []
    seen_keys = set()

    # Rule N: isinstance 타입 가드 — route.steps 검증
    if not isinstance(route, SynthesisRoute):
        logger.warning("_extract_safety_warnings: route가 SynthesisRoute가 아닙니다: %s", type(route))
        return []
    if not hasattr(route, 'steps') or not isinstance(route.steps, list):
        logger.warning("_extract_safety_warnings: route.steps가 리스트가 아닙니다")
        return []

    for step in route.steps:
        # Rule N: step.conditions 타입 가드
        conditions = step.conditions if hasattr(step, 'conditions') else ""
        if not isinstance(conditions, str):
            logger.warning("step.conditions가 str이 아닙니다: %s", type(conditions))
            conditions = str(conditions) if conditions is not None else ""
        cond_lower = conditions.lower()
        for key, (ghs, note) in _HAZARD_DB.items():
            if key in cond_lower and key not in seen_keys:
                seen_keys.add(key)
                warnings.append(f"{key.upper()}: {ghs} - {note}")

    # General safety
    general = [
        "실험복, 보호 안경, 내화학성 장갑을 반드시 착용하십시오.",
        "모든 유기 용매 취급은 흄 후드 안에서 수행하십시오.",
        "비상 샤워 및 눈 세척 장치의 위치를 사전에 확인하십시오.",
        "폐액은 지정된 폐액통에 분리 수거하십시오.",
    ]
    return warnings + general


# ═══════════════════════════════════════════════════════════
# 시약/준비물 추출
# ═══════════════════════════════════════════════════════════

def _extract_reagents_and_equipment(route: SynthesisRoute) -> Tuple[List[str], List[str]]:
    """Extract reagents and glassware from route steps."""
    reagents: List[str] = []
    seen_reagents = set()

    # Rule N: isinstance 타입 가드 — route 검증
    if not isinstance(route, SynthesisRoute):
        logger.warning("_extract_reagents_and_equipment: route가 SynthesisRoute가 아닙니다: %s", type(route))
        return [], []
    if not hasattr(route, 'steps') or not isinstance(route.steps, list):
        logger.warning("_extract_reagents_and_equipment: route.steps가 리스트가 아닙니다")
        return [], []

    for step in route.steps:
        # Reactant SMILES -> names
        for smi in step.reactant_smiles:
            if smi not in seen_reagents:
                seen_reagents.add(smi)
                info = get_building_block_info(smi)
                # Rule N: isinstance 타입 가드 — 외부 데이터 dict 검증
                if info and isinstance(info, dict):
                    name = info.get("name", smi)
                    formula = info.get("formula", "")
                    if not isinstance(name, str):
                        name = str(name) if name is not None else smi
                    if not isinstance(formula, str):
                        formula = str(formula) if formula is not None else ""
                    reagents.append(f"{name} ({formula})" if formula else name)
                else:
                    # Try to get a name from RDKit
                    if RDKIT_AVAILABLE:
                        mol = Chem.MolFromSmiles(smi)
                        if mol is not None:  # Rule L: None guard
                            mw = Descriptors.ExactMolWt(mol)
                            reagents.append(f"{smi} (MW: {mw:.1f} g/mol)")
                        else:
                            reagents.append(smi)
                    else:
                        reagents.append(smi)

        # Conditions -> reagents/solvents
        cond = step.conditions
        if cond and cond not in seen_reagents:
            seen_reagents.add(cond)
            reagents.append(f"[조건] {cond}")

    # Standard glassware
    equipment = [
        "둥근바닥 플라스크 (50-250 mL)",
        "자석 교반기 + 교반자",
        "분별 깔때기",
        "감압 증류 장치 (로타리 에바포레이터)",
        "TLC 플레이트 + UV 램프",
        "냉각기 (환류 장치용)",
        "주사기 / 시린지 (시약 주입용)",
        "전자저울",
        "pH 시험지",
    ]

    return reagents, equipment


# ═══════════════════════════════════════════════════════════
# ExperimentReportExporter 클래스
# ═══════════════════════════════════════════════════════════

class ExperimentReportExporter:
    """합성 경로 데이터 + AI 분석 결과를 학생용 실험 보고서 PDF로 생성."""

    def __init__(self, route: SynthesisRoute, target_name: str = "",
                 target_smiles: str = "", ai_analysis_text: str = ""):
        """
        Args:
            route: 합성 경로 객체 (SynthesisRoute)
            target_name: 타겟 분자 이름
            target_smiles: 타겟 분자 SMILES
            ai_analysis_text: Gemini AI 분석 결과 텍스트 (있으면 보고서에 반영)
        """
        # Rule N: isinstance 타입 가드 — 외부/AI 데이터 검증
        if not isinstance(route, SynthesisRoute):
            logger.warning("route가 SynthesisRoute 인스턴스가 아닙니다: %s", type(route))
            raise TypeError(f"route must be SynthesisRoute, got {type(route)}")
        if not isinstance(target_name, str):
            logger.warning("target_name이 str이 아닙니다: %s", type(target_name))
            target_name = str(target_name) if target_name is not None else ""
        if not isinstance(target_smiles, str):
            logger.warning("target_smiles가 str이 아닙니다: %s", type(target_smiles))
            target_smiles = str(target_smiles) if target_smiles is not None else ""
        if not isinstance(ai_analysis_text, str):
            logger.warning("ai_analysis_text가 str이 아닙니다: %s", type(ai_analysis_text))
            ai_analysis_text = str(ai_analysis_text) if ai_analysis_text is not None else ""

        self._route = route
        self._target_name = target_name or route.target_smiles
        self._target_smiles = target_smiles or route.target_smiles
        self._ai_text = ai_analysis_text
        _register_fonts()

    def export(self, file_path: str) -> Tuple[bool, str]:
        """PDF 실험 보고서 생성.

        Returns:
            (success: bool, message: str) - 성공 시 파일 경로, 실패 시 에러 메시지
        """
        if not REPORTLAB_AVAILABLE:
            return False, "reportlab 라이브러리가 설치되지 않았습니다."

        try:
            doc = SimpleDocTemplate(
                file_path,
                pagesize=A4,
                leftMargin=20 * mm,
                rightMargin=20 * mm,
                topMargin=15 * mm,
                bottomMargin=15 * mm,
                title=f"실험 보고서: {self._target_name}",
                author="ChemGrid Pro",
            )

            styles = self._build_styles()
            story = []

            # Header
            story.extend(self._build_header(styles))
            story.append(Spacer(1, 4 * mm))

            # Section 1: 실험 목적
            story.extend(self._build_section_purpose(styles))
            story.append(Spacer(1, 3 * mm))

            # Section 2: 이론적 배경
            story.extend(self._build_section_theory(styles))
            story.append(Spacer(1, 3 * mm))

            # Section 3: 실험 준비물
            story.extend(self._build_section_materials(styles))
            story.append(Spacer(1, 3 * mm))

            # Section 4: 실험 방법/절차
            story.extend(self._build_section_procedure(styles))
            story.append(Spacer(1, 3 * mm))

            # Section 5: 주의사항
            story.extend(self._build_section_safety(styles))

            # Page break before student sections
            story.append(PageBreak())

            # Section 6: 결과 및 관찰 (blank)
            story.extend(self._build_section_results_blank(styles))
            story.append(Spacer(1, 3 * mm))

            # Section 7: 결과 분석 (blank + reference spectra)
            story.extend(self._build_section_analysis(styles))
            story.append(Spacer(1, 3 * mm))

            # Section 8: 고찰 (blank)
            story.extend(self._build_section_discussion_blank(styles))

            doc.build(story)
            return True, file_path

        except Exception as e:
            logger.error("Experiment report PDF generation failed: %s", e)
            return False, f"PDF 생성 실패: {e}"

    # ── 스타일 정의 ──

    def _build_styles(self) -> Dict[str, ParagraphStyle]:
        """Build paragraph styles for the report."""
        base = getSampleStyleSheet()
        fn = _FONT_NAME
        fnb = _FONT_BOLD_NAME

        styles = {}
        styles["title"] = ParagraphStyle(
            "ReportTitle", parent=base["Title"],
            fontName=fnb, fontSize=18, leading=24,
            alignment=TA_CENTER, spaceAfter=2 * mm,
            textColor=colors.HexColor("#1a1a2e"),
        )
        styles["subtitle"] = ParagraphStyle(
            "ReportSubtitle", parent=base["Normal"],
            fontName=fn, fontSize=10, leading=14,
            alignment=TA_CENTER, textColor=colors.grey,
        )
        styles["section_header"] = ParagraphStyle(
            "SectionHeader", parent=base["Heading2"],
            fontName=fnb, fontSize=12, leading=16,
            spaceBefore=3 * mm, spaceAfter=2 * mm,
            textColor=colors.HexColor("#0d47a1"),
            borderWidth=0, borderPadding=0,
        )
        styles["body"] = ParagraphStyle(
            "ReportBody", parent=base["Normal"],
            fontName=fn, fontSize=10, leading=15,
            alignment=TA_JUSTIFY, spaceAfter=1.5 * mm,
        )
        styles["body_bold"] = ParagraphStyle(
            "ReportBodyBold", parent=base["Normal"],
            fontName=fnb, fontSize=10, leading=15,
            spaceAfter=1 * mm,
        )
        styles["list_item"] = ParagraphStyle(
            "ReportList", parent=base["Normal"],
            fontName=fn, fontSize=9.5, leading=14,
            leftIndent=8 * mm, bulletIndent=3 * mm,
            spaceAfter=1 * mm,
        )
        styles["blank_line"] = ParagraphStyle(
            "BlankLine", parent=base["Normal"],
            fontName=fn, fontSize=10, leading=20,
            textColor=colors.HexColor("#cccccc"),
            borderWidth=0,
        )
        styles["small"] = ParagraphStyle(
            "Small", parent=base["Normal"],
            fontName=fn, fontSize=8, leading=11,
            textColor=colors.grey,
        )
        styles["warning"] = ParagraphStyle(
            "Warning", parent=base["Normal"],
            fontName=fn, fontSize=9.5, leading=14,
            leftIndent=5 * mm, spaceAfter=1.5 * mm,
            textColor=colors.HexColor("#b71c1c"),
        )
        return styles

    # ── 헤더 (타이틀 + 날짜 + 빈칸) ──

    def _build_header(self, styles) -> list:
        """Build report header with title and info fields."""
        elements = []

        # Title
        elements.append(Paragraph(
            f"실험 보고서", styles["title"]))
        elements.append(Paragraph(
            f"{self._target_name}의 합성", styles["subtitle"]))

        elements.append(Spacer(1, 3 * mm))

        # Info table: date, name, group
        today = datetime.now().strftime("%Y년 %m월 %d일")
        info_data = [
            ["실험 날짜", today, "실험자", ""],
            ["학번", "", "조", ""],
        ]
        info_table = Table(info_data, colWidths=[25 * mm, 55 * mm, 20 * mm, 55 * mm])
        info_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (0, -1), _FONT_BOLD_NAME),
            ("FONTNAME", (2, 0), (2, -1), _FONT_BOLD_NAME),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bdbdbd")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e3f2fd")),
            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e3f2fd")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(info_table)

        # Thin separator
        elements.append(Spacer(1, 2 * mm))
        elements.append(HRFlowable(
            width="100%", thickness=0.5,
            color=colors.HexColor("#90caf9"), spaceAfter=2 * mm))

        return elements

    # ── Section 1: 실험 목적 ──

    def _build_section_purpose(self, styles) -> list:
        """Build section 1: experiment objective."""
        elements = []
        elements.append(Paragraph("1. 실험 목적", styles["section_header"]))

        purpose_text = (
            f"{self._target_name}의 합성 경로를 이해하고, "
            f"각 반응 단계의 메커니즘과 조건을 학습한다. "
            f"총 {self._route.total_steps}단계의 합성 과정을 통해 "
            f"유기합성의 기본 원리와 실험 기술을 익힌다."
        )
        elements.append(Paragraph(purpose_text, styles["body"]))

        # Add target molecule image
        target_png = _smiles_to_png_bytes(self._target_smiles, 200, 160)
        if target_png:
            img_buf = io.BytesIO(target_png)
            elements.append(Spacer(1, 2 * mm))
            img = RLImage(img_buf, width=50 * mm, height=40 * mm)
            # Wrap in table for centering
            img_table = Table([[img]], colWidths=[170 * mm])
            img_table.setStyle(TableStyle([
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
            ]))
            elements.append(img_table)
            elements.append(Paragraph(
                f"[그림 1] 타겟 분자: {self._target_name} ({self._target_smiles})",
                styles["small"]))

        return elements

    # ── Section 2: 이론적 배경 ──

    def _build_section_theory(self, styles) -> list:
        """Build section 2: theoretical background."""
        elements = []
        elements.append(Paragraph("2. 이론적 배경", styles["section_header"]))

        # Describe each reaction type used in the route
        for step in self._route.steps:
            step_desc = (
                f"<b>Step {step.step_number}: {step.transform_name} "
                f"({step.transform_name_en})</b>"
            )
            elements.append(Paragraph(step_desc, styles["body_bold"]))

            reactants_str = " + ".join(step.reactant_smiles)
            detail = (
                f"반응물 {reactants_str}로부터 {step.product_smiles}을(를) 합성한다. "
                f"반응 조건: {step.conditions}. "
                f"(신뢰도: {step.confidence * 100:.0f}%)"
            )
            elements.append(Paragraph(detail, styles["body"]))

        # Add AI analysis excerpt if available
        # Rule N: isinstance 타입 가드 — AI 텍스트 검증
        ai_text = self._ai_text
        if not isinstance(ai_text, str):
            logger.warning("AI 분석 텍스트가 str이 아닙니다: %s", type(ai_text))
            ai_text = str(ai_text) if ai_text is not None else ""
        if ai_text:
            elements.append(Spacer(1, 2 * mm))
            elements.append(Paragraph(
                "<b>[AI 분석 참고]</b>", styles["body_bold"]))
            # Truncate to reasonable length for theory section
            ai_lines = ai_text.strip().split("\n")
            excerpt_lines = []
            char_count = 0
            for line in ai_lines:
                if char_count > 800:
                    excerpt_lines.append("...")
                    break
                # Sanitize for reportlab XML
                safe_line = (line.replace("&", "&amp;")
                             .replace("<", "&lt;").replace(">", "&gt;"))
                excerpt_lines.append(safe_line)
                char_count += len(line)
            excerpt = "<br/>".join(excerpt_lines)
            elements.append(Paragraph(excerpt, styles["list_item"]))

        return elements

    # ── Section 3: 실험 준비물 ──

    def _build_section_materials(self, styles) -> list:
        """Build section 3: materials and equipment."""
        elements = []
        elements.append(Paragraph("3. 실험 준비물", styles["section_header"]))

        reagents, equipment = _extract_reagents_and_equipment(self._route)

        # Reagents table
        elements.append(Paragraph("<b>3-1. 시약 및 용매</b>", styles["body_bold"]))
        reagent_data = [["No.", "시약/용매", "비고"]]
        for i, r in enumerate(reagents, 1):
            safe_r = (r.replace("&", "&amp;")
                      .replace("<", "&lt;").replace(">", "&gt;"))
            reagent_data.append([str(i), safe_r, ""])

        if len(reagent_data) > 1:
            col_widths = [12 * mm, 100 * mm, 45 * mm]
            rtable = Table(reagent_data, colWidths=col_widths)
            rtable.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD_NAME),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3f2fd")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bdbdbd")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ]))
            elements.append(rtable)

        elements.append(Spacer(1, 2 * mm))

        # Equipment table
        elements.append(Paragraph("<b>3-2. 기구 및 장비</b>", styles["body_bold"]))
        equip_data = [["No.", "기구/장비"]]
        for i, eq in enumerate(equipment, 1):
            equip_data.append([str(i), eq])

        etable = Table(equip_data, colWidths=[12 * mm, 145 * mm])
        etable.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD_NAME),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3f2fd")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bdbdbd")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ]))
        elements.append(etable)

        # Safety equipment
        elements.append(Spacer(1, 2 * mm))
        elements.append(Paragraph("<b>3-3. 안전 장비</b>", styles["body_bold"]))
        safety_equip = [
            "실험복 (면 소재)", "보호 안경 (고글형)", "내화학성 장갑 (니트릴)",
            "흄 후드", "소화기", "응급 세안 장치",
        ]
        for item in safety_equip:
            elements.append(Paragraph(f"\u2022 {item}", styles["list_item"]))

        return elements

    # ── Section 4: 실험 방법/절차 ──

    def _build_section_procedure(self, styles) -> list:
        """Build section 4: step-by-step procedure."""
        elements = []
        elements.append(Paragraph("4. 실험 방법 및 절차", styles["section_header"]))

        proc_num = 1
        for step in self._route.steps:
            elements.append(Paragraph(
                f"<b>[Step {step.step_number}] {step.transform_name} "
                f"({step.transform_name_en})</b>",
                styles["body_bold"]))

            # Reactant structure images in a row
            img_cells = []
            for smi in step.reactant_smiles:
                png = _smiles_to_png_bytes(smi, 150, 120)
                if png:
                    buf = io.BytesIO(png)
                    img_cells.append(RLImage(buf, width=30 * mm, height=24 * mm))
                else:
                    img_cells.append(Paragraph(smi, styles["small"]))

            # Add arrow and product
            arrow_p = Paragraph("\u2192", ParagraphStyle(
                "Arrow", fontName="Helvetica", fontSize=16,
                alignment=TA_CENTER, leading=20))
            prod_png = _smiles_to_png_bytes(step.product_smiles, 150, 120)
            if prod_png:
                prod_img = RLImage(io.BytesIO(prod_png), width=30 * mm, height=24 * mm)
            else:
                prod_img = Paragraph(step.product_smiles, styles["small"])

            if img_cells:
                row = img_cells + [arrow_p, prod_img]
                n_cols = len(row)
                cw = [30 * mm] * len(img_cells) + [10 * mm, 30 * mm]
                # Limit columns to fit A4
                if sum(cw) > 160 * mm:
                    cw = [int(160 * mm / n_cols)] * n_cols
                try:
                    rxn_table = Table([row], colWidths=cw)
                    rxn_table.setStyle(TableStyle([
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]))
                    elements.append(rxn_table)
                except Exception as e:
                    logger.warning("Failed to build reaction table: %s", e)

            # Procedure steps
            cond = step.conditions
            procedures = [
                f"{proc_num}. 둥근바닥 플라스크에 반응물을 준비한다.",
                f"{proc_num + 1}. 조건({cond})에 따라 시약을 첨가하고 반응을 개시한다.",
                f"{proc_num + 2}. TLC로 반응 진행을 모니터링한다.",
                f"{proc_num + 3}. 반응이 완료되면 후처리(workup)를 수행한다.",
                f"{proc_num + 4}. 필요 시 컬럼 크로마토그래피로 정제한다.",
            ]
            proc_num += 5

            for p in procedures:
                elements.append(Paragraph(p, styles["list_item"]))

            elements.append(Spacer(1, 2 * mm))

        return elements

    # ── Section 5: 주의사항 ──

    def _build_section_safety(self, styles) -> list:
        """Build section 5: safety warnings."""
        elements = []
        elements.append(Paragraph("5. 주의사항", styles["section_header"]))

        warnings = _extract_safety_warnings(self._route)
        for w in warnings:
            safe_w = (w.replace("&", "&amp;")
                      .replace("<", "&lt;").replace(">", "&gt;"))
            elements.append(Paragraph(f"\u26a0 {safe_w}", styles["warning"]))

        return elements

    # ── Section 6: 결과 및 관찰 (빈칸) ──

    def _build_section_results_blank(self, styles) -> list:
        """Build section 6: blank results section for student."""
        elements = []
        elements.append(Paragraph("6. 결과 및 관찰", styles["section_header"]))
        elements.append(Paragraph(
            "(아래에 실험 결과를 기록하십시오.)", styles["blank_line"]))

        # Create blank table for each step
        for step in self._route.steps:
            step_data = [
                [f"Step {step.step_number}: {step.transform_name}", ""],
                ["수득량 (g)", ""],
                ["수율 (%)", ""],
                ["외관/색상", ""],
                ["TLC Rf 값", ""],
                ["녹는점/끓는점", ""],
                ["관찰 사항", ""],
            ]
            st = Table(step_data, colWidths=[45 * mm, 110 * mm])
            st.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (0, 0), _FONT_BOLD_NAME),
                ("SPAN", (0, 0), (1, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3f2fd")),
                ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f5f5f5")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bdbdbd")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("ROWHEIGHTS", (0, 0), (-1, -1), 22),
            ]))
            elements.append(st)
            elements.append(Spacer(1, 2 * mm))

        return elements

    # ── Section 7: 결과 분석 (빈칸 + 예측 스펙트럼) ──

    def _build_section_analysis(self, styles) -> list:
        """Build section 7: analysis section with reference spectra."""
        elements = []
        elements.append(Paragraph("7. 결과 분석", styles["section_header"]))
        elements.append(Paragraph(
            "(실험 결과를 분석하고, 아래 예측 스펙트럼과 비교하십시오.)",
            styles["blank_line"]))

        # Blank writing area
        blank_data = [["분석 내용을 기록하십시오:"]] + [[""] for _ in range(6)]
        bt = Table(blank_data, colWidths=[155 * mm])
        bt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e0e0e0")),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f5f5f5")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("ROWHEIGHTS", (0, 1), (-1, -1), 20),
        ]))
        elements.append(bt)
        elements.append(Spacer(1, 3 * mm))

        # Reference spectra
        elements.append(Paragraph(
            "<b>[참고] 예측 스펙트럼 (이론값)</b>", styles["body_bold"]))

        # IR spectrum
        ir_png = _generate_ir_spectrum_png(self._target_smiles)
        if ir_png:
            elements.append(Spacer(1, 2 * mm))
            ir_buf = io.BytesIO(ir_png)
            ir_img = RLImage(ir_buf, width=150 * mm, height=55 * mm)
            elements.append(ir_img)
            elements.append(Paragraph(
                "[그림] 예측 IR 스펙트럼 (이론 계산 기반 참고값)",
                styles["small"]))

        # 1H NMR spectrum
        nmr_png = _generate_nmr_spectrum_png(self._target_smiles)
        if nmr_png:
            elements.append(Spacer(1, 2 * mm))
            nmr_buf = io.BytesIO(nmr_png)
            nmr_img = RLImage(nmr_buf, width=150 * mm, height=55 * mm)
            elements.append(nmr_img)
            elements.append(Paragraph(
                "[그림] 예측 1H NMR 스펙트럼 (이론 계산 기반 참고값)",
                styles["small"]))

        return elements

    # ── Section 8: 고찰 (빈칸) ──

    def _build_section_discussion_blank(self, styles) -> list:
        """Build section 8: blank discussion section."""
        elements = []
        elements.append(Paragraph("8. 고찰", styles["section_header"]))
        elements.append(Paragraph(
            "(실험 결과를 바탕으로 고찰을 기록하십시오. "
            "예상과 다른 결과가 있었다면 그 원인을 분석하십시오.)",
            styles["blank_line"]))

        # Blank lined area
        blank_data = [[""] for _ in range(12)]
        bt = Table(blank_data, colWidths=[155 * mm])
        bt.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e0e0e0")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("ROWHEIGHTS", (0, 0), (-1, -1), 20),
        ]))
        elements.append(bt)

        # Footer
        elements.append(Spacer(1, 5 * mm))
        elements.append(HRFlowable(
            width="100%", thickness=0.3,
            color=colors.HexColor("#bdbdbd"), spaceAfter=2 * mm))
        elements.append(Paragraph(
            f"Generated by ChemGrid Pro | {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            styles["small"]))

        return elements


# ═══════════════════════════════════════════════════════════
# Convenience function
# ═══════════════════════════════════════════════════════════

def export_experiment_report(route: SynthesisRoute, file_path: str,
                              target_name: str = "", target_smiles: str = "",
                              ai_analysis_text: str = "") -> Tuple[bool, str]:
    """Convenience wrapper for ExperimentReportExporter.

    Returns:
        (success: bool, message: str)
    """
    # Rule N: isinstance 타입 가드 — 외부 호출 인자 검증
    if not isinstance(route, SynthesisRoute):
        logger.warning("export_experiment_report: route가 SynthesisRoute가 아닙니다: %s", type(route))
        return False, f"route 타입 오류: {type(route)} (SynthesisRoute 필요)"
    if not isinstance(file_path, str) or not file_path:
        logger.warning("export_experiment_report: file_path가 유효하지 않습니다: %s", file_path)
        return False, "유효한 파일 경로가 필요합니다."

    exporter = ExperimentReportExporter(
        route=route,
        target_name=target_name,
        target_smiles=target_smiles,
        ai_analysis_text=ai_analysis_text,
    )
    return exporter.export(file_path)
