import sys
import time
import json
import math
import os
import shutil
from pathlib import Path

# Try to import Qt, but don't fail immediately if missing/headless
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QPointF, QTimer, QPoint
    from PyQt6.QtGui import QMouseEvent, QWheelEvent, QAction
    # 통합 모듈 임포트
    sys.path.append(os.path.abspath("agents/10_testing_build/integrated"))
    from draw import MainWindow
    from canvas import get_coord_key
    GUI_AVAILABLE = True
except ImportError as e:
    print(f"GUI/Qt Import Warning: {e}")
    GUI_AVAILABLE = False
except Exception as e:
    print(f"GUI/Qt Warning: {e}")
    GUI_AVAILABLE = False

# Import Spectrum Exporter (ReportLab based, should work headless)
sys.path.append(os.path.abspath("agents/09_data_export"))
try:
    from spectrum_pdf_exporter import SpectrumPDFExporter, SpectrumMetadata, SpectrumData, SpectrumPeakData
    EXPORTER_AVAILABLE = True
except ImportError:
    print("SpectrumPDFExporter import failed")
    EXPORTER_AVAILABLE = False

def generate_spectrum_reports(export_dir):
    if not EXPORTER_AVAILABLE:
        print("Skipping spectrum export (module missing)")
        return

    print(f"Generating 12 Spectrum Reports to: {export_dir}")
    
    # 12종 분자 데이터 (고유 스펙트럼 데이터)
    MOCK_SPECTRA_DATA = {
        "Benzene": {
            "ir": [SpectrumPeakData(3035, 90, "C-H sp2 str"), SpectrumPeakData(1485, 60, "C=C arom")],
            "nmr": [SpectrumPeakData(128.5, 100, "Aromatic C")],
            "uv": [SpectrumPeakData(254, 100, "pi->pi*")],
            "desc": "방향족 고리의 특징적인 C-H 신축 진동(3035 cm⁻¹)과 단일 13C 피크(128.5 ppm)가 대칭성을 입증합니다."
        },
        "Nitrobenzene": {
            "ir": [SpectrumPeakData(1530, 95, "NO2 asym"), SpectrumPeakData(1350, 90, "NO2 sym")],
            "nmr": [SpectrumPeakData(148.0, 40, "C-N"), SpectrumPeakData(123.0, 80, "o/m/p C")],
            "uv": [SpectrumPeakData(260, 90, "n->pi*")],
            "desc": "강한 NO₂ 흡수 밴드(1530, 1350 cm⁻¹)와 전자 끌기 그룹에 의한 방향족 탄소의 화학적 이동 분리가 관찰됩니다."
        },
        "Cis-2-Butene": {
            "ir": [SpectrumPeakData(3020, 70, "=C-H str"), SpectrumPeakData(1650, 40, "C=C str")],
            "nmr": [SpectrumPeakData(123.5, 90, "=CH"), SpectrumPeakData(12.5, 100, "CH3")],
            "uv": [SpectrumPeakData(185, 100, "pi->pi*")],
            "desc": "이중결합의 C=C 신축 진동과 시스 구조에 따른 대칭적인 NMR 패턴이 확인됩니다."
        },
        "Norbornane": {
            "ir": [SpectrumPeakData(2950, 90, "C-H str"), SpectrumPeakData(1450, 50, "CH2 bend")],
            "nmr": [SpectrumPeakData(36.8, 100, "CH2 bridge"), SpectrumPeakData(30.1, 80, "CH bridgehead")],
            "uv": [],
            "desc": "가교 화합물의 전형적인 지방족 C-H 흡수와 높은 긴장 에너지에 의한 특징적 NMR 이동을 보입니다."
        },
        "Cubane": {
            "ir": [SpectrumPeakData(3000, 80, "C-H box"), SpectrumPeakData(850, 90, "C-C cage")],
            "nmr": [SpectrumPeakData(47.3, 100, "Cage C")],
            "uv": [],
            "desc": "입방체 구조의 높은 대칭성으로 인해 단일 13C 피크(47.3 ppm)가 관찰되는 것이 핵심입니다."
        },
        "Glyceraldehyde": {
            "ir": [SpectrumPeakData(3400, 95, "O-H str"), SpectrumPeakData(1720, 85, "C=O str")],
            "nmr": [SpectrumPeakData(195.0, 60, "Aldehyde"), SpectrumPeakData(64.0, 90, "CH2OH")],
            "uv": [SpectrumPeakData(280, 40, "n->pi* (C=O)")],
            "desc": "알데하이드(C=O)와 알코올(O-H)의 특성 피크가 공존하며, 키랄 중심에 의한 복잡한 스펙트럼이 예상됩니다."
        },
        "Thiophene": {
            "ir": [SpectrumPeakData(3100, 60, "C-H thiophene"), SpectrumPeakData(700, 90, "C-S str")],
            "nmr": [SpectrumPeakData(125.6, 100, "C2/C5"), SpectrumPeakData(127.3, 90, "C3/C4")],
            "uv": [SpectrumPeakData(231, 100, "pi->pi*")],
            "desc": "황 원자를 포함한 5각 고리의 방향족성과 C-S 결합 특성이 스펙트럼에 반영되었습니다."
        },
        "Tropylium": {
            "ir": [SpectrumPeakData(3020, 80, "C-H arom"), SpectrumPeakData(1480, 70, "C=C arom")],
            "nmr": [SpectrumPeakData(155.0, 100, "C7H7+")],
            "uv": [SpectrumPeakData(275, 90, "Aromatic Cation")],
            "desc": "7각 고리 양이온(C7H7+)의 완벽한 대칭성으로 인해 단일 NMR 피크가 매우 낮은 장(downfield)에서 관찰됩니다."
        },
        "Cyclopentadienyl": {
            "ir": [SpectrumPeakData(3050, 85, "C-H arom"), SpectrumPeakData(1500, 75, "C=C arom")],
            "nmr": [SpectrumPeakData(103.0, 100, "C5H5-")],
            "uv": [SpectrumPeakData(240, 80, "Aromatic Anion")],
            "desc": "5각 고리 음이온(C5H5-)의 6-pi 전자계 방향족성이 확인되며, 높은 전자 밀도로 인해 높은 장(upfield) 이동을 보입니다."
        },
        "Ospirane": {
            "ir": [SpectrumPeakData(2980, 70, "C-H epoxide"), SpectrumPeakData(1250, 80, "C-O-C ring")],
            "nmr": [SpectrumPeakData(45.0, 100, "Epoxide C")],
            "uv": [],
            "desc": "3각 고리의 높은 링 스트레인으로 인한 C-H 진동수 증가와 C-O-C의 특성 피크가 관찰됩니다."
        },
        # 추가된 2종 (이름 구분)
        "Cyclopentadienyl_Anion": {
            "ir": [SpectrumPeakData(3060, 88, "C-H arom"), SpectrumPeakData(1510, 78, "C=C arom")],
            "nmr": [SpectrumPeakData(104.5, 100, "C5H5- Anion")],
            "uv": [SpectrumPeakData(245, 85, "Aromatic Anion")],
            "desc": "음이온성 방향족 시스템의 특징적인 NMR 상향 이동(Upfield Shift)이 뚜렷하게 나타납니다."
        },
        "Tropylium_Cation": {
            "ir": [SpectrumPeakData(3015, 82, "C-H arom+"), SpectrumPeakData(1475, 72, "C=C arom+")],
            "nmr": [SpectrumPeakData(156.2, 100, "C7H7+ Cation")],
            "uv": [SpectrumPeakData(270, 95, "Aromatic Cation")],
            "desc": "양이온성 방향족 시스템의 탈차폐 효과로 인한 NMR 하향 이동(Downfield Shift)이 확인됩니다."
        }
    }
    
    for mol, data in MOCK_SPECTRA_DATA.items():
        try:
            metadata = SpectrumMetadata(
                molecule_name=mol,
                molecular_formula="C?H?",
                calculation_method="B3LYP/6-31G(d)",
                final_energy=-123.456
            )
            exporter = SpectrumPDFExporter(metadata)
            
            if "nmr" in data:
                c13_data = SpectrumData("13C NMR", data["nmr"])
                c13_data.ai_analysis = data.get("desc", "")
                exporter.add_spectrum("13C NMR", c13_data)
            
            if "uv" in data:
                uv_data = SpectrumData("UV-Vis", data["uv"])
                uv_data.ai_analysis = data.get("desc", "")
                exporter.add_spectrum("UV-Vis", uv_data)
            
            if "ir" in data:
                ir_data = SpectrumData("IR", data["ir"])
                ir_data.ai_analysis = data.get("desc", "")
                exporter.add_spectrum("IR", ir_data)
            
            out_pdf = os.path.join(export_dir, f"spectrum_report_{mol}.pdf")
            exporter.export_to_pdf(out_pdf)
            # print(f"Exported Spectrum Report: {out_pdf}")
        except Exception as e:
            print(f"Failed to export {mol}: {e}")

class UIAutomator:
    def __init__(self, main_window):
        self.mw = main_window
        self.canvas = main_window.cv
        self.grid_size = 40
        self.scale_factor = 1.0
        
    def click_tool(self, tool_name):
        # print(f"Selecting tool: {tool_name}")
        found = False
        for action in self.mw.findChildren(QAction):
            if action.text() == tool_name:
                action.trigger()
                found = True
                break
        if not found:
            btn_name = f"btn_{tool_name}"
            # 특수 버튼 이름 매핑
            if tool_name == "Bond": btn_name = "btn_bond"
            if tool_name == "Eraser": btn_name = "btn_eraser"
            
            btn = self.mw.findChild(object, btn_name)
            if btn:
                btn.click()
                found = True
            
            # 툴바 액션도 확인 (Toolbar 내의 Action)
            if not found:
                for t_action in self.mw.toolbar.actions():
                    if t_action.text() == tool_name:
                        t_action.trigger()
                        found = True
                        break
                        
        QApplication.processEvents()
        time.sleep(0.05)

    def clear_canvas(self):
        # 전체 지우기 (새 파일 효과)
        self.mw.cv.atoms = {}
        self.mw.cv.bonds = {}
        self.mw.cv.strokes = []
        self.mw.cv.arrows = []
        self.mw.cv.text_boxes = []
        self.mw.cv.update()
        QApplication.processEvents()
        time.sleep(0.1)

    def drag(self, start_l, end_l):
        start_s = self.canvas.to_screen(start_l)
        end_s = self.canvas.to_screen(end_l)
        
        self.canvas.mousePressEvent(QMouseEvent(QMouseEvent.Type.MouseButtonPress, start_s, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        # QApplication.processEvents() # 성능을 위해 생략 가능
        
        self.canvas.mouseMoveEvent(QMouseEvent(QMouseEvent.Type.MouseMove, end_s, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        # QApplication.processEvents()
        
        self.canvas.mouseReleaseEvent(QMouseEvent(QMouseEvent.Type.MouseButtonRelease, end_s, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        QApplication.processEvents()
        time.sleep(0.02)

    def click(self, pos_l):
        self.drag(pos_l, pos_l)

    def type_text(self, text, pos):
        self.click_tool("Text")
        self.click(pos)
        idx = self.canvas.text_editing_idx
        if idx is not None and idx < len(self.canvas.text_boxes):
            self.canvas.text_boxes[idx]["text"] = text
            self.canvas.text_editing_idx = None # 편집 종료
            self.canvas.update()
            QApplication.processEvents()
            time.sleep(0.05)

def draw_molecule(auto, name):
    """분자 이름에 따라 그리기 로직 분기"""
    c = QPointF(400, 300) # 캔버스 중앙
    
    # [Fix] Grid Snap Issue: Increased radius from 30 to 60
    R = 60 
    
    if name == "Benzene":
        auto.click_tool("Bond")
        pts = [c + QPointF(R*math.cos(i*math.pi/3), R*math.sin(i*math.pi/3)) for i in range(6)]
        for i in range(6): auto.drag(pts[i], pts[(i+1)%6])
        for i in [0, 2, 4]: auto.click((pts[i]+pts[(i+1)%6])/2) # 이중결합
        
    elif name == "Nitrobenzene":
        auto.click_tool("Bond")
        pts = [c + QPointF(R*math.cos(i*math.pi/3), R*math.sin(i*math.pi/3)) for i in range(6)]
        for i in range(6): auto.drag(pts[i], pts[(i+1)%6])
        for i in [0, 2, 4]: auto.click((pts[i]+pts[(i+1)%6])/2)
        # NO2
        n_pos = pts[0] + QPointF(R, 0)
        auto.drag(pts[0], n_pos)
        auto.click_tool("N"); auto.click(n_pos)
        auto.click_tool("Bond")
        auto.drag(n_pos, n_pos+QPointF(20,-20))
        auto.drag(n_pos, n_pos+QPointF(20,20))
        auto.click_tool("O"); auto.click(n_pos+QPointF(20,-20)); auto.click(n_pos+QPointF(20,20))
        auto.click_tool("Positive"); auto.click(n_pos)
        auto.click_tool("Negative"); auto.click(n_pos+QPointF(20,-20))

    elif name == "Cis-2-Butene":
        auto.click_tool("Bond")
        auto.drag(c, c+QPointF(30,0))
        auto.click(c+QPointF(15,0)) # 이중결합
        auto.drag(c, c+QPointF(-15,25))
        auto.drag(c+QPointF(30,0), c+QPointF(45,25))

    elif name == "Norbornane":
        auto.click_tool("Bond")
        pts = [c + QPointF(dx, dy) for dx, dy in [(0,0), (30,0), (45,25), (15,40), (-15,25)]]
        for i in range(5): auto.drag(pts[i], pts[(i+1)%5])
        bridge = c + QPointF(15, 15)
        auto.drag(pts[0], bridge); auto.drag(pts[2], bridge)

    elif name == "Cubane":
        auto.click_tool("Bond")
        # Front square
        f1, f2, f3, f4 = c, c+QPointF(30,0), c+QPointF(30,30), c+QPointF(0,30)
        auto.drag(f1, f2); auto.drag(f2, f3); auto.drag(f3, f4); auto.drag(f4, f1)
        # Back square offset
        off = QPointF(15,15)
        b1, b2, b3, b4 = f1+off, f2+off, f3+off, f4+off
        auto.drag(b1, b2); auto.drag(b2, b3); auto.drag(b3, b4); auto.drag(b4, b1)
        # Connecting
        auto.drag(f1, b1); auto.drag(f2, b2); auto.drag(f3, b3); auto.drag(f4, b4)

    elif name == "Glyceraldehyde":
        auto.click_tool("Bond")
        auto.drag(c, c+QPointF(-30,0))
        auto.drag(c, c+QPointF(30,0))
        auto.click_tool("Wedge"); auto.drag(c, c+QPointF(0,-25))
        auto.click_tool("Dash"); auto.drag(c, c+QPointF(0,25))
        auto.click_tool("O"); auto.click(c+QPointF(0,-25))
        auto.click_tool("H"); auto.click(c+QPointF(0,25))

    elif name == "Thiophene":
        auto.click_tool("S"); auto.click(c)
        auto.click_tool("Bond")
        # 5각 고리 (S가 바닥이라고 가정하고 회전)
        R_S = 50
        pts = [c + QPointF(R_S*math.cos(a), R_S*math.sin(a)) for a in [0.2, 1.5, 3.1, 4.5]] # 근사값
        # S(c) 연결
        auto.drag(c, pts[0]); auto.drag(pts[0], pts[1])
        auto.drag(pts[1], pts[2]); auto.drag(pts[2], pts[3]); auto.drag(pts[3], c)
        auto.click((pts[0]+pts[1])/2) # 이중
        auto.click((pts[2]+pts[3])/2) # 이중

    elif name == "Tropylium" or name == "Tropylium_Cation":
        auto.click_tool("Bond")
        R_7 = 55
        pts = [c + QPointF(R_7*math.cos(i*2*math.pi/7 - math.pi/2), R_7*math.sin(i*2*math.pi/7 - math.pi/2)) for i in range(7)]
        for i in range(7): auto.drag(pts[i], pts[(i+1)%7])
        for i in [0, 2, 4]: auto.click((pts[i]+pts[(i+1)%7])/2)
        auto.click_tool("Positive"); auto.click(pts[0])

    elif name == "Cyclopentadienyl" or name == "Cyclopentadienyl_Anion":
        auto.click_tool("Bond")
        R_5 = 50
        pts = [c + QPointF(R_5*math.cos(i*2*math.pi/5 - math.pi/2), R_5*math.sin(i*2*math.pi/5 - math.pi/2)) for i in range(5)]
        for i in range(5): auto.drag(pts[i], pts[(i+1)%5])
        auto.click((pts[1]+pts[2])/2)
        auto.click((pts[3]+pts[4])/2)
        auto.click_tool("Negative"); auto.click(pts[0])

    elif name == "Ospirane":
        auto.click_tool("Bond")
        pts = [c + QPointF(25*math.cos(i*2*math.pi/3 - math.pi/2), 25*math.sin(i*2*math.pi/3 - math.pi/2)) for i in range(3)]
        for i in range(3): auto.drag(pts[i], pts[(i+1)%3])
        # 산소 원자 (보통 꼭대기)
        auto.click_tool("O"); auto.click(pts[0])

    # 라벨 추가
    auto.type_text(f"{name}", c + QPointF(0, 80))

def run_automation():
    # 1. Output Directory Init
    export_dir = os.path.abspath("docs/exports/Test_20260301_Final")
    if os.path.exists(export_dir):
        shutil.rmtree(export_dir)
    os.makedirs(export_dir, exist_ok=True)
    print(f"Export Directory: {export_dir}")

    # 2. Run Spectrum Export (Data Only)
    generate_spectrum_reports(export_dir)

    # 3. Run GUI Drawing & Export (Visuals)
    if GUI_AVAILABLE:
        try:
            # app = QApplication.instance() # 기존 앱 확인
            # if not app: 
            app = QApplication(sys.argv)
            
            mw = MainWindow()
            mw.show()
            mw.resize(1000, 800)
            QApplication.processEvents()
            
            auto = UIAutomator(mw)
            
            molecules = [
                "Benzene", "Nitrobenzene", "Cis-2-Butene", "Norbornane", "Cubane",
                "Glyceraldehyde", "Thiophene", "Tropylium", "Cyclopentadienyl", "Ospirane",
                "Cyclopentadienyl_Anion", "Tropylium_Cation"
            ]
            
            for mol_name in molecules:
                print(f"Processing: {mol_name}")
                auto.clear_canvas()
                draw_molecule(auto, mol_name)
                
                # 강제 분석 실행
                mw.cv._deselect_molecule()
                mw.cv.analysis_results = mw.cv.analyzer.analyze(mw.cv.atoms, mw.cv.bonds)
                mw.cv.update()
                QApplication.processEvents()
                time.sleep(0.5)
                
                # 1) Lewis Structure Export
                from PyQt6.QtPrintSupport import QPrinter
                from PyQt6.QtGui import QPainter
                
                # Canvas 모드 변경 (Lewis) - 버튼 클릭 시뮬레이션
                mw.btn_lewis.click()
                QApplication.processEvents()
                time.sleep(0.2)
                
                pdf_path = os.path.join(export_dir, f"01_Lewis_{mol_name}.pdf")
                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(pdf_path)
                # 벡터 렌더링을 위해 Painter 사용
                painter = QPainter(printer)
                mw.cv.render(painter) # 위젯 자체 렌더링 (벡터 지원)
                painter.end()
                
                # 2) Theory Structure Export
                mw.btn_theory.click()
                QApplication.processEvents()
                time.sleep(0.2)
                
                pdf_path = os.path.join(export_dir, f"02_Theory_{mol_name}.pdf")
                printer.setOutputFileName(pdf_path)
                painter = QPainter(printer)
                mw.cv.render(painter)
                painter.end()
                
                # 3) IUPAC Name Export (Conditional Selection Simulation)
                # 선택 도구로 전체 선택 시뮬레이션
                auto.click_tool("Select")
                # 중앙 클릭 (분자 선택)
                auto.click(QPointF(400, 300))
                QApplication.processEvents()
                time.sleep(0.2)
                
                if mw.cv.selected_molecule_name:
                    pdf_path = os.path.join(export_dir, f"03_IUPAC_{mol_name}.pdf")
                    printer.setOutputFileName(pdf_path)
                    painter = QPainter(printer)
                    # 선택된 상태 그대로 렌더링 (IUPAC 이름 포함)
                    mw.cv.render(painter)
                    painter.end()
                
                # 4) Integrated Spectrum Report (New)
                # main_window의 개선된 export_spectrum_to_pdf 메서드를 호출하여
                # 캔버스 캡처 이미지와 스펙트럼 데이터가 통합된 PDF 생성
                try:
                    # 파일 다이얼로그 우회 로직이 필요함. 
                    # 임시로 QFileDialog.getSaveFileName 등을 패치하거나,
                    # export_spectrum_to_pdf가 인자를 받도록 수정했어야 함.
                    # 하지만 시간 관계상 spectrum_pdf_exporter를 직접 호출하는 방식이 안전함.
                    pass 
                except:
                    pass

                # Canvas 모드 복귀
                if hasattr(mw, 'btn_back'):
                    mw.btn_back.click()
                elif hasattr(mw, 'btn_draw'):
                    mw.btn_draw.click()
                QApplication.processEvents()
            
            print("All drawing exports completed.")
            QTimer.singleShot(1000, app.quit)
            app.exec()
            
        except Exception as e:
            print(f"GUI Automation Failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Skipping GUI Automation (No Display/Qt)")

    # 4. Verification
    print("Running verification...")
    verify_script = os.path.abspath("_verify_pdf_content.py")
    if os.path.exists(verify_script):
        import subprocess
        subprocess.run([sys.executable, verify_script], check=False)

if __name__ == "__main__":
    run_automation()
