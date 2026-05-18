# molecule_comparator.py (v1.00 - Phase 4 Molecular Comparison)
"""
ChemGrid Pro Phase 4: Molecule Comparator Module
- Two-molecule SMILES comparison
- Tanimoto similarity scoring
- Structural difference visualization
- 3D popup integration

기술 제약:
- 모든 좌표: round(coord, 2)
- SMILES 표준화
- Tanimoto 지수 기반 유사도
"""

import json
import logging
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from PyQt6.QtCore import QThread, pyqtSignal, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush

logger = logging.getLogger(__name__)


@dataclass
class MoleculeSnapshot:
    """분자 스냅샷 데이터"""
    smiles: str
    formula: str
    molecular_weight: float
    num_atoms: int
    num_bonds: int
    fingerprint_bits: str  # 화학지문 (base64 인코딩)
    timestamp: str  # ISO 형식
    source_layer: str  # "Drawing" / "Lewis" / "Theory"
    geometry: Dict  # 원자 좌표 {pos_key: (x, y)}
    
    def to_dict(self):
        return asdict(self)


@dataclass
class ComparisonResult:
    """분자 비교 결과"""
    mol1_smiles: str
    mol2_smiles: str
    tanimoto_similarity: float  # 0.0 ~ 1.0
    is_identical: bool  # 동일 분자 여부
    common_substructure: Optional[str]  # 공통 부분구조
    differences: Dict  # 차이점 상세
    comparison_timestamp: str
    
    def to_dict(self):
        return asdict(self)


class MoleculeComparator:
    """
    두 분자의 구조 및 성질 비교
    """
    
    @staticmethod
    def generate_snapshot(smiles: str, atoms: Dict, bonds: Dict, 
                         formula: str, layer: str = "Theory") -> MoleculeSnapshot:
        """
        분자 스냅샷 생성
        
        Args:
            smiles: SMILES 문자열
            atoms: 원자 데이터
            bonds: 결합 데이터
            formula: 분자식
            layer: 레이어 이름
        
        Returns:
            MoleculeSnapshot
        """
        try:
            mol = Chem.MolFromSmiles(smiles)
            if not mol:
                return None
            
            # Morgan fingerprint 생성 (Tanimoto 유사도 계산용)
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=1024)
            fp_bits = fp.ToBitString()
            
            # 분자량 계산
            mw = Chem.Descriptors.MolWt(mol)
            
            # 스냅샷 생성
            snapshot = MoleculeSnapshot(
                smiles=smiles,
                formula=formula,
                molecular_weight=round(mw, 2),
                num_atoms=mol.GetNumAtoms(),
                num_bonds=mol.GetNumBonds(),
                fingerprint_bits=fp_bits,
                timestamp=datetime.now().isoformat(),
                source_layer=layer,
                geometry={str(k): (round(v[0], 2), round(v[1], 2)) 
                         for k, v in atoms.items() if isinstance(v, dict)}
            )
            
            return snapshot
        except Exception as e:
            print(f"[ERROR] snapshot generation: {e}")
            return None
    
    @staticmethod
    def calculate_similarity(snapshot1: MoleculeSnapshot, 
                           snapshot2: MoleculeSnapshot) -> float:
        """
        Tanimoto 유사도 계산 (0.0 ~ 1.0)
        
        Args:
            snapshot1, snapshot2: 비교할 분자 스냅샷
        
        Returns:
            Tanimoto 유사도 점수
        """
        try:
            fp1 = Chem.DataStructs.ExplicitBitVect(snapshot1.fingerprint_bits)
            fp2 = Chem.DataStructs.ExplicitBitVect(snapshot2.fingerprint_bits)
            
            # Morgan fingerprint로 다시 생성 (더 정확)
            mol1 = Chem.MolFromSmiles(snapshot1.smiles)
            mol2 = Chem.MolFromSmiles(snapshot2.smiles)
            
            if mol1 and mol2:
                fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2, nBits=1024)
                fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2, nBits=1024)
                similarity = DataStructs.TanimotoSimilarity(fp1, fp2)
                return round(similarity, 3)
        except Exception as e:
            logger.warning("Tanimoto similarity failed: %s", e)

        return 0.0
    
    @staticmethod
    def find_common_substructure(smiles1: str, smiles2: str) -> Optional[str]:
        """
        두 분자의 공통 부분구조 찾기
        
        Args:
            smiles1, smiles2: SMILES 문자열
        
        Returns:
            공통 부분구조 SMILES 또는 None
        """
        try:
            mol1 = Chem.MolFromSmiles(smiles1)
            mol2 = Chem.MolFromSmiles(smiles2)
            
            if not mol1 or not mol2:
                return None
            
            # 기본 공통 부분구조 (원소만)
            atoms1 = set(atom.GetSymbol() for atom in mol1.GetAtoms())
            atoms2 = set(atom.GetSymbol() for atom in mol2.GetAtoms())
            common_atoms = atoms1 & atoms2
            
            if not common_atoms:
                return None
            
            # 공통 원소로 SMILES 생성 (간단한 구현)
            # TODO: MCDLQ (Maximum Common Detailed Label Query) 사용
            
            # 원자수 기반 단순 비교
            if mol1.GetNumAtoms() == mol2.GetNumAtoms():
                return smiles1  # 동일 크기면 첫 번째 반환
            
            return None
        except Exception as e:
            logger.warning("Common substructure search failed: %s", e)
            return None
    
    @staticmethod
    def compare(snapshot1: MoleculeSnapshot, 
                snapshot2: MoleculeSnapshot) -> ComparisonResult:
        """
        두 분자 스냅샷 비교
        
        Args:
            snapshot1, snapshot2: 비교할 분자 스냅샷
        
        Returns:
            ComparisonResult
        """
        # 1. Tanimoto 유사도 계산
        tanimoto = MoleculeComparator.calculate_similarity(snapshot1, snapshot2)
        
        # 2. 동일성 판단
        is_identical = (tanimoto > 0.99) or (snapshot1.smiles == snapshot2.smiles)
        
        # 3. 공통 부분구조 찾기
        common_substructure = None
        if not is_identical:
            common_substructure = MoleculeComparator.find_common_substructure(
                snapshot1.smiles, snapshot2.smiles
            )
        
        # 4. 차이점 분석
        differences = {
            "formula_match": snapshot1.formula == snapshot2.formula,
            "atom_count_diff": abs(snapshot1.num_atoms - snapshot2.num_atoms),
            "bond_count_diff": abs(snapshot1.num_bonds - snapshot2.num_bonds),
            "weight_diff": abs(snapshot1.molecular_weight - snapshot2.molecular_weight),
            "molecular_weight_percent": (
                abs(snapshot1.molecular_weight - snapshot2.molecular_weight) /
                snapshot1.molecular_weight * 100
                if snapshot1.molecular_weight > 0 else 0
            )
        }
        
        # 5. 결과 생성
        result = ComparisonResult(
            mol1_smiles=snapshot1.smiles,
            mol2_smiles=snapshot2.smiles,
            tanimoto_similarity=tanimoto,
            is_identical=is_identical,
            common_substructure=common_substructure,
            differences=differences,
            comparison_timestamp=datetime.now().isoformat()
        )
        
        return result


class MoleculeComparatorThread(QThread):
    """
    비교 계산을 위한 백그라운드 스레드
    
    Signals:
        result: ComparisonResult 발출
        error: 에러 메시지 발출
    """
    
    result = pyqtSignal(object)  # ComparisonResult
    error = pyqtSignal(str)
    progress = pyqtSignal(int)  # 진행률 (0-100)
    
    def __init__(self, snapshot1: MoleculeSnapshot, snapshot2: MoleculeSnapshot):
        super().__init__()
        self.snapshot1 = snapshot1
        self.snapshot2 = snapshot2
    
    def run(self):
        """비교 실행"""
        try:
            self.progress.emit(25)
            
            # 유사도 계산
            tanimoto = MoleculeComparator.calculate_similarity(
                self.snapshot1, self.snapshot2
            )
            self.progress.emit(50)
            
            # 공통 부분구조 찾기
            common = MoleculeComparator.find_common_substructure(
                self.snapshot1.smiles, self.snapshot2.smiles
            )
            self.progress.emit(75)
            
            # 전체 비교
            result = MoleculeComparator.compare(self.snapshot1, self.snapshot2)
            self.progress.emit(100)
            
            self.result.emit(result)
        except Exception as e:
            self.error.emit(f"Comparison error: {str(e)}")


class ComparisonVisualizer:
    """
    비교 결과 시각화
    """
    
    @staticmethod
    def draw_similarity_bar(painter: QPainter, rect, similarity: float, 
                           label: str = "Tanimoto Similarity"):
        """
        유사도 막대 그래프 그리기
        
        Args:
            painter: QPainter
            rect: 그리는 위치 QRect
            similarity: 유사도 (0.0 ~ 1.0)
            label: 레이블
        """
        painter.save()
        
        # 배경 박스
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.setBrush(QColor(200, 200, 200))
        painter.drawRect(rect)
        
        # 유사도 바 (색상: 빨강 → 노랑 → 초록)
        bar_width = rect.width() * similarity
        if similarity < 0.5:
            color = QColor(255, int(255 * similarity / 0.5), 0)  # 빨강 → 노랑
        else:
            color = QColor(int(255 * (1 - similarity)), 255, 0)  # 노랑 → 초록
        
        painter.fillRect(rect.x(), rect.y(), bar_width, rect.height(), color)
        
        # 텍스트 (퍼센트)
        painter.setFont(painter.font())
        painter.setPen(QColor(0, 0, 0))
        text = f"{label}: {similarity*100:.1f}%"
        painter.drawText(rect, 4, text)  # 4 = Qt.AlignCenter
        
        painter.restore()
    
    @staticmethod
    def draw_comparison_table(painter: QPainter, x: int, y: int, 
                             comparison_result: ComparisonResult):
        """
        비교 결과 테이블 그리기
        
        Args:
            painter: QPainter
            x, y: 시작 좌표
            comparison_result: ComparisonResult
        """
        painter.save()
        
        # 테이블 제목
        painter.setFont(painter.font())
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(x, y, "Molecule Comparison Result")
        
        # 결과 텍스트
        y_offset = y + 25
        lines = [
            f"Tanimoto: {comparison_result.tanimoto_similarity:.3f}",
            f"Identical: {'Yes' if comparison_result.is_identical else 'No'}",
            f"Atom Count Diff: {comparison_result.differences['atom_count_diff']}",
            f"Weight Diff: {comparison_result.differences['weight_diff']:.2f}",
        ]
        
        for line in lines:
            painter.drawText(x, y_offset, line)
            y_offset += 20
        
        painter.restore()


def save_comparison_to_json(comparison_result: ComparisonResult, 
                           filepath: str) -> bool:
    """
    비교 결과를 JSON 파일로 저장
    
    Args:
        comparison_result: ComparisonResult
        filepath: 저장 경로
    
    Returns:
        성공 여부
    """
    try:
        data = comparison_result.to_dict()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[INFO] Comparison saved: {filepath}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save comparison: {e}")
        return False


def load_comparison_from_json(filepath: str) -> Optional[ComparisonResult]:
    """
    JSON 파일에서 비교 결과 로드
    
    Args:
        filepath: 로드 경로
    
    Returns:
        ComparisonResult 또는 None
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return ComparisonResult(**data)
    except Exception as e:
        print(f"[ERROR] Failed to load comparison: {e}")
        return None
