
#!/usr/bin/env python3
"""
verify_integrated_fixes.py — Integrated Phase 6-1A Fix Verification
===================================================================
Verifies that critical fixes are present in the 'integrated/' folder.
Adapted from verify_critical_fixes.py for the new file structure.

Usage:
  py verify_integrated_fixes.py
"""

import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_INTEGRATED_DIR = _SCRIPT_DIR / "integrated"
_SOURCE_DIR = _SCRIPT_DIR.parent.parent / "_source"

PASS = "✅ PASS"
FAIL = "❌ FAIL"

results = []

def check(test_id, description, condition):
    status = PASS if condition else FAIL
    results.append((test_id, description, condition))
    print(f"  {status} {test_id}: {description}")
    return condition

def read_file(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""

def main():
    print("=" * 70)
    print("Integrated Phase 6-1A Critical Fix Verification")
    print("=" * 70)

    # ── 파일 존재 확인 ──
    print("\n[0] File Existence Check")
    integrated_files = [
        "orca_interface.py",
        "popup_3d.py",
        "canvas.py",
        "renderer.py",
        "draw.py",
        "main_window.py"
    ]
    for f in integrated_files:
        check(f"FILE_{f}", f"integrated/{f} exists", (_INTEGRATED_DIR / f).exists())

    # ── C1: ORCA Portable Path ──
    print("\n[C1] ORCA Path Hardcoding Fix")
    orca_code = read_file(_INTEGRATED_DIR / "orca_interface.py")
    
    check("C1-1", "__file__ based path present", "os.path.abspath(__file__)" in orca_code)
    check("C1-2", "No absolute path 'C:\\Users' in active code", 
          not any("C:\\Users" in line and not line.strip().startswith("#") for line in orca_code.split('\n')))

    # ── C2: popup_3d.py Import Fix ──
    print("\n[C2] popup_3d.py Import Fix")
    popup_code = read_file(_INTEGRATED_DIR / "popup_3d.py")
    
    check("C2-1", "No 'from PyQt6.QtOpenGL import GL'", 
          "from PyQt6.QtOpenGL import GL" not in popup_code)

    # ── C3: self.canvas.repaint() -> self.update() ──
    print("\n[C3] repaint() -> update() Fix (canvas.py)")
    canvas_code = read_file(_INTEGRATED_DIR / "canvas.py")
    
    check("C3-1", "No 'self.canvas.repaint()'", "self.canvas.repaint()" not in canvas_code)
    check("C3-2", "Uses 'self.update()'", "self.update()" in canvas_code)

    # ── C5: Portable Path System (General) ──
    print("\n[C5] Portable Path System (General)")
    draw_code = read_file(_INTEGRATED_DIR / "draw.py")
    
    check("C5-1", "No hardcoded 'organicdraw' path", "organicdraw" not in draw_code)
    check("C5-2", "No hardcoded 'C:\\Users'", "C:\\Users" not in draw_code)

    # ── M1: Crosshair Rendering Fix ──
    print("\n[M1] Single Crosshair Rendering Call")
    # canvas.py handles rendering now
    crosshair_calls = canvas_code.count("CloudRenderer.draw_crosshairs_v32(")
    check("M1-1", f"draw_crosshairs_v32 called exactly once (Found: {crosshair_calls})", crosshair_calls == 1)

    # ── M2: Debug Print Removal ──
    print("\n[M2] Debug Print Removal (renderer.py)")
    renderer_code = read_file(_INTEGRATED_DIR / "renderer.py")
    debug_prints = renderer_code.count('print(f"')
    check("M2-1", f"Reduced debug prints (Found: {debug_prints})", debug_prints < 5) 

    # ── Syntax Check ──
    print("\n[SYN] Syntax Verification")
    import ast
    for f in integrated_files:
        try:
            ast.parse(read_file(_INTEGRATED_DIR / f))
            check(f"SYN_{f}", f"{f} syntax valid", True)
        except SyntaxError as e:
            check(f"SYN_{f}", f"{f} syntax error: {e}", False)

    # ── Summary ──
    total = len(results)
    passed = sum(1 for _, _, ok in results if ok)
    failed = total - passed

    print(f"\n{'=' * 70}")
    print(f"Verification Result: {passed}/{total} PASS ({failed} FAIL)")
    print(f"{'=' * 70}")

    if failed > 0:
        print("\nFailed Items:")
        for tid, desc, ok in results:
            if not ok:
                print(f"  ❌ {tid}: {desc}")

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
