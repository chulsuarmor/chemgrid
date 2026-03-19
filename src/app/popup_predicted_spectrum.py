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
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

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
        except Exception:
            pass

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
                 .replace("fingerprint region", "")
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
    ax.set_xlabel("Wavenumber (cm⁻¹)", fontsize=9)
    ax.set_ylabel("Transmittance (%)", fontsize=9)
    ax.set_title("IR Spectrum (Predicted)", fontsize=10, fontweight='bold', pad=8)
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
        ax.set_title(f"¹H-NMR Spectrum (Predicted) — {formula}", fontsize=10, fontweight='bold')
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
                color='#E74C3C', lw=2.2, solid_capstyle='butt', zorder=6)
        ax.text(pk.shift, step_height + integ_scale * 0.15,
                f"{pk.integration:.0f}H",
                fontsize=6.5, ha='center', va='bottom',
                color='#C0392B', fontweight='bold', zorder=7)

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
    ax.set_title(f"¹H-NMR Spectrum (Predicted) — {formula}",
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

            ax.plot([pk.shift, pk.shift], [0, peak_h],
                    color=color, lw=2.0, alpha=0.82, solid_capstyle='butt', zorder=3)

            ax.text(pk.shift, peak_h + 0.02, f"{pk.shift:.1f}",
                    fontsize=5.8, ha='center', va='bottom', color=color,
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
    ax.set_title(f"¹³C-NMR Spectrum (Predicted) — {formula}",
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

        ax.annotate(
            f"{pk.shift:.0f} cm⁻¹\n{pk.assignment}",
            xy=(pk.shift, y_pk),
            xytext=(0, 14), textcoords='offset points',
            fontsize=6.5, ha='center', color='#1A252F', zorder=5,
            arrowprops=dict(arrowstyle='->', color='#95A5A6', lw=0.7),
            bbox=dict(boxstyle='round,pad=0.25', facecolor='white',
                      edgecolor='#BDC3C7', alpha=0.92, lw=0.8)
        )

    ax.set_xlim(0, 4000)
    ax.set_ylim(0, y_max * 1.65)
    ax.set_xlabel("Raman Shift (cm⁻¹)", fontsize=9)
    ax.set_ylabel("Intensity (a.u.)", fontsize=9)
    ax.set_title("Raman Spectrum (Predicted)", fontsize=10, fontweight='bold', pad=8)
    ax.grid(True, alpha=0.15, color='#AAB7B8')
    ax.text(3980, y_max * 1.58, "* Estimated — not for publication",
            fontsize=6, color='#AAB7B8', style='italic', ha='right')
    fig.tight_layout(pad=1.5)
    return fig


# ─── UV-Vis 스펙트럼 ───────────────────────────────────────────────

def _make_uvvis_figure(peaks: List) -> "Figure":
    """
    UV-Vis Figure (듀얼 뷰)
    GUIDE.md §3.5 기준:
      - 좌: ε linear, 우: log ε
      - x축 200~700 nm, λmax 수직 점선, 전이 타입 라벨
      - 라벨 Y_LEVELS 5단계 순환 (중첩 방지)
      - 가시광선(400~700nm) 배경 음영
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
    ax1.set_ylabel("ε (L·mol⁻¹·cm⁻¹)", fontsize=9)
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
    fig.tight_layout(pad=1.5)
    return fig


# ─── 팝업 클래스 ───────────────────────────────────────────────────

class PredictedSpectrumPopup(QDialog):
    """SMILES 기반 예측 스펙트럼 팝업 (탭형) — GUIDE.md v3 기준"""

    def __init__(self, smiles: str, spectrum_type: str = "ir", parent=None):
        super().__init__(parent)
        self.smiles = smiles
        self.spectrum_type = spectrum_type.lower()
        self.setWindowTitle(f"예측 스펙트럼 — {smiles}")
        self.resize(1000, 700)
        self.setMinimumSize(900, 600)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel(f"SMILES: {self.smiles}")
        header.setFont(QFont("Monospace", 9))
        header.setStyleSheet(
            "background:#1e293b; color:#94a3b8; padding:4px 8px; border-radius:4px;"
        )
        layout.addWidget(header)

        if not PREDICT_OK:
            layout.addWidget(QLabel("⚠️ predict_spectra 모듈 로드 실패"))
            return
        if not MPL_OK:
            layout.addWidget(QLabel("⚠️ matplotlib 미설치"))
            return

        spec = predict_all(self.smiles)

        formula_row = QHBoxLayout()
        formula_row.addStretch()
        formula_row.addWidget(QLabel(f"분자식: {spec.formula}"))
        layout.addLayout(formula_row)

        for w in spec.warnings:
            wlabel = QLabel(f"⚠️ {w}")
            wlabel.setStyleSheet("color: #E67E22; font-size: 9px;")
            layout.addWidget(wlabel)

        tabs = QTabWidget()

        def _expanding_canvas(fig):
            """FigureCanvas that expands to fill available space."""
            canvas = FigureCanvas(fig)
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            canvas.setMinimumHeight(300)
            return canvas

        tabs.addTab(_expanding_canvas(_make_ir_figure(spec.ir_peaks)), "IR")
        # [NEW v3] Raman에 IR peaks 전달 → ghost layer
        tabs.addTab(_expanding_canvas(_make_raman_figure(spec.raman_peaks, spec.ir_peaks)), "Raman")
        tabs.addTab(_expanding_canvas(_make_nmr_h1_figure(spec.h1_nmr_peaks, spec.formula, self.smiles)), "¹H-NMR")
        tabs.addTab(_expanding_canvas(_make_nmr_c13_figure(spec.c13_peaks, spec.formula, self.smiles)), "¹³C-NMR")
        tabs.addTab(_expanding_canvas(_make_uvvis_figure(spec.uvvis_peaks)), "UV-Vis")

        tab_map = {
            "ir": 0, "raman": 1,
            "nmr": 2, "h1": 2, "1h": 2,
            "c13": 3, "13c": 3,
            "uvvis": 4, "uv": 4, "uv-vis": 4,
        }
        tabs.setCurrentIndex(tab_map.get(self.spectrum_type, 0))
        layout.addWidget(tabs)

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(
            "QPushButton{background:#3b82f6;color:white;border-radius:6px;padding:6px 20px;}"
            "QPushButton:hover{background:#2563eb;}"
        )
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        note = QLabel(
            "※ 이 스펙트럼은 SMILES 구조 기반 추정값입니다. "
            "정밀도는 ORCA 계산 대비 낮으며 발표·논문에 사용하지 마십시오."
        )
        note.setStyleSheet("color: #64748b; font-size: 9px; font-style: italic;")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        layout.addWidget(note)


def launch_predicted_spectrum(smiles: str, spectrum_type: str = "ir", parent=None):
    """간편 실행 함수"""
    dlg = PredictedSpectrumPopup(smiles, spectrum_type, parent)
    dlg.exec()
