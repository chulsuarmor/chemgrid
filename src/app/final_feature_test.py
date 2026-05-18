#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ChemGrid Comprehensive Foreground Feature Test
Tests all major features with screenshot capture.
Run from src/app/ directory with chemgrid conda env.
"""

import sys
import os
import time
import traceback
import logging

# Force offscreen rendering for automated test
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Setup path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
PROJECT_ROOT = os.path.abspath(os.path.join(APP_DIR, "..", ".."))

# Screenshot output directory
SCREENSHOT_DIR = os.path.join(PROJECT_ROOT, "departments", "archive", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("final_feature_test")

# Fix cp949 encoding on Windows console
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── Results tracking ──
results = {}

def _safe_str(s):
    """Remove emojis and problematic unicode for safe printing."""
    import re
    # Remove emoji/symbol chars that cp949 can't handle
    return re.sub(r'[\U00010000-\U0010ffff]', '', str(s))

def save_screenshot(widget, name):
    """Save widget screenshot to SCREENSHOT_DIR."""
    path = os.path.join(SCREENSHOT_DIR, f"final_test_{name}.png")
    try:
        from PyQt6.QtWidgets import QApplication
        widget.setAttribute(
            __import__('PyQt6.QtCore', fromlist=['Qt']).Qt.WidgetAttribute.WA_DontShowOnScreen,
            True
        )
        widget.show()
        QApplication.processEvents()
        # Force layout
        widget.adjustSize()
        QApplication.processEvents()
        time.sleep(0.3)
        QApplication.processEvents()

        pixmap = widget.grab()
        if pixmap.isNull() or pixmap.width() < 10:
            logger.warning(f"Screenshot {name}: pixmap too small or null")
            return None
        pixmap.save(path)
        print(f"    Saved: {path} ({pixmap.width()}x{pixmap.height()})")
        return path
    except Exception as e:
        logger.error(f"Screenshot {name} failed: {e}")
        traceback.print_exc()
        return None


def record_result(test_name, status, detail=""):
    results[test_name] = {"status": status, "detail": _safe_str(detail)}
    marker = "PASS" if status else "FAIL"
    print(f"  [{marker}] {_safe_str(test_name)}: {_safe_str(detail)}")


# ══════════════════════════════════════════════════════════════
# Initialize QApplication
# ══════════════════════════════════════════════════════════════
print("=" * 70)
print("ChemGrid Comprehensive Feature Test")
print("=" * 70)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer

app = QApplication(sys.argv)

# ── Import core modules ──
from main_window import MainWindow
from canvas import MoleculeCanvas

# SMILES for testing
ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"
IBUPROFEN_SMILES = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
STYRENE_SMILES = "C=Cc1ccccc1"

# ══════════════════════════════════════════════════════════════
# Helper: Create MainWindow with a drawn molecule
# ══════════════════════════════════════════════════════════════
def create_window_with_molecule(smiles, mol_name="Test"):
    """Create MainWindow and draw molecule via SMILES."""
    win = MainWindow()
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    QApplication.processEvents()

    # Draw molecule using pubchem_client draw method
    try:
        from draw import draw_smiles_on_canvas
        draw_smiles_on_canvas(win.cv, smiles, mol_name)
    except Exception:
        # Fallback: use canvas method directly
        try:
            win.cv._last_drawn_smiles = smiles
            win.cv._last_drawn_mol_name = mol_name
            # Try to draw via RDKit
            from rdkit import Chem
            from rdkit.Chem import AllChem, Draw
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                AllChem.Compute2DCoords(mol)
                conf = mol.GetConformer()
                cx, cy = 400, 300  # center
                scale = 40
                atoms_dict = {}
                for i, atom in enumerate(mol.GetAtoms()):
                    pos = conf.GetAtomPosition(i)
                    x = cx + pos.x * scale
                    y = cy + pos.y * scale
                    sym = atom.GetSymbol()
                    key = (x, y)
                    # Carbon = empty string per project rules
                    main_sym = "" if sym == "C" else sym
                    atoms_dict[key] = {"main": main_sym}

                bonds_dict = {}
                for bond in mol.GetBonds():
                    i1 = bond.GetBeginAtomIdx()
                    i2 = bond.GetEndAtomIdx()
                    p1 = conf.GetAtomPosition(i1)
                    p2 = conf.GetAtomPosition(i2)
                    k1 = (cx + p1.x * scale, cy + p1.y * scale)
                    k2 = (cx + p2.x * scale, cy + p2.y * scale)
                    bt = bond.GetBondTypeAsDouble()
                    bonds_dict[(k1, k2)] = bt

                win.cv.atoms = atoms_dict
                win.cv.bonds = bonds_dict
                win.cv._last_drawn_smiles = smiles
                win.cv._last_drawn_mol_name = mol_name

                # Trigger analysis
                if hasattr(win.cv, 'analyze_molecule'):
                    try:
                        win.cv.analyze_molecule()
                    except Exception as e:
                        logger.warning("analyze_molecule failed: %s", e)
        except Exception as e:
            logger.warning(f"Molecule draw fallback failed: {e}")

    QApplication.processEvents()
    return win


# ══════════════════════════════════════════════════════════════
# TEST 1: 3D Popup with all 6 tabs
# ══════════════════════════════════════════════════════════════
print("\n[TEST 1] 3D Popup + All Tabs (Aspirin)")
try:
    from popup_3d import Molecule3DData, Molecule3DPopup

    win = create_window_with_molecule(ASPIRIN_SMILES, "Aspirin")

    # Build Molecule3DData from canvas
    mol_data = Molecule3DData(
        atoms=win.cv.atoms,
        bonds=win.cv.bonds,
        theory_data={},
        smiles=ASPIRIN_SMILES,
    )

    popup = Molecule3DPopup(mol_data, parent=None)
    popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    popup.show()
    QApplication.processEvents()
    time.sleep(0.5)
    QApplication.processEvents()

    # Main popup screenshot
    path = save_screenshot(popup, "3d_popup_main")
    record_result("3D_popup_main", path is not None, f"Screenshot: {path}")

    # Find tab widget
    tab_widget = None
    for child in popup.findChildren(__import__('PyQt6.QtWidgets', fromlist=['QTabWidget']).QTabWidget):
        tab_widget = child
        break

    if tab_widget:
        tab_count = tab_widget.count()
        print(f"  Found {tab_count} tabs")
        for i in range(tab_count):
            tab_name = tab_widget.tabText(i)
            tab_widget.setCurrentIndex(i)
            QApplication.processEvents()
            time.sleep(0.3)
            QApplication.processEvents()
            safe_name = tab_name.replace(" ", "_").replace("/", "_")
            # Remove emoji for filename
            import re
            safe_name = re.sub(r'[^\w\-_]', '', safe_name)
            if not safe_name:
                safe_name = f"tab{i}"
            path = save_screenshot(popup, f"3d_tab{i}_{safe_name}")
            record_result(f"3D_tab{i}_{safe_name}", path is not None, f"Tab: {tab_name}")
    else:
        record_result("3D_tabs", False, "No QTabWidget found in 3D popup")

    popup.close()
    win.close()
    del popup, win
    QApplication.processEvents()

except Exception as e:
    record_result("3D_popup", False, f"Exception: {e}")
    traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# TEST 2: Reaction Mechanism Popups
# ══════════════════════════════════════════════════════════════
print("\n[TEST 2] Reaction Mechanism Popups (SN2, E2, Aldol)")
REACTION_PAIRS = {
    "SN2": (["CBr", "O"], ["SN2 reactant", "SN2 nucleophile"]),
    "E2": (["CC(Br)CC", "[OH-]"], ["E2 substrate", "E2 base"]),
    "Aldol": (["CC=O", "CC(=O)C"], ["Aldehyde", "Ketone"]),
}

for rxn_name, (smiles_list, names_list) in REACTION_PAIRS.items():
    try:
        from popup_reaction import ReactionPopup

        popup = ReactionPopup(smiles_list=smiles_list, names=names_list, parent=None)
        popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        popup.show()
        QApplication.processEvents()
        time.sleep(1.0)  # Allow reaction prediction to run
        QApplication.processEvents()

        path = save_screenshot(popup, f"mechanism_{rxn_name}")
        record_result(f"Mechanism_{rxn_name}", path is not None, f"Screenshot: {path}")

        popup.close()
        del popup
        QApplication.processEvents()

    except Exception as e:
        record_result(f"Mechanism_{rxn_name}", False, f"Exception: {e}")
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# TEST 3: Retrosynthesis Popups
# ══════════════════════════════════════════════════════════════
print("\n[TEST 3] Retrosynthesis Popups (Aspirin, Ibuprofen)")
RETRO_TARGETS = {
    "Aspirin": ASPIRIN_SMILES,
    "Ibuprofen": IBUPROFEN_SMILES,
}

for name, smiles in RETRO_TARGETS.items():
    try:
        from popup_synthesis import SynthesisPopup

        popup = SynthesisPopup(target_smiles=smiles, target_name=name, parent=None)
        popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        popup.show()
        QApplication.processEvents()
        time.sleep(2.0)  # Allow retrosynthesis engine to process
        QApplication.processEvents()

        path = save_screenshot(popup, f"retrosynthesis_{name}")
        record_result(f"Retrosynthesis_{name}", path is not None, f"Screenshot: {path}")

        popup.close()
        del popup
        QApplication.processEvents()

    except Exception as e:
        record_result(f"Retrosynthesis_{name}", False, f"Exception: {e}")
        traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# TEST 4: ADMET Popup with 4 tabs
# ══════════════════════════════════════════════════════════════
print("\n[TEST 4] ADMET Popup (Aspirin) - 4 Tabs")
try:
    from popup_admet import ADMETPopup

    popup = ADMETPopup(smiles=ASPIRIN_SMILES, mol_name="Aspirin", parent=None)
    popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    popup.show()
    QApplication.processEvents()
    time.sleep(0.5)
    QApplication.processEvents()

    # Main screenshot
    path = save_screenshot(popup, "admet_main")
    record_result("ADMET_main", path is not None, f"Screenshot: {path}")

    # Find tabs
    from PyQt6.QtWidgets import QTabWidget
    tab_widget = None
    for child in popup.findChildren(QTabWidget):
        tab_widget = child
        break

    if tab_widget:
        tab_count = tab_widget.count()
        print(f"  Found {tab_count} ADMET tabs")
        for i in range(tab_count):
            tab_name = tab_widget.tabText(i)
            tab_widget.setCurrentIndex(i)
            QApplication.processEvents()
            time.sleep(0.3)
            QApplication.processEvents()
            safe_name = re.sub(r'[^\w\-_]', '', tab_name.replace(" ", "_"))
            if not safe_name:
                safe_name = f"tab{i}"
            path = save_screenshot(popup, f"admet_tab{i}_{safe_name}")
            record_result(f"ADMET_tab{i}_{safe_name}", path is not None, f"Tab: {tab_name}")
    else:
        record_result("ADMET_tabs", False, "No QTabWidget found in ADMET popup")

    popup.close()
    del popup
    QApplication.processEvents()

except Exception as e:
    record_result("ADMET_popup", False, f"Exception: {e}")
    traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# TEST 5: Predicted Spectrum - 6 subtabs
# ══════════════════════════════════════════════════════════════
print("\n[TEST 5] Predicted Spectrum (Aspirin) - 6 Subtabs")
SPECTRUM_TYPES = ["ir", "1h_nmr", "13c_nmr", "uv_vis", "mass", "raman"]
SPECTRUM_LABELS = ["IR", "1H-NMR", "13C-NMR", "UV-Vis", "EI-MS", "Raman"]

try:
    from popup_predicted_spectrum import PredictedSpectrumPopup

    popup = PredictedSpectrumPopup(smiles=ASPIRIN_SMILES, spectrum_type="ir", parent=None)
    popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    popup.show()
    QApplication.processEvents()
    time.sleep(0.5)
    QApplication.processEvents()

    # Main screenshot
    path = save_screenshot(popup, "spectrum_main")
    record_result("Spectrum_main", path is not None, f"Screenshot: {path}")

    # Find tabs
    from PyQt6.QtWidgets import QTabWidget
    tab_widget = None
    for child in popup.findChildren(QTabWidget):
        tab_widget = child
        break

    if tab_widget:
        tab_count = tab_widget.count()
        print(f"  Found {tab_count} spectrum tabs")
        for i in range(tab_count):
            tab_name = tab_widget.tabText(i)
            tab_widget.setCurrentIndex(i)
            QApplication.processEvents()
            time.sleep(0.5)
            QApplication.processEvents()
            safe_name = re.sub(r'[^\w\-_]', '', tab_name.replace(" ", "_").replace("-", "_"))
            if not safe_name:
                safe_name = f"tab{i}"
            path = save_screenshot(popup, f"spectrum_tab{i}_{safe_name}")
            record_result(f"Spectrum_tab{i}_{safe_name}", path is not None, f"Tab: {tab_name}")
    else:
        record_result("Spectrum_tabs", False, "No QTabWidget found")

    popup.close()
    del popup
    QApplication.processEvents()

except Exception as e:
    record_result("Spectrum_popup", False, f"Exception: {e}")
    traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# TEST 6: DryLab PDF Generation
# ══════════════════════════════════════════════════════════════
print("\n[TEST 6] DryLab PDF Generation (Aspirin)")
try:
    from drylab_report_exporter import DryLabData, export_drylab_report

    # Build DryLabData with aspirin
    data = DryLabData()
    data.smiles = ASPIRIN_SMILES
    data.name = "Aspirin (Acetylsalicylic acid)"
    data.goal = "COX-2 선택적 저해제 개발"

    # Add basic mol_data
    data.mol_data = {
        "formula": "C9H8O4",
        "mw": 180.16,
        "smiles": ASPIRIN_SMILES,
    }

    # Try to add ADMET data
    try:
        from admet_predictor import ADMETPredictor
        predictor = ADMETPredictor()
        profile = predictor.predict(ASPIRIN_SMILES)
        data.admet_profile = profile if isinstance(profile, dict) else {}
    except Exception as e:
        logger.warning(f"ADMET for DryLab failed (non-critical): {e}")
        data.admet_profile = {"MW": 180.16, "LogP": 1.2, "HBD": 1, "HBA": 4}

    # Try to add synthesis routes
    try:
        from retrosynthesis_engine import RetrosynthesisEngine
        engine = RetrosynthesisEngine(target_smiles=ASPIRIN_SMILES)
        routes = engine.search()
        data.synthesis_routes = routes[:3] if routes else []
    except Exception as e:
        logger.warning(f"Retrosynthesis for DryLab failed (non-critical): {e}")

    # Try to add spectra
    try:
        from predict_spectra import predict_all
        spec = predict_all(ASPIRIN_SMILES)
        data.spectra = {
            "ir": {"peaks": getattr(spec, 'ir_peaks', [])},
            "nmr_1h": {"peaks": getattr(spec, 'nmr_1h_peaks', [])},
        }
    except Exception as e:
        logger.warning(f"Spectra for DryLab failed (non-critical): {e}")

    pdf_path = os.path.join(SCREENSHOT_DIR, "final_test_drylab_aspirin.pdf")
    success, msg = export_drylab_report(data, pdf_path)

    if success and os.path.exists(pdf_path):
        file_size = os.path.getsize(pdf_path)
        # Count pages
        page_count = 0
        try:
            with open(pdf_path, 'rb') as f:
                content = f.read()
                # Count /Type /Page (not /Pages)
                import re as _re
                page_count = len(_re.findall(rb'/Type\s*/Page[^s]', content))
        except Exception:
            page_count = -1

        record_result("DryLab_PDF", True,
                      f"Generated: {pdf_path} ({file_size} bytes, ~{page_count} pages)")
    else:
        record_result("DryLab_PDF", False, f"Export failed: {msg}")

except Exception as e:
    record_result("DryLab_PDF", False, f"Exception: {e}")
    traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# TEST 7: PolymerLab (Polystyrene)
# ══════════════════════════════════════════════════════════════
print("\n[TEST 7] PolymerLab (Polystyrene / Styrene)")
try:
    from popup_polymer import PolymerAnalysisPopup

    popup = PolymerAnalysisPopup(
        smiles=STYRENE_SMILES,
        mol_name="Polystyrene",
        parent=None,
    )
    popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    popup.show()
    QApplication.processEvents()
    time.sleep(1.0)
    QApplication.processEvents()

    # Main screenshot
    path = save_screenshot(popup, "polymer_main")
    record_result("Polymer_main", path is not None, f"Screenshot: {path}")

    # Find tabs
    from PyQt6.QtWidgets import QTabWidget
    tab_widget = None
    for child in popup.findChildren(QTabWidget):
        tab_widget = child
        break

    if tab_widget:
        tab_count = tab_widget.count()
        print(f"  Found {tab_count} polymer tabs")
        for i in range(min(tab_count, 4)):  # First 4 tabs
            tab_name = tab_widget.tabText(i)
            tab_widget.setCurrentIndex(i)
            QApplication.processEvents()
            time.sleep(0.3)
            QApplication.processEvents()
            safe_name = re.sub(r'[^\w\-_]', '', tab_name.replace(" ", "_"))
            if not safe_name:
                safe_name = f"tab{i}"
            path = save_screenshot(popup, f"polymer_tab{i}_{safe_name}")
            record_result(f"Polymer_tab{i}_{safe_name}", path is not None, f"Tab: {tab_name}")

    # Try PDF export using polymer_report_exporter directly
    try:
        from polymer_report_exporter import PolymerReportData, export_polymer_report as _export_poly
        pdf_path = os.path.join(SCREENSHOT_DIR, "final_test_polymer_styrene.pdf")
        poly_data = PolymerReportData(
            monomer_smiles=STYRENE_SMILES,
            polymer_props=getattr(popup, '_props', None),
            conditions=getattr(popup, '_conditions', {}),
            ai_text="Automated test - polystyrene analysis",
        )
        success, msg = _export_poly(poly_data, pdf_path)
        if success and os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path)
            record_result("Polymer_PDF", True, f"PDF: {pdf_path} ({file_size} bytes)")
        else:
            record_result("Polymer_PDF", False, f"PDF export failed: {msg}")
    except ImportError as e:
        record_result("Polymer_PDF", False, f"polymer_report_exporter not available: {e}")
    except Exception as e:
        record_result("Polymer_PDF", False, f"PDF export failed: {e}")

    popup.close()
    del popup
    QApplication.processEvents()

except Exception as e:
    record_result("Polymer_popup", False, f"Exception: {e}")
    traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

pass_count = sum(1 for v in results.values() if v["status"])
fail_count = sum(1 for v in results.values() if not v["status"])
total = len(results)

for name, info in results.items():
    marker = "PASS" if info["status"] else "FAIL"
    print(f"  [{marker}] {name}: {info['detail']}")

print(f"\nTotal: {total} | PASS: {pass_count} | FAIL: {fail_count}")
print(f"Screenshots saved to: {SCREENSHOT_DIR}")
print("=" * 70)

# Exit
sys.exit(0 if fail_count == 0 else 1)
