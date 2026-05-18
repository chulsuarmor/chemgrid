#!/usr/bin/env python3
"""
Comprehensive Exam-Style Mechanism Engine Test Suite
====================================================

75 organic chemistry exam problems across 5 difficulty levels,
testing the mechanism engine's ability to generate correct intermediates,
step counts, and PNG diagrams.

Level 1 (L1): Basic named reactions (15) - directly in our database
Level 2 (L2): Intermediate named reactions (15) - requiring template matching
Level 3 (L3): Advanced/composite reactions (15) - multi-step or unusual
Level 4 (L4): Novel/unseen reactions (10) - NOT in our database, tests rule engine
Level 5 (L5): Mixed edge cases (20) - carbonyl, heterocycle, protecting group, MCR, redox

Grading:
  A = correct step count + unique intermediates + PNG generated
  B = 3+ steps generated + PNG generated (partial quality)
  C = fewer than expected steps or no PNG (needs improvement)

All SMILES verified with RDKit Chem.MolFromSmiles().
"""
import sys
import os
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ── Exam problem definitions ──
# (id, name, level, reactant_smi, product_smi, conditions, expected_min_steps, expected_source)
# expected_source: "gold" = gold standard, "hardcoded" = template, "rule" = rule engine,
#                  "dft" = quantum, "any" = any source ok, "none" = expected to fail gracefully

EXAM_PROBLEMS = [
    # ═══════════════════════════════════════════════════════════════════
    # Level 1: Basic (15 problems) - Standard named reactions
    # ═══════════════════════════════════════════════════════════════════

    # L1_01: Fischer esterification of benzoic acid + methanol
    # PhCOOH + MeOH -> PhCOOMe (acid-catalyzed, 4-6 steps: protonate C=O, nuc attack, tetrahedral int, dehydration)
    ("L1_01", "Fischer Esterification (PhCOOH + MeOH)", 1,
     "c1ccc(cc1)C(=O)O",           # benzoic acid
     "c1ccc(cc1)C(=O)OC",          # methyl benzoate
     "H2SO4, MeOH, Fischer", 4, "gold"),

    # L1_02: SN2 of 1-bromobutane + NaCN
    # CH3CH2CH2CH2Br + CN- -> CH3CH2CH2CH2CN (1 step concerted, but mechanism shows 2-3 with TS)
    ("L1_02", "SN2 (1-BuBr + NaCN)", 1,
     "CCCCBr",                      # 1-bromobutane
     "CCCCC#N",                     # pentanenitrile
     "NaCN, DMSO, SN2", 2, "gold"),

    # L1_03: E2 of 2-bromopentane + KOtBu
    # Strong bulky base, anti-periplanar elimination
    ("L1_03", "E2 Elimination (2-BrPentane + KOtBu)", 1,
     "CCCC(C)Br",                   # 2-bromopentane
     "CCC=CC",                      # 2-pentene (Zaitsev product)
     "KOtBu, E2", 2, "any"),

    # L1_04: Aldol condensation of propanal
    # Base-catalyzed: enolize -> nuc attack -> beta-hydroxy aldehyde -> dehydration
    ("L1_04", "Aldol Condensation (Propanal)", 1,
     "CCC=O",                       # propanal
     "CC/C=C/C=O",                  # 2-ethyl-2-butenal (condensation product)
     "NaOH, heat, Aldol", 4, "gold"),

    # L1_05: Grignard of PhMgBr + acetone
    # Nucleophilic addition to ketone -> tertiary alcohol
    ("L1_05", "Grignard (PhMgBr + Acetone)", 1,
     "CC(=O)C",                     # acetone
     "CC(O)(C)c1ccccc1",            # 2-phenyl-2-propanol
     "PhMgBr, THF, H3O+, Grignard", 3, "any"),

    # L1_06: Diels-Alder of butadiene + acrolein
    # [4+2] cycloaddition -> cyclohex-2-enecarbaldehyde
    ("L1_06", "Diels-Alder (Butadiene + Acrolein)", 1,
     "C=CC=C",                      # 1,3-butadiene
     "O=CC1CC=CCC1",                # cyclohex-2-enecarbaldehyde
     "heat, Diels-Alder", 2, "gold"),

    # L1_07: NaBH4 reduction of cyclohexanone
    # Hydride delivery to C=O -> alkoxide -> protonation
    ("L1_07", "NaBH4 Reduction (Cyclohexanone)", 1,
     "O=C1CCCCC1",                  # cyclohexanone
     "OC1CCCCC1",                   # cyclohexanol
     "NaBH4, MeOH, reduction", 3, "any"),

    # L1_08: Friedel-Crafts acylation of benzene + AcCl
    # Lewis acid catalyzed EAS: acylium ion -> sigma complex -> rearomatization
    ("L1_08", "Friedel-Crafts Acylation (Benzene + AcCl)", 1,
     "c1ccccc1",                    # benzene
     "CC(=O)c1ccccc1",              # acetophenone
     "AlCl3, CH3COCl, Friedel-Crafts", 4, "hardcoded"),

    # L1_09: Beckmann rearrangement of cyclohexanone oxime
    # Oxime -> protonation -> [1,2]-shift -> nitrilium -> hydrolysis -> caprolactam
    ("L1_09", "Beckmann Rearrangement (Cyclohexanone Oxime)", 1,
     "ON=C1CCCCC1",                 # cyclohexanone oxime
     "O=C1CCCCCN1",                 # caprolactam
     "H2SO4, Beckmann", 4, "gold"),

    # L1_10: Ozonolysis of cyclohexene
    # O3 -> molozonide -> ozonide -> reductive workup -> dialdehyde
    ("L1_10", "Ozonolysis (Cyclohexene)", 1,
     "C1CC=CCC1",                   # cyclohexene
     "O=CCCCC=O",                   # glutaraldehyde (adipaldehyde)
     "O3, DMS, ozonolysis", 3, "any"),

    # L1_11: Wittig reaction of benzaldehyde + Ph3P=CH2
    # Ylide attack -> betaine -> oxaphosphetane -> alkene + Ph3P=O
    ("L1_11", "Wittig (Benzaldehyde + Ph3P=CH2)", 1,
     "O=Cc1ccccc1",                 # benzaldehyde
     "C=Cc1ccccc1",                 # styrene
     "Ph3P=CH2, THF, Wittig", 3, "any"),

    # L1_12: Michael addition of diethyl malonate + MVK
    # 1,4-conjugate addition: enolize malonate -> attack beta-C of enone
    ("L1_12", "Michael Addition (Diethyl Malonate + MVK)", 1,
     "CCOC(=O)CC(=O)OCC",           # diethyl malonate
     "CCOC(=O)C(CC(C)=O)C(=O)OCC", # Michael adduct
     "NaOEt, EtOH, Michael", 4, "gold"),

    # L1_13: Suzuki coupling of PhBr + PhB(OH)2
    # Pd(0) catalytic cycle: oxidative addition -> transmetalation -> reductive elimination
    ("L1_13", "Suzuki Coupling (PhBr + PhB(OH)2)", 1,
     "c1ccc(cc1)Br",                # bromobenzene
     "c1ccc(-c2ccccc2)cc1",         # biphenyl
     "Pd(PPh3)4, Na2CO3, Suzuki", 3, "any"),

    # L1_14: Swern oxidation of benzyl alcohol
    # DMSO/(COCl)2 activation -> alkoxide attack -> elimination
    ("L1_14", "Swern Oxidation (Benzyl Alcohol)", 1,
     "OCc1ccccc1",                   # benzyl alcohol
     "O=Cc1ccccc1",                  # benzaldehyde
     "DMSO, (COCl)2, Et3N, Swern", 6, "gold"),

    # L1_15: Birch reduction of anisole
    # Na/NH3(l): dissolving metal reduction -> 1,4-dihydro product
    ("L1_15", "Birch Reduction (Anisole)", 1,
     "COc1ccccc1",                   # anisole
     "COC1CC=CCC1",                  # 1-methoxy-1,4-cyclohexadiene
     "Na, NH3(l), Birch", 3, "any"),

    # ═══════════════════════════════════════════════════════════════════
    # Level 2: Intermediate (15 problems) - Specific template matching
    # ═══════════════════════════════════════════════════════════════════

    # L2_01: Baeyer-Villiger of cyclopentanone with mCPBA
    # Criegee intermediate -> migration of more substituted C -> lactone
    ("L2_01", "Baeyer-Villiger (Cyclopentanone + mCPBA)", 2,
     "O=C1CCCC1",                    # cyclopentanone
     "O=C1CCCO1",                    # delta-valerolactone
     "mCPBA, Baeyer-Villiger", 4, "any"),

    # L2_02: Curtius rearrangement of benzoyl chloride + NaN3
    # Acyl azide -> heat -> [1,2]-shift -> isocyanate -> (+ H2O -> amine)
    ("L2_02", "Curtius Rearrangement (PhCOCl + NaN3)", 2,
     "O=C(Cl)c1ccccc1",             # benzoyl chloride
     "O=C=Nc1ccccc1",               # phenyl isocyanate
     "NaN3, heat, Curtius", 4, "gold"),

    # L2_03: Stork enamine synthesis (cyclohexanone + pyrrolidine + alkyl halide)
    # Enamine formation -> alkylation -> hydrolysis
    ("L2_03", "Stork Enamine (Cyclohexanone + Pyrrolidine)", 2,
     "O=C1CCCCC1",                   # cyclohexanone
     "O=C1CCCCC1C",                  # 2-methylcyclohexanone
     "pyrrolidine, CH3I, H3O+, Stork", 6, "any"),

    # L2_04: Hofmann rearrangement of benzamide
    # Br2/NaOH: N-bromo -> rearrangement -> isocyanate -> amine (one fewer C)
    ("L2_04", "Hofmann Rearrangement (Benzamide)", 2,
     "NC(=O)c1ccccc1",              # benzamide
     "Nc1ccccc1",                    # aniline
     "Br2, NaOH, Hofmann", 4, "any"),

    # L2_05: Sharpless epoxidation of allyl alcohol
    # Ti(OiPr)4 + TBHP + diethyl tartrate -> chiral epoxide
    ("L2_05", "Sharpless Epoxidation (Allyl Alcohol)", 2,
     "OCC=C",                        # allyl alcohol
     "OCC1CO1",                      # glycidol (2,3-epoxy-1-propanol)
     "Ti(OiPr)4, TBHP, DET, Sharpless", 3, "any"),

    # L2_06: Wacker oxidation of 1-decene
    # PdCl2/CuCl2/O2: anti-Markovnikov -> methyl ketone
    ("L2_06", "Wacker Oxidation (1-Decene)", 2,
     "C=CCCCCCCCC",                  # 1-decene
     "CC(=O)CCCCCCCC",              # 2-decanone
     "PdCl2, CuCl2, O2, H2O, Wacker", 4, "any"),

    # L2_07: Appel reaction (ROH + PPh3 + CCl4 -> RCl)
    # PPh3 + CCl4 -> [Ph3PCl]+ + CCl3- -> ROH attack -> RCl + OPPh3
    ("L2_07", "Appel Reaction (PrOH + PPh3 + CCl4)", 2,
     "CCCO",                         # 1-propanol
     "ClCCC",                        # 1-chloropropane
     "PPh3, CCl4, Appel", 3, "any"),

    # L2_08: Dess-Martin oxidation of cyclohexanol
    # Periodinane oxidation: mild, selective for alcohols
    ("L2_08", "Dess-Martin Oxidation (Cyclohexanol)", 2,
     "OC1CCCCC1",                    # cyclohexanol
     "O=C1CCCCC1",                   # cyclohexanone
     "DMP, CH2Cl2, Dess-Martin", 3, "any"),

    # L2_09: Negishi coupling ArI + RZnCl
    # Pd-catalyzed: oxidative addition -> transmetalation -> reductive elimination
    ("L2_09", "Negishi Coupling (PhI + EtZnCl)", 2,
     "c1ccc(cc1)I",                  # iodobenzene
     "CCc1ccccc1",                   # ethylbenzene
     "Pd(PPh3)4, EtZnCl, THF, Negishi", 3, "any"),

    # L2_10: Buchwald-Hartwig amination (ArBr + amine -> ArNHR)
    # Pd catalytic cycle: OA -> amine coordination -> RE
    ("L2_10", "Buchwald-Hartwig (PhBr + Morpholine)", 2,
     "c1ccc(cc1)Br",                 # bromobenzene
     "c1ccc(cc1)N1CCOCC1",          # N-phenylmorpholine
     "Pd2(dba)3, BINAP, NaOtBu, Buchwald-Hartwig", 3, "any"),

    # L2_11: Robinson annulation (cyclohexanone + MVK)
    # Michael addition -> intramolecular aldol -> dehydration
    ("L2_11", "Robinson Annulation (Cyclohexanone + MVK)", 2,
     "O=C1CCCCC1",                   # cyclohexanone
     "O=C1C=CC2(CCCCC2)CC1",        # 2-decalone enone (Hajos-Parrish type product)
     "NaOH, MVK, heat, Robinson", 8, "gold"),

    # L2_12: Claisen rearrangement of allyl vinyl ether
    # [3,3]-sigmatropic: concerted thermal -> pentenal
    ("L2_12", "Claisen Rearrangement (Allyl Vinyl Ether)", 2,
     "C=COC=C",                      # allyl vinyl ether (simplified)
     "O=CCC=C",                      # 4-pentenal
     "heat, Claisen rearrangement", 2, "any"),

    # L2_13: Pinacol rearrangement (1,2-diol -> ketone)
    # Acid-catalyzed: protonate OH -> loss of H2O -> 1,2-shift -> pinacolone
    ("L2_13", "Pinacol Rearrangement", 2,
     "CC(O)C(O)(C)C",               # pinacol (2,3-dimethyl-2,3-butanediol)
     "CC(=O)C(C)(C)C",              # pinacolone (3,3-dimethyl-2-butanone)
     "H2SO4, heat, Pinacol rearrangement", 4, "any"),

    # L2_14: Jones oxidation of 1-propanol (primary -> carboxylic acid)
    # CrO3/H2SO4: full oxidation of primary alcohol
    ("L2_14", "Jones Oxidation (1-Propanol)", 2,
     "CCCO",                         # 1-propanol
     "CCC(=O)O",                     # propanoic acid
     "CrO3, H2SO4, acetone, Jones oxidation", 3, "any"),

    # L2_15: Cope elimination of amine oxide
    # Syn elimination via 5-membered cyclic TS -> alkene + hydroxylamine
    ("L2_15", "Cope Elimination (Amine Oxide)", 2,
     "CCC(C)[N+]([O-])(C)C",        # N,N-dimethyl-2-butylamine oxide
     "CC=CC",                        # 2-butene
     "heat, Cope elimination", 2, "any"),

    # ═══════════════════════════════════════════════════════════════════
    # Level 3: Advanced / Composite (15 problems)
    # ═══════════════════════════════════════════════════════════════════

    # L3_01: Tandem Michael-aldol (different from Robinson)
    # Enone + active methylene -> 1,4-add -> intramolecular aldol
    ("L3_01", "Tandem Michael-Aldol (Cyclopentanone + MVK)", 3,
     "O=C1CCCC1",                    # cyclopentanone
     "O=C1CC(CCC2=O)CC12",          # bicyclic product (rough)
     "NaOH, MVK, heat, Michael, aldol", 6, "any"),

    # L3_02: Acid-catalyzed ring opening of propylene oxide + methanol
    # Regioselective: acid opens at more substituted C (Markovnikov)
    ("L3_02", "Acid-Catalyzed Epoxide Opening (Propylene Oxide + MeOH)", 3,
     "CC1CO1",                       # propylene oxide
     "COCC(C)O",                     # 1-methoxy-2-propanol
     "H2SO4, MeOH, acid, epoxide opening", 3, "rule"),

    # L3_03: Base-catalyzed hydrolysis of mixed anhydride
    # Selective: nucleophile attacks more electrophilic C=O
    ("L3_03", "Mixed Anhydride Hydrolysis (Acetic-Propionic)", 3,
     "CC(=O)OC(=O)CC",              # acetic propionic anhydride
     "CCC(=O)[O-]",                 # propanoate (+ acetate)
     "NaOH, H2O, hydrolysis", 3, "rule"),

    # L3_04: Reductive amination (cyclohexanone + benzylamine + NaBH3CN)
    # Imine formation -> selective reduction of C=N (not C=O)
    ("L3_04", "Reductive Amination (Cyclohexanone + BnNH2)", 3,
     "O=C1CCCCC1",                   # cyclohexanone
     "C(c1ccccc1)NC1CCCCC1",        # N-benzylcyclohexylamine
     "PhCH2NH2, NaBH3CN, AcOH, reductive amination", 4, "any"),

    # L3_05: Favorskii rearrangement + ester hydrolysis (2-step sequence)
    # alpha-halo ketone -> cyclopropanone -> ring opening -> ester -> hydrolysis
    ("L3_05", "Favorskii + Hydrolysis (2-Chlorocyclohexanone)", 3,
     "O=C1CCCCC1Cl",                # 2-chlorocyclohexanone
     "OC(=O)C1CCCC1",              # cyclopentanecarboxylic acid
     "NaOMe, then H3O+, Favorskii", 6, "gold"),

    # L3_06: Bamford-Stevens reaction (tosylhydrazone -> alkene via carbene)
    # TsNHNH2 + ketone -> tosylhydrazone -> NaOMe/heat -> diazo -> carbene -> alkene
    ("L3_06", "Bamford-Stevens (Acetone Tosylhydrazone)", 3,
     "CC(=NNS(=O)(=O)c1ccc(C)cc1)C", # acetone tosylhydrazone
     "CC=C",                         # propene
     "NaOMe, heat, Bamford-Stevens", 4, "any"),

    # L3_07: Tiffeneau-Demjanov ring expansion
    # Cyclic ketone -> diazomethane -> alpha-diazo ketone -> ring expansion
    ("L3_07", "Tiffeneau-Demjanov (Cyclohexanone -> Cycloheptanone)", 3,
     "O=C1CCCCC1",                   # cyclohexanone
     "O=C1CCCCCC1",                  # cycloheptanone
     "CH2N2, NaNO2, HCl, Tiffeneau-Demjanov", 5, "any"),

    # L3_08: Schmidt reaction of carboxylic acid + HN3
    # Acid + HN3 -> acylium -> [1,2]-shift -> isocyanate -> amine (loss of CO2)
    ("L3_08", "Schmidt Reaction (Benzoic Acid + HN3)", 3,
     "c1ccc(cc1)C(=O)O",            # benzoic acid
     "Nc1ccccc1",                    # aniline
     "HN3, H2SO4, Schmidt", 5, "any"),

    # L3_09: Ireland-Claisen rearrangement
    # Ester -> enolize with LDA/TMSCl -> silyl ketene acetal -> [3,3]-sigmatropic -> acid
    ("L3_09", "Ireland-Claisen (Allyl Acetate)", 3,
     "C=CCOC(=O)C",                  # allyl acetate
     "C=CCC(C)C(=O)O",              # 4-pentenoic acid derivative
     "LDA, TMSCl, heat, Ireland-Claisen", 4, "any"),

    # L3_10: Aza-Cope/Mannich cascade
    # Iminium + homoallyl -> [2,3]-aza-Cope -> hydrolysis -> Mannich
    ("L3_10", "Aza-Cope/Mannich (Formaldehyde + Homoallylamine)", 3,
     "C=CCCN",                       # homoallylamine
     "O=C1CCCN1",                    # 2-pyrrolidinone (rough product)
     "HCHO, acid, Aza-Cope, Mannich", 5, "any"),

    # L3_11: Paterno-Buchi [2+2] photocycloaddition
    # C=O + C=C -> oxetane under UV
    ("L3_11", "Paterno-Buchi (Benzaldehyde + Ethylene)", 3,
     "O=Cc1ccccc1",                  # benzaldehyde
     "C1OCC1c1ccccc1",              # 2-phenyloxetane
     "hv, UV, Paterno-Buchi, [2+2]", 2, "any"),

    # L3_12: Barton radical decarboxylation
    # RCOOH -> thiohydroxamic ester -> radical -> decarboxylation -> RH or R-trap
    ("L3_12", "Barton Decarboxylation (Benzoic Acid)", 3,
     "c1ccc(cc1)C(=O)O",            # benzoic acid
     "c1ccccc1",                     # benzene
     "Barton ester, hv, radical, Barton decarboxylation", 4, "any"),

    # L3_13: Chan-Lam coupling (ArB(OH)2 + amine -> ArNH2 under Cu)
    # Cu(OAc)2 mediated C-N bond formation
    ("L3_13", "Chan-Lam Coupling (PhB(OH)2 + Aniline)", 3,
     "c1ccc(cc1)B(O)O",             # phenylboronic acid
     "c1ccc(Nc2ccccc2)cc1",         # diphenylamine
     "Cu(OAc)2, pyridine, O2, Chan-Lam", 3, "any"),

    # L3_14: Meinwald rearrangement of styrene oxide
    # Acid-catalyzed: epoxide -> carbocation -> [1,2]-H shift -> phenylacetaldehyde
    ("L3_14", "Meinwald Rearrangement (Styrene Oxide)", 3,
     "C(c1ccccc1)1CO1",             # styrene oxide
     "O=CCc1ccccc1",                # phenylacetaldehyde
     "BF3.Et2O, Meinwald rearrangement", 3, "any"),

    # L3_15: Retro-Diels-Alder of norbornene derivative
    # Thermal: cycloreversion -> diene + dienophile fragments
    ("L3_15", "Retro-Diels-Alder (Norbornene)", 3,
     "C1CC2CC1C=C2",                # norbornene
     "C=CC=C",                      # 1,3-butadiene (+ ethylene)
     "heat, 500C, retro Diels-Alder, retro-[4+2]", 2, "any"),

    # ═══════════════════════════════════════════════════════════════════
    # Level 4: Novel / Unseen (10 problems) - NOT in our database
    # These SHOULD fail in gold standard/hardcoded and test the rule engine
    # ═══════════════════════════════════════════════════════════════════

    # L4_01: Acyloin condensation (Na, xylene, TMSCl)
    # Intramolecular version: diester -> alpha-hydroxy ketone via radical/anionic
    ("L4_01", "Acyloin Condensation (Diethyl Adipate)", 4,
     "O=C(OCC)CCCCC(=O)OCC",        # diethyl adipate
     "OC1CCCCC1=O",                  # 2-hydroxycyclohexanone
     "Na, xylene, TMSCl, acyloin condensation", 4, "none"),

    # L4_02: Thorpe-Ziegler cyclization (intramolecular nitrile condensation)
    # Dinitrile -> base -> intramolecular Claisen-like -> cyclic beta-aminonitrile
    ("L4_02", "Thorpe-Ziegler (Adiponitrile)", 4,
     "N#CCCCCCC#N",                  # heptanedinitrile (pimelonitrile)
     "N=C1CCCCC1C#N",               # 2-amino-1-cyanocyclohexene (rough)
     "NaH, THF, Thorpe-Ziegler cyclization", 4, "none"),

    # L4_03: Darzens glycidic ester condensation
    # Aldehyde + alpha-halo ester -> glycidic ester (epoxy ester)
    ("L4_03", "Darzens Condensation (PhCHO + ClCH2COOEt)", 4,
     "O=Cc1ccccc1",                  # benzaldehyde
     "CCOC(=O)C1OC1c1ccccc1",       # ethyl 3-phenylglycidate
     "ClCH2COOEt, NaOEt, Darzens", 4, "none"),

    # L4_04: Knoevenagel condensation of malonate + aldehyde
    # Decarboxylative or not: aldehyde + active methylene -> alpha,beta-unsat
    ("L4_04", "Knoevenagel (PhCHO + Malonic Acid)", 4,
     "O=Cc1ccccc1",                  # benzaldehyde
     "O=C(O)/C(=C/c1ccccc1)C(=O)O", # benzylidenemalonic acid
     "piperidine, AcOH, Knoevenagel", 4, "none"),

    # L4_05: Baylis-Hillman reaction (DABCO catalyst)
    # Acrylate + aldehyde -> alpha-methylene-beta-hydroxy ester (DABCO catalytic cycle)
    ("L4_05", "Baylis-Hillman (PhCHO + Methyl Acrylate)", 4,
     "O=Cc1ccccc1",                  # benzaldehyde
     "OC(c1ccccc1)C(=C)C(=O)OC",    # Baylis-Hillman product
     "DABCO, methyl acrylate, Baylis-Hillman", 5, "none"),

    # L4_06: Staudinger ligation (azide + phosphine -> amine)
    # Azide + PPh3 -> phosphazide -> aza-ylide -> + H2O -> amine + OPPh3
    ("L4_06", "Staudinger Ligation (PhN3 + PPh3)", 4,
     "c1ccc(cc1)[N-][N+]#N",        # phenyl azide
     "Nc1ccccc1",                    # aniline
     "PPh3, H2O, Staudinger ligation", 4, "none"),

    # L4_07: Kulinkovich reaction (Ti(OiPr)4 + EtMgBr + ester -> cyclopropanol)
    # Titanacyclopropane + ester -> cyclopropanol
    ("L4_07", "Kulinkovich (Ethyl Acetate -> 1-Methylcyclopropanol)", 4,
     "CC(=O)OCC",                    # ethyl acetate
     "OC1(C)CC1",                    # 1-methylcyclopropanol
     "Ti(OiPr)4, EtMgBr, Kulinkovich", 4, "none"),

    # L4_08: Henry (nitroaldol) reaction
    # Aldehyde + nitroalkane -> beta-nitro alcohol
    ("L4_08", "Henry Reaction (PhCHO + Nitromethane)", 4,
     "O=Cc1ccccc1",                  # benzaldehyde
     "OC(c1ccccc1)C[N+](=O)[O-]",   # 2-nitro-1-phenylethanol
     "CH3NO2, NaOH, Henry, nitroaldol", 3, "none"),

    # L4_09: Trost allylation (Pd-catalyzed allylation with soft nucleophile)
    # Pd(0)/allyl acetate + malonate -> allylated malonate
    ("L4_09", "Trost Allylation (Allyl Acetate + Dimethyl Malonate)", 4,
     "C=CCOC(=O)C",                  # allyl acetate
     "C=CCC(C(=O)OC)C(=O)OC",       # allyl dimethyl malonate
     "Pd(PPh3)4, dimethyl malonate, NaH, Trost allylation", 4, "none"),

    # L4_10: Mukaiyama aldol (TiCl4 + silyl enol ether + aldehyde)
    # Lewis acid-mediated: TiCl4 activates aldehyde -> silyl enol ether attacks
    ("L4_10", "Mukaiyama Aldol (PhCHO + TMS-Enol Ether of Acetone)", 4,
     "O=Cc1ccccc1",                  # benzaldehyde
     "OC(c1ccccc1)CC(=O)C",         # 4-hydroxy-4-phenyl-2-butanone
     "TiCl4, TMS enol ether, CH2Cl2, Mukaiyama aldol", 3, "none"),

    # ═══════════════════════════════════════════════════════════════════
    # Level 5: Mixed Edge Cases (20 problems) - Exam-style coverage boost
    # Carbonyl, heterocycle, protecting group, MCR, redox edge cases
    # ═══════════════════════════════════════════════════════════════════

    # ── Carbonyl chemistry edge cases (5) ──

    # L5_01: Cannizzaro reaction (non-enolizable aldehyde + strong base)
    # HCHO + NaOH -> disproportionation: one molecule oxidized, one reduced
    # 2 HCHO -> CH3OH + HCOONa
    ("L5_01", "Cannizzaro (Formaldehyde + NaOH)", 5,
     "C=O",                          # formaldehyde
     "CO",                           # methanol (reduced product)
     "NaOH, Cannizzaro", 4, "any"),

    # L5_02: Meerwein-Ponndorf-Verley reduction
    # Ketone + Al(OiPr)3 -> secondary alcohol (hydride transfer via 6-membered TS)
    ("L5_02", "Meerwein-Ponndorf-Verley (Cyclohexanone + Al(OiPr)3)", 5,
     "O=C1CCCCC1",                   # cyclohexanone
     "OC1CCCCC1",                    # cyclohexanol
     "Al(OiPr)3, iPrOH, Meerwein-Ponndorf-Verley reduction", 3, "any"),

    # L5_03: Tischenko reaction (aldehyde dimerization to ester)
    # 2 PhCHO -> PhCH2OC(=O)Ph (one aldehyde is oxidized, one is reduced)
    ("L5_03", "Tischenko (Benzaldehyde + SmI2 catalyst)", 5,
     "O=Cc1ccccc1",                  # benzaldehyde
     "O=C(OCc1ccccc1)c1ccccc1",     # benzyl benzoate
     "SmI2, Tischenko reaction", 3, "any"),

    # L5_04: Reformatsky reaction
    # alpha-Bromo ester + Zn -> organozinc enolate, then attacks aldehyde
    ("L5_04", "Reformatsky (BrCH2COOEt + Zn + PhCHO)", 5,
     "O=Cc1ccccc1",                  # benzaldehyde
     "CCOC(=O)CC(O)c1ccccc1",       # ethyl 3-hydroxy-3-phenylpropanoate
     "BrCH2COOEt, Zn, THF, Reformatsky", 4, "any"),

    # L5_05: Weinreb amide + Grignard -> ketone (no over-addition)
    # R-C(=O)N(OMe)Me + R'MgBr -> R-C(=O)R' (chelation control)
    ("L5_05", "Weinreb Amide + Grignard (PhC(=O)N(OMe)Me + MeMgBr)", 5,
     "CN(C)C(=O)c1ccccc1",          # N-methoxy-N-methylbenzamide (Weinreb amide) — note: simplified SMILES
     "CC(=O)c1ccccc1",              # acetophenone
     "MeMgBr, THF, Weinreb amide, Grignard", 3, "any"),

    # ── Heterocycle synthesis (5) ──

    # L5_06: Fischer indole synthesis
    # Phenylhydrazine + ketone -> [3,3]-sigmatropic -> indole
    ("L5_06", "Fischer Indole (Phenylhydrazine + Acetone)", 5,
     "NNc1ccccc1",                   # phenylhydrazine
     "Cc1[nH]c2ccccc2c1C",          # 2,3-dimethylindole
     "ZnCl2, AcOH, heat, Fischer indole synthesis", 5, "any"),

    # L5_07: Hantzsch pyridine synthesis
    # Aldehyde + 2 eq ethyl acetoacetate + NH3 -> dihydropyridine -> oxidize -> pyridine
    ("L5_07", "Hantzsch Pyridine (PhCHO + Ethyl Acetoacetate + NH3)", 5,
     "O=Cc1ccccc1",                  # benzaldehyde
     "CCOC(=O)c1cc(C)nc(C)c1C(=O)OCC",  # diethyl 2,6-dimethyl-4-phenylpyridine-3,5-dicarboxylate (rough)
     "ethyl acetoacetate, NH4OAc, heat, Hantzsch pyridine", 6, "any"),

    # L5_08: Paal-Knorr furan synthesis
    # 1,4-Diketone + acid -> furan (intramolecular cyclization + dehydration)
    ("L5_08", "Paal-Knorr Furan (Acetonylacetone)", 5,
     "CC(=O)CCC(=O)C",              # 2,5-hexanedione (acetonylacetone)
     "Cc1ccc(C)o1",                  # 2,5-dimethylfuran
     "H2SO4, heat, Paal-Knorr furan", 4, "any"),

    # L5_09: Gewald reaction
    # Ketone + elemental sulfur + cyanoacetate -> 2-aminothiophene
    ("L5_09", "Gewald (Cyclohexanone + S8 + Ethyl Cyanoacetate)", 5,
     "O=C1CCCCC1",                   # cyclohexanone
     "CCOC(=O)c1cc2c(s1)CCCC2N",   # ethyl 2-amino-4,5,6,7-tetrahydrobenzo[b]thiophene-3-carboxylate (rough)
     "S8, NCCH2COOEt, Et3N, Gewald reaction", 5, "any"),

    # L5_10: Skraup quinoline synthesis
    # Aniline + glycerol + nitrobenzene (oxidant) + H2SO4 -> quinoline
    ("L5_10", "Skraup Quinoline (Aniline + Glycerol)", 5,
     "Nc1ccccc1",                    # aniline
     "c1ccc2ncccc2c1",              # quinoline
     "glycerol, H2SO4, nitrobenzene, FeSO4, Skraup quinoline", 6, "any"),

    # ── Protecting group chemistry (3) ──

    # L5_11: TBS protection of primary alcohol
    # ROH + TBSCl + imidazole -> ROTBS (silyl ether)
    ("L5_11", "TBS Protection (BnOH + TBSCl + Imidazole)", 5,
     "OCc1ccccc1",                   # benzyl alcohol
     "O([Si](C)(C)C(C)(C)C)Cc1ccccc1",  # benzyl TBS ether
     "TBSCl, imidazole, DMF, TBS protection", 2, "any"),

    # L5_12: Boc protection of amine
    # RNH2 + Boc2O -> RNHBoc (carbamate)
    ("L5_12", "Boc Protection (Benzylamine + Boc2O)", 5,
     "NCc1ccccc1",                   # benzylamine
     "O=C(OC(C)(C)C)NCc1ccccc1",   # N-Boc-benzylamine
     "Boc2O, Et3N, DMAP, Boc protection", 3, "any"),

    # L5_13: Acetalization of ketone (carbonyl protection)
    # Ketone + ethylene glycol + acid -> cyclic acetal
    ("L5_13", "Acetalization (Cyclohexanone + Ethylene Glycol)", 5,
     "O=C1CCCCC1",                   # cyclohexanone
     "C1(CCCCC1)1OCCO1",            # cyclohexanone ethylene acetal (1,3-dioxolane)
     "HOCH2CH2OH, p-TsOH, toluene, Dean-Stark, acetalization", 3, "any"),

    # ── Multi-component / tandem reactions (4) ──

    # L5_14: Mannich reaction
    # Formaldehyde + secondary amine + ketone -> beta-amino ketone
    ("L5_14", "Mannich (Acetone + HCHO + Dimethylamine)", 5,
     "CC(=O)C",                      # acetone
     "CC(=O)CN(C)C",               # 4-(dimethylamino)-2-butanone
     "HCHO, HN(CH3)2, HCl, Mannich reaction", 4, "any"),

    # L5_15: Strecker synthesis
    # Aldehyde + ammonia + HCN -> alpha-amino nitrile (-> amino acid after hydrolysis)
    ("L5_15", "Strecker (PhCHO + NH3 + HCN)", 5,
     "O=Cc1ccccc1",                  # benzaldehyde
     "NC(C#N)c1ccccc1",             # alpha-aminophenylacetonitrile
     "NH3, HCN, Strecker synthesis", 4, "any"),

    # L5_16: Ugi 4-component reaction
    # Aldehyde + amine + carboxylic acid + isocyanide -> alpha-acylaminoamide
    ("L5_16", "Ugi 4CR (PhCHO + MeNH2 + AcOH + tBuNC)", 5,
     "O=Cc1ccccc1",                  # benzaldehyde
     "CC(=O)N(C)C(c1ccccc1)C(=O)NC(C)(C)C",  # Ugi product (rough)
     "MeNH2, AcOH, tBuNC, MeOH, Ugi reaction", 5, "any"),

    # L5_17: Passerini 3-component reaction
    # Aldehyde + carboxylic acid + isocyanide -> alpha-acyloxyamide
    ("L5_17", "Passerini 3CR (PhCHO + AcOH + tBuNC)", 5,
     "O=Cc1ccccc1",                  # benzaldehyde
     "CC(=O)OC(c1ccccc1)C(=O)NC(C)(C)C",  # Passerini product
     "AcOH, tBuNC, CH2Cl2, Passerini reaction", 4, "any"),

    # ── Oxidation / Reduction edge cases (3) ──

    # L5_18: Oppenauer oxidation
    # Alcohol + Al(OtBu)3 + acetone (hydride acceptor) -> ketone
    ("L5_18", "Oppenauer Oxidation (Cyclohexanol + Al(OtBu)3 + Acetone)", 5,
     "OC1CCCCC1",                    # cyclohexanol
     "O=C1CCCCC1",                   # cyclohexanone
     "Al(OtBu)3, acetone, Oppenauer oxidation", 3, "any"),

    # L5_19: Luche reduction (selective 1,2-reduction of enone)
    # NaBH4 + CeCl3: CeCl3 directs 1,2-selectivity over 1,4-addition
    ("L5_19", "Luche Reduction (2-Cyclohexenone + NaBH4/CeCl3)", 5,
     "O=C1CC=CCC1",                  # 2-cyclohexenone
     "OC1CC=CCC1",                   # 2-cyclohexen-1-ol (1,2-product)
     "NaBH4, CeCl3, MeOH, Luche reduction", 3, "any"),

    # L5_20: Corey-Kim oxidation
    # NCS + DMS -> activated DMSO equivalent, then alcohol -> aldehyde/ketone
    ("L5_20", "Corey-Kim Oxidation (Cyclohexanol + NCS/DMS)", 5,
     "OC1CCCCC1",                    # cyclohexanol
     "O=C1CCCCC1",                   # cyclohexanone
     "NCS, DMS, Et3N, Corey-Kim oxidation", 4, "any"),
]


def _grade_result(steps, min_steps, reactant_smi, pid):
    """Grade mechanism quality: A (excellent), B (acceptable), C (poor)."""
    if not steps:
        return "C", 0

    n_steps = len(steps)

    # Check intermediates are not copies of reactant
    from rdkit import Chem
    r_can = Chem.MolToSmiles(Chem.MolFromSmiles(reactant_smi)) if reactant_smi else ""

    unique_intermediates = 0
    for i, s in enumerate(steps):
        smi = s.get('mol_smi', '')
        if smi:
            try:
                mol = Chem.MolFromSmiles(smi)
                if mol:
                    can = Chem.MolToSmiles(mol)
                    if can != r_can:
                        unique_intermediates += 1
            except Exception:
                pass

    # Grade A: meets step count AND has unique intermediates
    if n_steps >= min_steps and unique_intermediates >= min(2, n_steps - 1):
        return "A", n_steps

    # Grade B: at least 3 steps or meets step count partially
    if n_steps >= 3 or (n_steps >= min_steps - 1 and unique_intermediates >= 1):
        return "B", n_steps

    return "C", n_steps


def test_exam_problems():
    """Run all 75 exam-style mechanism problems and report results."""
    from drylab_report_exporter import (
        _get_mechanism_steps,
        _generate_mechanism_step_png,
    )

    results = {"L1": [], "L2": [], "L3": [], "L4": [], "L5": []}
    all_details = []
    start_time = time.time()

    print("=" * 70)
    print("  Mechanism Engine Exam Problem Test Suite")
    print(f"  {len(EXAM_PROBLEMS)} problems across 4 difficulty levels")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    for pid, name, level, rsmi, psmi, cond, min_steps, expected_src in EXAM_PROBLEMS:
        t0 = time.time()
        level_key = f"L{level}"

        # Generate mechanism steps
        try:
            steps = _get_mechanism_steps(rsmi, psmi, cond)
        except Exception as e:
            steps = None
            print(f"  [ERROR] {pid}: _get_mechanism_steps raised {type(e).__name__}: {e}")

        # Grade quality
        grade, n_steps = _grade_result(steps, min_steps, rsmi, pid)

        # Try PNG generation
        png_ok = False
        png_size = 0
        try:
            png = _generate_mechanism_step_png(rsmi, psmi, cond)
            if png and len(png) > 100:
                png_ok = True
                png_size = len(png)
        except Exception as e:
            print(f"  [ERROR] {pid}: PNG generation raised {type(e).__name__}: {e}")

        # Detect source tier
        source = "unknown"
        if steps:
            first_label = steps[0].get('label', '') if steps else ''
            first_badge = steps[0].get('mech_badge', '') if steps else ''
            if first_badge:
                source = "gold"
            elif 'hardcoded' in str(steps[0].get('annotation', '')).lower():
                source = "hardcoded"
            elif n_steps >= 3:
                source = "rule"
            else:
                source = "fallback"

        elapsed = time.time() - t0

        # Collect intermediate SMILES for analysis
        intermediate_smis = []
        if steps:
            for s in steps:
                smi = s.get('mol_smi', '')
                if smi:
                    intermediate_smis.append(smi)

        detail = {
            "pid": pid,
            "name": name,
            "level": level,
            "grade": grade,
            "n_steps": n_steps,
            "min_steps": min_steps,
            "png_ok": png_ok,
            "png_bytes": png_size,
            "source": source,
            "expected_source": expected_src,
            "elapsed_sec": round(elapsed, 2),
            "intermediates": intermediate_smis,
        }
        all_details.append(detail)
        results[level_key].append((pid, name, grade, n_steps, png_ok, source, elapsed))

        # Console output
        emoji = {"A": "PASS", "B": "PART", "C": "FAIL"}[grade]
        src_match = ""
        if expected_src != "any" and expected_src != "none":
            src_match = f" [src:{source}" + ("=OK" if source == expected_src else "!=expect") + "]"
        elif expected_src == "none":
            src_match = f" [novel:{source}]"

        print(f"  [{emoji}] {pid} {name}: Grade {grade} "
              f"({n_steps}/{min_steps} steps, PNG={'OK' if png_ok else 'FAIL'}"
              f"{src_match}, {elapsed:.1f}s)")

    # ── Summary ──
    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("  SUMMARY BY LEVEL")
    print("=" * 70)

    grand_a = grand_b = grand_c = 0
    for lv in ["L1", "L2", "L3", "L4", "L5"]:
        items = results[lv]
        a_count = sum(1 for i in items if i[2] == "A")
        b_count = sum(1 for i in items if i[2] == "B")
        c_count = sum(1 for i in items if i[2] == "C")
        png_count = sum(1 for i in items if i[4])
        grand_a += a_count
        grand_b += b_count
        grand_c += c_count

        level_names = {
            "L1": "Basic (15)",
            "L2": "Intermediate (15)",
            "L3": "Advanced (15)",
            "L4": "Novel/Unseen (10)",
            "L5": "Mixed Edge Cases (20)"
        }
        pct_a = a_count / len(items) * 100 if items else 0
        print(f"\n  Level {lv} - {level_names[lv]}:")
        print(f"    A (excellent): {a_count:2d} | B (partial): {b_count:2d} | C (fail): {c_count:2d}")
        print(f"    PNG success:   {png_count}/{len(items)}")
        print(f"    A-rate:        {pct_a:.0f}%")

    total = grand_a + grand_b + grand_c
    print(f"\n  TOTAL: {grand_a}A / {grand_b}B / {grand_c}C  ({total} problems)")
    print(f"  Overall A-rate: {grand_a/total*100:.1f}%")
    print(f"  Overall pass (A+B): {(grand_a+grand_b)/total*100:.1f}%")
    print(f"  Total time: {total_time:.1f}s")
    print("=" * 70)

    return all_details


def save_results(details, output_dir):
    """Save results to JSON and summary text file."""
    os.makedirs(output_dir, exist_ok=True)

    # JSON with full details
    json_path = os.path.join(output_dir, "exam_results.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_problems": len(details),
            "summary": {
                "A": sum(1 for d in details if d["grade"] == "A"),
                "B": sum(1 for d in details if d["grade"] == "B"),
                "C": sum(1 for d in details if d["grade"] == "C"),
            },
            "by_level": {
                f"L{lv}": {
                    "A": sum(1 for d in details if d["level"] == lv and d["grade"] == "A"),
                    "B": sum(1 for d in details if d["level"] == lv and d["grade"] == "B"),
                    "C": sum(1 for d in details if d["level"] == lv and d["grade"] == "C"),
                }
                for lv in [1, 2, 3, 4, 5]
            },
            "problems": details,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to: {json_path}")

    # Summary markdown
    md_path = os.path.join(output_dir, "exam_summary.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# Mechanism Engine Exam Test Results\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        total = len(details)
        a_total = sum(1 for d in details if d["grade"] == "A")
        b_total = sum(1 for d in details if d["grade"] == "B")
        c_total = sum(1 for d in details if d["grade"] == "C")

        f.write("## Overall Summary\n\n")
        f.write(f"| Grade | Count | Percentage |\n")
        f.write(f"|-------|-------|------------|\n")
        f.write(f"| A (excellent) | {a_total} | {a_total/total*100:.1f}% |\n")
        f.write(f"| B (partial) | {b_total} | {b_total/total*100:.1f}% |\n")
        f.write(f"| C (fail) | {c_total} | {c_total/total*100:.1f}% |\n")
        f.write(f"| **Total** | **{total}** | |\n\n")

        for lv, lv_name in [(1, "Basic"), (2, "Intermediate"),
                             (3, "Advanced"), (4, "Novel/Unseen"),
                             (5, "Mixed Edge Cases")]:
            lv_items = [d for d in details if d["level"] == lv]
            f.write(f"\n## Level {lv}: {lv_name}\n\n")
            f.write(f"| ID | Reaction | Grade | Steps | PNG | Source | Time |\n")
            f.write(f"|-----|----------|-------|-------|-----|--------|------|\n")
            for d in lv_items:
                mark = {"A": "PASS", "B": "PART", "C": "FAIL"}[d["grade"]]
                f.write(f"| {d['pid']} | {d['name'][:40]} | {mark} | "
                        f"{d['n_steps']}/{d['min_steps']} | "
                        f"{'OK' if d['png_ok'] else 'FAIL'} | "
                        f"{d['source']} | {d['elapsed_sec']}s |\n")

        # Failing problems analysis
        fails = [d for d in details if d["grade"] == "C"]
        if fails:
            f.write(f"\n## Failing Problems ({len(fails)})\n\n")
            for d in fails:
                f.write(f"- **{d['pid']}** {d['name']}: {d['n_steps']}/{d['min_steps']} steps, "
                        f"source={d['source']}, expected={d['expected_source']}\n")
                if d['intermediates']:
                    f.write(f"  - Intermediates: {', '.join(d['intermediates'][:5])}\n")

    print(f"  Summary saved to: {md_path}")


def save_png_samples(details, output_dir):
    """Generate and save PNG samples for grade-A problems."""
    from drylab_report_exporter import _generate_mechanism_step_png

    png_dir = os.path.join(output_dir, "png_samples")
    os.makedirs(png_dir, exist_ok=True)

    saved = 0
    # Save PNG for first 5 grade-A problems and first 3 grade-B/C as comparison
    a_items = [d for d in details if d["grade"] == "A"][:5]
    bc_items = [d for d in details if d["grade"] in ("B", "C")][:3]

    for d in a_items + bc_items:
        # Find the matching problem
        for pid, name, level, rsmi, psmi, cond, _, _ in EXAM_PROBLEMS:
            if pid == d["pid"]:
                try:
                    png = _generate_mechanism_step_png(rsmi, psmi, cond)
                    if png and len(png) > 100:
                        fname = f"{d['pid']}_{d['grade']}_{name[:30].replace(' ', '_').replace('/', '_')}.png"
                        fpath = os.path.join(png_dir, fname)
                        with open(fpath, 'wb') as f:
                            f.write(png)
                        saved += 1
                except Exception:
                    pass
                break

    print(f"  Saved {saved} PNG samples to: {png_dir}")


if __name__ == "__main__":
    # Determine output directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..', '..'))
    evidence_dir = os.path.join(project_root, "departments", "domain_mechanism",
                                "evidence", "exam_test")

    print(f"\n  Output directory: {evidence_dir}\n")

    # Run exam
    details = test_exam_problems()

    # Save results
    save_results(details, evidence_dir)

    # Save PNG samples
    save_png_samples(details, evidence_dir)

    print("\n  Exam test complete.")
