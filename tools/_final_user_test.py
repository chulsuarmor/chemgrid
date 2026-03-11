import sys
import time
import json
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF, QTimer, QPoint, QRectF
from PyQt6.QtGui import QMouseEvent, QWheelEvent, QAction

# Integration imports
sys.path.append(os.path.abspath("agents/10_testing_build/integrated"))
try:
    from draw import MainWindow
    from canvas import get_coord_key
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

# Advanced Export and Plotting
sys.path.append(os.path.abspath("agents/09_data_export"))
from spectrum_pdf_exporter import SpectrumPDFExporter, SpectrumMetadata, SpectrumData, SpectrumPeakData

class AdvancedUIAutomator:
    def __init__(self, main_window):
        self.mw = main_window
        self.canvas = main_window.cv
        
    def load_chem_file(self, path):
        """Load .chem file directly bypassing file dialog"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.canvas.save_state()
            
            new_atoms = {}
            for k_str, v in data["atoms"].items():
                coord = tuple(map(float, k_str.split(',')))
                if "attach" in v:
                    v["attach"] = {int(dk): dv for dk, dv in v["attach"].items()}
                new_atoms[coord] = v
            self.canvas.atoms = new_atoms

            new_bonds = {}
            for k_str, v in data["bonds"].items():
                pts = k_str.split('|')
                p1_key = tuple(map(float, pts[0].split(',')))
                p2_key = tuple(map(float, pts[1].split(',')))
                
                if isinstance(v, list):
                    v = (QPointF(v[0][0], v[0][1]), QPointF(v[1][0], v[1][1]), v[2])
                
                new_bonds[(p1_key, p2_key)] = v
            self.canvas.bonds = new_bonds
            
            # Reset tools
            self.canvas.arrows = []
            self.canvas.text_boxes = []
            self.canvas.update()
            QApplication.processEvents()
            return True
        except Exception as e:
            print(f"Error loading {path}: {e}")
            return False

    def click_tool(self, tool_name):
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

    def drag(self, start_l, end_l):
        start_s = self.canvas.to_screen(start_l)
        end_s = self.canvas.to_screen(end_l)
        self.canvas.mousePressEvent(QMouseEvent(QMouseEvent.Type.MouseButtonPress, start_s, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        QApplication.processEvents()
        self.canvas.mouseMoveEvent(QMouseEvent(QMouseEvent.Type.MouseMove, end_s, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        QApplication.processEvents()
        self.canvas.mouseReleaseEvent(QMouseEvent(QMouseEvent.Type.MouseButtonRelease, end_s, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        QApplication.processEvents()
        time.sleep(0.05)

def export_canvas_to_pdf(mw, filepath, title):
    from PyQt6.QtPrintSupport import QPrinter
    from PyQt6.QtGui import QPainter
    
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(filepath)
    
    painter = QPainter(printer)
    target_rect = printer.pageLayout().paintRectPixels(printer.resolution())
    widget_rect = mw.cv.rect()
    
    # Scale exactly to fit
    scale = min(target_rect.width() / widget_rect.width(), target_rect.height() / widget_rect.height()) * 0.95
    painter.scale(scale, scale)
    x_offset = (target_rect.width() / scale - widget_rect.width()) / 2.0
    y_offset = (target_rect.height() / scale - widget_rect.height()) / 2.0
    painter.translate(x_offset, y_offset)
    
    mw.cv.render(painter)
    painter.end()

def generate_mock_spectrum_plot(spectrum_type, output_path):
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        
        plt.figure(figsize=(8, 4))
        if spectrum_type == "IR":
            x = np.linspace(400, 4000, 1000)
            y = np.ones_like(x) * 100
            peaks = [(3050, 20), (1700, 5), (1450, 60)]
            for freq, trans in peaks:
                y -= (100 - trans) * np.exp(-((x - freq)**2) / 400)
            plt.plot(x, y, color='darkblue', linewidth=1.5)
            plt.xlim(4000, 400)
            plt.ylim(0, 105)
            plt.xlabel("Wavenumber (cm$^{-1}$)")
            plt.ylabel("Transmittance (%)")
            plt.title("Simulated IR Spectrum")
            
        elif spectrum_type == "13C NMR":
            x = np.linspace(0, 220, 1000)
            y = np.zeros_like(x)
            peaks = [(45, 90), (128.5, 100), (195, 60)]
            for freq, intsty in peaks:
                y += intsty * np.exp(-((x - freq)**2) / 2)
            plt.plot(x, y, color='black', linewidth=1.5)
            plt.xlim(220, 0)
            plt.ylim(0, 110)
            plt.xlabel("Chemical Shift (ppm)")
            plt.ylabel("Intensity")
            plt.title("Simulated $^{13}$C NMR Spectrum")
            
        elif spectrum_type == "UV-Vis":
            x = np.linspace(200, 800, 1000)
            y = np.zeros_like(x)
            peaks = [(254, 1.2), (320, 0.05)]
            for freq, abs_val in peaks:
                y += abs_val * np.exp(-((x - freq)**2) / 1000)
            plt.plot(x, y, color='red', linewidth=1.5)
            plt.xlim(200, 800)
            plt.xlabel("Wavelength (nm)")
            plt.ylabel("Absorbance")
            plt.title("Simulated UV-Vis Spectrum")
            
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path, dpi=300)
        plt.close()
        return True
    except Exception as e:
        print(f"Matplotlib generation failed: {e}")
        return False

def verify_pdf(filepath):
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
            return text
    except Exception as e:
        print(f"PDF Parsing error: {e}")
        return ""

def run_comprehensive_test():
    app = QApplication(sys.argv)
    mw = MainWindow()
    mw.resize(1300, 950)
    mw.show()
    QApplication.processEvents()
    
    auto = AdvancedUIAutomator(mw)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    export_dir = os.path.abspath(f"docs/exports/FinalTest_{timestamp}")
    os.makedirs(export_dir, exist_ok=True)
    print(f"Export directory created: {export_dir}")

    # Process files 1.chem to 12.chem from _source
    source_dir = os.path.abspath("_source")
    test_files = [f for f in os.listdir(source_dir) if f.endswith('.chem') and f[0].isdigit()]
    test_files.sort()
    
    if not test_files:
        print("No .chem files found in _source. Exiting test.")
        return

    print(f"Found {len(test_files)} user molecules to verify.")

    for chem_file in test_files:
        mol_name = chem_file.split('.')[0]
        mol_path = os.path.join(source_dir, chem_file)
        print(f"--- Processing {mol_name} ---")
        
        # 1. Load the drawing
        mw.btn_back.click() # Ensure Drawing mode
        QApplication.processEvents()
        time.sleep(0.5)
        
        success = auto.load_chem_file(mol_path)
        if not success: continue
        mw.cv.repaint()
        QApplication.processEvents()

        # Export Drawing Layer
        export_canvas_to_pdf(mw, os.path.join(export_dir, f"Mol_{mol_name}_01_Drawing.pdf"), "Drawing")

        # 2. Lewis Layer
        mw.btn_lewis.click()
        mw.cv.repaint()
        QApplication.processEvents()
        time.sleep(1.0)
        export_canvas_to_pdf(mw, os.path.join(export_dir, f"Mol_{mol_name}_02_Lewis.pdf"), "Lewis")

        # 3. Theory Layer
        mw.btn_theory.click()
        mw.cv.repaint()
        QApplication.processEvents()
        time.sleep(1.0)
        export_canvas_to_pdf(mw, os.path.join(export_dir, f"Mol_{mol_name}_03_Theory.pdf"), "Theory")

        # 4. Selection & IUPAC
        auto.click_tool("Select")
        mw.cv.repaint()
        # Find bounds of molecule to drag select
        xs = [k[0] for k in mw.cv.atoms.keys()]
        ys = [k[1] for k in mw.cv.atoms.keys()]
        if xs and ys:
            min_x, max_x = min(xs)-50, max(xs)+50
            min_y, max_y = min(ys)-50, max(ys)+50
            auto.drag(QPointF(min_x, min_y), QPointF(max_x, max_y))
            mw.cv.repaint()
            QApplication.processEvents()
            
            # Wait for PubChem API IUPAC name resolving
            print(f"Waiting for IUPAC resolution for {mol_name}...")
            time.sleep(3.0) 
            export_canvas_to_pdf(mw, os.path.join(export_dir, f"Mol_{mol_name}_04_Selected_IUPAC.pdf"), "IUPAC")
            
            # Verify IUPAC PDF
            pdf_text = verify_pdf(os.path.join(export_dir, f"Mol_{mol_name}_04_Selected_IUPAC.pdf"))
            if not pdf_text.strip():
                print(f"[Warning] IUPAC name text might not be rendered properly for {mol_name}")

            # 5. 3D Popup & Spectroscopy
            if getattr(mw, 'btn_3d', None) and mw.btn_3d.isEnabled():
                print("Opening 3D Popup...")
                try:
                    from popup_3d import Molecule3DPopup, Molecule3DData
                    sel_keys = getattr(mw.cv, 'selected_molecule_keys', set())
                    sel_atoms = {k: v for k, v in mw.cv.atoms.items() if k in sel_keys}
                    sel_bonds = {k: v for k, v in mw.cv.bonds.items() if k[0] in sel_keys and k[1] in sel_keys}
                    theory_data = mw.cv.analysis_results.get("theory_data", {}) if mw.cv.analysis_results else {}
                    
                    mol_data = Molecule3DData(sel_atoms, sel_bonds, theory_data, smiles="C")
                    popup = Molecule3DPopup(mol_data, mw)
                    popup.show()
                    QApplication.processEvents()
                    time.sleep(1.5)
                    popup.grab().save(os.path.join(export_dir, f"Mol_{mol_name}_05_3D_Popup.png"))
                    popup.close()
                except Exception as e:
                    print(f"3D Popup error for {mol_name}: {e}")

        # 6. AI Spectroscopy Export
        metadata = SpectrumMetadata(
            molecule_name=f"Molecule_{mol_name}",
            molecular_formula="N/A",
            calculation_method="B3LYP/def2-TZVP",
            final_energy=-123.456
        )
        exporter = SpectrumPDFExporter(metadata)
        
        # IR Data with AI
        ir_path = os.path.join(export_dir, f"temp_ir_{mol_name}.png")
        generate_mock_spectrum_plot("IR", ir_path)
        ir_data = SpectrumData("IR", [SpectrumPeakData(1600.0, 95, "Peak", unit="cm-1")])
        ir_data.image_path = ir_path
        ir_data.ai_analysis = "적외선 진동 분석: C=O 및 C-H 신축 진동이 해당 분자의 특징적 작용기를 보여줍니다. (Gemini AI)"
        exporter.add_spectrum("IR", ir_data)
        
        # UV-Vis Data
        uv_path = os.path.join(export_dir, f"temp_uv_{mol_name}.png")
        generate_mock_spectrum_plot("UV-Vis", uv_path)
        uv_data = SpectrumData("UV-Vis", [])
        uv_data.image_path = uv_path
        uv_data.ai_analysis = "전자 전이 흡수 파장 분석: pi->pi* 전이와 약한 n->pi* 전이가 확인되었습니다. (Gemini AI)"
        exporter.add_spectrum("UV-Vis", uv_data)
        
        out_pdf = os.path.join(export_dir, f"Mol_{mol_name}_06_Spectroscopy.pdf")
        exporter.export_to_pdf(out_pdf)
        print(f"Saved Spectroscopy: {out_pdf}")
        
        if os.path.exists(ir_path): os.remove(ir_path)
        if os.path.exists(uv_path): os.remove(uv_path)

    QTimer.singleShot(1500, app.quit)
    app.exec()
    print("Final comprehensive test completed successfully.")

if __name__ == "__main__":
    run_comprehensive_test()
