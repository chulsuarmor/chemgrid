"""
Test: ReactionPathwayWidget 교과서 스타일 전체 경로 표시 확인
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

# 반응 경로 선택 (첫 번째)
if popup.reaction_list.count() > 0:
    popup.reaction_list.setCurrentRow(0)

def capture():
    screenshot_dir = os.path.join(os.path.dirname(__file__), "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)

    pixmap = popup.grab()
    path = os.path.join(screenshot_dir, "pathway_textbook_v1.png")
    pixmap.save(path)
    print(f"Screenshot saved: {path}")

    # 반응 목록 정보 출력
    n = popup.reaction_list.count()
    print(f"Detected reactions: {n}")
    for i in range(n):
        print(f"  [{i}] {popup.reaction_list.item(i).text()}")

    app.quit()

QTimer.singleShot(800, capture)
app.exec()
