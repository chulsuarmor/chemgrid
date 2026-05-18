"""
test_visual_3d.py — ChemGrid 3D/Orbital/Docking Visual QA
==========================================================
Real-display screenshot capture for 3D OpenGL content.
MUST run on a real display (NOT headless/offscreen).

Covers:
  A. 3D Ball-and-Stick views
  B. Orbital visualization (pi, hybrid, d, all)
  C. Docking popup
  D. Orbital OFF vs ON comparison

Usage:
    cd C:/chemgrid/src/app
    python tests/test_visual_3d.py

Outputs:
    departments/archive/screenshots/3d_audit_YYYYMMDD/
        *.png              - individual screenshots
        report.html        - styled HTML report
        results.json       - machine-readable results
"""
import sys
import os
import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# -- Path setup --
SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = APP_DIR.parent.parent  # C:/chemgrid
sys.path.insert(0, str(APP_DIR))
os.chdir(str(APP_DIR))

# -- Output directories --
TODAY = datetime.now().strftime("%Y%m%d")
OUTPUT_DIR = PROJECT_ROOT / "departments" / "archive" / "screenshots" / f"3d_audit_{TODAY}"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# -- Test molecules --
MOLECULES = {
    "benzene":   ("c1ccccc1",                          "simple aromatic"),
    "aspirin":   ("CC(=O)Oc1ccccc1C(=O)O",             "ester + aromatic"),
    "ferrocene": ("[Fe+2].[cH-]1cccc1.[cH-]1cccc1",    "coordination compound"),
    "ethanol":   ("CCO",                                "simple alcohol"),
    "caffeine":  ("Cn1cnc2c1c(=O)n(c(=O)n2C)C",        "purine ring"),
}


# -- Data classes --
@dataclass
class TestStep:
    step_id: str
    description: str
    molecule: str
    category: str
    screenshot_path: Optional[str] = None
    passed: bool = False
    error: Optional[str] = None
    duration_ms: float = 0.0
    pixel_colors: int = 0  # unique color count in viewport


@dataclass
class TestReport:
    timestamp: str = ""
    total_steps: int = 0
    passed: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)
    steps: List[TestStep] = field(default_factory=list)
    duration_sec: float = 0.0


report = TestReport(timestamp=datetime.now().isoformat())


# ================================================================
# Helper functions
# ================================================================

def count_unique_colors(pixmap, sample_region=None):
    """Count unique colors in a pixmap to detect blank/solid screens."""
    img = pixmap.toImage()
    colors = set()
    w, h = img.width(), img.height()
    # Sample center region (or full if small)
    x0 = w // 4 if w > 200 else 0
    y0 = h // 4 if h > 200 else 0
    x1 = 3 * w // 4 if w > 200 else w
    y1 = 3 * h // 4 if h > 200 else h
    step = max(1, (x1 - x0) * (y1 - y0) // 5000)  # sample ~5000 pixels
    idx = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            idx += 1
            if idx % step == 0:
                colors.add(img.pixel(x, y))
    return len(colors)


def grab_widget(widget, step_id, description, molecule, category):
    """Capture a screenshot and record the result."""
    t0 = time.time()
    step = TestStep(
        step_id=step_id,
        description=description,
        molecule=molecule,
        category=category,
    )
    try:
        app.processEvents()
        time.sleep(0.3)
        app.processEvents()
        pix = widget.grab()
        if pix.isNull() or pix.width() == 0:
            step.error = "Empty/null pixmap"
            step.passed = False
        else:
            fp = str(OUTPUT_DIR / f"{step_id}.png")
            pix.save(fp, "PNG")
            if os.path.exists(fp) and os.path.getsize(fp) > 500:
                step.screenshot_path = fp
                step.pixel_colors = count_unique_colors(pix)
                # 3D content should have many colors (>20), blank/solid = fail
                if step.pixel_colors > 10:
                    step.passed = True
                else:
                    step.error = f"Only {step.pixel_colors} unique colors - likely blank/solid"
                    step.passed = False
            else:
                step.error = "Screenshot file too small or missing"
                step.passed = False
        step.duration_ms = (time.time() - t0) * 1000
        status = "PASS" if step.passed else "FAIL"
        colors_info = f" ({step.pixel_colors} colors)" if step.pixel_colors else ""
        print(f"  [{status}] {step_id}: {description}{colors_info}")
    except Exception as e:
        step.error = str(e)
        step.passed = False
        step.duration_ms = (time.time() - t0) * 1000
        print(f"  [FAIL] {step_id}: {e}")
    report.steps.append(step)
    return step


def err(ctx, exc_info):
    msg = f"[{ctx}] {str(exc_info)[:200]}"
    report.errors.append(msg)
    print(f"  [ERR] {msg}")


def make_mol_data(smiles, name):
    """Create a Molecule3DData from SMILES using RDKit."""
    from rdkit import Chem
    from rdkit.Chem import AllChem, Draw
    from popup_3d import Molecule3DData

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Cannot parse SMILES: {smiles}")

    mol = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
    AllChem.MMFFOptimizeMolecule(mol)

    # Build atoms/bonds dicts similar to canvas format
    atoms = {}
    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        atom = mol.GetAtomWithIdx(i)
        pos3d = conf.GetAtomPosition(i)
        key = (200 + pos3d.x * 30, 200 + pos3d.y * 30)
        sym = atom.GetSymbol()
        atoms[key] = {
            "main": "" if sym == "C" else sym,
            "rdkit_idx": i,
        }

    bonds = {}
    bond_id = 0
    for bond in mol.GetBonds():
        a1 = bond.GetBeginAtomIdx()
        a2 = bond.GetEndAtomIdx()
        p1 = conf.GetAtomPosition(a1)
        p2 = conf.GetAtomPosition(a2)
        k1 = (200 + p1.x * 30, 200 + p1.y * 30)
        k2 = (200 + p2.x * 30, 200 + p2.y * 30)
        bt = bond.GetBondTypeAsDouble()
        bonds[bond_id] = {
            "from": k1,
            "to": k2,
            "type": int(bt),
        }
        bond_id += 1

    return Molecule3DData(atoms=atoms, bonds=bonds, smiles=smiles)


def generate_html_report(report):
    """Generate HTML report with thumbnails and PASS/FAIL badges."""
    categories = {}
    for step in report.steps:
        cat = step.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(step)

    pass_rate = (report.passed / report.total_steps * 100) if report.total_steps > 0 else 0
    status_color = "#22c55e" if pass_rate >= 90 else "#f59e0b" if pass_rate >= 50 else "#ef4444"

    cards_html = ""
    for cat, steps in categories.items():
        cards_html += f'<h2 class="cat-header">{cat}</h2>\n<div class="grid">\n'
        for s in steps:
            badge = '<span class="badge pass">PASS</span>' if s.passed else '<span class="badge fail">FAIL</span>'
            colors_info = f"<br><small>{s.pixel_colors} unique colors</small>" if s.pixel_colors else ""
            if s.screenshot_path:
                rel = os.path.basename(s.screenshot_path)
                img_tag = f'<img src="{rel}" alt="{s.step_id}" loading="lazy" onclick="openModal(this.src)">'
            else:
                img_tag = '<div class="no-img">No Screenshot</div>'
            error_html = f'<div class="error">{s.error}</div>' if s.error else ""
            cards_html += f'''<div class="card">
  {badge}
  {img_tag}
  <div class="info"><b>{s.step_id}</b><br>{s.description}{colors_info}{error_html}</div>
</div>\n'''
        cards_html += '</div>\n'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ChemGrid 3D Visual QA Report</title>
<style>
body {{ font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; margin: 20px; }}
h1 {{ color: #58a6ff; }}
h2.cat-header {{ color: #8b949e; border-bottom: 1px solid #30363d; padding-bottom: 8px; margin-top: 30px; }}
.summary {{ display: flex; gap: 20px; margin: 20px 0; }}
.stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px 24px; text-align: center; }}
.stat .num {{ font-size: 2em; font-weight: bold; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }}
.card img {{ width: 100%; height: 220px; object-fit: contain; background: #000; cursor: pointer; }}
.card .no-img {{ width: 100%; height: 220px; display: flex; align-items: center; justify-content: center; background: #1a1a2e; color: #666; }}
.card .info {{ padding: 10px; font-size: 0.85em; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; margin: 8px; }}
.badge.pass {{ background: #22c55e20; color: #22c55e; border: 1px solid #22c55e; }}
.badge.fail {{ background: #ef444420; color: #ef4444; border: 1px solid #ef4444; }}
.error {{ color: #f87171; font-size: 0.8em; margin-top: 4px; }}
.modal {{ display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); }}
.modal img {{ margin: auto; display: block; max-width: 90%; max-height: 90%; margin-top: 2%; }}
.modal:target {{ display: flex; }}
</style>
<script>
function openModal(src) {{
  let m = document.getElementById('modal');
  m.style.display = 'flex';
  document.getElementById('modal-img').src = src;
}}
function closeModal() {{ document.getElementById('modal').style.display = 'none'; }}
</script>
</head><body>
<h1>ChemGrid 3D Visual QA Report</h1>
<p>Generated: {report.timestamp} | Duration: {report.duration_sec:.1f}s</p>
<div class="summary">
  <div class="stat"><div class="num" style="color:{status_color}">{pass_rate:.0f}%</div>Pass Rate</div>
  <div class="stat"><div class="num">{report.total_steps}</div>Total</div>
  <div class="stat"><div class="num" style="color:#22c55e">{report.passed}</div>Passed</div>
  <div class="stat"><div class="num" style="color:#ef4444">{report.failed}</div>Failed</div>
</div>
{cards_html}
<div id="modal" class="modal" onclick="closeModal()"><img id="modal-img"></div>
</body></html>"""
    return html


# ================================================================
# Main test execution
# ================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("ChemGrid 3D Visual QA - Real Display Test")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    # Ensure NOT headless
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        print("ERROR: This test MUST run on a real display. Remove QT_QPA_PLATFORM=offscreen")
        sys.exit(1)

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    app = QApplication(sys.argv)

    t_start = time.time()

    # ── A. 3D Ball-and-Stick views ──
    print("\n[A] 3D Ball-and-Stick Views")
    print("-" * 40)
    from popup_3d import Molecule3DData, Molecule3DPopup, Molecule3DViewer

    for mol_name in ["benzene", "aspirin", "ferrocene"]:
        smiles, desc = MOLECULES[mol_name]
        try:
            mol_data = make_mol_data(smiles, mol_name)
            popup = Molecule3DPopup(mol_data)
            popup.show()
            app.processEvents()
            time.sleep(0.5)
            app.processEvents()

            grab_widget(popup, f"3d_ballstick_{mol_name}",
                       f"{mol_name} Ball-and-Stick 3D view", mol_name, "A. 3D Ball-and-Stick")

            popup.close()
            app.processEvents()
        except Exception as e:
            err(f"3D_{mol_name}", traceback.format_exc())

    # ── B. Orbital Visualization ──
    print("\n[B] Orbital Visualization")
    print("-" * 40)

    orbital_tests = [
        ("benzene", "pi",      "benzene pi orbital (sp2)"),
        ("benzene", "hybrid",  "benzene hybrid orbital (auto)"),
        ("benzene", "all",     "benzene all orbitals"),
        ("ethanol", "hybrid",  "ethanol sigma/pi hybrid"),
        ("ferrocene", "d_orbital", "ferrocene d-orbital"),
    ]

    for mol_name, orbital_mode, desc in orbital_tests:
        smiles, _ = MOLECULES[mol_name]
        try:
            mol_data = make_mol_data(smiles, mol_name)
            popup = Molecule3DPopup(mol_data)
            popup.show()
            app.processEvents()
            time.sleep(0.3)
            app.processEvents()

            # Set orbital mode via combo box
            mode_map = {'none': 0, 'pi': 1, 'hybrid': 2, 'd_orbital': 3, 'f_orbital': 4, 'all': 5}
            idx = mode_map.get(orbital_mode, 0)
            if hasattr(popup, 'orbital_combo'):
                popup.orbital_combo.setCurrentIndex(idx)
                app.processEvents()
                time.sleep(0.5)
                app.processEvents()

            grab_widget(popup, f"orbital_{mol_name}_{orbital_mode}",
                       desc, mol_name, "B. Orbital Visualization")

            popup.close()
            app.processEvents()
        except Exception as e:
            err(f"orbital_{mol_name}_{orbital_mode}", traceback.format_exc())

    # ── B2. Orbital OFF vs ON comparison ──
    print("\n[B2] Orbital OFF vs ON Comparison")
    print("-" * 40)

    try:
        mol_data = make_mol_data("c1ccccc1", "benzene")
        popup = Molecule3DPopup(mol_data)
        popup.show()
        app.processEvents()
        time.sleep(0.3)
        app.processEvents()

        # OFF
        if hasattr(popup, 'orbital_combo'):
            popup.orbital_combo.setCurrentIndex(0)  # none
            app.processEvents()
            time.sleep(0.3)
            app.processEvents()
        grab_widget(popup, "orbital_off_benzene",
                   "benzene orbital OFF (baseline)", "benzene", "B2. Orbital Comparison")

        # ON (pi)
        if hasattr(popup, 'orbital_combo'):
            popup.orbital_combo.setCurrentIndex(1)  # pi
            app.processEvents()
            time.sleep(0.5)
            app.processEvents()
        grab_widget(popup, "orbital_on_benzene_pi",
                   "benzene orbital ON (pi) - should show lobes", "benzene", "B2. Orbital Comparison")

        popup.close()
        app.processEvents()
    except Exception as e:
        err("orbital_comparison", traceback.format_exc())

    # ── C. Docking Popup ──
    print("\n[C] Docking Popup")
    print("-" * 40)

    try:
        from popup_docking import DockingPopup
        dock = DockingPopup(canvas=None, parent=None)
        dock.show()
        app.processEvents()
        time.sleep(0.5)
        app.processEvents()

        grab_widget(dock, "docking_initial",
                   "Docking popup initial state", "aspirin", "C. Docking")

        # Try to set ligand SMILES if possible
        if hasattr(dock, 'ligand_input'):
            dock.ligand_input.setText("CC(=O)Oc1ccccc1C(=O)O")
            app.processEvents()
            time.sleep(0.3)

        grab_widget(dock, "docking_with_ligand",
                   "Docking popup with aspirin ligand", "aspirin", "C. Docking")

        # Try receptor selection if available
        if hasattr(dock, 'receptor_combo') and dock.receptor_combo.count() > 0:
            dock.receptor_combo.setCurrentIndex(0)
            app.processEvents()
            time.sleep(0.5)
            app.processEvents()
            grab_widget(dock, "docking_receptor_selected",
                       "Docking with receptor selected", "aspirin", "C. Docking")

        dock.close()
        app.processEvents()
    except Exception as e:
        err("docking", traceback.format_exc())

    # ── D. Spectrum tabs in 3D popup ──
    print("\n[D] Spectrum Tabs in 3D Popup")
    print("-" * 40)

    try:
        mol_data = make_mol_data("c1ccccc1", "benzene")
        popup = Molecule3DPopup(mol_data)
        popup.show()
        app.processEvents()
        time.sleep(0.5)
        app.processEvents()

        # Screenshot each tab
        if hasattr(popup, 'tab_widget'):
            for tab_idx in range(popup.tab_widget.count()):
                tab_name = popup.tab_widget.tabText(tab_idx)
                safe_name = tab_name.replace(" ", "_").replace("/", "_")
                popup.tab_widget.setCurrentIndex(tab_idx)
                app.processEvents()
                time.sleep(0.3)
                app.processEvents()
                grab_widget(popup, f"3d_tab_{tab_idx}_{safe_name}",
                           f"3D popup tab: {tab_name}", "benzene", "D. Spectrum Tabs")

        popup.close()
        app.processEvents()
    except Exception as e:
        err("spectrum_tabs", traceback.format_exc())

    # ── Finalize report ──
    report.duration_sec = time.time() - t_start
    report.total_steps = len(report.steps)
    report.passed = sum(1 for s in report.steps if s.passed)
    report.failed = report.total_steps - report.passed

    # Save results
    results_path = OUTPUT_DIR / "results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, ensure_ascii=False, indent=2)

    html = generate_html_report(report)
    html_path = OUTPUT_DIR / "report.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Summary
    print("\n" + "=" * 60)
    print(f"3D Visual QA Complete: {report.passed}/{report.total_steps} PASS")
    if report.errors:
        print(f"  Errors: {len(report.errors)}")
        for e in report.errors:
            print(f"    {e}")
    print(f"  Duration: {report.duration_sec:.1f}s")
    print(f"  Report: {html_path}")
    print(f"  Screenshots: {OUTPUT_DIR}")
    print("=" * 60)

    sys.exit(0 if report.failed == 0 else 1)
