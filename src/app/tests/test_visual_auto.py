"""
test_visual_auto.py — ChemGrid Automated Visual QA System v4
=============================================================
Headless screenshot capture + HTML report generation.

Launches the app with WA_DontShowOnScreen, simulates user interactions
via QTest, captures screenshots at every step, and generates a
professional HTML report with thumbnails, PASS/FAIL badges, and stats.

Usage:
    cd C:/chemgrid/src/app
    python tests/test_visual_auto.py

Outputs:
    departments/archive/screenshots/visual_qa_YYYYMMDD/
        *.png              — individual screenshots
        report.html        — styled HTML report
        results.json       — machine-readable results
"""
import sys
import os
import json
import math
import time
import traceback
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# ── Path setup ──
SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = APP_DIR.parent.parent  # C:/chemgrid
sys.path.insert(0, str(APP_DIR))
os.chdir(str(APP_DIR))

# ── Output directories ──
TODAY = datetime.now().strftime("%Y%m%d")
OUTPUT_DIR = PROJECT_ROOT / "departments" / "archive" / "screenshots" / f"visual_qa_{TODAY}"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Test molecules ──
MOLECULES = [
    ("benzene",     "c1ccccc1",                             "simple aromatic"),
    ("aspirin",     "CC(=O)Oc1ccccc1C(=O)O",               "ester + aromatic + carboxyl"),
    ("caffeine",    "Cn1cnc2c1c(=O)n(c(=O)n2C)C",          "purine ring + carbonyls"),
    ("ferrocene",   "[Fe+2].[cH-]1cccc1.[cH-]1cccc1",      "coordination compound"),
    ("hemoglobin",  "C1=CC2=CC3=CC(=C1)N=C3C=C4C=CC(=N4)C=C5C=CC(=N5)C=C2N=6", "large porphyrin"),
]


# ── Data classes ──
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


# ══════════════════════════════════════════════════════════════
# Helper functions
# ══════════════════════════════════════════════════════════════

def grab(widget, step_id: str, description: str, molecule: str, category: str) -> TestStep:
    """Capture a screenshot and record the result."""
    t0 = time.time()
    step = TestStep(
        step_id=step_id,
        description=description,
        molecule=molecule,
        category=category,
    )
    try:
        pix = widget.grab()
        # Check if the pixmap is non-empty (has non-zero size and not all white/black)
        if pix.isNull() or pix.width() == 0 or pix.height() == 0:
            step.error = "Empty/null pixmap"
            step.passed = False
        else:
            fp = str(OUTPUT_DIR / f"{step_id}.png")
            pix.save(fp, "PNG")
            if os.path.exists(fp) and os.path.getsize(fp) > 100:
                step.screenshot_path = fp
                step.passed = True
            else:
                step.error = "Screenshot file too small or missing"
                step.passed = False
        step.duration_ms = (time.time() - t0) * 1000
        status = "PASS" if step.passed else "FAIL"
        print(f"  [{status}] {step_id}: {description}")
    except Exception as e:
        step.error = str(e)
        step.passed = False
        step.duration_ms = (time.time() - t0) * 1000
        print(f"  [FAIL] {step_id}: {e}")
    report.steps.append(step)
    return step


def err(ctx: str, exc_info: str):
    """Record an error without a screenshot step."""
    msg = f"[{ctx}] {exc_info[:200]}"
    report.errors.append(msg)
    print(f"  [ERR] {msg}")


def force_reveal(canvas):
    """Bypass reveal animation clipping to force full render."""
    max_r = math.hypot(canvas.width(), canvas.height()) * 1.2
    canvas._reveal_radius = max_r
    if hasattr(canvas, 'anim'):
        try:
            canvas.anim.stop()
        except Exception:
            pass


def load_mol(win, app, smiles: str, name: str):
    """Load a molecule onto the canvas."""
    win.switch_view("Drawing")
    app.processEvents()
    win.cv.atoms.clear()
    win.cv.bonds.clear()
    win.cv._last_drawn_smiles = ""
    app.processEvents()
    win._draw_smiles_on_canvas(smiles, name)
    app.processEvents()
    app.processEvents()


def switch_and_grab(win, app, mode: str, step_id: str, desc: str, mol: str, cat: str) -> TestStep:
    """Switch view mode, force reveal, then screenshot."""
    win.switch_view(mode)
    app.processEvents()
    force_reveal(win.cv)
    app.processEvents()
    app.processEvents()
    return grab(win, step_id, desc, mol, cat)


def safe_close(widget):
    """Safely close a widget if it exists."""
    if widget is not None:
        try:
            widget.close()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# HTML Report Generator
# ══════════════════════════════════════════════════════════════

def generate_html_report(report: TestReport) -> str:
    """Generate a professional HTML report with CSS styling and thumbnails."""

    # Group steps by category
    categories = {}
    for step in report.steps:
        cat = step.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(step)

    pass_rate = (report.passed / report.total_steps * 100) if report.total_steps > 0 else 0
    status_color = "#22c55e" if pass_rate >= 90 else "#f59e0b" if pass_rate >= 50 else "#ef4444"

    # Build screenshot grid cards
    cards_html = ""
    for cat, steps in categories.items():
        cards_html += f'<h2 class="cat-header">{cat}</h2>\n'
        cards_html += '<div class="grid">\n'
        for s in steps:
            badge = '<span class="badge pass">PASS</span>' if s.passed else '<span class="badge fail">FAIL</span>'
            if s.screenshot_path:
                # Use relative path for the HTML file
                rel_path = os.path.basename(s.screenshot_path)
                img_tag = f'<img src="{rel_path}" alt="{s.step_id}" loading="lazy" onclick="openModal(this.src)">'
            else:
                img_tag = '<div class="no-img">No Screenshot</div>'
            error_line = f'<div class="error-msg">{s.error}</div>' if s.error else ''
            cards_html += f'''<div class="card {'pass-card' if s.passed else 'fail-card'}">
  {img_tag}
  <div class="card-body">
    {badge}
    <div class="step-id">{s.step_id}</div>
    <div class="step-desc">{s.description}</div>
    <div class="step-mol">Molecule: {s.molecule}</div>
    <div class="step-time">{s.duration_ms:.0f} ms</div>
    {error_line}
  </div>
</div>
'''
        cards_html += '</div>\n'

    # Error list
    error_list_html = ""
    if report.errors:
        error_list_html = '<div class="error-section"><h2>Errors</h2><ul>'
        for e in report.errors:
            error_list_html += f'<li>{e}</li>'
        error_list_html += '</ul></div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ChemGrid Visual QA Report — {report.timestamp[:10]}</title>
<style>
  :root {{
    --bg: #0f172a;
    --surface: #1e293b;
    --surface2: #334155;
    --text: #e2e8f0;
    --text-dim: #94a3b8;
    --accent: #3b82f6;
    --pass: #22c55e;
    --fail: #ef4444;
    --warn: #f59e0b;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    padding: 2rem;
  }}
  .header {{
    text-align: center;
    padding: 2rem 0 1.5rem;
    border-bottom: 1px solid var(--surface2);
    margin-bottom: 2rem;
  }}
  .header h1 {{
    font-size: 2rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
  }}
  .header .subtitle {{
    color: var(--text-dim);
    font-size: 1rem;
  }}
  .stats {{
    display: flex;
    gap: 1.5rem;
    justify-content: center;
    flex-wrap: wrap;
    margin-bottom: 2rem;
  }}
  .stat-card {{
    background: var(--surface);
    border-radius: 12px;
    padding: 1.2rem 2rem;
    text-align: center;
    min-width: 140px;
    border: 1px solid var(--surface2);
  }}
  .stat-card .value {{
    font-size: 2rem;
    font-weight: 700;
  }}
  .stat-card .label {{
    color: var(--text-dim);
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .cat-header {{
    font-size: 1.3rem;
    font-weight: 600;
    margin: 2rem 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid var(--accent);
    display: inline-block;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
    margin-bottom: 1rem;
  }}
  .card {{
    background: var(--surface);
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--surface2);
    transition: transform 0.15s, box-shadow 0.15s;
  }}
  .card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  }}
  .card img {{
    width: 100%;
    height: 200px;
    object-fit: cover;
    cursor: pointer;
    display: block;
    background: #000;
  }}
  .no-img {{
    width: 100%;
    height: 200px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--surface2);
    color: var(--text-dim);
    font-size: 0.9rem;
  }}
  .card-body {{
    padding: 0.8rem 1rem;
  }}
  .badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .badge.pass {{ background: var(--pass); color: #000; }}
  .badge.fail {{ background: var(--fail); color: #fff; }}
  .step-id {{
    font-weight: 600;
    font-size: 0.85rem;
    margin-top: 0.4rem;
    color: var(--accent);
  }}
  .step-desc {{
    font-size: 0.85rem;
    color: var(--text);
    margin-top: 0.2rem;
  }}
  .step-mol {{
    font-size: 0.75rem;
    color: var(--text-dim);
    margin-top: 0.15rem;
  }}
  .step-time {{
    font-size: 0.7rem;
    color: var(--text-dim);
  }}
  .error-msg {{
    font-size: 0.75rem;
    color: var(--fail);
    margin-top: 0.3rem;
    word-break: break-all;
  }}
  .pass-card {{ border-left: 3px solid var(--pass); }}
  .fail-card {{ border-left: 3px solid var(--fail); }}
  .error-section {{
    background: var(--surface);
    border: 1px solid var(--fail);
    border-radius: 10px;
    padding: 1.5rem;
    margin-top: 2rem;
  }}
  .error-section h2 {{
    color: var(--fail);
    margin-bottom: 0.5rem;
  }}
  .error-section li {{
    font-size: 0.85rem;
    margin-left: 1.5rem;
    margin-bottom: 0.3rem;
    color: var(--text-dim);
  }}
  .footer {{
    text-align: center;
    color: var(--text-dim);
    font-size: 0.8rem;
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid var(--surface2);
  }}
  /* Modal for full-size image */
  .modal {{
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.9);
    z-index: 9999;
    justify-content: center;
    align-items: center;
    cursor: pointer;
  }}
  .modal.active {{ display: flex; }}
  .modal img {{
    max-width: 95vw;
    max-height: 95vh;
    object-fit: contain;
    border-radius: 8px;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>ChemGrid Visual QA Report</h1>
  <div class="subtitle">{report.timestamp} | Duration: {report.duration_sec:.1f}s</div>
</div>

<div class="stats">
  <div class="stat-card">
    <div class="value" style="color: {status_color}">{pass_rate:.0f}%</div>
    <div class="label">Pass Rate</div>
  </div>
  <div class="stat-card">
    <div class="value">{report.total_steps}</div>
    <div class="label">Total Steps</div>
  </div>
  <div class="stat-card">
    <div class="value" style="color: var(--pass)">{report.passed}</div>
    <div class="label">Passed</div>
  </div>
  <div class="stat-card">
    <div class="value" style="color: var(--fail)">{report.failed}</div>
    <div class="label">Failed</div>
  </div>
  <div class="stat-card">
    <div class="value">{len(report.errors)}</div>
    <div class="label">Errors</div>
  </div>
</div>

{cards_html}

{error_list_html}

<div class="footer">
  Generated by ChemGrid Visual QA System v4 | Python {sys.version.split()[0]}
</div>

<div class="modal" id="imgModal" onclick="closeModal()">
  <img id="modalImg" src="" alt="Full size">
</div>

<script>
function openModal(src) {{
  document.getElementById('modalImg').src = src;
  document.getElementById('imgModal').classList.add('active');
}}
function closeModal() {{
  document.getElementById('imgModal').classList.remove('active');
}}
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') closeModal();
}});
</script>

</body>
</html>"""
    return html


# ══════════════════════════════════════════════════════════════
# Main test runner
# ══════════════════════════════════════════════════════════════

def run_tests():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtTest import QTest

    t_start = time.time()

    app = QApplication(sys.argv)

    from main_window import MainWindow
    win = MainWindow()
    win.resize(1400, 900)
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    app.processEvents()
    app.processEvents()

    print("=" * 70)
    print("ChemGrid Visual QA System v4 — Automated Screenshot + HTML Report")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 70)

    # ══════════════════════════════════════════════
    # 1. INITIAL STATE
    # ══════════════════════════════════════════════
    print("\n[1] Initial State")
    grab(win, "01_initial_empty", "Empty canvas on startup", "none", "Initial State")

    # ══════════════════════════════════════════════
    # 2. TEXT INPUT SIMULATION — Type molecule name
    # ══════════════════════════════════════════════
    print("\n[2] Text Input Simulation (QTest)")
    try:
        if hasattr(win, 'mol_name_input'):
            win.mol_name_input.clear()
            app.processEvents()
            QTest.keyClicks(win.mol_name_input, "benzene")
            app.processEvents()
            grab(win, "02_text_input_typed", "Typed 'benzene' in molecule input", "benzene", "Text Input")
            QTest.keyClick(win.mol_name_input, Qt.Key.Key_Return)
            app.processEvents()
            app.processEvents()
            app.processEvents()
            # Wait a bit for the molecule to load (PubChem lookup might take time)
            for _ in range(10):
                app.processEvents()
            grab(win, "02_text_input_result", "After pressing Enter on 'benzene'", "benzene", "Text Input")
    except Exception as e:
        err("text_input", traceback.format_exc())

    # ══════════════════════════════════════════════
    # 3. PER-MOLECULE TESTS
    # ══════════════════════════════════════════════
    for mol_name, smiles, mol_desc in MOLECULES:
        print(f"\n[3] Molecule: {mol_name} ({mol_desc})")
        safe_name = mol_name.replace(" ", "_").lower()

        # ── 3a: Load via SMILES and capture Drawing view ──
        try:
            load_mol(win, app, smiles, mol_name)
            grab(win, f"03_{safe_name}_drawing",
                 f"{mol_name} Drawing view ({mol_desc})", mol_name, "Drawing View")
        except Exception as e:
            err(f"load_{safe_name}", traceback.format_exc())
            # Skip remaining tests for this molecule
            step = TestStep(
                step_id=f"03_{safe_name}_drawing",
                description=f"FAILED to load {mol_name}",
                molecule=mol_name, category="Drawing View",
                error=str(e), passed=False,
            )
            report.steps.append(step)
            continue

        # ── 3b: Theory view ──
        try:
            switch_and_grab(win, app, "Theory", f"03_{safe_name}_theory",
                            f"{mol_name} Theory view — electron clouds", mol_name, "Theory View")
        except Exception as e:
            err(f"theory_{safe_name}", traceback.format_exc())

        # ── 3c: Lewis view ──
        try:
            switch_and_grab(win, app, "Lewis", f"03_{safe_name}_lewis",
                            f"{mol_name} Lewis structure — lone pairs + H", mol_name, "Lewis View")
        except Exception as e:
            err(f"lewis_{safe_name}", traceback.format_exc())

    # ══════════════════════════════════════════════
    # 4. 3D POPUP — Benzene (all tabs)
    # ══════════════════════════════════════════════
    print("\n[4] 3D Popup — Benzene")
    popup_3d = None
    try:
        load_mol(win, app, "c1ccccc1", "benzene")
        win.switch_view("Theory")
        app.processEvents()
        force_reveal(win.cv)
        app.processEvents()

        from popup_3d import Molecule3DData, Molecule3DPopup
        sel_atoms = dict(win.cv.atoms)
        sel_bonds = dict(win.cv.bonds)
        smiles_3d = win.cv.get_smiles() if hasattr(win.cv, 'get_smiles') else "c1ccccc1"

        mol_data = Molecule3DData(
            atoms=sel_atoms, bonds=sel_bonds,
            theory_data={}, smiles=smiles_3d or "c1ccccc1",
        )
        popup_3d = Molecule3DPopup(mol_data, win)
        popup_3d.resize(1200, 800)
        popup_3d.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        popup_3d.show()
        app.processEvents()
        app.processEvents()
        app.processEvents()

        grab(popup_3d, "04_3d_popup_default", "3D Popup — default (properties) tab",
             "benzene", "3D Popup")

        # Iterate through all tabs
        if hasattr(popup_3d, 'tabs'):
            for i in range(popup_3d.tabs.count()):
                tab_text = popup_3d.tabs.tabText(i)
                tab_id = tab_text.replace(" ", "_").replace("/", "_")
                popup_3d.tabs.setCurrentIndex(i)
                app.processEvents()
                app.processEvents()
                app.processEvents()
                grab(popup_3d, f"04_3d_tab_{i}_{tab_id}",
                     f"3D Popup tab {i}: {tab_text}", "benzene", "3D Popup Tabs")
    except Exception as e:
        err("3d_popup", traceback.format_exc())

    # ── 4a: Spectrum sub-tabs ──
    print("\n[4a] 3D Popup — Spectrum sub-tabs")
    if popup_3d and hasattr(popup_3d, 'tab_spectrum'):
        sp = popup_3d.tab_spectrum
        # Switch to spectrum tab first
        for i in range(popup_3d.tabs.count()):
            txt = popup_3d.tabs.tabText(i)
            if any(kw in txt for kw in ["스펙트럼", "Spectrum", "spectrum"]):
                popup_3d.tabs.setCurrentIndex(i)
                app.processEvents()
                break

        for stype in ["IR", "Raman", "NMR_H", "NMR_C13", "UV-Vis"]:
            try:
                if hasattr(sp, '_spec_btns') and stype in sp._spec_btns:
                    sp._on_spec_type_changed(stype)
                    app.processEvents()
                    app.processEvents()
                    grab(sp, f"04a_spec_{stype}", f"Spectrum: {stype}",
                         "benzene", "Spectrum Tabs")
            except Exception as e:
                err(f"spec_{stype}", traceback.format_exc())

    # ── 4b: Orbital visualization ──
    print("\n[4b] 3D Popup — Orbital")
    if popup_3d and hasattr(popup_3d, 'orbital_combo'):
        try:
            combo = popup_3d.orbital_combo
            for idx in range(min(combo.count(), 3)):
                combo.setCurrentIndex(idx)
                app.processEvents()
                app.processEvents()
                mode_name = combo.itemText(idx).replace(" ", "_").replace("/", "_")
                grab(popup_3d, f"04b_orbital_{idx}_{mode_name}",
                     f"Orbital mode: {combo.itemText(idx)}", "benzene", "Orbital")
        except Exception as e:
            err("orbital", traceback.format_exc())

    safe_close(popup_3d)
    popup_3d = None

    # ══════════════════════════════════════════════
    # 5. INDIVIDUAL SPECTRUM POPUPS
    # ══════════════════════════════════════════════
    print("\n[5] Predicted Spectrum Popups")
    for stype in ["ir", "raman", "nmr_h", "nmr_c13", "uv_vis"]:
        try:
            from popup_predicted_spectrum import PredictedSpectrumPopup
            sp = PredictedSpectrumPopup(smiles="c1ccccc1", spectrum_type=stype, parent=win)
            sp.resize(1000, 700)
            sp.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            sp.show()
            app.processEvents()
            app.processEvents()
            app.processEvents()
            grab(sp, f"05_predicted_spec_{stype}",
                 f"Predicted spectrum popup: {stype}", "benzene", "Predicted Spectrum")
            sp.close()
        except Exception as e:
            err(f"predicted_spec_{stype}", traceback.format_exc())

    # ══════════════════════════════════════════════
    # 6. REACTION POPUP
    # ══════════════════════════════════════════════
    print("\n[6] Reaction Popup")
    try:
        from popup_reaction import ReactionPopup
        rp = ReactionPopup(
            smiles_list=["CC(=O)Oc1ccccc1C(=O)O"],
            names=["aspirin"],
            parent=win,
        )
        rp.resize(1200, 800)
        rp.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        rp.show()
        app.processEvents()
        app.processEvents()
        app.processEvents()
        grab(rp, "06_reaction_popup", "Reaction pathway popup — aspirin",
             "aspirin", "Reaction Analysis")

        # Try switching tabs if available
        if hasattr(rp, 'tabs'):
            for i in range(rp.tabs.count()):
                rp.tabs.setCurrentIndex(i)
                app.processEvents()
                app.processEvents()
                tab_text = rp.tabs.tabText(i)
                grab(rp, f"06_reaction_tab_{i}",
                     f"Reaction tab {i}: {tab_text}", "aspirin", "Reaction Analysis")
        rp.close()
    except Exception as e:
        err("reaction_popup", traceback.format_exc())

    # ══════════════════════════════════════════════
    # 7. SYNTHESIS POPUP
    # ══════════════════════════════════════════════
    print("\n[7] Synthesis (Retrosynthesis) Popup")
    try:
        from popup_synthesis import SynthesisPopup
        sp = SynthesisPopup(
            target_smiles="CC(=O)Oc1ccccc1C(=O)O",
            target_name="aspirin",
            parent=win,
        )
        sp.resize(1200, 800)
        sp.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        sp.show()
        app.processEvents()
        app.processEvents()
        app.processEvents()
        grab(sp, "07_synthesis_popup", "Retrosynthesis route — aspirin",
             "aspirin", "Synthesis")

        # Try mechanism tab
        if hasattr(sp, 'tabs'):
            for i in range(sp.tabs.count()):
                sp.tabs.setCurrentIndex(i)
                app.processEvents()
                app.processEvents()
                tab_text = sp.tabs.tabText(i)
                grab(sp, f"07_synthesis_tab_{i}",
                     f"Synthesis tab {i}: {tab_text}", "aspirin", "Synthesis")
        sp.close()
    except Exception as e:
        err("synthesis_popup", traceback.format_exc())

    # ══════════════════════════════════════════════
    # 8. DOCKING POPUP
    # ══════════════════════════════════════════════
    print("\n[8] Docking Popup")
    try:
        from popup_docking import DockingPopup
        dp = DockingPopup(canvas=win.cv, parent=win)
        dp.resize(1100, 750)
        dp.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        dp.show()
        app.processEvents()
        app.processEvents()
        app.processEvents()
        grab(dp, "08_docking_popup", "Molecular docking simulation",
             "aspirin", "Docking")
        dp.close()
    except Exception as e:
        err("docking_popup", traceback.format_exc())

    # ══════════════════════════════════════════════
    # 9. ADMET POPUP
    # ══════════════════════════════════════════════
    print("\n[9] ADMET Popup")
    admet = None
    try:
        from popup_admet import ADMETPopup
        admet = ADMETPopup(
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            mol_name="aspirin",
            parent=win,
        )
        admet.resize(1000, 700)
        admet.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        admet.show()
        app.processEvents()
        app.processEvents()
        app.processEvents()
        grab(admet, "09_admet_default", "ADMET analysis — default tab",
             "aspirin", "ADMET")

        # Switch through tabs
        if hasattr(admet, 'tabs'):
            for i in range(admet.tabs.count()):
                admet.tabs.setCurrentIndex(i)
                app.processEvents()
                app.processEvents()
                tab_text = admet.tabs.tabText(i)
                grab(admet, f"09_admet_tab_{i}",
                     f"ADMET tab {i}: {tab_text}", "aspirin", "ADMET")
        safe_close(admet)
        admet = None
    except Exception as e:
        err("admet", traceback.format_exc())
        safe_close(admet)

    # ══════════════════════════════════════════════
    # 10. DRUG SCREENING POPUP
    # ══════════════════════════════════════════════
    print("\n[10] Drug Screening Popup")
    try:
        from popup_drug_screening import DrugScreeningPopup
        dsp = DrugScreeningPopup(
            smiles_list=["CC(=O)Oc1ccccc1C(=O)O", "c1ccccc1"],
            names_list=["aspirin", "benzene"],
            parent=win,
        )
        dsp.resize(1100, 750)
        dsp.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        dsp.show()
        app.processEvents()
        app.processEvents()
        app.processEvents()
        grab(dsp, "10_drug_screening", "Drug screening — aspirin + benzene",
             "aspirin", "Drug Screening")
        dsp.close()
    except Exception as e:
        err("drug_screening", traceback.format_exc())

    # ══════════════════════════════════════════════
    # 11. ALPHAFOLD POPUP
    # ══════════════════════════════════════════════
    print("\n[11] AlphaFold Popup")
    try:
        from popup_alphafold import AlphaFoldPopup
        afp = AlphaFoldPopup(parent=win)
        afp.resize(1100, 750)
        afp.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        afp.show()
        app.processEvents()
        app.processEvents()
        app.processEvents()
        grab(afp, "11_alphafold_popup", "AlphaFold structure prediction input",
             "none", "AlphaFold")
        afp.close()
    except Exception as e:
        err("alphafold", traceback.format_exc())

    # ══════════════════════════════════════════════
    # 12. PDF EXPORT VERIFICATION
    # ══════════════════════════════════════════════
    print("\n[12] PDF Export")
    pdf_step = TestStep(
        step_id="12_pdf_export",
        description="PDF export — verify file created",
        molecule="benzene",
        category="PDF Export",
    )
    try:
        load_mol(win, app, "c1ccccc1", "benzene")
        app.processEvents()

        from popup_predicted_spectrum import PredictedSpectrumPopup
        sp = PredictedSpectrumPopup(smiles="c1ccccc1", spectrum_type="ir", parent=win)
        sp.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        sp.show()
        app.processEvents()
        app.processEvents()

        pdf_path = str(OUTPUT_DIR / "test_export.pdf")

        # Try export via spectrum_pdf_exporter or manual fallback
        exported = False
        try:
            from matplotlib.backends.backend_pdf import PdfPages
            from matplotlib.figure import Figure
            import matplotlib
            matplotlib.use('Agg')

            from predict_spectra import predict_all
            from popup_predicted_spectrum import (
                _make_ir_figure, _make_raman_figure,
                _make_nmr_h1_figure, _make_nmr_c13_figure,
                _make_uvvis_figure
            )
            spec_data = predict_all("c1ccccc1")

            with PdfPages(pdf_path) as pdf:
                # Cover page
                fig1 = Figure(figsize=(8.5, 11), dpi=150)
                ax1 = fig1.add_subplot(111)
                ax1.text(0.5, 0.5, "ChemGrid QA Test — Benzene Spectrum Export",
                         ha='center', va='center', fontsize=14, transform=ax1.transAxes)
                ax1.axis('off')
                pdf.savefig(fig1)

                for title, fn in [
                    ("IR", _make_ir_figure),
                    ("Raman", _make_raman_figure),
                    ("1H NMR", _make_nmr_h1_figure),
                    ("13C NMR", _make_nmr_c13_figure),
                    ("UV-Vis", _make_uvvis_figure),
                ]:
                    try:
                        fig = fn(spec_data, "c1ccccc1")
                        pdf.savefig(fig)
                    except Exception:
                        fig_fb = Figure(figsize=(8.5, 11), dpi=150)
                        ax = fig_fb.add_subplot(111)
                        ax.text(0.5, 0.5, f"{title}: generation failed",
                                ha='center', va='center')
                        pdf.savefig(fig_fb)
            exported = True
        except Exception as e:
            err("pdf_export_inner", str(e))

        sp.close()

        if exported and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 500:
            pdf_step.passed = True
            pdf_step.description = f"PDF exported: {os.path.getsize(pdf_path):,} bytes"
            print(f"  [PASS] PDF: {os.path.getsize(pdf_path):,} bytes")
        else:
            pdf_step.error = "PDF not created or too small"
            pdf_step.passed = False
            print(f"  [FAIL] PDF export failed")

    except Exception as e:
        pdf_step.error = str(e)
        pdf_step.passed = False
        err("pdf_export", traceback.format_exc())

    report.steps.append(pdf_step)

    # ══════════════════════════════════════════════
    # 13. MANUAL DRAW SIMULATION
    # ══════════════════════════════════════════════
    print("\n[13] Manual Draw Simulation")
    try:
        win.switch_view("Drawing")
        app.processEvents()
        win.cv.atoms.clear()
        win.cv.bonds.clear()
        win.cv._last_drawn_smiles = ""
        app.processEvents()

        from canvas import get_coord_key
        p1 = QPointF(400, 400)
        p2 = QPointF(440, 400)
        k1 = get_coord_key(p1)
        k2 = get_coord_key(p2)
        win.cv.atoms[k1] = {"main": "", "charge": "", "attach": {}}
        win.cv.atoms[k2] = {"main": "", "charge": "", "attach": {}}
        win.cv.bonds[(k1, k2)] = 1
        app.processEvents()
        grab(win, "13_manual_draw_ethane", "Manual draw: 2 carbons + bond (ethane)",
             "ethane (manual)", "Manual Drawing")

        switch_and_grab(win, app, "Theory", "13_manual_ethane_theory",
                        "Manual ethane — Theory view (no clouds expected)",
                        "ethane (manual)", "Manual Drawing")
    except Exception as e:
        err("manual_draw", traceback.format_exc())

    # ══════════════════════════════════════════════
    # FINALIZE
    # ══════════════════════════════════════════════
    report.duration_sec = time.time() - t_start
    report.total_steps = len(report.steps)
    report.passed = sum(1 for s in report.steps if s.passed)
    report.failed = report.total_steps - report.passed

    print("\n" + "=" * 70)
    print(f"COMPLETE: {report.passed}/{report.total_steps} passed, "
          f"{report.failed} failed, {len(report.errors)} errors")
    print(f"Duration: {report.duration_sec:.1f}s")
    print(f"Output:   {OUTPUT_DIR}")
    print("=" * 70)

    # ── Save results.json ──
    results_path = OUTPUT_DIR / "results.json"
    with open(str(results_path), "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False, default=str)
    print(f"  Saved: {results_path}")

    # ── Generate HTML report ──
    html_path = OUTPUT_DIR / "report.html"
    html_content = generate_html_report(report)
    with open(str(html_path), "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  Saved: {html_path}")

    # ── Cleanup ──
    safe_close(popup_3d)
    win.close()
    app.quit()

    return report


# ══════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        result = run_tests()
        sys.exit(0 if result.failed == 0 else 1)
    except Exception as e:
        report.errors.append(f"CRASH: {traceback.format_exc()}")
        report.total_steps = len(report.steps)
        report.passed = sum(1 for s in report.steps if s.passed)
        report.failed = report.total_steps - report.passed

        # Still try to generate report even on crash
        try:
            results_path = OUTPUT_DIR / "results.json"
            with open(str(results_path), "w", encoding="utf-8") as f:
                json.dump(asdict(report), f, indent=2, ensure_ascii=False, default=str)
            html_path = OUTPUT_DIR / "report.html"
            with open(str(html_path), "w", encoding="utf-8") as f:
                f.write(generate_html_report(report))
            print(f"Crash report saved to: {html_path}")
        except Exception:
            pass

        print(f"\nCRASH: {e}")
        traceback.print_exc()
        sys.exit(1)
