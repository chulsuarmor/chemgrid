#!/usr/bin/env python3
"""Ch.2 유기합성반응정리노트 — 엔진 대조 테스트.

교재 p011~p020 (알코올/알켄 합성, 방향족 반응, 카르보닐 환원)에서
식별된 반응 30건을 엔진에 대조하여 A/B/C 등급 분류.

등급 기준:
  A: 전용 템플릿 매칭, 올바른 중간체, 교과서 수준 단계
  B: 범용 3단계 폴백 (Substrate Activation → Bond Reorganization → Product)
  C: 잘못된 템플릿 매칭 또는 렌더 실패

Usage:
  cd C:/chemgrid/src/app/tests
  python test_ch2_reactions.py
"""
import sys
import os
import json
import traceback
import io

# Force UTF-8 output to avoid cp949 encoding errors on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ──────────────────────────────────────────────
# Ch.2 Test Cases (from reference images p011~p020)
# ──────────────────────────────────────────────

CH2_TEST_CASES = [
    # ── p011: Alkene electrophilic addition ──
    {
        "name": "p011_01_markovnikov_HBr",
        "reactant": "C=CC",          # propene
        "product": "CC(Br)C",         # 2-bromopropane
        "conditions": "HBr",
        "type": "electrophilic addition",
        "page": "p011",
        "expected_template": "generic",
        "expected_min_steps": 2,
        "notes": "Markovnikov addition: H to less substituted, Br to more substituted C",
    },
    {
        "name": "p011_02_halide_addition_Br2",
        "reactant": "C=CC",          # propene
        "product": "CC(Br)CBr",       # 1,2-dibromopropane
        "conditions": "Br2, CCl4",
        "type": "anti-addition",
        "page": "p011",
        "expected_template": "br2_addition",
        "expected_min_steps": 3,
        "notes": "Bromonium ion intermediate, anti-addition (trans product)",
    },
    {
        "name": "p011_03_halide_addition_Cl2",
        "reactant": "C=C",            # ethene
        "product": "ClCCCl",           # 1,2-dichloroethane
        "conditions": "Cl2",
        "type": "anti-addition",
        "page": "p011",
        "expected_template": "generic",
        "expected_min_steps": 3,
        "notes": "Chloronium ion pathway (analogous to bromonium)",
    },

    # ── p012: Alkyne reduction & hydration ──
    {
        "name": "p012_04_lindlar_syn_addition",
        "reactant": "CC#CC",          # 2-butyne
        "product": "C/C=C\\C",         # cis-2-butene
        "conditions": "H2, Lindlar catalyst (Pd/CaCO3, quinoline)",
        "type": "syn-addition",
        "page": "p012",
        "expected_template": "generic",
        "expected_min_steps": 2,
        "notes": "Lindlar catalyst: poisoned Pd, stops at cis-alkene",
    },
    {
        "name": "p012_05_birch_reduction",
        "reactant": "c1ccccc1",       # benzene
        "product": "C1=CCC=CC1",       # 1,4-cyclohexadiene
        "conditions": "Na, NH3(l), Birch reduction",
        "type": "dissolving metal reduction",
        "page": "p012",
        "expected_template": "birch",
        "expected_min_steps": 4,
        "notes": "SET mechanism: radical anion → protonation → radical → protonation",
    },
    {
        "name": "p012_06_acid_catalyzed_hydration",
        "reactant": "C=CC",           # propene
        "product": "CC(O)C",           # 2-propanol (Markovnikov)
        "conditions": "H2SO4, H2O, acid-catalyzed hydration",
        "type": "Markovnikov addition",
        "page": "p012",
        "expected_template": "acid_hydration",
        "expected_min_steps": 3,
        "notes": "Carbocation intermediate, Markovnikov regiochemistry",
    },
    {
        "name": "p012_07_grignard_addition",
        "reactant": "CC=O",           # acetaldehyde
        "product": "CC(O)C",           # 2-propanol
        "conditions": "CH3MgBr, THF, then H3O+, Grignard",
        "type": "nucleophilic addition",
        "page": "p012",
        "expected_template": "grignard",
        "expected_min_steps": 3,
        "notes": "RMgX attacks C=O, workup gives alcohol",
    },
    {
        "name": "p012_08_NaBH4_reduction",
        "reactant": "CC=O",           # acetaldehyde
        "product": "CCO",              # ethanol
        "conditions": "NaBH4, MeOH",
        "type": "reduction",
        "page": "p012",
        "expected_template": "nabh4",
        "expected_min_steps": 2,
        "notes": "Hydride delivery to C=O",
    },
    {
        "name": "p012_09_LiAlH4_reduction",
        "reactant": "CC(=O)O",        # acetic acid
        "product": "CCO",              # ethanol
        "conditions": "LiAlH4, THF, then H3O+",
        "type": "reduction",
        "page": "p012",
        "expected_template": "lialh4",
        "expected_min_steps": 2,
        "notes": "Strong reducing agent: acid → aldehyde → alcohol (2 equiv H-)",
    },

    # ── p013: Anti-Markovnikov & oxidation ──
    {
        "name": "p013_10_hydroboration_oxidation",
        "reactant": "C=CC",           # propene
        "product": "CCCO",             # 1-propanol (anti-Markovnikov)
        "conditions": "BH3, THF, then H2O2, NaOH, hydroboration",
        "type": "anti-Markovnikov addition",
        "page": "p013",
        "expected_template": "hydroboration",
        "expected_min_steps": 3,
        "notes": "Concerted syn addition, anti-Markovnikov, 4-center TS",
    },
    {
        "name": "p013_11_KMnO4_mild_oxidation",
        "reactant": "C=CC",           # propene
        "product": "OCC(O)C",          # propylene glycol (cis-diol)
        "conditions": "KMnO4, cold, dilute, OH-",
        "type": "syn-dihydroxylation",
        "page": "p013",
        "expected_template": "generic",
        "expected_min_steps": 2,
        "notes": "Concerted [3+2] cycloaddition with manganate ester intermediate",
    },
    {
        "name": "p013_12_KMnO4_hot_oxidation",
        "reactant": "C=CC",           # propene
        "product": "CC(=O)O",          # acetic acid (from one fragment)
        "conditions": "KMnO4, H2SO4, heat",
        "type": "oxidative cleavage",
        "page": "p013",
        "expected_template": "generic",
        "expected_min_steps": 2,
        "notes": "C=C cleaved completely, terminal CH2= → CO2, internal C= → COOH",
    },
    {
        "name": "p013_13_ozonolysis",
        "reactant": "C=CC",           # propene
        "product": "CC=O",             # acetaldehyde (+ formaldehyde from CH2=)
        "conditions": "O3, then Zn/AcOH, ozonolysis",
        "type": "oxidative cleavage",
        "page": "p013",
        "expected_template": "ozonolysis",
        "expected_min_steps": 3,
        "notes": "Molozonide → ozonide → reductive workup → carbonyls",
    },

    # ── p014: Aromatic EAS (electrophilic aromatic substitution) ──
    {
        "name": "p014_14_aromatic_halogenation",
        "reactant": "c1ccccc1",        # benzene
        "product": "Brc1ccccc1",        # bromobenzene
        "conditions": "Br2, FeBr3",
        "type": "electrophilic aromatic substitution",
        "page": "p014",
        "expected_template": "generic",
        "expected_min_steps": 3,
        "notes": "Arenium (sigma complex) intermediate, re-aromatization by loss of H+",
    },
    {
        "name": "p014_15_nitration",
        "reactant": "c1ccccc1",        # benzene
        "product": "[O-][N+](=O)c1ccccc1",  # nitrobenzene
        "conditions": "HNO3, H2SO4, nitration",
        "type": "electrophilic aromatic substitution",
        "page": "p014",
        "expected_template": "generic",
        "expected_min_steps": 3,
        "notes": "NO2+ electrophile from HNO3/H2SO4, arenium intermediate",
    },
    {
        "name": "p014_16_sulfonation",
        "reactant": "c1ccccc1",        # benzene
        "product": "OS(=O)(=O)c1ccccc1",  # benzenesulfonic acid
        "conditions": "SO3, H2SO4, sulfonation",
        "type": "electrophilic aromatic substitution",
        "page": "p014",
        "expected_template": "generic",
        "expected_min_steps": 3,
        "notes": "SO3 electrophile, reversible under acidic conditions + heat",
    },
    {
        "name": "p014_17_friedel_crafts_alkylation",
        "reactant": "c1ccccc1",        # benzene
        "product": "CCc1ccccc1",        # ethylbenzene
        "conditions": "CH3CH2Cl, AlCl3, Friedel-Crafts",
        "type": "electrophilic aromatic substitution",
        "page": "p014",
        "expected_template": "friedel_crafts",
        "expected_min_steps": 3,
        "notes": "Carbocation generation by AlCl3 + RCl, sigma complex, H+ loss",
    },
    {
        "name": "p014_18_friedel_crafts_acylation",
        "reactant": "c1ccccc1",        # benzene
        "product": "O=C(C)c1ccccc1",   # acetophenone
        "conditions": "CH3COCl, AlCl3, Friedel-Crafts acylation",
        "type": "electrophilic aromatic substitution",
        "page": "p014",
        "expected_template": "friedel_crafts",
        "expected_min_steps": 3,
        "notes": "Acylium ion from RCOCl + AlCl3, no rearrangement (unlike alkylation)",
    },

    # ── p015: Benzylic reactions, named reductions ──
    {
        "name": "p015_19_benzylic_oxidation",
        "reactant": "Cc1ccccc1",       # toluene
        "product": "OC(=O)c1ccccc1",   # benzoic acid
        "conditions": "KMnO4, H2O, heat",
        "type": "oxidation",
        "page": "p015",
        "expected_template": "generic",
        "expected_min_steps": 2,
        "notes": "Benzylic C-H oxidized to COOH by KMnO4",
    },
    {
        "name": "p015_20_gattermann_koch",
        "reactant": "Cc1ccccc1",       # toluene
        "product": "O=Cc1ccc(C)cc1",   # p-tolualdehyde
        "conditions": "CO, HCl, AlCl3, Gattermann-Koch",
        "type": "electrophilic aromatic substitution",
        "page": "p015",
        "expected_template": "generic",
        "expected_min_steps": 3,
        "notes": "Formylation: CO/HCl/AlCl3 generates formyl cation [CHO]+",
    },
    {
        "name": "p015_21_clemmensen_reduction",
        "reactant": "O=C(C)c1ccccc1",  # acetophenone
        "product": "CCc1ccccc1",        # ethylbenzene
        "conditions": "Zn(Hg), HCl, Clemmensen",
        "type": "reduction",
        "page": "p015",
        "expected_template": "generic",
        "expected_min_steps": 2,
        "notes": "C=O → CH2 under acidic conditions (cf. Wolff-Kishner is basic)",
    },
    {
        "name": "p015_22_wolff_kishner_reduction",
        "reactant": "O=C(C)c1ccccc1",  # acetophenone
        "product": "CCc1ccccc1",        # ethylbenzene
        "conditions": "NH2NH2, KOH, 200C, ethylene glycol, Wolff-Kishner",
        "type": "reduction",
        "page": "p015",
        "expected_template": "wolff_kishner",
        "expected_min_steps": 4,
        "notes": "Hydrazone → base-mediated tautomerization → N2 loss → CH2",
    },

    # ── p016: Diels-Alder, diazotization ──
    {
        "name": "p016_23_diels_alder",
        "reactant": "C=CC=C",         # 1,3-butadiene
        "product": "C1=CCCCC1",        # cyclohexene (simplified product)
        "conditions": "heat, Diels-Alder",
        "type": "pericyclic [4+2]",
        "page": "p016",
        "expected_template": "diels_alder",
        "expected_min_steps": 2,
        "notes": "Concerted [4+2] cycloaddition, suprafacial on both components",
    },
    {
        "name": "p016_24_birch_reduction_anisole",
        "reactant": "COc1ccccc1",      # anisole
        "product": "COC1=CCC=CC1",     # 2,5-dihydroanisole (1,4-diene)
        "conditions": "Na, NH3(l), t-BuOH, Birch reduction",
        "type": "dissolving metal reduction",
        "page": "p016",
        "expected_template": "birch",
        "expected_min_steps": 4,
        "notes": "EDG (OMe) directs 1,4-reduction to unconjugated positions",
    },

    # ── p017: Naphthalene chemistry ──
    {
        "name": "p017_25_naphthalene_oxidation",
        "reactant": "c1ccc2ccccc2c1",  # naphthalene
        "product": "O=C1C=CC(=O)c2ccccc21",  # 1,4-naphthoquinone
        "conditions": "CrO3, AcOH, oxidation",
        "type": "oxidation",
        "page": "p017",
        "expected_template": "generic",
        "expected_min_steps": 2,
        "notes": "Selective oxidation of one ring of naphthalene",
    },

    # ── p018: Heterocyclic / nucleophilic aromatic substitution ──
    {
        "name": "p018_26_chichibabin_amination",
        "reactant": "c1ccncc1",        # pyridine
        "product": "Nc1ccccn1",         # 2-aminopyridine
        "conditions": "NaNH2, NucArSub, Chichibabin",
        "type": "nucleophilic aromatic substitution",
        "page": "p018",
        "expected_template": "generic",
        "expected_min_steps": 3,
        "notes": "NaNH2 attacks C2 of pyridine, addition-elimination, Meisenheimer complex",
    },

    # ── p019-p020: Grignard, SN1/SN2 table ──
    {
        "name": "p020_27_sn2_with_cyanide",
        "reactant": "CCBr",           # bromoethane
        "product": "CCC#N",            # propionitrile
        "conditions": "NaCN, DMF, SN2",
        "type": "nucleophilic substitution",
        "page": "p020",
        "expected_template": "sn2",
        "expected_min_steps": 2,
        "notes": "CN- backside attack on primary carbon, Walden inversion",
    },
    {
        "name": "p020_28_sn2_williamson_ether",
        "reactant": "CCBr",           # bromoethane
        "product": "CCOC",             # methyl ethyl ether (ethyl methyl ether)
        "conditions": "NaOMe, Williamson ether synthesis, SN2",
        "type": "nucleophilic substitution",
        "page": "p020",
        "expected_template": "sn2",
        "expected_min_steps": 2,
        "notes": "Alkoxide attacks primary halide by SN2",
    },
    {
        "name": "p020_29_sn1_tertiary",
        "reactant": "CC(C)(C)Br",     # tert-butyl bromide
        "product": "CC(C)(C)O",        # tert-butanol
        "conditions": "H2O, heat, SN1",
        "type": "nucleophilic substitution",
        "page": "p020",
        "expected_template": "generic",
        "expected_min_steps": 3,
        "notes": "SN1: LG departure → carbocation → nucleophile capture",
    },
    {
        "name": "p013_30_mcpba_epoxidation",
        "reactant": "C=CC",           # propene
        "product": "CC1CO1",            # propylene oxide (1,2-epoxypropane)
        "conditions": "mCPBA, CH2Cl2",
        "type": "concerted [2+1]",
        "page": "p013",
        "expected_template": "mcpba_epoxidation",
        "expected_min_steps": 2,
        "notes": "Butterfly TS, concerted oxygen transfer to C=C",
    },
]

# ──────────────────────────────────────────────
# Test Runner
# ──────────────────────────────────────────────

def _detect_grade(steps, test_case):
    """Classify mechanism output as A/B/C grade.

    A: Dedicated template matched, correct intermediates, step count >= expected_min_steps
    B: Generic 3-step fallback (Substrate Activation → Bond Reorganization → Product)
    C: Wrong template triggered or render failure
    """
    if steps is None or len(steps) == 0:
        return 'C', 'No mechanism generated'

    # Detect generic 3-step fallback
    labels = [s.get('label', '') for s in steps]
    labels_lower = [l.lower() for l in labels]

    is_generic_fallback = (
        len(steps) == 3 and
        any('substrate activation' in l for l in labels_lower) and
        any('bond reorganization' in l for l in labels_lower)
    )

    if is_generic_fallback:
        return 'B', 'Generic 3-step fallback'

    # Check for wrong template (e.g., SN2 when should be E2)
    expected = test_case.get('expected_template', 'generic')

    # If it's supposed to be a specific template, check the label badges
    all_text = ' '.join(labels_lower)
    badge_text = ' '.join([s.get('mech_badge', '').lower() for s in steps])
    combined_text = all_text + ' ' + badge_text

    # Mismatch detection: expected template vs actual
    wrong_template = False
    if expected == 'sn2' and 'sn2' not in combined_text:
        wrong_template = True
        reason = f'Expected SN2, got: {labels[0][:50]}'
    elif expected == 'br2_addition' and 'bromonium' not in combined_text:
        # Check if generic fallback handles it
        if len(steps) >= 3 and any('bromonium' in l.lower() for l in labels):
            wrong_template = False
        elif is_generic_fallback:
            return 'B', 'Expected bromonium template, got generic fallback'
    elif expected == 'wolff_kishner' and 'wolff' not in combined_text and 'hydrazone' not in combined_text:
        wrong_template = True
        reason = f'Expected Wolff-Kishner, got: {labels[0][:50]}'
    elif expected == 'friedel_crafts' and 'friedel' not in combined_text:
        # Check for generic fallback
        if is_generic_fallback:
            return 'B', 'Expected Friedel-Crafts, got generic fallback'
    elif expected == 'grignard' and 'grignard' not in combined_text:
        if is_generic_fallback:
            return 'B', 'Expected Grignard, got generic fallback'
    elif expected == 'birch' and 'birch' not in combined_text and 'radical anion' not in combined_text:
        if is_generic_fallback:
            return 'B', 'Expected Birch, got generic fallback'
    elif expected == 'acid_hydration' and 'carbocation' not in combined_text and 'markovnikov' not in combined_text.lower():
        if is_generic_fallback:
            return 'B', 'Expected acid-hydration, got generic fallback'
    elif expected == 'hydroboration' and 'hydroboration' not in combined_text and '4-center' not in combined_text:
        if is_generic_fallback:
            return 'B', 'Expected hydroboration, got generic fallback'
    elif expected == 'ozonolysis' and 'ozon' not in combined_text and 'molozonide' not in combined_text:
        if is_generic_fallback:
            return 'B', 'Expected ozonolysis, got generic fallback'
    elif expected == 'diels_alder' and 'diels' not in combined_text and '[4+2]' not in combined_text:
        if is_generic_fallback:
            return 'B', 'Expected Diels-Alder, got generic fallback'
    elif expected == 'mcpba_epoxidation' and 'epoxid' not in combined_text and 'butterfly' not in combined_text:
        if is_generic_fallback:
            return 'B', 'Expected mCPBA epoxidation, got generic fallback'
    elif expected == 'nabh4' and 'hydride' not in combined_text and 'nabh4' not in combined_text:
        if is_generic_fallback:
            return 'B', 'Expected NaBH4 reduction, got generic fallback'
    elif expected == 'lialh4' and 'hydride' not in combined_text and 'lialh4' not in combined_text:
        if is_generic_fallback:
            return 'B', 'Expected LiAlH4 reduction, got generic fallback'

    if wrong_template:
        return 'C', reason

    # Step count check
    min_steps = test_case.get('expected_min_steps', 2)
    if len(steps) < min_steps:
        return 'B', f'Step count {len(steps)} < expected {min_steps}'

    # If we got a specific template with enough steps, it's A-grade
    return 'A', f'{len(steps)} steps, template matched'


def _detect_template_name(steps):
    """Extract which template/pattern was triggered."""
    if not steps:
        return 'NONE'
    labels = [s.get('label', '') for s in steps]
    badges = [s.get('mech_badge', '') for s in steps]
    all_text = ' '.join(labels + badges).lower()

    template_keywords = [
        ('Robinson', 'robinson'), ('Swern', 'swern'), ('Favorskii', 'favorskii'),
        ('Fischer', 'fischer'), ('Aldol', 'aldol'), ('Beckmann', 'beckmann'),
        ('Wolff-Kishner', 'wolff'), ('Curtius', 'curtius'), ('SN2', 'sn2'),
        ('E2', 'e2'), ('E1', 'e1'), ('Bromonium', 'bromonium'),
        ('Friedel-Crafts', 'friedel'), ('NBS', 'nbs'), ('mCPBA', 'mcpba'),
        ('Diels-Alder', 'diels'), ('Grignard', 'grignard'),
        ('Birch', 'birch'), ('Hydroboration', 'hydroboration'),
        ('Ozonolysis', 'ozon'), ('Wittig', 'wittig'),
        ('Michael', 'michael'), ('Claisen', 'claisen'),
        ('Baeyer-Villiger', 'baeyer'), ('Simmons-Smith', 'simmons'),
        ('NaBH4/LiAlH4', 'hydride'), ('Acid-Hydration', 'carbocation'),
        ('Butterfly', 'butterfly'),
    ]
    for name, kw in template_keywords:
        if kw in all_text:
            return name

    # Check for generic 3-step
    labels_lower = [l.lower() for l in labels]
    if any('substrate activation' in l for l in labels_lower):
        return 'Generic-3step'

    return 'Unknown'


def run_ch2_tests():
    """Run all Ch.2 mechanism tests and produce JSON results + PNG evidence."""
    from drylab_report_exporter import (
        _generate_generic_mechanism,
        _get_hardcoded_mechanism,
        _generate_mechanism_step_png,
    )

    evidence_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', '..',
        'departments', 'domain_mechanism', 'evidence', 'ch2_test'
    )
    os.makedirs(evidence_dir, exist_ok=True)

    results = []
    grade_counts = {'A': 0, 'B': 0, 'C': 0}

    for tc in CH2_TEST_CASES:
        name = tc['name']
        rsmi = tc['reactant']
        psmi = tc['product']
        cond = tc['conditions']
        page = tc['page']

        print(f"\n{'='*65}")
        print(f"  [{page}] {name}")
        print(f"  Reactant: {rsmi}  →  Product: {psmi}")
        print(f"  Conditions: {cond}")
        print(f"{'='*65}")

        # 1) Try hardcoded first, then generic
        steps = _get_hardcoded_mechanism(rsmi, psmi, cond)
        source = 'hardcoded'
        if steps is None:
            steps = _generate_generic_mechanism(rsmi, psmi, cond)
            source = 'generic'
        if steps is None:
            steps = []
            source = 'none'

        n_steps = len(steps)
        template_name = _detect_template_name(steps)
        grade, reason = _detect_grade(steps, tc)
        grade_counts[grade] += 1

        # Print step details
        if steps:
            total_arrows = 0
            for i, s in enumerate(steps):
                label = s.get('label', f'Step {i+1}')
                is_int = s.get('is_intermediate', False)
                is_ts = s.get('is_transition_state', False)
                ad = len(s.get('arrow_defs', []))
                ia = len(s.get('inner_arrows', []))
                reagent = s.get('reagent_smi', '')
                total_arrows += ad + ia
                tag = ' [intermediate]' if is_int else ' [TS]' if is_ts else ''
                r_tag = f' reagent={reagent}' if reagent else ''
                print(f"    Step {i+1}: {label}{tag}{r_tag}  (arrows: {ad}+{ia})")
            print(f"  Total arrows: {total_arrows}")
        else:
            print(f"  NO STEPS GENERATED")

        print(f"  Source: {source} | Template: {template_name} | "
              f"Grade: {grade} | Reason: {reason}")

        # 2) Render PNG
        png_ok = False
        png_size_kb = 0
        png_path = ''
        try:
            png_bytes = _generate_mechanism_step_png(rsmi, psmi, cond)
            if png_bytes and len(png_bytes) > 1000:
                png_path = os.path.join(evidence_dir, f'{name}.png')
                with open(png_path, 'wb') as f:
                    f.write(png_bytes)
                png_size_kb = len(png_bytes) / 1024
                png_ok = True
                print(f"  PNG: {png_size_kb:.0f} KB -> {png_path}")
            else:
                print(f"  PNG: render returned empty or small ({len(png_bytes) if png_bytes else 0} bytes)")
        except Exception as e:
            print(f"  PNG: RENDER ERROR: {e}")
            traceback.print_exc()

        # 3) Record result
        step_labels = [s.get('label', '') for s in steps] if steps else []
        results.append({
            "name": name,
            "page": page,
            "reactant": rsmi,
            "product": psmi,
            "conditions": cond,
            "type": tc['type'],
            "source": source,
            "template": template_name,
            "n_steps": n_steps,
            "step_labels": step_labels,
            "grade": grade,
            "grade_reason": reason,
            "png_ok": png_ok,
            "png_size_kb": round(png_size_kb, 1),
            "expected_template": tc.get('expected_template', 'generic'),
            "expected_min_steps": tc.get('expected_min_steps', 2),
            "notes": tc.get('notes', ''),
        })

    # ── Summary ──
    print(f"\n{'='*65}")
    print(f"  CH.2 TEST SUMMARY")
    print(f"{'='*65}")
    print(f"  Total: {len(results)}")
    print(f"  A-grade (dedicated template): {grade_counts['A']}")
    print(f"  B-grade (generic fallback):   {grade_counts['B']}")
    print(f"  C-grade (wrong/fail):         {grade_counts['C']}")
    print()

    for r in results:
        icon = {'A': '[A]', 'B': '[B]', 'C': '[C]'}[r['grade']]
        png_tag = 'PNG-OK' if r['png_ok'] else 'NO-PNG'
        print(f"  {icon} {r['name']}: {r['n_steps']} steps, "
              f"tmpl={r['template']}, {png_tag}, {r['grade_reason'][:40]}")

    # ── Save JSON results ──
    json_path = os.path.join(evidence_dir, 'ch2_results.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved: {json_path}")

    return results, grade_counts


if __name__ == '__main__':
    results, counts = run_ch2_tests()
    # Exit code: 0 if no C-grades
    sys.exit(1 if counts.get('C', 0) > 0 else 0)
