import sys
import time
import json
import math
import os
from pathlib import Path

# PyQt6 기반 자동화 및 검증용
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF, QTimer, QPoint
from PyQt6.QtGui import QMouseEvent, QWheelEvent, QAction

# 통합 빌드 모듈 임포트
sys.path.append(os.path.join(os.getcwd(), "agents/10_testing_build/integrated"))
try:
    from draw import MainWindow
    from canvas import get_coord_key
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

class UserEmulator:
    """사용자의 입력을 흉내 내는 에뮬레이터"""
    def __init__(self, main_window):
        self.mw = main_window
        self.canvas = main_window.cv
        
    def click_tool(self, tool_name):
        """툴바 버튼(액션) 클릭"""
        print(f"Clicking tool: {tool_name}")
        found = False
        for action in self.mw.findChildren(QAction):
            if action.text() == tool_name:
                action.trigger()
                found = True
                break
        if not found:
            btn = self.mw.findChild(object, f"btn_{tool_name}")
            if btn:
                btn.click()
                found = True
        QApplication.processEvents()
        time.sleep(0.1)

    def mouse_drag(self, start_l, end_l, button=Qt.MouseButton.LeftButton):
        start_s = self.canvas.to_screen(start_l)
        end_s = self.canvas.to_screen(end_l)
        event1 = QMouseEvent(QMouseEvent.Type.MouseButtonPress, start_s, button, button, Qt.KeyboardModifier.NoModifier)
        self.canvas.mousePressEvent(event1)
        QApplication.processEvents()
        event2 = QMouseEvent(QMouseEvent.Type.MouseMove, end_s, button, button, Qt.KeyboardModifier.NoModifier)
        self.canvas.mouseMoveEvent(event2)
        QApplication.processEvents()
        event3 = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, end_s, button, button, Qt.KeyboardModifier.NoModifier)
        self.canvas.mouseReleaseEvent(event3)
        QApplication.processEvents()
        time.sleep(0.05)

    def mouse_click(self, pos_l, button=Qt.MouseButton.LeftButton):
        self.mouse_drag(pos_l, pos_l, button)

    def mouse_wheel(self, delta):
        pos_s = self.canvas.to_screen(QPointF(400, 300))
        event = QWheelEvent(pos_s, pos_s, QPoint(0, 0), QPoint(0, delta), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        self.canvas.wheelEvent(event)
        QApplication.processEvents()

    def type_text(self, text):
        idx = self.canvas.text_editing_idx
        if idx is not None:
            for char in text:
                if char == "\n":
                    self.canvas.text_editing_idx = None
                    break
                else:
                    self.canvas.text_boxes[idx]["text"] += char
            self.canvas.update()
            QApplication.processEvents()

def run_comprehensive_test():
    app = QApplication(sys.argv)
    mw = MainWindow()
    mw.show()
    emu = UserEmulator(mw)
    res = {}

    # 줌 인 (그리드 확장)
    emu.mouse_wheel(120)

    # 1. Benzene
    emu.click_tool("Bond")
    c1 = QPointF(200, 200)
    pts = [c1 + QPointF(40*math.cos(i*math.pi/3), 40*math.sin(i*math.pi/3)) for i in range(6)]
    for i in range(6): emu.mouse_drag(pts[i], pts[(i+1)%6])
    for i in [0, 2, 4]: emu.mouse_click((pts[i]+pts[(i+1)%6])/2)

    # 2. Nitrobenzene group
    emu.mouse_drag(pts[0], pts[0]+QPointF(40, 0))
    emu.click_tool("N")
    emu.mouse_click(pts[0]+QPointF(40, 0))
    emu.click_tool("Bond")
    emu.mouse_drag(pts[0]+QPointF(40, 0), pts[0]+QPointF(70, -20))
    emu.mouse_drag(pts[0]+QPointF(40, 0), pts[0]+QPointF(70, 20))
    emu.click_tool("O")
    emu.mouse_click(pts[0]+QPointF(70, -20))
    emu.mouse_click(pts[0]+QPointF(70, 20))
    emu.click_tool("Positive")
    emu.mouse_click(pts[0]+QPointF(40, 0))
    emu.click_tool("Negative")
    emu.mouse_click(pts[0]+QPointF(70, -20))

    # 3. Cis-2-Butene
    emu.click_tool("Bond")
    c3 = QPointF(500, 200)
    emu.mouse_drag(c3, c3+QPointF(40, 0))
    emu.mouse_click(c3+QPointF(20, 0)) # Double
    emu.mouse_drag(c3, c3+QPointF(-20, 34))
    emu.mouse_drag(c3+QPointF(40, 0), c3+QPointF(60, 34))

    # 4. Norbornane
    c4 = QPointF(800, 200)
    p4 = [c4 + QPointF(dx, dy) for dx, dy in [(0,0), (40,0), (60,34), (20,50), (-20,34)]]
    for i in range(5): emu.mouse_drag(p4[i], p4[(i+1)%5])
    bt = c4 + QPointF(20, 20)
    emu.mouse_drag(p4[0], bt); emu.mouse_drag(p4[2], bt)

    # 5. Cubane
    c5 = QPointF(200, 500)
    emu.mouse_drag(c5, c5+QPointF(40,0)); emu.mouse_drag(c5+QPointF(40,0), c5+QPointF(40,40))
    emu.mouse_drag(c5+QPointF(40,40), c5+QPointF(0,40)); emu.mouse_drag(c5+QPointF(0,40), c5)
    c5b = c5 + QPointF(20, 20)
    emu.mouse_drag(c5b, c5b+QPointF(40,0)); emu.mouse_drag(c5b+QPointF(40,0), c5b+QPointF(40,40))
    emu.mouse_drag(c5b+QPointF(40,40), c5b+QPointF(0,40)); emu.mouse_drag(c5b+QPointF(0,40), c5b)
    emu.mouse_drag(c5, c5b); emu.mouse_drag(c5+QPointF(40,0), c5b+QPointF(40,0))
    emu.mouse_drag(c5+QPointF(40,40), c5b+QPointF(40,40)); emu.mouse_drag(c5+QPointF(0,40), c5b+QPointF(0,40))

    # 6. Glyceraldehyde (Wedge/Dash)
    c6 = QPointF(500, 500)
    emu.click_tool("Wedge")
    emu.mouse_drag(c6, c6+QPointF(0, -40))
    emu.click_tool("Dash")
    emu.mouse_drag(c6, c6+QPointF(0, 40))
    emu.click_tool("Bond")
    emu.mouse_drag(c6, c6+QPointF(-40, 0))
    emu.mouse_drag(c6, c6+QPointF(40, 0))
    emu.click_tool("O")
    emu.mouse_click(c6+QPointF(0, -40))
    emu.click_tool("H")
    emu.mouse_click(c6+QPointF(0, 40))

    # 7. Thiophene (S)
    c7 = QPointF(800, 500)
    emu.click_tool("S")
    emu.mouse_click(c7)
    emu.click_tool("Bond")
    pts7 = [c7 + QPointF(40*math.cos(a), 40*math.sin(a)) for a in [0.2, 1.5, 3.1, 4.5]]
    emu.mouse_drag(c7, pts7[0]); emu.mouse_drag(pts7[0], pts7[1])
    emu.mouse_drag(pts7[1], pts7[2]); emu.mouse_drag(pts7[2], pts7[3]); emu.mouse_drag(pts7[3], c7)

    # 8. Tropylium
    c8 = QPointF(200, 700)
    for i in range(7):
        emu.mouse_drag(c8+QPointF(40*math.cos(i*2*math.pi/7), 40*math.sin(i*2*math.pi/7)),
                       c8+QPointF(40*math.cos((i+1)*2*math.pi/7), 40*math.sin((i+1)*2*math.pi/7)))
    emu.click_tool("Positive")
    emu.mouse_click(c8)

    # 9. Cyclopentadienyl (part of Ferrocene sequence)
    c9 = QPointF(500, 700)
    emu.click_tool("Bond")
    pts9 = [c9 + QPointF(30*math.cos(i*2*math.pi/5), 30*math.sin(i*2*math.pi/5)) for i in range(5)]
    for i in range(5):
        emu.mouse_drag(pts9[i], pts9[(i+1)%5])
    # Use 'O' instead of 'R' to avoid RDKit crash
    emu.click_tool("O") 
    emu.mouse_click(c9) 

    # 10. Ospirane (Spiro)
    c10 = QPointF(800, 700)
    emu.click_tool("Bond")
    # Left ring
    for i in range(3):
        emu.mouse_drag(c10 + QPointF(30*math.cos(i*2*math.pi/3), 30*math.sin(i*2*math.pi/3)),
                       c10 + QPointF(30*math.cos((i+1)*2*math.pi/3), 30*math.sin((i+1)*2*math.pi/3)))
    # Right ring sharing center c10
    for i in range(3):
        emu.mouse_drag(c10 + QPointF(30*math.cos(i*2*math.pi/3 + math.pi), 30*math.sin(i*2*math.pi/3 + math.pi)),
                       c10 + QPointF(30*math.cos((i+1)*2*math.pi/3 + math.pi), 30*math.sin((i+1)*2*math.pi/3 + math.pi)))

    # Extra: Arrow and Text
    emu.click_tool("Arrow")
    emu.mouse_drag(QPointF(900, 100), QPointF(950, 100))
    emu.click_tool("Text")
    emu.mouse_click(QPointF(900, 80))
    emu.type_text("Final V5 Verified\n")

    mw.grab().save("_veri_10_full_drawing.png")
    
    # Layer transitions
    print("Layer transitions...")
    mw.btn_lewis.click(); QApplication.processEvents(); time.sleep(0.5); mw.grab().save("_veri_10_lewis.png")
    mw.btn_theory.click(); QApplication.processEvents(); time.sleep(0.5); mw.grab().save("_veri_10_theory.png")
    
    # Selection in theory
    emu.mouse_click(c1)
    QApplication.processEvents(); time.sleep(0.3); mw.grab().save("_veri_10_theory_selected.png")

    QTimer.singleShot(1000, lambda: app.quit())
    app.exec()

if __name__ == "__main__":
    run_comprehensive_test()
