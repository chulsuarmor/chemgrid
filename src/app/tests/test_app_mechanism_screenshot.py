#!/usr/bin/env python3
"""
실제 ChemGrid 앱 UI에서 반응 메커니즘 팝업을 띄우고 스크린샷 캡처.
앱이 사용자에게 어떻게 보이는지 확인용.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QImage, QPainter, QColor

app = QApplication.instance() or QApplication(sys.argv)

from popup_reaction import ReactionSchemeWidget
from reaction_mechanisms import get_mechanism
from mechanism_engine import MechanismEngine

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'app_screenshots')
os.makedirs(OUTPUT_DIR, exist_ok=True)

engine = MechanismEngine()


def capture_mechanism(mech, filename, width=1200, height=320):
    """메커니즘을 실제 위젯 크기로 렌더링하여 캡처"""
    widget = ReactionSchemeWidget()
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.resize(width, height)
    widget.set_mechanism(mech, 0)
    widget.show()

    img = QImage(QSize(width, height), QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    painter = QPainter(img)
    widget.render(painter)
    painter.end()

    path = os.path.join(OUTPUT_DIR, filename)
    img.save(path, "PNG")
    print(f"  Saved: {path}")
    widget.close()
    return path


print("=" * 60)
print("ChemGrid App UI - Mechanism Screenshot Test")
print(f"Output: {OUTPUT_DIR}")
print("=" * 60)

# Gold standard 반응들
print("\n[Gold Standard - 실제 앱 UI]")
for mtype in ["sn2", "sn1", "e2", "eas", "esterification"]:
    mech = get_mechanism(mtype)
    if mech:
        print(f"  {mtype}: {mech.title}")
        # Step 별로 각각 캡처 (사용자가 단계 넘길 때 보이는 것)
        for step_idx in range(mech.total_steps):
            widget = ReactionSchemeWidget()
            widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            widget.resize(1200, 320)
            widget.set_mechanism(mech, step_idx)
            widget.show()

            img = QImage(QSize(1200, 320), QImage.Format.Format_ARGB32)
            img.fill(QColor(255, 255, 255))
            painter = QPainter(img)
            widget.render(painter)
            painter.end()

            path = os.path.join(OUTPUT_DIR, f"app_{mtype}_step{step_idx + 1}.png")
            img.save(path, "PNG")
            print(f"    Step {step_idx + 1}: {path}")
            widget.close()

# 자동 생성 반응들
print("\n[Auto-Generated - 실제 앱 UI]")
auto_tests = [
    ("SN2", "CBr.[OH-]", "CO.[Br-]"),
    ("EAS", "c1ccccc1", "c1ccc(Br)cc1"),
    ("DielsAlder", "C=CC=C.C=C", "C1CC=CCC1"),
    ("Ester", "CC(=O)O.CO", "CC(=O)OC"),
    ("FriedelCrafts", "c1ccccc1.CCl", "CCc1ccccc1"),
]

for name, r_smi, p_smi in auto_tests:
    mech = engine.generate_mechanism(r_smi, p_smi)
    if mech:
        print(f"  {name}: {mech.title} ({mech.total_steps} steps)")
        capture_mechanism(mech, f"app_auto_{name}.png")
    else:
        print(f"  {name}: FAILED")

print(f"\nDone! Screenshots saved to {OUTPUT_DIR}")
