"""
popup_predicted_spectrum.py
===========================
SMILES 기반 예측 스펙트럼 팝업 (ORCA 파일 없이 작동)
각 탭에 IR, Raman, 1H-NMR, 13C-NMR, UV-Vis 그래프 표시

[GUIDE.md v3 기준 — 2026-03-11]
- IR     : 빨간선, Fingerprint 영역 음영, 작용기 annotation, 피크↓ (Transmittance %)
           [BUG FIX] ylim(-5,108) — bottom=-5/top=108 → 위=100%, 아래=0%, 피크 아래 방향
- ¹H-NMR : 계단형 적분선, 피크별 그룹 색상 매핑, multiplicity/δ 표기
           [NEW] AddHs 구조식 — 수소 전부 표시 + 피크-수소 색상 하이라이트
- ¹³C-NMR: 영역 색띠 5구간, 탄소 귀속
           [NEW] AddHs 구조식 — 탄소 zone별 색상 하이라이트 + H도 부모 탄소 색상
- Raman  : 진홍색 선, 주요 피크 배경 밴드 하이라이트
           [NEW] IR ghost layer — IR 스펙트럼을 alpha=0.08로 배경 중첩 (상보성 표시)
- UV-Vis : ε 좌 + log ε 우 듀얼 뷰, λmax 수직점선, 전이 타입 라벨, x축 200~700 nm
"""
from __future__ import annotations
import math
from typing import List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QPushButton, QSizePolicy,
    QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QFrame, QGroupBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

# matplotlib 임포트
try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.patches as mpatches
    import matplotlib.gridspec as gridspec
    MPL_OK = True
except ImportError:
    MPL_OK = False

# 예측 모듈
try:
    from predict_spectra import (
        predict_all, PredictedSpectra, IRPeak, RamanPeak,
        NMRPeak, C13Peak, UVVisPeak
    )
    PREDICT_OK = True
except ImportError:
    PREDICT_OK = False

# 실험 데이터 임포트 모듈
try:
    from experimental_data_importer import (
        load_experimental_file, compare_spectra,
        ir_peaks_to_comparison_format,
        uvvis_peaks_to_comparison_format,
        raman_peaks_to_comparison_format,
        ExperimentalSpectrum, SpectrumComparison,
    )
    EXP_IMPORT_OK = True
except ImportError:
    EXP_IMPORT_OK = False

import logging
_logger = logging.getLogger(__name__)


# ─── 색상 유틸 ──────────────────────────────────────────────────────

def _hex_to_rgb01(hex_color: str):
    """#RRGGBB → (r, g, b) 0~1 범위 (RDKit/matplotlib용)"""
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))


# ─── ¹H-NMR 수소 환경 그룹별 색상 (GUIDE.md §3.2) ──────────────────

_H_COLOR_MAP = {
    "ArH":   "#F39C12",   # 주황  - 방향족 H
    "CHO":   "#1ABC9C",   # 청록  - 알데히드 H
    "OH":    "#9B59B6",   # 보라  - 히드록실
    "NH":    "#8E44AD",   # 진보라 - 아민 H
    "vinyl": "#2980B9",   # 진파랑 - 알켄 =CH
    "OCH":   "#3498DB",   # 파랑  - O-CH₂/O-CH₃
    "NCH":   "#16A085",   # 청록  - N-CH
    "CHX":   "#E74C3C",   # 빨강  - 할라이드 α
    "CH2CO": "#E67E22",   # 주황  - C=O α 메틸렌
    "other": "#7F8C8D",   # 회색  - 기타 알케인
}

def _h_color(assignment: str) -> str:
    """¹H-NMR 피크 assignment → 색상 코드"""
    a = assignment.lower()
    if "ar-h" in a or "aromatic" in a:
        return _H_COLOR_MAP["ArH"]
    if "cho" in a or "aldehyde" in a:
        return _H_COLOR_MAP["CHO"]
    if "carboxyl" in a:
        return _H_COLOR_MAP["OH"]
    if "o-h" in a or "alcohol" in a:
        return _H_COLOR_MAP["OH"]
    if "n-h" in a:
        return _H_COLOR_MAP["NH"]
    if "vinyl" in a or "=ch" in a:
        return _H_COLOR_MAP["vinyl"]
    if "och" in a or "c-o" in a:
        return _H_COLOR_MAP["OCH"]
    if "nch" in a or "c-n" in a:
        return _H_COLOR_MAP["NCH"]
    if "halide" in a or "chx" in a:
        return _H_COLOR_MAP["CHX"]
    if "c=o" in a or "adjacent to c=o" in a:
        return _H_COLOR_MAP["CH2CO"]
    return _H_COLOR_MAP["other"]


# ─── RDKit 원자 환경 추론 ────────────────────────────────────────────

def _infer_h_env_str(parent_atom, mol) -> str:
    """
    부모 원자(C/O/N)로부터 붙은 H의 화학적 환경을 assignment 문자열로 반환.
    predict_spectra.py의 assignment 형식과 매핑 가능하도록 작성.
    """
    ps = parent_atom.GetSymbol()

    if ps == "O":
        # 카르복시산 O-H: O의 이웃 C가 또 다른 O(=O)와 결합?
        for nbr in parent_atom.GetNeighbors():
            if nbr.GetSymbol() == "C":
                for nbr2 in nbr.GetNeighbors():
                    if (nbr2.GetSymbol() == "O"
                            and nbr2.GetIdx() != parent_atom.GetIdx()
                            and nbr2.GetTotalNumHs() == 0):
                        return "carboxyl O-H"
        return "O-H"

    elif ps == "N":
        return "N-H"

    elif ps == "C":
        try:
            from rdkit.Chem import rdchem
            if parent_atom.GetIsAromatic():
                return "Ar-H"

            hyb = parent_atom.GetHybridization()
            if hyb == rdchem.HybridizationType.SP2:
                # CHO (알데히드)
                for nbr in parent_atom.GetNeighbors():
                    if nbr.GetSymbol() == "O" and nbr.GetTotalNumHs() == 0:
                        # 이 C=O가 1개 H (aldehyde H)인지
                        if parent_atom.GetTotalNumHs() >= 1:
                            return "CHO"
                return "vinyl"

            # sp3 탄소
            for nbr in parent_atom.GetNeighbors():
                s = nbr.GetSymbol()
                if s == "O":
                    return "OCH"
                if s == "N":
                    return "NCH"
                if s in ("Cl", "Br", "I", "F"):
                    return "CHX"

            # C=O 알파 위치
            for nbr in parent_atom.GetNeighbors():
                if nbr.GetSymbol() == "C":
                    from rdkit.Chem import rdchem as rc2
                    if nbr.GetHybridization() == rc2.HybridizationType.SP2:
                        for nbr2 in nbr.GetNeighbors():
                            if nbr2.GetSymbol() == "O":
                                return "C=O alpha"
        except Exception as e:
            _logger.warning("[PopupPredictedSpectrum] _get_h1_environment RDKit processing failed: %s", e)

    return "other"


def _get_h1_atom_highlights(smiles: str, peaks):
    """
    ¹H-NMR 피크의 색상에 해당하는 수소 원자 인덱스 → RDKit highlight_colors dict.
    AddHs(mol) 기준 인덱스 반환.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return [], {}
        mol_h = Chem.AddHs(mol)
        AllChem.Compute2DCoords(mol_h)

        highlight_atoms = []
        highlight_colors = {}

        for atom in mol_h.GetAtoms():
            if atom.GetAtomicNum() != 1:
                continue
            nbrs = atom.GetNeighbors()
            if not nbrs:
                continue
            parent = nbrs[0]
            env_str = _infer_h_env_str(parent, mol_h)
            color_hex = _h_color(env_str)
            color_rgb = _hex_to_rgb01(color_hex)
            idx = atom.GetIdx()
            if idx not in highlight_colors:
                highlight_atoms.append(idx)
                highlight_colors[idx] = color_rgb

        return highlight_atoms, highlight_colors

    except Exception:
        return [], {}


def _get_c13_atom_highlights(smiles: str):
    """
    ¹³C-NMR: 탄소 원자를 zone별 색상으로 매핑.
    수소도 부모 탄소 색상으로 매핑.
    AddHs(mol) 기준 인덱스 반환.
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem, rdchem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return [], {}
        mol_h = Chem.AddHs(mol)
        AllChem.Compute2DCoords(mol_h)

        zone_color_hex = {
            "aliphatic": "#1E8449",
            "c_o":       "#D35400",   # C-O/C-N (50~90 ppm)
            "aromatic":  "#1A5276",
            "carbonyl":  "#922B21",
        }

        highlight_atoms = []
        highlight_colors = {}

        for atom in mol_h.GetAtoms():
            if atom.GetAtomicNum() != 6:
                continue

            is_arom = atom.GetIsAromatic()
            hyb = atom.GetHybridization()

            if is_arom:
                zone = "aromatic"
            elif hyb == rdchem.HybridizationType.SP2:
                # carbonyl 여부
                is_co = any(
                    mol_h.GetBondBetweenAtoms(
                        atom.GetIdx(),
                        b.GetOtherAtomIdx(atom.GetIdx())
                    ).GetBondType() == Chem.rdchem.BondType.DOUBLE
                    and mol_h.GetAtomWithIdx(
                        b.GetOtherAtomIdx(atom.GetIdx())
                    ).GetAtomicNum() == 8
                    for b in atom.GetBonds()
                )
                zone = "carbonyl" if is_co else "aromatic"
            else:
                # C-O/C-N 여부 (50~90 ppm 구간)
                has_o_n = any(
                    nb.GetAtomicNum() in (7, 8)
                    for nb in atom.GetNeighbors()
                )
                zone = "c_o" if has_o_n else "aliphatic"

            color_hex = zone_color_hex.get(zone, "#2C3E50")
            idx = atom.GetIdx()
            highlight_atoms.append(idx)
            highlight_colors[idx] = _hex_to_rgb01(color_hex)

        # 수소에도 부모 탄소 색상 적용
        for atom in mol_h.GetAtoms():
            if atom.GetAtomicNum() != 1:
                continue
            nbrs = atom.GetNeighbors()
            if nbrs and nbrs[0].GetIdx() in highlight_colors:
                idx = atom.GetIdx()
                highlight_atoms.append(idx)
                highlight_colors[idx] = highlight_colors[nbrs[0].GetIdx()]

        return highlight_atoms, highlight_colors

    except Exception:
        return [], {}


# ─── 공통: RDKit 구조식 (H 포함) → Axes ────────────────────────────

def _draw_structure_lewis(ax_mol, smiles: str, title: str = "Structure",
                          highlight_atoms=None, highlight_colors=None):
    """
    [NEW v3] RDKit AddHs + rdMolDraw2D으로 수소 전부 표시 (루이스 구조 스타일).
    highlight_atoms / highlight_colors: 피크와 연결된 원자 하이라이트.
    RDKit/Pillow 미설치 시 SMILES 텍스트 fallback.
    """
    try:
        import numpy as np
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from rdkit.Chem.Draw import rdMolDraw2D
        from io import BytesIO

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError("Invalid SMILES")

        # ★ 핵심: H 전부 추가 (루이스 구조처럼)
        mol_h = Chem.AddHs(mol)
        AllChem.Compute2DCoords(mol_h)

        drawer = rdMolDraw2D.MolDraw2DCairo(300, 220)
        opts = drawer.drawOptions()
        opts.padding = 0.12
        opts.addAtomIndices = False
        opts.addStereoAnnotation = False
        opts.explicitMethyl = True    # CH₃를 명시적으로 표시

        if highlight_atoms and highlight_colors:
            # RDKit highlight: atom_idx → (r,g,b) 0~1
            valid_ha = [i for i in highlight_atoms if i < mol_h.GetNumAtoms()]
            valid_hc = {i: highlight_colors[i]
                        for i in valid_ha if i in highlight_colors}
            drawer.DrawMolecule(mol_h,
                                highlightAtoms=valid_ha,
                                highlightAtomColors=valid_hc,
                                highlightBonds=[],
                                highlightBondColors={})
        else:
            drawer.DrawMolecule(mol_h)

        drawer.FinishDrawing()

        from PIL import Image
        img = Image.open(BytesIO(drawer.GetDrawingText()))
        ax_mol.imshow(np.array(img))
        ax_mol.axis('off')
        ax_mol.set_title(title, fontsize=8, color='#2C3E50', pad=3)

    except Exception:
        # fallback: 텍스트 표시
        ax_mol.text(0.5, 0.58, "구조식 (Lewis)", ha='center', va='center',
                    fontsize=10, color='#7F8C8D', transform=ax_mol.transAxes)
        ax_mol.text(0.5, 0.38, smiles[:30] + ("…" if len(smiles) > 30 else ""),
                    ha='center', va='center', fontsize=6.5, color='#95A5A6',
                    transform=ax_mol.transAxes, style='italic')
        ax_mol.text(0.5, 0.22, "(RDKit/Pillow 필요)", ha='center', va='center',
                    fontsize=6, color='#BDC3C7', transform=ax_mol.transAxes)
        ax_mol.set_xlim(0, 1)
        ax_mol.set_ylim(0, 1)
        for spine in ax_mol.spines.values():
            spine.set_edgecolor('#E0E0E0')
        ax_mol.set_xticks([])
        ax_mol.set_yticks([])
        ax_mol.set_title(title, fontsize=8, color='#2C3E50', pad=3)


# ─── IR 스펙트럼 ──────────────────────────────────────────────────────

def _make_ir_figure(peaks: List) -> "Figure":
    """
    IR 스펙트럼 Figure 생성
    GUIDE.md §3.1 기준:
      - 빨간 실선, x축 4000→400, y축 Transmittance%, 피크↓
      - 지문 영역(400~1500) 배경 음영 + 레이블
      - 주요 피크 작용기 annotation

    [BUG FIX v3] ylim(-5, 108)
      - bottom=-5 (화면 아래), top=108 (화면 위)
      - y=100(baseline)이 화면 위쪽에 위치 → 피크(y값 낮음)가 아래로 뾰족함 ✅
      - 이전 ylim(108, -12)는 bottom=108/top=-12 → 축이 뒤집혀 피크가 위로 솟았음 (수정됨)
    """
    import numpy as np

    fig = Figure(figsize=(9.0, 4.5), facecolor='white')
    ax = fig.add_subplot(111)

    x_arr = np.linspace(400, 4000, 3000)
    baseline_y = 100.0
    y_arr = np.full_like(x_arr, baseline_y)

    for pk in peaks:
        if "fingerprint" in pk.assignment:
            continue
        sigma = max(pk.width / 2.355, 5.0)
        # 피크 깊이: baseline - transmittance_min → 아래로 오목
        depth = baseline_y - pk.transmittance
        gauss = depth * np.exp(-0.5 * ((x_arr - pk.wavenumber) / sigma) ** 2)
        y_arr -= gauss  # 빼기 → y값이 낮아짐 → 화면에서 아래로

    # 지문 영역 복잡한 패턴
    fp_mask = x_arr < 1500
    rng = np.random.default_rng(42)
    fp_noise = 5.0 * np.sin(x_arr[fp_mask] * 0.08) * rng.random(fp_mask.sum())
    y_arr[fp_mask] -= np.abs(fp_noise)
    y_arr = np.clip(y_arr, 0, 100)

    # ① 지문 영역 배경 음영 (400~1500 cm⁻¹)
    ax.axvspan(400, 1500, alpha=0.12, color='#E8A0A0', zorder=0)
    ax.text(950, 96, "◀ Fingerprint Region", fontsize=7.5, color='#c0392b',
            ha='center', va='top', style='italic', alpha=0.9, zorder=1)

    # ② 스펙트럼 선 (빨간색)
    ax.plot(x_arr, y_arr, color='#C0392B', lw=1.4, zorder=3)
    ax.fill_between(x_arr, y_arr, baseline_y, alpha=0.08, color='#E74C3C', zorder=2)

    # ③ 작용기 Annotation
    non_fp = [pk for pk in peaks
              if "fingerprint" not in pk.assignment and pk.transmittance < 70]
    non_fp.sort(key=lambda p: p.transmittance)  # 강한 피크 우선

    annotated = []
    ann_y_offsets = []

    for pk in non_fp[:8]:
        if any(abs(pk.wavenumber - w) < 80 for w in annotated):
            continue
        annotated.append(pk.wavenumber)

        idx = np.argmin(np.abs(x_arr - pk.wavenumber))
        y_at_peak = y_arr[idx]

        short = (pk.assignment
                 .replace("str.", "ν")
                 .replace("bend", "δ")
                 .replace(" (broad)", "†")
                 .replace(" (carboxylic)", "†")
                 .strip())

        # 피크 아래(낮은 Transmittance)에 주석 배치
        # ylim(-5,108)이므로 y_at_peak가 낮을수록 화면 아래
        # annotation은 피크 아래 방향으로 (y를 더 낮게)
        offset_y = 8 + 5 * (len(ann_y_offsets) % 3)

        ax.annotate(
            f"{pk.wavenumber:.0f}\n{short}",
            xy=(pk.wavenumber, y_at_peak),
            xytext=(pk.wavenumber, y_at_peak - offset_y),
            fontsize=6, ha='center', color='#1A252F', zorder=5,
            arrowprops=dict(arrowstyle='->', color='#95A5A6', lw=0.7),
            bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                      edgecolor='#BDC3C7', alpha=0.92, lw=0.8)
        )
        ann_y_offsets.append(offset_y)

    ax.set_xlim(4000, 400)      # IR: 고파수 → 저파수
    # [BUG FIX v3] bottom=-5, top=108 → y=100(baseline)이 위, y=0이 아래 → 피크 ↓
    ax.set_ylim(-5, 108)
    # [M816 FIX] Rule Q-c (M566 패턴): cm⁻¹ unicode → matplotlib mathtext
    # Malgun Gothic이 U+207B(SUPERSCRIPT MINUS)/U+00B9(SUPERSCRIPT ONE) 글리프 미지원
    # → 사용자 화면에서 빈 박스(□)로 표시되어 "스펙트럼 다 날려먹었냐"(격분 #15) 발생
    ax.set_xlabel(r"Wavenumber (cm$^{-1}$)", fontsize=9)
    ax.set_ylabel("Transmittance (%)", fontsize=9)
    ax.set_title("IR Spectrum (이론적 스펙트럼, 엔진 기반)", fontsize=10, fontweight='bold', pad=8)  # CLAUDE.md E-a M486
    ax.grid(True, alpha=0.15, color='#AAB7B8')
    ax.text(3980, 105, "* Estimated — not for publication",
            fontsize=6, color='#AAB7B8', style='italic')
    fig.tight_layout(pad=1.5)
    return fig


# ─── ¹H-NMR 스펙트럼 ──────────────────────────────────────────────

def _make_nmr_h1_figure(peaks: List, formula: str, smiles: str = "") -> "Figure":
    """
    ¹H-NMR Figure
    GUIDE.md §3.2 기준:
      - x축 반전 (12→0 ppm), 피크↑
      - 피크별 그룹 색상 매핑 + 계단형 적분선 + multiplicity/δ annotation
      - [NEW v3] AddHs 구조식 — 수소 전부 표시 + 피크-수소 색상 하이라이트
    """
    import numpy as np
    from matplotlib.gridspec import GridSpec

    # 구조식 하이라이트 계산 (RDKit)
    h_atoms, h_colors = _get_h1_atom_highlights(smiles, peaks) if smiles else ([], {})

    fig = Figure(figsize=(9.0, 4.5), facecolor='white')
    gs = GridSpec(1, 2, figure=fig, width_ratios=[1, 2.8],
                  left=0.04, right=0.98, bottom=0.12, top=0.92, wspace=0.10)
    ax_mol = fig.add_subplot(gs[0])
    ax    = fig.add_subplot(gs[1])

    # [NEW v3] AddHs 구조식 + 피크 하이라이트
    _draw_structure_lewis(ax_mol, smiles or "C",
                          title=f"¹H-NMR 귀속\n{formula}",
                          highlight_atoms=h_atoms,
                          highlight_colors=h_colors)

    # 피크-색상 범례 (구조식 패널 하단)
    if peaks:
        color_seen = {}
        for pk in peaks:
            clr = _h_color(pk.assignment)
            if clr not in color_seen:
                color_seen[clr] = pk.assignment
        for i, (clr, label) in enumerate(color_seen.items()):
            row = i // 2
            col = i % 2
            legend_y = -0.04
            rect = mpatches.FancyBboxPatch(
                (0.05 + col * 0.50, legend_y - row * 0.10), 0.08, 0.07,
                boxstyle="round,pad=0.01", transform=ax_mol.transAxes,
                facecolor=clr, alpha=0.75, clip_on=False
            )
            ax_mol.add_patch(rect)
            ax_mol.text(0.15 + col * 0.50, legend_y - row * 0.10 + 0.035,
                        label[:14], fontsize=5.2, va='center', color='#2C3E50',
                        transform=ax_mol.transAxes, clip_on=False)

    if not peaks:
        ax.text(6, 0.5, "No ¹H peaks detected", ha='center', fontsize=10, color='gray')
        ax.set_xlim(12, 0)
        ax.set_xlabel("Chemical Shift δ (ppm)", fontsize=9)
        ax.set_ylabel("Intensity (a.u.)", fontsize=9)
        ax.set_title(f"¹H-NMR Spectrum (이론적 스펙트럼, 엔진 기반) — {formula}", fontsize=10, fontweight='bold')  # CLAUDE.md E-a M486
        return fig

    x_arr = np.linspace(-0.5, 13.0, 5000)
    y_total = np.zeros_like(x_arr)
    sigma = 0.035

    colors = [_h_color(pk.assignment) for pk in peaks]
    max_integ = max(p.integration for p in peaks)

    peak_gaussians = []
    for pk, color in zip(peaks, colors):
        norm = pk.integration / max_integ
        gauss = norm * np.exp(-0.5 * ((x_arr - pk.shift) / sigma) ** 2)
        peak_gaussians.append(gauss)
        y_total += gauss
        ax.fill_between(x_arr, gauss, alpha=0.30, color=color, zorder=2)
        ax.plot(x_arr, gauss, color=color, lw=1.6, alpha=0.85, zorder=3)

    ax.plot(x_arr, y_total, color='#2C3E50', lw=0.8, alpha=0.4, zorder=4)

    y_max = max(y_total.max(), 0.1)

    # ① 계단형 적분선
    integ_base  = y_max * 1.12
    integ_scale = y_max * 0.15

    sorted_pks = sorted(enumerate(peaks), key=lambda t: t[1].shift)
    cumulative = 0.0
    for orig_idx, pk in sorted_pks:
        cumulative += pk.integration
        half = max(sigma * 3, 0.18)
        step_height = integ_base + (cumulative / max_integ) * integ_scale
        ax.plot([pk.shift - half, pk.shift + half],
                [step_height, step_height],
                color=colors[orig_idx], lw=2.2, solid_capstyle='butt', zorder=6)
        ax.text(pk.shift, step_height + integ_scale * 0.15,
                f"{pk.integration:.0f}H",
                fontsize=6.5, ha='center', va='bottom',
                color=colors[orig_idx], fontweight='bold', zorder=7)

    # 계단 수직 연결선
    pks_sorted = sorted(zip(peaks, colors), key=lambda t: t[0].shift)
    cumul2 = 0.0
    prev_x = prev_y = None
    for pk, _ in pks_sorted:
        half = max(sigma * 3, 0.18)
        next_cumul = cumul2 + pk.integration
        next_step_y = integ_base + (next_cumul / max_integ) * integ_scale
        x_left = pk.shift - half
        x_right = pk.shift + half
        if prev_x is not None:
            ax.plot([prev_x, x_left], [prev_y, prev_y],
                    color='#E74C3C', lw=0.8, alpha=0.4, zorder=5)
            ax.plot([x_left, x_left], [prev_y, next_step_y],
                    color='#E74C3C', lw=0.8, alpha=0.4, zorder=5)
        prev_x = x_right
        prev_y = next_step_y
        cumul2 = next_cumul

    # ② δ + multiplicity annotation
    for pk, color in zip(peaks, colors):
        idx = np.argmin(np.abs(x_arr - pk.shift))
        peak_y = y_total[idx]
        if peak_y > 0.015:
            ax.annotate(
                f"δ {pk.shift:.2f}\n({pk.multiplicity})",
                xy=(pk.shift, peak_y),
                xytext=(0, 10), textcoords='offset points',
                fontsize=6.5, ha='center', color=color, fontweight='bold',
                arrowprops=dict(arrowstyle='-', color=color, lw=0.5, alpha=0.5),
                zorder=8
            )

    # TMS 기준선
    ax.axvline(x=0, color='#7F8C8D', lw=0.9, linestyle='--', alpha=0.5, zorder=1)
    ax.text(0.05, y_max * 0.92, "TMS\n0.00", fontsize=5.5, color='#7F8C8D', ha='left', va='top')

    ax.set_xlim(12, 0)
    ax.set_ylim(-0.05, y_max * 2.0)
    ax.set_xlabel("Chemical Shift δ (ppm)", fontsize=9)
    ax.set_ylabel("Intensity (a.u.)", fontsize=9)
    ax.set_title(f"¹H-NMR Spectrum (이론적 스펙트럼, 엔진 기반) — {formula}",  # CLAUDE.md E-a M486
                 fontsize=10, fontweight='bold', pad=8)
    ax.grid(True, alpha=0.12, color='#AAB7B8')
    ax.text(11.8, -0.04, "* Estimated — not for publication",
            fontsize=6, color='#AAB7B8', style='italic')
    return fig


# ─── ¹³C-NMR 스펙트럼 ─────────────────────────────────────────────

def _make_nmr_c13_figure(peaks: List, formula: str, smiles: str = "") -> "Figure":
    """
    ¹³C-NMR Figure
    GUIDE.md §3.3 기준:
      - x축 반전 (220→0 ppm), 수직 피크선↑, 영역 색띠 5구간
      - [NEW v3] AddHs 구조식 — 탄소 zone별 색상 + H도 동일 색 하이라이트
    """
    import numpy as np
    from matplotlib.gridspec import GridSpec

    # 구조식 하이라이트 계산
    c_atoms, c_colors = _get_c13_atom_highlights(smiles) if smiles else ([], {})

    fig = Figure(figsize=(9.0, 4.5), facecolor='white')
    gs = GridSpec(1, 2, figure=fig, width_ratios=[1, 2.8],
                  left=0.04, right=0.98, bottom=0.12, top=0.92, wspace=0.10)
    ax_mol = fig.add_subplot(gs[0])
    ax    = fig.add_subplot(gs[1])

    # [NEW v3] AddHs 구조식 + zone 색상 하이라이트
    _draw_structure_lewis(ax_mol, smiles or "C",
                          title=f"¹³C-NMR 귀속\n{formula}",
                          highlight_atoms=c_atoms,
                          highlight_colors=c_colors)

    # ① 영역 색띠 (Zone Coloring) - GUIDE.md §3.3
    zone_bands = [
        (0,   50,  '#FEF9E7', 'Aliphatic\n(sp³)'),
        (50,  90,  '#FDF2E9', 'C–O / C–N\n(sp³)'),
        (90,  100, '#F4F6F7', 'Alkyne\n(sp)'),
        (100, 160, '#FDEDEC', 'Aromatic /\nAlkene (sp²)'),
        (160, 220, '#F5EEF8', 'Carbonyl\n(C=O)'),
    ]
    for x_lo, x_hi, clr, lbl in zone_bands:
        ax.axvspan(x_lo, x_hi, alpha=0.60, color=clr, zorder=0)
        mid = (x_lo + x_hi) / 2
        ax.text(mid, 0.96, lbl, fontsize=5.8, ha='center', va='top',
                color='#5D6D7E', style='italic', zorder=1, multialignment='center',
                transform=ax.get_xaxis_transform())

    for boundary in [50, 90, 100, 160]:
        ax.axvline(x=boundary, color='#BFC9CA', lw=0.7, linestyle=':', alpha=0.8, zorder=1)

    if peaks:
        zone_colors_hex = {
            "aliphatic": "#1E8449",
            "aromatic":  "#1A5276",
            "carbonyl":  "#922B21",
        }
        peak_h = 0.68

        for i, pk in enumerate(peaks):
            color = zone_colors_hex.get(pk.zone, '#2C3E50')
            if 50 <= pk.shift <= 90 and pk.zone == "aliphatic":
                color = "#D35400"  # C-O/C-N 구간

            # [M682 item21] 막대 두께 2.0→1.0px (사용자: "막대그래프 두께 너무 두껍다")
            ax.plot([pk.shift, pk.shift], [0, peak_h],
                    color=color, lw=1.0, alpha=0.82, solid_capstyle='butt', zorder=3)

            # [M682 item21] 레이블 폰트 5.8→8.0pt (사용자: "위 글자 너무 작다")
            ax.text(pk.shift, peak_h + 0.02, f"{pk.shift:.1f}",
                    fontsize=8.0, ha='center', va='bottom', color=color,
                    fontweight='bold', rotation=90, zorder=4)

            short_asgn = (pk.assignment
                          .replace("(aliphatic)", "")
                          .replace("(aromatic)", "")
                          .replace("(carbonyl)", "")
                          .strip())
            if len(short_asgn) > 15:
                short_asgn = short_asgn[:15]

            y_asgn = peak_h + 0.22 if i % 2 == 0 else peak_h + 0.06
            ax.text(pk.shift, y_asgn, short_asgn,
                    fontsize=5.2, ha='center', va='bottom',
                    color=color, alpha=0.85, rotation=90, zorder=4)
    else:
        ax.text(110, 0.5, "No ¹³C peaks detected", ha='center',
                fontsize=10, color='gray')

    ax.set_xlim(220, 0)
    ax.set_ylim(0, 1.35)
    ax.set_xlabel("Chemical Shift δ (ppm)", fontsize=9)
    ax.set_ylabel("Intensity (a.u.)", fontsize=9)
    ax.set_title(f"¹³C-NMR Spectrum (이론적 스펙트럼, 엔진 기반) — {formula}",  # CLAUDE.md E-a M486
                 fontsize=10, fontweight='bold', pad=8)
    ax.grid(True, alpha=0.10, axis='x', color='#AAB7B8')

    legend_patches = [
        mpatches.Patch(color='#1E8449', alpha=0.7, label='Aliphatic (0–50 ppm)'),
        mpatches.Patch(color='#D35400', alpha=0.7, label='C–O/C–N (50–90 ppm)'),
        mpatches.Patch(color='#1A5276', alpha=0.7, label='Aromatic/Alkene (100–160 ppm)'),
        mpatches.Patch(color='#922B21', alpha=0.7, label='Carbonyl (160–220 ppm)'),
    ]
    ax.legend(handles=legend_patches, fontsize=6.5, loc='upper right', framealpha=0.88)
    ax.text(218, 0.02, "* Estimated — not for publication",
            fontsize=6, color='#AAB7B8', style='italic')
    return fig


# ─── Raman 스펙트럼 ────────────────────────────────────────────────

def _make_raman_figure(peaks: List, ir_peaks: List = None) -> "Figure":
    """
    Raman Figure
    GUIDE.md §3.4 기준:
      - 진홍색 선, x축 0→4000 cm⁻¹, 피크↑
      - intensity > 0.45 피크 배경 밴드 하이라이트
      - [NEW v3] IR ghost layer — IR 스펙트럼을 alpha=0.08로 배경에 중첩
        IR과 Raman의 상보성(complementarity) 표시:
          - 극성 결합(C=O, O-H): IR 강함, Raman 약함
          - 비극성 결합(C=C ring, C≡C): Raman 강함, IR 약함
        wavenumber 단위 동일 → 직접 중첩 가능
    """
    import numpy as np

    fig = Figure(figsize=(9.0, 4.5), facecolor='white')
    ax = fig.add_subplot(111)

    x_arr = np.linspace(0, 4000, 3000)
    y_arr = np.zeros_like(x_arr)

    for pk in peaks:
        sigma = max(pk.width / 2.355, 5.0)
        gauss = pk.intensity * np.exp(-0.5 * ((x_arr - pk.shift) / sigma) ** 2)
        y_arr += gauss

    y_max = max(y_arr.max(), 0.1)

    # [NEW v3] IR ghost layer (상보성 시각화)
    if ir_peaks:
        ir_y = np.zeros_like(x_arr)
        for pk in ir_peaks:
            if "fingerprint" in pk.assignment:
                continue
            # IR transmittance → absorbance (0~1): 흡수 강한 곳이 높게
            absorbance = max(0.0, (100.0 - pk.transmittance) / 100.0)
            sigma_ir = max(pk.width / 2.355, 5.0)
            gauss_ir = absorbance * np.exp(-0.5 * ((x_arr - pk.wavenumber) / sigma_ir) ** 2)
            ir_y += gauss_ir

        # Raman y_max 기준으로 정규화 (30% 크기로 배경 표시)
        ir_max = ir_y.max()
        if ir_max > 0:
            ir_y_norm = ir_y / ir_max * y_max * 0.30
            ax.fill_between(x_arr, ir_y_norm, alpha=0.06, color='#5D6D7E', zorder=0)
            ax.plot(x_arr, ir_y_norm, color='#5D6D7E', lw=0.5,
                    alpha=0.12, linestyle='--', zorder=0)
            ax.text(50, y_max * 0.27, "IR (ghost, α≈0.08)",
                    fontsize=5.5, color='#95A5A6', alpha=0.7,
                    style='italic', zorder=1)

    # ① 특징 밴드 하이라이트
    highlight_palette = ['#FDEDEC', '#EAF2FF', '#EAFAF1', '#FEF9E7']
    h_idx = 0
    for pk in peaks:
        if pk.intensity > 0.45:
            half_w = max(pk.width * 2.5, 50)
            ax.axvspan(pk.shift - half_w, pk.shift + half_w,
                       alpha=0.50, color=highlight_palette[h_idx % len(highlight_palette)],
                       zorder=0)
            h_idx += 1

    # ② Raman 선
    ax.plot(x_arr, y_arr, color='#922B21', lw=1.5, zorder=3)
    ax.fill_between(x_arr, y_arr, alpha=0.12, color='#C0392B', zorder=2)

    # ③ 피크 annotation
    annotated = []
    for pk in sorted(peaks, key=lambda p: -p.intensity):
        if pk.intensity < 0.20:
            continue
        if any(abs(pk.shift - w) < 100 for w in annotated):
            continue
        annotated.append(pk.shift)

        idx = np.argmin(np.abs(x_arr - pk.shift))
        y_pk = y_arr[idx]

        # [M816 FIX] cm⁻¹ unicode → mathtext (Malgun Gothic 글리프 미지원 회피)
        ax.annotate(
            f"{pk.shift:.0f} cm$^{{-1}}$\n{pk.assignment}",
            xy=(pk.shift, y_pk),
            xytext=(0, 14), textcoords='offset points',
            fontsize=6.5, ha='center', color='#1A252F', zorder=5,
            arrowprops=dict(arrowstyle='->', color='#95A5A6', lw=0.7),
            bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                      edgecolor='#BDC3C7', alpha=0.92, lw=0.8)
        )

    ax.set_xlim(0, 4000)
    ax.set_ylim(0, y_max * 1.65)
    # [M816 FIX] Rule Q-c (M566 패턴): cm⁻¹ unicode → matplotlib mathtext
    ax.set_xlabel(r"Raman Shift (cm$^{-1}$)", fontsize=9)
    ax.set_ylabel("Intensity (a.u.)", fontsize=9)
    ax.set_title("Raman Spectrum (이론적 스펙트럼, 엔진 기반)", fontsize=10, fontweight='bold', pad=8)  # CLAUDE.md E-a M486
    ax.grid(True, alpha=0.15, color='#AAB7B8')
    ax.text(3980, y_max * 1.58, "* Estimated — not for publication",
            fontsize=6, color='#AAB7B8', style='italic', ha='right')
    fig.tight_layout(pad=1.5)
    return fig


# ─── UV-Vis 스펙트럼 ───────────────────────────────────────────────

def _make_uvvis_figure(peaks: List, smiles: str = "") -> "Figure":
    """
    UV-Vis Figure (듀얼 뷰)
    GUIDE.md §3.5 기준:
      - 좌: ε linear, 우: log ε
      - x축 200~700 nm, λmax 수직 점선, 전이 타입 라벨
      - 라벨 Y_LEVELS 5단계 순환 (중첩 방지)
      - 가시광선(400~700nm) 배경 음영
    [M691_W_P2_UV_INSET] 사용자 격분 (231355 card11 item20):
      "루이스구조를 저 각 그래프의 우측 상단 빈공간(500~700nm의 그래프 안 노란 빈공간)에 표현"
      smiles 제공 시 log ε 그래프 우측 상단 인셋에 2D 구조 삽입 (RDKit Draw2D).
    """
    import numpy as np

    fig = Figure(figsize=(9.0, 4.5), facecolor='white')
    ax1 = fig.add_subplot(121)   # 좌: ε linear
    ax2 = fig.add_subplot(122)   # 우: log ε

    X_MIN, X_MAX = 200, 700
    x_arr = np.linspace(150, 720, 3000)
    y_eps = np.zeros_like(x_arr)

    valid_peaks = [pk for pk in peaks if 150 <= pk.wavelength <= 720]

    for pk in valid_peaks:
        sigma = 22.0
        gauss = pk.epsilon * np.exp(-0.5 * ((x_arr - pk.wavelength) / sigma) ** 2)
        y_eps += gauss

    y_log = np.log10(np.maximum(y_eps, 1.0))
    eps_max = max(y_eps.max(), 10.0)
    log_max = max(y_log.max(), 0.5)

    for ax in (ax1, ax2):
        ax.axvspan(400, 700, alpha=0.07, color='gold', zorder=0)
        ax.text(550, 0, "Visible", fontsize=6.5, color='#B7950B',
                ha='center', va='bottom', alpha=0.9, style='italic')

    ax1.plot(x_arr, y_eps, color='#5B2C6F', lw=1.5, zorder=3)
    ax1.fill_between(x_arr, y_eps, alpha=0.13, color='#8E44AD', zorder=2)
    ax1.set_xlim(X_MIN, X_MAX)
    ax1.set_ylim(0, eps_max * 1.30)
    ax1.set_xlabel("Wavelength λ (nm)", fontsize=9)
    # [M816 FIX] Rule Q-c (M566 패턴): ε / mol⁻¹·cm⁻¹ unicode → matplotlib mathtext
    # Malgun Gothic 글리프 미지원 (U+207B + U+00B9) 회피
    ax1.set_ylabel(r"$\varepsilon$ (L$\cdot$mol$^{-1}$$\cdot$cm$^{-1}$)", fontsize=9)
    ax1.set_title("UV-Vis: ε (Linear)", fontsize=9.5, fontweight='bold')
    ax1.grid(True, alpha=0.15)

    ax2.plot(x_arr, y_log, color='#1A5276', lw=1.5, zorder=3)
    ax2.fill_between(x_arr, y_log, alpha=0.13, color='#2471A3', zorder=2)
    ax2.set_xlim(X_MIN, X_MAX)
    ax2.set_ylim(0, log_max * 1.40)
    ax2.set_xlabel("Wavelength λ (nm)", fontsize=9)
    ax2.set_ylabel("log ε", fontsize=9)
    ax2.set_title("UV-Vis: log ε", fontsize=9.5, fontweight='bold')
    ax2.grid(True, alpha=0.15)

    Y_LEVELS = [0.88, 0.62, 0.40, 0.74, 0.52]
    annotated_lam = []
    vis_pks = sorted(
        [pk for pk in valid_peaks if X_MIN <= pk.wavelength <= X_MAX],
        key=lambda p: -p.epsilon
    )

    ann_count = 0
    for pk in vis_pks[:6]:
        if any(abs(pk.wavelength - w) < 18 for w in annotated_lam):
            continue
        annotated_lam.append(pk.wavelength)

        t = pk.transition_type.lower()
        if "sigma" in t:
            continue
        elif "n" in t and "pi" in t:
            t_label = "n→π*"
            lbl_color = '#1A5276'
        elif "pi" in t:
            t_label = "π→π*"
            lbl_color = '#C0392B'
        else:
            t_label = pk.transition_type
            lbl_color = '#7D6608'

        log_eps_val = math.log10(max(pk.epsilon, 1.0))
        ann_text_ax1 = f"λ={pk.wavelength:.0f} nm\n{t_label}\nε={pk.epsilon:.0f}"
        ann_text_ax2 = f"λ={pk.wavelength:.0f} nm\n{t_label}\nlog ε={log_eps_val:.1f}"

        ax1.axvline(x=pk.wavelength, color=lbl_color, lw=0.9, linestyle='--', alpha=0.7, zorder=4)
        ax2.axvline(x=pk.wavelength, color=lbl_color, lw=0.9, linestyle='--', alpha=0.7, zorder=4)

        y_frac = Y_LEVELS[ann_count % len(Y_LEVELS)]
        y_pos_ax1 = eps_max * y_frac
        y_pos_ax2 = log_max * y_frac

        h_offset = 6 if pk.wavelength < (X_MIN + (X_MAX - X_MIN) * 0.70) else -6
        ha_dir = 'left' if h_offset > 0 else 'right'

        ax1.text(pk.wavelength + h_offset, y_pos_ax1, ann_text_ax1,
                 fontsize=6.5, color=lbl_color, va='top', ha=ha_dir,
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                           edgecolor=lbl_color, alpha=0.92, lw=0.8), zorder=6)
        ax2.text(pk.wavelength + h_offset, y_pos_ax2, ann_text_ax2,
                 fontsize=6.5, color=lbl_color, va='top', ha=ha_dir,
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                           edgecolor=lbl_color, alpha=0.92, lw=0.8), zorder=6)

        ann_count += 1

    ax2.text(698, log_max * 0.03, "* Estimated — not for publication",
             fontsize=6, color='#AAB7B8', style='italic', ha='right')

    # [M691_W_P2_UV_INSET] 우측 그래프(log ε) 500-700nm 빈 공간에 2D 구조 인셋
    # 사용자 요구: "루이스구조를 500~700nm의 그래프 안 노란 빈공간에 표현"
    # RDKit Draw2D 기반 구조 PNG → matplotlib imshow inset
    if smiles:
        try:
            from rdkit import Chem
            from rdkit.Chem import Draw
            mol_inset = Chem.MolFromSmiles(smiles)  # Rule L: MolFromSmiles + None 체크
            if mol_inset is not None:
                from rdkit.Chem.Draw import rdMolDraw2D
                import io as _io
                drawer = rdMolDraw2D.MolDraw2DSVG(120, 90)
                drawer.drawOptions().addAtomIndices = False
                drawer.drawOptions().addBondIndices = False
                drawer.DrawMolecule(mol_inset)
                drawer.FinishDrawing()
                svg_text = drawer.GetDrawingText()
                # SVG → PNG via cairosvg or matplotlib svgpath fallback
                try:
                    import cairosvg as _csv
                    png_bytes = _csv.svg2png(bytestring=svg_text.encode(), output_width=120, output_height=90)
                    import io as _io2
                    from matplotlib.image import imread as _imread
                    import numpy as _np2
                    img_arr = _imread(_io2.BytesIO(png_bytes))
                    # inset axes: 우측 그래프 우측 상단 (x=0.60~0.98, y=0.52~0.98 in axes fraction)
                    ax_inset = ax2.inset_axes([0.60, 0.52, 0.38, 0.45])
                    ax_inset.imshow(img_arr)
                    ax_inset.axis('off')
                    ax_inset.set_facecolor('white')
                    for spine in ax_inset.spines.values():
                        spine.set_edgecolor('#CCCCCC')
                        spine.set_linewidth(0.5)
                    ax_inset.text(0.5, -0.05, "구조식", transform=ax_inset.transAxes,
                                  fontsize=6, ha='center', color='#555555')
                except Exception as _e_cairo:
                    # cairosvg 미설치 시 PNG Draw fallback
                    import logging as _log_inset
                    _log_inset.getLogger(__name__).warning(
                        "[uvvis_inset] cairosvg 미설치, PNG Draw fallback: %s", _e_cairo)
                    try:
                        from rdkit.Chem.Draw import MolToImage
                        pil_img = MolToImage(mol_inset, size=(120, 90))
                        import io as _io3
                        import numpy as _np3
                        from PIL import Image as _PIL
                        buf = _io3.BytesIO()
                        pil_img.save(buf, format='PNG')
                        buf.seek(0)
                        img_arr = __import__('matplotlib.image', fromlist=['imread']).imread(buf)
                        ax_inset = ax2.inset_axes([0.60, 0.52, 0.38, 0.45])
                        ax_inset.imshow(img_arr)
                        ax_inset.axis('off')
                        ax_inset.text(0.5, -0.05, "구조식", transform=ax_inset.transAxes,
                                      fontsize=6, ha='center', color='#555555')
                    except Exception as _e_pil:
                        import logging as _log2
                        _log2.getLogger(__name__).warning(
                            "[uvvis_inset] PIL Draw 실패: %s", _e_pil)  # Rule M: silent failure 금지
        except Exception as _e_inset:
            import logging as _log_top
            _log_top.getLogger(__name__).warning(
                "[uvvis_inset] 구조 인셋 실패 (SMILES=%s): %s", smiles[:40], _e_inset)  # Rule M

    fig.tight_layout(pad=1.5)
    return fig


# ─── Mass Spectrum (EI-MS) ────────────────────────────────────────────

def _compute_ms_fragments(smiles: str):
    """SMILES에서 EI-MS 단편화 예측 (M566 — 학회용 절단선 빨강 + Lewis fragment 표시).

    Returns:
        list of (mz_float, intensity_float, label_str, cleaved_bond_idx_or_None)
        bond_idx는 RDKit mol의 bond index (GetBonds() 기준).
        M⁺, 공통 손실(M-1, M-OH 등)은 bond_idx=None.

    NIST WebBook 참조 — 5종 학회 시연 분자 M+ (사용자 격분 #13 직결):
      • benzene  (c1ccccc1)              M+ =  78  (C6H6)
      • aniline  (Nc1ccccc1)              M+ =  93  (C6H7N)
      • aspirin  (CC(=O)Oc1ccccc1C(=O)O)  M+ = 180  (C9H8O4)
      • caffeine (Cn1cnc2c1c(=O)n(C)c(=O)n2C) M+ = 194  (C8H10N4O2)
      • dopamine (NCCc1ccc(O)c(O)c1)      M+ = 153  (C8H11NO2)
    검증: RDKit Descriptors.ExactMolWt round() — 5/5 NIST 일치 (M566).
    """
    peaks = []
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return peaks

        mw = round(Descriptors.ExactMolWt(mol), 2)
        mw_int = round(mw)

        # M⁺ (분자 이온) — M566: matplotlib mathtext 사용 (Malgun Gothic 글리프 미지원 회피)
        # CLAUDE.md Rule Q-c: ⁺ 글리프 미지원 → mathtext $M^{+}$ 으로 렌더링
        peaks.append((float(mw_int), 100.0, r"$\mathregular{M^{+}}$", None))
        # M-1 (수소 라디칼 손실)
        peaks.append((float(mw_int - 1), 20.0, "M-1", None))

        # 작용기 기반 손실
        n_OH = sum(1 for a in mol.GetAtoms()
                   if a.GetAtomicNum() == 8 and a.GetTotalNumHs() > 0)
        if n_OH > 0:
            peaks.append((float(mw_int - 17), 40.0, "M-OH", None))

        n_CH3 = sum(1 for a in mol.GetAtoms()
                    if a.GetAtomicNum() == 6 and a.GetTotalNumHs() >= 3)
        if n_CH3 > 0:
            # M566: ₃ 아래첨자 → mathtext (Malgun Gothic 글리프 미지원 회피)
            peaks.append((float(mw_int - 15), 30.0, r"$\mathregular{M-CH_{3}}$", None))

        n_CO = sum(1 for b in mol.GetBonds()
                   if b.GetBondTypeAsDouble() >= 2.0 and
                   {b.GetBeginAtom().GetAtomicNum(),
                    b.GetEndAtom().GetAtomicNum()} == {6, 8})
        if n_CO > 0:
            peaks.append((float(mw_int - 28), 25.0, "M-CO", None))

        # m/z=77 (페닐 카티온)
        n_ar = rdMolDescriptors.CalcNumAromaticRings(mol)
        if n_ar > 0 and mw_int > 80:
            # M566: Ph⁺ → mathtext (글리프 회피)
            peaks.append((77.0, 35.0, r"$\mathregular{Ph^{+}}$" + "\n(m/z 77)", None))

        # ── McLafferty Rearrangement (M684 신설) ──────────────────────
        # γ-H 이동 → C=O β-γ 결합 분열. 6원 전이상태(6-membered cyclic TS).
        # SMARTS: C=O를 기준으로 α, β, γ 탄소 + γ-H 존재 확인.
        # McLafferty 이온 m/z = 오른쪽 엔올 fragment 질량.
        # DeepSeek R1 dispatch 권고 SMARTS (M684) — γ-H to carbonyl
        _MCLAFFERTY_SMARTS = Chem.MolFromSmarts("[CX3;$(C(=O))]~[#6]~[#6]~[#6;$([#6][H])]")  # M684 McLafferty 6TS
        if _MCLAFFERTY_SMARTS is not None:
            matches = mol.GetSubstructMatches(_MCLAFFERTY_SMARTS)
            for match in matches:
                # match = (C=O, Cα, Cβ, Cγ)
                # 분열 위치: Cβ-Cγ 사이 (retro 6-TS) — fragment = Cβ=CH₂ enol + aldehyde
                if len(match) < 4:
                    continue
                # Cβ-Cγ 결합 끊기 시뮬레이션
                try:
                    c_beta_idx = match[2]
                    c_gamma_idx = match[3]
                    em_mc = Chem.RWMol(mol)
                    em_mc.RemoveBond(c_beta_idx, c_gamma_idx)
                    frags_mc = Chem.GetMolFrags(em_mc.GetMol(), asMols=True, sanitizeFrags=False)
                    if len(frags_mc) == 2:
                        for frag_mc in frags_mc:
                            fmw_mc = round(Descriptors.ExactMolWt(frag_mc))
                            if 28 <= fmw_mc < mw_int:
                                existing_mc = {round(p[0]) for p in peaks}
                                if fmw_mc not in existing_mc:
                                    peaks.append((float(fmw_mc), 55.0,
                                                  f"McLafferty\nm/z {fmw_mc}", None))  # intensity 55 — 특징적 강한 피크
                                    break  # 첫 번째 fragment만 추가
                except Exception as _emc:
                    _logger.warning("[M684] McLafferty fragment error: %s", _emc)
                break  # 최대 1개 match (분자당 대표 McLafferty 피크)

        # ── 단결합 분열 단편 (α-cleavage, 최대 5개) ─────────────────
        # 비방향족 단결합이면서 고리가 아닌 결합을 끊어 단편 질량 계산
        # α-cleavage 우선순위: 헤테로원자(N,O,S) 인접 C-X 결합 (가장 쉽게 분열)
        frag_count = 0
        # α-cleavage: 헤테로원자 인접 단결합 우선 정렬 (M684 보강)
        _HETERO_ATOMS = {7, 8, 16}  # N, O, S — alpha-cleavage 우선 대상
        def _alpha_priority(bond):
            """헤테로원자 인접 C-X 결합은 우선순위 높음 (0 = highest)."""
            a1, a2 = bond.GetBeginAtom().GetAtomicNum(), bond.GetEndAtom().GetAtomicNum()
            if a1 in _HETERO_ATOMS or a2 in _HETERO_ATOMS:
                return 0  # α-cleavage 우선
            return 1  # 일반 C-C 결합

        sorted_bonds = sorted(
            [b for b in mol.GetBonds()
             if not b.GetIsAromatic()
             and b.GetBondTypeAsDouble() <= 1.0
             and not b.IsInRing()],
            key=_alpha_priority,
        )
        for bond in sorted_bonds:
            if frag_count >= 5:  # 최대 5개 단편 — M566 원본 상한 유지
                break

            idx_b = bond.GetIdx()
            em = Chem.RWMol(mol)
            em.RemoveBond(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
            # 연결 성분 분리
            frags = Chem.GetMolFrags(em.GetMol(), asMols=True, sanitizeFrags=False)
            if len(frags) != 2:
                continue
            for frag in frags:
                try:
                    fmw = round(Descriptors.ExactMolWt(frag))
                    if 28 <= fmw < mw_int:
                        # 같은 m/z가 이미 있으면 skip
                        existing = {round(p[0]) for p in peaks}
                        if fmw not in existing:
                            # α-cleavage (헤테로인접) vs 일반 단편 강도 구분
                            a1n = bond.GetBeginAtom().GetAtomicNum()
                            a2n = bond.GetEndAtom().GetAtomicNum()
                            intensity = 45.0 if (a1n in _HETERO_ATOMS or a2n in _HETERO_ATOMS) else 22.0
                            peaks.append((float(fmw), intensity, f"m/z {fmw}", idx_b))
                            frag_count += 1
                except Exception as _ef:
                    _logger.warning("[PopupPredictedSpectrum] MS fragment bond cleavage failed: %s", _ef)

    except Exception as _e:
        _logger.warning("_compute_ms_fragments failed: %s", _e)

    # 내림차순 intensity 정렬
    peaks.sort(key=lambda p: -p[1])
    return peaks


def _make_ms_figure(smiles: str) -> "Figure":
    """EI-Mass Spectrum Figure (M566 — 학회용 EI-MS Lewis 절단선 빨강).

    Layout: [2D molecule + bond cleavage markers | MS bar spectrum]
    - 왼쪽: RDKit 2D 구조 + 단편화 결합에 빨강 점선 (수직, 사용자 격분 #13 직결)
            + Lewis 구조에 fragment ion m/z 텍스트 라벨 (학생 학회용)
    - 오른쪽: m/z 막대 그래프, 주요 피크 레이블 (NIST 데이터베이스 대조)

    사용자 격분 #13 (2026-03-20): "MS도 H-NMR이나 C-NMR처럼 루이스구조 그려놓고
    끊어지는 결합 부분에 빨간 수직방향 절단선으로 표시해주는게 필요해"
    """
    import numpy as np
    from matplotlib.gridspec import GridSpec

    peaks = _compute_ms_fragments(smiles)

    # 단편화 결합 인덱스 수집
    cleaved_bond_indices = {p[3] for p in peaks if p[3] is not None}

    fig = Figure(figsize=(9.0, 4.5), facecolor='white')
    gs = GridSpec(1, 2, figure=fig, width_ratios=[1, 2.8],
                  left=0.04, right=0.98, bottom=0.12, top=0.92, wspace=0.10)
    ax_mol = fig.add_subplot(gs[0])
    ax     = fig.add_subplot(gs[1])

    # ── 왼쪽: 분자 구조 + 결합 분열선 ──────────────────────────────
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from rdkit.Chem.Draw import rdMolDraw2D
        from io import BytesIO
        import PIL.Image as _PIL
        import numpy as _np2

        mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is not None:
            AllChem.Compute2DCoords(mol)

            # 단편화 결합 강조 색상 (M566: 회색→빨강, 사용자 격분 #13 직결)
            # #E74C3C RGB = (0.91, 0.30, 0.24) — 학생 학회 시연용 명확한 빨강
            highlight_bonds = list(cleaved_bond_indices)
            highlight_bond_colors = {bi: (0.91, 0.30, 0.24) for bi in highlight_bonds}

            drawer = rdMolDraw2D.MolDraw2DCairo(280, 210)
            opts = drawer.drawOptions()
            opts.padding = 0.12
            opts.addAtomIndices = False
            opts.addStereoAnnotation = False

            if highlight_bonds:
                drawer.DrawMolecule(
                    mol,
                    highlightAtoms=[],
                    highlightAtomColors={},
                    highlightBonds=highlight_bonds,
                    highlightBondColors=highlight_bond_colors,
                )
            else:
                drawer.DrawMolecule(mol)
            drawer.FinishDrawing()

            img = _PIL.open(BytesIO(drawer.GetDrawingText()))
            ax_mol.imshow(_np2.array(img))
            ax_mol.axis('off')

            # ── 결합 분열 위치에 수직 점선 오버레이 (M566: 회색→빨강) ────
            # 사용자 격분 #13 (2026-03-20): "빨간 수직방향 절단선으로 표시"
            # rdMolDraw2D 좌표를 픽셀로 변환하여 점선 + m/z 라벨 추가
            if cleaved_bond_indices:
                img_w, img_h = img.size  # (280, 210) in pixels
                conf = mol.GetConformer()
                xs = [conf.GetAtomPosition(i).x for i in range(mol.GetNumAtoms())]
                ys = [conf.GetAtomPosition(i).y for i in range(mol.GetNumAtoms())]
                x_min, x_max = min(xs), max(xs)
                y_min, y_max = min(ys), max(ys)
                # RDKit 좌표 → 이미지 픽셀 (with padding factor)
                pad = opts.padding  # 0.12
                x_range = (x_max - x_min) if x_max != x_min else 1.0
                y_range = (y_max - y_min) if y_max != y_min else 1.0
                scale = min(
                    img_w * (1 - 2 * pad) / x_range,
                    img_h * (1 - 2 * pad) / y_range
                )
                cx = img_w / 2 - scale * (x_min + x_max) / 2
                cy = img_h / 2 + scale * (y_min + y_max) / 2  # y-flip

                # bond_idx → m/z label 매핑 (peaks list에서 추출)
                # peaks: (mz, intens, label, bond_idx) — bond_idx 기준 라벨 lookup
                bond_to_mz = {p[3]: p[0] for p in peaks if p[3] is not None}

                for bi in cleaved_bond_indices:
                    bond = mol.GetBondWithIdx(bi)
                    ai = bond.GetBeginAtomIdx()
                    aj = bond.GetEndAtomIdx()
                    xi = conf.GetAtomPosition(ai).x * scale + cx
                    yi = img_h - (conf.GetAtomPosition(ai).y * scale + (img_h / 2 - scale * (y_min + y_max) / 2))
                    xj = conf.GetAtomPosition(aj).x * scale + cx
                    yj = img_h - (conf.GetAtomPosition(aj).y * scale + (img_h / 2 - scale * (y_min + y_max) / 2))
                    # 결합 중점
                    mx_px = (xi + xj) / 2
                    my_px = (yi + yj) / 2
                    # 결합 방향 벡터 → 수직 벡터
                    dx, dy = xj - xi, yj - yi
                    bond_len = max((dx**2 + dy**2) ** 0.5, 1e-6)
                    # 수직 단위 벡터 (픽셀 좌표는 y 아래 방향)
                    nx, ny = -dy / bond_len, dx / bond_len
                    cleavage_half = 18.0  # 점선 반길이 (픽셀, M566: 14→18 학회 가시성)
                    # 빨강 절단선 (M566 사용자 격분 #13 직결)
                    ax_mol.plot(
                        [mx_px - nx * cleavage_half, mx_px + nx * cleavage_half],
                        [my_px - ny * cleavage_half, my_px + ny * cleavage_half],
                        color='#E74C3C', linewidth=2.5,  # M566: 회색→빨강 + 1.5→2.5 두께
                        linestyle=(0, (4, 3)),  # 점선
                        transform=ax_mol.transData,
                        zorder=10, solid_capstyle='round',
                    )

                    # Lewis 구조에 fragment ion m/z 텍스트 라벨 (M566 신설)
                    # 절단선 끝에 m/z 표시 — 학생이 어떤 fragment인지 직관적 인식
                    mz_val = bond_to_mz.get(bi)
                    if mz_val is not None:
                        # 라벨 위치: 수직선 끝 + 약간 오프셋 (10px 외곽)
                        # M566 매직넘버 주석: 18+8=26px 외곽 (라벨 가독성)
                        label_offset = cleavage_half + 8.0
                        lx = mx_px + nx * label_offset
                        ly = my_px + ny * label_offset
                        ax_mol.text(
                            lx, ly, f"m/z {int(mz_val)}",
                            fontsize=6.5, color='#C0392B',  # 진빨강 (절단선과 톤 일치)
                            fontweight='bold',
                            ha='center', va='center',
                            transform=ax_mol.transData,
                            zorder=11,
                            bbox=dict(boxstyle='round,pad=0.18',
                                      facecolor='#FFF5F5',  # 연한 핑크 배경
                                      edgecolor='#E74C3C', linewidth=0.6, alpha=0.95),
                        )
        else:
            # fallback
            ax_mol.text(0.5, 0.55, "구조식", ha='center', va='center',
                        fontsize=10, color='#7F8C8D', transform=ax_mol.transAxes)
            ax_mol.text(0.5, 0.38, (smiles or "")[:28],
                        ha='center', va='center', fontsize=6.5, color='#95A5A6',
                        transform=ax_mol.transAxes, style='italic')
    except Exception as _e:
        _logger.warning("MS mol drawing failed: %s", _e)
        ax_mol.text(0.5, 0.5, "구조식 표시 오류", ha='center', va='center',
                    fontsize=9, color='#7F8C8D', transform=ax_mol.transAxes)

    # M566: 사용자 격분 #13 — 빨강 절단선 표시 의무 (한국어+영어 병기 Rule Q)
    ax_mol.set_title("Lewis 구조 + 절단선 (Bond Cleavage, 빨강 점선)",
                     fontsize=8, color='#2C3E50', pad=4)

    # ── 오른쪽: MS 막대 스펙트럼 ──────────────────────────────────
    ax.set_facecolor('white')

    if not peaks:
        ax.text(0.5, 0.5, "No MS peaks — check SMILES",
                ha='center', va='center', fontsize=10,
                color='gray', transform=ax.transAxes)
    else:
        mz_vals = np.array([p[0] for p in peaks])
        intensities = np.array([p[1] for p in peaks])
        labels = [p[2] for p in peaks]
        bond_idxs = [p[3] for p in peaks]

        # 색상 (M566): 결합 분열 단편 = 빨강 (Lewis 절단선과 일치),
        #              분자이온(M⁺) + 공통 손실(M-1/M-OH/M-CH₃/M-CO) = 보라
        # 학생이 Lewis ↔ MS 막대 매칭 시각적 인식 가능
        colors = []
        for bi in bond_idxs:
            if bi is None:
                colors.append('#7E57C2')  # M⁺/공통 손실 (보라)
            else:
                colors.append('#E74C3C')  # M566: 단편화 결합 유래 = 빨강 (Lewis 절단선 일치)

        # 막대 그래프
        # [M682 item21] MS 막대 너비 0.012→0.006 (사용자: "막대그래프 두께 너무 두껍다")
        mw_max = int(mz_vals.max()) if len(mz_vals) > 0 else 100
        ax.bar(mz_vals, intensities, width=max(mw_max * 0.006, 0.5),  # [MAGIC: 0.006] M682 절반
               color=colors, alpha=0.85, zorder=3)

        # 베이스라인
        ax.axhline(y=0, color='#555', lw=0.8, zorder=2)

        # 피크 레이블
        y_max_all = intensities.max()
        for mz_v, intens, lbl in zip(mz_vals, intensities, labels):
            if intens >= y_max_all * 0.15:
                # [M682 item21] MS 레이블 폰트 6.5→9.0pt (사용자: "위 글자 너무 작다")
                ax.text(mz_v, intens + y_max_all * 0.03,
                        lbl.replace('\n', '\n'),
                        fontsize=9.0, ha='center', va='bottom',
                        color='#4A148C', fontweight='bold',
                        rotation=70, zorder=5)

        ax.set_xlim(max(0, mz_vals.min() - mw_max * 0.08),
                    mw_max + mw_max * 0.12)
        ax.set_ylim(-5, y_max_all * 1.35)

    ax.set_xlabel("m/z", fontsize=9, color='#2C3E50')
    ax.set_ylabel("Relative Intensity (%)", fontsize=9, color='#2C3E50')
    ax.set_title("Mass Spectrum (EI-MS, 이론적 스펙트럼, 엔진 기반)", fontsize=10,  # CLAUDE.md E-a M486
                 fontweight='bold', color='#2C3E50', pad=6)
    ax.grid(True, alpha=0.15, color='#AAB7B8', axis='y')
    ax.tick_params(colors='#2C3E50', labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor('#BDC3C7')

    # M566: NIST WebBook 대조 안내 (학생 학회용 학술 표기)
    # mathtext + Malgun Gothic 회피 (Rule Q-c) — ⁺ 글리프 미지원
    ax.text(0.98, -0.16,
            r"* $\mathregular{M^{+}}$ NIST WebBook 대조 (benzene 78 / aniline 93 / aspirin 180 / "
            "caffeine 194 / dopamine 153) — 단편 이온은 RDKit α-cleavage 추정값",
            fontsize=5.5, color='#7F8C8D', style='italic',
            ha='right', va='top', transform=ax.transAxes)

    fig.tight_layout(pad=1.0)
    return fig


# ─── 분자 안정성 분석 (Stability — Block7 M684) ───────────────────
# DeepSeek R1 dispatch 권고 기반 (M684):
# 1. 열역학 안정성: BDE 경험칙 + 불안정 서브구조 SMARTS
# 2. 광안정성: 공액계 → λmax 추정 → UVA/UVB 범위 비교
# 3. 3등급 판정: stable / moderate / labile

def _compute_stability(smiles: str) -> dict:
    """분자 안정성 판정 (M684 Block7 신설).

    Returns dict:
        {
          "thermal": {"grade": str, "reason": str, "alerts": list},
          "photo":   {"grade": str, "reason": str, "lambda_max": float or None},
          "overall": str,    # "stable" / "moderate" / "labile"
          "score":   float,  # 0.0 ~ 1.0 (높을수록 안정)
        }

    열역학 안정성 경험칙 (DeepSeek R1 권고):
      - 과산화물 [O-O]: BDE ~38 kcal/mol → labile
      - 니트로기 [N+](=O)[O-]: 열분해 위험
      - 아조 [N=N]: BDE ~40-60 kcal/mol (일부 → labile)
      - 스트레인 소환 [C]1CC1 (cyclopropane): 링 스트레인 ~27 kcal/mol

    광안정성 경험칙:
      - 공액 이중결합 수 (n) → λmax 추정 (Woodward-Fieser 근사)
      - λmax > 320 nm → UVA 흡수 → photo-labile 가능성
    """
    result = {
        "thermal": {"grade": "stable", "reason": "불안정 서브구조 없음", "alerts": []},
        "photo":   {"grade": "stable", "reason": "UV 흡수 없음", "lambda_max": None},
        "overall": "stable",
        "score": 1.0,
    }
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            _logger.warning("[M684 Block7] _compute_stability: mol is None for smiles=%r", smiles)
            return result

        # ── 1. 열역학 안정성 SMARTS 스캔 ─────────────────────────
        # (Rule I 매직넘버 주석: BDE 근거 및 출처)
        _UNSTABLE_SMARTS = [
            ("[OX2][OX2]",  "labile",   "과산화물 O-O: BDE ~38 kcal/mol (매우 불안정)"),
            ("[NX2]=[NX2]", "labile",   "아조기 N=N: 열분해 위험 (BDE ~40 kcal/mol)"),
            ("[N+](=O)[O-]","moderate", "니트로기: 고온/충격 분해 가능 (TNT 등)"),
            ("[CX3](=O)[OX2][OX2]", "labile", "퍼옥시에스터: 매우 불안정, BDE ~25 kcal/mol"),
            ("[CX2]#[NX1]", "moderate", "시아나이드(-C≡N): 고독성, 열 분해 가능"),
            ("C1CC1",       "moderate", "시클로프로판: 링 스트레인 ~27 kcal/mol"),
            ("[SX2][SX2]",  "moderate", "다이설파이드 S-S: 산화환원 활성"),
        ]
        thermal_grade = "stable"
        thermal_reasons = []
        for smt_str, grade, reason in _UNSTABLE_SMARTS:
            smt = Chem.MolFromSmarts(smt_str)
            if smt is not None and mol.HasSubstructMatch(smt):
                thermal_reasons.append(reason)
                if grade == "labile":
                    thermal_grade = "labile"
                elif grade == "moderate" and thermal_grade == "stable":
                    thermal_grade = "moderate"

        result["thermal"]["grade"] = thermal_grade
        result["thermal"]["alerts"] = thermal_reasons
        if thermal_reasons:
            result["thermal"]["reason"] = "; ".join(thermal_reasons)
        else:
            result["thermal"]["reason"] = "불안정 서브구조 없음 — 일반 조건 안정"

        # ── 2. 광안정성: 공액계 λmax 추정 ─────────────────────────
        # Woodward-Fieser 변형: λmax ≈ 217 + 30*(n_conj-1) nm (단순 선형)
        # n_conj = 공액 이중결합 수
        n_conj = 0
        _CONJ_BOND_SMARTS = Chem.MolFromSmarts("[#6]=[#6]-[#6]=[#6]")  # 공액 1,3-다이엔 단위
        if _CONJ_BOND_SMARTS is not None:
            matches_conj = mol.GetSubstructMatches(_CONJ_BOND_SMARTS)
            n_conj = len(matches_conj)

        n_aromatic = rdMolDescriptors.CalcNumAromaticRings(mol)

        # 방향족 고리 수 기반 λmax 보정 (폴리아센 연장)
        if n_aromatic >= 3:   # 안트라센류: λmax ~380 nm
            lambda_est = 380.0 + (n_aromatic - 3) * 40.0   # 경험칙: 추가 고리당 +40nm
        elif n_aromatic == 2:  # 나프탈렌: λmax ~320 nm
            lambda_est = 320.0
        elif n_aromatic == 1:  # 벤젠: λmax ~254 nm (B band)
            lambda_est = 254.0 + n_conj * 15.0
        elif n_conj > 0:       # 비방향족 공액계
            lambda_est = 217.0 + 30.0 * n_conj  # Woodward-Fieser 기본 (diene)
        else:
            lambda_est = None  # UV 흡수 없음

        result["photo"]["lambda_max"] = lambda_est

        if lambda_est is None:
            result["photo"]["grade"] = "stable"
            result["photo"]["reason"] = "공액계 없음 — UV 흡수 없음"
        elif lambda_est >= 400.0:  # 가시광선 흡수 → 가장 민감
            result["photo"]["grade"] = "labile"
            result["photo"]["reason"] = (
                f"가시광선 흡수 (λmax≈{lambda_est:.0f}nm) — 광분해 위험성 높음 "
                "(폴리방향족/공액 색소 등)"
            )
        elif lambda_est >= 320.0:  # UVA 흡수
            result["photo"]["grade"] = "moderate"
            result["photo"]["reason"] = (
                f"UVA 흡수 (λmax≈{lambda_est:.0f}nm, 320-400nm) — "
                "광안정화제 권고"
            )
        elif lambda_est >= 280.0:  # UVB 흡수
            result["photo"]["grade"] = "moderate"
            result["photo"]["reason"] = (
                f"UVB 흡수 (λmax≈{lambda_est:.0f}nm, 280-320nm) — "
                "직사광선 차단 권고"
            )
        else:
            result["photo"]["grade"] = "stable"
            result["photo"]["reason"] = (
                f"UVC 이하만 흡수 (λmax≈{lambda_est:.0f}nm, <280nm) — "
                "일반 환경 광안정"
            )

        # ── 3. 종합 판정 & score ─────────────────────────────────
        _GRADE_MAP = {"stable": 0, "moderate": 1, "labile": 2}
        _max_grade = max(
            _GRADE_MAP[result["thermal"]["grade"]],
            _GRADE_MAP[result["photo"]["grade"]],
        )
        _GRADE_STR = {0: "stable", 1: "moderate", 2: "labile"}
        result["overall"] = _GRADE_STR[_max_grade]
        result["score"] = 1.0 - _max_grade * 0.4   # stable=1.0, moderate=0.6, labile=0.2

    except Exception as _es:
        _logger.warning("[M684 Block7] _compute_stability failed: %s", _es)

    return result


def _make_stability_figure(smiles: str) -> "Figure":
    """분자 안정성 요약 Figure (Block7 M684).

    Layout:
    - 왼쪽: 2D 구조 (불안정 서브구조 빨강 강조)
    - 오른쪽: 안정성 등급 게이지 + 열역학/광안정성 텍스트 요약
    """
    import numpy as np

    stab = _compute_stability(smiles)
    if not isinstance(stab, dict):
        _logger.warning("_make_stability_figure: _compute_stability returned %s, expected dict", type(stab).__name__)
        stab = {"overall": "stable", "score": 1.0, "thermal": {}, "photo": {}}

    fig = Figure(figsize=(9.0, 4.0), facecolor='white')
    gs = __import__('matplotlib').gridspec.GridSpec(
        1, 2, figure=fig, width_ratios=[1, 2],
        left=0.04, right=0.98, bottom=0.08, top=0.92, wspace=0.12,
    )
    ax_mol = fig.add_subplot(gs[0])
    ax_info = fig.add_subplot(gs[1])

    # ── 왼쪽: 분자 구조 (불안정 서브구조 빨강 강조) ──────────────
    _drawn = False
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from rdkit.Chem.Draw import rdMolDraw2D
        from io import BytesIO
        import PIL.Image as _PIL

        mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is not None:
            AllChem.Compute2DCoords(mol)

            # 불안정 서브구조 원자 강조 (빨강)
            hi_atoms: list = []
            _UNSTABLE_SMARTS_DRAW = [
                "[OX2][OX2]", "[NX2]=[NX2]", "[N+](=O)[O-]",
                "[CX3](=O)[OX2][OX2]", "C1CC1", "[SX2][SX2]",
            ]
            for smt_str in _UNSTABLE_SMARTS_DRAW:
                smt = Chem.MolFromSmarts(smt_str)
                if smt is not None:
                    for match in mol.GetSubstructMatches(smt):
                        hi_atoms.extend(list(match))
            hi_atoms = list(set(hi_atoms))
            hi_colors = {a: (0.91, 0.30, 0.24) for a in hi_atoms}   # 빨강

            drawer = rdMolDraw2D.MolDraw2DCairo(280, 210)
            drawer.drawOptions().padding = 0.12
            if hi_atoms:
                drawer.DrawMolecule(
                    mol,
                    highlightAtoms=hi_atoms,
                    highlightAtomColors=hi_colors,
                    highlightBonds=[],
                    highlightBondColors={},
                )
            else:
                drawer.DrawMolecule(mol)
            drawer.FinishDrawing()

            img_bytes = BytesIO(drawer.GetDrawingText())
            pil_img = _PIL.open(img_bytes)
            ax_mol.imshow(pil_img)
            _drawn = True
    except Exception as _edraw:
        _logger.warning("[M684 Block7] stability mol draw failed: %s", _edraw)

    if not _drawn:
        ax_mol.text(0.5, 0.5, "구조\n표시 불가", ha='center', va='center', fontsize=10)
    ax_mol.axis('off')
    ax_mol.set_title("분자 구조\n(불안정 서브구조 빨강)", fontsize=8)

    # ── 오른쪽: 안정성 등급 게이지 + 요약 텍스트 ─────────────────
    ax_info.axis('off')

    _OVERALL = stab.get("overall", "stable")
    _SCORE   = stab.get("score", 1.0)
    _COLORS  = {"stable": "#27AE60", "moderate": "#F39C12", "labile": "#E74C3C"}
    _LABELS  = {"stable": "안정 (Stable)", "moderate": "보통 (Moderate)", "labile": "불안정 (Labile)"}
    _col     = _COLORS.get(_OVERALL, "#7F8C8D")
    _lbl     = _LABELS.get(_OVERALL, _OVERALL)

    # 게이지 바 (수평 색상 바)
    bar_y = 0.82
    ax_info.barh([bar_y], [_SCORE], height=0.12, color=_col, alpha=0.85, left=0.0)
    ax_info.barh([bar_y], [1.0 - _SCORE], height=0.12, color='#ECF0F1', alpha=0.85, left=_SCORE)
    ax_info.text(0.5, bar_y + 0.10, f"종합 안정성: {_lbl}  (score={_SCORE:.1f})",
                 ha='center', va='bottom', fontsize=11, fontweight='bold', color=_col)

    # 열역학 안정성
    th = stab.get("thermal", {})
    _th_col = _COLORS.get(th.get("grade", "stable"), "#27AE60")
    ax_info.text(0.02, 0.65, f"열역학 안정성: {th.get('grade','?').upper()}",
                 fontsize=9, color=_th_col, fontweight='bold')
    ax_info.text(0.02, 0.55, th.get("reason", ""), fontsize=8, color='#2C3E50',
                 wrap=True)

    # 광안정성
    ph = stab.get("photo", {})
    _ph_col = _COLORS.get(ph.get("grade", "stable"), "#27AE60")
    ax_info.text(0.02, 0.40, f"광안정성 (UV): {ph.get('grade','?').upper()}",
                 fontsize=9, color=_ph_col, fontweight='bold')
    lm = ph.get("lambda_max")
    lm_str = f"λmax ≈ {lm:.0f} nm" if lm else "UV 흡수 없음"
    ax_info.text(0.02, 0.30, f"{lm_str}  —  {ph.get('reason', '')}", fontsize=8, color='#2C3E50')

    # 학술 기준 안내
    ax_info.text(0.02, 0.10,
                 "* 열역학 안정성: SMARTS 기반 BDE 경험칙 (Blanksby & Ellison, Acc. Chem. Res. 2003)\n"
                 "  광안정성: Woodward-Fieser 근사 λmax 추정 (SIMULATION_MODE — 이론적 스펙트럼)",
                 fontsize=6.5, color='#7F8C8D', style='italic')

    ax_info.set_xlim(0, 1)
    ax_info.set_ylim(0, 1)

    fig.suptitle("분자 안정성 분석 (Molecular Stability — Block7 M684)",
                 fontsize=10, y=0.97)
    fig.tight_layout(pad=0.8, rect=[0, 0, 1, 0.96])
    return fig


# ─── 실험 데이터 비교 오버레이 Figure 생성 ──────────────────────────

def _make_ir_comparison_figure(
    theo_peaks: List,
    exp: "ExperimentalSpectrum",
    comparison: "SpectrumComparison",
) -> "Figure":
    """
    IR comparison overlay figure: theoretical (red) + experimental (blue).
    Matched peaks shown with green markers and delta labels.
    Publication-ready styling.
    """
    import numpy as np

    fig = Figure(figsize=(10.0, 5.5), facecolor='white')
    ax = fig.add_subplot(111)

    # --- Theoretical spectrum (red) ---
    x_theo = np.linspace(400, 4000, 3000)
    y_theo = np.full_like(x_theo, 100.0)

    for pk in theo_peaks:
        if "fingerprint" in pk.assignment:
            continue
        sigma = max(pk.width / 2.355, 5.0)
        depth = 100.0 - pk.transmittance
        gauss = depth * np.exp(-0.5 * ((x_theo - pk.wavenumber) / sigma) ** 2)
        y_theo -= gauss

    y_theo = np.clip(y_theo, 0, 100)
    ax.plot(x_theo, y_theo, color='#C0392B', lw=1.4, alpha=0.85,
            label='Theoretical (predicted)', zorder=3)
    ax.fill_between(x_theo, y_theo, 100, alpha=0.06, color='#E74C3C', zorder=1)

    # --- Experimental spectrum (blue) ---
    x_exp = np.array(exp.x_data)
    y_exp = np.array(exp.y_data)

    # Sort by x for clean line plotting
    sort_idx = np.argsort(x_exp)
    x_exp = x_exp[sort_idx]
    y_exp = y_exp[sort_idx]

    # Normalize experimental to same y scale if needed
    if exp.y_unit == "Abs":
        # Convert absorbance to transmittance: T = 10^(-A) * 100
        y_exp = np.power(10.0, -np.clip(y_exp, 0, 4)) * 100.0
    elif exp.y_unit == "a.u.":
        # Normalize arbitrary units to 0-100 range
        y_min, y_max = y_exp.min(), y_exp.max()
        if y_max > y_min:
            y_exp = (1.0 - (y_exp - y_min) / (y_max - y_min)) * 100.0

    ax.plot(x_exp, y_exp, color='#2471A3', lw=1.2, alpha=0.85,
            label='Experimental', zorder=4)
    ax.fill_between(x_exp, y_exp, 100, alpha=0.06, color='#3498DB', zorder=1)

    # --- Matched peak markers (green) ---
    for match in comparison.peak_matches:
        # Green diamond at experimental peak position
        ax.plot(match.exp_position, match.exp_intensity, 'D',
                color='#27AE60', markersize=6, zorder=6, alpha=0.9)
        # Delta label
        delta_str = f"{match.delta:+.0f}"
        label_y = min(match.exp_intensity, match.theo_intensity) - 8
        label_y = max(label_y, 5)
        # [M816 FIX] cm\u207b\u00b9 unicode escape \u2192 mathtext (Malgun Gothic \uae00\ub9ac\ud504 \ubbf8\uc9c0\uc6d0 \ud68c\ud53c)
        ax.annotate(
            f"{delta_str} cm$^{{-1}}$",
            xy=(match.exp_position, match.exp_intensity),
            xytext=(match.exp_position, label_y),
            fontsize=5.5, ha='center', color='#1E8449', fontweight='bold',
            arrowprops=dict(arrowstyle='-', color='#27AE60', lw=0.5, alpha=0.5),
            bbox=dict(boxstyle='round,pad=0.2', facecolor='#EAFAF1',
                      edgecolor='#27AE60', alpha=0.85, lw=0.6),
            zorder=7,
        )

    # --- Unmatched experimental peaks (orange X) ---
    for pos in comparison.unmatched_exp[:5]:
        # Find y value at this position
        idx = np.argmin(np.abs(x_exp - pos))
        y_at = y_exp[idx] if idx < len(y_exp) else 50.0
        ax.plot(pos, y_at, 'x', color='#E67E22', markersize=7, mew=2, zorder=6)

    # --- Score box ---
    # [M816 FIX] cm\u207b\u00b9 unicode escape \u2192 mathtext (Malgun Gothic \uae00\ub9ac\ud504 \ubbf8\uc9c0\uc6d0 \ud68c\ud53c)
    score_text = (
        f"Match Score: {comparison.overall_score:.1f}%\n"
        f"Peaks Matched: {len(comparison.peak_matches)}/{len(comparison.peak_matches) + len(comparison.unmatched_exp)}\n"
        f"Cosine Sim: {comparison.cosine_similarity:.3f}\n"
        f"Peak RMSD: {comparison.peak_rmsd:.1f} cm$^{{-1}}$"
    )
    ax.text(
        0.02, 0.02, score_text, transform=ax.transAxes,
        fontsize=7.5, va='bottom', ha='left',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                  edgecolor='#2C3E50', alpha=0.92, lw=1.0),
        fontfamily='monospace', zorder=8,
    )

    # Fingerprint region shading
    ax.axvspan(400, 1500, alpha=0.06, color='#E8A0A0', zorder=0)

    ax.set_xlim(4000, 400)
    ax.set_ylim(-5, 108)
    # [M816 FIX] cm\u207b\u00b9 unicode escape \u2192 mathtext
    ax.set_xlabel(r"Wavenumber (cm$^{-1}$)", fontsize=9)
    ax.set_ylabel("Transmittance (%)", fontsize=9)
    ax.set_title("IR Spectrum: Theoretical vs Experimental", fontsize=10,
                 fontweight='bold', pad=8)
    ax.legend(loc='upper right', fontsize=7.5, framealpha=0.9)
    ax.grid(True, alpha=0.12, color='#AAB7B8')
    fig.tight_layout(pad=1.5)
    return fig


def _make_uvvis_comparison_figure(
    theo_peaks: List,
    exp: "ExperimentalSpectrum",
    comparison: "SpectrumComparison",
) -> "Figure":
    """UV-Vis comparison overlay: theoretical (red) + experimental (blue)."""
    import numpy as np

    fig = Figure(figsize=(10.0, 5.0), facecolor='white')
    ax = fig.add_subplot(111)

    X_MIN, X_MAX = 200, 700
    x_arr = np.linspace(150, 750, 3000)

    # --- Theoretical (red) ---
    y_theo = np.zeros_like(x_arr)
    for pk in theo_peaks:
        sigma = 22.0
        gauss = pk.epsilon * np.exp(-0.5 * ((x_arr - pk.wavelength) / sigma) ** 2)
        y_theo += gauss

    ax.plot(x_arr, y_theo, color='#C0392B', lw=1.4, alpha=0.85,
            label='Theoretical', zorder=3)
    ax.fill_between(x_arr, y_theo, alpha=0.08, color='#E74C3C', zorder=1)

    # --- Experimental (blue) ---
    x_exp = np.array(exp.x_data)
    y_exp = np.array(exp.y_data)
    sort_idx = np.argsort(x_exp)
    x_exp = x_exp[sort_idx]
    y_exp = y_exp[sort_idx]

    # Scale experimental to match theoretical range
    theo_max = max(y_theo.max(), 1.0)
    exp_max = max(y_exp.max(), 1.0)
    y_exp_scaled = y_exp * (theo_max / exp_max)

    ax.plot(x_exp, y_exp_scaled, color='#2471A3', lw=1.2, alpha=0.85,
            label='Experimental', zorder=4)
    ax.fill_between(x_exp, y_exp_scaled, alpha=0.06, color='#3498DB', zorder=1)

    # --- Matched peaks ---
    for match in comparison.peak_matches:
        ax.axvline(x=match.exp_position, color='#27AE60', lw=0.8,
                   linestyle='--', alpha=0.5, zorder=5)
        y_pos = theo_max * 0.85
        ax.text(match.exp_position + 3, y_pos,
                f"{match.delta:+.0f} nm",
                fontsize=6, color='#1E8449', fontweight='bold', zorder=6)

    # Visible region
    ax.axvspan(400, 700, alpha=0.05, color='gold', zorder=0)

    # Score box
    score_text = (
        f"Match: {comparison.overall_score:.1f}%  |  "
        f"Cosine: {comparison.cosine_similarity:.3f}  |  "
        f"RMSD: {comparison.peak_rmsd:.1f} nm"
    )
    ax.text(0.5, 1.02, score_text, transform=ax.transAxes,
            fontsize=8, ha='center', va='bottom',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#EAFAF1',
                      edgecolor='#27AE60', alpha=0.9, lw=0.8),
            zorder=8)

    ax.set_xlim(X_MIN, X_MAX)
    ax.set_ylim(0, theo_max * 1.25)
    ax.set_xlabel("Wavelength (nm)", fontsize=9)
    ax.set_ylabel("Intensity (scaled)", fontsize=9)
    ax.set_title("UV-Vis Spectrum: Theoretical vs Experimental",
                 fontsize=10, fontweight='bold', pad=12)
    ax.legend(loc='upper right', fontsize=7.5, framealpha=0.9)
    ax.grid(True, alpha=0.12)
    fig.tight_layout(pad=1.5)
    return fig


def _make_raman_comparison_figure(
    theo_peaks: List,
    exp: "ExperimentalSpectrum",
    comparison: "SpectrumComparison",
) -> "Figure":
    """Raman comparison overlay: theoretical (crimson) + experimental (blue)."""
    import numpy as np

    fig = Figure(figsize=(10.0, 5.0), facecolor='white')
    ax = fig.add_subplot(111)

    x_arr = np.linspace(0, 4000, 3000)

    # --- Theoretical (crimson) ---
    y_theo = np.zeros_like(x_arr)
    for pk in theo_peaks:
        sigma = max(pk.width / 2.355, 5.0)
        gauss = pk.intensity * np.exp(-0.5 * ((x_arr - pk.shift) / sigma) ** 2)
        y_theo += gauss

    ax.plot(x_arr, y_theo, color='#922B21', lw=1.4, alpha=0.85,
            label='Theoretical', zorder=3)
    ax.fill_between(x_arr, y_theo, alpha=0.08, color='#C0392B', zorder=1)

    # --- Experimental (blue) ---
    x_exp = np.array(exp.x_data)
    y_exp = np.array(exp.y_data)
    sort_idx = np.argsort(x_exp)
    x_exp = x_exp[sort_idx]
    y_exp = y_exp[sort_idx]

    theo_max = max(y_theo.max(), 0.1)
    exp_max = max(y_exp.max(), 0.1)
    y_exp_scaled = y_exp * (theo_max / exp_max)

    ax.plot(x_exp, y_exp_scaled, color='#2471A3', lw=1.2, alpha=0.85,
            label='Experimental', zorder=4)

    # Matched peaks
    for match in comparison.peak_matches:
        ax.plot(match.exp_position, match.exp_intensity * (theo_max / exp_max),
                'D', color='#27AE60', markersize=5, zorder=6)

    # [M816 FIX] cm\u207b\u00b9 unicode escape \u2192 mathtext (Malgun Gothic \uae00\ub9ac\ud504 \ubbf8\uc9c0\uc6d0 \ud68c\ud53c)
    score_text = (
        f"Match: {comparison.overall_score:.1f}%  |  "
        f"Cosine: {comparison.cosine_similarity:.3f}  |  "
        f"RMSD: {comparison.peak_rmsd:.1f} cm$^{{-1}}$"
    )
    ax.text(0.5, 1.02, score_text, transform=ax.transAxes,
            fontsize=8, ha='center', va='bottom',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#EAFAF1',
                      edgecolor='#27AE60', alpha=0.9, lw=0.8),
            zorder=8)

    ax.set_xlim(0, 4000)
    ax.set_ylim(0, theo_max * 1.3)
    # [M816 FIX] cm\u207b\u00b9 unicode escape \u2192 mathtext
    ax.set_xlabel(r"Raman Shift (cm$^{-1}$)", fontsize=9)
    ax.set_ylabel("Intensity (scaled)", fontsize=9)
    ax.set_title("Raman Spectrum: Theoretical vs Experimental",
                 fontsize=10, fontweight='bold', pad=12)
    ax.legend(loc='upper right', fontsize=7.5, framealpha=0.9)
    ax.grid(True, alpha=0.12)
    fig.tight_layout(pad=1.5)
    return fig


def _build_comparison_table(comparison: "SpectrumComparison") -> QTableWidget:
    """
    Build a QTableWidget showing peak-by-peak comparison results.
    Columns: Exp. Peak | Theo. Peak | Delta | Assignment | Status
    """
    all_rows = []

    for m in comparison.peak_matches:
        all_rows.append((
            f"{m.exp_position:.1f}",
            f"{m.theo_position:.1f}",
            f"{m.delta:+.1f}",
            m.assignment or "-",
            "MATCH",
        ))

    for pos in comparison.unmatched_exp:
        all_rows.append((f"{pos:.1f}", "-", "-", "-", "MISS (exp)"))

    for pos in comparison.unmatched_theo:
        all_rows.append(("-", f"{pos:.1f}", "-", "-", "MISS (theo)"))

    table = QTableWidget(len(all_rows), 5)
    table.setHorizontalHeaderLabels([
        "Exp. Peak", "Theo. Peak", "Delta (\u0394)", "Assignment", "Status"
    ])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setMaximumHeight(200)

    # Style
    table.setStyleSheet("""
        QTableWidget {
            font-size: 9px;
            background: white;
            gridline-color: #E0E0E0;
        }
        QTableWidget::item { padding: 2px 4px; }
        QHeaderView::section {
            background: #1e293b; color: #94a3b8;
            font-size: 9px; font-weight: bold;
            padding: 3px;
        }
    """)

    for row_idx, (exp_pk, theo_pk, delta, asgn, status) in enumerate(all_rows):
        items = [exp_pk, theo_pk, delta, asgn, status]
        for col, text in enumerate(items):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if status == "MATCH":
                item.setBackground(QColor("#EAFAF1"))
            elif "MISS" in status:
                item.setBackground(QColor("#FDEDEC"))

            table.setItem(row_idx, col, item)

    return table


# ─── 팝업 클래스 ───────────────────────────────────────────────────

class PredictedSpectrumPopup(QDialog):
    """SMILES 기반 예측 스펙트럼 팝업 (탭형) — GUIDE.md v3 기준 + 실험 데이터 비교"""

    def __init__(self, smiles: str, spectrum_type: str = "ir", parent=None):
        super().__init__(parent)
        self.smiles = smiles
        if not isinstance(spectrum_type, str):
            _logger.warning("PredictedSpectrumPopup: spectrum_type=%r is not str, defaulting to 'ir'", spectrum_type)
            spectrum_type = "ir"
        self.spectrum_type = spectrum_type.lower()
        self.setWindowTitle(f"예측 스펙트럼 — {smiles}")
        self.resize(1100, 800)
        self.setMinimumSize(950, 650)

        # Store predicted data for comparison
        self._spec: Optional["PredictedSpectra"] = None
        self._tabs: Optional[QTabWidget] = None
        self._comparison_panel: Optional[QWidget] = None

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(f"SMILES: {self.smiles}")
        header.setFont(QFont("Monospace", 9))
        header.setStyleSheet(
            "background:#1e293b; color:#94a3b8; padding:4px 8px; border-radius:4px;"
        )
        layout.addWidget(header)

        if not PREDICT_OK:
            layout.addWidget(QLabel("predict_spectra module not loaded"))
            return
        if not MPL_OK:
            layout.addWidget(QLabel("matplotlib not installed"))
            return

        self._spec = predict_all(self.smiles)

        # [Rule GG] SIMULATION_MODE 노랑 배너 — ORCA 없이 경험적 추정만 사용
        sim_banner = QLabel(
            "[SIMULATION_MODE] 이론적 스펙트럼 (SMARTS 경험적 추정) — "
            "ORCA DFT 계산 결과가 아닙니다. 학술 논문 인용 불가."
        )
        sim_banner.setWordWrap(True)
        # [MAGIC] _SIM_BANNER_BG=#fff3cd, _SIM_BANNER_FG=#856404 — Bootstrap warning 톤
        sim_banner.setStyleSheet(
            "QLabel { background-color: #fff3cd; color: #856404; "
            "border: 1px solid #ffeeba; border-radius: 4px; "
            "padding: 6px 10px; font-weight: bold; font-size: 11px; }"
        )
        layout.addWidget(sim_banner)

        formula_row = QHBoxLayout()
        formula_row.addStretch()
        formula_row.addWidget(QLabel(f"Formula: {self._spec.formula}"))
        layout.addLayout(formula_row)

        for w in self._spec.warnings:
            wlabel = QLabel(f"Warning: {w}")
            wlabel.setStyleSheet("color: #E67E22; font-size: 9px;")
            layout.addWidget(wlabel)

        # --- Main splitter: spectrum tabs (top) + comparison panel (bottom) ---
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Spectrum tabs
        self._tabs = QTabWidget()

        self._tabs.addTab(self._expanding_canvas(
            _make_ir_figure(self._spec.ir_peaks)), "IR")
        self._tabs.addTab(self._expanding_canvas(
            _make_raman_figure(self._spec.raman_peaks, self._spec.ir_peaks)), "Raman")
        self._tabs.addTab(self._expanding_canvas(
            _make_nmr_h1_figure(self._spec.h1_nmr_peaks, self._spec.formula, self.smiles)),
            "\u00b9H-NMR")
        self._tabs.addTab(self._expanding_canvas(
            _make_nmr_c13_figure(self._spec.c13_peaks, self._spec.formula, self.smiles)),
            "\u00b9\u00b3C-NMR")
        self._tabs.addTab(self._expanding_canvas(
            _make_uvvis_figure(self._spec.uvvis_peaks, self.smiles)), "UV-Vis")  # [M691_W_P2_UV_INSET]

        # EI-MS 탭 (M684 Block4 — McLafferty + α-cleavage 강화)
        try:
            self._tabs.addTab(
                self._expanding_canvas(_make_ms_figure(self.smiles)), "EI-MS"
            )
        except Exception as _ems:
            _logger.warning("[M684 Block4] EI-MS tab failed: %s", _ems)
            self._tabs.addTab(QLabel("EI-MS 로드 실패"), "EI-MS")

        # Stability 탭 (M684 Block7 신설 — 열역학/광안정성)
        try:
            self._tabs.addTab(
                self._expanding_canvas(_make_stability_figure(self.smiles)), "안정성"
            )
        except Exception as _estab:
            _logger.warning("[M684 Block7] Stability tab failed: %s", _estab)
            self._tabs.addTab(QLabel("안정성 분석 로드 실패"), "안정성")

        tab_map = {
            "ir": 0, "raman": 1,
            "nmr": 2, "h1": 2, "1h": 2,
            "c13": 3, "13c": 3,
            "uvvis": 4, "uv": 4, "uv-vis": 4,
            "ms": 5, "ei-ms": 5, "ei_ms": 5,
            "stability": 6, "stab": 6,
        }
        self._tabs.setCurrentIndex(tab_map.get(self.spectrum_type, 0))
        splitter.addWidget(self._tabs)

        # Comparison panel (initially hidden)
        self._comparison_panel = QFrame()
        self._comparison_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self._comparison_panel.setVisible(False)
        self._comparison_layout = QVBoxLayout(self._comparison_panel)
        self._comparison_layout.setContentsMargins(4, 4, 4, 4)

        placeholder = QLabel("Load experimental data to see comparison results here.")
        placeholder.setStyleSheet("color: #94a3b8; font-style: italic; padding: 8px;")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._comparison_layout.addWidget(placeholder)

        splitter.addWidget(self._comparison_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        # --- Button row ---
        btn_row = QHBoxLayout()

        # Experimental data import button
        if EXP_IMPORT_OK:
            exp_btn = QPushButton("Load Experimental Data")
            exp_btn.setToolTip(
                "Load .jdx/.dx (JCAMP-DX) or .csv spectroscopy data "
                "and compare against theoretical predictions"
            )
            exp_btn.clicked.connect(self._on_load_experimental)
            exp_btn.setStyleSheet(
                "QPushButton{background:#059669;color:white;border-radius:6px;"
                "padding:6px 16px;font-weight:bold;}"
                "QPushButton:hover{background:#047857;}"
            )
            btn_row.addWidget(exp_btn)
        else:
            no_exp = QLabel("(experimental_data_importer not available)")
            no_exp.setStyleSheet("color:#94a3b8; font-size:8px;")
            btn_row.addWidget(no_exp)

        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(
            "QPushButton{background:#3b82f6;color:white;border-radius:6px;padding:6px 20px;}"
            "QPushButton:hover{background:#2563eb;}"
        )
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        note = QLabel(
            "* This spectrum is estimated from SMILES structure. "
            "Precision is lower than ORCA DFT calculations."
        )
        note.setStyleSheet("color: #64748b; font-size: 9px; font-style: italic;")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        layout.addWidget(note)

    @staticmethod
    def _expanding_canvas(fig: "Figure") -> "FigureCanvas":
        """FigureCanvas that expands to fill available space."""
        canvas = FigureCanvas(fig)
        canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        canvas.setMinimumHeight(300)
        return canvas

    # ------------------------------------------------------------------
    # Experimental data loading and comparison
    # ------------------------------------------------------------------

    def _on_load_experimental(self) -> None:
        """Handle 'Load Experimental Data' button click."""
        if not EXP_IMPORT_OK or self._spec is None:
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Load Experimental Spectrum",
            "",
            "JCAMP-DX (*.jdx *.dx);;CSV (*.csv *.tsv *.txt);;All Files (*)",
        )
        if not filepath:
            return

        try:
            exp_data = load_experimental_file(filepath)
        except FileNotFoundError as e:
            _logger.warning("File not found: %s", e)
            self._show_comparison_error(f"File not found: {filepath}")
            return
        except ValueError as e:
            _logger.warning("Parse error: %s", e)
            self._show_comparison_error(f"Could not parse file: {e}")
            return
        except OSError as e:
            _logger.warning("IO error loading experimental file: %s", e)
            self._show_comparison_error(f"IO error: {e}")
            return

        _logger.info(
            "Loaded experimental data: %s, %d points, type=%s",
            filepath, exp_data.num_points, exp_data.spectrum_type,
        )

        # Determine which spectrum type to compare
        current_tab = self._tabs.currentIndex() if self._tabs else 0
        self._run_comparison(exp_data, current_tab)

    def _run_comparison(self, exp_data: "ExperimentalSpectrum",
                        tab_index: int) -> None:
        """Run comparison and update UI with results."""
        if self._spec is None:
            return

        # Map tab index to spectrum type and get corresponding peaks
        tab_type_map = {0: "IR", 1: "Raman", 4: "UV-Vis"}
        spectrum_type = tab_type_map.get(tab_index, exp_data.spectrum_type)

        comparison: Optional["SpectrumComparison"] = None
        overlay_fig = None

        try:
            if spectrum_type == "IR" and self._spec.ir_peaks:
                theo_tuples, assignments = ir_peaks_to_comparison_format(
                    self._spec.ir_peaks)
                comparison = compare_spectra(
                    exp_data, theo_tuples, tolerance=50.0,
                    assignments=assignments, method="IR",
                )
                overlay_fig = _make_ir_comparison_figure(
                    self._spec.ir_peaks, exp_data, comparison)
                target_tab = 0

            elif spectrum_type == "Raman" and self._spec.raman_peaks:
                theo_tuples, assignments = raman_peaks_to_comparison_format(
                    self._spec.raman_peaks)
                comparison = compare_spectra(
                    exp_data, theo_tuples, tolerance=50.0,
                    assignments=assignments, method="Raman",
                )
                overlay_fig = _make_raman_comparison_figure(
                    self._spec.raman_peaks, exp_data, comparison)
                target_tab = 1

            elif spectrum_type == "UV-Vis" and self._spec.uvvis_peaks:
                theo_tuples, assignments = uvvis_peaks_to_comparison_format(
                    self._spec.uvvis_peaks)
                comparison = compare_spectra(
                    exp_data, theo_tuples, tolerance=20.0,
                    assignments=assignments, method="UV-Vis",
                )
                overlay_fig = _make_uvvis_comparison_figure(
                    self._spec.uvvis_peaks, exp_data, comparison)
                target_tab = 4

            else:
                # Try IR as fallback
                if self._spec.ir_peaks:
                    theo_tuples, assignments = ir_peaks_to_comparison_format(
                        self._spec.ir_peaks)
                    comparison = compare_spectra(
                        exp_data, theo_tuples, tolerance=50.0,
                        assignments=assignments, method="IR",
                    )
                    overlay_fig = _make_ir_comparison_figure(
                        self._spec.ir_peaks, exp_data, comparison)
                    target_tab = 0

        except (ValueError, TypeError, IndexError) as e:
            _logger.warning("Comparison failed: %s", e)
            self._show_comparison_error(f"Comparison error: {e}")
            return

        if comparison is None or overlay_fig is None:
            self._show_comparison_error(
                "No matching theoretical data for the selected spectrum type.")
            return

        # Replace the corresponding tab with overlay figure
        if self._tabs is not None:
            tab_label = self._tabs.tabText(target_tab) + " [vs Exp]"
            self._tabs.removeTab(target_tab)
            self._tabs.insertTab(
                target_tab, self._expanding_canvas(overlay_fig), tab_label)
            self._tabs.setCurrentIndex(target_tab)

        # Update comparison panel
        self._update_comparison_panel(comparison, exp_data)

    def _update_comparison_panel(self, comparison: "SpectrumComparison",
                                 exp_data: "ExperimentalSpectrum") -> None:
        """Populate the comparison panel with results."""
        if self._comparison_panel is None:
            return

        # Clear existing content
        while self._comparison_layout.count():
            child = self._comparison_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._comparison_panel.setVisible(True)

        # Score summary header
        score_color = "#27AE60" if comparison.overall_score >= 70 else (
            "#E67E22" if comparison.overall_score >= 40 else "#E74C3C")

        summary = QGroupBox("Comparison Results")
        summary.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold; font-size: 10px;
                border: 2px solid {score_color};
                border-radius: 6px; margin-top: 6px; padding-top: 14px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px; padding: 0 4px;
                color: {score_color};
            }}
        """)
        summary_layout = QHBoxLayout(summary)

        # Metrics
        metrics_text = (
            f"Overall Match Score: {comparison.overall_score:.1f}%\n"
            f"Peaks Matched: {len(comparison.peak_matches)} / "
            f"{len(comparison.peak_matches) + len(comparison.unmatched_exp)} "
            f"({comparison.match_percentage:.0f}%)\n"
            f"Cosine Similarity: {comparison.cosine_similarity:.4f}\n"
            f"Peak Position RMSD: {comparison.peak_rmsd:.1f} "
            f"{'cm\u207b\u00b9' if comparison.method == 'IR' else 'nm'}\n"
            f"Spectrum Type: {comparison.method}\n"
            f"Tolerance: {comparison.tolerance_used:.0f} "
            f"{'cm\u207b\u00b9' if comparison.method == 'IR' else 'nm'}\n"
            f"Experimental Points: {exp_data.num_points}\n"
            f"Exp. Peaks Found: {len(exp_data.peaks)}"
        )
        metrics_label = QLabel(metrics_text)
        metrics_label.setFont(QFont("Monospace", 8))
        metrics_label.setStyleSheet("padding: 4px;")
        summary_layout.addWidget(metrics_label)

        # Large score display
        score_display = QLabel(f"{comparison.overall_score:.0f}%")
        score_display.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        score_display.setStyleSheet(f"color: {score_color}; padding: 8px;")
        score_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary_layout.addWidget(score_display)

        self._comparison_layout.addWidget(summary)

        # Peak comparison table
        if comparison.peak_matches or comparison.unmatched_exp or comparison.unmatched_theo:
            table = _build_comparison_table(comparison)
            self._comparison_layout.addWidget(table)

    def _show_comparison_error(self, message: str) -> None:
        """Display an error in the comparison panel."""
        if self._comparison_panel is None:
            return

        while self._comparison_layout.count():
            child = self._comparison_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._comparison_panel.setVisible(True)

        err_label = QLabel(f"Error: {message}")
        err_label.setStyleSheet(
            "color: #E74C3C; font-weight: bold; padding: 8px;"
            "background: #FDEDEC; border-radius: 4px;"
        )
        err_label.setWordWrap(True)
        self._comparison_layout.addWidget(err_label)


def launch_predicted_spectrum(smiles: str, spectrum_type: str = "ir",
                              parent: Optional[QWidget] = None) -> None:
    """Convenience launcher function."""
    dlg = PredictedSpectrumPopup(smiles, spectrum_type, parent)
    dlg.exec()
