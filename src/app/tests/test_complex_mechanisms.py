"""
Test: 복잡한 메커니즘 렌더링 (Friedel-Crafts, Tosylation, Radical, Beckmann, Michael, Curtius)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

app = QApplication(sys.argv)

from reaction_mechanisms import get_mechanism, get_available_mechanisms
from popup_reaction import ReactionPathwayWidget

print(f"Available mechanisms: {get_available_mechanisms()}")

screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(screenshot_dir, exist_ok=True)

# 새로 추가한 복잡 메커니즘들 테스트
test_mechs = [
    "friedel_crafts_alkylation",
    "tosylation",
    "radical_halogenation",
    "beckmann",
    "michael_addition",
    "curtius",
]

pw = ReactionPathwayWidget()
pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
pw.resize(1400, 300)
pw.show()

results = []

def capture_all():
    for name in test_mechs:
        mech = get_mechanism(name)
        if not mech:
            print(f"  [SKIP] {name}: not found")
            continue

        # 높이 조정
        n_mols = len(mech.steps) + 1
        pw.resize(1400, max(250, 300))
        pw.set_mechanism(mech)

        pixmap = pw.grab()
        fname = f"mech_{name}.png"
        path = os.path.join(screenshot_dir, fname)
        pixmap.save(path)

        # 화살표 수 세기
        total_arrows = sum(len(s.arrows) for s in mech.steps)
        reagent_steps = sum(1 for s in mech.steps if getattr(s, 'reagents', ''))

        print(f"  [OK] {name}: {mech.title} ({mech.total_steps} steps, {total_arrows} arrows, {reagent_steps} reagent labels)")
        results.append((name, path))

    print(f"\nTotal: {len(results)} mechanisms rendered")
    app.quit()

QTimer.singleShot(500, capture_all)
app.exec()
