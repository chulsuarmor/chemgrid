# smiles_validator.py - SMILES 유효성 검사 및 표준화
"""
SMILES Validation System for ChemDraw Pro
- SMILES 문법 검사
- 분자 유효성 확인
- 표준화 및 정규화
"""

from typing import Tuple, Optional, List
from dataclasses import dataclass
import logging

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
    logging.warning("[SMILES] RDKit not available")


@dataclass
class SMILESValidationResult:
    """SMILES 검증 결과"""
    is_valid: bool
    normalized_smiles: str
    canonical_smiles: str
    error_message: str = ""
    warnings: List[str] = None
    molecular_weight: float = 0.0
    num_atoms: int = 0
    num_bonds: int = 0
    num_rotatable_bonds: int = 0
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class SMILESValidator:
    """SMILES 유효성 검사 및 분자 정보 추출"""
    
    @staticmethod
    def validate_and_normalize(smiles: str) -> SMILESValidationResult:
        """
        SMILES 검증 및 정규화
        
        Args:
            smiles: SMILES 문자열
        
        Returns:
            SMILESValidationResult 객체
        """
        if not RDKIT_AVAILABLE:
            return SMILESValidationResult(
                is_valid=False,
                normalized_smiles=smiles,
                canonical_smiles="",
                error_message="RDKit이 설치되지 않았습니다"
            )
        
        result = SMILESValidationResult(
            is_valid=False,
            normalized_smiles="",
            canonical_smiles="",
            warnings=[]
        )
        
        # 빈 문자열 확인
        if not smiles or not smiles.strip():
            result.error_message = "SMILES가 비어있습니다"
            return result
        
        smiles = smiles.strip()
        
        try:
            # SMILES 파싱
            mol = Chem.MolFromSmiles(smiles)
            
            if mol is None:
                result.error_message = f"유효하지 않은 SMILES 구문: {smiles}"
                return result
            
            # 분자 살균화 (sanitization)
            try:
                Chem.SanitizeMol(mol)
            except Chem.SanitizationException as e:
                result.error_message = f"분자 살균화 실패: {str(e)}"
                result.warnings.append("부분적으로 유효한 SMILES")
                # 살균화 실패해도 계속 진행 (부분 유효)
            
            # 입체화학 할당
            try:
                Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
            except Exception as e:
                result.warnings.append(f"입체화학 할당 실패: {str(e)}")
            
            # 정규화된 SMILES
            try:
                normalized = Chem.MolToSmiles(mol)
                result.normalized_smiles = normalized
            except Exception as e:
                result.error_message = f"정규화 실패: {str(e)}"
                return result
            
            # 정준 SMILES
            try:
                canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
                result.canonical_smiles = canonical
            except Exception as e:
                result.canonical_smiles = result.normalized_smiles
            
            # 분자 정보 추출
            result.num_atoms = mol.GetNumAtoms()
            result.num_bonds = mol.GetNumBonds()
            
            try:
                result.molecular_weight = Descriptors.MolWt(mol)
                result.num_rotatable_bonds = Descriptors.NumRotatableBonds(mol)
            except Exception as e:
                result.warnings.append(f"분자 특성 계산 실패: {str(e)}")
            
            # 검증 통과
            result.is_valid = True
            
            # 경고 확인
            if result.num_atoms > 1000:
                result.warnings.append("매우 큰 분자 (1000+ 원자)")
            
            if "." in normalized:
                result.warnings.append("다중 분자 (혼합물 또는 염)")
            
            return result
        
        except Exception as e:
            result.error_message = f"예상치 못한 오류: {str(e)}"
            return result
    
    @staticmethod
    def validate_batch(smiles_list: List[str]) -> List[SMILESValidationResult]:
        """
        여러 SMILES 일괄 검증
        
        Args:
            smiles_list: SMILES 문자열 리스트
        
        Returns:
            검증 결과 리스트
        """
        return [SMILESValidator.validate_and_normalize(s) for s in smiles_list]
    
    @staticmethod
    def get_molecular_formula(smiles: str) -> Optional[str]:
        """분자식 계산"""
        if not RDKIT_AVAILABLE:
            return None
        
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            
            from rdkit.Chem import rdMolDescriptors
            return rdMolDescriptors.CalcMolFormula(mol)
        except Exception:
            return None
    
    @staticmethod
    def get_inchi(smiles: str) -> Optional[str]:
        """InChI 문자열 계산"""
        if not RDKIT_AVAILABLE:
            return None
        
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            
            return Chem.MolToInchi(mol)
        except Exception:
            return None
    
    @staticmethod
    def get_inchi_key(smiles: str) -> Optional[str]:
        """InChI Key 계산"""
        if not RDKIT_AVAILABLE:
            return None
        
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            
            return Chem.MolToInchiKey(mol)
        except Exception:
            return None
    
    @staticmethod
    def round_trip_test(smiles: str) -> Tuple[bool, str]:
        """
        왕복 검증 (SMILES → mol → SMILES)
        
        Returns:
            (is_consistent, normalized_smiles)
        """
        if not RDKIT_AVAILABLE:
            return False, ""
        
        try:
            mol1 = Chem.MolFromSmiles(smiles)
            if mol1 is None:
                return False, ""
            
            norm1 = Chem.MolToSmiles(mol1)
            
            mol2 = Chem.MolFromSmiles(norm1)
            if mol2 is None:
                return False, norm1
            
            norm2 = Chem.MolToSmiles(mol2)
            
            # 두 번의 정규화가 동일하면 일관성 있음
            is_consistent = norm1 == norm2
            return is_consistent, norm2
        
        except Exception:
            return False, ""
    
    @staticmethod
    def get_warnings_summary(result: SMILESValidationResult) -> str:
        """경고 메시지 요약"""
        if not result.warnings:
            return "✓ 경고 없음"
        
        summary = "⚠️ 경고:\n"
        for warning in result.warnings:
            summary += f"  • {warning}\n"
        return summary.strip()
    
    @staticmethod
    def get_info_summary(result: SMILESValidationResult) -> str:
        """분자 정보 요약"""
        if not result.is_valid:
            return f"❌ 유효하지 않음\n오류: {result.error_message}"
        
        info = "✓ 유효한 SMILES\n"
        info += f"분자식: {SMILESValidator.get_molecular_formula(result.canonical_smiles)}\n"
        info += f"원자: {result.num_atoms}, 결합: {result.num_bonds}\n"
        info += f"분자량: {result.molecular_weight:.2f}\n"
        info += f"회전 결합: {result.num_rotatable_bonds}\n"
        
        if result.warnings:
            info += f"\n{SMILESValidator.get_warnings_summary(result)}"
        
        return info


# 테스트 코드
if __name__ == "__main__":
    test_smiles = [
        "C",  # 메탄
        "CCO",  # 에탄올
        "c1ccccc1",  # 벤젠
        "CC(=O)O",  # 아세트산
        "invalid_smiles",  # 잘못된 SMILES
    ]
    
    for smiles in test_smiles:
        result = SMILESValidator.validate_and_normalize(smiles)
        print(f"\nSMILES: {smiles}")
        print(f"유효성: {result.is_valid}")
        if result.is_valid:
            print(f"정규화: {result.normalized_smiles}")
            print(result.get_info_summary())
        else:
            print(f"오류: {result.error_message}")
