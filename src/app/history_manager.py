# history_manager.py (v1.00 - Phase 4 Calculation History)
"""
ChemGrid Pro Phase 4: Calculation History Manager
- JSON-based history storage with timestamps
- ORCA result caching for fast reload
- Search and filter by date/formula/method

기술 제약:
- 모든 좌표: round(coord, 2)
- ISO 8601 타임스탬프
- 메모리 효율적 캐시
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime
from collections import OrderedDict


@dataclass
class CalculationEntry:
    """계산 히스토리 항목"""
    id: str  # 고유 ID (타임스탐프 기반)
    timestamp: str  # ISO 8601
    smiles: str
    formula: str
    method: str  # "ORCA_B3LYP" 등
    basis_set: str  # "6-31G(d)" 등
    charge: int
    multiplicity: int
    energy: float  # 하트리 단위
    geometry: Dict[str, Tuple[float, float]]  # {pos_key: (x, y)}
    dipole_moment: Optional[float] = None
    homo_lumo_gap: Optional[float] = None
    convergence_status: str = "converged"
    computation_time_sec: float = 0.0
    notes: str = ""
    
    def to_dict(self):
        d = asdict(self)
        # Tuple을 리스트로 변환 (JSON 직렬화)
        d['geometry'] = {k: list(v) for k, v in d['geometry'].items()}
        return d
    
    @classmethod
    def from_dict(cls, data):
        """딕셔너리에서 객체 생성"""
        # 리스트를 Tuple로 변환
        if 'geometry' in data:
            data['geometry'] = {k: tuple(v) for k, v in data['geometry'].items()}
        return cls(**data)


class HistoryManager:
    """
    계산 히스토리 관리
    - JSON 파일 저장/로드
    - 인메모리 캐시
    - 검색 및 필터링
    """
    
    def __init__(self, history_dir: str = None):
        """
        HistoryManager 초기화
        
        Args:
            history_dir: 히스토리 저장 디렉토리 경로
        """
        self.history_dir = Path(history_dir or "./orca_history")
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        self.history_file = self.history_dir / "calculation_history.json"
        self.cache_file = self.history_dir / "cache.json"
        
        # 인메모리 캐시 (LRU: 최근 100개)
        self.cache = OrderedDict()
        self.max_cache_size = 100
        
        # 히스토리 로드
        self.entries = []
        self.load_from_file()
    
    def load_from_file(self):
        """히스토리 파일에서 로드"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.entries = [CalculationEntry.from_dict(e) for e in data]
                print(f"[INFO] Loaded {len(self.entries)} history entries")
            
            # 캐시 로드
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    self.cache = OrderedDict(cache_data)
                print(f"[INFO] Loaded {len(self.cache)} cache entries")
        except Exception as e:
            print(f"[WARNING] Failed to load history: {e}")
    
    def save_to_file(self):
        """현재 히스토리를 파일에 저장"""
        try:
            # 히스토리 저장
            data = [e.to_dict() for e in self.entries]
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # 캐시 저장
            cache_data = dict(self.cache)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            print(f"[INFO] History saved: {self.history_file}")
        except Exception as e:
            print(f"[ERROR] Failed to save history: {e}")
    
    def add_entry(self, entry: CalculationEntry) -> str:
        """
        새 계산 항목 추가
        
        Args:
            entry: CalculationEntry
        
        Returns:
            생성된 항목 ID
        """
        # ID 생성 (타임스탐프 기반)
        if not entry.id:
            entry.id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:23]
        
        self.entries.append(entry)
        
        # 캐시에도 추가
        self.cache[entry.id] = entry.to_dict()
        if len(self.cache) > self.max_cache_size:
            self.cache.popitem(last=False)  # FIFO 제거
        
        self.save_to_file()
        print(f"[INFO] Added history entry: {entry.id}")
        
        return entry.id
    
    def get_entry(self, entry_id: str) -> Optional[CalculationEntry]:
        """
        ID로 항목 조회
        
        Args:
            entry_id: 항목 ID
        
        Returns:
            CalculationEntry 또는 None
        """
        # 캐시 확인
        if entry_id in self.cache:
            return CalculationEntry.from_dict(self.cache[entry_id])
        
        # 전체 히스토리에서 검색
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        
        return None
    
    def search_by_formula(self, formula: str) -> List[CalculationEntry]:
        """
        분자식으로 검색
        
        Args:
            formula: 분자식 (예: "C6H6")
        
        Returns:
            일치하는 항목 리스트
        """
        return [e for e in self.entries if formula.lower() in e.formula.lower()]
    
    def search_by_method(self, method: str) -> List[CalculationEntry]:
        """
        계산 방법으로 검색
        
        Args:
            method: 방법 (예: "ORCA_B3LYP")
        
        Returns:
            일치하는 항목 리스트
        """
        return [e for e in self.entries if method.lower() in e.method.lower()]
    
    def search_by_date_range(self, start_date: str, end_date: str) -> List[CalculationEntry]:
        """
        날짜 범위로 검색
        
        Args:
            start_date: ISO 8601 형식 (예: "2026-02-06T10:00:00")
            end_date: ISO 8601 형식
        
        Returns:
            범위 내 항목 리스트
        """
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        results = []
        for e in self.entries:
            try:
                entry_time = datetime.fromisoformat(e.timestamp)
                if start <= entry_time <= end:
                    results.append(e)
            except:
                pass
        
        return results
    
    def get_recent(self, limit: int = 10) -> List[CalculationEntry]:
        """
        최근 항목 조회
        
        Args:
            limit: 조회 개수
        
        Returns:
            최근 항목 리스트
        """
        return sorted(self.entries, key=lambda e: e.timestamp, reverse=True)[:limit]
    
    def get_statistics(self) -> Dict:
        """
        히스토리 통계
        
        Returns:
            통계 딕셔너리
        """
        if not self.entries:
            return {
                "total_entries": 0,
                "unique_formulas": 0,
                "methods": [],
                "avg_energy": 0.0,
                "total_computation_time": 0.0
            }
        
        methods = set(e.method for e in self.entries)
        formulas = set(e.formula for e in self.entries)
        energies = [e.energy for e in self.entries if e.energy]
        times = [e.computation_time_sec for e in self.entries]
        
        stats = {
            "total_entries": len(self.entries),
            "unique_formulas": len(formulas),
            "methods": list(methods),
            "avg_energy": sum(energies) / len(energies) if energies else 0.0,
            "total_computation_time": sum(times)
        }
        
        return stats
    
    def export_to_csv(self, filepath: str) -> bool:
        """
        히스토리를 CSV로 내보내기
        
        Args:
            filepath: 저장 경로
        
        Returns:
            성공 여부
        """
        try:
            import csv
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'id', 'timestamp', 'smiles', 'formula', 'method',
                    'basis_set', 'energy', 'convergence_status'
                ])
                writer.writeheader()
                
                for entry in self.entries:
                    writer.writerow({
                        'id': entry.id,
                        'timestamp': entry.timestamp,
                        'smiles': entry.smiles,
                        'formula': entry.formula,
                        'method': entry.method,
                        'basis_set': entry.basis_set,
                        'energy': round(entry.energy, 6),
                        'convergence_status': entry.convergence_status
                    })
            
            print(f"[INFO] Exported to CSV: {filepath}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to export CSV: {e}")
            return False
    
    def clear_old_entries(self, days: int = 30) -> int:
        """
        오래된 항목 제거
        
        Args:
            days: 몇 일 이상 된 항목 제거
        
        Returns:
            제거된 항목 수
        """
        cutoff_time = datetime.now().replace(microsecond=0) - \
                      __import__('datetime').timedelta(days=days)
        
        removed = 0
        original_count = len(self.entries)
        
        self.entries = [
            e for e in self.entries
            if datetime.fromisoformat(e.timestamp) > cutoff_time
        ]
        
        removed = original_count - len(self.entries)
        
        if removed > 0:
            self.save_to_file()
            print(f"[INFO] Removed {removed} old entries")
        
        return removed
    
    def duplicate_check(self, smiles: str) -> Optional[CalculationEntry]:
        """
        동일한 SMILES의 계산 결과가 있는지 확인
        (캐시 히트로 빠른 재로드 가능)
        
        Args:
            smiles: SMILES 문자열
        
        Returns:
            기존 항목 또는 None
        """
        for entry in reversed(self.entries):  # 최근 것부터
            if entry.smiles == smiles:
                return entry
        
        return None
    
    def get_cache_info(self) -> Dict:
        """
        캐시 정보 조회
        
        Returns:
            캐시 통계
        """
        return {
            "cache_size": len(self.cache),
            "max_size": self.max_cache_size,
            "cache_usage": f"{len(self.cache) / self.max_cache_size * 100:.1f}%"
        }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_entry_from_orca_result(orca_result, smiles: str, formula: str,
                                 notes: str = "") -> CalculationEntry:
    """
    ORCA 계산 결과에서 HistoryEntry 생성
    
    Args:
        orca_result: OrcaCalculationResult
        smiles: SMILES 문자열
        formula: 분자식
        notes: 추가 메모
    
    Returns:
        CalculationEntry
    """
    # 좌표 변환
    geometry = {}
    if hasattr(orca_result, 'geometry'):
        for atom_idx, coords in orca_result.geometry.items():
            # (x, y) 좌표로 변환 (2D 표현)
            key = f"atom_{atom_idx}"
            geometry[key] = (round(coords[0], 2), round(coords[1], 2))
    
    entry = CalculationEntry(
        id="",  # auto-generated
        timestamp=datetime.now().isoformat(),
        smiles=smiles,
        formula=formula,
        method="ORCA_B3LYP",
        basis_set="6-31G(d)",
        charge=0,
        multiplicity=1,
        energy=orca_result.energy if hasattr(orca_result, 'energy') else 0.0,
        geometry=geometry,
        convergence_status="converged" if orca_result.converged else "unconverged",
        computation_time_sec=orca_result.computation_time if hasattr(orca_result, 'computation_time') else 0.0,
        notes=notes
    )
    
    return entry


def backup_history(history_dir: str, backup_dir: str = None) -> bool:
    """
    히스토리 백업 생성
    
    Args:
        history_dir: 원본 디렉토리
        backup_dir: 백업 디렉토리 (기본값: history_dir/backups/)
    
    Returns:
        성공 여부
    """
    try:
        import shutil
        
        if backup_dir is None:
            backup_dir = os.path.join(history_dir, "backups")
        
        Path(backup_dir).mkdir(parents=True, exist_ok=True)
        
        # 백업 파일 이름 (타임스탐프)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"history_backup_{timestamp}.json")
        
        history_file = os.path.join(history_dir, "calculation_history.json")
        if os.path.exists(history_file):
            shutil.copy2(history_file, backup_file)
            print(f"[INFO] Backup created: {backup_file}")
            return True
    except Exception as e:
        print(f"[ERROR] Backup failed: {e}")
    
    return False
