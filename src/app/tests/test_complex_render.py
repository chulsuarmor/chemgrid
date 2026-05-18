"""
Test: 복잡한 분자 반응 렌더링 — 실제 앱에서 사용하는 ReactionPopup 형태로
벤젠+Br2 (EAS), 아세트산+에탄올, 톨루엔 니트로화 등
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

app = QApplication(sys.argv)

from reaction_mechanisms import get_mechanism, get_available_mechanisms
from popup_reaction import ReactionPopup, ReactionPathwayWidget

screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(screenshot_dir, exist_ok=True)

# === 1. 실제 팝업: 벤젠 + Br2 (EAS) ===
popup1 = ReactionPopup(["c1ccccc1", "BrBr"], ["벤젠", "Br₂"])
popup1.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
popup1.resize(1200, 850)
popup1.show()
if popup1.reaction_list.count() > 0:
    popup1.reaction_list.setCurrentRow(0)

# === 2. 실제 팝업: 아세트산 + 에탄올 (에스터화) ===
popup2 = ReactionPopup(["CC(=O)O", "CCO"], ["아세트산", "에탄올"])
popup2.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
popup2.resize(1200, 850)
popup2.show()
if popup2.reaction_list.count() >= 2:
    popup2.reaction_list.setCurrentRow(1)  # Fischer

# === 3. 개별 메커니즘 위젯: 모든 복잡 메커니즘 ===
all_mechs = [
    "sn2", "sn1", "eas", "esterification",
    "friedel_crafts_alkylation", "tosylation",
    "radical_halogenation", "beckmann",
    "michael_addition", "curtius",
    "diels_alder", "oxidation", "amidation",
]

pw = ReactionPathwayWidget()
pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

def capture():
    # 팝업 캡처
    pix1 = popup1.grab()
    p1 = os.path.join(screenshot_dir, "popup_benzene_br2.png")
    pix1.save(p1)
    print(f"[POPUP] benzene+Br2: {p1}")

    pix2 = popup2.grab()
    p2 = os.path.join(screenshot_dir, "popup_acoh_etoh.png")
    pix2.save(p2)
    print(f"[POPUP] AcOH+EtOH: {p2}")

    # 개별 메커니즘 캡처
    for name in all_mechs:
        mech = get_mechanism(name)
        if not mech:
            continue
        n_mols = len(mech.steps) + 1
        h = max(280, 300)
        pw.resize(1400, h)
        pw.show()
        pw.set_mechanism(mech)
        pixmap = pw.grab()
        path = os.path.join(screenshot_dir, f"mech_{name}.png")
        pixmap.save(path)
        arrows = sum(len(s.arrows) for s in mech.steps)
        print(f"  [OK] {name}: {mech.title} ({mech.total_steps}steps, {arrows}arrows)")

    app.quit()

QTimer.singleShot(1000, capture)
app.exec()
