"""
Test: ReactionPathwayWidget - Fischer 에스터화 반응 (더 많은 단계)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

app = QApplication(sys.argv)

from popup_reaction import ReactionPopup

# 아세트산 + 에탄올 → 에스터화 반응
smiles_list = ["CC(=O)O", "CCO"]
names = ["아세트산", "에탄올"]

popup = ReactionPopup(smiles_list, names)
popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
popup.resize(1100, 800)
popup.show()

# 에스터화 반응 선택 (두 번째)
if popup.reaction_list.count() >= 2:
    popup.reaction_list.setCurrentRow(1)

def capture():
    screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    pixmap = popup.grab()
    path = os.path.join(screenshot_dir, "pathway_ester_v1.png")
    pixmap.save(path)
    print(f"Screenshot saved: {path}")
    app.quit()

QTimer.singleShot(800, capture)
app.exec()
