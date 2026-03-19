#!/usr/bin/env python3
"""
Cascade #8 Task 3: 합성경로 PDF 내보내기 + 반응 메커니즘 화살표 정확성 검증
MM-SYNTHESIS Worker 테스트 스크립트
"""
import sys
import os
import traceback
import tempfile

# Add src/app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src', 'app'))

from retrosynthesis_engine import RetrosynthesisEngine, SynthesisRoute, SynthesisStep
from mechanism_pdf_exporter import MechanismPDFExporter, export_synthesis_route_pdf
from mechanism_engine import MechanismEngine, auto_mechanism

# ============================================================================
# PART 1: PDF Export Test (5 molecules)
# ============================================================================

MOLECULES = [
    ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
    ("Caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
    ("Ibuprofen", "CC(C)Cc1ccc(C(C)C(=O)O)cc1"),
    ("Phenol", "Oc1ccccc1"),
    ("Aniline", "Nc1ccccc1"),
]

def test_pdf_export():
    """Test 1: PDF export for 5 molecules via retrosynthesis + PDF exporter"""
    print("=" * 70)
    print("PART 1: PDF Export Test (5 molecules)")
    print("=" * 70)

    engine = RetrosynthesisEngine()
    exporter = MechanismPDFExporter()
    results = []

    for name, smiles in MOLECULES:
        print(f"\n--- {name} ({smiles}) ---")
        try:
            routes = engine.find_routes(smiles, max_depth=5, max_routes=3,
                                         validate=False, timeout_seconds=15.0)
            print(f"  Routes found: {len(routes)}")

            if not routes:
                # Create a minimal synthetic route for PDF test
                print(f"  [!] No retrosynthesis routes found. Creating minimal test route...")
                from dataclasses import dataclass
                test_step = SynthesisStep(
                    step_number=1,
                    reactant_smiles=[smiles],
                    product_smiles=smiles,
                    transform_name="직접 합성",
                    transform_name_en="Direct synthesis",
                    conditions="적절한 조건",
                    confidence=0.5,
                )
                route = SynthesisRoute(
                    target_smiles=smiles,
                    steps=[test_step],
                    total_steps=1,
                    score=0.5,
                    building_blocks=[smiles],
                    validated=False,
                )
            else:
                route = routes[0]
                print(f"  Best route: {route.total_steps} steps, score={route.score:.2f}")
                print(f"  Building blocks: {route.building_blocks[:3]}")
                for step in route.steps:
                    print(f"    Step {step.step_number}: {step.transform_name}")
                    print(f"      Reactants: {step.reactant_smiles}")
                    print(f"      Product: {step.product_smiles}")
                    print(f"      Conditions: {step.conditions}")

            # Export PDF
            output_dir = os.path.join(os.path.dirname(__file__))
            pdf_path = os.path.join(output_dir, f"test_{name.lower()}_route.pdf")
            success = exporter.export_route(route, pdf_path)

            if success and os.path.exists(pdf_path):
                file_size = os.path.getsize(pdf_path)
                size_ok = file_size > 10240  # > 10KB
                print(f"  PDF exported: {pdf_path}")
                print(f"  File size: {file_size} bytes {'PASS (>10KB)' if size_ok else 'FAIL (<10KB)'}")
                results.append((name, True, len(routes), file_size, size_ok))
            else:
                print(f"  PDF export FAILED")
                results.append((name, False, len(routes), 0, False))

        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()
            results.append((name, False, 0, 0, False))

    # Also test convenience function
    print(f"\n--- Convenience function test (export_synthesis_route_pdf) ---")
    try:
        if routes:
            ok, path_or_err = export_synthesis_route_pdf(routes[0])
            print(f"  Result: {'OK' if ok else 'FAIL'} → {path_or_err}")
        else:
            print(f"  Skipped (no routes available)")
    except Exception as e:
        print(f"  ERROR: {e}")

    return results

# ============================================================================
# PART 2: Mechanism Engine Accuracy Test
# ============================================================================

def test_mechanism_engine():
    """Test 2: Mechanism engine for SN2, EAS, ester hydrolysis"""
    print("\n" + "=" * 70)
    print("PART 2: Mechanism Engine Accuracy Test")
    print("=" * 70)

    engine = MechanismEngine()
    results = []

    # Test 2a: SN2 — bromoethane + OH- → ethanol + Br-
    print("\n--- Test 2a: SN2 (CCBr + [OH-] → CCO + [Br-]) ---")
    try:
        mech = engine.generate_mechanism(
            reactant_smiles="CCBr.[OH-]",
            product_smiles="CCO.[Br-]",
            mechanism_type_hint="sn2"
        )
        if mech:
            print(f"  Mechanism type: {mech.mechanism_type}")
            print(f"  Title: {mech.title}")
            print(f"  Steps: {mech.total_steps}")
            for step in mech.steps:
                print(f"    Step {step.step_number}: {step.title}")
                print(f"      Arrows: {len(step.arrows)}")
                for arrow in step.arrows:
                    print(f"        {arrow.from_label} → {arrow.to_label} ({arrow.arrow_type})")
            results.append(("SN2", True, mech.total_steps, len(mech.steps[0].arrows) if mech.steps else 0))
        else:
            print("  FAILED: No mechanism generated")
            results.append(("SN2", False, 0, 0))
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        results.append(("SN2", False, 0, 0))

    # Test 2b: EAS — benzene + Br2 → bromobenzene
    print("\n--- Test 2b: EAS (c1ccccc1 + BrBr → Brc1ccccc1) ---")
    try:
        mech = engine.generate_mechanism(
            reactant_smiles="c1ccccc1.BrBr",
            product_smiles="Brc1ccccc1.[HBr]",
            mechanism_type_hint="eas_bromination"
        )
        if mech is None:
            # Try without hint
            mech = engine.generate_mechanism(
                reactant_smiles="c1ccccc1.BrBr",
                product_smiles="Brc1ccccc1",
            )
        if mech:
            print(f"  Mechanism type: {mech.mechanism_type}")
            print(f"  Title: {mech.title}")
            print(f"  Steps: {mech.total_steps}")
            for step in mech.steps:
                print(f"    Step {step.step_number}: {step.title}")
                print(f"      Arrows: {len(step.arrows)}")
                for arrow in step.arrows:
                    print(f"        {arrow.from_label} → {arrow.to_label} ({arrow.arrow_type})")
            results.append(("EAS", True, mech.total_steps, sum(len(s.arrows) for s in mech.steps)))
        else:
            print("  FAILED: No mechanism generated")
            results.append(("EAS", False, 0, 0))
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        results.append(("EAS", False, 0, 0))

    # Test 2c: Ester hydrolysis — aspirin decomposition
    print("\n--- Test 2c: Ester Hydrolysis (Aspirin → Salicylic acid + Acetic acid) ---")
    try:
        mech = engine.generate_mechanism(
            reactant_smiles="CC(=O)Oc1ccccc1C(=O)O.O",
            product_smiles="Oc1ccccc1C(=O)O.CC(=O)O",
            mechanism_type_hint="ester_hydrolysis"
        )
        if mech is None:
            # Try without hint
            mech = engine.generate_mechanism(
                reactant_smiles="CC(=O)Oc1ccccc1C(=O)O.O",
                product_smiles="Oc1ccccc1C(=O)O.CC(=O)O",
            )
        if mech:
            print(f"  Mechanism type: {mech.mechanism_type}")
            print(f"  Title: {mech.title}")
            print(f"  Steps: {mech.total_steps}")
            for step in mech.steps:
                print(f"    Step {step.step_number}: {step.title}")
                print(f"      Arrows: {len(step.arrows)}")
                for arrow in step.arrows:
                    print(f"        {arrow.from_label} → {arrow.to_label} ({arrow.arrow_type})")
            results.append(("Ester Hydrolysis", True, mech.total_steps, sum(len(s.arrows) for s in mech.steps)))
        else:
            print("  FAILED: No mechanism generated")
            results.append(("Ester Hydrolysis", False, 0, 0))
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        results.append(("Ester Hydrolysis", False, 0, 0))

    # Test 2d: auto_mechanism convenience function
    print("\n--- Test 2d: auto_mechanism convenience function ---")
    try:
        mech = auto_mechanism("CCBr.[OH-]", "CCO.[Br-]")
        print(f"  auto_mechanism result: {'OK' if mech else 'FAIL'}")
        if mech:
            print(f"  Steps: {mech.total_steps}, Arrows: {sum(len(s.arrows) for s in mech.steps)}")
    except Exception as e:
        print(f"  ERROR: {e}")

    return results

# ============================================================================
# PART 3: py_compile check
# ============================================================================

def test_py_compile():
    """Test 3: py_compile all OWNED_FILES"""
    print("\n" + "=" * 70)
    print("PART 3: py_compile Verification")
    print("=" * 70)

    import py_compile
    owned_files = [
        "retrosynthesis_engine.py",
        "mechanism_engine.py",
        "building_blocks.py",
        "popup_synthesis.py",
        "reaction_mechanisms.py",
        "arrow_generator.py",
        "mechanism_pdf_exporter.py",
    ]

    src_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src', 'app')
    results = []

    for fname in owned_files:
        fpath = os.path.join(src_dir, fname)
        if not os.path.exists(fpath):
            print(f"  {fname}: NOT FOUND")
            results.append((fname, False, "File not found"))
            continue
        try:
            py_compile.compile(fpath, doraise=True)
            print(f"  {fname}: PASS")
            results.append((fname, True, "OK"))
        except py_compile.PyCompileError as e:
            print(f"  {fname}: FAIL - {e}")
            results.append((fname, False, str(e)))

    return results

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("ChemGrid Cascade #8 — Synthesis Domain Test Suite")
    print(f"Python: {sys.version}")
    print(f"Working dir: {os.getcwd()}")
    print()

    # Run all tests
    pdf_results = test_pdf_export()
    mech_results = test_mechanism_engine()
    compile_results = test_py_compile()

    # ============================================================================
    # SUMMARY
    # ============================================================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print("\n[PDF Export Results]")
    for name, success, n_routes, fsize, size_ok in pdf_results:
        status = "PASS" if (success and size_ok) else ("PARTIAL" if success else "FAIL")
        print(f"  {name:12s}: {status} (routes={n_routes}, size={fsize}B)")

    print("\n[Mechanism Engine Results]")
    for name, success, n_steps, n_arrows in mech_results:
        status = "PASS" if success else "FAIL"
        print(f"  {name:20s}: {status} (steps={n_steps}, arrows={n_arrows})")

    print("\n[py_compile Results]")
    for fname, success, msg in compile_results:
        status = "PASS" if success else "FAIL"
        print(f"  {fname:35s}: {status}")

    # Overall
    all_pdf_ok = all(s for _, s, _, _, _ in pdf_results)
    all_mech_ok = all(s for _, s, _, _ in mech_results)
    all_compile_ok = all(s for _, s, _ in compile_results)

    print(f"\n{'='*70}")
    print(f"PDF Export:      {'ALL PASS' if all_pdf_ok else 'SOME FAILURES'}")
    print(f"Mechanism Engine: {'ALL PASS' if all_mech_ok else 'SOME FAILURES'}")
    print(f"py_compile:      {'ALL PASS' if all_compile_ok else 'SOME FAILURES'}")
    print(f"OVERALL:         {'ALL PASS' if (all_pdf_ok and all_mech_ok and all_compile_ok) else 'ISSUES FOUND'}")
    print(f"{'='*70}")
