"""
test_serial_audit_cycle3.py — Serial Pipeline Cycle 3 QTest Audit
================================================================
Verifies the P0 btn_back fix and DryLab cairo workaround using
QTest.mouseClick() for ALL button interactions.

Steps:
  1. Open app
  2. Type "aspirin" + Enter
  3. Click "루이스 구조" button
  4. Click "그리기 화면으로 복귀" button (P0 bug fix)
  5. Verify app doesn't freeze
  6. Click "이론적 구조" button
  7. Click "입체 구조" button
  8. Click "2D로 복귀" button
  9. Open DryLab via menu
  10. DryLab PDF or error (not crash)?

Each step: screenshot + PASS/FAIL
"""
import sys
import os
import time
import tempfile
import traceback
from pathlib import Path
from datetime import datetime

# Path setup
SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = APP_DIR.parent.parent
sys.path.insert(0, str(APP_DIR))
os.chdir(str(APP_DIR))

# Output directory
AUDIT_DIR = PROJECT_ROOT / "departments" / "archive" / "screenshots" / f"audit_cycle3_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# Results tracking
results = []


def record(step_id, description, passed, error=None, screenshot_path=None):
    """Record a test step result."""
    status = "PASS" if passed else "FAIL"
    results.append({
        "step_id": step_id,
        "description": description,
        "status": status,
        "error": error,
        "screenshot": screenshot_path,
    })
    print(f"  [{status}] Step {step_id}: {description}")
    if error:
        print(f"         Error: {error}")


def screenshot(widget, name):
    """Capture a screenshot and return the path."""
    try:
        pix = widget.grab()
        if pix.isNull() or pix.width() == 0:
            return None
        fp = str(AUDIT_DIR / f"{name}.png")
        pix.save(fp, "PNG")
        return fp
    except Exception as e:
        print(f"    Screenshot failed: {e}")
        return None


def main():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtCore import Qt, QPoint

    app = QApplication.instance() or QApplication(sys.argv)

    # Import main window
    from main_window import MainWindow
    win = MainWindow()
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    win.resize(1400, 900)
    win.show()
    for _ in range(5):
        app.processEvents()

    # ──────────────────────────────────────────────
    # Step 1: Open app
    # ──────────────────────────────────────────────
    print("\n[Step 1] App opened")
    sp = screenshot(win, "01_app_opened")
    record("1", "App opens without crash", True, screenshot_path=sp)

    # ──────────────────────────────────────────────
    # Step 2: Type "aspirin" + Enter
    # ──────────────────────────────────────────────
    print("\n[Step 2] Type 'aspirin' + Enter")
    try:
        assert hasattr(win, 'mol_name_input'), "mol_name_input not found"
        win.mol_name_input.clear()
        app.processEvents()
        QTest.keyClicks(win.mol_name_input, "aspirin")
        app.processEvents()
        QTest.keyClick(win.mol_name_input, Qt.Key.Key_Return)
        # Process events multiple times to let PubChem lookup / SMILES drawing complete
        for _ in range(30):
            app.processEvents()
            time.sleep(0.05)
        sp = screenshot(win, "02_aspirin_drawn")
        # Check if SMILES was set
        smiles = getattr(win.cv, '_last_drawn_smiles', '') or ''
        if not smiles:
            ar = getattr(win.cv, 'analysis_results', None) or {}
            smiles = ar.get('smiles', '') if isinstance(ar, dict) else ''
        has_atoms = bool(getattr(win.cv, 'atoms', None))
        passed = bool(smiles) or has_atoms
        record("2", f"Type 'aspirin' + Enter -> SMILES={smiles[:40]}", passed,
               error=None if passed else "No SMILES or atoms after typing aspirin",
               screenshot_path=sp)
    except Exception as e:
        sp = screenshot(win, "02_aspirin_error")
        record("2", "Type 'aspirin' + Enter", False, error=str(e), screenshot_path=sp)

    # ──────────────────────────────────────────────
    # Step 3: Click "루이스 구조" button
    # ──────────────────────────────────────────────
    print("\n[Step 3] Click '루이스 구조' button")
    try:
        assert hasattr(win, 'btn_lewis'), "btn_lewis not found"
        assert win.btn_lewis.isVisible(), "btn_lewis is not visible"
        QTest.mouseClick(win.btn_lewis, Qt.MouseButton.LeftButton)
        for _ in range(10):
            app.processEvents()
        sp = screenshot(win, "03_lewis_view")
        # Verify we switched to Lewis mode
        cv_view = getattr(win.cv, 'view_state', '')
        passed = (cv_view == "Lewis")
        record("3", f"Click Lewis button -> view_state={cv_view}", passed,
               error=None if passed else f"Expected Lewis, got {cv_view}",
               screenshot_path=sp)
    except Exception as e:
        sp = screenshot(win, "03_lewis_error")
        record("3", "Click '루이스 구조' button", False, error=str(e), screenshot_path=sp)

    # ──────────────────────────────────────────────
    # Step 4: Click "그리기 화면으로 복귀" (P0 BUG)
    # ──────────────────────────────────────────────
    print("\n[Step 4] Click '그리기 화면으로 복귀' button (P0 bug)")
    try:
        assert hasattr(win, 'btn_back'), "btn_back not found"
        assert win.btn_back.isVisible(), "btn_back is not visible (should show in Lewis mode)"
        QTest.mouseClick(win.btn_back, Qt.MouseButton.LeftButton)
        for _ in range(10):
            app.processEvents()
        sp = screenshot(win, "04_back_to_drawing")
        cv_view = getattr(win.cv, 'view_state', '')
        passed = (cv_view == "Drawing")
        record("4", f"Click back button -> view_state={cv_view} (P0 fix)", passed,
               error=None if passed else f"Expected Drawing, got {cv_view}",
               screenshot_path=sp)
    except Exception as e:
        sp = screenshot(win, "04_back_error")
        record("4", "Click '그리기 화면으로 복귀' button", False, error=str(e), screenshot_path=sp)

    # ──────────────────────────────────────────────
    # Step 5: Verify app didn't freeze
    # ──────────────────────────────────────────────
    print("\n[Step 5] Verify app responsive after back button")
    try:
        # If we got here, app didn't freeze
        app.processEvents()
        sp = screenshot(win, "05_responsive_check")
        record("5", "App is responsive after back button click", True, screenshot_path=sp)
    except Exception as e:
        record("5", "App responsiveness check", False, error=str(e))

    # ──────────────────────────────────────────────
    # Step 6: Click "이론적 구조" button
    # ──────────────────────────────────────────────
    print("\n[Step 6] Click '이론적 구조' button")
    try:
        assert hasattr(win, 'btn_theory'), "btn_theory not found"
        assert win.btn_theory.isVisible(), "btn_theory is not visible"
        QTest.mouseClick(win.btn_theory, Qt.MouseButton.LeftButton)
        for _ in range(10):
            app.processEvents()
        sp = screenshot(win, "06_theory_view")
        cv_view = getattr(win.cv, 'view_state', '')
        passed = (cv_view == "Theory")
        record("6", f"Click Theory button -> view_state={cv_view}", passed,
               error=None if passed else f"Expected Theory, got {cv_view}",
               screenshot_path=sp)
    except Exception as e:
        sp = screenshot(win, "06_theory_error")
        record("6", "Click '이론적 구조' button", False, error=str(e), screenshot_path=sp)

    # ──────────────────────────────────────────────
    # Step 7: Click "입체 구조" button
    # ──────────────────────────────────────────────
    print("\n[Step 7] Click '입체 구조' button")
    try:
        assert hasattr(win, 'btn_3d'), "btn_3d not found"
        if not win.btn_3d.isVisible():
            record("7", "btn_3d not visible (Theory mode required)", False,
                   error="btn_3d not visible - may need atoms selected")
        elif not win.btn_3d.isEnabled():
            record("7", "btn_3d not enabled (need molecule selected)", False,
                   error="btn_3d is disabled")
        else:
            QTest.mouseClick(win.btn_3d, Qt.MouseButton.LeftButton)
            for _ in range(15):
                app.processEvents()
            sp = screenshot(win, "07_3d_view")
            # In 3D mode, btn_3d text changes to "2D로 복귀"
            btn_text = win.btn_3d.text()
            passed = ("2D" in btn_text or "복귀" in btn_text)
            record("7", f"Click 3D button -> btn text='{btn_text}'", passed,
                   error=None if passed else f"btn_3d text did not change to 2D return mode",
                   screenshot_path=sp)
    except Exception as e:
        sp = screenshot(win, "07_3d_error")
        record("7", "Click '입체 구조' button", False, error=str(e), screenshot_path=sp)

    # ──────────────────────────────────────────────
    # Step 8: Click "2D로 복귀" button
    # ──────────────────────────────────────────────
    print("\n[Step 8] Click '2D로 복귀' button")
    try:
        btn_text = win.btn_3d.text() if hasattr(win, 'btn_3d') else ""
        if "2D" in btn_text or "복귀" in btn_text:
            QTest.mouseClick(win.btn_3d, Qt.MouseButton.LeftButton)
            for _ in range(10):
                app.processEvents()
            sp = screenshot(win, "08_back_to_2d")
            new_text = win.btn_3d.text()
            passed = ("입체" in new_text or "3D" in new_text.upper())
            record("8", f"Click 2D return -> btn text='{new_text}'", passed,
                   error=None if passed else f"btn_3d text did not revert",
                   screenshot_path=sp)
        else:
            # 3D wasn't toggled in step 7, skip
            record("8", "2D return skipped (3D was not activated)", False,
                   error="Step 7 did not activate 3D mode")
    except Exception as e:
        sp = screenshot(win, "08_2d_error")
        record("8", "Click '2D로 복귀' button", False, error=str(e), screenshot_path=sp)

    # ──────────────────────────────────────────────
    # Step 9: Open DryLab via menu
    # ──────────────────────────────────────────────
    print("\n[Step 9] DryLab report generation")
    try:
        # Ensure we're in Drawing mode and have a molecule
        win.switch_view("Drawing")
        for _ in range(5):
            app.processEvents()

        # Try calling the DryLab method directly (since QFileDialog is modal
        # and can't be tested with QTest in headless mode)
        smiles = getattr(win.cv, '_last_drawn_smiles', '') or ''
        if not smiles:
            ar = getattr(win.cv, 'analysis_results', None) or {}
            smiles = ar.get('smiles', '') if isinstance(ar, dict) else ''

        if not smiles:
            record("9", "DryLab skipped (no SMILES available)", False,
                   error="No molecule loaded for DryLab")
        else:
            # Import and run DryLab directly.
            # Force headless mode to skip expensive 3D rendering and
            # membrane permeability sweep (which can take >60s).
            # The key test is: does it produce a PDF without crashing?
            import drylab_report_exporter as _dre
            _dre._HEADLESS_MODE = True
            from drylab_report_exporter import DryLabData, DryLabReportExporter
            data = DryLabData(smiles=smiles, name="Aspirin")
            exporter = DryLabReportExporter(data=data)
            out_path = os.path.join(tempfile.gettempdir(), "audit_cycle3_drylab.pdf")
            ok, msg = exporter.export(out_path)
            if ok:
                pdf_size = os.path.getsize(out_path)
                record("9", f"DryLab PDF generated: {pdf_size} bytes", True)
            else:
                record("9", f"DryLab failed gracefully: {msg}", False,
                       error=f"DryLab returned error: {msg}")
    except Exception as e:
        record("9", "DryLab report generation", False, error=str(e))

    # ──────────────────────────────────────────────
    # Step 10: Summary
    # ──────────────────────────────────────────────
    sp = screenshot(win, "10_final_state")

    # Cleanup
    win.close()
    for _ in range(5):
        app.processEvents()

    # Print summary
    print("\n" + "=" * 70)
    print("AUDIT RESULTS - Serial Pipeline Cycle 3")
    print("=" * 70)
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = total - passed
    print(f"Total: {total}  PASS: {passed}  FAIL: {failed}")
    print("-" * 70)
    for r in results:
        mark = "OK" if r["status"] == "PASS" else "XX"
        # Sanitize for cp949 console encoding on Windows
        desc = r['description'].encode('ascii', errors='replace').decode('ascii')
        print(f"  [{mark}] Step {r['step_id']}: {desc}")
        if r.get("error"):
            err_safe = str(r['error']).encode('ascii', errors='replace').decode('ascii')
            print(f"         -> {err_safe}")
    print("-" * 70)

    # Write results JSON
    import json
    results_path = str(AUDIT_DIR / "audit_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "cycle": 3,
            "total": total,
            "passed": passed,
            "failed": failed,
            "steps": results,
            "output_dir": str(AUDIT_DIR),
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {results_path}")
    print(f"Screenshots in: {AUDIT_DIR}")

    verdict = "ALL PASS" if failed == 0 else f"{failed} FAILURES"
    print(f"\nVERDICT: {verdict}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as e:
        print(f"\nFATAL: Audit crashed: {e}")
        traceback.print_exc()
        exit_code = 2
    sys.exit(exit_code)
