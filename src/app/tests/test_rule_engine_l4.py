#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
L4 (Novel/Unseen) Rule Engine Test
====================================
Tests the MechanismRuleEngine on 10 L4-level exam problems that are
NOT in the gold standard database. These test the engine's ability to
classify and generate mechanisms from first principles (FG detection +
condition parsing + decision tree).

Uses the EXACT L4 problems from test_exam_problems.py.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mechanism_rule_engine import MechanismRuleEngine

engine = MechanismRuleEngine()

# L4 Novel problems - from test_exam_problems.py (exact SMILES)
l4_problems = [
    ("L4_01", "Acyloin Condensation", "O=C(OCC)CCCCC(=O)OCC", "OC1CCCCC1=O",
     "Na, xylene, TMSCl, acyloin condensation", 4),
    ("L4_02", "Thorpe-Ziegler", "N#CCCCCCC#N", "N=C1CCCCC1C#N",
     "NaH, THF, Thorpe-Ziegler cyclization", 4),
    ("L4_03", "Darzens Condensation", "O=Cc1ccccc1", "CCOC(=O)C1OC1c1ccccc1",
     "ClCH2COOEt, NaOEt, Darzens", 4),
    ("L4_04", "Knoevenagel Condensation", "O=Cc1ccccc1", "O=C(O)/C(=C/c1ccccc1)C(=O)O",
     "piperidine, AcOH, Knoevenagel", 4),
    ("L4_05", "Baylis-Hillman", "O=Cc1ccccc1", "OC(c1ccccc1)C(=C)C(=O)OC",
     "DABCO, methyl acrylate, Baylis-Hillman", 5),
    ("L4_06", "Staudinger Ligation", "c1ccc(cc1)[N-][N+]#N", "Nc1ccccc1",
     "PPh3, H2O, Staudinger ligation", 4),
    ("L4_07", "Kulinkovich", "CC(=O)OCC", "OC1(C)CC1",
     "Ti(OiPr)4, EtMgBr, Kulinkovich", 4),
    ("L4_08", "Henry Reaction", "O=Cc1ccccc1", "OC(c1ccccc1)C[N+](=O)[O-]",
     "CH3NO2, NaOH, Henry, nitroaldol", 3),
    ("L4_09", "Trost Allylation", "C=CCOC(=O)C", "C=CCC(C(=O)OC)C(=O)OC",
     "Pd(PPh3)4, dimethyl malonate, NaH, Trost allylation", 4),
    ("L4_10", "Mukaiyama Aldol", "O=Cc1ccccc1", "OC(c1ccccc1)CC(=O)C",
     "TiCl4, TMS enol ether, CH2Cl2, Mukaiyama aldol", 3),
]

# Results tracking
results = {
    "classified": 0,
    "generated": 0,
    "drylab": 0,
    "failed_classify": [],
    "failed_generate": [],
    "failed_drylab": [],
    "details": [],
}

print("=" * 70)
print("  L4 (Novel/Unseen) Rule Engine Test")
print("  Testing 10 reactions NOT in gold standard database")
print("=" * 70)

for pid, name, rsmi, psmi, cond, expected_steps in l4_problems:
    print(f"\n{'=' * 60}")
    print(f"  {pid}: {name}")
    print(f"  Reactant: {rsmi}")
    print(f"  Product:  {psmi}")
    print(f"  Conditions: {cond}")
    print(f"  Expected min steps: {expected_steps}")

    detail = {"id": pid, "name": name}

    # Test classification
    classification = engine.classify_only(rsmi, psmi, cond)
    if classification:
        results["classified"] += 1
        detail["class"] = f"{classification.reaction_class}/{classification.sub_class}"
        detail["confidence"] = classification.confidence
        detail["patterns"] = classification.pattern_sequence
        detail["fg_r"] = [fg.name for fg in classification.fg_reactant]
        print(f"  [CLASSIFY] {classification.reaction_class}/{classification.sub_class}")
        print(f"    Confidence: {classification.confidence:.2f}")
        print(f"    Patterns: {classification.pattern_sequence}")
        print(f"    FGs (reactant): {[fg.name for fg in classification.fg_reactant]}")
        print(f"    FGs (product):  {[fg.name for fg in classification.fg_product]}")
        print(f"    Conditions: {classification.conditions_parsed}")
    else:
        results["failed_classify"].append(pid)
        detail["class"] = None
        print(f"  [CLASSIFY] FAILED (None)")

    # Test full generation
    result = engine.generate(rsmi, psmi, cond)
    if result:
        results["generated"] += 1
        detail["steps"] = len(result.steps)
        detail["mechanism_type"] = result.mechanism_type
        print(f"  [GENERATE] OK: {result.mechanism_type} ({len(result.steps)} steps)")
        for i, step in enumerate(result.steps):
            desc_short = step.description[:70].replace('\n', ' ')
            print(f"    Step {i+1}: {step.title}")
            print(f"      {desc_short}...")
            print(f"      Arrows: {len(step.arrows)}")
            print(f"      SMILES: {step.reactant_smiles} -> {step.product_smiles}")
    else:
        results["failed_generate"].append(pid)
        detail["steps"] = 0
        print(f"  [GENERATE] FAILED (None)")

    # Test drylab format
    drylab = engine.generate_for_drylab(rsmi, psmi, cond)
    if drylab:
        results["drylab"] += 1
        detail["drylab_steps"] = len(drylab)
        print(f"  [DRYLAB] OK: {len(drylab)} steps")
    else:
        results["failed_drylab"].append(pid)
        detail["drylab_steps"] = 0
        print(f"  [DRYLAB] FAILED (None)")

    results["details"].append(detail)

# ─── Summary ───
print("\n" + "=" * 70)
print("  SUMMARY")
print("=" * 70)
print(f"  Classification: {results['classified']}/10 ({results['classified']*10}%)")
print(f"  Generation:     {results['generated']}/10 ({results['generated']*10}%)")
print(f"  DryLab:         {results['drylab']}/10 ({results['drylab']*10}%)")

if results["failed_classify"]:
    print(f"\n  Failed to classify: {results['failed_classify']}")
if results["failed_generate"]:
    print(f"  Failed to generate: {results['failed_generate']}")

print("\n  Per-problem breakdown:")
for d in results["details"]:
    status = "OK" if d.get("steps", 0) > 0 else "FAIL"
    cls = d.get("class", "N/A")
    steps = d.get("steps", 0)
    conf = d.get("confidence", 0.0)
    print(f"    [{status}] {d['id']}: {d['name']} -> {cls} ({steps} steps, conf={conf:.2f})")

print("\n  Missing patterns / needed improvements:")
for d in results["details"]:
    if d.get("steps", 0) == 0:
        fg = d.get("fg_r", [])
        print(f"    {d['id']} ({d['name']}): FGs={fg}, class={d.get('class', 'None')}")
        # Suggest what's needed
        if d["id"] == "L4_01":
            print(f"      -> Needs: acyloin condensation pattern (radical/anionic, ester -> hydroxy ketone)")
        elif d["id"] == "L4_02":
            print(f"      -> Needs: intramolecular nitrile condensation (Thorpe-Ziegler)")
        elif d["id"] == "L4_03":
            print(f"      -> Needs: Darzens condensation (aldehyde + alpha-halo ester -> glycidic ester)")
        elif d["id"] == "L4_04":
            print(f"      -> Needs: Knoevenagel condensation (aldehyde + active methylene -> alpha,beta-unsat)")
        elif d["id"] == "L4_05":
            print(f"      -> Needs: Baylis-Hillman catalytic cycle (DABCO + acrylate + aldehyde)")
        elif d["id"] == "L4_06":
            print(f"      -> Needs: Staudinger (azide + phosphine -> amine)")
        elif d["id"] == "L4_07":
            print(f"      -> Needs: Kulinkovich cyclopropanation (Ti/EtMgBr + ester)")
        elif d["id"] == "L4_08":
            print(f"      -> Needs: Henry/nitroaldol (aldehyde + nitroalkane -> beta-nitro alcohol)")
        elif d["id"] == "L4_09":
            print(f"      -> Needs: Trost allylation (Pd-catalyzed, allyl + soft nucleophile)")
        elif d["id"] == "L4_10":
            print(f"      -> Needs: Mukaiyama aldol (Lewis acid + TMS enol ether + aldehyde)")

print("\n" + "=" * 70)
print("  TEST COMPLETE")
print("=" * 70)
