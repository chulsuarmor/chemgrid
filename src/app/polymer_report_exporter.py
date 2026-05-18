#!/usr/bin/env python3
"""
고분자 분석 보고서 PDF 내보내기 (Polymer Analysis Report Exporter).

DryLab 보고서 패턴을 따르는 A4 세로 PDF 생성기.
Van Krevelen 그룹 기여법 기반 고분자 물성 예측 결과를 학술 보고서 양식으로 출력한다.

섹션 구성 (6 Parts):
  0. 표지 (Cover) — 고분자명, 단량체/반복단위 구조 이미지, 날짜
  1. Part 1: 단량체 분석 — 분자 구조, 분자량, 작용기 분해, 중합 유형 판별
  2. Part 2: 중합 반응 조건 — 개시제, 온도, 압력, 용매, 촉매, 반응 메커니즘
  3. Part 3: 고분자 물성 분석 — 열적/기계적/광학 특성 (표 + 그래프)
  4. Part 4: 응용 분석 및 AI 해석 — AI 분석 텍스트 + 활용 분야 추천
  5. Part 5: 비교 분석 — 범용 고분자 (PE, PP, PTFE, PVC, PS)와 레이더차트 + 비교표

Dependencies:
    - reportlab (PDF generation)
    - rdkit (2D structure, molecular properties)
    - matplotlib (charts: temperature bar, mechanical bar, radar)
    - PIL/Pillow (image conversion)
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
    RDKIT_AVAILABLE = True
except ImportError as e:
    RDKIT_AVAILABLE = False
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
    REPORTLAB_AVAILABLE = True
except ImportError as e:
    REPORTLAB_AVAILABLE = False
    logger.debug("Optional module reportlab not available: %s", e)
    mm = 2.834645669291339   # 1mm in points
    cm = 28.34645669291339
    A4 = (595.2755905511812, 841.8897637795276)
    ParagraphStyle = type('ParagraphStyle', (), {})
    getSampleStyleSheet = lambda: {}
    TA_CENTER = TA_LEFT = TA_JUSTIFY = TA_RIGHT = 0
    colors = type('colors', (), {'black': None, 'white': None, 'grey': None})()
    SimpleDocTemplate = Table = TableStyle = Paragraph = Spacer = None
    PageBreak = HRFlowable = KeepTogether = None
    RLImage = None

# ── PIL ──
try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError as e:
    PIL_AVAILABLE = False
    logger.debug("Optional module PIL not available: %s", e)

# ── matplotlib ──
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError as e:
    MATPLOTLIB_AVAILABLE = False
    logger.debug("Optional module matplotlib not available: %s", e)


# ═══════════════════════════════════════════════════════════
# Data container
# ═══════════════════════════════════════════════════════════

@dataclass
class PolymerReportData:
    """All data needed for Polymer analysis report generation."""
    monomer_smiles: str = ""
    polymer_props: Any = None        # PolymerProperties from polymer_property_engine
    conditions: Dict[str, Any] = field(default_factory=dict)  # polymerization conditions
    ai_text: str = ""                # AI interpretation text
    author: str = "ChemGrid Pro"
    date: str = ""                   # auto-filled if empty
    # [M709 POLYMER-REPORT-001] Part 6 분광분석 + Part 7 합성방법
    monomer_spectra: Any = None      # PredictedSpectra for monomer (중합 전)
    polymer_spectra: Any = None      # PredictedSpectra for polymer repeat unit (중합 후)
    synthesis_text: str = ""         # AI/engine-generated synthesis protocol text


# ═══════════════════════════════════════════════════════════
# Font Registration
# ═══════════════════════════════════════════════════════════

_KOREAN_FONT_PATHS = [
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
_KOREAN_BOLD_PATHS = [
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/NanumGothicBold.ttf",
]

_FONT_REGISTERED = False
_FN = "PolyFont"
_FNB = "PolyFontBold"
_MPL_FONT_PATH = ""


def _register_fonts():
    """Register Korean fonts for reportlab and matplotlib."""
    global _FONT_REGISTERED, _MPL_FONT_PATH
    if _FONT_REGISTERED or not REPORTLAB_AVAILABLE:
        return
    _FONT_REGISTERED = True

    for fpath in _KOREAN_FONT_PATHS:
        if os.path.isfile(fpath):
            try:
                pdfmetrics.registerFont(TTFont(_FN, fpath))
                _MPL_FONT_PATH = fpath
                break
            except Exception as e:
                logger.warning("Korean regular font registration failed for '%s': %s", fpath, e)
                continue
    else:
        logger.warning("Korean regular font not found, using Helvetica fallback")

    for fpath in _KOREAN_BOLD_PATHS:
        if os.path.isfile(fpath):
            try:
                pdfmetrics.registerFont(TTFont(_FNB, fpath))
                break
            except Exception as e:
                logger.warning("Korean bold font registration failed for '%s': %s", fpath, e)
                continue
    else:
        try:
            pdfmetrics.registerFont(TTFont(_FNB, _KOREAN_FONT_PATHS[0]))
        except Exception as e:
            logger.warning("Korean bold font not found: %s", e)


def _get_mpl_fontprop():
    """Get matplotlib FontProperties for Korean text."""
    if MATPLOTLIB_AVAILABLE and _MPL_FONT_PATH and os.path.isfile(_MPL_FONT_PATH):
        return fm.FontProperties(fname=_MPL_FONT_PATH)
    return None


# ═══════════════════════════════════════════════════════════
# Color Palette
# ═══════════════════════════════════════════════════════════

if REPORTLAB_AVAILABLE:
    _COL_HEADER_BG = colors.HexColor("#1a2e3d")       # 표지 배경 (진한 청록)
    _COL_SECTION_NUM = colors.HexColor("#2c3e50")      # 섹션 번호
    _COL_SECTION_LINE = colors.HexColor("#1abc9c")     # 섹션 구분선 (고분자 그린)
    _COL_TABLE_HEADER = colors.HexColor("#34495e")     # 테이블 헤더
    _COL_TABLE_HEADER_TEXT = colors.white
    _COL_TABLE_ALT = colors.HexColor("#f0faf7")        # 테이블 교대 행 (연녹색)
    _COL_ACCENT = colors.HexColor("#1abc9c")           # 강조색 (에메랄드)
    _COL_BODY = colors.HexColor("#1a1a1a")
    _COL_CAPTION = colors.HexColor("#444444")
    _COL_WHITE = colors.white
    _COL_BORDER = colors.HexColor("#cccccc")
    _COL_LIGHT_BORDER = colors.HexColor("#e0e0e0")
    _COL_PASS = colors.HexColor("#27ae60")
    _COL_WARN = colors.HexColor("#e67e22")
    _COL_BLANK_HINT = colors.HexColor("#999999")
else:
    _COL_HEADER_BG = _COL_SECTION_NUM = _COL_SECTION_LINE = None
    _COL_TABLE_HEADER = _COL_TABLE_HEADER_TEXT = _COL_TABLE_ALT = None
    _COL_ACCENT = _COL_BODY = _COL_CAPTION = _COL_WHITE = None
    _COL_BORDER = _COL_LIGHT_BORDER = _COL_PASS = _COL_WARN = None
    _COL_BLANK_HINT = None


# ═══════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════

def _safe_xml(text: str) -> str:
    """Escape XML special chars for reportlab Paragraph."""
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _smiles_to_png(smiles: str, w: int = 300, h: int = 250,
                   dark_bg: bool = False) -> Optional[bytes]:
    """SMILES -> PNG image bytes via RDKit."""
    if not RDKIT_AVAILABLE or not PIL_AVAILABLE:
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        AllChem.Compute2DCoords(mol)

        # Try SVG -> PNG via cairosvg first
        try:
            import cairosvg
            drawer = Draw.MolDraw2DSVG(w, h)
            if dark_bg:
                drawer.drawOptions().setBackgroundColour((0.1, 0.1, 0.15, 1.0))
            try:
                drawer.drawOptions().atomLabelFontSize = 14
            except AttributeError as e:
                logger.warning("RDKit drawer atomLabelFontSize not supported: %s", e)
            drawer.DrawMolecule(mol)
            drawer.FinishDrawing()
            svg = drawer.GetDrawingText()
            svg_png = cairosvg.svg2png(bytestring=svg.encode(), dpi=300)
            if svg_png:
                return svg_png
        except Exception as e:
            logger.warning("CairoSVG rendering failed, falling back to RDKit Draw: %s", e)

        # Fallback: RDKit Draw.MolToImage
        img = Draw.MolToImage(mol, size=(w, h))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.warning("SMILES to PNG failed for %s: %s", smiles, e)
        return None


def _fig_to_png_bytes(fig, dpi: int = 200) -> Optional[bytes]:
    """Convert a matplotlib Figure to PNG bytes."""
    try:
        if _MPL_FONT_PATH and os.path.isfile(_MPL_FONT_PATH):
            import matplotlib as _mpl
            _mpl.rcParams['font.family'] = 'sans-serif'
            font_name = fm.FontProperties(fname=_MPL_FONT_PATH).get_name()
            _mpl.rcParams['font.sans-serif'] = [font_name, 'DejaVu Sans']
            _mpl.rcParams['axes.unicode_minus'] = False
        buf = io.BytesIO()
        fig.savefig(buf, format="PNG", bbox_inches="tight",
                    facecolor='white', dpi=dpi)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.warning("Figure to PNG conversion failed: %s", e)
        try:
            plt.close(fig)
        except Exception as e2:
            logger.warning("Failed to close matplotlib figure: %s", e2)
        return None


def _make_rl_image_from_bytes(png_bytes: bytes, max_w: float = 155 * mm,
                               max_h: float = 100 * mm) -> Optional['RLImage']:
    """Create RLImage from PNG bytes preserving aspect ratio."""
    if not png_bytes or not REPORTLAB_AVAILABLE:
        return None
    try:
        img_buf = io.BytesIO(png_bytes)
        if PIL_AVAILABLE:
            pil_img = PILImage.open(io.BytesIO(png_bytes))
            orig_w, orig_h = pil_img.size
            pil_img.close()
            if orig_w <= 0 or orig_h <= 0:
                return RLImage(img_buf, width=max_w, height=max_h)
            aspect = orig_h / orig_w
            w = max_w
            h = w * aspect
            if h > max_h:
                h = max_h
                w = h / aspect
            return RLImage(img_buf, width=w, height=h)
        else:
            return RLImage(img_buf, width=max_w, height=max_h)
    except Exception as e:
        logger.warning("_make_rl_image_from_bytes failed: %s", e)
        return None


# ═══════════════════════════════════════════════════════════
# Chart Generators
# ═══════════════════════════════════════════════════════════

def _generate_temperature_bar_png(Tg: float, Tm: float, Td: float,
                                   max_temp: float) -> Optional[bytes]:
    """온도바 이미지 생성 (gradient blue->red, Tg/Tm/Td 마커).

    수평 온도 바에 Tg(유리전이), Tm(녹는점), Td(열분해) 마커를 표시한다.
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
    try:
        fp = _get_mpl_fontprop()
        fig, ax = plt.subplots(figsize=(8, 2.8))
        fig.patch.set_facecolor('white')

        # Temperature range: -200 to max(Td+100, 600)
        t_min = -200  # K 기준이 아닌 C 기준으로 표시
        t_max = max(Td + 100, 600) if Td > 0 else 600

        # Gradient bar
        gradient = np.linspace(0, 1, 256).reshape(1, -1)
        ax.imshow(gradient, aspect='auto', cmap='coolwarm',
                  extent=[t_min, t_max, 0, 1], alpha=0.7)

        # Markers
        markers = []
        if Tg != 0 and not math.isnan(Tg):
            markers.append((Tg, 'Tg (유리전이)', '#2980b9', 'v'))
        if Tm > 0 and not math.isnan(Tm):
            markers.append((Tm, 'Tm (녹는점)', '#e67e22', 's'))
        if Td > 0 and not math.isnan(Td):
            markers.append((Td, 'Td (열분해)', '#c0392b', '^'))
        if max_temp > 0 and not math.isnan(max_temp):
            markers.append((max_temp, '최대사용온도', '#27ae60', 'D'))

        y_positions = [0.5] * len(markers)
        for i, (temp, label, color, marker) in enumerate(markers):
            if t_min <= temp <= t_max:
                ax.plot(temp, 0.5, marker=marker, color=color,
                        markersize=14, markeredgecolor='white',
                        markeredgewidth=1.5, zorder=5)
                # Stagger label positions to avoid overlap
                y_label = 1.3 + (i % 2) * 0.4
                ax.annotate(f'{label}\n{temp:.0f} \u2103',
                            xy=(temp, 0.5), xytext=(temp, y_label),
                            ha='center', va='bottom', fontsize=9,
                            fontproperties=fp,
                            arrowprops=dict(arrowstyle='->', color=color, lw=1.2),
                            color=color, fontweight='bold')

        ax.set_xlim(t_min, t_max)
        ax.set_ylim(-0.2, 2.5)
        ax.set_yticks([])
        ax.set_xlabel('온도 (\u2103)', fontsize=10, fontproperties=fp)
        if fp:
            ax.set_title('열적 전이 온도 분포', fontsize=12, fontproperties=fp,
                          fontweight='bold', pad=10)
        ax.spines['top'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['right'].set_visible(False)

        fig.tight_layout()
        return _fig_to_png_bytes(fig)
    except Exception as e:
        logger.warning("Temperature bar generation failed: %s", e)
        return None


def _generate_tga_dsc_png(
    Tg: float, Tm: float, Td: float,
    monomer_smiles: str = "",
) -> Optional[bytes]:
    """TGA + DSC 시뮬레이션 그래프 PNG 생성.

    TGA: Weight % vs Temperature — sigmoid decomposition around Td.
    DSC: Heat Flow vs Temperature — Tg step + Tm endotherm + Td exotherm.
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
    if Td <= 0:
        return None
    try:
        fp = _get_mpl_fontprop()
        fkw = {"fontproperties": fp} if fp else {}

        # Determine aromaticity for char yield estimation
        is_aromatic = False
        if RDKIT_AVAILABLE and monomer_smiles:
            try:
                mol = Chem.MolFromSmiles(monomer_smiles)
                if mol is not None:
                    is_aromatic = any(a.GetIsAromatic() for a in mol.GetAtoms())
            except Exception as e:
                logger.warning("Aromaticity check failed for TGA/DSC: %s", e)

        # Residual weight: 15% for aromatic (more char), 5% for aliphatic
        residual = 15.0 if is_aromatic else 5.0

        # Temperature arrays
        t_max_tga = min(Td + 200, 800)
        T_tga = np.linspace(25, t_max_tga, 500)

        t_min_dsc = -50
        t_max_dsc = Td + 50
        T_dsc = np.linspace(t_min_dsc, t_max_dsc, 500)

        # TGA curve: sigmoid decomposition
        tga_width = 30.0  # °C — controls steepness of weight loss sigmoid
        weight = residual + (100.0 - residual) / (1.0 + np.exp((T_tga - Td) / tga_width))

        # DSC curve
        dsc = np.zeros_like(T_dsc)

        # Glass transition (Tg): step change
        step_height = 0.3  # mW/mg
        tg_step_width = 3.0  # °C
        if Tg != 0 and not math.isnan(Tg):
            dsc += step_height / (1.0 + np.exp(-(T_dsc - Tg) / tg_step_width))

        # Melting peak (Tm): endothermic (negative, exo up)
        has_tm = Tm > 0 and not math.isnan(Tm)
        melt_amplitude = 2.0  # mW/mg
        melt_sigma = 10.0  # °C
        if has_tm:
            dsc -= melt_amplitude * np.exp(-((T_dsc - Tm) ** 2) / (2.0 * melt_sigma ** 2))

        # Decomposition peak (Td): exothermic (positive, exo up)
        decomp_amplitude = 3.0  # mW/mg
        decomp_sigma = 20.0  # °C
        dsc += decomp_amplitude * np.exp(-((T_dsc - Td) ** 2) / (2.0 * decomp_sigma ** 2))

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
        fig.patch.set_facecolor('white')

        # --- TGA subplot ---
        ax1.plot(T_tga, weight, color='#c0392b', linewidth=2.0)
        ax1.axvline(x=Td, color='#7f8c8d', linestyle='--', linewidth=1.0, alpha=0.7)
        ax1.annotate(
            f'Td = {Td:.0f} \u2103',
            xy=(Td, residual + (100.0 - residual) / 2.0),
            xytext=(Td + 30, 60),
            fontsize=9, color='#c0392b', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color='#c0392b', lw=1.2),
            fontproperties=fp,
        )
        ax1.set_xlabel('Temperature (\u2103)', fontsize=9, fontproperties=fp)
        ax1.set_ylabel('Weight Remaining (%)', fontsize=9, fontproperties=fp)
        ax1.set_title('TGA (\uc5f4\uc911\ub7c9\ubd84\uc11d)', fontsize=11,
                      fontweight='bold', fontproperties=fp)
        ax1.set_ylim(-5, 110)
        ax1.set_xlim(25, t_max_tga)
        ax1.grid(True, alpha=0.3)
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)

        # --- DSC subplot ---
        ax2.plot(T_dsc, dsc, color='#2980b9', linewidth=2.0)

        if Tg != 0 and not math.isnan(Tg) and t_min_dsc <= Tg <= t_max_dsc:
            tg_y = step_height / 2.0  # midpoint of step
            ax2.axvline(x=Tg, color='#27ae60', linestyle=':', linewidth=1.0, alpha=0.7)
            ax2.annotate(
                f'Tg = {Tg:.0f} \u2103', xy=(Tg, tg_y),
                xytext=(Tg - 40, tg_y + 1.5),
                fontsize=8, color='#27ae60', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#27ae60', lw=1.0),
                fontproperties=fp,
            )

        if has_tm and t_min_dsc <= Tm <= t_max_dsc:
            ax2.axvline(x=Tm, color='#e67e22', linestyle=':', linewidth=1.0, alpha=0.7)
            ax2.annotate(
                f'Tm = {Tm:.0f} \u2103', xy=(Tm, -melt_amplitude * 0.8),
                xytext=(Tm + 25, -melt_amplitude - 0.5),
                fontsize=8, color='#e67e22', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#e67e22', lw=1.0),
                fontproperties=fp,
            )

        if t_min_dsc <= Td <= t_max_dsc:
            ax2.axvline(x=Td, color='#c0392b', linestyle=':', linewidth=1.0, alpha=0.7)
            ax2.annotate(
                f'Td = {Td:.0f} \u2103', xy=(Td, decomp_amplitude * 0.8),
                xytext=(Td - 50, decomp_amplitude + 0.5),
                fontsize=8, color='#c0392b', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#c0392b', lw=1.0),
                fontproperties=fp,
            )

        ax2.set_xlabel('Temperature (\u2103)', fontsize=9, fontproperties=fp)
        ax2.set_ylabel('Heat Flow (mW/mg)  \u2191 exo', fontsize=9, fontproperties=fp)
        ax2.set_title('DSC (\uc2dc\ucc28\uc8fc\uc0ac\uc5f4\ub7c9\uce21\uc815)', fontsize=11,
                      fontweight='bold', fontproperties=fp)
        ax2.set_xlim(t_min_dsc, t_max_dsc)
        ax2.grid(True, alpha=0.3)
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)

        fig.tight_layout(pad=2.0)
        return _fig_to_png_bytes(fig)
    except Exception as e:
        logger.warning("TGA/DSC graph generation failed: %s", e)
        return None


def _generate_mechanical_bar_png(tensile: float, modulus: float,
                                  elongation: float) -> Optional[bytes]:
    """기계적 특성 수평 막대 차트."""
    if not MATPLOTLIB_AVAILABLE:
        return None
    try:
        fp = _get_mpl_fontprop()
        fig, axes = plt.subplots(1, 3, figsize=(9, 3))
        fig.patch.set_facecolor('white')

        properties = [
            ('인장강도', tensile, 'MPa', '#2980b9', 200),    # max reference ~200 MPa
            ('영률', modulus, 'MPa', '#27ae60', 10000),       # max reference ~10 GPa
            ('신장률', elongation, '%', '#e67e22', 1000),     # max reference ~1000%
        ]

        for ax, (name, value, unit, color, ref_max) in zip(axes, properties):
            # Horizontal bar
            bar_val = min(value, ref_max)
            ax.barh([0], [bar_val], color=color, height=0.5, alpha=0.8,
                    edgecolor='white', linewidth=1)
            ax.barh([0], [ref_max], color='#ecf0f1', height=0.5, alpha=0.3,
                    zorder=0)

            ax.set_xlim(0, ref_max * 1.1)
            ax.set_yticks([])
            ax.set_xlabel(unit, fontsize=9, fontproperties=fp)
            if fp:
                ax.set_title(f'{name}\n{value:.1f} {unit}',
                             fontsize=10, fontproperties=fp, fontweight='bold')
            else:
                ax.set_title(f'{name}\n{value:.1f} {unit}', fontsize=10,
                             fontweight='bold')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_visible(False)

        fig.tight_layout()
        return _fig_to_png_bytes(fig)
    except Exception as e:
        logger.warning("Mechanical bar generation failed: %s", e)
        return None


# Reference polymers for radar chart comparison
_RADAR_REFERENCE_POLYMERS = {
    "PE": {"density": 0.94, "Tg": -125, "Tm": 137, "tensile": 30.0,
            "modulus": 1000, "delta": 16.2},
    "PP": {"density": 0.90, "Tg": -10, "Tm": 165, "tensile": 35.0,
            "modulus": 1500, "delta": 16.0},
    "PTFE": {"density": 2.15, "Tg": 127, "Tm": 327, "tensile": 30.5,
              "modulus": 575, "delta": 12.6},
    "PVC": {"density": 1.40, "Tg": 87, "Tm": 212, "tensile": 52.0,
             "modulus": 3000, "delta": 19.5},
    "PS": {"density": 1.05, "Tg": 100, "Tm": 240, "tensile": 40.0,
            "modulus": 3200, "delta": 18.5},
}


def _generate_radar_comparison_png(current_props: Any,
                                    reference_polymers: Optional[Dict] = None
                                    ) -> Optional[bytes]:
    """6축 레이더 차트: density, Tg, Tm, tensile, modulus, delta(용해도 파라미터).

    현재 고분자와 5종 범용 고분자를 비교한다.
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
    if current_props is None:
        return None

    refs = reference_polymers or _RADAR_REFERENCE_POLYMERS

    try:
        fp = _get_mpl_fontprop()

        categories = ['밀도\n(g/cm\u00b3)', 'Tg\n(\u2103)', 'Tm\n(\u2103)',
                       '인장강도\n(MPa)', '영률\n(MPa)', '\u03b4\n(MJ/m\u00b3)\u00b9/\u00b2']
        N = len(categories)

        # Normalization ranges (min, max) for each axis
        # Using practical ranges for common polymers
        norm_ranges = [
            (0.8, 2.5),    # density
            (-150, 200),   # Tg
            (50, 400),     # Tm
            (5, 100),      # tensile
            (100, 5000),   # modulus
            (10, 30),      # delta
        ]

        def _normalize(vals):
            """Normalize values to 0-1 range for radar chart."""
            out = []
            for v, (lo, hi) in zip(vals, norm_ranges):
                if hi == lo:
                    out.append(0.5)
                else:
                    out.append(max(0, min(1, (v - lo) / (hi - lo))))
            return out

        # Current polymer values
        current_vals = [
            getattr(current_props, 'density', 1.0),
            getattr(current_props, 'Tg', 0),
            getattr(current_props, 'Tm', 0),
            getattr(current_props, 'tensile_strength', 0),
            getattr(current_props, 'youngs_modulus', 0),
            getattr(current_props, 'solubility_param', 0),
        ]
        current_norm = _normalize(current_vals)

        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        angles += angles[:1]  # close the polygon

        fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(projection='polar'))
        fig.patch.set_facecolor('white')

        # Plot current polymer (bold, filled)
        cur_data = current_norm + current_norm[:1]
        poly_name = getattr(current_props, 'polymer_name', '현재 고분자')
        ax.fill(angles, cur_data, alpha=0.25, color='#c0392b')
        ax.plot(angles, cur_data, 'o-', linewidth=2.5, color='#c0392b',
                label=poly_name, markersize=7)

        # Plot reference polymers (thinner lines)
        ref_colors = ['#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c']
        for i, (name, rdata) in enumerate(refs.items()):
            # N-guard: rdata가 dict인지 검증
            if not isinstance(rdata, dict):
                logger.warning("레이더 차트 참조 고분자 '%s' 데이터가 dict가 아닙니다 (skip)", name)
                continue
            rvals = [
                rdata.get('density', 1.0),
                rdata.get('Tg', 0),
                rdata.get('Tm', 0),
                rdata.get('tensile', 0),
                rdata.get('modulus', 0),
                rdata.get('delta', 0),
            ]
            rnorm = _normalize(rvals)
            rplot = rnorm + rnorm[:1]
            c = ref_colors[i % len(ref_colors)]
            ax.plot(angles, rplot, '--', linewidth=1.2, color=c,
                    label=name, alpha=0.7)

        ax.set_xticks(angles[:-1])
        if fp:
            ax.set_xticklabels(categories, fontproperties=fp, fontsize=9)
        else:
            ax.set_xticklabels(categories, fontsize=9)

        ax.set_ylim(0, 1.05)
        ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_yticklabels(['20%', '40%', '60%', '80%', '100%'], fontsize=7,
                            color='grey')
        ax.grid(True, alpha=0.3)

        if fp:
            ax.set_title('범용 고분자 물성 비교', fontsize=13, fontproperties=fp,
                          fontweight='bold', pad=25)
            ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1.1),
                       prop=fp, fontsize=9)
        else:
            ax.set_title('범용 고분자 물성 비교', fontsize=13, fontweight='bold',
                          pad=25)
            ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1.1), fontsize=9)

        fig.tight_layout()
        return _fig_to_png_bytes(fig)
    except Exception as e:
        logger.warning("Radar comparison chart generation failed: %s", e)
        return None


def _generate_group_decomposition_table(groups: Dict[str, int]) -> List[list]:
    """작용기 분해 표 데이터 생성 (header + data rows).

    Returns list of rows: [["작용기", "개수"], ["-CH2-", "4"], ...]
    """
    rows = [["작용기", "개수"]]
    if not groups:
        rows.append(["(작용기 분해 데이터 없음)", ""])
        return rows
    for grp, count in sorted(groups.items(), key=lambda x: -x[1]):
        rows.append([grp, str(count)])
    return rows


def _get_reference_polymers_from_engine() -> Dict[str, Dict]:
    """Try to import KNOWN_POLYMERS from polymer_property_engine."""
    try:
        from polymer_property_engine import KNOWN_POLYMERS
        return KNOWN_POLYMERS
    except ImportError as e:
        logger.debug("Direct polymer_property_engine import failed: %s", e)
        try:
            import sys as _sys
            src_dir = os.path.dirname(os.path.abspath(__file__))
            if src_dir not in _sys.path:
                _sys.path.insert(0, src_dir)
            from polymer_property_engine import KNOWN_POLYMERS
            return KNOWN_POLYMERS
        except ImportError as e2:
            logger.debug("polymer_property_engine not available via sys.path: %s", e2)
            return {}


# ═══════════════════════════════════════════════════════════
# Main Exporter Class
# ═══════════════════════════════════════════════════════════

class PolymerReportExporter:
    """Polymer analysis 6-Part report PDF generator.

    Part 0: Cover — 고분자명, 단량체/반복단위 구조, 날짜
    Part 1: Monomer Analysis — 분자 구조, 분자량, 작용기 분해, 중합 유형
    Part 2: Polymerization Conditions — 개시제, 온도, 압력, 용매, 촉매
    Part 3: Property Analysis — 열적/기계적/광학 특성 (표 + 그래프)
    Part 4: Application & AI Interpretation — AI 분석 + 활용 분야
    Part 5: Comparative Analysis — 범용 고분자 비교 (레이더차트 + 비교표)
    """

    def __init__(self, data: PolymerReportData):
        self._data = data
        self._fig_num = 0
        self._tbl_num = 0
        self._fig_list: List[str] = []
        self._tbl_list: List[str] = []
        _register_fonts()

    # ── Numbering helpers ──

    def _next_fig(self, caption: str) -> str:
        self._fig_num += 1
        full = f"[그림 {self._fig_num}] {caption}"
        self._fig_list.append(full)
        return full

    def _next_tbl(self, caption: str) -> str:
        self._tbl_num += 1
        full = f"[표 {self._tbl_num}] {caption}"
        self._tbl_list.append(full)
        return full

    # ── Properties shortcut ──

    @property
    def _props(self):
        return self._data.polymer_props

    # ── Export entry ──

    def export(self, file_path: str) -> Tuple[bool, str]:
        """Generate 6-part polymer analysis report PDF."""
        if not REPORTLAB_AVAILABLE:
            return False, "reportlab not installed."

        smi = (self._data.monomer_smiles or "").strip()
        if not smi:
            return False, "Monomer SMILES is empty - cannot generate report."
        if RDKIT_AVAILABLE:
            test_mol = Chem.MolFromSmiles(smi)
            if test_mol is None:
                return False, f"Invalid SMILES '{smi}' - RDKit cannot parse it."

        if not self._data.date:
            self._data.date = datetime.now().strftime("%Y-%m-%d")

        try:
            doc = SimpleDocTemplate(
                file_path, pagesize=A4,
                leftMargin=25 * mm, rightMargin=20 * mm,
                topMargin=25 * mm, bottomMargin=20 * mm,
                title=f"Polymer Report: {getattr(self._props, 'polymer_name', smi)}",
                author=self._data.author,
            )
            styles = self._build_styles()
            story = []

            # Cover
            story.extend(self._sec_cover(styles))
            story.append(PageBreak())

            # Part 1: Monomer analysis
            story.extend(self._sec_part1_monomer(styles))
            story.append(PageBreak())

            # Part 2: Polymerization conditions
            story.extend(self._sec_part2_conditions(styles))
            story.append(PageBreak())

            # Part 3: Property analysis
            story.extend(self._sec_part3_properties(styles))
            story.append(PageBreak())

            # Part 4: Application & AI interpretation
            story.extend(self._sec_part4_application(styles))
            story.append(PageBreak())

            # Part 5: Comparative analysis
            story.extend(self._sec_part5_comparison(styles))

            # [M709 POLYMER-REPORT-001] Part 6: 분광분석 (중합 전/후)
            spec_section = self._sec_part6_spectrum(styles)
            if spec_section:
                story.append(PageBreak())
                story.extend(spec_section)

            # [M709 POLYMER-REPORT-001] Part 7: 합성방법
            synth_section = self._sec_part7_synthesis(styles)
            if synth_section:
                story.append(PageBreak())
                story.extend(synth_section)

            doc.build(story, onFirstPage=self._page_footer,
                      onLaterPages=self._page_footer)

            # [M710 POLYMER-REPORT-002] HWPX 동시 생성
            hwpx_path = os.path.splitext(file_path)[0] + ".hwpx"
            try:
                self._export_hwpx(hwpx_path)
            except Exception as hw_err:
                logger.warning("HWPX 생성 실패: %s", hw_err)

            return True, file_path
        except Exception as e:
            logger.error("Polymer report generation failed: %s", e, exc_info=True)
            return False, f"PDF generation failed: {e}"

    # ── Page footer ──

    def _page_footer(self, canvas_obj, doc):
        """Page footer with page number and ChemGrid Pro branding."""
        canvas_obj.saveState()
        canvas_obj.setFont(_FN, 8)
        canvas_obj.setFillColor(colors.HexColor("#888888"))
        page_num = canvas_obj.getPageNumber()
        canvas_obj.drawCentredString(A4[0] / 2, 12 * mm, f"- {page_num} -")
        canvas_obj.setFont(_FN, 6)
        canvas_obj.drawRightString(
            A4[0] - 20 * mm, 8 * mm,
            f"ChemGrid Pro | {self._data.date}")
        canvas_obj.restoreState()

    # ── Styles ──

    def _build_styles(self) -> Dict[str, ParagraphStyle]:
        """Build paragraph styles for the report."""
        base = getSampleStyleSheet()
        s = {}
        s["cover_title"] = ParagraphStyle(
            "CoverTitle", parent=base["Title"],
            fontName=_FNB, fontSize=20, leading=26,
            alignment=TA_CENTER, textColor=_COL_BODY)
        s["cover_subtitle"] = ParagraphStyle(
            "CoverSubtitle", parent=base["Normal"],
            fontName=_FNB, fontSize=14, leading=20,
            alignment=TA_CENTER, textColor=_COL_BODY)
        s["cover_field"] = ParagraphStyle(
            "CoverField", parent=base["Normal"],
            fontName=_FN, fontSize=11, leading=18,
            alignment=TA_CENTER, textColor=_COL_BODY)
        s["section"] = ParagraphStyle(
            "SectionHeader", parent=base["Heading1"],
            fontName=_FNB, fontSize=14, leading=20,
            spaceBefore=8 * mm, spaceAfter=4 * mm,
            textColor=_COL_SECTION_NUM, borderWidth=0, borderPadding=0)
        s["subsection"] = ParagraphStyle(
            "SubsectionHeader", parent=base["Heading2"],
            fontName=_FNB, fontSize=12, leading=16,
            spaceBefore=4 * mm, spaceAfter=2 * mm, textColor=_COL_BODY)
        s["subsubsection"] = ParagraphStyle(
            "SubsubsectionHeader", parent=base["Heading3"],
            fontName=_FNB, fontSize=11, leading=14,
            spaceBefore=3 * mm, spaceAfter=1.5 * mm,
            textColor=_COL_BODY, leftIndent=5 * mm)
        s["body"] = ParagraphStyle(
            "Body", parent=base["Normal"],
            fontName=_FN, fontSize=10, leading=16,
            alignment=TA_JUSTIFY, spaceAfter=2 * mm,
            textColor=_COL_BODY, firstLineIndent=10 * mm)
        s["body_no_indent"] = ParagraphStyle(
            "BodyNoIndent", parent=base["Normal"],
            fontName=_FN, fontSize=10, leading=16,
            alignment=TA_JUSTIFY, spaceAfter=2 * mm, textColor=_COL_BODY)
        s["body_bold"] = ParagraphStyle(
            "BodyBold", parent=base["Normal"],
            fontName=_FNB, fontSize=10, leading=16,
            spaceAfter=1 * mm, textColor=_COL_BODY)
        s["caption"] = ParagraphStyle(
            "Caption", parent=base["Normal"],
            fontName=_FNB, fontSize=9, leading=13,
            alignment=TA_CENTER, textColor=_COL_CAPTION,
            spaceAfter=4 * mm, spaceBefore=2 * mm)
        s["table_caption"] = ParagraphStyle(
            "TableCaption", parent=base["Normal"],
            fontName=_FNB, fontSize=9, leading=13,
            textColor=_COL_BODY, spaceAfter=2 * mm, spaceBefore=3 * mm)
        s["small"] = ParagraphStyle(
            "Small", parent=base["Normal"],
            fontName=_FN, fontSize=8, leading=11, textColor=_COL_CAPTION)
        s["blank_hint"] = ParagraphStyle(
            "BlankHint", parent=base["Normal"],
            fontName=_FN, fontSize=9, leading=14,
            textColor=_COL_BLANK_HINT, leftIndent=3 * mm)
        return s

    # ── Standard table style ──

    def _std_table_style(self, has_header: bool = True) -> TableStyle:
        """Standard academic table style."""
        cmds = [
            ("FONTNAME", (0, 0), (-1, -1), _FN),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEABOVE", (0, 0), (-1, 0), 1.5, _COL_BODY),
            ("LINEBELOW", (0, -1), (-1, -1), 1.5, _COL_BODY),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, _COL_BORDER),
        ]
        if has_header:
            cmds.extend([
                ("FONTNAME", (0, 0), (-1, 0), _FNB),
                ("BACKGROUND", (0, 0), (-1, 0), _COL_TABLE_HEADER),
                ("TEXTCOLOR", (0, 0), (-1, 0), _COL_TABLE_HEADER_TEXT),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("LINEBELOW", (0, 0), (-1, 0), 1.0, _COL_BODY),
            ])
        return TableStyle(cmds)

    def _add_alt_rows(self, style: TableStyle, nrows: int,
                       start_row: int = 1) -> TableStyle:
        """Add alternating row backgrounds to a table style."""
        for r in range(start_row, nrows):
            if r % 2 == 0:
                style.add("BACKGROUND", (0, r), (-1, r), _COL_TABLE_ALT)
        return style

    # ═══════════════════════════════════════════════════════
    # Section 0: Cover
    # ═══════════════════════════════════════════════════════

    def _sec_cover(self, styles) -> list:
        """표지: 고분자명, 단량체 구조 이미지, 반복단위 구조, 날짜."""
        els = []
        els.append(Spacer(1, 30 * mm))

        # Title
        poly_name = ""
        poly_name_kr = ""
        if self._props:
            poly_name = getattr(self._props, 'polymer_name', '') or ''
            poly_name_kr = getattr(self._props, 'polymer_name_kr', '') or ''

        title_text = poly_name_kr if poly_name_kr else (poly_name if poly_name else "고분자 분석")
        els.append(Paragraph(
            f"<b>고분자 분석 보고서</b>", styles["cover_title"]))
        els.append(Spacer(1, 5 * mm))
        els.append(Paragraph(
            _safe_xml(title_text), styles["cover_subtitle"]))

        if poly_name and poly_name_kr and poly_name not in poly_name_kr:
            els.append(Spacer(1, 2 * mm))
            els.append(Paragraph(
                f"({_safe_xml(poly_name)})", styles["cover_field"]))

        els.append(Spacer(1, 10 * mm))

        # Separator line
        els.append(HRFlowable(width="60%", thickness=1.5,
                                color=_COL_ACCENT, spaceAfter=8 * mm))

        # Monomer structure image
        smi = self._data.monomer_smiles
        mono_png = _smiles_to_png(smi, w=300, h=220)
        if mono_png:
            img = _make_rl_image_from_bytes(mono_png, max_w=70 * mm, max_h=55 * mm)
            if img:
                els.append(img)
                els.append(Paragraph(
                    self._next_fig("단량체 분자 구조"), styles["caption"]))

        # Repeat unit structure image
        if self._props:
            ru_smi = getattr(self._props, 'repeat_unit_smiles', '')
            if ru_smi:
                # Remove wildcard atoms for display
                display_smi = ru_smi.replace('[*]', '*')
                ru_png = _smiles_to_png(display_smi, w=300, h=220)
                if ru_png:
                    img2 = _make_rl_image_from_bytes(
                        ru_png, max_w=70 * mm, max_h=55 * mm)
                    if img2:
                        els.append(Spacer(1, 3 * mm))
                        els.append(img2)
                        els.append(Paragraph(
                            self._next_fig("반복단위 구조"), styles["caption"]))

        els.append(Spacer(1, 10 * mm))

        # Date and author
        els.append(Paragraph(
            f"작성일: {_safe_xml(self._data.date)}", styles["cover_field"]))
        els.append(Spacer(1, 2 * mm))
        els.append(Paragraph(
            f"작성자: {_safe_xml(self._data.author)}", styles["cover_field"]))
        els.append(Spacer(1, 2 * mm))
        els.append(Paragraph(
            f"단량체 SMILES: {_safe_xml(smi)}", styles["small"]))

        return els

    # ═══════════════════════════════════════════════════════
    # Part 1: Monomer Analysis
    # ═══════════════════════════════════════════════════════

    def _sec_part1_monomer(self, styles) -> list:
        """Part 1: 단량체 분석 — 구조, 분자량, 작용기 분해, 중합 유형."""
        els = []
        els.append(Paragraph("Part 1. 단량체 분석", styles["section"]))
        els.append(HRFlowable(width="100%", thickness=1,
                                color=_COL_SECTION_LINE, spaceAfter=4 * mm))

        # 1.1 Molecular structure
        els.append(Paragraph("1.1 분자 구조 및 기본 정보", styles["subsection"]))

        smi = self._data.monomer_smiles
        mol_data = []
        mol_data.append(["항목", "값"])
        mol_data.append(["단량체 SMILES", smi])

        if RDKIT_AVAILABLE:
            mol = Chem.MolFromSmiles(smi)
            if mol is not None:  # Rule L: None guard
                mw = Descriptors.MolWt(mol)
                mol_data.append(["단량체 분자량", f"{mw:.2f} g/mol"])
                formula = rdMolDescriptors.CalcMolFormula(mol)
                mol_data.append(["분자식", formula])

        if self._props:
            M_rep = getattr(self._props, 'M_repeat', 0)
            if M_rep > 0:
                mol_data.append(["반복단위 분자량", f"{M_rep:.2f} g/mol"])
            ru_smi = getattr(self._props, 'repeat_unit_smiles', '')
            if ru_smi:
                mol_data.append(["반복단위 SMILES", ru_smi])
            poly_type = getattr(self._props, 'poly_type', '')
            if poly_type:
                type_kr = {
                    'addition': '첨가 중합 (Addition)',
                    'condensation': '축합 중합 (Condensation)',
                    'ring_opening': '개환 중합 (Ring-Opening)',
                }.get(poly_type, poly_type)
                mol_data.append(["중합 유형", type_kr])

        cap = self._next_tbl("단량체 기본 정보")
        els.append(Paragraph(cap, styles["table_caption"]))
        avail_w = A4[0] - 45 * mm  # left + right margins
        tbl = Table(mol_data, colWidths=[avail_w * 0.35, avail_w * 0.65])
        ts = self._std_table_style()
        self._add_alt_rows(ts, len(mol_data))
        tbl.setStyle(ts)
        els.append(tbl)
        els.append(Spacer(1, 4 * mm))

        # 1.2 Group decomposition
        els.append(Paragraph("1.2 작용기 분해 (Group Contribution)", styles["subsection"]))

        groups = {}
        if self._props:
            groups = getattr(self._props, 'group_decomposition', {})

        if groups:
            els.append(Paragraph(
                "Van Krevelen 그룹 기여법에 의한 반복단위 작용기 분해 결과이다. "
                "각 작용기의 기여값(응집 에너지, 몰 부피 등)을 합산하여 "
                "고분자의 거시적 물성을 예측한다.",
                styles["body"]))

            grp_rows = _generate_group_decomposition_table(groups)
            cap2 = self._next_tbl("반복단위 작용기 분해")
            els.append(Paragraph(cap2, styles["table_caption"]))
            tbl2 = Table(grp_rows, colWidths=[avail_w * 0.6, avail_w * 0.4])
            ts2 = self._std_table_style()
            self._add_alt_rows(ts2, len(grp_rows))
            tbl2.setStyle(ts2)
            els.append(tbl2)
        else:
            els.append(Paragraph(
                "작용기 분해 데이터가 제공되지 않았습니다.",
                styles["blank_hint"]))

        els.append(Spacer(1, 4 * mm))

        # 1.3 Polymerization type analysis
        els.append(Paragraph("1.3 중합 유형 판별", styles["subsection"]))

        if self._props:
            poly_type = getattr(self._props, 'poly_type', '')
            if poly_type == 'addition':
                els.append(Paragraph(
                    "단량체에 비닐기(C=C)가 존재하여 <b>첨가 중합(Addition Polymerization)</b>이 "
                    "가능한 것으로 판별되었다. 첨가 중합은 개시제에 의해 활성 라디칼 또는 이온이 "
                    "생성되고, 이중결합이 순차적으로 열리면서 사슬이 성장하는 반응이다.",
                    styles["body"]))
            elif poly_type == 'condensation':
                els.append(Paragraph(
                    "단량체에 이관능기(디올, 디산, 디아민 등)가 존재하여 "
                    "<b>축합 중합(Condensation Polymerization)</b>이 가능한 것으로 판별되었다. "
                    "축합 중합은 두 관능기 사이의 반응으로 소분자(H\u2082O 등)가 탈리되면서 "
                    "사슬이 성장하는 단계 성장(step-growth) 반응이다.",
                    styles["body"]))
            elif poly_type == 'ring_opening':
                els.append(Paragraph(
                    "단량체에 고리 구조(에폭사이드, 락톤, 락탐 등)가 존재하여 "
                    "<b>개환 중합(Ring-Opening Polymerization)</b>이 가능한 것으로 판별되었다. "
                    "고리의 변형 에너지(ring strain)가 개환의 열역학적 구동력이 된다.",
                    styles["body"]))
            else:
                els.append(Paragraph(
                    f"중합 유형: {_safe_xml(poly_type)}",
                    styles["body"]))

            # Gold standard notice
            is_gold = getattr(self._props, 'is_gold_standard', False)
            if is_gold:
                els.append(Paragraph(
                    "\u2605 본 고분자는 <b>골드 스탠더드 DB</b>에 등록된 "
                    "문헌값 기반 데이터입니다.",
                    styles["body_bold"]))

        # Warnings
        if self._props:
            warnings = getattr(self._props, 'warnings', [])
            if warnings:
                els.append(Spacer(1, 2 * mm))
                els.append(Paragraph("\u26a0 예측 경고사항:", styles["body_bold"]))
                for w in warnings:
                    els.append(Paragraph(f"\u2022 {_safe_xml(w)}", styles["body_no_indent"]))

        return els

    # ═══════════════════════════════════════════════════════
    # Part 2: Polymerization Conditions
    # ═══════════════════════════════════════════════════════

    def _sec_part2_conditions(self, styles) -> list:
        """Part 2: 중합 반응 조건 — 개시제, 온도, 압력, 용매, 촉매."""
        els = []
        els.append(Paragraph("Part 2. 중합 반응 조건", styles["section"]))
        els.append(HRFlowable(width="100%", thickness=1,
                                color=_COL_SECTION_LINE, spaceAfter=4 * mm))

        # N-guard: conditions가 dict인지 검증 (외부 사용자 데이터)
        cond = self._data.conditions
        if not isinstance(cond, dict):
            logger.warning("polymer_report conditions가 dict가 아닙니다: type=%s", type(cond).__name__)
            cond = {}
        poly_type = ''
        if self._props:
            poly_type = getattr(self._props, 'poly_type', '')

        # 2.1 Reaction conditions table
        els.append(Paragraph("2.1 반응 조건 요약", styles["subsection"]))

        cond_rows = [["조건 항목", "값 / 설명"]]

        # Default conditions based on polymerization type
        default_conds = _get_default_conditions(poly_type)

        fields = [
            ("개시제 (Initiator)", "initiator"),
            ("촉매 (Catalyst)", "catalyst"),
            ("반응 온도", "temperature"),
            ("반응 압력", "pressure"),
            ("용매 (Solvent)", "solvent"),
            ("반응 시간", "reaction_time"),
            ("분위기 (Atmosphere)", "atmosphere"),
            ("교반 속도", "stirring_speed"),
        ]

        for label, key in fields:
            # Rule N: isinstance guard for cond
            if not isinstance(cond, dict): cond = {}
            val = cond.get(key, '') or default_conds.get(key, '-')
            cond_rows.append([label, str(val)])

        cap = self._next_tbl("중합 반응 조건")
        els.append(Paragraph(cap, styles["table_caption"]))
        avail_w = A4[0] - 45 * mm
        tbl = Table(cond_rows, colWidths=[avail_w * 0.35, avail_w * 0.65])
        ts = self._std_table_style()
        self._add_alt_rows(ts, len(cond_rows))
        tbl.setStyle(ts)
        els.append(tbl)
        els.append(Spacer(1, 5 * mm))

        # 2.2 Mechanism description
        els.append(Paragraph("2.2 중합 반응 메커니즘", styles["subsection"]))

        if poly_type == 'addition':
            els.append(Paragraph(
                "라디칼 첨가 중합의 메커니즘은 크게 세 단계로 구분된다:",
                styles["body"]))
            steps = [
                ("<b>개시 (Initiation)</b>: 개시제가 열 또는 광에 의해 분해되어 "
                 "라디칼을 생성한다. 생성된 라디칼이 단량체의 이중결합을 공격하여 "
                 "새로운 라디칼 중간체를 형성한다."),
                ("<b>전파 (Propagation)</b>: 활성 사슬 말단의 라디칼이 "
                 "인접한 단량체의 이중결합과 반복적으로 반응하여 사슬이 성장한다. "
                 "이 단계에서 고분자 사슬의 대부분이 형성된다."),
                ("<b>종결 (Termination)</b>: 두 개의 성장 사슬 라디칼이 "
                 "결합(combination)하거나, 수소 이동에 의한 불균화(disproportionation)로 "
                 "사슬 성장이 정지된다."),
            ]
            for step in steps:
                els.append(Paragraph(step, styles["body"]))
        elif poly_type == 'condensation':
            els.append(Paragraph(
                "축합 중합은 단계 성장(step-growth) 메커니즘을 따른다:",
                styles["body"]))
            steps = [
                ("<b>단량체 반응</b>: 두 관능기(-OH + -COOH, -NH\u2082 + -COOH 등)가 "
                 "반응하여 새로운 공유결합을 형성하고 소분자(H\u2082O, HCl 등)가 탈리된다."),
                ("<b>올리고머 형성</b>: 초기 반응으로 이량체, 삼량체 등 올리고머가 생성된다. "
                 "전환율이 낮을 때는 분자량이 작다."),
                ("<b>고분자 형성</b>: 전환율이 매우 높아져야(>99%) 비로소 "
                 "높은 분자량의 고분자가 얻어진다. Carothers 방정식: "
                 "DP = 1/(1-p), 여기서 p는 전환율이다."),
            ]
            for step in steps:
                els.append(Paragraph(step, styles["body"]))
        elif poly_type == 'ring_opening':
            els.append(Paragraph(
                "개환 중합 메커니즘:",
                styles["body"]))
            steps = [
                ("<b>개시</b>: 개시제(음이온, 양이온, 또는 배위 촉매)가 고리 단량체를 "
                 "공격하여 고리를 열고 활성 말단을 생성한다."),
                ("<b>전파</b>: 활성 말단이 다른 고리 단량체의 고리를 열면서 "
                 "사슬이 성장한다. 고리의 변형 에너지가 반응의 구동력이다."),
                ("<b>종결</b>: 종결제 첨가 또는 불순물에 의해 사슬 성장이 정지된다. "
                 "리빙(living) 중합에서는 종결이 억제되어 좁은 분자량 분포를 얻을 수 있다."),
            ]
            for step in steps:
                els.append(Paragraph(step, styles["body"]))
        else:
            els.append(Paragraph(
                "중합 반응 메커니즘에 대한 세부 정보가 제공되지 않았습니다.",
                styles["blank_hint"]))

        # Custom notes from conditions
        # Rule N: isinstance guard for cond
        if not isinstance(cond, dict): cond = {}
        notes = cond.get('notes', '')
        # N-guard: notes가 str인지 검증
        if not isinstance(notes, str):
            notes = str(notes) if notes else ''
        if notes:
            els.append(Spacer(1, 3 * mm))
            els.append(Paragraph("2.3 추가 참고사항", styles["subsection"]))
            for line in notes.split('\n'):
                if line.strip():
                    els.append(Paragraph(_safe_xml(line.strip()), styles["body"]))

        return els

    # ═══════════════════════════════════════════════════════
    # Part 3: Property Analysis
    # ═══════════════════════════════════════════════════════

    def _sec_part3_properties(self, styles) -> list:
        """Part 3: 고분자 물성 분석 — 열적/기계적/광학 특성."""
        els = []
        els.append(Paragraph("Part 3. 고분자 물성 분석", styles["section"]))
        els.append(HRFlowable(width="100%", thickness=1,
                                color=_COL_SECTION_LINE, spaceAfter=4 * mm))

        p = self._props
        avail_w = A4[0] - 45 * mm

        if not p:
            els.append(Paragraph(
                "고분자 물성 데이터가 제공되지 않았습니다. "
                "polymer_property_engine을 통해 예측을 실행해 주세요.",
                styles["blank_hint"]))
            return els

        # 3.1 Thermal properties
        els.append(Paragraph("3.1 열적 특성", styles["subsection"]))
        els.append(Paragraph(
            "Van Krevelen 그룹 기여법으로 예측된 열적 특성을 아래에 정리한다. "
            "유리전이온도(T<sub>g</sub>), 녹는점(T<sub>m</sub>), "
            "열분해온도(T<sub>d</sub>) 등은 고분자 가공 조건 설정에 핵심적이다.",
            styles["body"]))

        Tg = getattr(p, 'Tg', 0)
        Tm = getattr(p, 'Tm', 0)
        Td = getattr(p, 'Td', 0)
        max_t = getattr(p, 'max_service_temp', 0)
        CTE = getattr(p, 'CTE', 0)
        k_th = getattr(p, 'thermal_conductivity', 0)

        th_rows = [["물성", "기호", "값", "단위"]]
        th_rows.append(["유리전이온도", "Tg", f"{Tg:.1f}", "\u2103"])
        if Tm > 0:
            th_rows.append(["녹는점", "Tm", f"{Tm:.1f}", "\u2103"])
        else:
            th_rows.append(["녹는점", "Tm", "비결정성 (해당 없음)", "-"])
        th_rows.append(["열분해온도", "Td", f"{Td:.1f}", "\u2103"])
        th_rows.append(["최대사용온도", "Tmax", f"{max_t:.1f}", "\u2103"])
        if CTE > 0:
            th_rows.append(["열팽창계수", "CTE",
                             f"{CTE:.1f}", "\u00d710\u207b\u2076/K"])
        if k_th > 0:
            th_rows.append(["열전도도", "\u03bb",
                             f"{k_th:.3f}", "W/(m\u00b7K)"])

        cap = self._next_tbl("열적 특성 요약")
        els.append(Paragraph(cap, styles["table_caption"]))
        tbl = Table(th_rows, colWidths=[avail_w * 0.3, avail_w * 0.15,
                                          avail_w * 0.3, avail_w * 0.25])
        ts = self._std_table_style()
        self._add_alt_rows(ts, len(th_rows))
        tbl.setStyle(ts)
        els.append(tbl)
        els.append(Spacer(1, 4 * mm))

        # Temperature bar chart
        temp_png = _generate_temperature_bar_png(Tg, Tm, Td, max_t)
        if temp_png:
            img = _make_rl_image_from_bytes(temp_png, max_w=155 * mm, max_h=55 * mm)
            if img:
                els.append(img)
                els.append(Paragraph(
                    self._next_fig("열적 전이 온도 분포"),
                    styles["caption"]))

        els.append(Spacer(1, 4 * mm))

        # TGA / DSC simulation graphs
        smi = getattr(self._data, 'monomer_smiles', '') or ''
        tga_dsc_png = _generate_tga_dsc_png(Tg, Tm, Td, monomer_smiles=smi)
        if tga_dsc_png:
            img_td = _make_rl_image_from_bytes(tga_dsc_png, max_w=165 * mm, max_h=70 * mm)
            if img_td:
                els.append(img_td)
                els.append(Paragraph(
                    self._next_fig("TGA/DSC 시뮬레이션 곡선"),
                    styles["caption"]))
                els.append(Spacer(1, 4 * mm))

        # 3.2 Mechanical properties
        els.append(Paragraph("3.2 기계적 특성", styles["subsection"]))
        els.append(Paragraph(
            "그룹 기여법으로 예측된 기계적 물성이다. "
            "인장강도, 영률, 신장률은 고분자 재료의 구조적 용도 판단에 사용된다.",
            styles["body"]))

        tensile = getattr(p, 'tensile_strength', 0)
        modulus = getattr(p, 'youngs_modulus', 0)
        elong = getattr(p, 'elongation_at_break', 0)

        mech_rows = [["물성", "기호", "값", "단위"]]
        mech_rows.append(["인장강도", "\u03c3", f"{tensile:.1f}", "MPa"])
        mech_rows.append(["영률 (탄성계수)", "E", f"{modulus:.0f}", "MPa"])
        mech_rows.append(["파단 신장률", "\u03b5", f"{elong:.1f}", "%"])

        cap2 = self._next_tbl("기계적 특성 요약")
        els.append(Paragraph(cap2, styles["table_caption"]))
        tbl2 = Table(mech_rows, colWidths=[avail_w * 0.3, avail_w * 0.15,
                                             avail_w * 0.3, avail_w * 0.25])
        ts2 = self._std_table_style()
        self._add_alt_rows(ts2, len(mech_rows))
        tbl2.setStyle(ts2)
        els.append(tbl2)
        els.append(Spacer(1, 4 * mm))

        # Mechanical bar chart
        mech_png = _generate_mechanical_bar_png(tensile, modulus, elong)
        if mech_png:
            img2 = _make_rl_image_from_bytes(mech_png, max_w=155 * mm, max_h=55 * mm)
            if img2:
                els.append(img2)
                els.append(Paragraph(
                    self._next_fig("기계적 특성 막대 차트"),
                    styles["caption"]))

        els.append(Spacer(1, 4 * mm))

        # 3.3 Optical & other properties
        els.append(Paragraph("3.3 광학 및 기타 물성", styles["subsection"]))

        density = getattr(p, 'density', 0)
        n_ref = getattr(p, 'refractive_index', 0)
        delta = getattr(p, 'solubility_param', 0)

        opt_rows = [["물성", "기호", "값", "단위"]]
        opt_rows.append(["밀도", "\u03c1", f"{density:.3f}", "g/cm\u00b3"])
        opt_rows.append(["굴절률", "n", f"{n_ref:.3f}", "-"])
        opt_rows.append(["용해도 파라미터", "\u03b4",
                           f"{delta:.1f}", "(MJ/m\u00b3)\u00b9/\u00b2"])

        cap3 = self._next_tbl("광학 및 기타 물성")
        els.append(Paragraph(cap3, styles["table_caption"]))
        tbl3 = Table(opt_rows, colWidths=[avail_w * 0.3, avail_w * 0.15,
                                            avail_w * 0.3, avail_w * 0.25])
        ts3 = self._std_table_style()
        self._add_alt_rows(ts3, len(opt_rows))
        tbl3.setStyle(ts3)
        els.append(tbl3)

        # Interpretation paragraph
        els.append(Spacer(1, 3 * mm))
        interp = _build_property_interpretation(p)
        if interp:
            els.append(Paragraph("3.4 물성 해석", styles["subsection"]))
            els.append(Paragraph(interp, styles["body"]))

        return els

    # ═══════════════════════════════════════════════════════
    # Part 4: Application & AI Interpretation
    # ═══════════════════════════════════════════════════════

    def _sec_part4_application(self, styles) -> list:
        """Part 4: 응용 분석 및 AI 해석."""
        els = []
        els.append(Paragraph("Part 4. 응용 분석 및 AI 해석", styles["section"]))
        els.append(HRFlowable(width="100%", thickness=1,
                                color=_COL_SECTION_LINE, spaceAfter=4 * mm))

        # 4.1 Application areas
        els.append(Paragraph("4.1 응용 분야 추천", styles["subsection"]))

        applications = _suggest_applications(self._props)
        if applications:
            for app_name, app_desc in applications:
                els.append(Paragraph(
                    f"<b>\u2022 {_safe_xml(app_name)}</b>: {_safe_xml(app_desc)}",
                    styles["body_no_indent"]))
        else:
            els.append(Paragraph(
                "응용 분야 추천 데이터를 생성할 수 없습니다.",
                styles["blank_hint"]))

        els.append(Spacer(1, 5 * mm))

        # 4.2 AI interpretation
        els.append(Paragraph("4.2 AI 종합 해석", styles["subsection"]))

        ai_text = self._data.ai_text
        if ai_text:
            for para in ai_text.split('\n\n'):
                para = para.strip()
                if para:
                    els.append(Paragraph(_safe_xml(para), styles["body"]))
        else:
            # Auto-generate basic interpretation if no AI text
            auto_text = _generate_auto_interpretation(self._props, self._data.monomer_smiles)
            if auto_text:
                els.append(Paragraph(_safe_xml(auto_text), styles["body"]))
            else:
                els.append(Paragraph(
                    "(AI 해석 텍스트가 제공되지 않았습니다. "
                    "Groq/Gemini API를 통해 자동 해석을 생성할 수 있습니다.)",
                    styles["blank_hint"]))

        return els

    # ═══════════════════════════════════════════════════════
    # Part 5: Comparative Analysis
    # ═══════════════════════════════════════════════════════

    def _sec_part5_comparison(self, styles) -> list:
        """Part 5: 비교 분석 — 범용 고분자 비교 (레이더차트 + 비교표)."""
        els = []
        els.append(Paragraph("Part 5. 비교 분석", styles["section"]))
        els.append(HRFlowable(width="100%", thickness=1,
                                color=_COL_SECTION_LINE, spaceAfter=4 * mm))

        els.append(Paragraph(
            "주요 범용 고분자(PE, PP, PTFE, PVC, PS)와의 물성 비교를 통해 "
            "본 고분자의 상대적 위치를 파악한다.",
            styles["body"]))

        # 5.1 Radar chart
        els.append(Paragraph("5.1 물성 비교 레이더 차트", styles["subsection"]))

        radar_png = _generate_radar_comparison_png(self._props)
        if radar_png:
            img = _make_rl_image_from_bytes(radar_png, max_w=140 * mm, max_h=140 * mm)
            if img:
                els.append(img)
                els.append(Paragraph(
                    self._next_fig("범용 고분자 물성 비교 레이더 차트"),
                    styles["caption"]))
        else:
            els.append(Paragraph(
                "(레이더 차트 생성 실패 — matplotlib 필요)",
                styles["blank_hint"]))

        els.append(Spacer(1, 5 * mm))

        # 5.2 Comparison table
        els.append(Paragraph("5.2 물성 비교표", styles["subsection"]))

        avail_w = A4[0] - 45 * mm
        refs = _RADAR_REFERENCE_POLYMERS

        # Header row
        comp_rows = [["물성", "본 고분자"]]
        for name in refs:
            comp_rows[0].append(name)

        # Data rows
        p = self._props
        props_list = [
            ("밀도 (g/cm\u00b3)", "density", "density", ".3f"),
            ("Tg (\u2103)", "Tg", "Tg", ".0f"),
            ("Tm (\u2103)", "Tm", "Tm", ".0f"),
            ("인장강도 (MPa)", "tensile_strength", "tensile", ".1f"),
            ("영률 (MPa)", "youngs_modulus", "modulus", ".0f"),
            ("\u03b4 (MJ/m\u00b3)\u00b9/\u00b2", "solubility_param", "delta", ".1f"),
        ]

        for label, attr_name, ref_key, fmt in props_list:
            row = [label]
            val = getattr(p, attr_name, 0) if p else 0
            row.append(f"{val:{fmt}}")
            for rdata in refs.values():
                # N-guard: rdata 타입 검증
                if isinstance(rdata, dict):
                    rval = rdata.get(ref_key, 0)
                else:
                    rval = 0
                row.append(f"{rval:{fmt}}")
            comp_rows.append(row)

        cap = self._next_tbl("범용 고분자 물성 비교")
        els.append(Paragraph(cap, styles["table_caption"]))

        n_cols = 2 + len(refs)  # "물성" + "본 고분자" + 5 refs
        col_w_first = avail_w * 0.22
        col_w_each = (avail_w - col_w_first) / (n_cols - 1)
        col_widths = [col_w_first] + [col_w_each] * (n_cols - 1)

        tbl = Table(comp_rows, colWidths=col_widths)
        ts = self._std_table_style()
        self._add_alt_rows(ts, len(comp_rows))
        # Right-align numeric columns
        ts.add("ALIGN", (1, 1), (-1, -1), "CENTER")
        tbl.setStyle(ts)
        els.append(tbl)

        els.append(Spacer(1, 5 * mm))

        # 5.3 Summary
        els.append(Paragraph("5.3 비교 요약", styles["subsection"]))
        summary = _build_comparison_summary(self._props, refs)
        if summary:
            els.append(Paragraph(summary, styles["body"]))
        else:
            els.append(Paragraph(
                "(비교 요약을 생성할 수 없습니다.)",
                styles["blank_hint"]))

        return els

    # ====================================================================
    # Part 6: 분광분석 (M709 POLYMER-REPORT-001)
    # ====================================================================

    def _sec_part6_spectrum(self, styles) -> list:
        """Part 6: 분광분석 — 단량체(중합 전) + 고분자 반복단위(중합 후).

        IR (Transmittance) + 1H-NMR + UV-Vis 3패널 matplotlib 그래프.
        SIMULATION_MODE 배너 (Rule GG) — 이론적 스펙트럼, 실측 아님.
        """
        if not REPORTLAB_AVAILABLE or not MATPLOTLIB_AVAILABLE:
            return []
        _register_fonts()
        fn = _FN if _FONT_REGISTERED else "Helvetica"
        fnb = _FNB if _FONT_REGISTERED else "Helvetica-Bold"

        els = []
        # ── 섹션 제목
        els.append(Paragraph(
            "Part 6: 분광분석 (Spectroscopic Analysis)",
            styles.get("h1", ParagraphStyle("h1", fontName=fnb, fontSize=16,
                                            spaceAfter=6, textColor=colors.HexColor("#00695C")))
        ))
        # ── Rule GG: SIMULATION_MODE 배너 (노랑)
        sim_banner_style = ParagraphStyle(
            "sim_banner",
            fontName=fn, fontSize=9,
            backColor=colors.HexColor("#FFF9C4"),
            textColor=colors.HexColor("#7B3F00"),
            borderColor=colors.HexColor("#F0AD4E"),
            borderWidth=1,
            borderPadding=6,
            spaceAfter=10,
        )
        els.append(Paragraph(
            "⚠️ [SIMULATION MODE] 이론적 스펙트럼 (ChemGrid 예측 엔진 기반) — "
            "실험적으로 측정된 스펙트럼이 아님. "
            "학술 논문 제출 시 실측 데이터로 대체 필수.",
            sim_banner_style
        ))
        els.append(Spacer(1, 4 * mm))

        smi = (self._data.monomer_smiles or "").strip()
        props = self._props

        # ── predict_spectra 엔진 호출 (Rule POLYMER-REPORT-001)
        monomer_spectra = getattr(self._data, 'monomer_spectra', None)
        polymer_spectra = getattr(self._data, 'polymer_spectra', None)
        if monomer_spectra is None and smi:
            try:
                from predict_spectra import predict_all as _predict_all
                monomer_spectra = _predict_all(smi)
            except Exception as e:
                logger.warning("predict_spectra.predict_all 실패 (단량체): %s", e)
        if polymer_spectra is None and props is not None:
            repeat_smi = getattr(props, 'repeat_unit_smiles', smi)
            if repeat_smi and repeat_smi != smi:
                try:
                    from predict_spectra import predict_all as _predict_all
                    polymer_spectra = _predict_all(repeat_smi)
                except Exception as e:
                    logger.warning("predict_spectra.predict_all 실패 (반복단위): %s", e)

        # ── 단량체 스펙트럼 그래프
        els.append(Paragraph(
            "6-1. 단량체 이론적 스펙트럼 (중합 전)",
            styles.get("h2", ParagraphStyle("h2", fontName=fnb, fontSize=13,
                                            spaceAfter=4,
                                            textColor=colors.HexColor("#1565C0")))
        ))
        mono_png = self._render_spectrum_figure(
            smi, monomer_spectra, label="단량체 (Monomer)")
        if mono_png:
            img = _make_rl_image_from_bytes(mono_png, max_w=155 * mm, max_h=90 * mm)
            if img:
                els.append(img)
        else:
            els.append(Paragraph(
                "(단량체 스펙트럼 생성 불가 — SMILES 파싱 실패 또는 matplotlib 오류)",
                styles.get("blank_hint",
                           ParagraphStyle("blank_hint", fontName=fn,
                                          fontSize=9, textColor=colors.grey))
            ))
        els.append(Spacer(1, 6 * mm))

        # ── 고분자 반복단위 스펙트럼 그래프
        els.append(Paragraph(
            "6-2. 고분자 반복단위 이론적 스펙트럼 (중합 후)",
            styles.get("h2", ParagraphStyle("h2", fontName=fnb, fontSize=13,
                                            spaceAfter=4,
                                            textColor=colors.HexColor("#1565C0")))
        ))
        repeat_smi = getattr(props, 'repeat_unit_smiles', smi) if props else smi
        poly_png = self._render_spectrum_figure(
            repeat_smi, polymer_spectra, label="고분자 반복단위 (Repeat Unit)")
        if poly_png:
            img2 = _make_rl_image_from_bytes(poly_png, max_w=155 * mm, max_h=90 * mm)
            if img2:
                els.append(img2)
        else:
            els.append(Paragraph(
                "(고분자 반복단위 스펙트럼 생성 불가)",
                styles.get("blank_hint",
                           ParagraphStyle("blank_hint", fontName=fn,
                                          fontSize=9, textColor=colors.grey))
            ))
        return els

    def _render_spectrum_figure(self, smiles: str, spectra_data,
                                label: str = "") -> Optional[bytes]:
        """3-panel spectrum figure: IR / 1H-NMR / UV-Vis.

        Rule Q: matplotlib fontproperties 필수.
        Returns PNG bytes or None on failure.
        """
        if not MATPLOTLIB_AVAILABLE or not smiles:
            return None
        try:
            fp = _get_mpl_fontprop()
            fig, axes = plt.subplots(1, 3, figsize=(14, 4))
            fig.suptitle(
                label + " [SIMULATION — 이론적 스펙트럼]",
                fontproperties=fp, fontsize=11, color="#7B3F00"
            )

            # ── IR (Transmittance vs wavenumber)
            ax_ir = axes[0]
            if spectra_data is not None and hasattr(spectra_data, 'ir'):
                ir = spectra_data.ir
                wn = getattr(ir, 'wavenumbers', None)
                tr = getattr(ir, 'transmittance', None)
                if wn is not None and tr is not None:
                    ax_ir.plot(wn, tr, color='#1565C0', linewidth=1.0)
                    ax_ir.invert_xaxis()
                else:
                    self._draw_theoretical_ir(ax_ir, smiles)
            else:
                self._draw_theoretical_ir(ax_ir, smiles)
            ax_ir.set_xlabel("파수 (cm⁻¹)", fontproperties=fp)
            ax_ir.set_ylabel("투과율 (%)", fontproperties=fp)
            ax_ir.set_title("적외선 스펙트럼 (IR)", fontproperties=fp)
            ax_ir.set_ylim(0, 105)

            # ── 1H-NMR (ppm scale)
            ax_nmr = axes[1]
            if spectra_data is not None and hasattr(spectra_data, 'nmr'):
                nmr = spectra_data.nmr
                shifts = getattr(nmr, 'chemical_shifts', None)
                intens = getattr(nmr, 'intensities', None)
                if shifts is not None and intens is not None:
                    for s, h in zip(shifts, intens):
                        ax_nmr.plot([s, s], [0, h], color='#2E7D32', linewidth=1.5)
                else:
                    self._draw_theoretical_nmr(ax_nmr, smiles)
            else:
                self._draw_theoretical_nmr(ax_nmr, smiles)
            ax_nmr.invert_xaxis()
            ax_nmr.set_xlabel("화학적 이동 (δ, ppm)", fontproperties=fp)
            ax_nmr.set_ylabel("강도 (a.u.)", fontproperties=fp)
            ax_nmr.set_title("¹H-NMR 스펙트럼", fontproperties=fp)
            ax_nmr.set_xlim(12, -1)

            # ── UV-Vis
            ax_uv = axes[2]
            if spectra_data is not None and hasattr(spectra_data, 'uv_vis'):
                uv = spectra_data.uv_vis
                wl = getattr(uv, 'wavelengths', None)
                ab = getattr(uv, 'absorbance', None)
                if wl is not None and ab is not None:
                    ax_uv.plot(wl, ab, color='#6A1B9A', linewidth=1.0)
                else:
                    self._draw_theoretical_uv(ax_uv, smiles)
            else:
                self._draw_theoretical_uv(ax_uv, smiles)
            ax_uv.set_xlabel("파장 (nm)", fontproperties=fp)
            ax_uv.set_ylabel("흡광도 (A)", fontproperties=fp)
            ax_uv.set_title("UV-Vis 스펙트럼", fontproperties=fp)

            fig.tight_layout()
            png_bytes = _fig_to_png_bytes(fig, dpi=150)
            plt.close(fig)
            return png_bytes
        except Exception as e:
            logger.warning("_render_spectrum_figure 실패 (%s): %s", label, e)
            return None

    def _draw_theoretical_ir(self, ax, smiles: str):
        """SMILES 기반 이론적 IR 스펙트럼 — Lorentzian 합성."""
        if not RDKIT_AVAILABLE or not smiles:
            ax.text(0.5, 0.5, "IR 데이터 없음", transform=ax.transAxes,
                    ha='center', va='center', color='grey')
            return
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                ax.text(0.5, 0.5, "SMILES 파싱 불가", transform=ax.transAxes,
                        ha='center', va='center', color='grey')
                return
            import numpy as _np
            wn = _np.linspace(500, 4000, 1000)
            tr = _np.ones_like(wn) * 95  # baseline transmittance
            # 작용기 기반 흡수 피크 이론적 배정
            peaks = []  # (center_cm-1, depth, width)
            ri = mol.GetRingInfo()
            has_ring = ri.NumRings() > 0
            has_oh = any(
                a.GetAtomicNum() == 8 and
                any(n.GetAtomicNum() == 1 for n in a.GetNeighbors())
                for a in mol.GetAtoms()
            )
            has_nh = any(
                a.GetAtomicNum() == 7 and
                any(n.GetAtomicNum() == 1 for n in a.GetNeighbors())
                for a in mol.GetAtoms()
            )
            has_co = any(
                a.GetAtomicNum() == 8 and
                any(b.GetBondTypeAsDouble() == 2 for b in a.GetBonds())
                for a in mol.GetAtoms()
            )
            # C-H stretch ~2900 cm-1
            peaks.append((2900, 40, 60))
            if has_oh:
                peaks.append((3350, 60, 150))   # O-H broad
                peaks.append((1050, 50, 50))    # C-O
            if has_nh:
                peaks.append((3350, 45, 80))    # N-H
            if has_co:
                peaks.append((1720, 70, 40))    # C=O carbonyl
            if has_ring:
                peaks.append((1600, 35, 25))    # C=C aromatic
                peaks.append((700, 50, 30))     # out-of-plane
            for center, depth, width in peaks:
                tr -= depth * _np.exp(-((wn - center) ** 2) / (2 * width ** 2))
            tr = _np.clip(tr, 5, 100)
            ax.plot(wn, tr, color='#1565C0', linewidth=1.0)
            ax.invert_xaxis()
            ax.set_ylim(0, 105)
        except Exception as e:
            logger.warning("_draw_theoretical_ir 실패: %s", e)

    def _draw_theoretical_nmr(self, ax, smiles: str):
        """SMILES 기반 이론적 1H-NMR 스펙트럼 — 간단한 피크 예측."""
        if not RDKIT_AVAILABLE or not smiles:
            ax.text(0.5, 0.5, "NMR 데이터 없음", transform=ax.transAxes,
                    ha='center', va='center', color='grey')
            return
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                ax.text(0.5, 0.5, "SMILES 파싱 불가", transform=ax.transAxes,
                        ha='center', va='center', color='grey')
                return
            # 간단한 이론적 1H 화학이동 배정
            peaks = []  # (ppm, height)
            for atom in mol.GetAtoms():
                if atom.GetAtomicNum() == 6:  # Carbon
                    hn = atom.GetTotalNumHs()
                    if hn == 0:
                        continue
                    nb_nums = [n.GetAtomicNum() for n in atom.GetNeighbors()]
                    # 방향족 환경: ~7.2 ppm
                    if atom.GetIsAromatic():
                        peaks.append((7.2 + (atom.GetIdx() % 5) * 0.05, hn))
                    elif 8 in nb_nums or 7 in nb_nums:
                        peaks.append((3.5 + (atom.GetIdx() % 10) * 0.1, hn))
                    elif any(nb.GetIsAromatic() for nb in atom.GetNeighbors()):
                        peaks.append((2.3 + (atom.GetIdx() % 5) * 0.05, hn))
                    else:
                        peaks.append((1.2 + (atom.GetIdx() % 15) * 0.05, hn))
                elif atom.GetAtomicNum() == 8:
                    hn = atom.GetTotalNumHs()
                    if hn > 0:
                        peaks.append((4.5, hn * 0.8))  # OH broad
            for ppm, ht in peaks:
                ax.plot([ppm, ppm], [0, ht], color='#2E7D32', linewidth=1.5)
            ax.set_xlim(12, -1)
        except Exception as e:
            logger.warning("_draw_theoretical_nmr 실패: %s", e)

    def _draw_theoretical_uv(self, ax, smiles: str):
        """SMILES 기반 이론적 UV-Vis 스펙트럼 — Gaussian 밴드."""
        if not RDKIT_AVAILABLE or not smiles:
            ax.text(0.5, 0.5, "UV-Vis 데이터 없음", transform=ax.transAxes,
                    ha='center', va='center', color='grey')
            return
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                ax.text(0.5, 0.5, "SMILES 파싱 불가", transform=ax.transAxes,
                        ha='center', va='center', color='grey')
                return
            import numpy as _np
            wl = _np.linspace(200, 700, 500)
            ab = _np.zeros_like(wl)
            ri = mol.GetRingInfo()
            n_arom = sum(1 for ring in ri.AtomRings()
                         if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring))
            # sigma: ~200 nm, pi: ~250 nm, n->pi* carbonyl ~330nm, extended pi ~350nm+
            ab += 1.2 * _np.exp(-((wl - 205) ** 2) / (2 * 15 ** 2))
            has_pi = any(b.GetBondTypeAsDouble() >= 2 for b in mol.GetBonds())
            if has_pi:
                ab += 0.8 * _np.exp(-((wl - 250) ** 2) / (2 * 20 ** 2))
            has_co = any(
                a.GetAtomicNum() == 8 and
                any(b.GetBondTypeAsDouble() == 2 for b in a.GetBonds())
                for a in mol.GetAtoms()
            )
            if has_co:
                ab += 0.15 * _np.exp(-((wl - 335) ** 2) / (2 * 30 ** 2))
            if n_arom >= 1:
                ab += 0.6 * _np.exp(-((wl - 254 + n_arom * 15) ** 2) / (2 * 25 ** 2))
            if n_arom >= 2:
                ab += 0.4 * _np.exp(-((wl - 320 + n_arom * 10) ** 2) / (2 * 35 ** 2))
            ab = _np.clip(ab, 0, None)
            ax.plot(wl, ab, color='#6A1B9A', linewidth=1.0)
        except Exception as e:
            logger.warning("_draw_theoretical_uv 실패: %s", e)

    # ====================================================================
    # Part 7: 합성방법 (M709 POLYMER-REPORT-001)
    # ====================================================================

    def _sec_part7_synthesis(self, styles) -> list:
        """Part 7: 합성방법 — 실험 준비물 표 + 합성 절차 + 정제/분석 방법."""
        if not REPORTLAB_AVAILABLE:
            return []
        _register_fonts()
        fn = _FN if _FONT_REGISTERED else "Helvetica"
        fnb = _FNB if _FONT_REGISTERED else "Helvetica-Bold"

        els = []
        els.append(Paragraph(
            "Part 7: 합성방법 (Synthetic Procedure)",
            styles.get("h1", ParagraphStyle("h1", fontName=fnb, fontSize=16,
                                            spaceAfter=6,
                                            textColor=colors.HexColor("#00695C")))
        ))
        smi = (self._data.monomer_smiles or "").strip()
        props = self._props
        conditions = self._data.conditions or {}
        poly_name = getattr(props, 'polymer_name', smi) if props else smi

        # ── 7.1 실험 준비물 표
        els.append(Paragraph(
            "7-1. 실험 준비물",
            styles.get("h2", ParagraphStyle("h2", fontName=fnb, fontSize=13,
                                            spaceAfter=4,
                                            textColor=colors.HexColor("#1565C0")))
        ))
        reagent_data = _build_reagent_table(smi, conditions, props)
        if reagent_data:
            col_widths = [35 * mm, 25 * mm, 30 * mm, 20 * mm, 45 * mm]
            tbl = Table(reagent_data, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0),
                 colors.HexColor("#004D40")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), fnb),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 1), (-1, -1), fn),
                ("GRID", (0, 0), (-1, -1),
                 0.5, colors.HexColor("#BDBDBD")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F9FBE7")]),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]))
            els.append(tbl)
            els.append(Spacer(1, 4 * mm))

        # ── 7.2 합성 절차
        els.append(Paragraph(
            "7-2. 합성 절차",
            styles.get("h2", ParagraphStyle("h2", fontName=fnb, fontSize=13,
                                            spaceAfter=4,
                                            textColor=colors.HexColor("#1565C0")))
        ))
        synth_text = getattr(self._data, 'synthesis_text', '') or ''
        if not synth_text:
            synth_text = _generate_synthesis_protocol(
                smi, poly_name, conditions, props)
        body_style = styles.get("body_left",
                                ParagraphStyle("body_left", fontName=fn,
                                               fontSize=10, leading=14,
                                               spaceAfter=4))
        for line in synth_text.split("\n"):
            line = line.strip()
            if not line:
                els.append(Spacer(1, 2 * mm))
                continue
            els.append(Paragraph(_safe_xml(line), body_style))

        # ── 7.3 정제 및 분석 방법
        els.append(Spacer(1, 4 * mm))
        els.append(Paragraph(
            "7-3. 정제 및 분석 방법",
            styles.get("h2", ParagraphStyle("h2", fontName=fnb, fontSize=13,
                                            spaceAfter=4,
                                            textColor=colors.HexColor("#1565C0")))
        ))
        purif_lines = [
            "1. 재침전법: 반응 혼합물을 THF에 용해 후 메탄올/에탄올에 적가하여 침전 수집.",
            "2. 여과: 부흐너 깔때기 + 흡인 여과 (GF/C 또는 Nylon 0.45 μm 필터).",
            "3. 세척: 메탄올 50 mL × 3회 반복 (미반응 단량체·개시제 제거).",
            "4. 건조: 60 ℃ 진공 오븐, 24시간 이상 (잔류 용매 < 0.1% 목표).",
            "5. GPC 분석: THF 이동상, PS 표준, Mn·Mw·PDI 측정.",
            "6. 1H-NMR 확인: CDCl3 용매, 400/600 MHz, 전환율 및 반복단위 구조 확인.",
            "7. DSC 분석: N2 분위기, 10 ℃/min 승온, Tg 확인.",
            "8. TGA 분석: N2/공기 분위기, 10 ℃/min, Td5% 측정.",
        ]
        for pl in purif_lines:
            els.append(Paragraph(_safe_xml(pl), body_style))

        return els

    # ====================================================================
    # HWPX Export (M710 POLYMER-REPORT-002)
    # ====================================================================

    def _export_hwpx(self, hwpx_path: str) -> None:
        """ZIP/Open XML HWPX 1.x 형식 내보내기.

        HWPX spec: mimetype 무압축(ZIP_STORED) 의무.
        최소 구조: mimetype + META-INF/container.xml + Contents/section1.xml
        """
        import zipfile
        import xml.etree.ElementTree as ET

        props = self._props
        smi = (self._data.monomer_smiles or "").strip()
        poly_name = getattr(props, 'polymer_name', smi) if props else smi
        date_str = self._data.date or datetime.now().strftime("%Y-%m-%d")

        # ── 1. mimetype (무압축 의무 — HWPX 1.x spec)
        mimetype_content = b"application/hwp+zip"

        # ── 2. META-INF/container.xml
        container_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            '  <rootfiles>\n'
            '    <rootfile full-path="Contents/section1.xml"'
            ' media-type="application/hwp+xml"/>\n'
            '  </rootfiles>\n'
            '</container>'
        )

        # ── 3. Contents/section1.xml (HP namespace)
        # 단순 텍스트 본문 — poly 이름 + 물성 요약
        Tg_val = getattr(props, 'Tg', 0) if props else 0
        tensile_val = getattr(props, 'tensile_strength', 0) if props else 0
        mw_val = getattr(props, 'molecular_weight', 0) if props else 0

        body_text = (
            f"{poly_name} 고분자 분석 보고서\n"
            f"작성일: {date_str}\n"
            f"단량체 SMILES: {smi}\n\n"
            f"주요 물성:\n"
            f"  유리전이온도 Tg: {Tg_val:.1f} ℃\n"
            f"  인장강도: {tensile_val:.0f} MPa\n"
            f"  분자량: {mw_val:.0f} g/mol\n\n"
            "[Part 6: 분광분석 — PDF 본문 참조]\n"
            "[Part 7: 합성방법 — PDF 본문 참조]\n"
        )

        section_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<hsp:HSParaList xmlns:hsp="http://www.hancom.co.kr/hwpml/2012/HWPStyle"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2012/paragraph">\n'
        )
        for line in body_text.split("\n"):
            # XML 특수문자 이스케이프
            safe_line = (line.replace("&", "&amp;").replace("<", "&lt;")
                         .replace(">", "&gt;").replace('"', "&quot;"))
            section_xml += (
                f'  <hp:p><hp:run><hp:t>{safe_line}</hp:t></hp:run></hp:p>\n'
            )
        section_xml += '</hsp:HSParaList>'

        # ── ZIP 생성
        with zipfile.ZipFile(hwpx_path, 'w') as zf:
            # mimetype: 반드시 첫 번째, 무압축(ZIP_STORED)
            zf.writestr(zipfile.ZipInfo("mimetype"), mimetype_content,
                        compress_type=zipfile.ZIP_STORED)
            zf.writestr("META-INF/container.xml",
                        container_xml.encode("utf-8"),
                        compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("Contents/section1.xml",
                        section_xml.encode("utf-8"),
                        compress_type=zipfile.ZIP_DEFLATED)

        logger.info("_export_hwpx 완료: %s", hwpx_path)


# ═══════════════════════════════════════════════════════════
# Helper: Default polymerization conditions
# ═══════════════════════════════════════════════════════════

def _get_default_conditions(poly_type: str) -> Dict[str, str]:
    """Return default polymerization conditions based on type."""
    if poly_type == 'addition':
        return {
            "initiator": "AIBN (아조비스이소부티로니트릴) 또는 BPO (벤조일퍼옥사이드)",
            "catalyst": "-",
            "temperature": "60~80 \u2103 (열개시) 또는 실온 (광개시)",
            "pressure": "상압 (1 atm)",
            "solvent": "벌크 중합 또는 톨루엔/THF",
            "reaction_time": "2~24시간",
            "atmosphere": "N\u2082 (질소 분위기)",
            "stirring_speed": "200~500 rpm",
        }
    elif poly_type == 'condensation':
        return {
            "initiator": "-",
            "catalyst": "p-TSA (p-톨루엔설폰산) 또는 Ti(OBu)\u2084",
            "temperature": "180~280 \u2103",
            "pressure": "감압 (소분자 제거)",
            "solvent": "벌크 중합 (무용매)",
            "reaction_time": "4~12시간",
            "atmosphere": "N\u2082 (질소 분위기)",
            "stirring_speed": "100~300 rpm",
        }
    elif poly_type == 'ring_opening':
        return {
            "initiator": "Sn(Oct)\u2082 (옥토산주석) 또는 NaH",
            "catalyst": "배위 촉매 또는 유기촉매",
            "temperature": "25~150 \u2103",
            "pressure": "상압 (1 atm)",
            "solvent": "톨루엔, DCM, 또는 벌크",
            "reaction_time": "1~48시간",
            "atmosphere": "N\u2082 또는 Ar (불활성 분위기)",
            "stirring_speed": "200~500 rpm",
        }
    return {
        "initiator": "-",
        "catalyst": "-",
        "temperature": "-",
        "pressure": "-",
        "solvent": "-",
        "reaction_time": "-",
        "atmosphere": "-",
        "stirring_speed": "-",
    }


# ═══════════════════════════════════════════════════════════
# Helper: Property interpretation
# ═══════════════════════════════════════════════════════════

def _build_property_interpretation(props) -> str:
    """Build a property interpretation paragraph from PolymerProperties."""
    if props is None:
        return ""

    lines = []
    Tg = getattr(props, 'Tg', 0)
    Tm = getattr(props, 'Tm', 0)
    tensile = getattr(props, 'tensile_strength', 0)
    modulus = getattr(props, 'youngs_modulus', 0)
    elong = getattr(props, 'elongation_at_break', 0)
    density = getattr(props, 'density', 0)

    # Tg interpretation
    if Tg > 100:
        lines.append(
            f"유리전이온도(Tg={Tg:.0f}\u2103)가 높아 상온에서 단단하고 "
            "취성이 있는 유리질 고분자이다.")
    elif Tg > 25:
        lines.append(
            f"유리전이온도(Tg={Tg:.0f}\u2103)가 상온 근처에 위치하여 "
            "사용 환경에 따라 유리질-고무질 전이가 일어날 수 있다.")
    else:
        lines.append(
            f"유리전이온도(Tg={Tg:.0f}\u2103)가 낮아 상온에서 "
            "유연한 고무질 거동을 보인다.")

    # Tm/crystallinity
    if Tm > 0:
        ratio = (Tg + 273.15) / (Tm + 273.15) if (Tm + 273.15) > 0 else 0
        lines.append(
            f"Tg/Tm 비율은 {ratio:.2f}로, "
            f"{'대칭 고분자' if ratio < 0.55 else '비대칭 고분자'}에 해당한다 "
            f"(Boyer-Beaman 규칙: 대칭 ~0.50, 비대칭 ~0.67).")
    else:
        lines.append("결정성이 낮아 녹는점이 관측되지 않는 비결정성 고분자이다.")

    # Mechanical character
    if tensile > 60:
        lines.append(
            f"인장강도({tensile:.0f} MPa)가 높아 구조 재료 용도에 적합하다.")
    elif tensile > 30:
        lines.append(
            f"인장강도({tensile:.0f} MPa)가 중간 수준으로 일반 범용 고분자 수준이다.")
    else:
        lines.append(
            f"인장강도({tensile:.0f} MPa)가 낮아 구조 용도보다는 "
            "필름, 코팅 등 비구조적 용도에 적합하다.")

    if elong > 200:
        lines.append(
            f"파단 신장률({elong:.0f}%)이 높아 우수한 연성(ductility)을 가진다.")
    elif elong < 10:
        lines.append(
            f"파단 신장률({elong:.0f}%)이 매우 낮아 취성 파괴 거동을 보인다.")

    return " ".join(lines)


def _suggest_applications(props) -> List[Tuple[str, str]]:
    """Suggest application areas based on polymer properties."""
    if props is None:
        return []

    apps = []
    Tg = getattr(props, 'Tg', 0)
    Tm = getattr(props, 'Tm', 0)
    Td = getattr(props, 'Td', 0)
    tensile = getattr(props, 'tensile_strength', 0)
    modulus = getattr(props, 'youngs_modulus', 0)
    elong = getattr(props, 'elongation_at_break', 0)
    n_ref = getattr(props, 'refractive_index', 0)
    delta = getattr(props, 'solubility_param', 0)

    # High temperature resistance
    if Td > 400 or (Tm > 250 and Td > 350):
        apps.append(("내열 부품", "높은 열분해온도와 녹는점으로 "
                       "자동차 엔진룸, 전자기기 내열 부품에 적용 가능하다."))

    # Structural material
    if tensile > 50 and modulus > 2000:
        apps.append(("구조 재료", "높은 인장강도와 영률로 기계 부품, "
                       "건축 자재 등 하중 지지 구조물에 적합하다."))

    # Flexible packaging
    if elong > 200 and Tg < 0:
        apps.append(("유연 포장재", "높은 신장률과 낮은 유리전이온도로 "
                       "식품 포장 필름, 산업용 포장재에 적합하다."))

    # Optical application
    if n_ref > 1.45 and n_ref < 1.65:
        apps.append(("광학 소재", f"굴절률({n_ref:.3f})이 적절하여 "
                       "렌즈, 광도파관, 광학 필름에 응용 가능하다."))

    # Elastomer
    if Tg < -20 and elong > 300:
        apps.append(("엘라스토머", "낮은 Tg와 높은 신장률로 "
                       "씰링재, 가스켓, 의료용 튜브에 활용 가능하다."))

    # Biomedical (based on solubility and density)
    if 1.0 <= getattr(props, 'density', 0) <= 1.5 and delta > 18:
        apps.append(("생체의료 소재", "밀도와 용해도 파라미터가 적절하여 "
                       "생체적합성 검토 후 의료기기/약물 전달체에 활용 가능하다."))

    # Default if no specific match
    if not apps:
        apps.append(("범용 플라스틱", "일반적인 열가소성 수지로서 "
                       "사출성형, 압출성형 등 다양한 가공법 적용이 가능하다."))

    return apps


def _generate_auto_interpretation(props, monomer_smiles: str) -> str:
    """Generate automatic interpretation text when no AI text is provided."""
    if props is None:
        return ""

    name = getattr(props, 'polymer_name_kr', '') or getattr(props, 'polymer_name', '')
    if not name:
        name = "본 고분자"

    poly_type = getattr(props, 'poly_type', '')
    type_str = {
        'addition': '첨가 중합',
        'condensation': '축합 중합',
        'ring_opening': '개환 중합',
    }.get(poly_type, '중합')

    Tg = getattr(props, 'Tg', 0)
    Tm = getattr(props, 'Tm', 0)
    tensile = getattr(props, 'tensile_strength', 0)

    is_gold = getattr(props, 'is_gold_standard', False)
    source = "문헌값(골드 스탠더드 DB)" if is_gold else "Van Krevelen 그룹 기여법 예측"

    lines = []
    lines.append(
        f"{_safe_xml(name)}은(는) {type_str}으로 합성 가능한 고분자로, "
        f"본 보고서의 물성 데이터는 {source}에 기반한다.")

    if Tg > 80:
        lines.append(
            f"Tg가 {Tg:.0f}\u2103로 높아 상온에서 경질 플라스틱 거동을 보이며, "
            "엔지니어링 플라스틱으로서의 잠재력이 있다.")
    elif Tg < 0:
        lines.append(
            f"Tg가 {Tg:.0f}\u2103로 낮아 상온에서 유연한 탄성체 거동을 보이며, "
            "필름 및 코팅 분야에 적합하다.")

    if tensile > 50:
        lines.append(
            f"인장강도 {tensile:.0f} MPa로 우수한 기계적 강도를 보여 "
            "구조 재료로서 활용 가치가 높다.")

    return " ".join(lines)


def _build_comparison_summary(props, refs: Dict) -> str:
    """Build a comparison summary paragraph."""
    if props is None:
        return ""

    name = getattr(props, 'polymer_name', '본 고분자')
    Tg = getattr(props, 'Tg', 0)
    tensile = getattr(props, 'tensile_strength', 0)
    density = getattr(props, 'density', 0)

    # Find closest reference polymer by Tg
    closest_name = ""
    closest_diff = float('inf')
    for rname, rdata in refs.items():
        # N-guard: rdata 타입 검증
        if not isinstance(rdata, dict):
            continue
        diff = abs(Tg - rdata.get('Tg', 0))
        if diff < closest_diff:
            closest_diff = diff
            closest_name = rname

    # Find polymer with highest tensile
    max_t_name = max(refs, key=lambda k: refs[k].get('tensile', 0) if isinstance(refs[k], dict) else 0)
    max_t_ref = refs.get(max_t_name)
    max_t_val = max_t_ref.get('tensile', 0) if isinstance(max_t_ref, dict) else 0

    lines = []
    lines.append(
        f"{_safe_xml(name)}의 유리전이온도(Tg={Tg:.0f}\u2103)는 "
        f"범용 고분자 중 {closest_name}과(와) 가장 유사하다.")

    if tensile > max_t_val:
        lines.append(
            f"인장강도({tensile:.0f} MPa)는 비교 대상 범용 고분자 중 "
            f"가장 높은 {max_t_name}({max_t_val:.0f} MPa)보다 우수하다.")
    elif tensile > max_t_val * 0.8:
        lines.append(
            f"인장강도({tensile:.0f} MPa)는 {max_t_name}({max_t_val:.0f} MPa)에 "
            "근접하는 수준이다.")

    if density < 1.0:
        lines.append("밀도가 1.0 g/cm\u00b3 미만으로 경량 소재에 해당한다.")
    elif density > 1.5:
        lines.append(
            f"밀도({density:.2f} g/cm\u00b3)가 높아 무거운 편이나 "
            "이는 할로겐 또는 금속 원소 함유에 기인할 수 있다.")

    return " ".join(lines)


# ═══════════════════════════════════════════════════════════
# Helper: Part 7 Synthesis Protocol (M709)
# ═══════════════════════════════════════════════════════════

def _build_reagent_table(smiles: str, conditions: dict,
                         props) -> List[List[str]]:
    """실험 준비물 테이블 빌드 (헤더 행 포함).

    Returns: List[List[str]] — 첫 행 = 헤더.
    """
    poly_type = (conditions.get("polymerization_type", "")
                 or (getattr(props, 'polymerization_type', '') if props else ''))

    header = ["시약/재료", "분자량 (g/mol)", "사용량 (예시)",
              "순도", "비고"]
    rows = [header]

    mono_mw = (getattr(props, 'molecular_weight', 100) if props else 100)
    if not isinstance(mono_mw, (int, float)) or mono_mw <= 0:
        mono_mw = 100

    # 단량체
    rows.append([smiles[:18] + "..." if len(smiles) > 18 else smiles,
                 f"{mono_mw:.1f}", "5.0 g (1.0 eq)",
                 "≥98%", "단량체"])

    # 개시제/촉매
    initiator = conditions.get("initiator", "")
    if not initiator:
        if poly_type == "addition":
            initiator = "AIBN"
        elif poly_type == "condensation":
            initiator = "p-TsOH"
        else:
            initiator = "BPO"
    rows.append([initiator, "—", "0.05~0.10 eq",
                 "≥97%", "개시제"])

    # 용매
    solvent = conditions.get("solvent", "THF")
    rows.append([solvent, "—", "50 mL / 1g monomer",
                 "HPLC급", "반응 용매"])

    # 정제 용매
    rows.append(["메탄올 (MeOH)", "32.04",
                 "300 mL (재침전)", "≥99%", "재침전 용매"])
    rows.append(["증류수 (DI Water)", "18.02",
                 "필요시", "≥99.9%", "세척"])
    rows.append(["GPC 용매 (THF)", "72.11",
                 "200 mL", "HPLC급", "분자량 분석"])

    return rows


def _generate_synthesis_protocol(smiles: str, poly_name: str,
                                  conditions: dict, props) -> str:
    """단계별 합성 절차 문자열 생성."""
    poly_type = (conditions.get("polymerization_type", "")
                 or (getattr(props, 'polymerization_type', '') if props else ''))
    temp = conditions.get("temperature", "60~80 ℃")
    atm = conditions.get("atmosphere", "N₂ 분위기")
    initiator = conditions.get("initiator", "AIBN")
    solvent = conditions.get("solvent", "THF")
    time_ = conditions.get("reaction_time", "6~12시간")

    if poly_type == "condensation":
        steps = [
            "【사전 준비】",
            f"1. 단량체 ({smiles[:20]}...) 및 모든 시약을 진공 오븐(60 ℃, 24h)에서 사전 건조한다.",
            "2. 반응 플라스크(250 mL 3구 RB Flask)를 오븐 건조 후 N₂ purge한다.",
            "",
            "【중합 반응】",
            f"3. 건조 단량체를 {solvent}에 용해 (0.5~1.0 M 농도)한다.",
            f"4. 촉매/개시제 ({initiator})를 0.05~0.10 eq 첨가한다.",
            f"5. {atm} 하에서 {temp}로 가열하며 {time_} 교반 반응한다.",
            "6. TLC로 반응 진행 모니터링 (1~2시간 간격).",
            "",
            "【후처리 및 정제】",
            "7. 반응 완료 후 실온 냉각. 메탄올에 적가하여 침전 유도.",
            "8. 여과 후 메탄올로 3회 세척 (미반응 단량체 제거).",
            "9. 진공 건조 (60 ℃, 24h).",
        ]
    else:  # radical addition (default)
        steps = [
            "【사전 준비】",
            f"1. 단량체 ({smiles[:20]}...)를 Al₂O₃ 컬럼으로 억제제 제거 후 사용.",
            "2. 반응 플라스크(250 mL 슐렝크 플라스크)를 오븐 건조.",
            "3. 동결-펌프-해동(Freeze-pump-thaw) 3회 탈기.",
            "",
            "【중합 반응 — 자유 라디칼 중합】",
            f"4. 단량체를 {solvent}에 용해 (1.0~2.0 M). 개시제 ({initiator}) 0.1 wt% 첨가.",
            f"5. 반응 용기를 {atm} 하에서 {temp}로 가열.",
            f"6. {time_} 동안 교반 유지 (200~300 rpm).",
            "7. 전환율이 목표치(50~80%) 달성 시 드라이아이스 배스로 급냉하여 반응 정지.",
            "",
            "【후처리 및 정제】",
            "8. 반응 혼합물을 소량 THF에 용해 후 메탄올(10배 부피)에 적가하여 재침전.",
            "9. 부흐너 깔때기로 진공 여과 (Nylon 0.45 μm 필터).",
            "10. 메탄올 50 mL × 3회 세척 후 진공 건조 (50 ℃, 24h).",
            "",
            "【특성 분석】",
            f"11. ¹H-NMR (CDCl₃, 400 MHz): {poly_name} 반복단위 구조 확인.",
            "12. GPC (THF, 25 ℃, 1.0 mL/min, PS 표준): Mn, Mw, PDI 측정.",
            "13. DSC (N₂, 10 ℃/min, -100→200 ℃): Tg 확인.",
        ]

    return "\n".join(steps)


# ═══════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════

def export_polymer_report(data: PolymerReportData,
                           file_path: str) -> Tuple[bool, str]:
    """Export polymer analysis report as PDF.

    Args:
        data: PolymerReportData containing all analysis data.
        file_path: Output PDF file path.

    Returns:
        (success: bool, message: str) — message is file_path on success,
        error description on failure.
    """
    exporter = PolymerReportExporter(data)
    return exporter.export(file_path)
