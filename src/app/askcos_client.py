#!/usr/bin/env python3
"""
ASKCOS API Client for ChemGrid retrosynthesis integration.

ASKCOS (Automated Synthesis Planning via Computer-Assisted Synthesis):
MIT 개발 역합성 분석 플랫폼. 1M+ 문헌 기반 반응 템플릿 (Reaxys/USPTO).
토큰 불필요 (공개 엔드포인트 사용).

v1 (2026-04-19): Initial integration
- expand_one: 1단계 역합성 (빠름, ~1-5s)
- tree_search: 다단계 MCTS 트리 탐색 (느림, ~30-60s)
- 결과 캐싱 (동일 분자 반복 호출 방지)
- 네트워크 오류 시 graceful fallback

v1.1 (2026-04-21): 시약/용매/조건 추론 강화 (M165/P0-A fix)
- "Unknown transformation" fallback 완전 제거
- 작용기 변화 분석 기반 시약/용매/온도 추론 (10+ 패턴)
- retrosynthesis_engine.FRAGMENT_CONDITION_MAP 재사용
- Rule M/N 준수: silent failure 금지, 타입 가드

v1.2 (2026-05-06): M852 — ASKCOS multi-endpoint + IBM RXN fallback
- ASKCOS mirror URLs: MIT primary → MLPDS mirror → self-hosted fallback
- IBM RXN for Chemistry (Schwaller 2020) REST API fallback
- 학술 인용: Schwaller, P. et al. (2020) Chem. Sci. 11: 3316-3325.
"""
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

logger = logging.getLogger(__name__)

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# ─────────────────────────────────────────────────────────────
# FP-15: SIMULATION_MODE markers for external engines
# ASKCOS: public MIT endpoint (no token) — may be offline/unreachable.
#   Results fall back to local SMARTS heuristics when offline.
# IBM RXN: requires RXN4CHEMISTRY_API_KEY env var (Rule I: no hardcoding).
#   SIMULATION_MODE when key absent or server unreachable.
#   ACADEMIC_INTEGRITY: IBM RXN results are transformer-based estimates
#   (Schwaller 2020 Chem.Sci. 11:3316); not verified wet-lab routes.
# OpenBabel: optional dependency for PDBQT conversion (OBABEL_AVAILABLE in docking_interface.py).
#   Absent → RDKit-only fallback (no structural data lost, format only).
# ─────────────────────────────────────────────────────────────
_IBM_RXN_API_KEY_PRESENT: bool = bool(os.environ.get("RXN4CHEMISTRY_API_KEY", "").strip())
IBM_RXN_SIMULATION_MODE: bool = not _IBM_RXN_API_KEY_PRESENT
if IBM_RXN_SIMULATION_MODE:
    # FP-15: IBM RXN API key absent — client will return [] on calls; no real transformer output
    logger.info(
        "[askcos_client] IBM_RXN_SIMULATION_MODE=True — "
        "RXN4CHEMISTRY_API_KEY not set; IBM RXN fallback inactive (Schwaller 2020)"
    )

# ═══════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════

@dataclass
class ASKCOSPrecursor:
    """One-step retrosynthesis result from ASKCOS expand-one."""
    outcome_smiles: str         # Precursor SMILES (dot-separated if multiple)
    score: float                # Plausibility score (0-1, higher = more plausible)
    template_smarts: str        # Reaction SMARTS template applied
    template_set: str           # Template source (e.g., "reaxys")
    num_examples: int           # Number of literature examples for this template
    rank: int                   # Rank among results


@dataclass
class ASKCOSReaction:
    """A single reaction step in a tree-search route."""
    target: str                 # Product SMILES
    precursors: List[str]       # Reactant SMILES list
    template_smarts: str        # Reaction template
    score: float                # Plausibility
    conditions: str             # Inferred conditions


@dataclass
class ASKCOSRoute:
    """Multi-step synthesis route from ASKCOS tree search."""
    target_smiles: str
    reactions: List[ASKCOSReaction]
    total_steps: int
    overall_score: float
    building_blocks: List[str]  # Terminal (buyable) nodes


# ═══════════════════════════════════════════════════════════
# Reaction inference helpers (v1.1 — M165/P0-A fix)
# "Unknown transformation" 완전 제거, 작용기 변화 기반 추론 강화
# ═══════════════════════════════════════════════════════════

# Common reaction pattern recognition from template SMARTS
# (이름, 시약, 용매, 온도/시간)  ← 3줄 표시용 tuple로 확장
_REACTION_PATTERNS: Dict[str, Tuple[str, str, str, str]] = {
    # Amide bond formation
    'C(=O)N':   ('Amide coupling',             'EDC·HCl (1.2 eq), HOBt (1.2 eq), DIPEA (3 eq)', 'DMF, RT',      '12 h'),
    'NC(=O)':   ('Amide coupling',             'EDC·HCl (1.2 eq), HOBt (1.2 eq), DIPEA (3 eq)', 'DMF, RT',      '12 h'),
    # Suzuki coupling
    'c:c':      ('Suzuki coupling',             'Pd(PPh₃)₄ (5 mol%), Na₂CO₃ (2M aq., 3 eq)',    'DME/H₂O (3:1), 80°C', '12 h'),
    '[c:1]-[c:2]': ('Suzuki coupling',         'Pd(PPh₃)₄ (5 mol%), Na₂CO₃ (2M aq., 3 eq)',    'DME/H₂O (3:1), 80°C', '12 h'),
    # Ester formation (Fischer)
    'C(=O)O':  ('Fischer esterification',      'H₂SO₄ (cat., 5 mol%), Dean-Stark',              'toluene, reflux (110°C)', '12 h'),
    'OC(=O)':  ('Fischer esterification',      'H₂SO₄ (cat., 5 mol%), Dean-Stark',              'toluene, reflux (110°C)', '12 h'),
    # Alcohol formation (ketone/aldehyde reduction)
    '[C:1]([OH])': ('Carbonyl reduction',      'NaBH₄ (1.1 eq)',                                'MeOH, 0°C → rt', '1 h'),
    # Aromatic hydroxylation (phenol)
    'c-O':     ('Aromatic hydroxylation',      'H₂O₂ (2 eq), TFA (cat.) or Dakin oxidation',   'AcOH/H₂O, 60°C', '3 h'),
    # Wittig / Horner-Wadsworth-Emmons
    'C=C':     ('Wittig olefination',          'Ph₃P=CHR (1.2 eq) or NaH + phosphonate (HWE)', 'THF, -78°C → rt', '12 h'),
    # Grignard / organometallic C-C
    'C-C':     ('Grignard addition',           'RMgBr (1.5 eq, in Et₂O)',                       'THF, 0°C → rt', '2 h'),
    # Friedel-Crafts acylation
    'c-C(=O)': ('Friedel-Crafts acylation',   'AlCl₃ (1.1 eq), RCOCl (1.05 eq)',               'CH₂Cl₂, 0°C → rt', '2 h'),
    # Buchwald-Hartwig amination
    'c-N':     ('Buchwald-Hartwig amination', 'Pd₂(dba)₃ (2 mol%), BINAP (4 mol%), NaOtBu (1.4 eq)', 'toluene, 100°C', '16 h'),
    # Aldol condensation
    'CC(O)CC=O': ('Aldol condensation',        'NaOH (0.1 eq)',                                 'H₂O/EtOH (1:1), 0°C → rt', '2 h'),
    # Heck coupling
    'C=Cc':    ('Heck coupling',               'Pd(OAc)₂ (5 mol%), PPh₃ (10 mol%), Et₃N (2 eq)', 'DMF, 120°C', '16 h'),
    # Reductive amination
    'CN':      ('Reductive amination',         'NaBH₃CN (1.5 eq), AcOH (0.1 eq)',               'MeOH, pH 6-7, rt', '4 h'),
    # Halide introduction
    'CBr':     ('Bromination (allylic/radical)', 'NBS (1.05 eq), AIBN (cat.)',                  'CCl₄, 80°C (reflux)', '2 h'),
    'CCl':     ('Chlorination (acyl)',          'SOCl₂ (1.5 eq), cat. DMF',                     'neat or CH₂Cl₂, reflux', '2 h'),
    # Williamson ether
    'COC':     ('Williamson ether synthesis',  'NaH (1.2 eq), R-X (1.1 eq)',                    'THF, 0°C → rt, Ar atm.', '2 h'),
    # N-alkylation
    'CN(C)':   ('N-Alkylation',               'K₂CO₃ (2 eq), R-X (1.1 eq)',                    'DMF, 80°C', '6 h'),
    # Nitration (aromatic)
    'c-[N+](=O)': ('Electrophilic nitration', 'HNO₃ (1.05 eq), H₂SO₄ (conc., 2 eq)',          'H₂SO₄ (0°C → 5°C)', '1 h'),
    # Dihydroxylation (Upjohn)
    'C(O)C(O)': ('Dihydroxylation',           'OsO₄ (cat., 1 mol%), NMO (1.5 eq)',              'acetone/H₂O (4:1), rt', '12 h'),
}

# ─── SMARTS-based functional group detection patterns ──────────────────────────
# retrosynthesis_engine.FRAGMENT_CONDITION_MAP 재사용 (타입 가드 포함, Rule N)
def _get_fragment_condition_map() -> Dict[str, str]:
    """retrosynthesis_engine.FRAGMENT_CONDITION_MAP 안전 로드 (타입 가드 + fallback)."""
    try:
        import retrosynthesis_engine as _retro  # noqa: PLC0415
        fmap = getattr(_retro, 'FRAGMENT_CONDITION_MAP', None)
        if not isinstance(fmap, dict):  # Rule N 타입 가드
            logger.warning("FRAGMENT_CONDITION_MAP is not dict: %s", type(fmap))
            return {}
        return fmap
    except Exception as e:
        logger.warning("Could not load FRAGMENT_CONDITION_MAP from retrosynthesis_engine: %s", e)
        return {}


def _count_oh_groups(mol) -> int:
    """RDKit mol의 -OH 그룹 개수 반환."""
    if mol is None:
        return 0
    patt_alc = Chem.MolFromSmarts('[OX2H]')
    patt_phe = Chem.MolFromSmarts('c[OH]')
    if patt_alc is None or patt_phe is None:
        return 0
    matches = mol.GetSubstructMatches(patt_alc) + mol.GetSubstructMatches(patt_phe)
    return len(matches)


def _count_carbonyl(mol) -> int:
    """RDKit mol의 C=O 개수 (알데히드+케톤+카복실+에스터 포함)."""
    if mol is None:
        return 0
    patt = Chem.MolFromSmarts('[CX3]=[OX1]')
    if patt is None:
        return 0
    return len(mol.GetSubstructMatches(patt))


def _count_aromatic_rings(mol) -> int:
    """RDKit mol의 방향족 고리 수 (NumAtomRings 기반 방향족 원자 여부 체크)."""
    if mol is None:
        return 0
    try:
        # RDKit 2025 호환: NumAromaticRings 대신 방향족 원자 포함 고리 수동 카운트
        ring_info = mol.GetRingInfo()
        atom_rings = ring_info.AtomRings()
        count = 0
        for ring in atom_rings:
            if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring):
                count += 1
        return count
    except Exception as e:
        logger.warning("_count_aromatic_rings failed: %s", e)
        return 0


def _analyze_fg_change(reactants: List[str], product: str) -> Tuple[str, str, str, str]:
    """작용기 변화 분석으로 반응명 + 3줄 조건 추론.

    Returns: (rxn_name, reagent_line, solvent_temp_line, catalyst_line)
    Rule N: 외부 SMILES 파싱 실패 시 logger.warning + fallback 반환 (Rule M 준수)
    """
    if not RDKIT_AVAILABLE:
        return ("Transform: reagent TBD — consult Reaxys", "", "", "")

    # ── 생성물 파싱 (Rule L: MolFromSmiles + None 체크) ──────────────────────
    prod_mol = None
    if product:
        prod_mol = Chem.MolFromSmiles(product)
        if prod_mol is None:
            logger.warning("_analyze_fg_change: product SMILES parse failed: %s", product[:60])

    # ── 반응물 파싱 ──────────────────────────────────────────────────────────
    react_mols = []
    for smi in (reactants or []):
        if not isinstance(smi, str) or not smi:  # Rule N 타입 가드
            continue
        m = Chem.MolFromSmiles(smi)
        if m is None:
            logger.warning("_analyze_fg_change: reactant SMILES parse failed: %s", smi[:60])
        react_mols.append(m)

    prod_oh  = _count_oh_groups(prod_mol)
    prod_co  = _count_carbonyl(prod_mol)
    prod_ar  = _count_aromatic_rings(prod_mol)
    react_oh = sum(_count_oh_groups(m) for m in react_mols)
    react_co = sum(_count_carbonyl(m)  for m in react_mols)
    react_ar = sum(_count_aromatic_rings(m) for m in react_mols)

    # ── 패턴 매칭 (McMurry 교과서 기준) ────────────────────────────────────────
    # 1) 케톤/알데히드 → 알코올 (환원)
    if prod_oh > react_oh and react_co > prod_co:
        return (
            "Carbonyl reduction",
            "NaBH₄ (1.1 eq)",
            "MeOH, 0°C → rt",
            "",
        )

    # 2) 알코올 → 케톤/알데히드 (산화)
    if prod_co > react_co and react_oh > prod_oh:
        return (
            "Swern oxidation",
            "(COCl)₂ (1.2 eq), DMSO (2 eq), Et₃N (3 eq)",
            "CH₂Cl₂, -78°C → rt",
            "",
        )

    # 3) 비방향족 → 방향족 (芳香족화 — 이중결합 도입)
    if prod_ar > react_ar:
        return (
            "Aromatization / dehydrogenation",
            "DDQ (1.5 eq) or Pd/C (5 wt%), H₂ (1 atm)",
            "toluene, reflux",
            "cat. Pd/C",
        )

    # 4) 페놀 신규 생성 (aromatic + OH)
    patt_phenol = Chem.MolFromSmarts('c[OH]') if RDKIT_AVAILABLE else None
    if (prod_mol is not None and patt_phenol is not None
            and prod_mol.HasSubstructMatch(patt_phenol)
            and react_oh == 0):
        return (
            "Dakin oxidation (aromatic hydroxylation)",
            "H₂O₂ (2 eq), cat. TFA or mCPBA",
            "AcOH/H₂O, 60°C",
            "",
        )

    # 5) 에스터 생성
    patt_ester = Chem.MolFromSmarts('[CX3](=O)[OX2][CX4]') if RDKIT_AVAILABLE else None
    react_ester = sum(
        len(m.GetSubstructMatches(patt_ester)) for m in react_mols
        if m is not None and patt_ester is not None
    )
    prod_ester = (len(prod_mol.GetSubstructMatches(patt_ester))
                  if prod_mol is not None and patt_ester is not None else 0)
    if prod_ester > react_ester:
        return (
            "Fischer esterification",
            "H₂SO₄ (cat., 5 mol%), Dean-Stark",
            "toluene, reflux (110°C)",
            "",
        )

    # 6) 아미드 생성
    patt_amide = Chem.MolFromSmarts('[CX3](=O)[NX3]') if RDKIT_AVAILABLE else None
    react_amide = sum(
        len(m.GetSubstructMatches(patt_amide)) for m in react_mols
        if m is not None and patt_amide is not None
    )
    prod_amide = (len(prod_mol.GetSubstructMatches(patt_amide))
                  if prod_mol is not None and patt_amide is not None else 0)
    if prod_amide > react_amide:
        return (
            "Amide coupling",
            "EDC·HCl (1.2 eq), HOBt (1.2 eq), DIPEA (3 eq)",
            "DMF, rt",
            "",
        )

    # 7) 원자수 증가 없이 C 줄어듦 (탈보호 or 가수분해)
    react_heavy = sum(m.GetNumHeavyAtoms() for m in react_mols if m is not None)
    prod_heavy  = prod_mol.GetNumHeavyAtoms() if prod_mol is not None else 0
    if react_heavy > 0 and prod_heavy < react_heavy * 0.7:
        return (
            "Hydrolysis / deprotection",
            "NaOH (2M, 3 eq) or HCl (2M, 3 eq)",
            "H₂O/EtOH (1:1), reflux",
            "",
        )

    # 8) 할로겐 제거 (RX → RY 치환)
    has_halogen_r = any(
        m is not None and any(
            a.GetAtomicNum() in (9, 17, 35, 53)
            for a in m.GetAtoms()
        )
        for m in react_mols
    )
    has_halogen_p = (prod_mol is not None and any(
        a.GetAtomicNum() in (9, 17, 35, 53) for a in prod_mol.GetAtoms()))
    if has_halogen_r and not has_halogen_p and prod_oh > 0:
        return (
            "SN2 substitution (OH⁻ nucleophile)",
            "NaOH (2 eq)",
            "H₂O/DMSO (1:1), rt",
            "",
        )

    # 9) Boronate 시약 존재 → Suzuki coupling
    for m in react_mols:
        if m is not None and any(a.GetAtomicNum() == 5 for a in m.GetAtoms()):
            return (
                "Suzuki coupling",
                "Pd(PPh₃)₄ (5 mol%), Na₂CO₃ (2M aq., 3 eq)",
                "DME/H₂O (3:1), 80°C",
                "cat. Pd(PPh₃)₄",
            )

    # 10) Sn 시약 → Stille coupling
    for m in react_mols:
        if m is not None and any(a.GetAtomicNum() == 50 for a in m.GetAtoms()):
            return (
                "Stille coupling",
                "Pd(PPh₃)₄ (5 mol%), CuI (0.1 eq), LiCl (3 eq)",
                "DMF, 90°C",
                "cat. Pd(PPh₃)₄",
            )

    # 최종 fallback — "Unknown" 완전 제거, 최소한 범주 제공 (Rule M)
    logger.warning(
        "_analyze_fg_change: no pattern matched for product=%s reactants=%s",
        (product or "")[:40], [(s or "")[:20] for s in (reactants or [])]
    )
    return (
        "Retrosynthetic transform",
        "Reagent TBD — consult Reaxys/SciFinder",
        "Solvent TBD",
        "",
    )


def _infer_reaction_name(template_smarts: str, reactants: List[str],
                         product: str) -> str:
    """Infer a human-readable reaction name from template SMARTS and structures.

    v1.1: "Unknown transformation" 완전 제거 (M165 P0-A fix).
    1) SMARTS 패턴 매칭 → 2) FG 변화 분석 → 3) 범주 fallback
    """
    # ── 1단계: SMARTS 패턴 딕셔너리 매칭 ──────────────────────────────────────
    if template_smarts:
        for pattern, (name, _reagent, _solvent, _cat) in _REACTION_PATTERNS.items():
            if pattern in template_smarts:
                return name

        # SMARTS >> 분해로 힌트
        if '>>' in template_smarts:
            parts = template_smarts.split('>>')
            if len(parts) == 2:
                lhs, rhs = parts[0], parts[1]
                if 'N' in lhs and 'C(=O)' in rhs:
                    return "Amide bond formation"
                if 'O' in lhs and 'C(=O)' in rhs:
                    return "Ester bond formation"
                if '[B' in lhs or 'B(' in lhs:
                    return "Suzuki coupling"
                if '[Sn' in lhs:
                    return "Stille coupling"
                if '[Mg' in lhs or '[Li' in lhs:
                    return "Organometallic addition (Grignard/Organolithium)"

    # ── 2단계: 작용기 변화 분석 ───────────────────────────────────────────────
    name, _r, _s, _c = _analyze_fg_change(reactants, product)
    return name


def _infer_conditions(template_smarts: str, template_set: str,
                      reactants: Optional[List[str]] = None,
                      product: Optional[str] = None) -> str:
    """Infer reaction conditions — 시약/용매/온도/시간 포함 전체 조건 문자열.

    v1.1: "Literature conditions (Reaxys)" 플레이스홀더 완전 제거 (M165 P0-A fix).
    반환 형식: "시약 | 용매, 온도 | 시간"  (popup_synthesis 3줄 파싱용)
    """
    # ── 1단계: SMARTS 패턴 딕셔너리 매칭 ──────────────────────────────────────
    for pattern, (_name, reagent, solvent_temp, _cat) in _REACTION_PATTERNS.items():
        if pattern in (template_smarts or ""):
            return f"{reagent} | {solvent_temp}"

    # ── 2단계: retrosynthesis_engine.FRAGMENT_CONDITION_MAP 재사용 ───────────
    fmap = _get_fragment_condition_map()
    if fmap and template_set:
        for key, cond in fmap.items():
            if not isinstance(key, str) or not isinstance(cond, str):  # Rule N
                continue
            if key.lower() in (template_set or "").lower():
                return cond

    # ── 3단계: 작용기 변화 분석 ───────────────────────────────────────────────
    if reactants is not None and product is not None:
        _name, reagent, solvent_temp, cat = _analyze_fg_change(reactants, product)
        parts = [p for p in [reagent, solvent_temp, cat] if p]
        if parts:
            return " | ".join(parts)

    # ── 최종 fallback (Rule M: "Unknown" 금지, 범주 제공) ────────────────────
    logger.warning(
        "_infer_conditions: fallback triggered for template_set=%s smarts=%s",
        template_set, (template_smarts or "")[:60]
    )
    return "Reagent TBD — consult Reaxys/SciFinder | Solvent TBD"


# ═══════════════════════════════════════════════════════════
# Conversion helpers (ASKCOS results -> SynthesisRoute format)
# ═══════════════════════════════════════════════════════════

def askcos_precursors_to_synthesis_steps(
    precursors: List[ASKCOSPrecursor], target_smiles: str
) -> List:
    """Convert ASKCOS precursor results to SynthesisStep objects.
    Returns list of (SynthesisStep-like dicts) for external consumption.
    Note: actual SynthesisStep creation is done in retrosynthesis_engine.py
    to avoid circular imports.
    """
    steps = []
    for i, p in enumerate(precursors):
        reactants = [s.strip() for s in p.outcome_smiles.split('.') if s.strip()]
        rxn_name = _infer_reaction_name(p.template_smarts, reactants, target_smiles)
        # v1.1: reactants + product 전달하여 FG 변화 분석 활성화 (M165 P0-A fix)
        conditions = _infer_conditions(
            p.template_smarts, p.template_set,
            reactants=reactants, product=target_smiles
        )
        steps.append({
            'step_number': 1,
            'reactant_smiles': reactants,
            'product_smiles': target_smiles,
            'transform_name': f"[ASKCOS] {rxn_name}",
            'transform_name_en': f"[ASKCOS] {rxn_name}",
            'conditions': conditions,
            'confidence': min(p.score + 0.3, 0.99),
        })
    return steps


def askcos_route_to_synthesis_route(route: ASKCOSRoute):
    """Convert an ASKCOSRoute (multi-step) to a SynthesisRoute-compatible object.
    Imports SynthesisRoute/SynthesisStep from retrosynthesis_engine to avoid
    duplicating data classes.
    """
    # Lazy import to avoid circular dependency
    from retrosynthesis_engine import SynthesisStep, SynthesisRoute

    steps = []
    for i, rxn in enumerate(route.reactions):
        rxn_name = _infer_reaction_name(rxn.template_smarts, rxn.precursors, rxn.target)
        # v1.1: reactants + product 전달 (M165 P0-A fix)
        inferred_cond = _infer_conditions(
            rxn.template_smarts, "reaxys",
            reactants=rxn.precursors, product=rxn.target
        )
        steps.append(SynthesisStep(
            step_number=i + 1,
            reactant_smiles=rxn.precursors,
            product_smiles=rxn.target,
            transform_name=f"[ASKCOS] {rxn_name}",
            transform_name_en=f"[ASKCOS] {rxn_name}",
            conditions=rxn.conditions or inferred_cond,
            confidence=min(rxn.score + 0.3, 0.99),
        ))

    return SynthesisRoute(
        target_smiles=route.target_smiles,
        steps=steps,
        total_steps=len(steps),
        score=max(0, (1.0 - route.overall_score) * 50),
        building_blocks=route.building_blocks,
        validated=True,
    )


# ═══════════════════════════════════════════════════════════
# Main Client Class
# ═══════════════════════════════════════════════════════════

class ASKCOSClient:
    """
    ASKCOS API client for retrosynthesis predictions.

    Uses MIT's public token-free endpoints:
    - expand-one: single-step retrosynthesis
    - tree-search: multi-step MCTS planning

    All results are cached in-memory to avoid redundant API calls.
    Timeout: 30s default per call. Graceful fallback on network errors.
    """

    BASE_URL = "https://askcos.mit.edu"

    # [M852] Multi-endpoint mirror list — primary fail 시 순차 시도 (Rule M: silent failure 금지)
    # 학술 인용: Coley, C.W. et al. (2019) ACS Cent. Sci. 5(9): 1572-1583.
    MIRROR_URLS = [
        "https://askcos.mit.edu",           # MIT primary
        "https://askcos2.mit.edu",          # MIT secondary (MLPDS)
    ]

    # Endpoints (token-free variants)
    EXPAND_ONE_URL = "/api/tree-search/expand-one/call-sync-without-token"
    TREE_SEARCH_URL = "/api/tree-search/mcts/call-sync-without-token"

    # M646_INTEGRATE: v2 API endpoint (사용자 로그인 후 사용 가능)
    # 사용 정책: 사용자가 askcos.mit.edu 로그인 컨텍스트에서 갱신된 v2 API 활용.
    # ASKCOS_TOKEN env var 있으면 Authorization 자동 첨부.
    EXPAND_ONE_URL_V2 = "/api/v2/retro/singlestep"
    TREE_SEARCH_URL_V2 = "/api/v2/retro/multistep"

    # [MAGIC:3] 최대 재시도 횟수 — 네트워크 일시 오류 복구용 (M849)
    MAX_RETRIES = 3
    # [MAGIC:1.5] 재시도 간 backoff 배수 (초) — 1.5, 3.0, 4.5s (M849)
    RETRY_BACKOFF = 1.5

    def __init__(self, timeout: int = 30):
        """Initialize client.

        Args:
            timeout: Default request timeout in seconds.
                     [MAGIC:30] ASKCOS 기본 응답 시간 (MIT 서버 평균 1-5s, 최대 ~25s).
        """
        self._timeout = timeout
        self._cache: Dict[str, object] = {}  # smiles_hash -> result
        self._session: Optional[object] = None
        self._last_error: Optional[str] = None  # M849: 최근 에러 추적 (Rule M)

    def get_last_error(self) -> str:
        """Return the latest ASKCOS connection/prediction error for UI surfacing."""
        return self._last_error or ""

    def _get_session(self):
        """Get or create a requests Session for connection pooling."""
        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests library not available")
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            })
        return self._session

    def _cache_key(self, prefix: str, smiles: str, **kwargs) -> str:
        """Generate a cache key from prefix + smiles + params."""
        raw = f"{prefix}:{smiles}:{sorted(kwargs.items())}"
        return hashlib.md5(raw.encode()).hexdigest()

    def is_available(self) -> bool:
        """Check if ASKCOS API is reachable via any mirror.

        [M852] multi-endpoint: MIT primary → mirrors 순차 시도.
        Returns True if any server responds within 5 seconds per attempt.
        Rule M: 실패 시 logger.warning (silent failure 금지).
        """
        if not REQUESTS_AVAILABLE:
            self._last_error = "requests library not installed"
            logger.warning("[ASKCOSClient] is_available: %s", self._last_error)
            return False

        # [M852] env var 오버라이드: ASKCOS_BASE_URL 있으면 mirror 리스트 맨 앞에 추가
        env_url = os.environ.get("ASKCOS_BASE_URL", "").strip().rstrip("/")
        mirrors = ([env_url] + self.MIRROR_URLS) if env_url else self.MIRROR_URLS

        payload = {
            "smiles": "CCO",
            "retro_backend_options": [
                {
                    "retro_backend": "template_relevance",
                    "retro_model_name": "reaxys",
                    "max_num_templates": 1,
                    "threshold": 0.3,
                    "top_k": 1,
                }
            ],
            "use_fast_filter": True,
            "fast_filter_threshold": 0.75,
        }
        for base_url in mirrors:
            try:
                session = self._get_session()
                resp = session.post(
                    f"{base_url}{self.EXPAND_ONE_URL}",
                    json=payload,
                    timeout=min(8, self._timeout),  # [MAGIC:8] bounded UI health probe
                )
                if resp.status_code == 200:
                    self._last_error = None
                    self.BASE_URL = base_url
                    logger.info("[ASKCOSClient] online via %s", base_url)
                    return True
                self._last_error = (
                    f"HTTP {resp.status_code} at {base_url}{self.EXPAND_ONE_URL}: "
                    f"{resp.text[:120]}"
                )
            except requests.exceptions.Timeout:
                self._last_error = f"timeout at {base_url}{self.EXPAND_ONE_URL}"
            except requests.exceptions.ConnectionError:
                self._last_error = f"connection refused at {base_url}{self.EXPAND_ONE_URL}"
            except Exception as e:
                self._last_error = f"{type(e).__name__}: {e}"
            logger.warning("[ASKCOSClient] is_available %s failed: %s",
                           base_url, self._last_error)
        return False

    def expand_one(self, smiles: str, top_k: int = 10) -> List[ASKCOSPrecursor]:
        """One-step retrosynthesis via ASKCOS API.

        Sends target SMILES to expand-one endpoint and returns ranked
        precursor sets with plausibility scores.

        Args:
            smiles: Target molecule SMILES (should be canonical)
            top_k: Maximum number of precursor sets to return

        Returns:
            List of ASKCOSPrecursor objects sorted by score (highest first)
        """
        # Check cache
        cache_key = self._cache_key("expand_one", smiles, top_k=top_k)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not REQUESTS_AVAILABLE:
            self._last_error = "requests library not installed"
            logger.warning("[ASKCOSClient] expand_one: %s", self._last_error)
            return []

        session = self._get_session()

        payload = {
            "smiles": smiles,
            "retro_backend_options": [
                {
                    "retro_backend": "template_relevance",
                    "retro_model_name": "reaxys",
                    "max_num_templates": 100,
                    "threshold": 0.3,
                    "top_k": top_k,
                }
            ],
            "use_fast_filter": True,
            "fast_filter_threshold": 0.75,
        }

        # M646_INTEGRATE: v1 → v2 fallback
        # 학술 인용: Coley, C.W. et al. (2019) ACS Cent. Sci. 5(9): 1572-1583.
        # ASKCOS_TOKEN env var 있으면 Authorization 헤더 첨부 (사용자 로그인 컨텍스트)
        askcos_token = os.environ.get("ASKCOS_TOKEN") or os.environ.get("ASKCOS_API_TOKEN")
        if askcos_token and isinstance(askcos_token, str) and askcos_token.strip():
            session.headers.update({"Authorization": f"Bearer {askcos_token.strip()}"})

        data = None
        last_error: Optional[str] = None
        # endpoint 후보 순서: 공식 token-free endpoint 우선.
        # Legacy/v2 후보는 공개 서버에서 404/timeout을 덮어써 원인 분석을 흐리므로
        # ASKCOS_TRY_LEGACY_ENDPOINTS=1일 때만 추가한다.
        endpoints_to_try = [self.EXPAND_ONE_URL]
        if os.environ.get("ASKCOS_TRY_LEGACY_ENDPOINTS", "").strip() == "1":
            endpoints_to_try.append(self.EXPAND_ONE_URL_V2)

        # [M1355_W184] Mirror list: primary BASE_URL 실패 시 순차 fallback 허용.
        # env var 오버라이드 포함 (is_available()과 동일 로직).
        env_url = os.environ.get("ASKCOS_BASE_URL", "").strip().rstrip("/")
        _mirror_list: List[str] = ([env_url] + list(self.MIRROR_URLS)) if env_url else list(self.MIRROR_URLS)
        # BASE_URL이 mirror_list에 없으면 맨 앞에 추가 (is_available()이 이미 선택한 경우)
        if self.BASE_URL not in _mirror_list:
            _mirror_list.insert(0, self.BASE_URL)
        # 이미 시도한 mirror 추적
        _tried_mirrors: list = []

        def _try_one_mirror(base_url: str) -> Optional[dict]:
            """단일 mirror URL에 대해 MAX_RETRIES 재시도. 성공 시 data dict 반환."""
            _data = None
            _lerr = None
            for attempt in range(self.MAX_RETRIES):
                for endpoint in endpoints_to_try:
                    try:
                        resp = session.post(
                            f"{base_url}{endpoint}",
                            json=payload,
                            timeout=self._timeout,
                        )
                        # v1 404 → v2 시도 (M645_W21 확인됨)
                        if resp.status_code == 404 and endpoint == self.EXPAND_ONE_URL:
                            _lerr = f"v1 HTTP 404 at {base_url} → v2 fallback"
                            logger.info("[ASKCOS] %s, trying %s", _lerr, self.EXPAND_ONE_URL_V2)
                            continue
                        resp.raise_for_status()
                        _data = resp.json()
                        break  # endpoint 성공
                    except requests.exceptions.Timeout:
                        _lerr = (
                            f"timeout at {base_url}{endpoint} "
                            f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                        )
                        logger.warning("[ASKCOS] expand_one %s for: %s", _lerr, smiles[:50])
                        continue
                    except requests.exceptions.ConnectionError:
                        _lerr = (
                            f"ConnectionError at {base_url} "
                            f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                        )
                        logger.warning("[ASKCOS] %s — server unreachable", _lerr)
                        break  # 이 mirror는 연결 불가 — 다음 mirror로
                    except requests.exceptions.HTTPError as e:
                        _lerr = f"HTTP error at {base_url}{endpoint}: {e}"
                        logger.warning("[ASKCOS] %s", _lerr)
                        continue
                    except Exception as e:
                        _lerr = f"Unexpected error at {base_url}{endpoint}: {e}"
                        logger.warning("[ASKCOS] %s", _lerr)
                        continue
                if _data is not None:
                    break  # attempt 루프 탈출
                if attempt < self.MAX_RETRIES - 1:
                    _wait = self.RETRY_BACKOFF * (attempt + 1)
                    logger.info("[ASKCOS] expand_one retry %d/%d (mirror=%s) after %.1fs",
                                attempt + 1, self.MAX_RETRIES, base_url, _wait)
                    time.sleep(_wait)
            return _data  # None or parsed dict

        # [M1355_W184] mirror 순회: 첫 mirror 성공 시 BASE_URL 갱신 후 종료
        # (Rule M: silent failure 금지 — 모든 mirror 소진 후 경고 로그)
        for _mirror in _mirror_list:
            if _mirror in _tried_mirrors:
                continue
            _tried_mirrors.append(_mirror)
            _result = _try_one_mirror(_mirror)
            if _result is not None:
                data = _result
                if _mirror != self.BASE_URL:
                    logger.info(
                        "[ASKCOS] expand_one: failover to mirror %s (primary=%s)",
                        _mirror, self.BASE_URL,
                    )
                    self.BASE_URL = _mirror  # 이후 호출도 동일 mirror 재사용
                last_error = None
                break
            last_error = f"all retries failed on mirror {_mirror}"

        if data is None:
            # Rule M: silent failure 차단 — 마지막 에러 로깅 + 인스턴스 추적
            self._last_error = last_error or "unknown"
            logger.warning("[ASKCOS] expand_one: all mirrors/retries exhausted (last: %s)",
                           self._last_error)
            return []

        # Parse response
        precursors = self._parse_expand_one_response(data, top_k)

        # Cache results
        self._cache[cache_key] = precursors
        return precursors

    def _parse_expand_one_response(self, data: dict, top_k: int) -> List[ASKCOSPrecursor]:
        """Parse the JSON response from expand-one endpoint."""
        results = []

        # ASKCOS response format: {"output": [...]} or {"result": [...]}
        # Handle multiple possible response structures
        raw_results = None
        if isinstance(data, dict):
            raw_results = data.get('output') or data.get('result') or data.get('results')
            # Sometimes nested under 'data'
            if raw_results is None and 'data' in data:
                inner = data['data']
                if isinstance(inner, dict):
                    raw_results = inner.get('output') or inner.get('result')
                elif isinstance(inner, list):
                    raw_results = inner
        elif isinstance(data, list):
            raw_results = data

        if not raw_results or not isinstance(raw_results, list):
            # [M804-B5] Rule M: silent return 금지 — ASKCOS 응답 파싱 실패 로그
            logger.warning(
                "[ASKCOSClient._parse_expand_one_response] 응답에서 결과 목록 추출 실패: "
                "raw_results=%r (type=%s)",
                raw_results,
                type(raw_results).__name__,
            )
            return []

        for i, item in enumerate(raw_results[:top_k]):
            if not isinstance(item, dict):
                continue

            # Extract precursor SMILES
            outcome = (
                item.get('outcome') or
                item.get('smiles') or
                item.get('precursor_smiles') or
                item.get('precursors', '')
            )
            if isinstance(outcome, list):
                outcome = '.'.join(outcome)
            if not outcome:
                continue

            # Extract score
            score = float(
                item.get('score', 0) or
                item.get('plausibility', 0) or
                item.get('prob', 0) or
                0
            )

            # Extract template info
            template = item.get('template', '') or item.get('tforms', '') or ''
            if isinstance(template, list):
                template = template[0] if template else ''

            template_set = item.get('template_set', 'reaxys') or 'reaxys'

            # Number of examples
            num_examples = int(
                item.get('num_examples', 0) or
                item.get('template_count', 0) or
                item.get('count', 0) or
                0
            )

            results.append(ASKCOSPrecursor(
                outcome_smiles=outcome,
                score=score,
                template_smarts=template,
                template_set=template_set,
                num_examples=num_examples,
                rank=i + 1,
            ))

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def tree_search(self, smiles: str, max_depth: int = 5,
                    timeout: int = 60, max_routes: int = 20) -> List[ASKCOSRoute]:
        """Full tree search (multi-step retrosynthesis) via ASKCOS API.

        Uses MCTS (Monte Carlo Tree Search) for planning multi-step routes.
        This is significantly slower than expand_one (~30-60s).

        If the MCTS endpoint is not available, falls back to iterative
        expand_one calls up to max_depth.

        Args:
            smiles: Target molecule SMILES
            max_depth: Maximum synthesis steps
            timeout: Total timeout for tree search (seconds)
            max_routes: Maximum routes to return

        Returns:
            List of ASKCOSRoute objects
        """
        # Check cache
        cache_key = self._cache_key("tree_search", smiles,
                                     max_depth=max_depth, max_routes=max_routes)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not REQUESTS_AVAILABLE:
            return []

        # Try the MCTS endpoint first
        routes = self._try_mcts_endpoint(smiles, max_depth, timeout, max_routes)

        # If MCTS fails or returns nothing, do iterative expand-one
        if not routes:
            routes = self._iterative_expand(smiles, max_depth, max_routes)

        # Cache
        self._cache[cache_key] = routes
        return routes

    def _try_mcts_endpoint(self, smiles: str, max_depth: int,
                           timeout: int, max_routes: int) -> List[ASKCOSRoute]:
        """Try the MCTS tree search endpoint."""
        session = self._get_session()

        payload = {
            "smiles": smiles,
            "max_depth": max_depth,
            "max_branching": 25,
            "expansion_time": min(timeout, 120),
            "retro_backend_options": [
                {
                    "retro_backend": "template_relevance",
                    "retro_model_name": "reaxys",
                    "max_num_templates": 100,
                    "threshold": 0.3,
                    "top_k": 10,
                }
            ],
            "use_fast_filter": True,
            "fast_filter_threshold": 0.75,
            "max_trees": max_routes,
        }

        try:
            resp = session.post(
                f"{self.BASE_URL}{self.TREE_SEARCH_URL}",
                json=payload,
                timeout=timeout + 10,  # Extra buffer for network
            )
            if resp.status_code == 404 or resp.status_code == 405:
                # MCTS endpoint not available
                return []
            resp.raise_for_status()
            data = resp.json()
            return self._parse_tree_search_response(data, smiles)
        except requests.exceptions.Timeout:
            logger.warning("[ASKCOS] tree_search timeout (%ss) for: %s", timeout, smiles[:50])
            return []
        except requests.exceptions.ConnectionError:
            logger.warning("[ASKCOS] tree_search connection error for: %s", smiles[:50])
            return []
        except requests.exceptions.HTTPError:
            logger.warning("[ASKCOS] tree_search HTTP error for: %s", smiles[:50])
            return []
        except Exception as e:
            logger.warning("[ASKCOS] tree_search error: %s", e)
            return []

    def _parse_tree_search_response(self, data: dict,
                                     target_smiles: str) -> List[ASKCOSRoute]:
        """Parse tree search response into ASKCOSRoute objects."""
        routes = []

        # Handle different response formats
        trees = None
        if isinstance(data, dict):
            trees = (data.get('trees') or data.get('output') or
                     data.get('result') or data.get('routes'))
            if trees is None and 'data' in data:
                inner = data['data']
                if isinstance(inner, dict):
                    trees = inner.get('trees') or inner.get('routes')
                elif isinstance(inner, list):
                    trees = inner
        elif isinstance(data, list):
            trees = data

        if not trees or not isinstance(trees, list):
            return []

        for tree in trees:
            if not isinstance(tree, dict):
                continue
            route = self._parse_single_tree(tree, target_smiles)
            if route and route.reactions:
                routes.append(route)

        return routes

    def _parse_single_tree(self, tree: dict,
                           target_smiles: str) -> Optional[ASKCOSRoute]:
        """Parse a single synthesis tree into an ASKCOSRoute."""
        reactions = []
        building_blocks = []

        # DFS through tree to extract linear route
        def _extract_reactions(node: dict, depth: int = 0):
            if depth > 10:  # Safety limit
                return
            if not isinstance(node, dict):
                return

            smiles = node.get('smiles') or node.get('chemical', '')
            children = node.get('children') or node.get('reactions') or []

            if not children:
                # Terminal node = building block
                if smiles:
                    building_blocks.append(smiles)
                return

            for child in children:
                if not isinstance(child, dict):
                    continue

                # This is a reaction node
                precursors_nodes = (child.get('children') or
                                    child.get('precursors') or [])
                precursor_smiles = []

                for p_node in precursors_nodes:
                    if isinstance(p_node, dict):
                        p_smi = p_node.get('smiles') or p_node.get('chemical', '')
                        if p_smi:
                            precursor_smiles.append(p_smi)
                        _extract_reactions(p_node, depth + 1)
                    elif isinstance(p_node, str):
                        precursor_smiles.append(p_node)

                if precursor_smiles:
                    template = child.get('template', '') or child.get('tforms', '') or ''
                    if isinstance(template, list):
                        template = template[0] if template else ''
                    score = float(child.get('score', 0) or child.get('plausibility', 0) or 0.5)

                    reactions.append(ASKCOSReaction(
                        target=smiles,
                        precursors=precursor_smiles,
                        template_smarts=template,
                        score=score,
                        conditions=_infer_conditions(template, 'reaxys'),
                    ))

        _extract_reactions(tree)

        if not reactions:
            return None

        overall_score = sum(r.score for r in reactions) / len(reactions) if reactions else 0

        return ASKCOSRoute(
            target_smiles=target_smiles,
            reactions=reactions,
            total_steps=len(reactions),
            overall_score=overall_score,
            building_blocks=list(set(building_blocks)),
        )

    def _iterative_expand(self, smiles: str, max_depth: int,
                          max_routes: int) -> List[ASKCOSRoute]:
        """Fallback: iterative expand-one calls to build multi-step routes.

        BFS expansion: for each non-buyable precursor, call expand_one again.
        Stop when all precursors are buyable or max_depth reached.
        """
        if not RDKIT_AVAILABLE:
            return []

        routes = []
        # Track explored molecules to avoid cycles
        explored: set = set()
        explored.add(smiles)

        # BFS queue: (current_smiles, reactions_so_far, depth)
        from collections import deque
        queue = deque()

        # Start with first expansion
        first_precursors = self.expand_one(smiles, top_k=5)
        if not first_precursors:
            return []

        for p in first_precursors[:5]:  # Limit branching
            reactants = [s.strip() for s in p.outcome_smiles.split('.') if s.strip()]
            if not reactants:
                continue

            rxn = ASKCOSReaction(
                target=smiles,
                precursors=reactants,
                template_smarts=p.template_smarts,
                score=p.score,
                conditions=_infer_conditions(p.template_smarts, p.template_set),
            )

            # Check if all reactants are buyable
            all_buyable = self._all_buyable(reactants)
            if all_buyable:
                routes.append(ASKCOSRoute(
                    target_smiles=smiles,
                    reactions=[rxn],
                    total_steps=1,
                    overall_score=p.score,
                    building_blocks=reactants,
                ))
            elif max_depth > 1:
                # Need further expansion
                queue.append((reactants, [rxn], 1))

        # BFS expansion of non-buyable precursors
        while queue and len(routes) < max_routes:
            current_reactants, reactions_so_far, depth = queue.popleft()

            if depth >= max_depth:
                continue

            # Find the most complex non-buyable reactant to expand
            for reactant in current_reactants:
                if reactant in explored:
                    continue
                if self._is_buyable(reactant):
                    continue

                explored.add(reactant)

                # Expand this reactant
                sub_precursors = self.expand_one(reactant, top_k=3)
                if not sub_precursors:
                    continue

                for sp in sub_precursors[:3]:
                    sub_reactants = [s.strip() for s in sp.outcome_smiles.split('.')
                                     if s.strip()]
                    if not sub_reactants:
                        continue

                    sub_rxn = ASKCOSReaction(
                        target=reactant,
                        precursors=sub_reactants,
                        template_smarts=sp.template_smarts,
                        score=sp.score,
                        conditions=_infer_conditions(sp.template_smarts, sp.template_set),
                    )

                    new_reactions = reactions_so_far + [sub_rxn]

                    # Replace expanded reactant with its precursors in the check
                    remaining = [r for r in current_reactants if r != reactant] + sub_reactants
                    all_buyable = self._all_buyable(remaining)

                    if all_buyable:
                        all_bbs = [r for r in remaining if self._is_buyable(r)]
                        routes.append(ASKCOSRoute(
                            target_smiles=smiles,
                            reactions=new_reactions,
                            total_steps=len(new_reactions),
                            overall_score=sum(r.score for r in new_reactions) / len(new_reactions),
                            building_blocks=all_bbs,
                        ))
                    elif depth + 1 < max_depth:
                        queue.append((remaining, new_reactions, depth + 1))

                # Only expand one non-buyable per level to limit combinatorial explosion
                break

        return routes[:max_routes]

    @staticmethod
    def _is_buyable(smiles: str) -> bool:
        """Check if a molecule is commercially available (building block)."""
        try:
            from building_blocks import is_building_block, is_commercially_available
            return is_building_block(smiles) or is_commercially_available(smiles)
        except ImportError:
            # Fallback: simple heuristic (small molecules are likely buyable)
            if not RDKIT_AVAILABLE:
                return len(smiles) < 10
            try:
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    return False
                return mol.GetNumHeavyAtoms() <= 6
            except Exception as e:
                logger.warning("[ASKCOSClient] _is_buyable SMILES parse failed: %s", e)
                return False

    @staticmethod
    def _all_buyable(smiles_list: List[str]) -> bool:
        """Check if all molecules in a list are buyable."""
        return all(ASKCOSClient._is_buyable(s) for s in smiles_list)

    def clear_cache(self):
        """Clear the result cache."""
        self._cache.clear()


# ═══════════════════════════════════════════════════════════
# IBM RXN for Chemistry — fallback retrosynthesis engine (M852)
# 학술 인용: Schwaller, P. et al. (2020) Chem. Sci. 11: 3316-3325.
# API 키: RXN4CHEMISTRY_API_KEY env var (Rule I: 소스 코드 하드코딩 금지)
# ═══════════════════════════════════════════════════════════

class IBMRXNClient:
    """IBM RXN for Chemistry REST API client — ASKCOS 실패 시 fallback.

    Schwaller, P. et al. (2020) "Predicting retrosynthetic pathways
    using transformer-based models and a hyper-graph exploration strategy."
    Chem. Sci. 11: 3316-3325.

    Timeout: 30s default. API 키 없으면 graceful skip (Rule M).
    """

    BASE_URL = "https://rxn.res.ibm.com"
    # [MAGIC:30] IBM RXN 기본 타임아웃 — transformer 모델 응답 평균 5-15s, 최대 ~25s
    DEFAULT_TIMEOUT = 30

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self._timeout = timeout
        self._api_key: Optional[str] = None
        self._project_id: Optional[str] = None
        self._session: Optional[object] = None
        self._last_error: Optional[str] = None
        self._cache: Dict[str, list] = {}

    def _load_api_key(self) -> Optional[str]:
        """Load IBM RXN API key from env var (Rule I: no hardcoding)."""
        if self._api_key is not None:
            return self._api_key
        key = os.environ.get("RXN4CHEMISTRY_API_KEY", "").strip()
        if key:
            self._api_key = key
            return key
        self._last_error = "RXN4CHEMISTRY_API_KEY not set"
        logger.info("[IBMRXNClient] %s — IBM RXN fallback inactive", self._last_error)
        return None

    def _get_session(self):
        """Get or create requests Session with auth headers."""
        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests library not available")
        if self._session is None:
            key = self._load_api_key()
            if not key:
                raise RuntimeError("IBM RXN API key not configured")
            self._session = requests.Session()
            self._session.headers.update({
                'Authorization': f'apikey {key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            })
        return self._session

    def is_available(self) -> bool:
        """Check if IBM RXN API is reachable and API key is configured.

        Rule M: 실패 시 logger.warning (silent failure 금지).
        """
        if not REQUESTS_AVAILABLE:
            self._last_error = "requests library not installed"
            return False
        key = self._load_api_key()
        if not key:
            return False
        try:
            session = self._get_session()
            resp = session.get(
                f"{self.BASE_URL}/rxn/api/api-v2/retrosynthesis",
                timeout=10,  # [MAGIC:10] health-check 타임아웃
            )
            # 401 = bad key, but server is reachable
            if resp.status_code < 500:
                self._last_error = None
                return True
            self._last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            self._last_error = "timeout"
        except requests.exceptions.ConnectionError:
            self._last_error = "connection refused"
        except Exception as e:
            self._last_error = f"{type(e).__name__}: {e}"
        logger.warning("[IBMRXNClient] is_available failed: %s", self._last_error)
        return False

    def predict_retrosynthesis(self, smiles: str,
                                max_steps: int = 5) -> List[ASKCOSPrecursor]:
        """Predict retrosynthesis via IBM RXN API.

        Returns ASKCOSPrecursor-compatible objects for seamless integration
        with retrosynthesis_engine.py.

        Args:
            smiles: Target molecule SMILES (canonical)
            max_steps: Maximum retrosynthesis depth

        Returns:
            List of ASKCOSPrecursor (score/outcome_smiles/template_smarts)
        """
        # Cache check
        cache_key = hashlib.md5(f"ibm_rxn:{smiles}:{max_steps}".encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not REQUESTS_AVAILABLE:
            return []

        try:
            session = self._get_session()
        except RuntimeError as e:
            logger.warning("[IBMRXNClient] session init failed: %s", e)
            return []

        # Step 1: Submit retrosynthesis prediction
        payload = {
            "smiles": smiles,
            "availability_pricing_threshold": 10,
            "max_steps": max_steps,
            "ai_model": "12class-tokens-2021-05-14",
        }

        prediction_id = None
        try:
            resp = session.post(
                f"{self.BASE_URL}/rxn/api/api-v2/retrosynthesis/predict",
                json=payload,
                timeout=self._timeout,
            )
            if resp.status_code == 401:
                self._last_error = "Invalid API key (HTTP 401)"
                logger.warning("[IBMRXNClient] %s", self._last_error)
                return []
            resp.raise_for_status()
            data = resp.json()
            # Rule N: isinstance check
            if isinstance(data, dict):
                prediction_id = data.get("prediction_id") or data.get("id")
            if not prediction_id:
                self._last_error = "No prediction_id in response"
                logger.warning("[IBMRXNClient] %s: %s", self._last_error,
                               str(data)[:200])
                return []
        except requests.exceptions.Timeout:
            self._last_error = f"predict timeout ({self._timeout}s)"
            logger.warning("[IBMRXNClient] %s for: %s", self._last_error, smiles[:50])
            return []
        except Exception as e:
            self._last_error = f"predict error: {e}"
            logger.warning("[IBMRXNClient] %s", self._last_error)
            return []

        # Step 2: Poll for results (max 30s total)
        results = self._poll_prediction(session, prediction_id, smiles)
        if results:
            self._cache[cache_key] = results
        return results

    def _poll_prediction(self, session, prediction_id: str,
                          target_smiles: str) -> List[ASKCOSPrecursor]:
        """Poll IBM RXN for prediction results until complete or timeout.

        [MAGIC:2] 폴링 간격 2초 — IBM RXN 평균 응답 5-15s.
        [MAGIC:15] 최대 폴링 횟수 — 2s × 15 = 30s 최대 대기.
        """
        poll_url = f"{self.BASE_URL}/rxn/api/api-v2/retrosynthesis/predict/{prediction_id}"
        max_polls = 15  # [MAGIC:15] 최대 폴링 횟수
        poll_interval = 2  # [MAGIC:2] 폴링 간격 (초)

        for i in range(max_polls):
            time.sleep(poll_interval)
            try:
                resp = session.get(poll_url, timeout=10)
                if resp.status_code == 404:
                    continue  # 아직 처리 중
                resp.raise_for_status()
                data = resp.json()

                if not isinstance(data, dict):
                    continue

                status = data.get("status", "")
                if status == "PROCESSING":
                    continue
                if status in ("DONE", "SUCCESS", ""):
                    return self._parse_rxn_results(data, target_smiles)
                if status in ("FAILED", "ERROR"):
                    self._last_error = f"prediction failed: {data.get('error', 'unknown')}"
                    logger.warning("[IBMRXNClient] %s", self._last_error)
                    return []
            except requests.exceptions.Timeout:
                logger.warning("[IBMRXNClient] poll timeout (attempt %d/%d)",
                               i + 1, max_polls)
                continue
            except Exception as e:
                logger.warning("[IBMRXNClient] poll error: %s", e)
                continue

        self._last_error = "polling timeout exceeded"
        logger.warning("[IBMRXNClient] %s for prediction %s", self._last_error, prediction_id)
        return []

    def _parse_rxn_results(self, data: dict,
                            target_smiles: str) -> List[ASKCOSPrecursor]:
        """Parse IBM RXN response into ASKCOSPrecursor-compatible objects."""
        results = []

        # IBM RXN response structure: retrosynthetic_paths → []
        paths = data.get("retrosynthetic_paths") or data.get("output") or []
        if isinstance(data.get("payload"), dict):
            paths = data["payload"].get("retrosynthetic_paths", paths)

        if not isinstance(paths, list):
            return []

        for rank, path in enumerate(paths[:10]):  # [MAGIC:10] 최대 10경로
            if not isinstance(path, dict):
                continue

            # Extract first-step precursors
            reactions = path.get("reactions") or path.get("children") or []
            if not isinstance(reactions, list) or not reactions:
                continue

            first_rxn = reactions[0] if isinstance(reactions[0], dict) else {}
            precursor_smiles_list = first_rxn.get("precursors") or []
            if isinstance(precursor_smiles_list, str):
                precursor_smiles_list = [precursor_smiles_list]

            # Rule N: validate each precursor is a string
            valid_precursors = [
                p for p in precursor_smiles_list
                if isinstance(p, str) and p.strip()
            ]
            if not valid_precursors:
                continue

            outcome = ".".join(valid_precursors)
            confidence = float(first_rxn.get("confidence", 0.5)
                               if isinstance(first_rxn.get("confidence"), (int, float))
                               else 0.5)

            results.append(ASKCOSPrecursor(
                outcome_smiles=outcome,
                score=confidence,
                template_smarts="",  # IBM RXN은 transformer 기반 — SMARTS 미제공
                template_set="ibm_rxn",
                num_examples=0,  # IBM RXN은 문헌 예제 수 미제공
                rank=rank + 1,
            ))

        return results


# ═══════════════════════════════════════════════════════════
# Module-level convenience (for testing)
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    # Quick test: expand aspirin
    client = ASKCOSClient()
    print(f"ASKCOS available: {client.is_available()}")

    test_smiles = "CC(=O)Oc1ccccc1C(=O)O"  # Aspirin
    print(f"\nExpanding: {test_smiles} (Aspirin)")
    results = client.expand_one(test_smiles, top_k=5)
    for i, r in enumerate(results):
        print(f"  {i+1}. Score={r.score:.3f} | Precursors: {r.outcome_smiles}")
        print(f"     Template: {r.template_smarts[:80] if r.template_smarts else 'N/A'}")
        print(f"     Examples: {r.num_examples}")
