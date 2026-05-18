#!/usr/bin/env python3
"""
고분자 리드 최적화 종합 보고서 PDF 내보내기.

원본 분자→원본 중합체→리드 최적화 방법론→유도체 분석→대조→합성 프로토콜
전 과정을 학술 논문급으로 정리한다.

섹션 구성 (10 Parts):
  0. 표지 (Cover)
  1. Part 1: 원본 단량체 분석 — 분자 구조, 분광 예측(IR/NMR/UV), RDKit 디스크립터
  2. Part 2: 원본 중합체 물성 — Van Krevelen + RDKit 하이브리드 결과
  3. Part 3: 리드 최적화 방법론 — 목표, 엔진, 알고리즘, 전체 유도체 목록
  4. Part 4: 선정 유도체 단량체 분석 — 구조, 분광, 디스크립터
  5. Part 5: 유도체 중합체 물성
  6. Part 6: 원본 vs 유도체 대조 분석 — 비교표, 레이더차트, 의의 서술
  7. Part 7: 중합 반응 합성 프로토콜 — DryLab급 구체적 실험 방법
  8. Part 8: 이론적 근거 및 참고문헌
"""

import io
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── RDKit ──
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, Draw, rdMolDescriptors
    RDKIT_OK = True
except ImportError as e:
    RDKIT_OK = False
    logger.debug("Optional module RDKit not available: %s", e)

# ── reportlab ──
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
        PageBreak, Image as RLImage, KeepTogether, HRFlowable,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_OK = True
except ImportError as e:
    REPORTLAB_OK = False
    logger.debug("Optional module reportlab not available: %s", e)
    mm = 2.834645669291339
    cm = 28.34645669291339
    A4 = (595.28, 841.89)

# ── matplotlib ──
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import numpy as np
    MPL_OK = True
    # 한글 폰트 설정 (malgun.ttf)
    _KR_FONT_PATHS = [
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothic.ttf",
    ]
    _MPL_KR_FONT = None
    for _fp in _KR_FONT_PATHS:
        if os.path.exists(_fp):
            _MPL_KR_FONT = fm.FontProperties(fname=_fp)
            matplotlib.rcParams["font.family"] = _MPL_KR_FONT.get_name()
            fm.fontManager.addfont(_fp)
            break
    if _MPL_KR_FONT is None:
        matplotlib.rcParams["font.family"] = "sans-serif"
except ImportError as e:
    MPL_OK = False
    logger.debug("Optional module matplotlib not available: %s", e)

# ── predict_spectra ──
try:
    from predict_spectra import predict_all as _predict_spectra_all
    SPECTRA_OK = True
except ImportError as e:
    SPECTRA_OK = False
    logger.debug("Optional module predict_spectra not available: %s", e)

# ── popup_predicted_spectrum (high-quality figure generators) ──
try:
    from popup_predicted_spectrum import (
        _make_ir_figure as _popup_ir_figure,
        _make_nmr_h1_figure as _popup_h1_figure,
        _make_nmr_c13_figure as _popup_c13_figure,
        _make_raman_figure as _popup_raman_figure,
        _make_uvvis_figure as _popup_uvvis_figure,
    )
    _POPUP_SPECTRUM_OK = True
except ImportError as e:
    _POPUP_SPECTRUM_OK = False
    logger.debug("Optional module popup_predicted_spectrum figures not available: %s", e)

# ── retrosynthesis ──
try:
    from retrosynthesis_engine import RetrosynthesisEngine
    RETRO_OK = True
except ImportError as e:
    RETRO_OK = False
    logger.debug("Optional module retrosynthesis_engine not available: %s", e)

# ═══════════════════════════════════════════════════════════════
# 데이터 클래스
# ═══════════════════════════════════════════════════════════════

@dataclass
class PolymerLeadReportData:
    """리드 최적화 보고서 입력 데이터."""
    # 원본
    original_smiles: str
    original_polymer_props: Any  # PolymerProperties
    # 리드 최적화
    optimization_goal: str           # 예: "내열성 향상"
    optimization_weights: Dict[str, float] = field(default_factory=dict)
    all_variants: List[Dict] = field(default_factory=list)
    # [{smiles, description, score, props(PolymerProperties)}]
    # 선정 유도체
    selected_smiles: str = ""
    selected_description: str = ""
    selected_polymer_props: Any = None  # PolymerProperties
    selected_score: float = 0.0
    # AI 해석
    ai_text: str = ""
    # 추가 조건
    conditions: Dict[str, str] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# 색상 팔레트 (DryLab 보고서 동일)
# ═══════════════════════════════════════════════════════════════
if REPORTLAB_OK:
    _COL_HEADER_BG = colors.HexColor("#1a1a2e")
    _COL_SECTION_NUM = colors.HexColor("#2c3e50")
    _COL_SECTION_LINE = colors.HexColor("#2980b9")
    _COL_TABLE_HEADER = colors.HexColor("#34495e")
    _COL_TABLE_HEADER_TEXT = colors.white
    _COL_TABLE_ALT = colors.HexColor("#f7f9fc")
    _COL_ACCENT = colors.HexColor("#2980b9")
    _COL_BODY = colors.HexColor("#1a1a1a")
    _COL_CAPTION = colors.HexColor("#444444")
    _COL_WHITE = colors.white
    _COL_BORDER = colors.HexColor("#cccccc")
    _COL_PASS = colors.HexColor("#27ae60")
    _COL_FAIL = colors.HexColor("#e74c3c")
else:
    _COL_HEADER_BG = _COL_SECTION_NUM = _COL_SECTION_LINE = None
    _COL_TABLE_HEADER = _COL_TABLE_HEADER_TEXT = _COL_TABLE_ALT = None
    _COL_ACCENT = _COL_BODY = _COL_CAPTION = _COL_WHITE = None
    _COL_BORDER = _COL_PASS = _COL_FAIL = None


# ═══════════════════════════════════════════════════════════════
# 유틸리티
# ═══════════════════════════════════════════════════════════════

def _smiles_to_png(smiles: str, w: int = 300, h: int = 250) -> Optional[bytes]:
    """SMILES → PNG 바이트."""
    if not RDKIT_OK:
        logger.warning("_smiles_to_png: RDKit 미사용 - 분자 이미지 생성 불가")
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("_smiles_to_png: SMILES 파싱 실패: %s", smiles)
        return None
    try:
        AllChem.Compute2DCoords(mol)
        img = Draw.MolToImage(mol, size=(w, h))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning("_smiles_to_png failed: %s", e)
        return None


def _make_rl_image(png_bytes: bytes, max_w: float = 155 * mm,
                   max_h: float = 100 * mm) -> Optional['RLImage']:
    """PNG 바이트 → ReportLab Image (종횡비 유지)."""
    if not png_bytes or not REPORTLAB_OK:
        logger.debug("_make_rl_image: PNG 데이터 없음 또는 reportlab 미사용 (png_bytes=%s, REPORTLAB_OK=%s)",
                     bool(png_bytes), REPORTLAB_OK)
        return None
    try:
        from PIL import Image as PILImage
        buf = io.BytesIO(png_bytes)
        pil_img = PILImage.open(buf)
        orig_w, orig_h = pil_img.size
        ratio = min(max_w / orig_w, max_h / orig_h)
        new_w = orig_w * ratio
        new_h = orig_h * ratio
        buf2 = io.BytesIO(png_bytes)
        return RLImage(buf2, width=new_w, height=new_h)
    except Exception as e:
        logger.warning("_make_rl_image failed: %s", e)
        return None


def _get_rdkit_descriptors(smiles: str) -> Dict[str, Any]:
    """RDKit 분자 디스크립터 계산."""
    if not RDKIT_OK:
        logger.warning("_get_rdkit_descriptors: RDKit 미사용 - 디스크립터 계산 불가")
        return {}
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        logger.warning("_get_rdkit_descriptors: SMILES 파싱 실패: %s", smiles)
        return {}
    try:
        return {
            "분자량 (g/mol)": round(Descriptors.MolWt(mol), 2),
            "분자식": rdMolDescriptors.CalcMolFormula(mol),
            "LogP (Crippen)": round(Descriptors.MolLogP(mol), 2),
            "TPSA (Å²)": round(Descriptors.TPSA(mol), 1),
            "수소결합 수용체 (HBA)": Descriptors.NumHAcceptors(mol),
            "수소결합 공여체 (HBD)": Descriptors.NumHDonors(mol),
            "회전 가능 결합": Descriptors.NumRotatableBonds(mol),
            "방향족 고리": rdMolDescriptors.CalcNumAromaticRings(mol),
            "sp3 탄소 비율": round(Descriptors.FractionCSP3(mol), 3),
            "중원자 수": Descriptors.HeavyAtomCount(mol),
            "Kier-Hall α": round(rdMolDescriptors.CalcHallKierAlpha(mol), 3),
        }
    except Exception as e:
        logger.warning("RDKit descriptor calculation failed for SMILES: %s", e)
        return {}


def _get_spectra_summary(smiles: str) -> Dict[str, Any]:
    """분광 분석 예측 요약 (IR, 1H-NMR, 13C-NMR, UV-Vis)."""
    if not SPECTRA_OK:
        logger.warning("_get_spectra_summary: predict_spectra 모듈 미사용")
        return {}
    try:
        spectra = _predict_spectra_all(smiles)
        if spectra is None:
            logger.warning("_get_spectra_summary: 스펙트럼 예측 결과 없음: %s", smiles)
            return {}
        result = {}
        # IR
        if hasattr(spectra, 'ir_peaks') and spectra.ir_peaks:
            ir_data = []
            for p in spectra.ir_peaks[:10]:  # 상위 10개
                ir_data.append({
                    "파수 (cm⁻¹)": f"{p.wavenumber:.0f}",
                    "강도": p.intensity_label if hasattr(p, 'intensity_label') else "m",
                    "귀속": p.assignment or "-",
                })
            result["IR"] = ir_data
        # 1H NMR
        if hasattr(spectra, 'h_nmr_peaks') and spectra.h_nmr_peaks:
            nmr_data = []
            for p in spectra.h_nmr_peaks[:8]:
                nmr_data.append({
                    "δ (ppm)": f"{p.shift:.2f}",
                    "다중도": p.multiplicity if hasattr(p, 'multiplicity') else "m",
                    "적분": f"{p.integration:.1f}" if hasattr(p, 'integration') else "1.0",
                    "귀속": p.assignment or "-",
                })
            result["1H-NMR"] = nmr_data
        # 13C NMR
        if hasattr(spectra, 'c13_peaks') and spectra.c13_peaks:
            c_data = []
            for p in spectra.c13_peaks[:8]:
                c_data.append({
                    "δ (ppm)": f"{p.shift:.1f}",
                    "탄소 유형": p.carbon_type if hasattr(p, 'carbon_type') else "-",
                    "귀속": p.assignment or "-",
                })
            result["13C-NMR"] = c_data
        # UV-Vis
        if hasattr(spectra, 'uv_peaks') and spectra.uv_peaks:
            uv_data = []
            for p in spectra.uv_peaks[:5]:
                uv_data.append({
                    "λmax (nm)": f"{p.wavelength:.0f}",
                    "ε (L/mol·cm)": f"{p.epsilon:.0f}" if hasattr(p, 'epsilon') else "-",
                    "전이 유형": p.transition_type if hasattr(p, 'transition_type') else "-",
                })
            result["UV-Vis"] = uv_data
        return result
    except Exception as e:
        logger.warning("Spectra prediction failed: %s", e)
        return {}


def _get_spectra_full(smiles: str) -> Optional[Any]:
    """predict_spectra_all 결과 객체를 반환 (캐시 없이 직접 호출)."""
    if not SPECTRA_OK:
        logger.warning("_get_spectra_full: predict_spectra 모듈 미사용")
        return None
    try:
        return _predict_spectra_all(smiles)
    except Exception as e:
        logger.warning("predict_spectra_all failed: %s", e)
        return None


def _generate_nmr_spectrum_png(smiles: str, nucleus: str = "1H") -> Optional[bytes]:
    """NMR 스펙트럼 예측 차트 PNG (1H or 13C). Uses popup high-quality renderer when available."""
    if not MPL_OK:
        logger.debug("_generate_nmr_spectrum_png: matplotlib 미사용 - NMR 차트 생성 불가")
        return None
    try:
        _fkw = {"fontproperties": _MPL_KR_FONT} if _MPL_KR_FONT else {}
        spectra = _get_spectra_full(smiles)

        # Primary: high-quality popup renderer (integration lines, color groups)
        if _POPUP_SPECTRUM_OK and spectra:
            try:
                formula = ""
                if RDKIT_OK:
                    mol_f = Chem.MolFromSmiles(smiles)
                    if mol_f is not None:
                        from rdkit.Chem import rdMolDescriptors as _rmd
                        formula = _rmd.CalcMolFormula(mol_f)
                if nucleus == "1H":
                    raw_peaks = (spectra.h1_nmr_peaks
                                 if hasattr(spectra, 'h1_nmr_peaks')
                                 else getattr(spectra, 'h_nmr_peaks', []))
                    if raw_peaks:
                        hq_fig = _popup_h1_figure(raw_peaks, formula, smiles)
                        hq_png = _figure_to_png(hq_fig, dpi=150)
                        if hq_png:
                            return hq_png
                else:  # 13C
                    raw_peaks = (spectra.c13_peaks
                                 if hasattr(spectra, 'c13_peaks') else [])
                    if raw_peaks:
                        hq_fig = _popup_c13_figure(raw_peaks, formula, smiles)
                        hq_png = _figure_to_png(hq_fig, dpi=150)
                        if hq_png:
                            return hq_png
            except Exception as e:
                logger.debug("popup NMR figure fallback (%s): %s", nucleus, e)

        # Fallback: crude local renderer
        peaks = []  # (shift, intensity, label, n_h)

        if nucleus == "1H":
            raw = (spectra.h1_nmr_peaks if spectra and hasattr(spectra, 'h1_nmr_peaks')
                   else getattr(spectra, 'h_nmr_peaks', []) if spectra else [])
            for p in (raw or []):
                integ = getattr(p, 'integration', 1) or 1
                peaks.append((p.shift, max(integ * 0.3, 0.3),
                               p.assignment or "H", int(integ)))
            # SMARTS fallback
            if not peaks and RDKIT_OK:
                mol = Chem.MolFromSmiles(smiles)
                if mol is not None:  # Rule L: None guard
                    smarts_tbl = [
                        ("[CH3]", 0.9, "CH₃", 3), ("[CH2]", 1.3, "CH₂", 2),
                        ("C(=O)[CH3]", 2.1, "COCH₃", 3), ("[OH]", 3.5, "OH", 1),
                        ("O[CH3]", 3.3, "OCH₃", 3), ("[NH2]", 2.5, "NH₂", 2),
                        ("c[H]", 7.2, "Ar-H", 1), ("C(=O)O[H]", 11.0, "COOH", 1),
                        ("[CH]=[CH2]", 5.2, "=CH₂", 2), ("[CH]F", 4.8, "CHF", 1),
                        ("[CH2]F", 4.5, "CH₂F", 2),
                    ]
                    for sma, sh, lab, nh in smarts_tbl:
                        try:
                            pat = Chem.MolFromSmarts(sma)
                            if pat and mol.HasSubstructMatch(pat):
                                n = len(mol.GetSubstructMatches(pat))
                                peaks.append((sh, min(n * nh * 0.3, 4.0), lab, n * nh))
                        except Exception as e:
                            logger.warning("H-NMR SMARTS peak matching failed for pattern '%s': %s", sma, e)
            xrange = (-0.5, 13.0)
            xlabel = u"Chemical Shift / ppm (\u03b4)"
            title = u"\u00b9H-NMR \uc608\uce21 \uc2a4\ud399\ud2b8\ub7fc"
            sigma = 0.04
        else:  # 13C
            raw = (spectra.c13_peaks if spectra and hasattr(spectra, 'c13_peaks')
                   else [])
            for p in (raw or []):
                peaks.append((p.shift, 1.0, p.assignment or "C", 1))
            if not peaks and RDKIT_OK:
                mol = Chem.MolFromSmiles(smiles)
                if mol is not None:  # Rule L: None guard
                    smarts_tbl = [
                        ("[CH3]", 15.0, "CH₃", 1), ("[CH2]", 25.0, "CH₂", 1),
                        ("C=O", 195.0, "C=O", 1), ("c", 128.0, "Ar-C", 1),
                        ("CO", 60.0, "C-O", 1), ("C=C", 125.0, "C=C", 1),
                        ("CF", 85.0, "C-F", 1), ("[CH]=[CH2]", 115.0, "=CH₂", 1),
                    ]
                    for sma, sh, lab, _ in smarts_tbl:
                        try:
                            pat = Chem.MolFromSmarts(sma)
                            if pat and mol.HasSubstructMatch(pat):
                                n = len(mol.GetSubstructMatches(pat))
                                peaks.append((sh, 1.0, lab, n))
                        except Exception as e:
                            logger.warning("C13-NMR SMARTS peak matching failed for pattern '%s': %s", sma, e)
            xrange = (-5.0, 220.0)
            xlabel = u"Chemical Shift / ppm (\u03b4)"
            title = u"\u00b9\u00b3C-NMR \uc608\uce21 \uc2a4\ud399\ud2b8\ub7fc"
            sigma = 1.0

        if not peaks:
            logger.debug("_generate_nmr_spectrum_png: 피크 없음 (%s, SMILES=%s)", nucleus, smiles)
            return None

        fig, ax = plt.subplots(figsize=(7.5, 3.0))
        x = np.linspace(xrange[0], xrange[1], 3000)
        y = np.zeros_like(x)
        for shift, intensity, _, _ in peaks:
            y += intensity * np.exp(-((x - shift) ** 2) / (2 * sigma ** 2))

        ax.plot(x, y, color="#1a1a1a", linewidth=0.8)
        ax.fill_between(x, y, alpha=0.08, color="#2980b9")
        ax.set_xlim(xrange[1], xrange[0])
        ymax = max(y) if max(y) > 0 else 1.0
        ax.set_ylim(-0.05 * ymax, ymax * 1.35)
        if nucleus == "1H":
            ax.axvline(x=0, color='#999999', linewidth=0.5, linestyle='--')
        ax.set_xlabel(xlabel, fontsize=8, **_fkw)
        ax.set_ylabel("Intensity", fontsize=8, **_fkw)
        ax.set_title(title, fontsize=9, **_fkw)
        ax.grid(True, linestyle=':', alpha=0.3)
        ax.tick_params(labelsize=7)

        # Peak annotations
        sorted_pks = sorted([(s, i, l, n) for s, i, l, n in peaks if i > 0.1],
                             key=lambda p: p[0])
        prev = -999.0
        stagger = 0
        for sh, inten, lab, nh in sorted_pks:
            if abs(sh - prev) < (1.0 if nucleus == "1H" else 5.0):
                stagger += 1
            else:
                stagger = 0
            prev = sh
            ann = f"{sh:.1f}\n({lab})"
            if nucleus == "1H" and nh > 0:
                ann = f"{sh:.1f}\n({lab}, {nh}H)"
            ax.annotate(ann, xy=(sh, inten * 0.9),
                        xytext=(0, 8 + stagger * 15),
                        textcoords='offset points',
                        fontsize=5.0, ha='center', va='bottom', color='#2c3e50')

        fig.tight_layout(pad=1.0)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        logger.warning("NMR spectrum chart failed (%s): %s", nucleus, e)
        return None


def _generate_uvvis_spectrum_png(smiles: str) -> Optional[bytes]:
    """UV-Vis 스펙트럼 예측 차트 PNG. Uses popup high-quality renderer when available."""
    if not MPL_OK:
        logger.debug("_generate_uvvis_spectrum_png: matplotlib 미사용 - UV-Vis 차트 생성 불가")
        return None
    try:
        _fkw = {"fontproperties": _MPL_KR_FONT} if _MPL_KR_FONT else {}
        spectra = _get_spectra_full(smiles)

        # Primary: high-quality popup renderer (dual view, visible band shading)
        if _POPUP_SPECTRUM_OK and spectra:
            try:
                uv_raw = (spectra.uv_peaks if hasattr(spectra, 'uv_peaks') and spectra.uv_peaks
                          else getattr(spectra, 'uvvis_peaks', []))
                if uv_raw:
                    hq_fig = _popup_uvvis_figure(uv_raw)
                    hq_png = _figure_to_png(hq_fig, dpi=150)
                    if hq_png:
                        return hq_png
            except Exception as e:
                logger.debug("popup UV-Vis figure fallback: %s", e)

        # Fallback: crude local renderer
        peaks = []  # (wavelength, intensity 0-1, label)

        if spectra and hasattr(spectra, 'uv_peaks') and spectra.uv_peaks:
            max_eps = max((p.epsilon for p in spectra.uv_peaks), default=1.0) or 1.0
            for p in spectra.uv_peaks:
                tt = getattr(p, 'transition_type', '') or ''
                asn = getattr(p, 'assignment', '') or ''
                lab = f"{tt} ({asn})" if asn else tt
                peaks.append((p.wavelength, min(p.epsilon / max_eps, 1.0), lab))
        elif spectra and hasattr(spectra, 'uvvis_peaks') and spectra.uvvis_peaks:
            max_eps = max((p.epsilon for p in spectra.uvvis_peaks), default=1.0) or 1.0
            for p in spectra.uvvis_peaks:
                tt = getattr(p, 'transition_type', '') or ''
                lab = tt
                peaks.append((p.wavelength, min(p.epsilon / max_eps, 1.0), lab))

        # SMARTS fallback
        if not peaks and RDKIT_OK:
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:  # Rule L: None guard
                uv_checks = [
                    ("c", 254.0, 0.8, "π→π* (Ar)"),
                    ("C=O", 280.0, 0.3, "n→π* (C=O)"),
                    ("C=C", 185.0, 0.9, "π→π* (C=C)"),
                    ("C(=O)O", 205.0, 0.4, "n→π* (COOH)"),
                ]
                for sma, wl, inten, lab in uv_checks:
                    try:
                        pat = Chem.MolFromSmarts(sma)
                        if pat and mol.HasSubstructMatch(pat):
                            peaks.append((wl, inten, lab))
                    except Exception as e:
                        logger.warning("UV-Vis SMARTS peak matching failed for pattern '%s': %s", sma, e)
            if not peaks:
                peaks.append((200.0, 1.0, "σ→σ*"))

        if not peaks:
            logger.debug("_generate_uvvis_spectrum_png: 피크 없음 (SMILES=%s)", smiles)
            return None

        fig, ax = plt.subplots(figsize=(7.5, 3.0))
        x = np.linspace(180, 700, 2000)
        y = np.zeros_like(x)
        for wl, inten, _ in peaks:
            sigma = 15.0
            y += inten * np.exp(-((x - wl) ** 2) / (2 * sigma ** 2))
        if max(y) > 0:
            y = y / max(y)

        ax.plot(x, y, color="#2980b9", linewidth=1.0)
        ax.fill_between(x, y, alpha=0.12, color="#2980b9")
        ax.set_xlim(180, 700)
        ax.set_ylim(-0.05, 1.15)
        ax.set_xlabel("Wavelength / nm", fontsize=8, **_fkw)
        ax.set_ylabel("Absorbance (norm.)", fontsize=8, **_fkw)
        ax.set_title(u"UV-Vis \uc608\uce21 \uc2a4\ud399\ud2b8\ub7fc", fontsize=9, **_fkw)
        ax.grid(True, linestyle=':', alpha=0.3)
        ax.tick_params(labelsize=7)

        for wl, inten, lab in sorted(peaks, key=lambda p: -p[1])[:5]:
            idx = int((wl - 180) / (700 - 180) * len(x))
            idx = max(0, min(idx, len(x) - 1))
            y_val = y[idx]
            ax.annotate(f"{wl:.0f} nm\n{lab}",
                        xy=(wl, y_val), xytext=(0, 12),
                        textcoords='offset points',
                        fontsize=5.5, ha='center', va='bottom', color='#c0392b')

        fig.tight_layout(pad=1.0)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        logger.warning("UV-Vis spectrum chart failed: %s", e)
        return None


def _generate_mass_spectrum_png(smiles: str) -> Optional[bytes]:
    """Mass 스펙트럼 (EI-MS) 예측 차트 PNG."""
    if not MPL_OK or not RDKIT_OK:
        logger.debug("_generate_mass_spectrum_png: 필수 모듈 미사용 (MPL=%s, RDKit=%s)", MPL_OK, RDKIT_OK)
        return None
    try:
        _fkw = {"fontproperties": _MPL_KR_FONT} if _MPL_KR_FONT else {}
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("_generate_mass_spectrum_png: SMILES 파싱 실패: %s", smiles)
            return None
        from rdkit.Chem import Descriptors as _D
        mw = _D.ExactMolWt(mol)

        peaks = []  # (mz, rel_intensity, label)
        spectra = _get_spectra_full(smiles)
        if spectra and hasattr(spectra, 'mass_peaks') and spectra.mass_peaks:
            for p in spectra.mass_peaks:
                peaks.append((p.mz, p.intensity, p.assignment or ""))
        elif spectra and hasattr(spectra, 'ms_peaks') and spectra.ms_peaks:
            for p in spectra.ms_peaks:
                peaks.append((p.mz, p.intensity, getattr(p, 'assignment', '') or ""))

        if not peaks:
            # Fallback: element-aware fragmentation heuristics
            peaks.append((round(mw, 0), 100.0, "M\u207a"))
            peaks.append((round(mw + 1, 0), max(3.0, mw * 0.011 * 10), "M+1"))

            # Detect elements present in the molecule
            from rdkit.Chem import rdMolDescriptors as _RMD
            atom_syms = {a.GetSymbol() for a in mol.GetAtoms()}
            has_F   = "F" in atom_syms
            has_Cl  = "Cl" in atom_syms
            has_Br  = "Br" in atom_syms
            has_O   = "O" in atom_syms
            has_N   = "N" in atom_syms
            has_H   = any(a.GetTotalNumHs() > 0 for a in mol.GetAtoms())
            has_S   = "S" in atom_syms

            n_F  = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "F")
            n_Cl = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "Cl")
            n_Br = sum(1 for a in mol.GetAtoms() if a.GetSymbol() == "Br")

            # Build candidate losses keyed by (loss_mass, label, required_smarts_or_None)
            candidates = []

            # Halogen-containing losses (priority for halogenated molecules)
            if has_F:
                candidates += [
                    (19,  "F\u207a / [M-F]\u207a",    None),  # loss of F (19)
                    (38,  "[M-2F]\u207a",              None),  # loss of 2F
                    (50,  "CF\u2082\u207a",             None),  # CF2 fragment (50)
                    (69,  "CF\u2083\u207a",             None),  # CF3 (69)
                ]
            if has_Cl:
                candidates += [
                    (35,  "Cl\u207a / [M-Cl]\u207a",  None),
                    (70,  "[M-HCl]\u207a",             None),
                ]
            if has_Br:
                candidates += [
                    (79,  "Br\u207a / [M-Br]\u207a",  None),
                    (81,  "[M-\u2079\u00b9Br]\u207a",  None),
                ]

            # Oxygen/hydrogen losses — only when those elements are present
            if has_O and has_H:
                candidates += [
                    (18, "[M-H\u2082O]\u207a",   "[OH]"),
                    (17, "[M-OH]\u207a",          "[OH]"),
                ]
            if has_O:
                candidates += [
                    (28, "[M-CO]\u207a",          "C=O"),
                    (44, "[M-CO\u2082]\u207a",    "C(=O)O"),
                ]
            if has_H:
                candidates += [
                    (1,  "[M-H]\u207a",           None),
                ]

            # Alkyl losses — only when CH3 / CHO groups are present
            candidates += [
                (15,  "[M-CH\u2083]\u207a",     "[CH3]"),
                (29,  "[M-C\u2082H\u2085]\u207a / [M-CHO]\u207a", "[CH]=O"),  # CHO checked
                (31,  "[M-OCH\u2083]\u207a",    "CO[CH3]"),
            ]

            if has_N:
                candidates += [
                    (17, "[M-NH\u2083]\u207a",   "N"),
                    (27, "[HCN]\u207a",           "c"),  # aromatic N
                ]
            if has_S:
                candidates += [
                    (34, "[M-H\u2082S]\u207a",   "[SH]"),
                    (48, "[M-SO]\u207a",          "S=O"),
                ]

            # Evaluate each candidate
            for loss, label, sma in candidates:
                frag_mz = round(mw - loss, 0)
                if frag_mz < 10:
                    continue
                plausible = True
                if sma:
                    try:
                        pat = Chem.MolFromSmarts(sma)
                        plausible = bool(pat and mol.HasSubstructMatch(pat))
                    except Exception as e:
                        logger.warning("Mass spectrum SMARTS matching failed for pattern '%s': %s", sma, e)
                        plausible = False
                if plausible:
                    rel_int = max(5.0, 90 - loss * 0.7)
                    peaks.append((frag_mz, rel_int, label))

        if not peaks:
            return None

        fig, ax = plt.subplots(figsize=(7.5, 3.0))
        mz_vals = [p[0] for p in peaks]
        intensities = [p[1] for p in peaks]
        ax.bar(mz_vals, intensities, width=max(0.5, mw * 0.004),
               color="#1a1a1a", edgecolor="#333", linewidth=0.4)

        top_peaks = sorted(peaks, key=lambda p: -p[1])[:8]
        for mz, inten, lab in top_peaks:
            if inten > 8:
                ax.annotate(f"m/z {mz:.0f}\n{lab}",
                            xy=(mz, inten), xytext=(0, 6),
                            textcoords='offset points',
                            fontsize=5.0, ha='center', va='bottom', color='#c0392b')

        margin = max(20, mw * 0.08)
        ax.set_xlim(max(0, min(mz_vals) - margin), max(mz_vals) + margin)
        ax.set_ylim(0, 115)
        ax.set_xlabel("m/z", fontsize=8, **_fkw)
        ax.set_ylabel(u"Relative Intensity / %", fontsize=8, **_fkw)
        ax.set_title(u"Mass \uc2a4\ud399\ud2b8\ub7fc (EI-MS)", fontsize=9, **_fkw)
        ax.grid(True, linestyle=':', alpha=0.3, axis='y')
        ax.tick_params(labelsize=7)

        fig.tight_layout(pad=1.0)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        logger.warning("Mass spectrum chart failed: %s", e)
        return None


def _generate_collision_mechanism_3d_png(smiles: str,
                                         poly_type: str = "addition") -> Optional[bytes]:
    """3D 유효충돌 방향 + 전이상태 시각화 PNG.

    두 단량체가 유효충돌 방향으로 접근하는 모습을 ball-and-stick으로 렌더링한다.
    addition: C=C 면대면 접근, condensation: 작용기 head-on, ring_opening: 후면 공격.
    """
    if not MPL_OK or not RDKIT_OK:
        logger.debug("_generate_collision_mechanism_3d_png: 필수 모듈 미사용")
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("_generate_collision_mechanism_3d_png: SMILES 파싱 실패: %s", smiles)
            return None
        mol = Chem.AddHs(mol)
        status = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        if status != 0:
            AllChem.EmbedMolecule(mol, AllChem.ETKDGv3(),
                                  randomSeed=42, useRandomCoords=True)
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=500)  # MMFF94 force field
        except Exception as e:
            logger.debug("MMFF optimization failed, trying UFF: %s", e)
            try:
                AllChem.UFFOptimizeMolecule(mol, maxIters=500)  # fallback UFF
            except Exception as e2:
                logger.debug("UFF optimization also failed: %s", e2)

        conf = mol.GetConformer()
        coords_A = conf.GetPositions()  # monomer A coordinates (Angstrom)

        # ── CPK color scheme ──
        cpk = {6: '#333333', 1: '#FFFFFF', 7: '#3050F8', 8: '#FF0D0D',
               9: '#90E050', 15: '#FF8000', 16: '#FFFF30', 17: '#1FF01F',
               35: '#A62929', 53: '#940094'}

        # ── Identify reactive atom indices ──
        reactive_A = set()
        mol_noH = Chem.RemoveHs(mol)
        if poly_type in ('addition', 'radical', ''):
            # C=C double bond atoms
            for bond in mol_noH.GetBonds():
                if bond.GetBondTypeAsDouble() == 2.0:
                    a1, a2 = bond.GetBeginAtom(), bond.GetEndAtom()
                    if a1.GetAtomicNum() == 6 and a2.GetAtomicNum() == 6:
                        # Map back to Hs-added mol indices
                        reactive_A.add(bond.GetBeginAtomIdx())
                        reactive_A.add(bond.GetEndAtomIdx())
                        break
        elif poly_type in ('condensation', 'step_growth'):
            # OH and COOH functional groups
            pat_oh = Chem.MolFromSmarts('[OH]')
            pat_cooh = Chem.MolFromSmarts('[CX3](=O)[OX2H1]')
            for pat in [pat_oh, pat_cooh]:
                if pat:
                    matches = mol_noH.GetSubstructMatches(pat)
                    for m in matches:
                        for idx in m:
                            reactive_A.add(idx)
        elif poly_type == 'ring_opening':
            # Strained ring atoms (3 or 4 membered)
            ri = mol_noH.GetRingInfo()
            for ring in ri.AtomRings():
                if len(ring) <= 4:  # 3-4 membered rings are strained
                    for idx in ring:
                        reactive_A.add(idx)
                    break

        # ── Position monomer B offset along collision axis ──
        centroid_A = np.mean(coords_A, axis=0)
        if poly_type in ('addition', 'radical', ''):
            offset_dist = 3.5  # Angstrom: π-bond interaction distance for vinyl monomers
            offset_vec = np.array([offset_dist, 0.0, 0.0])
        elif poly_type in ('condensation', 'step_growth'):
            offset_dist = 4.0  # Angstrom: functional group approach distance
            offset_vec = np.array([offset_dist, 0.5, 0.0])
        else:  # ring_opening
            offset_dist = 3.8  # Angstrom: nucleophile approach for SN2
            offset_vec = np.array([offset_dist, 0.0, 0.5])

        coords_B = coords_A + offset_vec  # monomer B translated

        # ── Draw ──
        _fkw = {"fontproperties": _MPL_KR_FONT} if _MPL_KR_FONT else {}
        fig = plt.figure(figsize=(7, 5), dpi=200)
        ax = fig.add_subplot(111, projection='3d')

        def _draw_monomer(coords, alpha_val=1.0, is_B=False):
            """Draw one monomer as ball-and-stick."""
            for bond in mol.GetBonds():
                i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
                xs = [coords[i][0], coords[j][0]]
                ys = [coords[i][1], coords[j][1]]
                zs = [coords[i][2], coords[j][2]]
                lw = 2.5 if bond.GetBondTypeAsDouble() > 1 else 1.5
                ax.plot(xs, ys, zs, color='#555555', linewidth=lw,
                        alpha=alpha_val, zorder=1)
            for idx in range(mol.GetNumAtoms()):
                atom = mol.GetAtomWithIdx(idx)
                an = atom.GetAtomicNum()
                # Reactive atoms colored red (#FF0000)
                if idx in reactive_A:
                    color = '#FF0000'
                else:
                    # Rule N: isinstance guard for cpk
                    if not isinstance(cpk, dict): cpk = {}
                    color = cpk.get(an, '#FF69B4')
                sz = 120 if an == 1 else 280  # H atoms smaller
                ax.scatter(coords[idx][0], coords[idx][1], coords[idx][2],
                           c=color, s=sz, edgecolors='#333333',
                           linewidths=0.5, zorder=2, alpha=alpha_val,
                           depthshade=True)

        _draw_monomer(coords_A, alpha_val=1.0)
        _draw_monomer(coords_B, alpha_val=0.85, is_B=True)

        # ── Collision vector arrow ──
        centroid_B = np.mean(coords_B, axis=0)
        arrow_start = centroid_B + (centroid_B - centroid_A) * 0.5
        arrow_end = centroid_A + (centroid_A - centroid_B) * 0.1
        ax.quiver(arrow_start[0], arrow_start[1], arrow_start[2],
                  (arrow_end - arrow_start)[0],
                  (arrow_end - arrow_start)[1],
                  (arrow_end - arrow_start)[2],
                  color='#e74c3c', arrow_length_ratio=0.15,
                  linewidth=2.5, zorder=5)

        # ── Dashed lines between reactive atoms (partial bond formation) ──
        reactive_list = list(reactive_A)
        for idx in reactive_list[:2]:  # connect first 2 reactive atoms across monomers
            if idx < len(coords_A) and idx < len(coords_B):
                ax.plot([coords_A[idx][0], coords_B[idx][0]],
                        [coords_A[idx][1], coords_B[idx][1]],
                        [coords_A[idx][2], coords_B[idx][2]],
                        color='#e67e22', linestyle='--', linewidth=1.8,
                        zorder=3, alpha=0.8)

        # ── Annotations ──
        poly_labels = {
            'addition': '첨가 중합 (라디칼)',
            'radical': '라디칼 첨가 중합',
            'condensation': '축합 중합',
            'step_growth': '단계적 성장 중합',
            'ring_opening': '개환 중합',
        }
        # Rule N: isinstance guard for poly_labels
        if not isinstance(poly_labels, dict): poly_labels = {}
        mech_label = poly_labels.get(poly_type, '중합 반응')
        ax.text2D(0.05, 0.95, f"유효충돌 방향 ({mech_label})",
                  transform=ax.transAxes, fontsize=9, color='#2c3e50',
                  fontweight='bold', **_fkw)
        mid = (centroid_A + centroid_B) / 2
        ax.text(mid[0], mid[1], mid[2] + 1.5, "전이상태 (‡)",
                fontsize=8, color='#e74c3c', ha='center', **_fkw)

        ax.set_axis_off()
        ax.set_box_aspect([1, 1, 1])
        fig.patch.set_facecolor('white')
        fig.tight_layout(pad=0)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                    facecolor='white')
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        logger.warning("Collision mechanism 3D generation failed: %s", e)
        return None


def _generate_transition_state_3d_png(smiles: str,
                                       poly_type: str = "addition") -> Optional[bytes]:
    """전이상태 구조 3D 시각화 PNG.

    단일 병합 구조의 전이상태 기하학을 렌더링한다.
    부분 결합(dashed, 주황색)을 ~2.0 Å 거리에 표시하고,
    에너지 다이어그램 주석을 포함한다.
    """
    if not MPL_OK or not RDKIT_OK:
        logger.debug("_generate_transition_state_3d_png: 필수 모듈 미사용")
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.warning("_generate_transition_state_3d_png: SMILES 파싱 실패: %s", smiles)
            return None
        mol = Chem.AddHs(mol)
        status = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
        if status != 0:
            AllChem.EmbedMolecule(mol, AllChem.ETKDGv3(),
                                  randomSeed=42, useRandomCoords=True)
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
        except Exception as e:
            logger.debug("MMFF optimization failed, trying UFF: %s", e)
            try:
                AllChem.UFFOptimizeMolecule(mol, maxIters=500)
            except Exception as e2:
                logger.debug("UFF optimization also failed: %s", e2)

        conf = mol.GetConformer()
        coords_A = conf.GetPositions()

        # CPK coloring
        cpk = {6: '#333333', 1: '#FFFFFF', 7: '#3050F8', 8: '#FF0D0D',
               9: '#90E050', 15: '#FF8000', 16: '#FFFF30', 17: '#1FF01F',
               35: '#A62929', 53: '#940094'}

        # Transition state offset: ~2.0 Å (partial bond distance)
        ts_offset = 2.0  # Angstrom: transition state C···C distance
        coords_B = coords_A + np.array([ts_offset, 0.0, 0.0])

        _fkw = {"fontproperties": _MPL_KR_FONT} if _MPL_KR_FONT else {}

        fig = plt.figure(figsize=(7, 5), dpi=200)
        gs = fig.add_gridspec(1, 5)
        ax3d = fig.add_subplot(gs[0, :3], projection='3d')
        ax_energy = fig.add_subplot(gs[0, 3:])

        # ── Draw merged TS structure in 3D ──
        def _draw_mol_ts(coords, alpha_v=1.0):
            for bond in mol.GetBonds():
                i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
                lw = 2.5 if bond.GetBondTypeAsDouble() > 1 else 1.5
                ax3d.plot([coords[i][0], coords[j][0]],
                          [coords[i][1], coords[j][1]],
                          [coords[i][2], coords[j][2]],
                          color='#555555', linewidth=lw, alpha=alpha_v, zorder=1)
            for idx in range(mol.GetNumAtoms()):
                an = mol.GetAtomWithIdx(idx).GetAtomicNum()
                # Rule N: isinstance guard for cpk
                if not isinstance(cpk, dict): cpk = {}
                color = cpk.get(an, '#FF69B4')
                sz = 100 if an == 1 else 240
                ax3d.scatter(coords[idx][0], coords[idx][1], coords[idx][2],
                             c=color, s=sz, edgecolors='#333333',
                             linewidths=0.5, zorder=2, alpha=alpha_v,
                             depthshade=True)

        _draw_mol_ts(coords_A, alpha_v=1.0)
        _draw_mol_ts(coords_B, alpha_v=0.7)

        # ── Partial bonds (orange dashed) between reactive centers ──
        _parsed_smiles = Chem.MolFromSmiles(smiles)
        if _parsed_smiles is None:
            logger.warning(f"Invalid SMILES for polymer TS rendering: {smiles}")
            return
        mol_noH = Chem.RemoveHs(_parsed_smiles)
        reactive_idxs = []
        if poly_type in ('addition', 'radical', ''):
            for bond in mol_noH.GetBonds():
                if bond.GetBondTypeAsDouble() == 2.0:
                    a1, a2 = bond.GetBeginAtom(), bond.GetEndAtom()
                    if a1.GetAtomicNum() == 6 and a2.GetAtomicNum() == 6:
                        reactive_idxs = [bond.GetBeginAtomIdx(),
                                         bond.GetEndAtomIdx()]
                        break
        elif poly_type in ('condensation', 'step_growth'):
            pat = Chem.MolFromSmarts('[CX3](=O)[OX2H1]')
            if pat:
                matches = mol_noH.GetSubstructMatches(pat)
                if matches:
                    reactive_idxs = list(matches[0][:2])
        elif poly_type == 'ring_opening':
            ri = mol_noH.GetRingInfo()
            for ring in ri.AtomRings():
                if len(ring) <= 4:
                    reactive_idxs = list(ring[:2])
                    break

        for idx in reactive_idxs[:2]:
            if idx < len(coords_A) and idx < len(coords_B):
                ax3d.plot([coords_A[idx][0], coords_B[idx][0]],
                          [coords_A[idx][1], coords_B[idx][1]],
                          [coords_A[idx][2], coords_B[idx][2]],
                          color='#f39c12', linestyle='--', linewidth=2.5,
                          zorder=4, alpha=0.9)

        centroid = np.mean(np.vstack([coords_A, coords_B]), axis=0)
        ax3d.text(centroid[0], centroid[1], centroid[2] + 2.0, "‡",
                  fontsize=16, color='#e74c3c', ha='center',
                  fontweight='bold')
        ax3d.set_axis_off()
        ax3d.set_box_aspect([1, 1, 1])

        # ── Energy diagram (right panel) ──
        # Activation energies by polymerization type (kJ/mol)
        ea_map = {
            'addition': 30,    # ~20-40 kJ/mol for radical addition
            'radical': 30,
            'condensation': 60,  # ~40-80 kJ/mol for condensation
            'step_growth': 60,
            'ring_opening': 45,  # intermediate
        }
        # Rule N: isinstance guard for ea_map
        if not isinstance(ea_map, dict): ea_map = {}
        ea = ea_map.get(poly_type, 35)  # kJ/mol
        delta_h = -ea * 0.6  # exothermic by ~60% of Ea (approximate)

        x_pts = [0, 1, 2, 3]
        y_pts = [0, ea * 0.3, ea, ea + delta_h]  # reactants, approach, TS, products
        # Smooth energy curve via interpolation
        x_smooth = np.linspace(0, 3, 100)
        y_smooth = np.interp(x_smooth, x_pts, y_pts)

        ax_energy.plot(x_smooth, y_smooth, 'k-', linewidth=1.5)
        ax_energy.axhline(y=0, color='#bdc3c7', linewidth=0.5, linestyle=':')
        ax_energy.axhline(y=ea, color='#e74c3c', linewidth=0.5, linestyle=':')

        # Markers
        ax_energy.plot(0, 0, 'bo', markersize=6)
        ax_energy.plot(2, ea, 'r^', markersize=8)
        ax_energy.plot(3, ea + delta_h, 'gs', markersize=6)

        # Labels
        ax_energy.annotate("반응물", xy=(0, 0), xytext=(0.1, -ea * 0.15),
                           fontsize=7, color='#2980b9', **_fkw)
        ax_energy.annotate(f"전이상태 (‡)\nEa ~ {ea} kJ/mol",
                           xy=(2, ea), xytext=(1.5, ea + ea * 0.1),
                           fontsize=6.5, color='#e74c3c', **_fkw)
        ax_energy.annotate("생성물", xy=(3, ea + delta_h),
                           xytext=(2.5, ea + delta_h - ea * 0.15),
                           fontsize=7, color='#27ae60', **_fkw)
        # Double arrow for Ea
        ax_energy.annotate("", xy=(1.8, ea), xytext=(1.8, 0),
                           arrowprops=dict(arrowstyle='<->', color='#e74c3c',
                                           lw=1.2))
        ax_energy.text(1.5, ea * 0.5, f"Ea", fontsize=8, color='#e74c3c',
                       fontweight='bold')

        ax_energy.set_ylabel("에너지 (kJ/mol)", fontsize=7, **_fkw)
        ax_energy.set_xlabel("반응 좌표", fontsize=7, **_fkw)
        ax_energy.set_title("에너지 프로파일", fontsize=8, **_fkw)
        ax_energy.tick_params(labelsize=6)
        ax_energy.set_xlim(-0.3, 3.5)
        ax_energy.spines['top'].set_visible(False)
        ax_energy.spines['right'].set_visible(False)

        fig.patch.set_facecolor('white')
        fig.tight_layout(pad=1.0)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                    facecolor='white')
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        logger.warning("Transition state 3D generation failed: %s", e)
        return None


def _generate_radar_png(orig_props, deriv_props, w=500, h=400) -> Optional[bytes]:
    """원본 vs 유도체 레이더 차트 PNG."""
    if not MPL_OK:
        logger.debug("_generate_radar_png: matplotlib 미사용 - 레이더 차트 생성 불가")
        return None
    try:
        categories = ["Tg", "Tm", "Td", "밀도", "인장강도", "영률", "굴절률"]
        # 정규화 범위
        ranges = {
            "Tg": (-130, 350), "Tm": (100, 400), "Td": (200, 600),
            "밀도": (0.8, 2.3), "인장강도": (5, 150), "영률": (100, 5000),
            "굴절률": (1.3, 1.7),
        }
        attrs = ["Tg", "Tm", "Td", "density", "tensile_strength",
                 "youngs_modulus", "refractive_index"]

        def _normalize(props):
            vals = []
            for cat, attr in zip(categories, attrs):
                v = getattr(props, attr, 0)
                lo, hi = ranges[cat]
                vals.append(max(0, min(1, (v - lo) / (hi - lo))))
            return vals

        vals_orig = _normalize(orig_props)
        vals_deriv = _normalize(deriv_props)

        N = len(categories)
        angles = [n / float(N) * 2 * math.pi for n in range(N)]
        angles += angles[:1]
        vals_orig += vals_orig[:1]
        vals_deriv += vals_deriv[:1]

        fig, ax = plt.subplots(figsize=(w / 100, h / 100), subplot_kw=dict(polar=True))
        ax.plot(angles, vals_orig, 'b-o', linewidth=1.5, label='원본', markersize=4)
        ax.fill(angles, vals_orig, alpha=0.1, color='blue')
        ax.plot(angles, vals_deriv, 'r-s', linewidth=1.5, label='유도체', markersize=4)
        ax.fill(angles, vals_deriv, alpha=0.1, color='red')
        ax.set_xticks(angles[:-1])
        _fkw = {"fontproperties": _MPL_KR_FONT} if MPL_OK and _MPL_KR_FONT else {}
        ax.set_xticklabels(categories, fontsize=8, **_fkw)
        ax.set_ylim(0, 1)
        ax.legend(loc='upper right', fontsize=8, prop=_MPL_KR_FONT if _MPL_KR_FONT else None)
        ax.set_title("원본 vs 유도체 물성 비교", fontsize=10, pad=15, **_fkw)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        logger.warning("Radar chart failed: %s", e)
        return None


def _figure_to_png(fig: "plt.Figure", dpi: int = 150) -> Optional[bytes]:
    """Convert a matplotlib Figure to PNG bytes, then close the figure.

    Used to bridge popup_predicted_spectrum figure generators (which return
    Figure objects) into the report's PNG-based image pipeline.

    Args:
        fig: matplotlib Figure to convert
        dpi: output DPI

    Returns:
        PNG bytes or None if conversion fails.
    """
    if fig is None:
        return None
    try:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                    facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.warning("_figure_to_png failed: %s", e)
        try:
            plt.close(fig)
        except Exception as _e:
            logger.warning("[PolymerLeadReportExporter] plt.close(fig) failed: %s", _e)
        return None


def _generate_ir_spectrum_png(smiles: str, w=500, h=250) -> Optional[bytes]:
    """IR 스펙트럼 예측 차트 PNG. Uses popup high-quality renderer when available."""
    if not MPL_OK or not SPECTRA_OK:
        logger.debug("_generate_ir_spectrum_png: 필수 모듈 미사용 (MPL=%s, SPECTRA=%s)", MPL_OK, SPECTRA_OK)
        return None
    try:
        spectra = _predict_spectra_all(smiles)
        if not spectra or not hasattr(spectra, 'ir_peaks') or not spectra.ir_peaks:
            logger.debug("_generate_ir_spectrum_png: IR 피크 데이터 없음 (SMILES=%s)", smiles)
            return None

        # Primary: high-quality popup renderer (fingerprint region, annotations)
        if _POPUP_SPECTRUM_OK:
            try:
                hq_fig = _popup_ir_figure(spectra.ir_peaks)
                hq_png = _figure_to_png(hq_fig, dpi=150)
                if hq_png:
                    return hq_png
            except Exception as e:
                logger.debug("popup IR figure fallback: %s", e)

        # Fallback: crude local renderer
        fig, ax = plt.subplots(figsize=(w / 100, h / 100))
        x = list(range(4000, 399, -1))
        y = [100.0] * len(x)
        for p in spectra.ir_peaks:
            wn = p.wavenumber
            strength = {"vs": 0.15, "s": 0.30, "m": 0.55, "w": 0.75, "vw": 0.90}.get(
                getattr(p, 'intensity_label', 'm'), 0.55)
            width = getattr(p, 'width', 30) or 30
            for i, xi in enumerate(x):
                lorentz = 1.0 / (1.0 + ((xi - wn) / (width / 2)) ** 2)
                y[i] = min(y[i], 100 * (1 - (1 - strength) * lorentz))
        ax.plot(x, y, 'k-', linewidth=0.7)
        ax.set_xlim(4000, 400)
        ax.set_ylim(0, 105)
        ax.set_xlabel(r"Wavenumber (cm$^{-1}$)", fontsize=8)
        ax.set_ylabel("Transmittance (%)", fontsize=8)
        _fkw_ir = {"fontproperties": _MPL_KR_FONT} if MPL_OK and _MPL_KR_FONT else {}
        ax.set_title(f"예측 IR 스펙트럼: {smiles}", fontsize=9, **_fkw_ir)
        ax.tick_params(labelsize=7)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        logger.warning("IR spectrum chart failed: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════
# 메인 보고서 생성 클래스
# ═══════════════════════════════════════════════════════════════

class PolymerLeadReportExporter:
    """고분자 리드 최적화 종합 보고서 PDF 생성기."""

    def __init__(self, data: PolymerLeadReportData):
        self.data = data
        self._fig_no = 0
        self._tbl_no = 0
        self._styles = {}
        self._setup_fonts()
        self._setup_styles()

    def _next_fig(self, caption: str) -> str:
        self._fig_no += 1
        return f"[그림 {self._fig_no}] {caption}"

    def _next_tbl(self, caption: str) -> str:
        self._tbl_no += 1
        return f"[표 {self._tbl_no}] {caption}"

    def _setup_fonts(self):
        """한글 폰트 등록."""
        if not REPORTLAB_OK:
            return
        font_paths = [
            r"C:\Windows\Fonts\malgun.ttf",
            r"C:\Windows\Fonts\malgunbd.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        ]
        self._font_name = "Helvetica"
        self._font_bold = "Helvetica-Bold"
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    base = os.path.splitext(os.path.basename(fp))[0]
                    if base not in pdfmetrics._fonts:
                        pdfmetrics.registerFont(TTFont(base, fp))
                    if "bd" in base.lower() or "bold" in base.lower():
                        self._font_bold = base
                    else:
                        self._font_name = base
                except Exception as e:
                    logger.warning("Font registration failed for '%s': %s", fp, e)

    def _setup_styles(self):
        """ParagraphStyle 사전 구성."""
        if not REPORTLAB_OK:
            return
        base = getSampleStyleSheet()
        s = {}
        s["title"] = ParagraphStyle(
            "ReportTitle", parent=base["Title"],
            fontName=self._font_bold, fontSize=22,
            textColor=_COL_WHITE, alignment=TA_CENTER, spaceAfter=6 * mm)
        s["subtitle"] = ParagraphStyle(
            "ReportSubtitle", parent=base["Normal"],
            fontName=self._font_name, fontSize=14,
            textColor=_COL_WHITE, alignment=TA_CENTER, spaceAfter=4 * mm)
        s["section"] = ParagraphStyle(
            "SectionHeader", parent=base["Heading1"],
            fontName=self._font_bold, fontSize=14,
            textColor=_COL_SECTION_NUM, spaceAfter=3 * mm, spaceBefore=5 * mm)
        s["subsection"] = ParagraphStyle(
            "SubsectionHeader", parent=base["Heading2"],
            fontName=self._font_bold, fontSize=11,
            textColor=_COL_SECTION_NUM, spaceAfter=2 * mm, spaceBefore=3 * mm)
        s["body"] = ParagraphStyle(
            "BodyText", parent=base["Normal"],
            fontName=self._font_name, fontSize=9,
            textColor=_COL_BODY, leading=14, alignment=TA_JUSTIFY,
            spaceAfter=2 * mm)
        s["caption"] = ParagraphStyle(
            "Caption", parent=base["Normal"],
            fontName=self._font_name, fontSize=8,
            textColor=_COL_CAPTION, alignment=TA_CENTER, spaceAfter=3 * mm)
        s["cell"] = ParagraphStyle(
            "Cell", parent=base["Normal"],
            fontName=self._font_name, fontSize=8,
            textColor=_COL_BODY, leading=11)
        s["cell_bold"] = ParagraphStyle(
            "CellBold", parent=s["cell"],
            fontName=self._font_bold)
        s["header_white"] = ParagraphStyle(
            "HeaderWhite", parent=s["cell"],
            fontName=self._font_bold, fontSize=8,
            textColor=_COL_WHITE, alignment=TA_CENTER)
        s["ref"] = ParagraphStyle(
            "Reference", parent=base["Normal"],
            fontName=self._font_name, fontSize=8,
            textColor=_COL_BODY, leading=11, leftIndent=10 * mm,
            firstLineIndent=-10 * mm, spaceAfter=1.5 * mm)
        self._styles = s

    def _make_table(self, data_rows, col_widths=None, has_header=True):
        """표준 테이블 생성."""
        style_cmds = [
            ("GRID", (0, 0), (-1, -1), 0.5, _COL_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        if has_header:
            style_cmds += [
                ("BACKGROUND", (0, 0), (-1, 0), _COL_TABLE_HEADER),
                ("TEXTCOLOR", (0, 0), (-1, 0), _COL_TABLE_HEADER_TEXT),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ]
            for r in range(2, len(data_rows), 2):
                style_cmds.append(("BACKGROUND", (0, r), (-1, r), _COL_TABLE_ALT))
        tbl = Table(data_rows, colWidths=col_widths, repeatRows=1 if has_header else 0)
        tbl.setStyle(TableStyle(style_cmds))
        return tbl

    def _p(self, text, style_key="body"):
        return Paragraph(str(text), self._styles[style_key])

    def _add_full_spectra_section(self, elements: List, smiles: str,
                                   prefix: str = "") -> None:
        """DryLab급 분광 분석 5종 (IR/1H-NMR/13C-NMR/UV-Vis/Mass) 섹션을 추가.

        Args:
            elements: 추가할 reportlab 요소 리스트
            smiles: 분석할 SMILES
            prefix: 캡션 접두사 (예: "원본 단량체", "선정 유도체")
        """
        spectra = _get_spectra_summary(smiles)

        # ── IR ─────────────────────────────────────────
        elements.append(self._p("■ IR 스펙트럼 예측 (이론 스펙트럼, 엔진 기반)", "subsection"))
        if "IR" in spectra and spectra["IR"]:
            ir_rows = [[self._p("파수 (cm⁻¹)", "header_white"),
                        self._p("강도", "header_white"),
                        self._p("귀속", "header_white")]]
            for p in spectra["IR"]:
                ir_rows.append([self._p(p["파수 (cm⁻¹)"], "cell"),
                                self._p(p["강도"], "cell"),
                                self._p(p["귀속"], "cell")])
            elements.append(self._make_table(ir_rows, [50*mm, 30*mm, 90*mm]))
            elements.append(self._p(
                self._next_tbl(f"{prefix} IR 스펙트럼 예측 (주요 흡수대)"), "caption"))
        ir_png = _generate_ir_spectrum_png(smiles)
        if ir_png:
            rl = _make_rl_image(ir_png, 160*mm, 70*mm)
            if rl:
                elements.append(rl)
                elements.append(self._p(
                    self._next_fig(f"{prefix} 예측 IR 스펙트럼"), "caption"))
        if "IR" not in spectra:
            elements.append(self._p("IR 예측 데이터를 불러올 수 없습니다.", "body"))

        # ── ¹H-NMR ─────────────────────────────────────
        elements.append(self._p("■ ¹H-NMR 스펙트럼 예측", "subsection"))
        if "1H-NMR" in spectra and spectra["1H-NMR"]:
            nmr_rows = [[self._p("δ (ppm)", "header_white"),
                         self._p("다중도", "header_white"),
                         self._p("적분", "header_white"),
                         self._p("귀속", "header_white")]]
            for p in spectra["1H-NMR"]:
                nmr_rows.append([self._p(p["δ (ppm)"], "cell"),
                                  self._p(p["다중도"], "cell"),
                                  self._p(p["적분"], "cell"),
                                  self._p(p["귀속"], "cell")])
            elements.append(self._make_table(nmr_rows, [35*mm, 30*mm, 30*mm, 75*mm]))
            elements.append(self._p(
                self._next_tbl(f"{prefix} ¹H-NMR 예측 화학적 이동"), "caption"))
        h_png = _generate_nmr_spectrum_png(smiles, "1H")
        if h_png:
            rl = _make_rl_image(h_png, 160*mm, 65*mm)
            if rl:
                elements.append(rl)
                elements.append(self._p(
                    self._next_fig(f"{prefix} 예측 ¹H-NMR 스펙트럼"), "caption"))

        # ── ¹³C-NMR ────────────────────────────────────
        elements.append(self._p("■ ¹³C-NMR 스펙트럼 예측", "subsection"))
        if "13C-NMR" in spectra and spectra["13C-NMR"]:
            c_rows = [[self._p("δ (ppm)", "header_white"),
                       self._p("탄소 유형", "header_white"),
                       self._p("귀속", "header_white")]]
            for p in spectra["13C-NMR"]:
                c_rows.append([self._p(p["δ (ppm)"], "cell"),
                                self._p(p["탄소 유형"], "cell"),
                                self._p(p["귀속"], "cell")])
            elements.append(self._make_table(c_rows, [40*mm, 50*mm, 80*mm]))
            elements.append(self._p(
                self._next_tbl(f"{prefix} ¹³C-NMR 예측 화학적 이동"), "caption"))
        c13_png = _generate_nmr_spectrum_png(smiles, "13C")
        if c13_png:
            rl = _make_rl_image(c13_png, 160*mm, 65*mm)
            if rl:
                elements.append(rl)
                elements.append(self._p(
                    self._next_fig(f"{prefix} 예측 ¹³C-NMR 스펙트럼"), "caption"))

        # ── UV-Vis ─────────────────────────────────────
        elements.append(self._p("■ UV-Vis 스펙트럼 예측", "subsection"))
        if "UV-Vis" in spectra and spectra["UV-Vis"]:
            uv_rows = [[self._p("λmax (nm)", "header_white"),
                        self._p("ε (L/mol·cm)", "header_white"),
                        self._p("전이 유형", "header_white")]]
            for p in spectra["UV-Vis"]:
                uv_rows.append([self._p(p["λmax (nm)"], "cell"),
                                 self._p(p["ε (L/mol·cm)"], "cell"),
                                 self._p(p["전이 유형"], "cell")])
            elements.append(self._make_table(uv_rows, [40*mm, 50*mm, 80*mm]))
            elements.append(self._p(
                self._next_tbl(f"{prefix} UV-Vis 예측 흡수대"), "caption"))
        uv_png = _generate_uvvis_spectrum_png(smiles)
        if uv_png:
            rl = _make_rl_image(uv_png, 160*mm, 65*mm)
            if rl:
                elements.append(rl)
                elements.append(self._p(
                    self._next_fig(f"{prefix} 예측 UV-Vis 스펙트럼"), "caption"))

        # ── Mass (EI-MS) ────────────────────────────────
        elements.append(self._p("■ Mass 스펙트럼 예측 (EI-MS)", "subsection"))
        mass_png = _generate_mass_spectrum_png(smiles)
        if mass_png:
            rl = _make_rl_image(mass_png, 160*mm, 65*mm)
            if rl:
                elements.append(rl)
                elements.append(self._p(
                    self._next_fig(f"{prefix} 예측 EI-MS 스펙트럼"), "caption"))
        # Mass data table from SMILES
        if RDKIT_OK:
            try:
                mol_m = Chem.MolFromSmiles(smiles)
                if mol_m is not None:  # Rule L: None guard
                    from rdkit.Chem import Descriptors as _Desc
                    exact_mw = _Desc.ExactMolWt(mol_m)
                    nom_mw = round(exact_mw, 0)
                    mass_rows = [
                        [self._p("m/z", "header_white"),
                         self._p("상대강도 (%)", "header_white"),
                         self._p("귀속", "header_white")],
                        [self._p(f"{nom_mw:.0f}", "cell"),
                         self._p("100", "cell"),
                         self._p("M⁺ (분자이온)", "cell")],
                        [self._p(f"{nom_mw+1:.0f}", "cell"),
                         self._p(f"{max(3, exact_mw * 0.011 * 10):.1f}", "cell"),
                         self._p("M+1 (¹³C 동위원소)", "cell")],
                    ]
                    elements.append(self._make_table(mass_rows, [40*mm, 50*mm, 80*mm]))
                    elements.append(self._p(
                        self._next_tbl(f"{prefix} 주요 EI-MS 단편화 이온"), "caption"))
            except Exception as e:
                logger.warning("Mass table failed: %s", e)

    # ─── 섹션 빌더 ─────────────────────────────────────

    def _build_cover(self) -> List:
        """Part 0: 표지."""
        d = self.data
        op = d.original_polymer_props
        sp = d.selected_polymer_props
        elements = []

        # 표지 배경 테이블
        cover_data = [
            [self._p("ChemGrid Pro | 고분자 리드 최적화 보고서", "subtitle")],
            [Spacer(1, 10 * mm)],
            [self._p("Polymer Lead Optimization Report", "title")],
            [Spacer(1, 5 * mm)],
            [self._p(f"원본: {op.polymer_name_kr if op else d.original_smiles}", "subtitle")],
            [self._p(f"유도체: {sp.polymer_name_kr if sp else d.selected_smiles}", "subtitle")],
            [self._p(f"최적화 목표: {d.optimization_goal}", "subtitle")],
            [Spacer(1, 10 * mm)],
        ]
        # 원본/유도체 구조 이미지
        orig_png = _smiles_to_png(d.original_smiles, 250, 200)
        sel_png = _smiles_to_png(d.selected_smiles, 250, 200) if d.selected_smiles else None
        img_row = []
        if orig_png:
            img_row.append(_make_rl_image(orig_png, 60 * mm, 50 * mm))
        if sel_png:
            img_row.append(self._p("  →  ", "subtitle"))
            img_row.append(_make_rl_image(sel_png, 60 * mm, 50 * mm))
        if img_row:
            cover_data.append([Table([img_row], colWidths=None)])

        cover_data += [
            [Spacer(1, 10 * mm)],
            [self._p(f"작성일: {datetime.now().strftime('%Y-%m-%d')}", "subtitle")],
            [self._p("작성 엔진: Van Krevelen Group Contribution + RDKit QSPR Hybrid", "subtitle")],
        ]

        cover_tbl = Table(cover_data, colWidths=[170 * mm])
        cover_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _COL_HEADER_BG),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        elements.append(cover_tbl)
        elements.append(PageBreak())
        return elements

    def _build_part1_original_monomer(self) -> List:
        """Part 1: 원본 단량체 분석."""
        d = self.data
        smi = d.original_smiles
        elements = []

        elements.append(self._p("Part 1. 원본 단량체 분석", "section"))
        elements.append(HRFlowable(width="100%", thickness=1, color=_COL_SECTION_LINE))

        # 1.1 분자 구조
        elements.append(self._p("1.1 분자 구조", "subsection"))
        img_png = _smiles_to_png(smi, 350, 280)
        if img_png:
            rl_img = _make_rl_image(img_png, 80 * mm, 60 * mm)
            if rl_img:
                elements.append(rl_img)
                elements.append(self._p(self._next_fig("원본 단량체 2D 구조"), "caption"))

        # 1.2 RDKit 디스크립터
        elements.append(self._p("1.2 분자 디스크립터 (RDKit 계산)", "subsection"))
        desc = _get_rdkit_descriptors(smi)
        if desc:
            rows = [[self._p("디스크립터", "header_white"),
                     self._p("값", "header_white"),
                     self._p("계산 엔진", "header_white")]]
            for k, v in desc.items():
                rows.append([self._p(k, "cell"), self._p(str(v), "cell"),
                             self._p("RDKit 2025.09", "cell")])
            elements.append(self._make_table(rows, [70 * mm, 50 * mm, 50 * mm]))
            elements.append(self._p(self._next_tbl("원본 단량체 분자 디스크립터"), "caption"))

        # 1.3 분광 분석 예측 (DryLab급 5종)
        elements.append(self._p("1.3 분광 분석 예측 (이론 스펙트럼, 5종)", "subsection"))
        elements.append(self._p(
            "ChemGrid 6계층 분광 예측 엔진 (Gold Standard DB → Shoolery/Grant-Paul/"
            "Woodward-Fieser 경험 규칙 → SMARTS 상관표 → RDKit 디스크립터)을 "
            "사용하여 IR, ¹H-NMR, ¹³C-NMR, UV-Vis, Mass(EI-MS) 스펙트럼을 "
            "전량 이론적으로 예측하였다. 모든 스펙트럼은 ChemGrid 팝업과 동일 양식으로 "
            "표시된다(\"이론적 스펙트럼, 엔진 기반\" 표기).", "body"))

        self._add_full_spectra_section(elements, smi, prefix="원본 단량체")

        elements.append(PageBreak())
        return elements

    def _build_part2_original_polymer(self) -> List:
        """Part 2: 원본 중합체 물성."""
        op = self.data.original_polymer_props
        if not op:
            logger.debug("_build_part2_original_polymer: 원본 중합체 물성 데이터 없음")
            return []
        elements = []
        elements.append(self._p("Part 2. 원본 중합체 물성 분석", "section"))
        elements.append(HRFlowable(width="100%", thickness=1, color=_COL_SECTION_LINE))

        elements.append(self._p(
            f"Van Krevelen 그룹 기여법과 RDKit 분자 디스크립터 QSPR 보정을 결합한 "
            f"하이브리드 엔진으로 예측한 {op.polymer_name_kr}의 물성이다.", "body"))

        # 2.1 기본 정보
        elements.append(self._p("2.1 중합 유형 및 반복단위", "subsection"))
        info_rows = [
            [self._p("항목", "header_white"), self._p("값", "header_white")],
            [self._p("중합 유형", "cell_bold"), self._p(op.poly_type, "cell")],
            [self._p("반복단위 SMILES", "cell_bold"), self._p(op.repeat_unit_smiles, "cell")],
            [self._p("반복단위 분자량", "cell_bold"), self._p(f"{op.M_repeat} g/mol", "cell")],
            [self._p("그룹 분해", "cell_bold"), self._p(
                ", ".join(f"{g}×{n}" for g, n in op.group_decomposition.items()), "cell")],
        ]
        if op.is_gold_standard:
            info_rows.append([self._p("데이터 소스", "cell_bold"),
                              self._p("Gold Standard (문헌값)", "cell")])
        elements.append(self._make_table(info_rows, [60 * mm, 110 * mm]))
        elements.append(self._p(self._next_tbl("원본 중합체 기본 정보"), "caption"))

        # 2.2 열적 특성
        elements.append(self._p("2.2 열적 특성", "subsection"))
        th_rows = [
            [self._p("물성", "header_white"), self._p("기호", "header_white"),
             self._p("값", "header_white"), self._p("단위", "header_white"),
             self._p("예측 근거", "header_white")],
            [self._p("유리전이온도", "cell"), self._p("Tg", "cell"),
             self._p(f"{op.Tg}", "cell"), self._p("℃", "cell"),
             self._p("ΣYg/M + RDKit 보정", "cell")],
            [self._p("녹는점", "cell"), self._p("Tm", "cell"),
             self._p(f"{op.Tm}", "cell"), self._p("℃", "cell"),
             self._p("Boyer-Beaman rule (Td 상한)", "cell")],
            [self._p("열분해온도", "cell"), self._p("Td", "cell"),
             self._p(f"{op.Td}", "cell"), self._p("℃", "cell"),
             self._p("가중평균 BDE", "cell")],
            [self._p("최대사용온도", "cell"), self._p("Tmax", "cell"),
             self._p(f"{op.max_service_temp}", "cell"), self._p("℃", "cell"),
             self._p("min(Td-50, Tm-20)", "cell")],
            [self._p("열팽창계수", "cell"), self._p("CTE", "cell"),
             self._p(f"{op.CTE}", "cell"), self._p("×10⁻⁶/K", "cell"),
             self._p("Tg 역상관 경험식", "cell")],
            [self._p("열전도도", "cell"), self._p("λ", "cell"),
             self._p(f"{op.thermal_conductivity}", "cell"), self._p("W/(m·K)", "cell"),
             self._p("밀도 비례 경험식", "cell")],
        ]
        elements.append(self._make_table(th_rows, [35*mm, 15*mm, 25*mm, 25*mm, 70*mm]))
        elements.append(self._p(self._next_tbl("원본 중합체 열적 특성"), "caption"))

        # 2.3 기계적/광학적 특성
        elements.append(self._p("2.3 기계적 및 광학적 특성", "subsection"))
        mech_rows = [
            [self._p("물성", "header_white"), self._p("값", "header_white"),
             self._p("단위", "header_white"), self._p("예측 근거", "header_white")],
            [self._p("인장강도 (σ)", "cell"), self._p(f"{op.tensile_strength}", "cell"),
             self._p("MPa", "cell"), self._p("ρ×δ×Tg 복합 경험식", "cell")],
            [self._p("영률 (E)", "cell"), self._p(f"{op.youngs_modulus}", "cell"),
             self._p("MPa", "cell"), self._p("Tg+밀도 상관", "cell")],
            [self._p("파단 신장률 (ε)", "cell"), self._p(f"{op.elongation_at_break}", "cell"),
             self._p("%", "cell"), self._p("Tg 기반 유리질/고무질 분류", "cell")],
            [self._p("밀도 (ρ)", "cell"), self._p(f"{op.density}", "cell"),
             self._p("g/cm³", "cell"), self._p("M/ΣV + F질량분율 보정", "cell")],
            [self._p("굴절률 (n)", "cell"), self._p(f"{op.refractive_index}", "cell"),
             self._p("-", "cell"), self._p("Lorentz-Lorenz + F 보정", "cell")],
            [self._p("용해도 파라미터 (δ)", "cell"), self._p(f"{op.solubility_param}", "cell"),
             self._p("(MJ/m³)^0.5", "cell"), self._p("√(ΣEcoh/ΣV)", "cell")],
        ]
        elements.append(self._make_table(mech_rows, [45*mm, 30*mm, 30*mm, 65*mm]))
        elements.append(self._p(self._next_tbl("원본 중합체 기계적/광학적 특성"), "caption"))

        elements.append(PageBreak())
        return elements

    def _build_part3_methodology(self) -> List:
        """Part 3: 리드 최적화 방법론."""
        d = self.data
        elements = []
        elements.append(self._p("Part 3. 리드 최적화 방법론", "section"))
        elements.append(HRFlowable(width="100%", thickness=1, color=_COL_SECTION_LINE))

        # 3.1 최적화 목표
        elements.append(self._p("3.1 최적화 목표", "subsection"))
        elements.append(self._p(
            f"본 리드 최적화의 목표는 <b>'{d.optimization_goal}'</b>이다. "
            f"원본 단량체 {d.original_smiles}의 중합체를 기반으로, 치환기 교체/삽입/확장 전략을 통해 "
            f"목표 물성이 향상된 유도체를 탐색하였다.", "body"))

        if d.optimization_weights and isinstance(d.optimization_weights, dict):
            w_rows = [[self._p("물성 항목", "header_white"),
                       self._p("가중치", "header_white")]]
            for k, v in d.optimization_weights.items():
                if not isinstance(k, str):
                    continue
                if k.startswith("weight_"):
                    prop_name = k.replace("weight_", "")
                    w_rows.append([self._p(prop_name, "cell"), self._p(f"{v}", "cell")])
            elements.append(self._make_table(w_rows, [90 * mm, 80 * mm]))
            elements.append(self._p(self._next_tbl("최적화 가중치 설정"), "caption"))

        # 3.2 사용 엔진
        elements.append(self._p("3.2 사용 엔진 및 계산 기반", "subsection"))
        engine_rows = [
            [self._p("계산 항목", "header_white"), self._p("엔진/방법", "header_white"),
             self._p("이론적 근거", "header_white")],
            [self._p("유도체 생성", "cell"),
             self._p("SMARTS 기반 치환기 라이브러리 (15종)", "cell"),
             self._p("RDKit Chem.MolFromSmiles + 유효성 검증", "cell")],
            [self._p("중합 가능성 판별", "cell"),
             self._p("SMARTS 패턴 매칭", "cell"),
             self._p("비닐/축합/개환 3종 중합 유형", "cell")],
            [self._p("반복단위 변환", "cell"),
             self._p("RDKit RWMol C=C 개환", "cell"),
             self._p("비닐 이중결합 → 단일결합 + 더미 원자", "cell")],
            [self._p("그룹 분해", "cell"),
             self._p("SMARTS 순서 매칭 (큰 그룹 우선)", "cell"),
             self._p("Van Krevelen 작용기 가산법", "cell")],
            [self._p("Tg 예측", "cell"),
             self._p("ΣYg/M + RDKit 디스크립터 보정", "cell"),
             self._p("Van Krevelen (4th ed.) + 회전결합/방향족/F보정", "cell")],
            [self._p("Tm 예측", "cell"),
             self._p("Boyer-Beaman rule + Td 상한", "cell"),
             self._p("Tm/Tg ≈ 1.5(대칭), 2.0(비대칭); Tm < Td-30", "cell")],
            [self._p("Td 예측", "cell"),
             self._p("가중평균 BDE 경험식", "cell"),
             self._p("결합 분해 에너지 (C-F 485, C-C 348, C-O 360 kJ/mol)", "cell")],
            [self._p("밀도 예측", "cell"),
             self._p("M/ΣV + RDKit F질량분율 보정", "cell"),
             self._p("Van Krevelen 몰부피 가산 + 불소 경험 보정", "cell")],
            [self._p("인장강도", "cell"),
             self._p("ρ×δ×Tg 복합식", "cell"),
             self._p("응집에너지밀도 + 유리전이 기여", "cell")],
            [self._p("굴절률", "cell"),
             self._p("Lorentz-Lorenz + F 보정", "cell"),
             self._p("몰굴절 가산 + 불소 분극률 보정", "cell")],
            [self._p("분광 예측", "cell"),
             self._p("ChemGrid 6계층 엔진", "cell"),
             self._p("Silverstein/Pavia SMARTS + Shoolery/Grant-Paul 경험식", "cell")],
            [self._p("스코어링", "cell"),
             self._p("가중 정규화 합산 (0~1)", "cell"),
             self._p("각 물성 정규화 후 목표 가중치 적용", "cell")],
        ]
        elements.append(self._make_table(engine_rows, [40*mm, 60*mm, 70*mm]))
        elements.append(self._p(self._next_tbl("사용 엔진 및 이론적 근거"), "caption"))

        # 3.3 전체 유도체 후보 목록
        elements.append(self._p("3.3 전체 유도체 후보 목록", "subsection"))
        if d.all_variants:
            elements.append(self._p(
                f"총 {len(d.all_variants)}개의 유도체 후보가 생성되었으며, "
                f"'{d.optimization_goal}' 목표 기준 스코어링 결과를 순위별로 나열한다.", "body"))
            var_rows = [[self._p("#", "header_white"),
                         self._p("SMILES", "header_white"),
                         self._p("변형 설명", "header_white"),
                         self._p("Tg(℃)", "header_white"),
                         self._p("Td(℃)", "header_white"),
                         self._p("Score", "header_white")]]
            for i, v in enumerate(d.all_variants):
                # N코드: 외부 데이터 타입 가드 — v가 dict인지 확인
                if not isinstance(v, dict):
                    logger.warning("all_variants[%d] is not dict: type=%s", i, type(v).__name__)
                    continue
                # props 객체에서 Tg/Td 추출
                vp = v.get("props", None)
                tg_str = f"{vp.Tg:.1f}" if vp and hasattr(vp, 'Tg') else "-"
                td_str = f"{vp.Td:.1f}" if vp and hasattr(vp, 'Td') else "-"
                v_smiles = v.get("smiles", "")
                if not isinstance(v_smiles, str):
                    v_smiles = str(v_smiles) if v_smiles is not None else ""
                v_desc = v.get("description", "")
                if not isinstance(v_desc, str):
                    v_desc = str(v_desc) if v_desc is not None else ""
                v_score = v.get("score", 0)
                if not isinstance(v_score, (int, float)):
                    try:
                        v_score = float(v_score)
                    except (TypeError, ValueError):
                        logger.warning("all_variants[%d] score is not numeric: %s", i, v_score)
                        v_score = 0.0
                var_rows.append([
                    self._p(f"{i+1}", "cell"),
                    self._p(v_smiles[:30], "cell"),
                    self._p(v_desc, "cell"),
                    self._p(tg_str, "cell"),
                    self._p(td_str, "cell"),
                    self._p(f"{v_score:.4f}", "cell"),
                ])
            elements.append(self._make_table(
                var_rows, [10*mm, 45*mm, 50*mm, 20*mm, 20*mm, 25*mm]))
            elements.append(self._p(self._next_tbl("전체 유도체 후보 목록 및 스코어"), "caption"))
        else:
            elements.append(self._p("유도체 후보 목록이 제공되지 않았습니다.", "body"))

        elements.append(PageBreak())
        return elements

    def _build_part3b_polymerization_mechanism(self) -> List:
        """Part 3b: 중합 반응 메커니즘 3D 시각화.

        유효충돌 방향, 전이상태 구조, 충돌 파라미터 요약 표를 포함한다.
        """
        d = self.data
        smi = d.selected_smiles or d.original_smiles
        sp = d.selected_polymer_props or d.original_polymer_props
        poly_type = getattr(sp, 'poly_type', 'addition') if sp else 'addition'
        elements = []

        elements.append(self._p("Part 3b. 중합 반응 메커니즘 3D 시각화", "section"))
        elements.append(HRFlowable(width="100%", thickness=1, color=_COL_SECTION_LINE))
        elements.append(self._p(
            "중합 반응의 유효충돌 방향과 전이상태 구조를 3D 시각화하여, "
            "분자 수준에서의 반응 메커니즘을 이해한다.", "body"))

        # ── 3b.1 유효충돌 방향 시각화 ──
        elements.append(self._p("3b.1 유효충돌 방향 시각화", "subsection"))

        collision_png = _generate_collision_mechanism_3d_png(smi, poly_type)
        if collision_png:
            rl = _make_rl_image(collision_png, 155 * mm, 100 * mm)
            if rl:
                elements.append(rl)
                elements.append(self._p(
                    self._next_fig("단량체 유효충돌 방향 3D 시각화 "
                                   "(적색: 반응 활성점, 주황 점선: 형성 결합, 적색 화살표: 충돌 벡터)"),
                    "caption"))

        # 중합 유형별 설명
        poly_desc = {
            'addition': (
                "비닐 단량체의 첨가 중합에서 유효충돌은 두 C=C 이중결합이 면대면(face-to-face)으로 "
                "접근하여 π 전자 궤도가 중첩되는 방향으로 일어난다. "
                "충돌 축은 C=C 평면에 수직이며, π 전자 상호작용은 약 3.5 Å에서 시작되어 "
                "전이상태(~2.0 Å)를 거쳐 σ 결합(1.54 Å)이 형성된다."
            ),
            'radical': (
                "라디칼 첨가 중합에서 성장 라디칼은 단량체의 C=C 이중결합에 면대면으로 접근한다. "
                "라디칼-단량체 간 유효충돌 방향 인자(p)는 약 0.1~0.3이며, "
                "충돌 에너지가 활성화 에너지(Ea ≈ 20~40 kJ/mol)를 초과해야 반응이 진행된다."
            ),
            'condensation': (
                "축합 중합에서 유효충돌은 친핵체(OH)가 친전자체(C=O, 카보닐)에 "
                "약 109°의 Bürgi-Dunitz 각도로 접근하는 head-on 방향이다. "
                "반응 과정에서 H₂O 분자가 이탈하며 새로운 공유결합이 형성된다. "
                "활성화 에너지는 약 40~80 kJ/mol이다."
            ),
            'step_growth': (
                "단계적 성장 중합에서는 두 작용기가 head-on으로 접근하며, "
                "각 단계마다 소분자(H₂O, HCl 등)가 부산물로 생성된다. "
                "유효충돌 조건은 적절한 방향성과 충분한 운동 에너지를 모두 만족해야 한다."
            ),
            'ring_opening': (
                "개환 중합에서 친핵체는 변형된 고리(에폭사이드, 락톤 등)의 "
                "탄소 원자에 후면(back-side)에서 SN2형으로 접근한다. "
                "고리 변형 에너지가 반응의 열역학적 구동력을 제공하며, "
                "활성화 에너지는 약 25~50 kJ/mol이다."
            ),
        }
        # Rule N: isinstance guard for poly_desc
        if not isinstance(poly_desc, dict): poly_desc = {}
        desc_text = poly_desc.get(poly_type, poly_desc['addition'])
        elements.append(self._p(desc_text, "body"))

        # ── 3b.2 전이상태 구조 ──
        elements.append(self._p("3b.2 전이상태 구조", "subsection"))

        ts_png = _generate_transition_state_3d_png(smi, poly_type)
        if ts_png:
            rl = _make_rl_image(ts_png, 155 * mm, 95 * mm)
            if rl:
                elements.append(rl)
                elements.append(self._p(
                    self._next_fig("전이상태 구조 3D + 에너지 프로파일 "
                                   "(주황 점선: 형성 중인 부분 결합, ‡: 전이상태)"),
                    "caption"))

        # Activation energy description by type
        ea_info = {
            'addition': ("20~40", "라디칼", "1.54"),
            'radical': ("20~40", "라디칼", "1.54"),
            'condensation': ("40~80", "이온", "1.47"),
            'step_growth': ("40~80", "단계적 성장", "1.47"),
            'ring_opening': ("25~50", "개환", "1.54"),
        }
        # Rule N: isinstance guard for ea_info
        if not isinstance(ea_info, dict): ea_info = {}
        ea_range, mech_type, bond_len = ea_info.get(poly_type,
                                                     ("20~40", "일반", "1.54"))
        elements.append(self._p(
            f"전이상태에서 형성 중인 C···C 부분 결합의 거리는 약 2.0 Å이며, "
            f"이는 완전한 공유 결합({bond_len} Å)보다 길다. "
            f"{mech_type} 중합의 활성화 에너지(Ea)는 약 {ea_range} kJ/mol 범위이다. "
            f"전이상태를 넘어서면 발열 반응으로 생성물이 안정화된다.", "body"))

        # ── 충돌 파라미터 요약 표 ──
        elements.append(self._p("3b.3 충돌 파라미터 요약", "subsection"))

        steric_map = {
            'addition': "0.1~0.3",
            'radical': "0.1~0.3",
            'condensation': "0.01~0.1",
            'step_growth': "0.01~0.1",
            'ring_opening': "0.05~0.2",
        }
        collision_dir_map = {
            'addition': "C=C 면대면 (수직 접근)",
            'radical': "C=C 면대면 (수직 접근)",
            'condensation': "작용기 head-on (Bürgi-Dunitz 109°)",
            'step_growth': "작용기 head-on",
            'ring_opening': "고리 탄소 후면 공격 (SN2형)",
        }

        # Rule N: isinstance guard for collision_dir_map
        if not isinstance(collision_dir_map, dict):
            collision_dir_map = {}
        param_rows = [
            [self._p("파라미터", "header_white"),
             self._p("값", "header_white"),
             self._p("설명", "header_white")],
            [self._p("유효충돌 방향", "cell"),
             self._p(collision_dir_map.get(poly_type, "면대면 접근"), "cell"),
             self._p("반응 활성점 간의 최적 접근 기하학", "cell")],
            [self._p("활성화 에너지 (Ea)", "cell"),
             self._p(f"{ea_range} kJ/mol", "cell"),
             self._p(f"{mech_type} 중합 문헌값 범위 (Odian, 4th ed.)", "cell")],
            [self._p("입체 인자 (p)", "cell"),
             self._p(steric_map.get(poly_type, "0.1~0.3"), "cell"),
             self._p("유효충돌 비율 = 올바른 방향의 충돌 / 전체 충돌", "cell")],
            [self._p("전이상태 거리", "cell"),
             self._p("~2.0 Å", "cell"),
             self._p("형성 중인 부분 결합(C···C)의 핵간 거리", "cell")],
            [self._p("최종 결합 거리", "cell"),
             self._p(f"{bond_len} Å", "cell"),
             self._p("완전 형성된 공유 σ 결합 길이", "cell")],
        ]
        elements.append(self._make_table(param_rows, [45 * mm, 45 * mm, 80 * mm]))
        elements.append(self._p(
            self._next_tbl("충돌 파라미터 요약 (유효충돌 방향, 활성화에너지, 입체인자)"),
            "caption"))

        elements.append(PageBreak())
        return elements

    def _build_part4_derivative_monomer(self) -> List:
        """Part 4: 선정 유도체 단량체 분석."""
        d = self.data
        smi = d.selected_smiles
        if not smi:
            logger.debug("_build_part4_derivative_monomer: 선정 유도체 SMILES 없음")
            return []
        elements = []
        elements.append(self._p("Part 4. 선정 유도체 단량체 분석", "section"))
        elements.append(HRFlowable(width="100%", thickness=1, color=_COL_SECTION_LINE))

        elements.append(self._p(
            f"리드 최적화 결과 최고 스코어({d.selected_score:.4f})를 기록한 "
            f"유도체 <b>{d.selected_description}</b>를 선정하였다. "
            f"SMILES: {smi}", "body"))

        # 4.1 구조
        elements.append(self._p("4.1 유도체 분자 구조", "subsection"))
        img_png = _smiles_to_png(smi, 350, 280)
        if img_png:
            rl = _make_rl_image(img_png, 80 * mm, 60 * mm)
            if rl:
                elements.append(rl)
                elements.append(self._p(self._next_fig("선정 유도체 2D 구조"), "caption"))

        # 4.2 디스크립터
        elements.append(self._p("4.2 유도체 분자 디스크립터", "subsection"))
        desc = _get_rdkit_descriptors(smi)
        if desc:
            rows = [[self._p("디스크립터", "header_white"),
                     self._p("값", "header_white")]]
            for k, v in desc.items():
                rows.append([self._p(k, "cell"), self._p(str(v), "cell")])
            elements.append(self._make_table(rows, [90 * mm, 80 * mm]))
            elements.append(self._p(self._next_tbl("유도체 분자 디스크립터"), "caption"))

        # 4.3 분광 분석 (DryLab급 5종)
        elements.append(self._p("4.3 유도체 분광 분석 예측 (이론 스펙트럼, 5종)", "subsection"))
        elements.append(self._p(
            "원본 단량체와 동일한 6계층 분광 예측 엔진을 사용하여 선정 유도체의 "
            "IR, ¹H-NMR, ¹³C-NMR, UV-Vis, Mass 스펙트럼을 예측하였다. "
            "원본과의 피크 위치/강도 차이를 통해 구조 변경의 영향을 확인할 수 있다.", "body"))

        self._add_full_spectra_section(elements, smi, prefix="선정 유도체")

        elements.append(PageBreak())
        return elements

    def _build_part5_derivative_polymer(self) -> List:
        """Part 5: 유도체 중합체 물성."""
        sp = self.data.selected_polymer_props
        if not sp:
            logger.debug("_build_part5_derivative_polymer: 유도체 중합체 물성 데이터 없음")
            return []
        elements = []
        elements.append(self._p("Part 5. 유도체 중합체 물성 분석", "section"))
        elements.append(HRFlowable(width="100%", thickness=1, color=_COL_SECTION_LINE))

        # 동일 구조로 Part 2 반복
        elements.append(self._p("5.1 중합 유형 및 그룹 분해", "subsection"))
        info_rows = [
            [self._p("항목", "header_white"), self._p("값", "header_white")],
            [self._p("중합 유형", "cell_bold"), self._p(sp.poly_type, "cell")],
            [self._p("반복단위", "cell_bold"), self._p(sp.repeat_unit_smiles, "cell")],
            [self._p("반복단위 MW", "cell_bold"), self._p(f"{sp.M_repeat} g/mol", "cell")],
            [self._p("그룹 분해", "cell_bold"),
             self._p(", ".join(f"{g}×{n}" for g, n in sp.group_decomposition.items()), "cell")],
        ]
        elements.append(self._make_table(info_rows, [60*mm, 110*mm]))
        elements.append(self._p(self._next_tbl("유도체 중합체 기본 정보"), "caption"))

        # 전체 물성표
        elements.append(self._p("5.2 전체 물성 요약", "subsection"))
        all_rows = [
            [self._p("물성", "header_white"), self._p("값", "header_white"),
             self._p("단위", "header_white")],
        ]
        props_list = [
            ("Tg", sp.Tg, "℃"), ("Tm", sp.Tm, "℃"), ("Td", sp.Td, "℃"),
            ("최대사용온도", sp.max_service_temp, "℃"),
            ("밀도", sp.density, "g/cm³"), ("인장강도", sp.tensile_strength, "MPa"),
            ("영률", sp.youngs_modulus, "MPa"), ("신장률", sp.elongation_at_break, "%"),
            ("굴절률", sp.refractive_index, "-"), ("CTE", sp.CTE, "×10⁻⁶/K"),
            ("열전도도", sp.thermal_conductivity, "W/(m·K)"),
            ("δ", sp.solubility_param, "(MJ/m³)^0.5"),
        ]
        for name, val, unit in props_list:
            all_rows.append([self._p(name, "cell"), self._p(f"{val}", "cell"),
                             self._p(unit, "cell")])
        elements.append(self._make_table(all_rows, [60*mm, 55*mm, 55*mm]))
        elements.append(self._p(self._next_tbl("유도체 중합체 전체 물성"), "caption"))

        elements.append(PageBreak())
        return elements

    def _build_part6_comparison(self) -> List:
        """Part 6: 원본 vs 유도체 대조 분석."""
        d = self.data
        op = d.original_polymer_props
        sp = d.selected_polymer_props
        if not op or not sp:
            logger.debug("_build_part6_comparison: 비교 데이터 불충분 (op=%s, sp=%s)", bool(op), bool(sp))
            return []
        elements = []
        elements.append(self._p("Part 6. 원본 vs 유도체 대조 분석", "section"))
        elements.append(HRFlowable(width="100%", thickness=1, color=_COL_SECTION_LINE))

        # 6.1 비교표
        elements.append(self._p("6.1 물성 비교표", "subsection"))
        cmp_rows = [
            [self._p("물성", "header_white"), self._p("원본", "header_white"),
             self._p("유도체", "header_white"), self._p("변화", "header_white"),
             self._p("변화율", "header_white")],
        ]
        # N코드: 속성 접근 전 타입 가드 — 숫자 값 안전 추출 헬퍼
        def _safe_num(obj, attr: str, default: float = 0.0) -> float:
            val = getattr(obj, attr, default)
            if not isinstance(val, (int, float)):
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    logger.warning("Property '%s' is not numeric: %s (type=%s)",
                                   attr, val, type(val).__name__)
                    val = default
            return val

        comparisons = [
            ("Tg (℃)", _safe_num(op, 'Tg'), _safe_num(sp, 'Tg')),
            ("Tm (℃)", _safe_num(op, 'Tm'), _safe_num(sp, 'Tm')),
            ("Td (℃)", _safe_num(op, 'Td'), _safe_num(sp, 'Td')),
            ("밀도 (g/cm³)", _safe_num(op, 'density'), _safe_num(sp, 'density')),
            ("인장강도 (MPa)", _safe_num(op, 'tensile_strength'), _safe_num(sp, 'tensile_strength')),
            ("영률 (MPa)", _safe_num(op, 'youngs_modulus'), _safe_num(sp, 'youngs_modulus')),
            ("굴절률", _safe_num(op, 'refractive_index'), _safe_num(sp, 'refractive_index')),
            ("CTE (×10⁻⁶/K)", _safe_num(op, 'CTE'), _safe_num(sp, 'CTE')),
            ("δ (MJ/m³)^0.5", _safe_num(op, 'solubility_param'), _safe_num(sp, 'solubility_param')),
        ]
        for name, orig_v, deriv_v in comparisons:
            delta = deriv_v - orig_v
            pct = (delta / abs(orig_v) * 100) if orig_v != 0 else 0
            sign = "↑" if delta > 0 else "↓" if delta < 0 else "="
            cmp_rows.append([
                self._p(name, "cell"),
                self._p(f"{orig_v}", "cell"),
                self._p(f"{deriv_v}", "cell"),
                self._p(f"{sign} {abs(delta):.1f}", "cell"),
                self._p(f"{pct:+.1f}%", "cell"),
            ])
        elements.append(self._make_table(cmp_rows, [40*mm, 30*mm, 30*mm, 35*mm, 35*mm]))
        elements.append(self._p(self._next_tbl("원본 vs 유도체 물성 비교"), "caption"))

        # 6.2 레이더 차트
        elements.append(self._p("6.2 물성 비교 레이더 차트", "subsection"))
        radar_png = _generate_radar_png(op, sp)
        if radar_png:
            rl = _make_rl_image(radar_png, 130 * mm, 100 * mm)
            if rl:
                elements.append(rl)
                elements.append(self._p(self._next_fig("원본 vs 유도체 물성 레이더 차트"), "caption"))

        # 6.3 유도체의 의의
        elements.append(self._p("6.3 유도체의 의의", "subsection"))
        tg_delta = _safe_num(sp, 'Tg') - _safe_num(op, 'Tg')
        td_delta = _safe_num(sp, 'Td') - _safe_num(op, 'Td')
        sig_text = (
            f"선정 유도체({d.selected_description})는 원본 대비 Tg가 {tg_delta:+.1f}℃ "
            f"{'상승' if tg_delta > 0 else '하강'}하였으며, "
            f"Td가 {td_delta:+.1f}℃ {'상승' if td_delta > 0 else '하강'}하였다. "
        )
        if tg_delta > 0:
            sig_text += (
                f"Tg 상승은 치환기 변경에 의한 주쇄 회전 장벽 증가(사슬 강성 향상)에 기인하며, "
                f"이는 고온 환경에서의 치수 안정성과 경도를 개선한다. "
            )
        density_delta = _safe_num(sp, 'density') - _safe_num(op, 'density')
        sig_text += (
            f"밀도는 {density_delta:+.3f} g/cm³ 변화하였으며, "
            f"{'경량화에 유리하다' if density_delta < 0 else '내구성 향상이 기대된다'}. "
        )
        if d.ai_text:
            sig_text += d.ai_text
        elements.append(self._p(sig_text, "body"))

        elements.append(PageBreak())
        return elements

    def _build_part7_synthesis(self) -> List:
        """Part 7: 합성 프로토콜 (DryLab급 구체적 실험 — Organic Syntheses 표준)."""
        d = self.data
        smi = d.selected_smiles or d.original_smiles
        sp = d.selected_polymer_props or d.original_polymer_props
        poly_name = sp.polymer_name_kr if sp else smi
        poly_type = getattr(sp, 'poly_type', 'addition') if sp else 'addition'
        elements = []
        elements.append(self._p("Part 7. 중합 반응 합성 프로토콜", "section"))
        elements.append(HRFlowable(width="100%", thickness=1, color=_COL_SECTION_LINE))

        # 분자량 계산
        mono_mw = 100.0
        mono_mmol = 100.0
        if RDKIT_OK:
            try:
                mol_tmp = Chem.MolFromSmiles(smi)
                if mol_tmp is not None:  # Rule L: None guard
                    from rdkit.Chem import Descriptors as _Desc
                    mono_mw = round(_Desc.MolWt(mol_tmp), 2)
                    mono_mmol = round(10000.0 / mono_mw, 1)  # 10.0 g 기준 mmol
            except Exception as e:
                logger.warning("Monomer molecular weight calculation failed: %s", e)

        # 라디칼 vs 축합 중합 판별 (poly_type 기반)
        is_radical = poly_type in ('addition', 'radical', '')
        is_condensation = poly_type in ('condensation', 'step_growth')

        elements.append(self._p(
            f"본 장에서는 선정 유도체 단량체 (SMILES: {smi}, MW: {mono_mw:.1f} g/mol)의 "
            f"{'라디칼 첨가 중합' if is_radical else '축합 중합'} 전 과정을 "
            f"Organic Syntheses / Odian \"Principles of Polymerization\" (4th ed.) 기준으로 "
            f"전공서 수준으로 상세 기술한다. "
            f"모든 시약량은 단량체 10.0 g ({mono_mmol:.1f} mmol) 기준으로 계산하였다.", "body"))

        # ── 7.1 시약 목록 (8열: 시약명/분자식/MW/사용량/당량/위험등급/제조사/순도) ──
        elements.append(self._p("7.1 시약 목록 (Organic Syntheses 표준 8열)", "subsection"))
        elements.append(self._p(
            "하기 시약 목록은 Organic Syntheses 투고 기준 (8열 형식)으로 작성되었다. "
            "당량(equiv.)은 단량체 1.0 equiv. 기준이다.", "body"))

        # 8열 헤더
        rg_hdr = [self._p("시약명", "header_white"),
                  self._p("분자식", "header_white"),
                  self._p("MW (g/mol)", "header_white"),
                  self._p("사용량", "header_white"),
                  self._p("당량 (equiv.)", "header_white"),
                  self._p("위험등급 (GHS)", "header_white"),
                  self._p("제조사", "header_white"),
                  self._p("순도", "header_white")]

        aibn_mmol = round(mono_mmol * 0.01, 2)   # 1 mol%
        aibn_g = round(aibn_mmol * 164.21 / 1000, 3)
        solv_ml = 30
        meoh_ml = int(mono_mmol * 3.5)  # ~200 mL 기준

        reagent_data = [
            rg_hdr,
            [self._p(f"단량체 ({smi[:25]}...)" if len(smi) > 25 else f"단량체 ({smi})", "cell_bold"),
             self._p("—", "cell"), self._p(f"{mono_mw:.1f}", "cell"),
             self._p(f"10.0 g ({mono_mmol:.1f} mmol)", "cell"),
             self._p("1.00", "cell"), self._p("자극성 (GHS07)", "cell"),
             self._p("Sigma-Aldrich", "cell"), self._p("≥99%, 무수", "cell")],
            [self._p("AIBN (아조비스이소부티로니트릴)", "cell"),
             self._p("C₈H₁₂N₄", "cell"), self._p("164.21", "cell"),
             self._p(f"{aibn_g:.3f} g ({aibn_mmol:.2f} mmol)", "cell"),
             self._p("0.010", "cell"), self._p("자기반응성 (GHS02)", "cell"),
             self._p("TCI", "cell"), self._p("≥98%, 재결정 정제", "cell")],
            [self._p("BPO (과산화벤조일, 대체)", "cell"),
             self._p("C₁₄H₁₀O₄", "cell"), self._p("242.23", "cell"),
             self._p("0.15 g (0.62 mmol)", "cell"),
             self._p("0.006", "cell"), self._p("산화성/자기반응성 (GHS03/02)", "cell"),
             self._p("Sigma-Aldrich", "cell"), self._p("75% 습윤 유지", "cell")],
            [self._p("무수 톨루엔 (anhydrous toluene)", "cell"),
             self._p("C₇H₈", "cell"), self._p("92.14", "cell"),
             self._p(f"{solv_ml} mL", "cell"),
             self._p("—", "cell"), self._p("인화성/독성 (GHS02/06)", "cell"),
             self._p("Sigma-Aldrich", "cell"), self._p("≥99.8%, Sure/Seal", "cell")],
            [self._p("트리플루오로톨루엔 (PhCF₃, 대체 용매)", "cell"),
             self._p("C₇H₅F₃", "cell"), self._p("146.11", "cell"),
             self._p("30 mL", "cell"),
             self._p("—", "cell"), self._p("인화성/자극성 (GHS02/07)", "cell"),
             self._p("Sigma-Aldrich", "cell"), self._p("≥99%, anhydrous", "cell")],
            [self._p("메탄올 (HPLC grade)", "cell"),
             self._p("CH₄O", "cell"), self._p("32.04", "cell"),
             self._p(f"{meoh_ml} mL", "cell"),
             self._p("—", "cell"), self._p("인화성/독성 (GHS02/06/08)", "cell"),
             self._p("Merck", "cell"), self._p("≥99.9% HPLC", "cell")],
            [self._p("n-헥산", "cell"),
             self._p("C₆H₁₄", "cell"), self._p("86.18", "cell"),
             self._p("100 mL", "cell"),
             self._p("—", "cell"), self._p("인화성/신경독성 (GHS02/06/08)", "cell"),
             self._p("Daejung", "cell"), self._p("≥95%", "cell")],
            [self._p("하이드로퀴논 (중합금지제)", "cell"),
             self._p("C₆H₆O₂", "cell"), self._p("110.11", "cell"),
             self._p("50 mg", "cell"),
             self._p("0.005", "cell"), self._p("독성/환경유해 (GHS06/09)", "cell"),
             self._p("Sigma-Aldrich", "cell"), self._p("≥99%", "cell")],
            [self._p("질소 가스 (N₂, 고순도)", "cell"),
             self._p("N₂", "cell"), self._p("28.01", "cell"),
             self._p("연속 퍼지 (반응 전/중/후)", "cell"),
             self._p("—", "cell"), self._p("질식성 가스 (GHS04)", "cell"),
             self._p("Air Liquide", "cell"), self._p("99.999% (5N)", "cell")],
            [self._p("액체 질소 (LN₂)", "cell"),
             self._p("N₂(l)", "cell"), self._p("28.01", "cell"),
             self._p("적량 (FPT 사이클용)", "cell"),
             self._p("—", "cell"), self._p("극저온/질식 (GHS04)", "cell"),
             self._p("현지 공급", "cell"), self._p("극저온(-196℃)", "cell")],
        ]
        # 8열 컬럼 너비: 총 170mm 분배
        col8 = [32*mm, 14*mm, 16*mm, 28*mm, 16*mm, 22*mm, 22*mm, 20*mm]
        elements.append(self._make_table(reagent_data, col8))
        elements.append(self._p(self._next_tbl("시약 목록 (Organic Syntheses 8열 형식)"), "caption"))

        # ── 7.2 장비 목록 ──────────────────────────────────────────
        elements.append(self._p("7.2 실험 장비 목록", "subsection"))
        equip_rows = [
            [self._p("장비명", "header_white"), self._p("규격/사양", "header_white"),
             self._p("용도", "header_white"), self._p("비고", "header_white")],
            [self._p("슈렝크 플라스크 (100 mL)", "cell"),
             self._p("3-구, Teflon 밸브, 자석 교반자 포함", "cell"),
             self._p("중합 반응 용기", "cell"), self._p("질소/진공 병용", "cell")],
            [self._p("오일배스 + 디지털 온도조절기", "cell"),
             self._p("±0.5℃ 정밀도, 80℃ 설정", "cell"),
             self._p("반응 온도 제어", "cell"), self._p("실리콘 오일 사용", "cell")],
            [self._p("진공/질소 이중 매니폴드", "cell"),
             self._p("Schlenk line (4-포트)", "cell"),
             self._p("Freeze-Pump-Thaw 탈기 / N₂ 퍼지", "cell"), self._p("", "cell")],
            [self._p("진공 펌프 (로터리 베인)", "cell"),
             self._p("도달 진공도 ≤0.1 mbar", "cell"),
             self._p("용존 산소 제거", "cell"), self._p("냉각 트랩 필수", "cell")],
            [self._p("기계식 교반기 / 자석교반기", "cell"),
             self._p("300 rpm 설정, 폐쇄형 교반", "cell"),
             self._p("균일 중합 환경 유지", "cell"), self._p("회전속도 일정 유지", "cell")],
            [self._p("주사기 + 주사침 (20 mL, 18G)", "cell"),
             self._p("N₂-정제, 기밀형", "cell"),
             self._p("시약 투입 (격막 통과)", "cell"), self._p("사용 전 N₂ 세척 3회", "cell")],
            [self._p("부흐너 깔때기 + 진공여과 장치", "cell"),
             self._p("규조토(Celite) 패드 선택적 사용", "cell"),
             self._p("침전 고분자 여과", "cell"), self._p("", "cell")],
            [self._p("회전증발기 (Rotavap)", "cell"),
             self._p("워터배스 40℃, 진공 ≤20 mbar", "cell"),
             self._p("용매 농축/제거", "cell"), self._p("", "cell")],
            [self._p("진공 오븐", "cell"),
             self._p("50℃, 24 h, ≤1 mbar", "cell"),
             self._p("최종 건조 (잔류 용매 제거)", "cell"), self._p("항량 확인 필수", "cell")],
            [self._p("GPC (겔투과크로마토그래피)", "cell"),
             self._p("THF 이동상, 35℃, 1.0 mL/min, PS 표준", "cell"),
             self._p("Mn, Mw, PDI 측정", "cell"), self._p("RI 검출기", "cell")],
            [self._p("DSC (시차주사열량계)", "cell"),
             self._p("10℃/min, -80℃→250℃, N₂ 50 mL/min", "cell"),
             self._p("Tg, Tm 측정 (2nd heating 기준)", "cell"), self._p("Al 팬 사용", "cell")],
            [self._p("TGA (열중량분석기)", "cell"),
             self._p("10℃/min, RT→600℃, N₂(→공기) 전환", "cell"),
             self._p("Td (5% 중량감소 온도) 측정", "cell"), self._p("Al₂O₃ 팬", "cell")],
            [self._p("FT-IR 분광계", "cell"),
             self._p("KBr 디스크법, 4000-400 cm⁻¹, 4 cm⁻¹ 해상도 32회 스캔", "cell"),
             self._p("구조 확인 및 전환율 모니터링", "cell"), self._p("", "cell")],
            [self._p("NMR 분광계 (400 MHz)", "cell"),
             self._p("¹H, ¹³C, ¹⁹F; CDCl₃ 또는 d₆-DMSO 용매", "cell"),
             self._p("구조 확인, 단량체/반복단위 비교", "cell"), self._p("TMS 내부표준", "cell")],
        ]
        col3e = [45*mm, 65*mm, 40*mm, 20*mm]
        elements.append(self._make_table(equip_rows, col3e))
        elements.append(self._p(self._next_tbl("실험 장비 목록 (14종)"), "caption"))

        # ── 7.3 상세 실험 절차 ──────────────────────────────────────
        elements.append(self._p("7.3 상세 실험 절차 (전공서 수준)", "subsection"))
        elements.append(self._p(
            "하기 30단계 실험 절차는 Organic Syntheses 투고 기준으로 작성되었다. "
            "모든 작업은 흄후드 내에서 수행하며, 불활성 기체(N₂) 분위기를 엄수한다. "
            "TLC 분석 시 UV 램프(254/365 nm) 및 KMnO₄ 현색액을 병용한다.", "body"))

        steps = [
            ("단계 1: 실험 전 안전 점검",
             "보안경, 니트릴 장갑(2중), 실험복, 내화학성 앞치마를 착용한다. "
             "흄후드 기류 속도를 0.4 m/s 이상으로 확인하고, 소화기(CO₂/분말) 위치를 파악한다. "
             "AIBN/BPO는 충격 및 가열 시 폭발 위험이 있으므로 소량씩 취급하고 화기 차단을 확인한다."),
            ("단계 2: 초자기구 건조",
             "슈렝크 플라스크(100 mL), 교반자, 주사기, 유리 깔때기 등 사용할 초자기구를 "
             "건조 오븐(120℃, 2 h)에서 건조한다. 꺼낸 후 즉시 진공 라인에 연결하여 냉각 중 N₂를 치환한다."),
            ("단계 3: Schlenk line 설치 및 점검",
             "진공 매니폴드를 확인하고 진공 펌프 오일 레벨 및 배기 여부를 점검한다. "
             "냉각 트랩(-78℃)을 설치하여 용매 증기가 펌프로 유입되는 것을 방지한다. "
             "모든 밸브의 기밀성을 진공 게이지(≤0.5 mbar 도달 여부)로 확인한다."),
            ("단계 4: N₂ 치환 — 반응 용기",
             "슈렝크 플라스크에 자석 교반자를 넣고 Teflon 밸브로 밀폐한다. "
             "진공/N₂ 전환을 3회 반복하여 플라스크 내부를 완전히 N₂로 치환한다. "
             "(진공 ≤0.5 mbar, 30 s 유지 후 N₂ 충전; 3회 반복)"),
            ("단계 5: 용매 주입",
             f"N₂-정제 20 mL 주사기를 사용하여 무수 톨루엔 {solv_ml} mL를 "
             "격막(rubber septum)을 통해 N₂ 양압 하에서 플라스크에 주입한다. "
             "불소 함유 단량체의 경우 트리플루오로톨루엔을 우선 사용한다 (용해도 우수)."),
            ("단계 6: 단량체 칭량 및 용해",
             f"정밀 저울로 단량체를 10.000 ± 0.005 g ({mono_mmol:.1f} mmol) 정확히 칭량한다. "
             f"(MW = {mono_mw:.1f} g/mol 기준) "
             "교반 하에 용매에 천천히 가하여 완전 용해 여부를 육안으로 확인한다. "
             "용해되지 않으면 온도를 30℃까지 약간 올려 보조하고 강제 가열은 삼간다."),
            ("단계 7: 탈기 Cycle 1 — Freeze",
             "액체 질소(-196℃) 욕조에 플라스크를 담가 용액을 완전히 동결시킨다. "
             "용액이 완전히 고화될 때까지 (5-10분) 기다린다."),
            ("단계 8: 탈기 Cycle 1 — Pump",
             "Teflon 밸브를 진공 쪽으로 열어 1분간 감압(≤0.5 mbar)한다. "
             "기포가 발생하지 않음을 확인한 후 진공 밸브를 닫는다."),
            ("단계 9: 탈기 Cycle 1 — Thaw",
             "실온(또는 미지근한 물)에서 용액을 완전히 해동시킨다. "
             "해동 중 교반하지 않는다."),
            ("단계 10: 탈기 Cycle 2 & 3 반복",
             "단계 7-9를 2회 더 반복한다 (총 3 FPT 사이클). "
             "3회 완료 후 N₂로 플라스크 내부를 양압으로 충전한다. "
             "이로써 용존 O₂가 99.9% 이상 제거된다."),
            ("단계 11: AIBN 칭량",
             f"재결정 정제한 AIBN {aibn_g:.3f} g ({aibn_mmol:.2f} mmol, 1.0 mol%)을 "
             "정밀 저울로 칭량한다. AIBN은 44℃ 이하에서 취급하고, "
             "대량 축적을 피하며 소분하여 보관한다."),
            ("단계 12: AIBN 용해 및 투입",
             "AIBN을 무수 톨루엔 1.0 mL에 용해시킨다. "
             "N₂-정제 5 mL 주사기로 격막을 통해 반응 플라스크에 신속히 주입한다. "
             "주사기를 뽑은 후 즉시 격막을 확인하여 N₂ 누출이 없는지 점검한다."),
            ("단계 13: 오일배스 예비 가열",
             "실리콘 오일 배스를 65±1℃로 예비 가열한다. "
             "디지털 온도 조절기의 센서를 오일에 직접 침지하여 "
             "플라스크 외부 온도를 실시간 모니터링한다."),
            ("단계 14: 중합 반응 개시",
             "예비 가열된 오일배스에 플라스크를 침지하고 교반기를 300 rpm으로 설정한다. "
             "반응 시작 시간을 기록한다. N₂ 양압(벌블러로 확인)을 유지하며 "
             "온도가 65±1℃에 안정화되는지 확인한다 (약 5분 소요)."),
            ("단계 15: 반응 모니터링 — 점도 변화",
             "1시간마다 교반 저항 및 용액 점도 변화를 육안/교반기 전류로 확인한다. "
             "점도 증가가 과도하면 무수 톨루엔 5-10 mL를 추가 주입하여 희석한다."),
            ("단계 16: 반응 중간 FT-IR 모니터링 (선택)",
             "2시간째, 6시간째, 12시간째 반응 용액 ~0.1 mL를 취하여 ATR-FT-IR로 "
             "비닐기(=CH₂, ~910 cm⁻¹) 감소를 확인하여 전환율을 추정한다."),
            ("단계 17: 18시간 반응 완료 — 종결",
             "18시간 경과 후 플라스크를 오일배스에서 꺼내 빙수조(0℃)에 즉시 담가 급냉한다. "
             "하이드로퀴논 50 mg을 소량의 톨루엔에 용해시켜 주입하여 "
             "잔류 라디칼을 완전히 소거한다."),
            ("단계 18: 용매 농축",
             "감압(rotavap, 워터배스 40℃, ≤20 mbar) 하에서 용매를 "
             "원부피의 약 1/3까지 농축한다. "
             "완전히 증발시키지 않도록 주의한다 (고분자 필름 형성 방지)."),
            ("단계 19: 침전 — 첫 번째",
             f"농축된 고분자 용액을 메탄올 {meoh_ml} mL (10배 부피)에 "
             "가는 유리봉으로 천천히 적하하면서 교반한다. "
             "백색~미황색 섬유상 또는 과립 형태의 침전물이 생성된다."),
            ("단계 20: 여과 — 첫 번째",
             "감압 여과 (부흐너 깔때기, 규조토 패드)로 침전물을 수집한다. "
             "메탄올 50 mL × 3회로 세척하여 미반응 단량체와 AIBN 잔류물을 제거한다."),
            ("단계 21: 재용해 및 재침전",
             "침전물을 무수 톨루엔 10 mL에 재용해한다. "
             "불용 부분이 있으면 여과로 제거한다. "
             "메탄올 100 mL에 동일 방법으로 재침전한다 (2회 반복)."),
            ("단계 22: 헥산 세정",
             "정제된 침전물을 n-헥산 50 mL로 30분간 Soxhlet 세정하거나, "
             "냉장(4℃) n-헥산 50 mL × 2회 세척하여 비극성 불순물을 제거한다."),
            ("단계 23: 진공 건조",
             "정제된 고분자를 진공 오븐(50℃, ≤1 mbar, 24 h)에서 건조한다. "
             "건조 후 데시케이터(실리카겔)에서 보관하고 항량에 도달했는지 "
             "4 h 간격으로 2회 측정하여 확인한다."),
            ("단계 24: 수율 계산",
             "건조 후 최종 중량을 측정하고 수율을 계산한다. "
             f"이론 수율 = 10.0 g (단량체 100% 전환 시). "
             "일반적으로 라디칼 용액 중합의 전환율은 60-85%이다. "
             "수율이 40% 미만이면 반응 조건(온도, 시간, 개시제 농도)을 재검토한다."),
            ("단계 25: GPC 분석 (분자량 분포)",
             "고분자 1.0 mg/mL THF 용액을 준비 (0.45 μm 막여과 후 사용). "
             "GPC 조건: THF 이동상, 35℃, 유속 1.0 mL/min, PS 표준 검량선, RI 검출기. "
             "Mn, Mw, PDI(Đ = Mw/Mn)를 보고한다. 목표: PDI ≤ 2.0."),
            ("단계 26: DSC 분석 (유리전이온도)",
             f"고분자 5-10 mg을 알루미늄 팬에 밀봉한다. "
             f"DSC 스캔: -80℃ → 300℃, 10℃/min, N₂ 50 mL/min. "
             f"2nd heating scan에서 Tg를 결정한다. "
             f"예상 Tg: {getattr(sp, 'Tg', '—')}℃ (Van Krevelen 예측값)."),
            ("단계 27: TGA 분석 (열안정성)",
             f"고분자 ~10 mg을 Al₂O₃ 팬에 넣는다. "
             f"TGA 스캔: RT→600℃, 10℃/min, N₂(→Air 전환 가능). "
             f"5% 중량 감소 온도(Td)를 보고한다. "
             f"예상 Td: {getattr(sp, 'Td', '—')}℃ (Van Krevelen BDE 예측값)."),
            ("단계 28: FT-IR 구조 확인",
             "KBr 디스크법: 고분자 1 wt%를 KBr 분말과 혼합, 압축 성형 후 측정. "
             "ATR법: 고분자 필름을 직접 측정 가능. "
             "분석 범위: 4000-400 cm⁻¹, 해상도 4 cm⁻¹, 32회 스캔. "
             "반복단위의 특성 피크가 단량체 대비 비닐기(~910, 990 cm⁻¹) 소멸을 확인한다."),
            ("단계 29: NMR 구조 확인",
             "¹H-NMR (400 MHz): 10 mg/0.6 mL CDCl₃ (또는 d₆-DMSO, d₂-DCM). "
             "TMS를 내부 표준(δ = 0 ppm)으로 사용한다. "
             "반복단위 ¹H 피크 위치 및 적분비를 단량체 NMR과 비교하여 중합 전환율을 확인한다. "
             "불소 함유 고분자의 경우 ¹⁹F-NMR (376 MHz)을 병행한다."),
            ("단계 30: 데이터 기록 및 보고",
             "최종적으로 외관(색, 형태, 탄성/강도), 수율(%), GPC (Mn, Mw, PDI), "
             f"DSC Tg, TGA Td, FT-IR 특성 피크, NMR 화학적 이동을 "
             "실험 기록부(ELN 또는 종이)에 기재한다. "
             "모든 스펙트럼 원본 파일(.csv, .jdx, .opj)을 보관한다."),
        ]
        for title, desc_text in steps:
            elements.append(self._p(f"<b>{title}</b>", "body"))
            elements.append(self._p(desc_text, "body"))
            elements.append(Spacer(1, 1.5 * mm))

        # ── 7.4 TLC/컬럼 크로마토그래피 정제 (모노머 순도 확인용) ──
        elements.append(self._p("7.4 TLC 및 분석 전략", "subsection"))
        tlc_text = (
            "본 합성에서 고분자 생성물은 TLC보다 침전/재침전으로 정제하지만, "
            "미반응 단량체와 올리고머 비율 확인을 위해 하기 분석을 병행한다. "
            "<b>TLC 조건:</b> 실리카겔 60 F₂₅₄, 전개 용매 톨루엔/헥산 = 1:4 (v/v), "
            "UV 254 nm 및 KMnO₄ 현색. 단량체 Rf: ~0.5, 올리고머 Rf: ~0.2-0.4, "
            "고분자: 원점 잔류(Rf ~0). "
            "<b>GPC 비교:</b> 재침전 전/후 Mn 및 PDI 비교로 올리고머 제거 정도를 확인한다."
        )
        elements.append(self._p(tlc_text, "body"))

        # ── 7.5 수율 계산 공식 ──────────────────────────────────────
        elements.append(self._p("7.5 수율 계산", "subsection"))
        yield_rows = [
            [self._p("항목", "header_white"), self._p("계산식/값", "header_white"),
             self._p("비고", "header_white")],
            [self._p("단량체 투입량", "cell_bold"),
             self._p(f"10.0 g = {mono_mmol:.1f} mmol (MW {mono_mw:.1f} g/mol)", "cell"),
             self._p("정밀 칭량값", "cell")],
            [self._p("이론 수율", "cell_bold"),
             self._p(f"10.0 g × (반복단위 MW / 단량체 MW) = 약 {getattr(sp, 'M_repeat', mono_mw):.1f} g/반복단위", "cell"),
             self._p("Van Krevelen 반복단위 기준", "cell")],
            [self._p("실제 수율 (%)", "cell_bold"),
             self._p("(최종 건조 중량 / 10.0 g) × 100%", "cell"),
             self._p("목표: 60-85%", "cell")],
            [self._p("전환율 (FT-IR)", "cell_bold"),
             self._p("(A₉₁₀,₀ - A₉₁₀,t) / A₉₁₀,₀ × 100%", "cell"),
             self._p("910 cm⁻¹ 비닐기 흡광도 변화", "cell")],
        ]
        elements.append(self._make_table(yield_rows, [40*mm, 90*mm, 40*mm]))
        elements.append(self._p(self._next_tbl("수율 계산 공식"), "caption"))

        # ── 7.6 안전 주의사항 (8가지) ──────────────────────────────
        elements.append(self._p("7.6 안전 주의사항 (GHS 기준)", "subsection"))
        safety_items = [
            ("① AIBN/BPO 취급",
             "AIBN은 가열 시 N₂ 가스를 급격히 방출하므로 밀폐 용기 사용 금지. "
             "44℃ 이하에서 취급하며, 대량 축적 금지. BPO는 마찰/충격 민감성 산화제이므로 "
             "습윤 상태(≥25% H₂O)로 보관하고 금속 스패츌러 사용 금지."),
            ("② 불소 단량체 피부 노출",
             "불소 함유 단량체는 피부 침투성이 높고 독성이 있으므로 이중 니트릴 장갑 착용 필수. "
             "접촉 시 즉시 다량의 물로 15분 이상 세척하고 의사에게 문의한다."),
            ("③ 가연성 용매 (톨루엔, 헥산)",
             "톨루엔(인화점 4℃), 헥산(인화점 -22℃)은 고인화성 액체(GHS02). "
             "전기 스파크, 정전기, 화기를 완전히 차단하고 흄후드 내에서만 취급한다. "
             "정전기 방전을 위해 금속 용기 사용 및 접지를 확인한다."),
            ("④ 액체 질소 취급",
             "액체 질소(-196℃)는 극저온으로 동상(동결상처)을 유발한다. "
             "절연 장갑 + 보안경 착용 필수. 밀폐 공간에서 대량 사용 시 질식 위험이 있으므로 "
             "산소 농도계로 모니터링하거나 충분한 환기를 확보한다."),
            ("⑤ 진공 장비",
             "진공 라인의 유리 부품은 파열 위험이 있으므로 점검 후 사용. "
             "Dewar flask 사용 시 파열 방지 케이지 착용을 권장한다. "
             "갑작스러운 압력 변화로 인한 역류(suckback)를 방지하기 위해 "
             "냉각 트랩을 반드시 설치한다."),
            ("⑥ 하이드로퀴논",
             "발암 가능 물질(IARC Group 3)이므로 장갑 착용 및 분진 흡입 주의. "
             "흄후드 내에서 취급하고 피부 접촉을 최소화한다."),
            ("⑦ 폐기물 처리",
             "할로겐 함유 폐용매(트리플루오로톨루엔 등)는 별도 수거하여 "
             "공인 폐기물 처리업체에 위탁한다. 폐기물 라벨에 성분, 농도, 발생일자를 기재한다."),
            ("⑧ 비상 대처",
             "화재 발생 시 CO₂ 소화기 사용(분말 소화기 병용 가능). "
             "대규모 용매 누출 시 즉시 전원 차단 후 대피하고 안전관리자에 연락한다. "
             "피부 접촉 시 즉시 흐르는 물로 15분 이상 세척하고 응급실에 방문한다."),
        ]
        for title, desc_text in safety_items:
            elements.append(self._p(f"<b>{title}:</b> {desc_text}", "body"))
            elements.append(Spacer(1, 1 * mm))

        elements.append(PageBreak())
        return elements

    def _build_part8_references(self) -> List:
        """Part 8: 이론적 근거 및 참고문헌."""
        elements = []
        elements.append(self._p("Part 8. 이론적 근거 및 참고문헌", "section"))
        elements.append(HRFlowable(width="100%", thickness=1, color=_COL_SECTION_LINE))

        refs = [
            "[1] Van Krevelen, D.W.; te Nijenhuis, K. \"Properties of Polymers\", "
            "4th Ed., Elsevier, Amsterdam, 2009. — 그룹 기여법 기본 프레임워크",
            "[2] Fedors, R.F. \"A Method for Estimating Both the Solubility Parameters "
            "and Molar Volumes of Liquids\", Polym. Eng. Sci. 14, 147-154 (1974). "
            "— 응집 에너지 밀도 및 용해도 파라미터",
            "[3] Boyer, R.F. \"The Relation of Transition Temperatures to Chemical "
            "Structure in High Polymers\", Rubber Chem. Technol. 36, 1303 (1963). "
            "— Boyer-Beaman rule (Tg/Tm 비율)",
            "[4] Bicerano, J. \"Prediction of Polymer Properties\", 3rd Ed., Marcel "
            "Dekker, New York, 2002. — QSPR 접근법 및 연결성 지수",
            "[5] RDKit: Open-Source Cheminformatics, https://www.rdkit.org, 2025. "
            "— 분자 디스크립터 계산 (LogP, TPSA, Crippen, Kier-Hall)",
            "[6] Silverstein, R.M.; Webster, F.X.; Kiemle, D.J. \"Spectrometric "
            "Identification of Organic Compounds\", 7th Ed., Wiley, 2005. "
            "— IR/NMR 스펙트럼 예측 규칙",
            "[7] Odian, G. \"Principles of Polymerization\", 4th Ed., Wiley-Interscience, "
            "2004. — 라디칼 중합 메커니즘 및 실험 프로토콜",
            "[8] Brazel, C.S.; Rosen, S.L. \"Fundamental Principles of Polymeric "
            "Materials\", 3rd Ed., Wiley, 2012. — 고분자 물성 측정 방법론",
            "[9] Lorentz, H.A. \"Ueber die Beziehung zwischen der Fortpflanzungsgeschwindigkeit "
            "des Lichtes...\", Ann. Phys. 9, 641 (1880). — Lorentz-Lorenz 굴절률 관계식",
            "[10] Luo, Y.R. \"Comprehensive Handbook of Chemical Bond Energies\", "
            "CRC Press, 2007. — 결합 분해 에너지 (BDE) 데이터",
        ]
        for ref in refs:
            elements.append(self._p(ref, "ref"))

        return elements

    # ─── 조립 및 내보내기 ──────────────────────────────

    def build(self) -> List:
        """전체 보고서 요소 조립."""
        elements = []
        elements += self._build_cover()
        elements += self._build_part1_original_monomer()
        elements += self._build_part2_original_polymer()
        elements += self._build_part3_methodology()
        elements += self._build_part3b_polymerization_mechanism()
        elements += self._build_part4_derivative_monomer()
        elements += self._build_part5_derivative_polymer()
        elements += self._build_part6_comparison()
        elements += self._build_part7_synthesis()
        elements += self._build_part8_references()
        return elements

    def export(self, file_path: str) -> Tuple[bool, str]:
        """PDF 파일 생성."""
        if not REPORTLAB_OK:
            return False, "reportlab 미설치"
        try:
            doc = SimpleDocTemplate(
                file_path, pagesize=A4,
                leftMargin=20 * mm, rightMargin=20 * mm,
                topMargin=15 * mm, bottomMargin=15 * mm,
            )
            page_num = [0]

            def _on_page(canvas, doc):
                page_num[0] += 1
                canvas.saveState()
                canvas.setFont(self._font_name, 7)
                canvas.setFillColor(_COL_CAPTION if _COL_CAPTION else colors.grey)
                canvas.drawString(20 * mm, 8 * mm, f"- {page_num[0]} -")
                w = A4[0]
                canvas.drawRightString(
                    w - 20 * mm, 8 * mm,
                    f"ChemGrid Pro | {datetime.now().strftime('%Y-%m-%d')}")
                canvas.restoreState()

            elements = self.build()
            doc.build(elements, onFirstPage=_on_page, onLaterPages=_on_page)
            return True, file_path
        except Exception as e:
            logger.error("PDF export failed: %s", e)
            return False, str(e)


# ═══════════════════════════════════════════════════════════════
# 편의 함수
# ═══════════════════════════════════════════════════════════════

def export_polymer_lead_report(data: PolymerLeadReportData,
                                file_path: str) -> Tuple[bool, str]:
    """고분자 리드 최적화 보고서 PDF 생성 (엔트리 포인트)."""
    exporter = PolymerLeadReportExporter(data)
    return exporter.export(file_path)
