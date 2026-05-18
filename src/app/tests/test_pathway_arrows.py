"""
Test: 각 단계별 화살표가 정확히 원자를 연결하는지 디버그
+ 확대된 개별 단계 캡처
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QImage

app = QApplication(sys.argv)

from reaction_mechanisms import get_mechanism, MechanismData
from popup_reaction import ReactionPathwayWidget

# Fischer 에스터화 메커니즘
mech = get_mechanism("esterification")
print(f"Mechanism: {mech.title}, {mech.total_steps} steps")

for i, step in enumerate(mech.steps):
    print(f"\n--- Step {i+1}: {step.title} ---")
    print(f"  Reactant: {step.reactant_smiles}")
    print(f"  Product:  {step.product_smiles}")
    for j, a in enumerate(step.arrows):
        print(f"  Arrow {j}: {a.from_label}[idx={a.from_atom_idx}] → {a.to_label}[idx={a.to_atom_idx}]")
        print(f"           type={a.arrow_type}, from_type={a.from_type}, curvature={a.curvature}")

# 넓은 경로 위젯으로 큰 이미지 생성
pw = ReactionPathwayWidget()
pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
pw.resize(1400, 350)
pw.show()
pw.set_mechanism(mech)

def capture():
    screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    pixmap = pw.grab()
    path = os.path.join(screenshot_dir, "pathway_arrows_debug.png")
    pixmap.save(path)
    print(f"\nScreenshot saved: {path}")

    # 산화 반응도 테스트
    mech2 = get_mechanism("oxidation")
    if mech2:
        pw.set_mechanism(mech2)
        pixmap2 = pw.grab()
        path2 = os.path.join(screenshot_dir, "pathway_oxidation_debug.png")
        pixmap2.save(path2)
        print(f"Screenshot saved: {path2}")

    # SN2 반응
    mech3 = get_mechanism("sn2")
    if mech3:
        pw.set_mechanism(mech3)
        pixmap3 = pw.grab()
        path3 = os.path.join(screenshot_dir, "pathway_sn2_debug.png")
        pixmap3.save(path3)
        print(f"Screenshot saved: {path3}")

    # Diels-Alder
    mech4 = get_mechanism("diels_alder")
    if mech4:
        pw.set_mechanism(mech4)
        pixmap4 = pw.grab()
        path4 = os.path.join(screenshot_dir, "pathway_da_debug.png")
        pixmap4.save(path4)
        print(f"Screenshot saved: {path4}")

    app.quit()

QTimer.singleShot(500, capture)
app.exec()
