"""
draw.py — ChemGrid 진입점 (Entry Point)
=========================================
canvas.py의 MoleculeCanvas와 main_window.py의 MainWindow를 사용합니다.

이전 버전에서는 이 파일에 MoleculeCanvas와 MainWindow가 모놀리스로 정의되어 있었으나,
Phase 6-4에서 모듈 분리가 완료되어 이제는 각 모듈에서 임포트합니다.

후방 호환: 다른 모듈이 `from draw import MoleculeCanvas`를 사용하는 경우를 위해
canvas.py에서 재임포트합니다.
"""
import sys
import os

# 현재 스크립트 디렉토리를 sys.path에 추가 (모듈 검색 경로)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from PyQt6.QtWidgets import QApplication

# ========== 후방 호환 재임포트 ==========
# 다른 모듈이 `from draw import X`를 사용하는 경우를 위한 재수출
from canvas import MoleculeCanvas, CanvasMode, get_coord_key
from main_window import MainWindow
from ui_utils import load_icon, VERSION

# ==========================================
# 진입점
# ==========================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()

    # ========== CLI 자동 분자 로딩 (자동화 테스트용) ==========
    # Usage: python draw.py --auto-mol "benzene"
    #        python draw.py --auto-smiles "c1ccccc1"
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--auto-mol', type=str, default=None,
                        help='Auto-load molecule by name on startup')
    parser.add_argument('--auto-smiles', type=str, default=None,
                        help='Auto-load molecule by SMILES on startup')
    args, _ = parser.parse_known_args()

    if args.auto_mol:
        from PyQt6.QtCore import QTimer
        def _auto_load_mol():
            win.mol_name_input.setText(args.auto_mol)
            win._on_mol_name_submit()
        QTimer.singleShot(1500, _auto_load_mol)
    elif args.auto_smiles:
        from PyQt6.QtCore import QTimer
        def _auto_load_smiles():
            win._draw_smiles_on_canvas(args.auto_smiles, "auto-test")
        QTimer.singleShot(1500, _auto_load_smiles)

    sys.exit(app.exec())
