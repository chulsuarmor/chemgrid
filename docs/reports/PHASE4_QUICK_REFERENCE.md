# Phase 4 Quick Reference Guide

**목적**: 개발자를 위한 빠른 API 참조

---

## 🎯 1. Lasso Selection Tool

**파일**: `layer_logic.py`

**클래스**: `LassoSelectionRenderer`

### 기본 사용법

```python
from layer_logic import LassoSelectionRenderer
from PyQt6.QtCore import QPointF

# 1. 인스턴스 생성
lasso = LassoSelectionRenderer()

# 2. 사용자 마우스 이벤트 처리
def on_mouse_press(point):
    lasso.start_lasso(point)

def on_mouse_move(point):
    if lasso.is_drawing:
        lasso.add_point_to_lasso(point)

def on_mouse_release(point):
    if lasso.end_lasso(point):
        atoms, bonds = lasso.select_molecules_in_lasso(
            atoms, bonds, analysis, t_map
        )

# 3. 렌더링
def on_paint(painter):
    if lasso.is_drawing:
        lasso.render_lasso_overlay(painter, alpha=0.3)
    
    if lasso.selected_atoms:
        lasso.render_selection_highlight(
            painter, lasso.selected_atoms, 
            lasso.selected_bonds, t_map, atoms, bonds
        )
```

### 주요 속성

```python
lasso.lasso_path         # QPainterPath: 그린 경로
lasso.points             # [(x, y), ...]: 경로상의 점들
lasso.selected_atoms     # set: 선택된 원자
lasso.selected_bonds     # set: 선택된 결합
lasso.is_drawing         # bool: 그리는 중인지
```

### 핵심 메서드

| 메서드 | 반환 | 설명 |
|--------|------|------|
| `start_lasso(point)` | - | 라소 시작 |
| `add_point_to_lasso(point)` | - | 점 추가 |
| `end_lasso(point)` | bool | 라소 종료, 유효성 반환 |
| `is_point_inside_lasso(point)` | bool | Ray casting 검사 |
| `select_molecules_in_lasso(...)` | tuple | (atoms, bonds) 반환 |
| `render_lasso_overlay(painter, alpha)` | - | 경로 표시 |
| `render_selection_highlight(...)` | - | 선택 하이라이트 |
| `get_selected_smiles(...)` | str | SMILES 추출 |
| `clear_selection()` | - | 선택 제거 |

---

## 🔄 2. Molecule Comparator

**파일**: `molecule_comparator.py`

**클래스**: `MoleculeComparator`, `MoleculeComparatorThread`

### 동기식 사용

```python
from molecule_comparator import MoleculeComparator

# 스냅샷 생성
snap1 = MoleculeComparator.generate_snapshot(
    "C1=CC=CC=C1", atoms, bonds, "C6H6", "Theory"
)
snap2 = MoleculeComparator.generate_snapshot(
    "Cc1ccccc1", atoms, bonds, "C7H8", "Theory"
)

# 비교
result = MoleculeComparator.compare(snap1, snap2)

print(f"Similarity: {result.tanimoto_similarity:.3f}")
print(f"Identical: {result.is_identical}")
```

### 비동기식 사용 (QThread)

```python
from molecule_comparator import MoleculeComparatorThread

thread = MoleculeComparatorThread(snap1, snap2)
thread.result.connect(on_comparison_done)
thread.error.connect(on_comparison_error)
thread.progress.connect(on_progress)
thread.start()

def on_comparison_done(result):
    print(f"Tanimoto: {result.tanimoto_similarity:.3f}")
```

### 저장/로드

```python
from molecule_comparator import save_comparison_to_json, load_comparison_from_json

# 저장
save_comparison_to_json(result, "comparison.json")

# 로드
result = load_comparison_from_json("comparison.json")
```

### ComparisonResult 필드

```python
result.mol1_smiles              # str
result.mol2_smiles              # str
result.tanimoto_similarity      # float (0.0 ~ 1.0)
result.is_identical             # bool
result.common_substructure      # str or None
result.differences = {
    'formula_match': bool,
    'atom_count_diff': int,
    'bond_count_diff': int,
    'weight_diff': float,
    'molecular_weight_percent': float
}
result.comparison_timestamp     # str (ISO 8601)
```

---

## 📊 3. History Manager

**파일**: `history_manager.py`

**클래스**: `HistoryManager`, `CalculationEntry`

### 기본 사용법

```python
from history_manager import HistoryManager, CalculationEntry
from datetime import datetime

# 초기화
history = HistoryManager("./orca_history")

# 항목 생성
entry = CalculationEntry(
    id="",  # auto-generated
    timestamp=datetime.now().isoformat(),
    smiles="C1=CC=CC=C1",
    formula="C6H6",
    method="ORCA_B3LYP",
    basis_set="6-31G(d)",
    charge=0,
    multiplicity=1,
    energy=-232.123456,
    geometry={"atom_0": (0.0, 0.0)},
    computation_time_sec=123.45
)

# 추가
entry_id = history.add_entry(entry)
```

### 검색 방법

```python
# 분자식으로 검색
results = history.search_by_formula("C6H6")

# 방법으로 검색
results = history.search_by_method("ORCA_B3LYP")

# 날짜 범위로 검색
from datetime import datetime, timedelta
yesterday = (datetime.now() - timedelta(days=1)).isoformat()
today = datetime.now().isoformat()
results = history.search_by_date_range(yesterday, today)

# 최근 항목
recent = history.get_recent(10)

# ID로 조회
entry = history.get_entry("entry_id")

# 중복 확인 (빠른 캐시 재로드)
existing = history.duplicate_check("C1=CC=CC=C1")
```

### 내보내기 및 관리

```python
# CSV 내보내기
history.export_to_csv("history.csv")

# 통계
stats = history.get_statistics()
print(f"Total: {stats['total_entries']}")
print(f"Methods: {stats['methods']}")

# 캐시 정보
cache_info = history.get_cache_info()
print(f"Cache: {cache_info['cache_usage']}")

# 오래된 항목 제거 (30일 이상)
removed = history.clear_old_entries(days=30)

# 백업
from history_manager import backup_history
backup_history("./orca_history")
```

### ORCA 계산 연동

```python
from history_manager import create_entry_from_orca_result

# ORCA 계산 후
orca_result = perform_orca_calculation(smiles)

# Entry 생성
entry = create_entry_from_orca_result(
    orca_result, 
    "C1=CC=CC=C1", 
    "C6H6",
    notes="Benzene test"
)

# 저장
history.add_entry(entry)
```

---

## ⚙️ 4. ORCA Batch Processor

**파일**: `batch_processor.py`

**클래스**: `BatchProcessor`, `BatchProcessorThread`, `BatchJob`

### 동기식 실행

```python
from batch_processor import BatchProcessor

# 프로세서 생성
processor = BatchProcessor()

# 분자 추가
processor.add_job("C1=CC=CC=C1", "C6H6")
processor.add_job("Cc1ccccc1", "C7H8")

# 또는 파일에서
processor.add_jobs_from_file("molecules.json")  # JSON or CSV

# 계산 함수 정의
def orca_calculator(smiles):
    # ORCA 계산 수행
    return {"energy": -232.123, "converged": True}

# 실행
summary = processor.run_batch(orca_calculator)

# 결과
print(f"Completed: {summary['completed']}/{summary['total_jobs']}")
print(f"Time: {summary['total_time_sec']:.2f} sec")
```

### 비동기식 실행 (QThread)

```python
from batch_processor import BatchProcessorThread

thread = BatchProcessorThread(processor, orca_calculator)
thread.progress.connect(on_progress)
thread.finished.connect(on_finished)
thread.job_failed.connect(on_job_failed)
thread.start()

def on_progress(completed, total, percentage):
    print(f"Progress: {percentage:.1f}%")

def on_finished(summary):
    print(f"Done: {summary['completed']}/{summary['total_jobs']}")
```

### 입력 파일 형식

**JSON** (molecules.json):
```json
{
  "molecules": [
    {"smiles": "C1=CC=CC=C1", "formula": "C6H6"},
    {"smiles": "Cc1ccccc1", "formula": "C7H8"},
    {"smiles": "C1=CC=C(C=C1)O", "formula": "C6H6O"}
  ]
}
```

**CSV** (molecules.csv):
```csv
smiles,formula
C1=CC=CC=C1,C6H6
Cc1ccccc1,C7H8
C1=CC=C(C=C1)O,C6H6O
```

### 내보내기

```python
from batch_processor import (
    export_batch_results_json,
    export_batch_results_csv,
    generate_batch_report
)

# JSON 내보내기
export_batch_results_json(summary, "batch_results.json")

# CSV 내보내기
export_batch_results_csv(summary, "batch_results.csv")

# 보고서 생성
report = generate_batch_report(summary)
print(report)
```

### BatchJob 상태

```python
from batch_processor import BatchJobStatus

# 가능한 상태
BatchJobStatus.PENDING     # 대기 중
BatchJobStatus.RUNNING     # 실행 중
BatchJobStatus.COMPLETED   # 완료
BatchJobStatus.FAILED      # 실패
BatchJobStatus.CANCELLED   # 취소됨
```

### BatchJob 속성

```python
job.id                      # str
job.smiles                  # str
job.formula                 # str
job.status                  # str (BatchJobStatus)
job.result                  # dict or None
job.error_message           # str
job.start_time              # str (ISO 8601)
job.end_time                # str (ISO 8601)
job.computation_time_sec    # float
```

---

## 🔌 통합 예제

### 완전한 워크플로우

```python
# 1. Lasso로 분자 선택
from layer_logic import LassoSelectionRenderer
lasso = LassoSelectionRenderer()
# ... 마우스 이벤트 처리 ...
atoms, bonds = lasso.select_molecules_in_lasso(...)

# 2. 선택된 분자 비교
from molecule_comparator import MoleculeComparator
snap1 = MoleculeComparator.generate_snapshot(
    smiles1, atoms, bonds, formula1, "Theory"
)
snap2 = MoleculeComparator.generate_snapshot(
    smiles2, atoms, bonds, formula2, "Theory"
)
result = MoleculeComparator.compare(snap1, snap2)

# 3. 계산 히스토리 저장
from history_manager import HistoryManager, CalculationEntry
history = HistoryManager()
entry = CalculationEntry(
    id="", timestamp=datetime.now().isoformat(),
    smiles=smiles1, formula=formula1,
    method="ORCA_B3LYP", basis_set="6-31G(d)",
    charge=0, multiplicity=1, energy=-232.123,
    geometry={}, computation_time_sec=123.45
)
history.add_entry(entry)

# 4. 배치 처리
from batch_processor import BatchProcessor
processor = BatchProcessor()
processor.add_jobs_from_file("molecules.json")
summary = processor.run_batch(orca_calculator)
```

---

## 📋 체크리스트

### Lasso Selection
- [ ] `LassoSelectionRenderer` import
- [ ] Mouse events 연결
- [ ] paintEvent 통합
- [ ] 3D popup trigger

### Molecule Comparator
- [ ] `MoleculeComparator` import
- [ ] snapshots 생성
- [ ] `MoleculeComparatorThread` 연결
- [ ] 결과 표시

### History Manager
- [ ] `HistoryManager` 초기화
- [ ] ORCA 계산 후 저장
- [ ] 검색 기능 테스트
- [ ] CSV 내보내기

### Batch Processor
- [ ] `BatchProcessor` 생성
- [ ] 입력 파일 로드
- [ ] 계산 함수 연결
- [ ] 결과 내보내기

---

## 🐛 일반적인 문제 해결

### ImportError: No module named 'molecule_comparator'

```python
# 확인
import sys
print(sys.path)

# 파일이 같은 디렉토리에 있는지 확인
import os
print(os.listdir('.'))
```

### QThread 신호 연결 안 됨

```python
# 신호는 QObject에서만 가능
# BatchProcessor와 MoleculeComparatorThread는 QObject/QThread 상속

from batch_processor import BatchProcessorThread
thread = BatchProcessorThread(processor)
thread.result.connect(callback)  # OK
```

### 좌표 반올림 문제

```python
# 모든 좌표는 2자리로 반올림
coord = (1.23456, 2.34567)
rounded = (round(coord[0], 2), round(coord[1], 2))
# (1.23, 2.35)
```

### JSON 직렬화 실패

```python
# Tuple을 리스트로 변환 필요
geometry = {"atom_0": [0.0, 1.4]}  # 리스트
json.dumps({"geometry": geometry})  # OK
```

---

## 🚀 유용한 팁

1. **캐시 히트 확인**:
   ```python
   existing = history.duplicate_check(smiles)
   if existing:
       # 계산 스킵, 기존 결과 사용
   ```

2. **배치 취소**:
   ```python
   processor.cancel_batch()
   ```

3. **진행률 모니터링**:
   ```python
   processor.progress.connect(lambda c, t, p: print(f"{p:.1f}%"))
   ```

4. **에러 핸들링**:
   ```python
   thread.error.connect(lambda msg: print(f"Error: {msg}"))
   ```

5. **성능 최적화**:
   - 배치: 100개 이상은 병렬 처리 검토
   - 비교: fingerprint 캐싱
   - 히스토리: 30일 이상 오래된 항목 정기 제거

---

## 📚 관련 문서

- `PHASE4_IMPLEMENTATION.md` - 상세 기능
- `PHASE4_INTEGRATION_GUIDE.md` - 통합 가이드
- `PHASE4_COMPLETION_REPORT.md` - 완료 보고서
- `test_phase4.py` - 통합 테스트

---

**작성**: 2026-02-06  
**버전**: Phase 4 v1.0  
**상태**: ✅ Ready
