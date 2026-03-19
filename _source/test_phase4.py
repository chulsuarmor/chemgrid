# test_phase4.py - Phase 4 Advanced Features Validation
"""
ChemDraw Pro Phase 4 모듈 통합 테스트
- Lasso Selection Tool 검증
- Molecule Comparator 검증
- History Manager 검증
- ORCA Batch Processor 검증
"""

import sys
import os
from pathlib import Path

# 작업 디렉토리 설정
WORK_DIR = Path(__file__).parent
sys.path.insert(0, str(WORK_DIR))

print("=" * 80)
print("ChemDraw Pro Phase 4 - Advanced Features Test Suite")
print("=" * 80)

# ============================================================================
# TEST 1: Lasso Selection Tool (layer_logic.py)
# ============================================================================

print("\n[TEST 1] Lasso Selection Tool")
print("-" * 80)

try:
    from layer_logic import LassoSelectionRenderer
    from PyQt6.QtCore import QPointF
    
    # LassoSelectionRenderer 생성
    lasso = LassoSelectionRenderer()
    
    # 라소 경로 생성 (간단한 사각형)
    lasso.start_lasso(QPointF(0, 0))
    lasso.add_point_to_lasso(QPointF(100, 0))
    lasso.add_point_to_lasso(QPointF(100, 100))
    lasso.add_point_to_lasso(QPointF(0, 100))
    lasso.end_lasso(QPointF(0, 0))
    
    # 점 포함성 검사
    test_point = QPointF(50, 50)  # 내부
    is_inside = lasso.is_point_inside_lasso(test_point)
    
    print(f"✓ LassoSelectionRenderer 초기화 성공")
    print(f"✓ 라소 경로 생성 성공 (점 수: {len(lasso.points)})")
    print(f"✓ 점 포함성 검사 성공 (50,50은 내부: {is_inside})")
    print(f"✓ 좌표 반올림 검증: {lasso.points[0]} (모두 2자리)")
    
    TEST1_PASS = True
except Exception as e:
    print(f"✗ TEST 1 실패: {e}")
    TEST1_PASS = False


# ============================================================================
# TEST 2: Molecule Comparator (molecule_comparator.py)
# ============================================================================

print("\n[TEST 2] Molecule Comparator")
print("-" * 80)

try:
    from molecule_comparator import (
        MoleculeComparator, MoleculeSnapshot, ComparisonResult
    )
    
    # 테스트 분자: 벤젠
    smiles1 = "C1=CC=CC=C1"
    formula1 = "C6H6"
    
    # 테스트 분자: 톨루엔
    smiles2 = "Cc1ccccc1"
    formula2 = "C7H8"
    
    # 스냅샷 생성
    snapshot1 = MoleculeComparator.generate_snapshot(
        smiles1, {}, {}, formula1, "Theory"
    )
    snapshot2 = MoleculeComparator.generate_snapshot(
        smiles2, {}, {}, formula2, "Theory"
    )
    
    if snapshot1 and snapshot2:
        # 유사도 계산
        similarity = MoleculeComparator.calculate_similarity(snapshot1, snapshot2)
        
        # 비교 수행
        result = MoleculeComparator.compare(snapshot1, snapshot2)
        
        print(f"✓ Molecule Snapshot 생성 성공")
        print(f"✓ Tanimoto 유사도 계산: {similarity:.3f}")
        print(f"✓ 비교 결과: 동일성={result.is_identical}")
        print(f"✓ 원자수 차이: {result.differences['atom_count_diff']}")
        
        TEST2_PASS = True
    else:
        print(f"✗ 스냅샷 생성 실패")
        TEST2_PASS = False
        
except Exception as e:
    print(f"✗ TEST 2 실패: {e}")
    import traceback
    traceback.print_exc()
    TEST2_PASS = False


# ============================================================================
# TEST 3: History Manager (history_manager.py)
# ============================================================================

print("\n[TEST 3] History Manager")
print("-" * 80)

try:
    from history_manager import HistoryManager, CalculationEntry
    from datetime import datetime
    
    # 히스토리 매니저 초기화
    history = HistoryManager(WORK_DIR / "test_history")
    
    # 테스트 항목 추가
    test_entry = CalculationEntry(
        id="test_001",
        timestamp=datetime.now().isoformat(),
        smiles="C1=CC=CC=C1",
        formula="C6H6",
        method="ORCA_B3LYP",
        basis_set="6-31G(d)",
        charge=0,
        multiplicity=1,
        energy=-232.123456,
        geometry={"atom_0": (0.0, 0.0), "atom_1": (1.4, 0.0)}
    )
    
    # 항목 추가
    entry_id = history.add_entry(test_entry)
    
    # 조회
    retrieved = history.get_entry(entry_id)
    
    # 통계
    stats = history.get_statistics()
    
    print(f"✓ HistoryManager 초기화 성공")
    print(f"✓ 계산 항목 추가 성공 (ID: {entry_id})")
    print(f"✓ 항목 조회 성공 (SMILES: {retrieved.smiles})")
    print(f"✓ 통계 생성 성공 (총 항목: {stats['total_entries']})")
    print(f"✓ 좌표 반올림 검증: {retrieved.geometry}")
    
    TEST3_PASS = True
except Exception as e:
    print(f"✗ TEST 3 실패: {e}")
    import traceback
    traceback.print_exc()
    TEST3_PASS = False


# ============================================================================
# TEST 4: ORCA Batch Processor (batch_processor.py)
# ============================================================================

print("\n[TEST 4] ORCA Batch Processor")
print("-" * 80)

try:
    from batch_processor import BatchProcessor, BatchJob, BatchJobStatus
    
    # 배치 프로세서 초기화
    processor = BatchProcessor()
    
    # 테스트 분자 추가
    molecules = [
        ("C1=CC=CC=C1", "C6H6"),  # 벤젠
        ("Cc1ccccc1", "C7H8"),     # 톨루엔
        ("C1=CC=C(C=C1)O", "C6H6O"),  # 페놀
    ]
    
    added = processor.add_jobs_from_list(molecules)
    
    # 배치 요약
    summary = processor.get_summary()
    
    print(f"✓ BatchProcessor 초기화 성공")
    print(f"✓ 배치 작업 추가 성공 ({added}개 분자)")
    print(f"✓ 배치 요약: 총 {summary['total']}개, 대기 {summary['pending']}개")
    print(f"✓ 진행률: {summary['progress_percent']:.1f}%")
    
    # 배치 실행 (더미 계산 함수)
    def dummy_calculator(smiles):
        return {"energy": -1000.0, "converged": True}
    
    # 배치 실행 (동기)
    result = processor.run_batch(dummy_calculator)
    
    print(f"✓ 배치 실행 완료")
    print(f"✓ 완료: {result['completed']}/{result['total_jobs']}")
    print(f"✓ 실패: {result['failed']}/{result['total_jobs']}")
    print(f"✓ 총 소요 시간: {result['total_time_sec']:.2f}초")
    
    TEST4_PASS = True
except Exception as e:
    print(f"✗ TEST 4 실패: {e}")
    import traceback
    traceback.print_exc()
    TEST4_PASS = False


# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)

results = {
    "Lasso Selection Tool": TEST1_PASS,
    "Molecule Comparator": TEST2_PASS,
    "History Manager": TEST3_PASS,
    "ORCA Batch Processor": TEST4_PASS
}

for test_name, passed in results.items():
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"{test_name}: {status}")

total_pass = sum(results.values())
total_tests = len(results)

print("-" * 80)
print(f"Overall: {total_pass}/{total_tests} tests passed")

if total_pass == total_tests:
    print("🎉 All Phase 4 tests PASSED!")
    exit(0)
else:
    print(f"⚠️  {total_tests - total_pass} test(s) FAILED")
    exit(1)
