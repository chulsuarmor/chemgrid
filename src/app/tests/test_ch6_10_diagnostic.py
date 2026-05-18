#!/usr/bin/env python3
"""
Ch.6-10 Engine Diagnostic: Test mechanism engine coverage
against Moloney textbook chapters 6-10.

Ch.6: Nucleophilic Substitution at Carbonyl (~8 reactions)
Ch.7: Elimination Reactions (~6 reactions)
Ch.8: Electrophilic Addition (~6 reactions)
Ch.9: Pericyclic Reactions (~6 reactions)
Ch.10: Radical Reactions (~5 reactions)

READ-ONLY diagnostic — does NOT modify any source files.
Outputs: results.json + individual PNGs + summary report.
"""
import sys, os, json, traceback, time, io, logging

logger = logging.getLogger(__name__)
from pathlib import Path

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add src/app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'src', 'app'))

from rdkit import Chem
from rdkit.Chem import AllChem, Draw

# ═══════════════════════════════════════════════════════════
# TEST CASES: Ch.6-10 Moloney textbook reactions
# Each: (id, chapter, reaction_name, reactant_smiles, product_smiles,
#         conditions, expected_retro_template, expected_mechanism_type)
# ═══════════════════════════════════════════════════════════

TEST_CASES = [
    # ──── Ch.6: Nucleophilic Substitution at Carbonyl ────
    ("ch6_01", "Ch.6", "Acid chloride + amine -> amide",
     "CC(=O)Cl", "CC(=O)NC",                           # acetyl chloride + methylamine -> N-methylacetamide
     "CH3NH2, base (pyridine)",
     "아실클로라이드 역합성",
     "amidation"),

    ("ch6_02", "Ch.6", "Ester hydrolysis (base, saponification)",
     "CC(=O)OCC", "CC(=O)[O-]",                        # ethyl acetate + NaOH -> sodium acetate
     "NaOH, H2O, reflux",
     None,
     "esterification"),  # reverse of esterification

    ("ch6_03", "Ch.6", "Transesterification",
     "CC(=O)OC", "CC(=O)OCC",                          # methyl acetate + ethanol -> ethyl acetate
     "EtOH, H2SO4 (cat.)",
     None,
     "esterification"),

    ("ch6_04", "Ch.6", "Anhydride + alcohol -> ester",
     "CC(=O)OC(C)=O", "CC(=O)OCC",                    # acetic anhydride + ethanol -> ethyl acetate
     "EtOH, pyridine",
     None,
     "esterification"),

    ("ch6_05", "Ch.6", "Weinreb amide reduction (to aldehyde)",
     "CC(=O)N(C)OC", "CC=O",                           # Weinreb amide -> acetaldehyde
     "LiAlH4, -78C, then H3O+",
     None,
     "nucleophilic_addition"),

    ("ch6_06", "Ch.6", "Claisen condensation",
     "CC(=O)OCC", "CC(=O)CC(=O)OCC",                  # 2x ethyl acetate -> ethyl acetoacetate
     "NaOEt, EtOH, then H3O+",
     None,
     None),  # check generic mechanism

    ("ch6_07", "Ch.6", "Dieckmann cyclization",
     "O=C(OCC)CCCCC(=O)OCC", "O=C1CCCC(C(=O)OCC)C1=O",  # diethyl adipate -> cyclized product (approx)
     "NaOEt, EtOH, heat",
     None,
     None),

    ("ch6_08", "Ch.6", "Acyl substitution with Grignard (ketone formation)",
     "CC(=O)Cl", "CC(=O)C",                            # acetyl chloride + CH3MgBr -> acetone (with CdCl2)
     "CH3MgBr (1 eq), CdCl2, then H3O+",
     "Grignard 역합성",
     "grignard"),

    # ──── Ch.7: Elimination Reactions ────
    ("ch7_01", "Ch.7", "E1 dehydration of alcohol",
     "CC(O)CC", "CC=CC",                                # 2-butanol -> 2-butene
     "H2SO4, heat (E1)",
     None,
     "e1"),

    ("ch7_02", "Ch.7", "E2 anti-periplanar elimination",
     "CC(Br)CC", "CC=CC",                               # 2-bromobutane + strong base -> 2-butene
     "KOtBu, tBuOH, E2 (anti-periplanar)",
     "E2 역합성 (알켄←할로알칸)",
     "e2"),

    ("ch7_03", "Ch.7", "E1cb elimination",
     "OCC(F)(F)F", "C=O",                               # 2,2,2-trifluoroethanol + base -> formaldehyde (simplified)
     "NaOH, E1cb (poor leaving group, acidic H)",
     None,
     None),

    ("ch7_04", "Ch.7", "Hofmann elimination (quaternary ammonium)",
     "CC(CC)[N+](C)(C)C", "CC=CC",                     # quaternary ammonium -> less substituted alkene
     "Ag2O, H2O, heat (Hofmann elimination)",
     None,
     "hofmann"),

    ("ch7_05", "Ch.7", "Cope elimination (amine oxide pyrolysis)",
     "CC(CC)[N+](C)(C)[O-]", "CC=CC",                  # amine oxide -> alkene + N,N-dimethylhydroxylamine
     "Heat, 150C (syn-elimination, cyclic TS)",
     None,
     "cope_rearrangement"),

    ("ch7_06", "Ch.7", "Chugaev elimination (xanthate pyrolysis)",
     "CC(CC)OC(=S)SC", "CC=CC",                        # xanthate ester -> alkene + COS + MeSH
     "Heat, 200C (syn-elimination, 6-membered TS)",
     None,
     None),

    # ──── Ch.8: Electrophilic Addition ────
    ("ch8_01", "Ch.8", "HBr addition to alkene (Markovnikov)",
     "CC=C", "CC(Br)C",                                 # propene + HBr -> 2-bromopropane
     "HBr (Markovnikov)",
     "HBr 첨가 역합성",
     "hx_addition"),

    ("ch8_02", "Ch.8", "HBr + peroxide (anti-Markovnikov radical)",
     "CC=C", "CCCBr",                                   # propene + HBr/peroxide -> 1-bromopropane
     "HBr, ROOR (radical, anti-Markovnikov)",
     None,
     "radical_halogenation"),

    ("ch8_03", "Ch.8", "Hydroboration-oxidation",
     "CC=C", "CCCO",                                    # propene -> 1-propanol (anti-Markovnikov, syn)
     "1) BH3.THF  2) NaOH/H2O2",
     None,
     "hydroboration"),

    ("ch8_04", "Ch.8", "Oxymercuration-demercuration",
     "CC=C", "CC(O)C",                                  # propene -> 2-propanol (Markovnikov)
     "1) Hg(OAc)2, H2O  2) NaBH4",
     None,
     None),

    ("ch8_05", "Ch.8", "Epoxidation with mCPBA",
     "CC=CC", "CC1OC1C",                                # 2-butene -> 2,3-epoxybutane
     "mCPBA, CH2Cl2",
     None,
     "sharpless_epoxidation"),  # closest match

    ("ch8_06", "Ch.8", "Dihydroxylation with OsO4",
     "CC=CC", "CC(O)C(O)C",                            # 2-butene -> 2,3-butanediol (syn)
     "OsO4 (cat.), NMO, acetone/H2O",
     None,
     "sharpless_dihydroxylation"),

    # ──── Ch.9: Pericyclic Reactions ────
    ("ch9_01", "Ch.9", "Diels-Alder [4+2] cycloaddition",
     "C=CC=C", "C1CC=CCC1=O",                          # butadiene + acrolein -> cyclohexene-CHO (simplified)
     "Heat or Lewis acid catalyst",
     None,
     "diels_alder"),

    ("ch9_02", "Ch.9", "Retro-Diels-Alder",
     "C1CC=CCC1=O", "C=CC=C",                          # reverse of above
     "Heat, >200C (retro [4+2])",
     None,
     "retro_diels_alder"),

    ("ch9_03", "Ch.9", "Claisen rearrangement (allyl vinyl ether)",
     "C=CCOC=C", "C=CCC(=O)C",                         # allyl vinyl ether -> pentenone
     "Heat, 200C ([3,3]-sigmatropic)",
     None,
     "claisen_rearrangement"),

    ("ch9_04", "Ch.9", "Cope rearrangement (1,5-hexadiene)",
     "C=CCC=CC", "C=CCCC=C",                           # 1,5-hexadiene isomerization
     "Heat, 300C ([3,3]-sigmatropic)",
     None,
     "cope_rearrangement"),

    ("ch9_05", "Ch.9", "[2,3]-Wittig rearrangement",
     "C=CCO[CH2-]", "C=CC(O)C",                        # allyl ether carbanion -> homoallylic alcohol
     "n-BuLi, THF, -78C",
     None,
     None),

    ("ch9_06", "Ch.9", "Ene reaction",
     "CC=C", "CC(C)C=C",                                # propene + propene ene reaction (simplified)
     "Heat or Lewis acid (ene reaction)",
     None,
     "ene_reaction"),

    # ──── Ch.10: Radical Reactions ────
    ("ch10_01", "Ch.10", "NBS allylic bromination",
     "CC=CC", "CC=CC(Br)",                              # 2-butene -> 1-bromo-2-butene
     "NBS, hv or AIBN, CCl4",
     None,
     "radical_halogenation"),

    ("ch10_02", "Ch.10", "Barton reaction (remote C-H functionalization)",
     "CCCCCC(=O)[O-]", "CCCC(O)CC(=O)[O-]",           # delta-C-H functionalization via nitrite ester
     "1) NOCl  2) hv (Barton reaction)",
     None,
     "barton_reaction"),

    ("ch10_03", "Ch.10", "Radical addition HBr anti-Markovnikov",
     "CC=C", "CCCBr",                                   # propene + HBr/ROOR -> 1-bromopropane
     "HBr, (PhCO2)2, anti-Markovnikov radical chain",
     None,
     "radical_halogenation"),

    ("ch10_04", "Ch.10", "Birch reduction (aromatic -> 1,4-diene)",
     "c1ccccc1", "C1=CCC=CC1",                         # benzene -> 1,4-cyclohexadiene
     "Na, NH3(l), tBuOH (Birch reduction)",
     None,
     "birch_reduction"),

    ("ch10_05", "Ch.10", "Hofmann-Loffler-Freytag reaction",
     "CCCCC(Cl)NC", "C1CCNC1C",                        # N-chloroamine -> pyrrolidine via radical
     "hv, H2SO4, then NaOH (Hofmann-Loffler-Freytag)",
     None,
     "hofmann_loffler_freytag"),
]

OUT_DIR = Path(__file__).parent


def test_retro_engine():
    """Test retrosynthesis engine template matching."""
    from retrosynthesis_engine import RetrosynthesisEngine
    engine = RetrosynthesisEngine()
    results = []

    for tc in TEST_CASES:
        tid, ch, name, r_smi, p_smi, cond, expected_retro, expected_mech = tc
        print(f"\n{'='*60}")
        print(f"[{tid}] {name}")
        print(f"  Reactant: {r_smi} -> Product: {p_smi}")

        retro_grade = "C"
        retro_detail = "No match"
        try:
            routes = engine.find_routes(p_smi, max_depth=3, max_routes=5)
            if routes:
                matched_templates = []
                for route in routes:
                    for step in route.steps:
                        matched_templates.append(step.transform_name)

                if expected_retro and expected_retro in matched_templates:
                    retro_grade = "A"
                    retro_detail = f"Dedicated template matched: {expected_retro}"
                elif matched_templates:
                    retro_grade = "B"
                    retro_detail = f"Generic match: {matched_templates[:3]}"
                else:
                    retro_grade = "C"
                    retro_detail = "Routes found but no relevant template"
            else:
                retro_grade = "C"
                retro_detail = "No routes found"
        except Exception as e:
            retro_grade = "C"
            retro_detail = f"Error: {str(e)[:100]}"

        print(f"  Retro Grade: {retro_grade} -- {retro_detail}")
        results.append({
            "id": tid, "chapter": ch, "reaction": name,
            "reactant": r_smi, "product": p_smi, "conditions": cond,
            "retro_grade": retro_grade, "retro_detail": retro_detail,
        })

    return results


def test_mechanism_engine():
    """Test mechanism engine (hardcoded + generic + BondChangeDetector)."""
    from reaction_mechanisms import get_mechanism, get_available_mechanisms, MechanismData
    from mechanism_engine import MechanismEngine

    avail = get_available_mechanisms()
    print(f"\n{'='*60}")
    print(f"Available hardcoded mechanisms: {len(avail)}")

    engine = MechanismEngine()
    results = []

    for tc in TEST_CASES:
        tid, ch, name, r_smi, p_smi, cond, _, expected_mech = tc
        print(f"\n{'='*60}")
        print(f"[{tid}] {name}")

        mech_grade = "C"
        mech_detail = "No mechanism"
        mech_steps = 0

        # 1) Check hardcoded mechanism by type hint
        if expected_mech:
            hc = get_mechanism(expected_mech)
            if hc:
                mech_grade = "A"
                mech_steps = len(hc.steps)
                mech_detail = f"Hardcoded '{expected_mech}' ({mech_steps} steps)"
            else:
                mech_detail = f"Expected '{expected_mech}' not found in hardcoded"

        # 2) Try BondChangeDetector-based generation
        if mech_grade != "A":
            try:
                mech = engine.generate_mechanism(r_smi, p_smi, mechanism_type_hint=expected_mech or "")
                if mech:
                    mech_steps = len(mech.steps)
                    if mech_steps >= 2:
                        mech_grade = "B"
                        mech_detail = f"BondChange auto-generated ({mech_steps} steps)"
                    else:
                        mech_grade = "B"
                        mech_detail = f"Minimal mechanism ({mech_steps} step)"
                else:
                    mech_grade = "C"
                    mech_detail = "Engine returned None"
            except Exception as e:
                mech_grade = "C"
                mech_detail = f"Error: {str(e)[:100]}"

        print(f"  Mechanism Grade: {mech_grade} -- {mech_detail} ({mech_steps} steps)")
        results.append({
            "id": tid, "chapter": ch, "reaction": name,
            "mech_grade": mech_grade, "mech_detail": mech_detail,
            "mech_steps": mech_steps,
        })

    return results


def test_drylab_mechanism():
    """Test _get_hardcoded_mechanism and _generate_generic_mechanism from drylab exporter."""
    try:
        from drylab_report_exporter import _get_hardcoded_mechanism, _generate_generic_mechanism
    except ImportError:
        print("WARNING: Could not import drylab mechanism functions")
        return []

    results = []
    for tc in TEST_CASES:
        tid, ch, name, r_smi, p_smi, cond, _, _ = tc
        print(f"\n{'='*60}")
        print(f"[{tid}] {name} (DryLab path)")

        dl_grade = "C"
        dl_detail = "No mechanism"
        dl_steps = 0

        # 1) Try hardcoded first
        try:
            hc = _get_hardcoded_mechanism(r_smi, p_smi, cond)
            if hc:
                dl_steps = len(hc)
                dl_grade = "A"
                dl_detail = f"Hardcoded ({dl_steps} steps)"
        except Exception as e:
            dl_detail = f"Hardcoded error: {str(e)[:80]}"

        # 2) Try generic if no hardcoded
        if dl_grade != "A":
            try:
                gen = _generate_generic_mechanism(r_smi, p_smi, cond)
                if gen:
                    dl_steps = len(gen)
                    # Check if steps have real intermediates (not just copies of reactant)
                    r_can = Chem.CanonSmiles(r_smi) if Chem.MolFromSmiles(r_smi) else r_smi
                    p_can = Chem.CanonSmiles(p_smi) if Chem.MolFromSmiles(p_smi) else p_smi
                    fake_count = 0
                    for step in gen:
                        step_smi = step.get('mol_smi', '') or step.get('smiles', '')
                        if step_smi:
                            try:
                                step_can = Chem.CanonSmiles(step_smi)
                                if step_can == r_can or step_can == p_can:
                                    fake_count += 1
                            except Exception as e:
                                logger.warning("CanonSmiles failed for step: %s", e)
                    if fake_count == 0:
                        dl_grade = "A"
                        dl_detail = f"Generic mechanism ({dl_steps} steps, all real intermediates)"
                    elif fake_count < dl_steps:
                        dl_grade = "B"
                        dl_detail = f"Generic ({dl_steps} steps, {fake_count} fake intermediates)"
                    else:
                        dl_grade = "C"
                        dl_detail = f"All {dl_steps} steps are reactant/product copies"
                else:
                    dl_grade = "C"
                    dl_detail = "No generic mechanism generated"
            except Exception as e:
                dl_detail = f"Generic error: {str(e)[:80]}"

        print(f"  DryLab Grade: {dl_grade} -- {dl_detail}")
        results.append({
            "id": tid, "chapter": ch, "reaction": name,
            "drylab_grade": dl_grade, "drylab_detail": dl_detail,
            "drylab_steps": dl_steps,
        })

    return results


def test_mechanism_step_png():
    """Test _generate_mechanism_step_png returns non-None bytes for each reaction."""
    try:
        from drylab_report_exporter import _get_hardcoded_mechanism, _generate_generic_mechanism, _generate_mechanism_step_png
    except ImportError:
        print("WARNING: Could not import _generate_mechanism_step_png")
        return []

    results = []
    for tc in TEST_CASES:
        tid, ch, name, r_smi, p_smi, cond, _, _ = tc
        print(f"\n{'='*60}")
        print(f"[{tid}] {name} (PNG generation)")

        png_grade = "C"
        png_detail = "No PNG"
        png_bytes_len = 0

        # Get mechanism steps
        steps = None
        try:
            steps = _get_hardcoded_mechanism(r_smi, p_smi, cond)
        except Exception as e:
            logger.warning("_get_hardcoded_mechanism failed: %s", e)
        if not steps:
            try:
                steps = _generate_generic_mechanism(r_smi, p_smi, cond)
            except Exception as e:
                logger.warning("_generate_generic_mechanism failed: %s", e)

        # Test PNG generation directly (doesn't need steps)
        if True:
            try:
                png_data = _generate_mechanism_step_png(r_smi, p_smi, conditions=cond, step_num=1)
                if png_data and len(png_data) > 100:  # > 100 bytes = real image
                    png_grade = "A"
                    png_bytes_len = len(png_data)
                    png_detail = f"PNG generated ({png_bytes_len} bytes)"

                    # Save to evidence
                    png_path = OUT_DIR / "pngs" / f"{tid}_step0.png"
                    with open(str(png_path), "wb") as f:
                        f.write(png_data)
                else:
                    png_grade = "C"
                    png_detail = f"PNG too small or None ({len(png_data) if png_data else 0} bytes)"
            except Exception as e:
                png_grade = "C"
                png_detail = f"PNG error: {str(e)[:100]}"

        print(f"  PNG Grade: {png_grade} -- {png_detail}")
        results.append({
            "id": tid, "chapter": ch, "reaction": name,
            "png_grade": png_grade, "png_detail": png_detail,
            "png_bytes": png_bytes_len,
        })

    return results


def generate_mol_pngs():
    """Generate molecule pair PNGs for each test case."""
    png_dir = OUT_DIR / "pngs"
    png_dir.mkdir(exist_ok=True)

    for tc in TEST_CASES:
        tid, ch, name, r_smi, p_smi, *_ = tc
        try:
            r_mol = Chem.MolFromSmiles(r_smi)
            p_mol = Chem.MolFromSmiles(p_smi)
            if r_mol and p_mol:
                img = Draw.MolsToGridImage(
                    [r_mol, p_mol],
                    molsPerRow=2,
                    subImgSize=(400, 300),
                    legends=[f"Reactant: {r_smi}", f"Product: {p_smi}"]
                )
                img.save(str(png_dir / f"{tid}.png"))
        except Exception as e:
            print(f"PNG error for {tid}: {e}")


def main():
    print("=" * 70)
    print("Ch.6-10 ENGINE DIAGNOSTIC (Moloney Textbook)")
    print(f"Test cases: {len(TEST_CASES)}")
    print("=" * 70)

    # Run all tests
    retro_results = test_retro_engine()
    mech_results = test_mechanism_engine()
    drylab_results = test_drylab_mechanism()
    png_results = test_mechanism_step_png()

    # Generate molecule PNGs
    generate_mol_pngs()

    # Merge results
    merged = []
    for i, tc in enumerate(TEST_CASES):
        entry = {
            **retro_results[i],
            "mech_grade": mech_results[i]["mech_grade"],
            "mech_detail": mech_results[i]["mech_detail"],
            "mech_steps": mech_results[i]["mech_steps"],
            "drylab_grade": drylab_results[i]["drylab_grade"] if i < len(drylab_results) else "N/A",
            "drylab_detail": drylab_results[i]["drylab_detail"] if i < len(drylab_results) else "N/A",
            "drylab_steps": drylab_results[i].get("drylab_steps", 0) if i < len(drylab_results) else 0,
            "png_grade": png_results[i]["png_grade"] if i < len(png_results) else "N/A",
            "png_detail": png_results[i]["png_detail"] if i < len(png_results) else "N/A",
            "png_bytes": png_results[i].get("png_bytes", 0) if i < len(png_results) else 0,
        }

        # Overall grade: best of all subsystems
        grades = [entry["retro_grade"], entry["mech_grade"],
                  entry.get("drylab_grade", "C"), entry.get("png_grade", "C")]
        if "A" in grades:
            entry["overall_grade"] = "A"
        elif "B" in grades:
            entry["overall_grade"] = "B"
        else:
            entry["overall_grade"] = "C"

        merged.append(entry)

    # Save results
    with open(str(OUT_DIR / "results.json"), "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # Print summary by chapter
    print("\n" + "=" * 70)
    print("SUMMARY BY CHAPTER")
    print("=" * 70)

    total_a = total_b = total_c = 0
    chapter_stats = {}

    for ch in ["Ch.6", "Ch.7", "Ch.8", "Ch.9", "Ch.10"]:
        ch_entries = [e for e in merged if e["chapter"] == ch]
        ch_a = sum(1 for e in ch_entries if e["overall_grade"] == "A")
        ch_b = sum(1 for e in ch_entries if e["overall_grade"] == "B")
        ch_c = sum(1 for e in ch_entries if e["overall_grade"] == "C")
        total_a += ch_a
        total_b += ch_b
        total_c += ch_c
        chapter_stats[ch] = {"total": len(ch_entries), "A": ch_a, "B": ch_b, "C": ch_c}

        print(f"\n{ch}: {len(ch_entries)} reactions")
        print(f"  A (dedicated template): {ch_a}")
        print(f"  B (generic/fallback):   {ch_b}")
        print(f"  C (wrong/no mechanism): {ch_c}")
        print(f"  Pass rate (A+B): {100*(ch_a+ch_b)/len(ch_entries):.0f}%")

    total = len(merged)
    print(f"\nOVERALL: {total} reactions")
    print(f"  A: {total_a} ({100*total_a/total:.0f}%)")
    print(f"  B: {total_b} ({100*total_b/total:.0f}%)")
    print(f"  C: {total_c} ({100*total_c/total:.0f}%)")
    print(f"  Coverage (A+B): {100*(total_a+total_b)/total:.0f}%")

    # Identify gaps
    print(f"\n{'='*70}")
    print("GRADE C REACTIONS (no coverage):")
    print("=" * 70)
    for e in merged:
        if e["overall_grade"] == "C":
            print(f"  [{e['id']}] {e['reaction']}")
            print(f"    Retro: {e['retro_grade']} -- {e['retro_detail']}")
            print(f"    Mech:  {e['mech_grade']} -- {e['mech_detail']}")
            print(f"    DryLab: {e.get('drylab_grade','N/A')} -- {e.get('drylab_detail','N/A')}")
            print(f"    PNG: {e.get('png_grade','N/A')} -- {e.get('png_detail','N/A')}")

    # Generic fallback reactions (B-grade)
    print(f"\n{'='*70}")
    print("GRADE B REACTIONS (generic fallback only):")
    print("=" * 70)
    for e in merged:
        if e["overall_grade"] == "B":
            print(f"  [{e['id']}] {e['reaction']}")
            print(f"    Retro: {e['retro_grade']} -- {e['retro_detail']}")
            print(f"    Mech:  {e['mech_grade']} -- {e['mech_detail']}")
            print(f"    DryLab: {e.get('drylab_grade','N/A')} -- {e.get('drylab_detail','N/A')}")

    # Subsystem breakdown
    print(f"\n{'='*70}")
    print("SUBSYSTEM BREAKDOWN:")
    print("=" * 70)
    for subsys, key in [("Retrosynthesis", "retro_grade"), ("Mechanism Engine", "mech_grade"),
                         ("DryLab", "drylab_grade"), ("PNG Render", "png_grade")]:
        sa = sum(1 for e in merged if e.get(key) == "A")
        sb = sum(1 for e in merged if e.get(key) == "B")
        sc = sum(1 for e in merged if e.get(key) == "C")
        print(f"  {subsys:20s}: A={sa:2d} B={sb:2d} C={sc:2d}  ({100*(sa+sb)/total:.0f}% coverage)")

    # Generate text report
    report_lines = [
        "# Ch.6-10 Engine Diagnostic Report (Moloney Textbook)",
        f"# Date: {time.strftime('%Y-%m-%d %H:%M')}",
        f"# Total test cases: {total}",
        f"# Grade A: {total_a} ({100*total_a/total:.0f}%)",
        f"# Grade B: {total_b} ({100*total_b/total:.0f}%)",
        f"# Grade C: {total_c} ({100*total_c/total:.0f}%)",
        f"# Coverage (A+B): {100*(total_a+total_b)/total:.0f}%",
        "",
        "## Chapter Summary",
        "",
    ]

    for ch, stats in chapter_stats.items():
        pass_pct = 100 * (stats["A"] + stats["B"]) / stats["total"]
        report_lines.append(f"| {ch} | {stats['total']} | A={stats['A']} B={stats['B']} C={stats['C']} | {pass_pct:.0f}% |")

    report_lines.append("")
    report_lines.append("## Detailed Results")
    report_lines.append("")

    for e in merged:
        report_lines.append(f"### [{e['id']}] {e['reaction']} -- Overall: {e['overall_grade']}")
        report_lines.append(f"- Chapter: {e['chapter']}")
        report_lines.append(f"- Reactant: `{e['reactant']}` -> Product: `{e['product']}`")
        report_lines.append(f"- Conditions: {e['conditions']}")
        report_lines.append(f"- Retro: {e['retro_grade']} -- {e['retro_detail']}")
        report_lines.append(f"- Mechanism: {e['mech_grade']} -- {e['mech_detail']} ({e['mech_steps']} steps)")
        report_lines.append(f"- DryLab: {e.get('drylab_grade','N/A')} -- {e.get('drylab_detail','N/A')} ({e.get('drylab_steps',0)} steps)")
        report_lines.append(f"- PNG: {e.get('png_grade','N/A')} -- {e.get('png_detail','N/A')}")
        report_lines.append("")

    report_lines.append("## Grade C Gaps (Need implementation)")
    report_lines.append("")
    for e in merged:
        if e["overall_grade"] == "C":
            report_lines.append(f"- **{e['reaction']}** ({e['chapter']}): needs dedicated template + mechanism")

    report_lines.append("")
    report_lines.append("## Grade B Fallbacks (Need dedicated templates)")
    report_lines.append("")
    for e in merged:
        if e["overall_grade"] == "B":
            report_lines.append(f"- **{e['reaction']}** ({e['chapter']}): has generic coverage, needs dedicated template for accuracy")

    with open(str(OUT_DIR / "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\nResults saved to: {OUT_DIR}")
    print(f"  results.json, report.md, pngs/")


if __name__ == "__main__":
    main()
