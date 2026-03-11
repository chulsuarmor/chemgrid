"""
test_spectra_render.py — 새 그래프 렌더링 시각적 검증 (PyQt6 없이 실행)
matplotlib Agg 백엔드로 5개 분광 그래프를 PNG로 저장
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'app'))

import matplotlib
matplotlib.use('Agg')  # GUI 없이 파일로 저장

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

# 예측 모듈 로드
from predict_spectra import predict_all

# 렌더 함수 가져오기 (PyQt6 없이 임포트되도록 패치)
import types, builtins

# PyQt6 stub (임포트 에러 방지)
qt_stub = types.ModuleType('PyQt6')
qt_stub.QtWidgets = types.ModuleType('PyQt6.QtWidgets')
qt_stub.QtCore    = types.ModuleType('PyQt6.QtCore')
qt_stub.QtGui     = types.ModuleType('PyQt6.QtGui')
for attr in ['QDialog','QVBoxLayout','QHBoxLayout','QTabWidget',
             'QWidget','QLabel','QPushButton']:
    setattr(qt_stub.QtWidgets, attr, object)
qt_stub.QtCore.Qt = type('Qt', (), {'AlignmentFlag': type('AF', (), {'AlignRight': 0, 'AlignCenter': 0})()})()
qt_stub.QtGui.QFont = object
sys.modules['PyQt6'] = qt_stub
sys.modules['PyQt6.QtWidgets'] = qt_stub.QtWidgets
sys.modules['PyQt6.QtCore'] = qt_stub.QtCore
sys.modules['PyQt6.QtGui'] = qt_stub.QtGui

# FigureCanvasQTAgg stub
from matplotlib.backends.backend_agg import FigureCanvasAgg
mpl_qt_stub = types.ModuleType('matplotlib.backends.backend_qtagg')
mpl_qt_stub.FigureCanvasQTAgg = FigureCanvasAgg
sys.modules['matplotlib.backends.backend_qtagg'] = mpl_qt_stub

from popup_predicted_spectrum import (
    _make_ir_figure, _make_raman_figure,
    _make_nmr_h1_figure, _make_nmr_c13_figure, _make_uvvis_figure
)

# ─── 테스트 분자 목록 ───────────────────────────────────────
TEST_MOLECULES = {
    "ethyl_benzoate": "CCOC(=O)c1ccccc1",
    "ibuprofen":      "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "ethanol":        "CCO",
    "benzene":        "c1ccccc1",
}

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'docs', 'exports', 'spectra_assets', 'auto_generated', 'temp_assets')
os.makedirs(OUT_DIR, exist_ok=True)

print("=" * 60)
print("분광 그래프 렌더링 테스트 시작")
print("=" * 60)

for mol_name, smiles in TEST_MOLECULES.items():
    print(f"\n[{mol_name}] SMILES: {smiles}")
    spec = predict_all(smiles)
    print(f"  분자식: {spec.formula}")
    print(f"  IR 피크: {len(spec.ir_peaks)}개")
    print(f"  Raman 피크: {len(spec.raman_peaks)}개")
    print(f"  ¹H-NMR 피크: {len(spec.h1_nmr_peaks)}개")
    print(f"  ¹³C-NMR 피크: {len(spec.c13_peaks)}개")
    print(f"  UV-Vis 피크: {len(spec.uvvis_peaks)}개")

    graph_funcs = {
        "IR":      (_make_ir_figure, [spec.ir_peaks]),
        "Raman":   (_make_raman_figure, [spec.raman_peaks]),
        "H1NMR":   (_make_nmr_h1_figure, [spec.h1_nmr_peaks, spec.formula]),
        "C13NMR":  (_make_nmr_c13_figure, [spec.c13_peaks, spec.formula]),
        "UVVis":   (_make_uvvis_figure, [spec.uvvis_peaks]),
    }

    for gname, (func, args) in graph_funcs.items():
        try:
            fig = func(*args)
            canvas = FigureCanvasAgg(fig)
            canvas.draw()
            out_path = os.path.join(OUT_DIR, f"{mol_name}_{gname}_new.png")
            fig.savefig(out_path, dpi=120, bbox_inches='tight', facecolor='white')
            print(f"  ✅ {gname} → {os.path.basename(out_path)}")
        except Exception as e:
            print(f"  ❌ {gname} 오류: {e}")
            import traceback
            traceback.print_exc()

print("\n" + "=" * 60)
print(f"저장 위치: {OUT_DIR}")
print("=" * 60)
