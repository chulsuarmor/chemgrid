#!/usr/bin/env python3
"""
intermediate_generator.py — RWMol 기반 반응 중간체 SMILES 생성 엔진
====================================================================
기존 메커니즘 엔진(mechanism_engine.py)이 하드코딩된 gold-standard SMILES에
의존하거나 문자열 치환으로 가짜 중간체를 만들었던 문제를 해결한다.

이 모듈은 RDKit RWMol 원자/결합 조작 API를 사용하여 각 반응 유형별로
화학적으로 정확한 중간체 SMILES를 생성한다.

지원 반응 유형:
  1. 카보닐 친핵첨가 (Wolff-Kishner, 알돌, Grignard, Fischer)
  2. 제거 반응 (E1cb, E2, 탈수)
  3. 1,2-자리옮김 (Beckmann, Curtius, Hofmann)
  4. 라디칼 연쇄 (NBS 등)
  5. 고리닫기/페리고리 (Diels-Alder — 협동, 중간체 없음)

핵심 RWMol 연산:
  bond.SetBondType(), atom.SetFormalCharge(), atom.SetNumRadicalElectrons(),
  rwmol.AddAtom(), rwmol.AddBond(), rwmol.RemoveAtom(), rwmol.RemoveBond(),
  Chem.SanitizeMol(), Chem.MolToSmiles()
"""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ============================================================
# RDKit guard
# ============================================================
RDKIT_AVAILABLE = False
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdFMCS
    RDKIT_AVAILABLE = True
except ImportError:
    logger.warning("RDKit not available — IntermediateGenerator disabled")


# ============================================================
# Data structures
# ============================================================

@dataclass
class IntermediateInfo:
    """단일 중간체/전이상태 정보."""
    smiles: str                                        # RDKit-valid SMILES
    label: str                                         # 한글 단계명: "사면체 중간체", "히드라존"
    annotation: str                                    # 영문 짧은 설명
    is_intermediate: bool = True                       # True = 안정 중간체
    is_transition_state: bool = False                  # True = 전이상태 (‡)
    charges: List[Tuple[int, int]] = field(default_factory=list)   # [(atom_idx, charge)]
    radicals: List[Tuple[int, int]] = field(default_factory=list)  # [(atom_idx, n_electrons)]


# ============================================================
# Utility: safe SMILES from RWMol
# ============================================================

def _safe_smiles(rwmol) -> Optional[str]:
    """RWMol → canonical SMILES (sanitize 포함). 실패시 None."""
    # N코드: 타입 가드 — rwmol이 None이면 조기 반환
    if rwmol is None:
        logger.warning("_safe_smiles: rwmol is None")
        return None
    try:
        mol = rwmol.GetMol() if hasattr(rwmol, 'GetMol') else rwmol
        Chem.SanitizeMol(mol)
        smi = Chem.MolToSmiles(mol)
        # 역검증: 생성된 SMILES를 다시 파싱
        if Chem.MolFromSmiles(smi) is None:
            logger.warning("_safe_smiles: round-trip validation failed for SMILES: %s", smi)
            return None
        return smi
    except Exception as exc:
        logger.debug("_safe_smiles failed: %s", exc)
        return None


def _safe_smiles_no_sanitize(rwmol) -> Optional[str]:
    """Sanitize 없이 SMILES 생성 (전하/라디칼이 비정상인 TS 표현용)."""
    # N코드: 타입 가드
    if rwmol is None:
        logger.warning("_safe_smiles_no_sanitize: rwmol is None")
        return None
    try:
        mol = rwmol.GetMol() if hasattr(rwmol, 'GetMol') else rwmol
        smi = Chem.MolToSmiles(mol)
        return smi
    except Exception as e:
        logger.warning("_safe_smiles_no_sanitize failed: %s", e)
        return None


def _find_carbonyl_carbon(mol) -> Optional[int]:
    """분자에서 C=O 카보닐 탄소 인덱스를 찾는다.
    케톤/알데히드/카복실 등 모든 C=O에서 첫 번째를 반환."""
    # N코드: 타입 가드
    if mol is None:
        logger.warning("_find_carbonyl_carbon: mol is None")
        return None
    for bond in mol.GetBonds():
        a1 = bond.GetBeginAtom()
        a2 = bond.GetEndAtom()
        if bond.GetBondTypeAsDouble() == 2.0:
            if a1.GetAtomicNum() == 6 and a2.GetAtomicNum() == 8:
                return a1.GetIdx()
            if a1.GetAtomicNum() == 8 and a2.GetAtomicNum() == 6:
                return a2.GetIdx()
    return None


def _find_atom_by_symbol(mol, symbol: str, start_idx: int = 0) -> Optional[int]:
    """주어진 원소 기호의 원자 인덱스를 찾는다."""
    # N코드: 타입 가드
    if mol is None:
        logger.warning("_find_atom_by_symbol: mol is None")
        return None
    if not isinstance(symbol, str):
        logger.warning("_find_atom_by_symbol: symbol 타입 불일치 (expected str, got %s)",
                       type(symbol).__name__)
        return None
    for atom in mol.GetAtoms():
        if atom.GetSymbol() == symbol and atom.GetIdx() >= start_idx:
            return atom.GetIdx()
    return None


def _find_co_bond(mol, c_idx: int) -> Optional[int]:
    """c_idx 탄소에 이중결합된 산소의 인덱스를 찾는다."""
    # N코드: 타입 가드
    if mol is None:
        logger.warning("_find_co_bond: mol is None")
        return None
    if not isinstance(c_idx, int):
        logger.warning("_find_co_bond: c_idx 타입 불일치 (expected int, got %s)",
                       type(c_idx).__name__)
        return None
    try:
        c_atom = mol.GetAtomWithIdx(c_idx)
    except Exception as e:
        logger.warning("_find_co_bond: GetAtomWithIdx(%d) failed: %s", c_idx, e)
        return None
    for bond in c_atom.GetBonds():
        other = bond.GetOtherAtom(c_atom)
        if other.GetAtomicNum() == 8 and bond.GetBondTypeAsDouble() == 2.0:
            return other.GetIdx()
    return None


# ============================================================
# Reaction-specific intermediate generators
# ============================================================

def _carbonyl_nucleophilic_addition(
    reactant_mol,
    nucleophile_smi: str,
    nuc_attach_symbol: str = "N",
) -> List[IntermediateInfo]:
    """카보닐 친핵첨가: Nu 가 C=O 공격 → 사면체 중간체 C(O⁻)(Nu)(R)(R').

    Parameters
    ----------
    reactant_mol : Chem.Mol
        카보닐 기를 포함하는 반응물
    nucleophile_smi : str
        친핵체 SMILES (예: "NN" for hydrazine, "[OH-]", "CC([O-])C")
    nuc_attach_symbol : str
        친핵체에서 카보닐 탄소를 공격하는 원자 원소 기호 (기본 "N")

    Returns
    -------
    list[IntermediateInfo]
        사면체 중간체 정보
    """
    if not RDKIT_AVAILABLE:
        logger.warning("_carbonyl_nucleophilic_addition: RDKit not available")
        return []

    # N코드: 타입 가드
    if reactant_mol is None:
        logger.warning("_carbonyl_nucleophilic_addition: reactant_mol is None")
        return []
    if not isinstance(nucleophile_smi, str) or not nucleophile_smi.strip():
        logger.warning("_carbonyl_nucleophilic_addition: nucleophile_smi 타입/값 불일치 (type=%s)",
                       type(nucleophile_smi).__name__)
        return []
    if not isinstance(nuc_attach_symbol, str):
        logger.warning("_carbonyl_nucleophilic_addition: nuc_attach_symbol 타입 불일치 (type=%s)",
                       type(nuc_attach_symbol).__name__)
        nuc_attach_symbol = "N"

    c_idx = _find_carbonyl_carbon(reactant_mol)
    if c_idx is None:
        logger.warning("No carbonyl found in reactant")
        return []

    o_idx = _find_co_bond(reactant_mol, c_idx)
    if o_idx is None:
        logger.warning("_carbonyl_nucleophilic_addition: no C=O double bond found at c_idx=%d", c_idx)
        return []

    nuc_mol = Chem.MolFromSmiles(nucleophile_smi)
    if nuc_mol is None:
        logger.warning("Invalid nucleophile SMILES: %s", nucleophile_smi)
        return []

    # ------ RWMol 조작으로 사면체 중간체 생성 ------
    # CombineMols로 반응물 + 친핵체를 하나의 분자 객체에 합침
    combined = Chem.CombineMols(reactant_mol, nuc_mol)
    rw = Chem.RWMol(combined)

    # 반응물 원자 수 (오프셋)
    n_reactant = reactant_mol.GetNumAtoms()

    # 1) C=O 이중결합 → 단일결합으로 변경
    bond = rw.GetBondBetweenAtoms(c_idx, o_idx)
    if bond is not None:
        bond.SetBondType(Chem.BondType.SINGLE)

    # 2) 산소에 음전하 부여 (C-O⁻)
    rw.GetAtomWithIdx(o_idx).SetFormalCharge(-1)

    # 3) 친핵체의 공격 원자 찾기 (합친 분자에서 오프셋 적용)
    nuc_attach_idx = None
    for i in range(n_reactant, rw.GetNumAtoms()):
        atom = rw.GetAtomWithIdx(i)
        if atom.GetSymbol() == nuc_attach_symbol:
            nuc_attach_idx = i
            break

    if nuc_attach_idx is None:
        # 친핵체에서 가장 전기음성도가 높은 비탄소 원자
        for i in range(n_reactant, rw.GetNumAtoms()):
            atom = rw.GetAtomWithIdx(i)
            if atom.GetAtomicNum() != 6 and atom.GetAtomicNum() != 1:
                nuc_attach_idx = i
                break

    if nuc_attach_idx is None:
        logger.warning("No nucleophilic atom found in %s", nucleophile_smi)
        return []

    # 4) C—Nu 결합 생성
    rw.AddBond(c_idx, nuc_attach_idx, Chem.BondType.SINGLE)

    # 5) 친핵체에 양성자가 있으면 형식전하 불필요, 없으면 양전하
    #    (히드라진 NH2NH2 같은 중성 친핵체는 N에 양전하)
    nuc_atom = rw.GetAtomWithIdx(nuc_attach_idx)
    # 원래 친핵체가 음전하를 가졌으면 중성으로
    if nuc_atom.GetFormalCharge() < 0:
        nuc_atom.SetFormalCharge(nuc_atom.GetFormalCharge() + 1)
    else:
        # 중성 친핵체(NH2NH2)가 새 결합을 만들면 양전하
        nuc_atom.SetFormalCharge(1)

    smi = _safe_smiles(rw)
    if smi is None:
        # sanitize 실패 시 전하 조정 시도
        nuc_atom.SetFormalCharge(0)
        rw.GetAtomWithIdx(o_idx).SetFormalCharge(0)
        smi = _safe_smiles(rw)

    if smi is None:
        logger.warning("Failed to generate tetrahedral intermediate SMILES")
        return []

    return [IntermediateInfo(
        smiles=smi,
        label="사면체 중간체",
        annotation="Tetrahedral intermediate: Nu attacked C=O",
        is_intermediate=True,
        charges=[(o_idx, -1)],
    )]


def _water_elimination(mol, c_idx: int, oh_idx: int) -> List[IntermediateInfo]:
    """탈수: C-OH → C=Nu + H2O (히드라존/이민 형성).

    mol에서 C-OH 단일결합을 끊고 C에 인접한 N과 이중결합을 형성한다.
    """
    if not RDKIT_AVAILABLE:
        logger.warning("_water_elimination: RDKit not available")
        return []

    # N코드: 타입 가드
    if mol is None:
        logger.warning("_water_elimination: mol is None")
        return []
    if not isinstance(c_idx, int) or not isinstance(oh_idx, int):
        logger.warning("_water_elimination: c_idx/oh_idx 타입 불일치 (c_idx=%s, oh_idx=%s)",
                       type(c_idx).__name__, type(oh_idx).__name__)
        return []

    rw = Chem.RWMol(mol)
    c_atom = rw.GetAtomWithIdx(c_idx)

    # OH 산소를 제거하기 전에 C에 연결된 N을 찾는다
    n_idx = None
    for neighbor in c_atom.GetNeighbors():
        if neighbor.GetAtomicNum() == 7:  # Nitrogen
            n_idx = neighbor.GetIdx()
            break

    if n_idx is None:
        logger.warning("_water_elimination: no nitrogen neighbor found for carbon at c_idx=%d", c_idx)
        return []

    # OH 제거 (C-O 결합 끊기 + O 원자 제거)
    rw.RemoveBond(c_idx, oh_idx)

    # C-N 결합을 이중결합으로 승격
    cn_bond = rw.GetBondBetweenAtoms(c_idx, n_idx)
    if cn_bond is not None:
        cn_bond.SetBondType(Chem.BondType.DOUBLE)

    # N의 양전하 제거 (이중결합 형성으로 자연스럽게 중성)
    n_atom = rw.GetAtomWithIdx(n_idx)
    n_atom.SetFormalCharge(0)

    # OH 산소 원자와 연결된 H 제거 — 물 분자로 분리
    # (산소 원자를 남겨두면 fragment가 됨)
    # RemoveAtom은 인덱스를 재배열하므로 주의
    # 대신 fragment로 남겨두고 SMILES에서 물을 분리
    o_atom = rw.GetAtomWithIdx(oh_idx)
    o_atom.SetFormalCharge(0)

    smi = _safe_smiles(rw)
    if smi is None:
        logger.warning("_water_elimination: failed to generate dehydration product SMILES")
        return []

    # SMILES에서 물(.O) 부분을 분리하여 주 생성물만 추출
    parts = smi.split('.')
    main_parts = [p for p in parts if p not in ('O', '[OH2]', '[H]O[H]')]
    if not main_parts:
        main_parts = parts

    return [IntermediateInfo(
        smiles='.'.join(main_parts),
        label="탈수 생성물",
        annotation="Dehydration product (water eliminated)",
        is_intermediate=True,
    )]


# ============================================================
# Wolff-Kishner 전체 경로
# ============================================================

def _wolff_kishner_intermediates(
    reactant_smi: str,
    product_smi: str,
) -> List[IntermediateInfo]:
    """Wolff-Kishner 환원: R2C=O + NH2NH2 → R2CH2.

    실제 메커니즘:
    1. 친핵첨가: NH2NH2 → 사면체 중간체 R2C(OH)(NHNH2)
    2. 탈수: → 히드라존 R2C=NNH2
    3. 염기 탈양성자: → R2C=NNH⁻ (음이온)
    4. 양성자 자리옮김: → R2CH-N=NH (탄소에 H 이동)
    5. N2 이탈: → R2CH⁻ + N2↑ (카보음이온)
    6. 양성자화: → R2CH2 (생성물)
    """
    if not RDKIT_AVAILABLE:
        logger.warning("_wolff_kishner_intermediates: RDKit not available")
        return []

    # N코드: 타입 가드
    if not isinstance(reactant_smi, str) or not reactant_smi.strip():
        logger.warning("_wolff_kishner_intermediates: reactant_smi 타입/값 불일치 (type=%s)",
                       type(reactant_smi).__name__)
        return []
    if not isinstance(product_smi, str) or not product_smi.strip():
        logger.warning("_wolff_kishner_intermediates: product_smi 타입/값 불일치 (type=%s)",
                       type(product_smi).__name__)
        return []

    reactant_mol = Chem.MolFromSmiles(reactant_smi)
    product_mol = Chem.MolFromSmiles(product_smi)
    if reactant_mol is None or product_mol is None:
        logger.warning("_wolff_kishner_intermediates: 잘못된 SMILES — reactant=%s, product=%s",
                       reactant_smi, product_smi)
        return []

    intermediates: List[IntermediateInfo] = []

    # 반응물 추가
    intermediates.append(IntermediateInfo(
        smiles=reactant_smi,
        label="반응물",
        annotation="Starting material (ketone/aldehyde)",
        is_intermediate=False,
    ))

    # ---- Step 1: 친핵첨가 (사면체 중간체) ----
    tet = _carbonyl_nucleophilic_addition(
        reactant_mol, "NN", nuc_attach_symbol="N"
    )
    if tet:
        intermediates.extend(tet)

    # ---- Step 2: 히드라존 (탈수 생성물) ----
    # RWMol로 직접 구축: 카보닐 C=O → C=N-NH2, -H2O
    c_idx = _find_carbonyl_carbon(reactant_mol)
    if c_idx is not None:
        # 히드라존 직접 생성: C=O를 C=NNC로 대체
        rw = Chem.RWMol(reactant_mol)
        o_idx = _find_co_bond(reactant_mol, c_idx)
        if o_idx is not None:
            # O를 N으로 변경
            rw.GetAtomWithIdx(o_idx).SetAtomicNum(7)  # O → N
            # N-NH2 추가: 새 N 원자 추가
            new_n = rw.AddAtom(Chem.Atom(7))  # 7 = N
            rw.AddBond(o_idx, new_n, Chem.BondType.SINGLE)
            # 명시적 수소 설정 불필요 — sanitize가 처리

            hydrazone_smi = _safe_smiles(rw)
            if hydrazone_smi:
                intermediates.append(IntermediateInfo(
                    smiles=hydrazone_smi,
                    label="히드라존",
                    annotation="Hydrazone (C=N-NH2, water eliminated)",
                    is_intermediate=True,
                ))

    # ---- Step 3: 염기 탈양성자 → 히드라존 음이온 ----
    if c_idx is not None and o_idx is not None:
        rw2 = Chem.RWMol(reactant_mol)
        rw2.GetAtomWithIdx(o_idx).SetAtomicNum(7)
        new_n2 = rw2.AddAtom(Chem.Atom(7))
        rw2.AddBond(o_idx, new_n2, Chem.BondType.SINGLE)
        # 말단 NH⁻: 음전하
        rw2.GetAtomWithIdx(new_n2).SetFormalCharge(-1)

        anion_smi = _safe_smiles(rw2)
        if anion_smi:
            intermediates.append(IntermediateInfo(
                smiles=anion_smi,
                label="히드라존 음이온",
                annotation="Hydrazone anion (C=N-NH(-), base deprotonation)",
                is_intermediate=True,
                charges=[(new_n2, -1)],
            ))

    # ---- Step 4: 양성자 자리옮김 → 디아제닐 중간체 ----
    # R₂CH-N=NH: C-N 단일결합, N=N 이중결합
    if c_idx is not None and o_idx is not None:
        rw3 = Chem.RWMol(reactant_mol)
        # C=O의 O를 N으로 변경
        rw3.GetAtomWithIdx(o_idx).SetAtomicNum(7)
        # C=N → C-N (단일결합화)
        bond_cn = rw3.GetBondBetweenAtoms(c_idx, o_idx)
        if bond_cn is not None:
            bond_cn.SetBondType(Chem.BondType.SINGLE)
        # N-NH 추가
        new_n3 = rw3.AddAtom(Chem.Atom(7))
        rw3.AddBond(o_idx, new_n3, Chem.BondType.DOUBLE)

        diazenyl_smi = _safe_smiles(rw3)
        if diazenyl_smi:
            intermediates.append(IntermediateInfo(
                smiles=diazenyl_smi,
                label="디아제닐 중간체",
                annotation="Diazenyl intermediate (R2CH-N=NH, proton tautomerism)",
                is_intermediate=True,
            ))

    # ---- Step 5: N2 이탈 → 카보음이온 ----
    # R₂CH⁻ (카보음이온): C에서 N을 떼고 C에 음전하
    if c_idx is not None:
        rw4 = Chem.RWMol(reactant_mol)
        o_idx_4 = _find_co_bond(reactant_mol, c_idx)
        if o_idx_4 is not None:
            # O 원자 제거
            rw4.RemoveAtom(o_idx_4)
            # c_idx가 o_idx_4보다 클 수 있으므로 재매핑
            new_c_idx = c_idx if c_idx < o_idx_4 else c_idx - 1
            rw4.GetAtomWithIdx(new_c_idx).SetFormalCharge(-1)

            carbanion_smi = _safe_smiles(rw4)
            if carbanion_smi:
                intermediates.append(IntermediateInfo(
                    smiles=carbanion_smi,
                    label="카보음이온",
                    annotation="Carbanion (R2CH(-), after N2 loss)",
                    is_intermediate=True,
                    charges=[(new_c_idx, -1)],
                ))

    # ---- Step 6: 생성물 ----
    intermediates.append(IntermediateInfo(
        smiles=product_smi,
        label="생성물",
        annotation="Final product (protonation of carbanion)",
        is_intermediate=False,
    ))

    return intermediates


# ============================================================
# Aldol reaction intermediates
# ============================================================

def _aldol_intermediates(
    reactant_smi: str,
    product_smi: str,
) -> List[IntermediateInfo]:
    """알돌 반응: R-CH2-C(=O)-R' + Base → β-하이드록시 카보닐 → 알돌.

    메커니즘:
    1. 에놀화 (α-탈양성자 → 에놀레이트)
    2. 친핵첨가 (에놀레이트가 다른 카보닐 공격 → 알돌레이트)
    3. 양성자화 → β-하이드록시 카보닐 (알돌)
    4. (선택) 탈수 → α,β-불포화 카보닐
    """
    if not RDKIT_AVAILABLE:
        logger.warning("_aldol_intermediates: RDKit not available")
        return []

    # N코드: 타입 가드
    if not isinstance(reactant_smi, str) or not reactant_smi.strip():
        logger.warning("_aldol_intermediates: reactant_smi 타입/값 불일치 (type=%s)",
                       type(reactant_smi).__name__)
        return []
    if not isinstance(product_smi, str) or not product_smi.strip():
        logger.warning("_aldol_intermediates: product_smi 타입/값 불일치 (type=%s)",
                       type(product_smi).__name__)
        return []

    mol = Chem.MolFromSmiles(reactant_smi)
    if mol is None:
        logger.warning("_aldol_intermediates: 잘못된 reactant SMILES: %s", reactant_smi)
        return []

    intermediates: List[IntermediateInfo] = []

    # 반응물
    intermediates.append(IntermediateInfo(
        smiles=reactant_smi,
        label="반응물",
        annotation="Starting material",
        is_intermediate=False,
    ))

    # ---- Step 1: 에놀레이트 생성 ----
    # α-탄소에서 H 제거 → 카보음이온 → 에놀레이트 (C=C-[O⁻])
    c_idx = _find_carbonyl_carbon(mol)
    if c_idx is not None:
        c_atom = mol.GetAtomWithIdx(c_idx)
        # α-탄소 찾기: C=O의 C에 인접한 탄소 중 H를 가진 것
        alpha_idx = None
        for neighbor in c_atom.GetNeighbors():
            if (neighbor.GetAtomicNum() == 6  # carbon
                    and neighbor.GetTotalNumHs() > 0):  # has H
                alpha_idx = neighbor.GetIdx()
                break

        if alpha_idx is not None:
            # RWMol 조작: C=O → C-[O⁻], C-C(α) → C=C(α) (에놀레이트 공명)
            rw = Chem.RWMol(mol)
            o_idx = _find_co_bond(mol, c_idx)
            if o_idx is not None:
                # C=O → C-O⁻
                bond_co = rw.GetBondBetweenAtoms(c_idx, o_idx)
                if bond_co:
                    bond_co.SetBondType(Chem.BondType.SINGLE)
                rw.GetAtomWithIdx(o_idx).SetFormalCharge(-1)

                # C-Cα → C=Cα (에놀레이트 이중결합)
                bond_cc = rw.GetBondBetweenAtoms(c_idx, alpha_idx)
                if bond_cc:
                    bond_cc.SetBondType(Chem.BondType.DOUBLE)

                enolate_smi = _safe_smiles(rw)
                if enolate_smi:
                    intermediates.append(IntermediateInfo(
                        smiles=enolate_smi,
                        label="에놀레이트",
                        annotation="Enolate anion (alpha-deprotonation)",
                        is_intermediate=True,
                        charges=[(o_idx, -1)],
                    ))

    # ---- Step 2: 알돌 축합 생성물 (β-히드록시 카보닐) ----
    # 두 분자의 축합은 복잡하므로, 생성물에서 역추적으로
    # β-히드록시 카보닐 중간체를 생성한다
    product_mol = Chem.MolFromSmiles(product_smi)
    if product_mol is not None:
        # 생성물이 α,β-불포화 카보닐이면 그 전 단계인 β-하이드록시 체를 생성
        # 생성물의 C=C-C=O 패턴에서 C=C → C(OH)-C로 변환
        patt = Chem.MolFromSmarts("[C:1]=[C:2][C:3]=[O:4]")
        if product_mol.HasSubstructMatch(patt):
            match = product_mol.GetSubstructMatch(patt)
            rw_p = Chem.RWMol(product_mol)
            # C=C → C-C
            bond_cc = rw_p.GetBondBetweenAtoms(match[0], match[1])
            if bond_cc:
                bond_cc.SetBondType(Chem.BondType.SINGLE)
            # match[0]에 OH 추가
            oh_o = rw_p.AddAtom(Chem.Atom(8))  # 8 = O
            rw_p.AddBond(match[0], oh_o, Chem.BondType.SINGLE)

            aldol_smi = _safe_smiles(rw_p)
            if aldol_smi:
                intermediates.append(IntermediateInfo(
                    smiles=aldol_smi,
                    label="알돌 (β-히드록시 카보닐)",
                    annotation="Aldol product (beta-hydroxy carbonyl)",
                    is_intermediate=True,
                ))

    # 생성물
    intermediates.append(IntermediateInfo(
        smiles=product_smi,
        label="생성물",
        annotation="Product (aldol condensation / dehydration)",
        is_intermediate=False,
    ))

    return intermediates


# ============================================================
# Fischer esterification intermediates
# ============================================================

def _fischer_esterification_intermediates(
    acid_smi: str,
    alcohol_smi: str,
    product_smi: str,
) -> List[IntermediateInfo]:
    """Fischer 에스터화: R-COOH + R'OH ⇌ R-COOR' + H2O (산 촉매).

    메커니즘:
    1. 카보닐 산소 양성자화 → [R-C(=OH⁺)-OH]
    2. 알코올 친핵첨가 → 사면체 중간체 [R-C(OH)₂(OR')]
    3. 양성자 이동 + 물 이탈 → 에스터
    """
    if not RDKIT_AVAILABLE:
        logger.warning("_fischer_esterification_intermediates: RDKit not available")
        return []

    # N코드: 타입 가드
    if not isinstance(acid_smi, str) or not acid_smi.strip():
        logger.warning("_fischer_esterification_intermediates: acid_smi 타입/값 불일치 (type=%s)",
                       type(acid_smi).__name__)
        return []
    if not isinstance(alcohol_smi, str) or not alcohol_smi.strip():
        logger.warning("_fischer_esterification_intermediates: alcohol_smi 타입/값 불일치 (type=%s)",
                       type(alcohol_smi).__name__)
        return []
    if not isinstance(product_smi, str) or not product_smi.strip():
        logger.warning("_fischer_esterification_intermediates: product_smi 타입/값 불일치 (type=%s)",
                       type(product_smi).__name__)
        return []

    acid_mol = Chem.MolFromSmiles(acid_smi)
    alc_mol = Chem.MolFromSmiles(alcohol_smi)
    if acid_mol is None or alc_mol is None:
        logger.warning("_fischer_esterification_intermediates: 잘못된 SMILES — acid=%s, alcohol=%s",
                       acid_smi, alcohol_smi)
        return []

    intermediates: List[IntermediateInfo] = []

    # 반응물
    intermediates.append(IntermediateInfo(
        smiles=f"{acid_smi}.{alcohol_smi}",
        label="반응물",
        annotation="Carboxylic acid + alcohol",
        is_intermediate=False,
    ))

    # ---- Step 1: 카보닐 양성자화 ----
    c_idx = _find_carbonyl_carbon(acid_mol)
    if c_idx is not None:
        o_idx = _find_co_bond(acid_mol, c_idx)
        if o_idx is not None:
            rw = Chem.RWMol(acid_mol)
            # C=O의 O에 양전하 (양성자화)
            rw.GetAtomWithIdx(o_idx).SetFormalCharge(1)

            prot_smi = _safe_smiles(rw)
            if prot_smi:
                intermediates.append(IntermediateInfo(
                    smiles=prot_smi,
                    label="카보닐 양성자화",
                    annotation="Protonated carbonyl [C=OH+]",
                    is_intermediate=True,
                    charges=[(o_idx, 1)],
                ))

    # ---- Step 2: 사면체 중간체 ----
    if c_idx is not None:
        tet = _carbonyl_nucleophilic_addition(
            acid_mol, alcohol_smi, nuc_attach_symbol="O"
        )
        if tet:
            intermediates.extend(tet)

    # ---- Step 3: 생성물 ----
    intermediates.append(IntermediateInfo(
        smiles=product_smi,
        label="에스터 생성물",
        annotation="Ester product + H2O",
        is_intermediate=False,
    ))

    return intermediates


# ============================================================
# E2 elimination intermediates
# ============================================================

def _e2_elimination_intermediates(
    reactant_smi: str,
    product_smi: str,
) -> List[IntermediateInfo]:
    """E2 제거: 동시 결합 끊김/형성 — 협동 반응이므로 진짜 중간체 없음.
    전이상태만 표현 (‡).
    """
    if not RDKIT_AVAILABLE:
        logger.warning("_e2_elimination_intermediates: RDKit not available")
        return []

    # N코드: 타입 가드
    if not isinstance(reactant_smi, str) or not reactant_smi.strip():
        logger.warning("_e2_elimination_intermediates: reactant_smi 타입/값 불일치 (type=%s)",
                       type(reactant_smi).__name__)
        return []
    if not isinstance(product_smi, str) or not product_smi.strip():
        logger.warning("_e2_elimination_intermediates: product_smi 타입/값 불일치 (type=%s)",
                       type(product_smi).__name__)
        return []

    intermediates = []

    intermediates.append(IntermediateInfo(
        smiles=reactant_smi,
        label="반응물",
        annotation="Starting material with leaving group",
        is_intermediate=False,
    ))

    # E2는 concerted → 전이상태만 (점선 결합)
    intermediates.append(IntermediateInfo(
        smiles=reactant_smi,  # TS는 정확한 SMILES로 표현 불가, 반응물 참고용
        label="전이상태 [‡]",
        annotation="E2 transition state (concerted, anti-periplanar)",
        is_intermediate=False,
        is_transition_state=True,
    ))

    intermediates.append(IntermediateInfo(
        smiles=product_smi,
        label="생성물",
        annotation="Alkene product + leaving group + HBase",
        is_intermediate=False,
    ))

    return intermediates


# ============================================================
# Radical chain (NBS allylic/benzylic bromination)
# ============================================================

def _radical_intermediates(
    reactant_smi: str,
    product_smi: str,
) -> List[IntermediateInfo]:
    """라디칼 연쇄 반응: 개시 → 전파 → 종결.

    NBS 벤질/알릴 브롬화 기준:
    1. 개시: Br2 → 2 Br· (광분해)
    2. 전파1: R-H + Br· → R· + HBr
    3. 전파2: R· + Br2 → R-Br + Br·
    """
    if not RDKIT_AVAILABLE:
        logger.warning("_radical_intermediates: RDKit not available")
        return []

    # N코드: 타입 가드
    if not isinstance(reactant_smi, str) or not reactant_smi.strip():
        logger.warning("_radical_intermediates: reactant_smi 타입/값 불일치 (type=%s)",
                       type(reactant_smi).__name__)
        return []
    if not isinstance(product_smi, str) or not product_smi.strip():
        logger.warning("_radical_intermediates: product_smi 타입/값 불일치 (type=%s)",
                       type(product_smi).__name__)
        return []

    mol = Chem.MolFromSmiles(reactant_smi)
    if mol is None:
        logger.warning("_radical_intermediates: 잘못된 reactant SMILES: %s", reactant_smi)
        return []

    intermediates = []

    intermediates.append(IntermediateInfo(
        smiles=reactant_smi,
        label="반응물",
        annotation="Starting material",
        is_intermediate=False,
    ))

    # ---- 라디칼 중간체 생성 ----
    # 벤질/알릴 위치에 라디칼 생성: C-H에서 H 제거 + 라디칼 전자 설정
    # 벤질 탄소 찾기: 방향족 고리에 인접한 sp3 탄소
    radical_idx = None
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 6 and atom.GetTotalNumHs() > 0:
            for nbr in atom.GetNeighbors():
                if nbr.GetIsAromatic():
                    radical_idx = atom.GetIdx()
                    break
            if radical_idx is not None:
                break

    # 알릴 위치: C=C에 인접한 sp3 탄소
    if radical_idx is None:
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() == 6 and atom.GetTotalNumHs() > 0:
                for nbr in atom.GetNeighbors():
                    bond = mol.GetBondBetweenAtoms(atom.GetIdx(), nbr.GetIdx())
                    if bond and bond.GetBondTypeAsDouble() == 2.0:
                        radical_idx = atom.GetIdx()
                        break
                if radical_idx is not None:
                    break

    if radical_idx is not None:
        rw = Chem.RWMol(mol)
        rw.GetAtomWithIdx(radical_idx).SetNumRadicalElectrons(1)
        rw.GetAtomWithIdx(radical_idx).SetNoImplicit(True)
        # H 하나 제거를 위해 NumExplicitHs 감소
        cur_h = rw.GetAtomWithIdx(radical_idx).GetNumExplicitHs()
        rw.GetAtomWithIdx(radical_idx).SetNumExplicitHs(max(0, cur_h - 1))

        rad_smi = _safe_smiles(rw)
        if rad_smi is None:
            # NoImplicit/ExplicitHs 없이 재시도
            rw2 = Chem.RWMol(mol)
            rw2.GetAtomWithIdx(radical_idx).SetNumRadicalElectrons(1)
            rad_smi = _safe_smiles(rw2)

        if rad_smi:
            intermediates.append(IntermediateInfo(
                smiles=rad_smi,
                label="탄소 라디칼",
                annotation="Carbon radical (benzylic/allylic, H abstraction by Br radical)",
                is_intermediate=True,
                radicals=[(radical_idx, 1)],
            ))

    intermediates.append(IntermediateInfo(
        smiles=product_smi,
        label="생성물",
        annotation="Brominated product",
        is_intermediate=False,
    ))

    return intermediates


# ============================================================
# Reaction detection + dispatcher
# ============================================================

def _detect_reaction_type(
    reactant_smi: str,
    product_smi: str,
    conditions: str = "",
) -> str:
    """반응물/생성물/조건으로 반응 유형 추정."""
    # N코드: 타입 가드
    if not isinstance(reactant_smi, str):
        logger.warning("_detect_reaction_type: reactant_smi 타입 불일치 (type=%s)",
                       type(reactant_smi).__name__)
        return "unknown"
    if not isinstance(product_smi, str):
        logger.warning("_detect_reaction_type: product_smi 타입 불일치 (type=%s)",
                       type(product_smi).__name__)
        return "unknown"
    if not isinstance(conditions, str):
        logger.warning("_detect_reaction_type: conditions 타입 불일치 (type=%s), converting",
                       type(conditions).__name__)
        conditions = str(conditions) if conditions else ""
    cond = conditions.lower()

    # Wolff-Kishner: 히드라진 + 강염기
    if "nh2nh2" in cond or "hydrazin" in cond or "n2h4" in cond:
        return "wolff_kishner"
    if "koh" in cond and ("200" in cond or "glycol" in cond):
        return "wolff_kishner"

    # Fischer: 산 촉매 + 알코올
    if "h2so4" in cond or "h+" in cond or "hcl" in cond:
        r_mol = Chem.MolFromSmiles(reactant_smi) if RDKIT_AVAILABLE else None
        if r_mol is not None:
            has_cooh = r_mol.HasSubstructMatch(Chem.MolFromSmarts("[CX3](=O)[OH]"))
            if has_cooh:
                return "fischer"

    # NBS / radical
    if "nbs" in cond or "radical" in cond or "hv" in cond or "peroxide" in cond:
        return "radical"

    # Aldol: 염기 + 카보닐
    if "naoh" in cond or "lda" in cond or "aldol" in cond or "naoet" in cond:
        return "aldol"

    # E2: 강염기 + 이탈기
    if ("naoh" in cond or "koet" in cond or "naome" in cond) and RDKIT_AVAILABLE:
        r_mol = Chem.MolFromSmiles(reactant_smi)
        if r_mol is not None:
            has_lg = r_mol.HasSubstructMatch(
                Chem.MolFromSmarts("[C][F,Cl,Br,I]")
            )
            if has_lg:
                return "e2"

    # 기본: 카보닐이 있으면 친핵첨가로 추정
    if RDKIT_AVAILABLE:
        r_mol = Chem.MolFromSmiles(reactant_smi)
        if r_mol is not None and _find_carbonyl_carbon(r_mol) is not None:
            return "carbonyl_addition"

    return "unknown"


def _split_reactants(reactant_smi: str) -> Tuple[str, str]:
    """'A.B' 형식의 SMILES를 두 조각으로 분리 (카보닐 쪽을 첫 번째로)."""
    # N코드: 타입 가드
    if not isinstance(reactant_smi, str):
        logger.warning("_split_reactants: reactant_smi 타입 불일치 (type=%s)",
                       type(reactant_smi).__name__)
        return (str(reactant_smi) if reactant_smi else "", "")
    parts = reactant_smi.split('.')
    if len(parts) < 2:
        return reactant_smi, ""

    if RDKIT_AVAILABLE:
        for i, p in enumerate(parts):
            m = Chem.MolFromSmiles(p)
            if m is not None and _find_carbonyl_carbon(m) is not None:
                others = '.'.join(parts[:i] + parts[i+1:])
                return p, others

    return parts[0], '.'.join(parts[1:])


# ============================================================
# PUBLIC API
# ============================================================

def generate_intermediates(
    reactant_smi: str,
    product_smi: str,
    conditions: str = "",
) -> List[Dict]:
    """반응물/생성물/조건에서 중간체 SMILES 목록 생성.

    Parameters
    ----------
    reactant_smi : str
        반응물 SMILES (여러 분자일 경우 '.'으로 연결)
    product_smi : str
        생성물 SMILES
    conditions : str
        반응 조건 텍스트 (예: "NH2NH2, KOH, 200°C, ethylene glycol")

    Returns
    -------
    list[dict]
        각 원소: {'smiles', 'label', 'annotation', 'is_intermediate',
                  'is_transition_state', 'charges', 'radicals'}
    """
    if not RDKIT_AVAILABLE:
        logger.warning("generate_intermediates: RDKit not available")
        return []

    if not isinstance(reactant_smi, str) or not reactant_smi.strip():
        logger.warning("generate_intermediates: invalid reactant_smi (type=%s, value=%r)",
                       type(reactant_smi).__name__, reactant_smi)
        return []

    if not isinstance(product_smi, str) or not product_smi.strip():
        logger.warning("generate_intermediates: invalid product_smi (type=%s, value=%r)",
                       type(product_smi).__name__, product_smi)
        return []

    if not isinstance(conditions, str):
        logger.warning("generate_intermediates: conditions is not str (type=%s), converting",
                       type(conditions).__name__)
        conditions = str(conditions) if conditions else ""

    rxn_type = _detect_reaction_type(reactant_smi, product_smi, conditions)
    logger.info("Detected reaction type: %s", rxn_type)

    results: List[IntermediateInfo] = []

    if rxn_type == "wolff_kishner":
        main_smi, _ = _split_reactants(reactant_smi)
        results = _wolff_kishner_intermediates(main_smi, product_smi)

    elif rxn_type == "aldol":
        main_smi, _ = _split_reactants(reactant_smi)
        results = _aldol_intermediates(main_smi, product_smi)

    elif rxn_type == "fischer":
        main_smi, alc_smi = _split_reactants(reactant_smi)
        if not alc_smi:
            alc_smi = "CO"  # methanol fallback
        results = _fischer_esterification_intermediates(
            main_smi, alc_smi, product_smi
        )

    elif rxn_type == "e2":
        results = _e2_elimination_intermediates(reactant_smi, product_smi)

    elif rxn_type == "radical":
        results = _radical_intermediates(reactant_smi, product_smi)

    elif rxn_type == "carbonyl_addition":
        main_smi, nuc_smi = _split_reactants(reactant_smi)
        mol = Chem.MolFromSmiles(main_smi)
        if mol is not None and nuc_smi:
            results.append(IntermediateInfo(
                smiles=reactant_smi,
                label="반응물",
                annotation="Starting materials",
                is_intermediate=False,
            ))
            tet = _carbonyl_nucleophilic_addition(mol, nuc_smi)
            results.extend(tet)
            results.append(IntermediateInfo(
                smiles=product_smi,
                label="생성물",
                annotation="Product",
                is_intermediate=False,
            ))

    # 기본 fallback: 반응물 + 생성물만
    if not results:
        results = [
            IntermediateInfo(
                smiles=reactant_smi,
                label="반응물",
                annotation="Starting material",
                is_intermediate=False,
            ),
            IntermediateInfo(
                smiles=product_smi,
                label="생성물",
                annotation="Product",
                is_intermediate=False,
            ),
        ]

    # Validate all SMILES
    validated: List[Dict] = []
    for info in results:
        check = Chem.MolFromSmiles(info.smiles)
        if check is not None:
            validated.append({
                'smiles': info.smiles,
                'label': info.label,
                'annotation': info.annotation,
                'is_intermediate': info.is_intermediate,
                'is_transition_state': info.is_transition_state,
                'charges': info.charges,
                'radicals': info.radicals,
            })
        else:
            logger.warning("Invalid SMILES skipped: %s (%s)", info.smiles, info.label)

    return validated
