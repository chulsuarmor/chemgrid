# mechanism_engine.py (v1.0 - General-Purpose Reaction Mechanism Engine)
"""
ChemGrid: 범용 반응 메커니즘 생성 엔진
- 하드코딩된 gold standard 메커니즘 우선 반환
- 미등록 반응 → BondChangeDetector + ArrowGenerator로 자동 생성
- ORCA DFT (Tier 1) / Gasteiger (Tier 2) / 전기음성도 (Tier 3) 품질 등급
"""

import logging
from typing import Optional, List, Tuple, Dict

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdChemReactions
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

from reaction_mechanisms import (
    ArrowData, MechanismStep, MechanismData,
    get_mechanism, MECHANISMS
)
from bond_change_detector import BondChangeDetector, BondChangeResult
from arrow_generator import ArrowGenerator


# ============================================================================
# ORCA Availability Check
# ============================================================================

def _check_orca() -> bool:
    """ORCA 실행파일 존재 여부 확인"""
    try:
        from orca_interface import find_orca_executable
        return find_orca_executable() is not None
    except ImportError:
        return False


# ============================================================================
# REACTION SMARTS TEMPLATES (for product prediction)
# ============================================================================

REACTION_SMARTS: Dict[str, str] = {
    # 기본 치환/제거 반응
    "sn2_halide_oh": "[C:1][F,Cl,Br,I:2].[OH-:3]>>[C:1][OH:3].[F,Cl,Br,I-:2]",
    "sn2_halide_cn": "[C:1][F,Cl,Br,I:2].[C-:3]#[N:4]>>[C:1][C:3]#[N:4].[F,Cl,Br,I-:2]",
    "ester_formation": "[C:1](=[O:2])[OH:3].[OH:4][C:5]>>[C:1](=[O:2])[O:4][C:5].[OH2:3]",
    "amide_formation": "[C:1](=[O:2])[OH:3].[NH2:4][C:5]>>[C:1](=[O:2])[NH:4][C:5].[OH2:3]",

    # 페리고리 반응
    "diels_alder": "[C:1]=[C:2][C:3]=[C:4].[C:5]=[C:6]>>[C:1]1[C:2]=[C:3][C:4][C:6][C:5]1",

    # E2 제거
    "e2_halide_base": "[C:1][C:2]([H:6])[F,Cl,Br,I:3].[OH-:4]>>[C:1]=[C:2].[F,Cl,Br,I-:3].[OH2:4]",

    # Suzuki coupling
    "suzuki_coupling": "[c:1][Cl,Br,I:2].[c:3][B:4]([OH:5])[OH:6]>>[c:1][c:3]",

    # Heck reaction (simplified)
    "heck_reaction": "[c:1][Cl,Br,I:2].[C:3]=[C:4]>>[c:1]/[C:3]=[C:4]",
}


# ============================================================================
# MULTI-STEP DECOMPOSITION HEURISTICS
# ============================================================================

def _get_substitution_degree(mol, atom_idx: int) -> int:
    """탄소의 치환도 (1차/2차/3차/4차)"""
    atom = mol.GetAtomWithIdx(atom_idx)
    if atom.GetAtomicNum() != 6:
        return 0
    carbon_neighbors = sum(1 for n in atom.GetNeighbors() if n.GetAtomicNum() == 6)
    return carbon_neighbors


LEAVING_GROUPS = {9, 17, 35, 53}  # F, Cl, Br, I

# Pauling electronegativity (주요 원소)
_ELECTRONEG = {
    1: 2.20,   # H
    6: 2.55,   # C
    7: 3.04,   # N
    8: 3.44,   # O
    9: 3.98,   # F
    15: 2.19,  # P
    16: 2.58,  # S
    17: 3.16,  # Cl
    35: 2.96,  # Br
    53: 2.66,  # I
}


def _has_leaving_group(mol, atom_idx: int) -> bool:
    """원자에 이탈기가 연결되어 있는지"""
    atom = mol.GetAtomWithIdx(atom_idx)
    for n in atom.GetNeighbors():
        if n.GetAtomicNum() in LEAVING_GROUPS:
            return True
    return False


# ============================================================================
# MAIN CLASS
# ============================================================================

class MechanismEngine:
    """
    범용 반응 메커니즘 생성 엔진.

    사용법:
        engine = MechanismEngine()
        mech = engine.generate_mechanism("CBr.[OH-]", "CO.[Br-]")
        if mech:
            for step in mech.steps:
                print(step.title, len(step.arrows), "arrows")
    """

    def __init__(self):
        self._detector = BondChangeDetector()
        self._arrow_gen = ArrowGenerator(orca_available=_check_orca())

    def generate_mechanism(self,
                            reactant_smiles: str,
                            product_smiles: str = "",
                            reagent_smiles: str = "",
                            mechanism_type_hint: str = "") -> Optional[MechanismData]:
        """
        반응 메커니즘 생성 (메인 진입점).

        Args:
            reactant_smiles: 반응물 SMILES (multi-fragment OK)
            product_smiles: 생성물 SMILES (빈 문자열이면 예측 시도)
            reagent_smiles: 시약 SMILES (옵션)
            mechanism_type_hint: 메커니즘 유형 힌트 (e.g. "sn2")

        Returns:
            MechanismData or None
        """
        if not RDKIT_AVAILABLE:
            logger.warning("RDKit not available - MechanismEngine disabled")
            return None

        # ─── 1. 하드코딩 gold standard 확인 ───
        if mechanism_type_hint:
            hardcoded = get_mechanism(mechanism_type_hint)
            if hardcoded:
                logger.info(f"Gold standard 메커니즘 반환: {mechanism_type_hint}")
                return hardcoded

        # ─── 2. 생성물 예측 (필요 시) ───
        if not product_smiles:
            product_smiles = self._predict_product(reactant_smiles, reagent_smiles)
            if not product_smiles:
                logger.warning("생성물 예측 실패")
                return None

        # ─── 3. 결합 변화 탐지 ───
        result = self._detector.detect(reactant_smiles, product_smiles)
        if result is None or not result.bond_changes:
            logger.warning("결합 변화 감지 실패 또는 변화 없음")
            return None

        # ─── 4. 다단계 분해 여부 결정 ───
        step_groups = self._decompose_into_steps(result)

        # ─── 5. 각 단계별 화살표 생성 ───
        mechanism_steps: List[MechanismStep] = []

        if len(step_groups) == 1:
            # 단일 단계 (동시)
            arrows = self._arrow_gen.generate(result)
            step = MechanismStep(
                step_number=1,
                title=self._generate_step_title(result, arrows),
                description=self._generate_step_description(result, arrows),
                reactant_smiles=reactant_smiles,
                product_smiles=product_smiles,
                arrows=arrows,
                notes=reagent_smiles,
            )
            mechanism_steps.append(step)
        else:
            # 다단계
            for i, (step_changes, step_desc) in enumerate(step_groups):
                step_result = BondChangeResult(
                    mapping=result.mapping,
                    bond_changes=step_changes,
                    charge_changes=[cc for cc in result.charge_changes
                                    if any(cc.atom_idx in (bc.atom_i, bc.atom_j)
                                           for bc in step_changes)],
                    r_mol=result.r_mol,
                    p_mol=result.p_mol,
                )
                arrows = self._arrow_gen.generate(step_result)

                # 중간체 SMILES (근사)
                if i == 0:
                    r_smi = reactant_smiles
                    p_smi = self._estimate_intermediate_smiles(reactant_smiles, step_changes)
                else:
                    r_smi = mechanism_steps[-1].product_smiles if mechanism_steps else reactant_smiles
                    p_smi = product_smiles if i == len(step_groups) - 1 else \
                            self._estimate_intermediate_smiles(r_smi, step_changes)

                step = MechanismStep(
                    step_number=i + 1,
                    title=step_desc,
                    description=self._generate_step_description(step_result, arrows),
                    reactant_smiles=r_smi,
                    product_smiles=p_smi,
                    arrows=arrows,
                    notes=reagent_smiles if i == 0 else "",
                )
                mechanism_steps.append(step)

        # ─── 6. MechanismData 조립 ───
        mech = MechanismData(
            mechanism_type="auto_generated",
            title=self._generate_mechanism_title(reactant_smiles, product_smiles),
            total_steps=len(mechanism_steps),
            steps=mechanism_steps,
            energy_diagram=self._estimate_energy_diagram(mechanism_steps),
            overall_description=self._generate_overall_description(mechanism_steps, reactant_smiles, product_smiles),
        )

        logger.info(
            f"메커니즘 자동 생성 완료: {mech.title}, "
            f"{mech.total_steps}단계, "
            f"총 {sum(len(s.arrows) for s in mech.steps)}개 화살표"
        )
        return mech

    # ────────────────────────────────────────────────────────────────────
    # Product Prediction
    # ────────────────────────────────────────────────────────────────────

    def _predict_product(self, reactant_smiles: str, reagent_smiles: str) -> str:
        """
        RDKit RunReactants로 생성물 예측.
        REACTION_SMARTS 템플릿을 순회하며 첫 매칭 반환.
        """
        try:
            # 시약을 반응물에 포함
            combined = reactant_smiles
            if reagent_smiles:
                combined = f"{reactant_smiles}.{reagent_smiles}"

            r_mol = Chem.MolFromSmiles(combined)
            if r_mol is None:
                return ""

            # 각 반응 템플릿 시도
            for name, smarts in REACTION_SMARTS.items():
                try:
                    rxn = rdChemReactions.ReactionFromSmarts(smarts)
                    if rxn is None:
                        continue

                    # 반응물 분리
                    frags = Chem.GetMolFrags(r_mol, asMols=True)
                    if len(frags) < rxn.GetNumReactantTemplates():
                        continue

                    # 모든 순열 시도
                    from itertools import permutations
                    for perm in permutations(frags, rxn.GetNumReactantTemplates()):
                        products = rxn.RunReactants(perm)
                        if products:
                            # 모든 product fragment를 합산하여 완전한 생성물 SMILES 생성
                            product_smiles_list = []
                            for p in products[0]:
                                try:
                                    Chem.SanitizeMol(p)
                                    product_smiles_list.append(Chem.MolToSmiles(p))
                                except Exception:
                                    pass
                            if product_smiles_list:
                                # 모든 fragment를 dot-separated로 합산 후 검증
                                combined = ".".join(product_smiles_list)
                                combined_mol = Chem.MolFromSmiles(combined)
                                if combined_mol is not None:
                                    # 정규화된 SMILES 반환 (모든 fragment 포함)
                                    result = Chem.MolToSmiles(combined_mol)
                                    logger.info(f"생성물 예측 성공 ({name}): {result}")
                                    return result
                                else:
                                    # 검증 실패 시 원본 합산 문자열 반환
                                    logger.info(f"생성물 예측 성공 ({name}, 미검증): {combined}")
                                    return combined

                except Exception as e:
                    logger.debug(f"반응 템플릿 {name} 실패: {e}")
                    continue

        except Exception as e:
            logger.warning(f"생성물 예측 오류: {e}")

        return ""

    # ────────────────────────────────────────────────────────────────────
    # Multi-Step Decomposition
    # ────────────────────────────────────────────────────────────────────

    def _decompose_into_steps(self, result: BondChangeResult) \
            -> List[Tuple[List, str]]:
        """
        결합 변화를 여러 단계로 분해.

        Returns:
            [(bond_changes, step_description), ...]
        """
        changes = result.bond_changes
        r_mol = result.r_mol

        # 페리고리 → 단일 단계
        from arrow_generator import ArrowGenerator
        temp_gen = ArrowGenerator()
        if temp_gen._detect_pericyclic(changes, r_mol):
            return [(changes, "페리고리 협주 반응: 전자가 고리형 전이 상태를 통해 동시 재배열")]

        # SN1/E1 패턴 감지 (3차 탄소 우선 — 변화 3개 이하라도 분해 시도)
        broken = [bc for bc in changes if bc.is_broken]
        formed = [bc for bc in changes if bc.is_formed]

        for bc in broken:
            # C-X 결합 끊김에서 C가 3차이면 → 2단계
            for atom_idx in (bc.atom_i, bc.atom_j):
                if 0 <= atom_idx < r_mol.GetNumAtoms():
                    atom = r_mol.GetAtomWithIdx(atom_idx)
                    if atom.GetAtomicNum() == 6:
                        degree = _get_substitution_degree(r_mol, atom_idx)
                        other_idx = bc.atom_j if atom_idx == bc.atom_i else bc.atom_i
                        if degree >= 3 and 0 <= other_idx < r_mol.GetNumAtoms():
                            other_atom = r_mol.GetAtomWithIdx(other_idx)
                            if other_atom.GetAtomicNum() in LEAVING_GROUPS:
                                # SN1/E1: 단계 1 = 이탈, 단계 2 = 공격
                                lg_name = {9: "F", 17: "Cl", 35: "Br", 53: "I"}.get(
                                    other_atom.GetAtomicNum(), "X")
                                step1 = [bc]  # C-X 끊김
                                step2 = [c for c in changes if c != bc]
                                return [
                                    (step1, f"C-{lg_name} 결합 이종 개열 → {lg_name}⁻ 이탈 + 카르보카티온(C⁺) 형성"),
                                    (step2, "친핵체의 론페어가 카르보카티온의 빈 p 오비탈을 공격"),
                                ]

        # 변화가 3개 이하면서 SN1 패턴이 아니면 → 단일 단계 (동시)
        if len(changes) <= 3:
            return [(changes, "동시 반응")]

        # 기본: 끊김 먼저, 생성 나중 (4개 이상 변화)
        if broken and formed:
            # 끊어지는 결합의 원자 기호를 추출
            broken_labels = []
            for bc in broken:
                if r_mol and 0 <= bc.atom_i < r_mol.GetNumAtoms() and 0 <= bc.atom_j < r_mol.GetNumAtoms():
                    si = r_mol.GetAtomWithIdx(bc.atom_i).GetSymbol()
                    sj = r_mol.GetAtomWithIdx(bc.atom_j).GetSymbol()
                    broken_labels.append(f"{si}-{sj}")
            formed_labels = []
            for bc in formed:
                if r_mol and 0 <= bc.atom_i < r_mol.GetNumAtoms() and 0 <= bc.atom_j < r_mol.GetNumAtoms():
                    si = r_mol.GetAtomWithIdx(bc.atom_i).GetSymbol()
                    sj = r_mol.GetAtomWithIdx(bc.atom_j).GetSymbol()
                    formed_labels.append(f"{si}-{sj}")

            other = [c for c in changes if c not in broken and c not in formed]
            step1 = broken + other
            step2 = formed
            bl = ", ".join(broken_labels) if broken_labels else "결합"
            fl = ", ".join(formed_labels) if formed_labels else "결합"
            return [
                (step1, f"{bl} 결합 끊어짐 → 전자쌍이 전기음성 원자로 이동"),
                (step2, f"새 {fl} 결합 형성 → 론페어/전자쌍이 결합으로 전환"),
            ]

        # 분해 불가 → 단일 단계
        return [(changes, "동시 협주 반응: 결합 끊김과 형성이 동시에 진행")]

    # ────────────────────────────────────────────────────────────────────
    # Helper Methods
    # ────────────────────────────────────────────────────────────────────

    def _generate_step_title(self, result: BondChangeResult,
                              arrows: List[ArrowData]) -> str:
        """단계 제목 자동 생성 — 화학적으로 의미있는 제목"""
        broken = []
        formed = []
        order_changes = []

        for bc in result.bond_changes:
            sym_i, sym_j = self._get_atom_symbols(result.r_mol, bc.atom_i, bc.atom_j)
            if bc.is_broken:
                broken.append(f"{sym_i}-{sym_j}")
            elif bc.is_formed:
                formed.append(f"{sym_i}-{sym_j}")
            else:
                order_changes.append(f"{sym_i}-{sym_j}")

        if broken and formed:
            return f"{', '.join(broken)} 결합 끊김 → {', '.join(formed)} 결합 형성 (동시)"
        elif broken:
            return f"{', '.join(broken)} 결합 이종 개열 (heterolysis)"
        elif formed:
            return f"{', '.join(formed)} 새 결합 형성 (친핵 공격)"
        elif order_changes:
            return f"{', '.join(order_changes)} 결합 차수 변화"
        else:
            return "전자 재배열"

    @staticmethod
    def _get_atom_symbols(mol, atom_i: int, atom_j: int):
        """원자 인덱스로부터 원소 기호 추출"""
        if mol:
            sym_i = mol.GetAtomWithIdx(atom_i).GetSymbol() \
                if 0 <= atom_i < mol.GetNumAtoms() else "외부"
            sym_j = mol.GetAtomWithIdx(atom_j).GetSymbol() \
                if 0 <= atom_j < mol.GetNumAtoms() else "외부"
        else:
            sym_i, sym_j = "?", "?"
        return sym_i, sym_j

    @staticmethod
    def _classify_atom_role(mol, atom_idx: int, is_leaving: bool = False) -> str:
        """원자의 화학적 역할을 판별 (친핵체/친전자체/이탈기 등)"""
        if mol is None or atom_idx < 0 or atom_idx >= mol.GetNumAtoms():
            return ""
        atom = mol.GetAtomWithIdx(atom_idx)
        anum = atom.GetAtomicNum()
        charge = atom.GetFormalCharge()
        symbol = atom.GetSymbol()

        # 이탈기 판별
        if is_leaving and anum in LEAVING_GROUPS:
            _names = {9: "F⁻", 17: "Cl⁻", 35: "Br⁻", 53: "I⁻"}
            return f"{_names.get(anum, symbol + '⁻')} (이탈기)"

        # 음전하 → 친핵체
        if charge < 0:
            return f"{symbol}⁻ (친핵체)"

        # 양전하 → 친전자체
        if charge > 0:
            return f"{symbol}⁺ (친전자체)"

        # 전기음성도 기반 역할 추론
        en = _ELECTRONEG.get(anum, 2.5)
        if en > 3.0 and anum != 6:  # O, N, F 등 전기음성 원소
            return f"{symbol} (론페어 보유, 친핵성)"
        if anum == 6:
            return f"C (탄소)"

        return symbol

    def _generate_step_description(self, result: BondChangeResult,
                                    arrows: List[ArrowData]) -> str:
        """
        단계 상세 설명 자동 생성 — 화학적으로 정확하고 교육적인 설명.
        각 결합 변화에 대해:
        - 어떤 결합이 끊어지는지/형성되는지
        - 전자가 어디로 이동하는지
        - 이탈기/친핵체/친전자체 명시
        - WHY 이 변화가 일어나는지 설명
        """
        parts = []
        broken_bonds = []
        formed_bonds = []

        for bc in result.bond_changes:
            sym_i, sym_j = self._get_atom_symbols(result.r_mol, bc.atom_i, bc.atom_j)

            if bc.is_broken:
                broken_bonds.append((sym_i, sym_j, bc))
            elif bc.is_formed:
                formed_bonds.append((sym_i, sym_j, bc))

        # 끊어지는 결합 설명
        for sym_i, sym_j, bc in broken_bonds:
            # 이탈기 여부 판별
            leaving_info = ""
            electron_info = ""
            if result.r_mol:
                en_i = _ELECTRONEG.get(
                    result.r_mol.GetAtomWithIdx(bc.atom_i).GetAtomicNum(), 2.5
                ) if 0 <= bc.atom_i < result.r_mol.GetNumAtoms() else 2.5
                en_j = _ELECTRONEG.get(
                    result.r_mol.GetAtomWithIdx(bc.atom_j).GetAtomicNum(), 2.5
                ) if 0 <= bc.atom_j < result.r_mol.GetNumAtoms() else 2.5

                if en_i > en_j:
                    electron_info = f"결합 전자쌍이 {sym_i}(전기음성도 {en_i:.1f})로 이동"
                    if 0 <= bc.atom_j < result.r_mol.GetNumAtoms() and \
                       result.r_mol.GetAtomWithIdx(bc.atom_j).GetAtomicNum() in LEAVING_GROUPS:
                        leaving_info = f" → {sym_j}⁻가 이탈기로 떠남"
                    elif 0 <= bc.atom_i < result.r_mol.GetNumAtoms() and \
                         result.r_mol.GetAtomWithIdx(bc.atom_i).GetAtomicNum() in LEAVING_GROUPS:
                        leaving_info = f" → {sym_i}⁻가 이탈기로 떠남"
                elif en_j > en_i:
                    electron_info = f"결합 전자쌍이 {sym_j}(전기음성도 {en_j:.1f})로 이동"
                    if 0 <= bc.atom_i < result.r_mol.GetNumAtoms() and \
                       result.r_mol.GetAtomWithIdx(bc.atom_i).GetAtomicNum() in LEAVING_GROUPS:
                        leaving_info = f" → {sym_i}⁻가 이탈기로 떠남"
                    elif 0 <= bc.atom_j < result.r_mol.GetNumAtoms() and \
                         result.r_mol.GetAtomWithIdx(bc.atom_j).GetAtomicNum() in LEAVING_GROUPS:
                        leaving_info = f" → {sym_j}⁻가 이탈기로 떠남"
                else:
                    electron_info = f"결합 전자쌍이 균일 개열(homolysis)"

            desc = f"{sym_i}-{sym_j} 결합이 이종 개열(heterolysis): {electron_info}{leaving_info}"
            parts.append(desc)

        # 형성되는 결합 설명
        for sym_i, sym_j, bc in formed_bonds:
            # 어느 쪽이 전자를 공여하는지 판별
            donor_info = ""
            if result.r_mol:
                # 음전하를 가진 쪽 또는 전기음성도가 높은 비탄소 원자가 전자 공여
                for idx, sym in [(bc.atom_i, sym_i), (bc.atom_j, sym_j)]:
                    if 0 <= idx < result.r_mol.GetNumAtoms():
                        atom = result.r_mol.GetAtomWithIdx(idx)
                        if atom.GetFormalCharge() < 0:
                            donor_info = f"{sym}⁻의 론페어가 전자를 공여 → "
                            break
                        elif atom.GetAtomicNum() in (7, 8, 16) and atom.GetAtomicNum() != 6:
                            donor_info = f"{sym}의 론페어가 전자를 공여 → "
                            break

            bond_type = "sigma"
            if hasattr(bc, 'product_order') and bc.product_order == 2.0:
                bond_type = "pi"

            desc = f"{donor_info}새 {sym_i}-{sym_j} {bond_type} 결합 형성"
            parts.append(desc)

        # 결합 차수 변화 설명
        for bc in result.bond_changes:
            if bc.change_type == "order_increase":
                sym_i, sym_j = self._get_atom_symbols(result.r_mol, bc.atom_i, bc.atom_j)
                parts.append(
                    f"{sym_i}-{sym_j} 결합 차수 증가 ({bc.reactant_order}→{bc.product_order}): "
                    f"전자밀도가 결합 영역으로 이동하여 결합이 강화됨"
                )
            elif bc.change_type == "order_decrease":
                sym_i, sym_j = self._get_atom_symbols(result.r_mol, bc.atom_i, bc.atom_j)
                parts.append(
                    f"{sym_i}-{sym_j} 결합 차수 감소 ({bc.reactant_order}→{bc.product_order}): "
                    f"전자밀도가 결합에서 빠져나가 결합이 약화됨"
                )

        if not parts:
            return "전자 재배열이 일어남"

        return ".\n".join(parts) + "."

    def _generate_overall_description(self, steps: List[MechanismStep],
                                        reactant_smiles: str,
                                        product_smiles: str) -> str:
        """메커니즘 전체 요약 설명 자동 생성"""
        n = len(steps)
        step_summaries = []
        for s in steps:
            # 제목에서 핵심 정보 추출
            step_summaries.append(f"단계 {s.step_number}: {s.title}")

        # 결합 변화 통계
        total_broken = sum(len([a for a in s.arrows if "끊" in a.from_label or "결합" in a.from_label])
                           for s in steps)
        total_formed = sum(len([a for a in s.arrows if "론페어" in a.from_label or "negative" in a.from_type])
                           for s in steps)

        desc = f"이 반응은 {n}단계로 진행됩니다. "
        if n == 1:
            desc += "모든 결합 변화가 동시에(협주적으로) 일어나는 반응입니다. "
        else:
            desc += "각 단계에서 결합이 순차적으로 끊어지고 형성됩니다. "

        desc += " → ".join(step_summaries) + "."
        return desc

    def _generate_mechanism_title(self, reactant_smiles: str,
                                   product_smiles: str) -> str:
        """메커니즘 전체 제목 생성"""
        # 간단한 SMILES → 이름 변환 시도
        try:
            r_mol = Chem.MolFromSmiles(reactant_smiles)
            p_mol = Chem.MolFromSmiles(product_smiles)
            if r_mol and p_mol:
                r_formula = Chem.rdMolDescriptors.CalcMolFormula(r_mol)
                p_formula = Chem.rdMolDescriptors.CalcMolFormula(p_mol)
                return f"{r_formula} → {p_formula}"
        except Exception:
            pass
        return f"반응 메커니즘"

    def _estimate_intermediate_smiles(self, start_smiles: str,
                                       step_changes) -> str:
        """
        RDKit RWMol 기반 중간체 SMILES 생성.

        결합 변화(BondChange) 목록을 start_smiles 분자에 적용하여
        중간체 구조를 생성한다.  결합 끊김/생성/차수 변화를 RWMol
        AddBond/RemoveBond/SetBondType으로 수행한 뒤 SanitizeMol을
        거쳐 SMILES를 반환한다.

        SanitizeMol 실패 시 start_smiles를 그대로 반환 (안전 폴백).
        """
        if not RDKIT_AVAILABLE:
            return start_smiles

        try:
            mol = Chem.MolFromSmiles(start_smiles)
            if mol is None:
                return start_smiles

            rwmol = Chem.RWMol(mol)
            num_atoms = rwmol.GetNumAtoms()

            # BondType 매핑
            _order_to_bondtype = {
                1.0: Chem.BondType.SINGLE,
                2.0: Chem.BondType.DOUBLE,
                3.0: Chem.BondType.TRIPLE,
                1.5: Chem.BondType.AROMATIC,
            }

            for bc in step_changes:
                ai = bc.atom_i
                aj = bc.atom_j

                # 범위 초과 원자 인덱스는 건너뛴다 (외부 조각 원자)
                if ai >= num_atoms or aj >= num_atoms or ai < 0 or aj < 0:
                    continue

                existing_bond = rwmol.GetBondBetweenAtoms(ai, aj)

                if bc.is_broken:
                    # ── 결합 끊김 ──
                    if existing_bond is not None:
                        rwmol.RemoveBond(ai, aj)
                        # 이탈기 원자의 형식전하 보정
                        self._adjust_charge_on_break(rwmol, ai, aj, bc.reactant_order)

                elif bc.is_formed:
                    # ── 새 결합 생성 ──
                    if existing_bond is None:
                        bt = _order_to_bondtype.get(bc.product_order, Chem.BondType.SINGLE)
                        rwmol.AddBond(ai, aj, bt)
                        # 형식전하 보정
                        self._adjust_charge_on_form(rwmol, ai, aj)

                elif bc.change_type in ("order_increase", "order_decrease"):
                    # ── 결합 차수 변화 ──
                    if existing_bond is not None:
                        new_bt = _order_to_bondtype.get(bc.product_order, Chem.BondType.SINGLE)
                        existing_bond.SetBondType(new_bt)

            # SanitizeMol 시도 — 실패 시 원래 SMILES 반환
            try:
                Chem.SanitizeMol(rwmol)
                result = Chem.MolToSmiles(rwmol)
                # 빈 SMILES나 유효하지 않은 결과 체크
                if result and Chem.MolFromSmiles(result) is not None:
                    return result
            except Exception as e:
                logger.debug(f"중간체 SanitizeMol 실패 (partial sanitize 시도): {e}")
                # partial sanitize 시도 (valence 에러 무시)
                try:
                    Chem.SanitizeMol(rwmol,
                                     sanitizeOps=Chem.SanitizeFlags.SANITIZE_ALL ^
                                     Chem.SanitizeFlags.SANITIZE_PROPERTIES)
                    result = Chem.MolToSmiles(rwmol)
                    if result:
                        return result
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"중간체 SMILES 생성 오류: {e}")

        return start_smiles  # 안전 폴백

    @staticmethod
    def _adjust_charge_on_break(rwmol, ai: int, aj: int, bond_order: float):
        """결합 끊김 시 형식전하 보정 (헤테로리틱 분열 가정)"""
        try:
            atom_i = rwmol.GetAtomWithIdx(ai)
            atom_j = rwmol.GetAtomWithIdx(aj)

            # 전기음성도가 높은 쪽에 음전하 부여 (헤테로리틱)
            en_i = _ELECTRONEG.get(atom_i.GetAtomicNum(), 2.5)
            en_j = _ELECTRONEG.get(atom_j.GetAtomicNum(), 2.5)

            if en_i > en_j:
                # i가 더 전기음성적 → 전자 쌍을 가져감
                atom_i.SetFormalCharge(atom_i.GetFormalCharge() - 1)
                atom_j.SetFormalCharge(atom_j.GetFormalCharge() + 1)
            elif en_j > en_i:
                atom_j.SetFormalCharge(atom_j.GetFormalCharge() - 1)
                atom_i.SetFormalCharge(atom_i.GetFormalCharge() + 1)
            # en_i == en_j: 동종 분열 — 전하 변화 없음
        except Exception:
            pass

    @staticmethod
    def _adjust_charge_on_form(rwmol, ai: int, aj: int):
        """새 결합 형성 시 형식전하 보정"""
        try:
            atom_i = rwmol.GetAtomWithIdx(ai)
            atom_j = rwmol.GetAtomWithIdx(aj)

            # 음전하를 가진 쪽이 전자를 공여 → 전하 중화
            if atom_i.GetFormalCharge() < 0:
                atom_i.SetFormalCharge(atom_i.GetFormalCharge() + 1)
            if atom_j.GetFormalCharge() > 0:
                atom_j.SetFormalCharge(atom_j.GetFormalCharge() - 1)
        except Exception:
            pass

    def _estimate_energy_diagram(self, steps: List[MechanismStep]) \
            -> List[Tuple[str, float]]:
        """에너지 다이어그램 근사"""
        diagram = [("반응물", 0.0)]

        for i, step in enumerate(steps):
            # 전이 상태 (활성화 에너지 근사)
            n_arrows = len(step.arrows)
            barrier = 15.0 + n_arrows * 5.0  # 화살표 많을수록 높은 장벽
            diagram.append((f"TS{i + 1}", barrier))

            # 중간체/생성물
            if i < len(steps) - 1:
                diagram.append((f"중간체 {i + 1}", 5.0))
            else:
                diagram.append(("생성물", -10.0))

        return diagram


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def auto_mechanism(reactant_smiles: str,
                    product_smiles: str = "",
                    reagent_smiles: str = "",
                    mechanism_type_hint: str = "") -> Optional[MechanismData]:
    """
    편의 함수: MechanismEngine 인스턴스 생성 없이 직접 호출.

    사용법:
        mech = auto_mechanism("CBr.[OH-]", "CO.[Br-]")
    """
    engine = MechanismEngine()
    return engine.generate_mechanism(
        reactant_smiles=reactant_smiles,
        product_smiles=product_smiles,
        reagent_smiles=reagent_smiles,
        mechanism_type_hint=mechanism_type_hint,
    )
