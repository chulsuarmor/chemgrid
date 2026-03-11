# Phase 4 Integration Guide

**목표**: draw.py에 Phase 4 모듈 통합

---

## 1️⃣ Imports 추가 (draw.py 상단)

```python
# === Phase 4 Advanced Features ===
try:
    from layer_logic import LassoSelectionRenderer
    LASSO_AVAILABLE = True
except ImportError:
    LASSO_AVAILABLE = False
    print("[draw.py] Lasso selection not available")

try:
    from molecule_comparator import (
        MoleculeComparator, MoleculeComparatorThread, ComparisonVisualizer
    )
    COMPARATOR_AVAILABLE = True
except ImportError:
    COMPARATOR_AVAILABLE = False
    print("[draw.py] Molecule comparator not available")

try:
    from history_manager import HistoryManager, CalculationEntry, create_entry_from_orca_result
    HISTORY_AVAILABLE = True
except ImportError:
    HISTORY_AVAILABLE = False
    print("[draw.py] History manager not available")

try:
    from batch_processor import (
        BatchProcessor, BatchProcessorThread, export_batch_results_json,
        export_batch_results_csv, generate_batch_report
    )
    BATCH_AVAILABLE = True
except ImportError:
    BATCH_AVAILABLE = False
    print("[draw.py] Batch processor not available")
```

---

## 2️⃣ ChemDrawCanvas 클래스에 속성 추가

```python
class ChemDrawCanvas(QMainWindow):
    def __init__(self):
        # ... 기존 코드 ...
        
        # === Phase 4 Objects ===
        self.lasso = LassoSelectionRenderer() if LASSO_AVAILABLE else None
        self.history = HistoryManager(Path("./orca_history")) if HISTORY_AVAILABLE else None
        self.batch_processor = BatchProcessor() if BATCH_AVAILABLE else None
        
        # UI 상태
        self.lasso_mode_active = False
        self.comparison_in_progress = False
        self.batch_in_progress = False
```

---

## 3️⃣ Lasso Selection 통합

### 마우스 이벤트 처리

```python
class ChemDrawCanvas(QMainWindow):
    def mousePressEvent(self, event):
        if self.lasso_mode_active and self.current_mode == CanvasMode.THEORY:
            # 라소 선택 시작
            if LASSO_AVAILABLE:
                self.lasso.start_lasso(QPointF(event.x(), event.y()))
                return
        
        # ... 기존 마우스 이벤트 처리 ...
    
    def mouseMoveEvent(self, event):
        if self.lasso_mode_active and self.current_mode == CanvasMode.THEORY:
            if LASSO_AVAILABLE and self.lasso.is_drawing:
                self.lasso.add_point_to_lasso(QPointF(event.x(), event.y()))
                self.update()  # 리드로우
                return
        
        # ... 기존 마우스 이벤트 처리 ...
    
    def mouseReleaseEvent(self, event):
        if self.lasso_mode_active and self.current_mode == CanvasMode.THEORY:
            if LASSO_AVAILABLE and self.lasso.is_drawing:
                if self.lasso.end_lasso(QPointF(event.x(), event.y())):
                    # 선택된 분자로 3D 팝업 트리거
                    self.on_lasso_selection_complete()
                return
        
        # ... 기존 마우스 이벤트 처리 ...
    
    def on_lasso_selection_complete(self):
        """라소 선택 완료 이벤트"""
        if not LASSO_AVAILABLE or not self.analysis:
            return
        
        # 이론적 좌표 맵 가져오기
        t_map = self.analysis.get("theory_data", {}).get("map", {})
        
        # 라소 영역 내 분자 선택
        selected_atoms, selected_bonds = self.lasso.select_molecules_in_lasso(
            self.atoms, self.bonds, self.analysis, t_map
        )
        
        print(f"[LASSO] Selected atoms: {len(selected_atoms)}, bonds: {len(selected_bonds)}")
        
        # 선택된 분자로 3D 팝업 트리거
        if PHASE_C_AVAILABLE and selected_atoms:
            smiles = self.lasso.get_selected_smiles(selected_atoms, self.atoms, self.bonds)
            if smiles:
                self.show_3d_popup(smiles)
```

### Paintbrush 통합

```python
def paintEvent(self, event):
    # ... 기존 드로잉 ...
    
    painter = QPainter(self)
    
    # Theory 레이어인 경우 라소 표시
    if self.current_mode == CanvasMode.THEORY and self.lasso_mode_active:
        if LASSO_AVAILABLE and self.lasso.is_drawing:
            self.lasso.render_lasso_overlay(painter)
        
        # 선택된 원자/결합 하이라이트
        if LASSO_AVAILABLE and self.lasso.selected_atoms:
            t_map = self.analysis.get("theory_data", {}).get("map", {})
            self.lasso.render_selection_highlight(
                painter, self.lasso.selected_atoms, 
                self.lasso.selected_bonds, t_map, self.atoms, self.bonds
            )
```

### 툴바 버튼 추가

```python
def create_toolbar(self):
    # ... 기존 툴바 ...
    
    # Phase 4 기능 버튼들
    if LASSO_AVAILABLE:
        lasso_action = QAction("🔍 Lasso Select", self)
        lasso_action.triggered.connect(self.on_lasso_mode_toggle)
        toolbar.addAction(lasso_action)
    
    if COMPARATOR_AVAILABLE:
        compare_action = QAction("🔄 Compare", self)
        compare_action.triggered.connect(self.on_compare_molecules)
        toolbar.addAction(compare_action)
    
    if HISTORY_AVAILABLE:
        history_action = QAction("📊 History", self)
        history_action.triggered.connect(self.on_show_history)
        toolbar.addAction(history_action)
    
    if BATCH_AVAILABLE:
        batch_action = QAction("⚙️ Batch", self)
        batch_action.triggered.connect(self.on_batch_processing)
        toolbar.addAction(batch_action)

def on_lasso_mode_toggle(self):
    """라소 모드 토글"""
    if self.current_mode != CanvasMode.THEORY:
        QMessageBox.warning(self, "Warning", "Lasso selection available only in Theory mode")
        return
    
    self.lasso_mode_active = not self.lasso_mode_active
    status = "Enabled" if self.lasso_mode_active else "Disabled"
    print(f"[LASSO] Mode: {status}")
```

---

## 4️⃣ Molecule Comparator 통합

```python
def on_compare_molecules(self):
    """두 분자 비교"""
    if not COMPARATOR_AVAILABLE or not self.analysis:
        return
    
    # 현재 분자의 스냅샷 생성
    smiles1 = self.current_smiles  # 또는 분석에서 추출
    formula1 = self.analysis.get("formula", "Unknown")
    
    snapshot1 = MoleculeComparator.generate_snapshot(
        smiles1, self.atoms, self.bonds, formula1, self.current_mode
    )
    
    # 비교할 분자 선택 (사용자 입력 또는 히스토리에서)
    # TODO: 분자 선택 대화창 구현
    
    # 백그라운드 비교 수행
    if snapshot1 and snapshot2:
        self.comparison_thread = MoleculeComparatorThread(snapshot1, snapshot2)
        self.comparison_thread.result.connect(self.on_comparison_complete)
        self.comparison_thread.error.connect(self.on_comparison_error)
        self.comparison_thread.progress.connect(self.on_comparison_progress)
        self.comparison_thread.start()
        self.comparison_in_progress = True

def on_comparison_complete(self, result):
    """비교 완료"""
    print(f"[COMPARATOR] Tanimoto: {result.tanimoto_similarity:.3f}")
    print(f"[COMPARATOR] Identical: {result.is_identical}")
    
    # 결과 표시 (대화창 또는 팝업)
    msg = f"""
Molecule Comparison Result
==========================
Tanimoto Similarity: {result.tanimoto_similarity:.3f}
Identical: {result.is_identical}
Atom Count Diff: {result.differences['atom_count_diff']}
Weight Diff: {result.differences['weight_diff']:.2f}
Success Rate: {result.differences.get('molecular_weight_percent', 0):.1f}%
    """
    QMessageBox.information(self, "Comparison Result", msg)
    
    # 저장
    if hasattr(result, 'to_dict'):
        import json
        with open("last_comparison.json", 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

def on_comparison_error(self, error_msg):
    QMessageBox.critical(self, "Comparison Error", error_msg)
    self.comparison_in_progress = False
```

---

## 5️⃣ History Manager 통합

```python
def on_orca_calculation_complete(self, result):
    """ORCA 계산 완료 - 히스토리 저장"""
    if not HISTORY_AVAILABLE:
        return
    
    try:
        # 스냅샷 생성
        entry = create_entry_from_orca_result(
            result, 
            self.current_smiles,
            self.analysis.get("formula", "Unknown"),
            notes=f"Calculated via {self.current_mode}"
        )
        
        # 중복 확인 (캐시 히트로 빠른 재로드 가능)
        existing = self.history.duplicate_check(self.current_smiles)
        if existing:
            print(f"[HISTORY] Cache hit! Using previous result from {existing.timestamp}")
            return
        
        # 새 항목 추가
        entry_id = self.history.add_entry(entry)
        print(f"[HISTORY] Entry saved: {entry_id}")
        
        # 통계 업데이트
        stats = self.history.get_statistics()
        print(f"[HISTORY] Total entries: {stats['total_entries']}")
        
    except Exception as e:
        print(f"[HISTORY] Error saving: {e}")

def on_show_history(self):
    """히스토리 검색/표시"""
    if not HISTORY_AVAILABLE:
        return
    
    # TODO: 히스토리 대화창 구현
    recent = self.history.get_recent(10)
    print(f"[HISTORY] Recent 10 entries:")
    for entry in recent:
        print(f"  {entry.timestamp}: {entry.formula} ({entry.method})")
    
    # CSV 내보내기
    self.history.export_to_csv("calculation_history.csv")
    print("[HISTORY] Exported to calculation_history.csv")
```

---

## 6️⃣ ORCA Batch Processor 통합

```python
def on_batch_processing(self):
    """배치 처리 시작"""
    if not BATCH_AVAILABLE:
        return
    
    # 파일 선택
    file_path, _ = QFileDialog.getOpenFileName(
        self, "Load Molecules",
        filter="JSON (*.json);;CSV (*.csv)"
    )
    
    if not file_path:
        return
    
    # 배치 프로세서 초기화
    processor = BatchProcessor()
    added = processor.add_jobs_from_file(file_path)
    print(f"[BATCH] Added {added} molecules")
    
    # 배치 실행 (백그라운드 스레드)
    batch_thread = BatchProcessorThread(processor, self.run_orca_calculation)
    batch_thread.progress.connect(self.on_batch_progress)
    batch_thread.finished.connect(self.on_batch_finished)
    batch_thread.job_failed.connect(self.on_batch_job_failed)
    batch_thread.start()
    
    self.batch_in_progress = True
    self.batch_processor = processor

def on_batch_progress(self, completed, total, percentage):
    """배치 진행률 표시"""
    print(f"[BATCH] Progress: {completed}/{total} ({percentage:.1f}%)")
    # 진행 바 업데이트
    # self.batch_progress_bar.setValue(int(percentage))

def on_batch_finished(self, summary):
    """배치 완료"""
    self.batch_in_progress = False
    
    print(f"[BATCH] Completed: {summary['completed']}/{summary['total_jobs']}")
    print(f"[BATCH] Failed: {summary['failed']}")
    print(f"[BATCH] Total time: {summary['total_time_sec']:.2f}sec")
    
    # 보고서 생성
    report = generate_batch_report(summary)
    print(report)
    
    # 결과 내보내기
    export_batch_results_json(summary, "batch_results.json")
    export_batch_results_csv(summary, "batch_results.csv")
    
    # 히스토리에 저장
    if HISTORY_AVAILABLE:
        for job_id, job_data in summary.get('results', {}).items():
            if job_data['status'] == 'completed':
                entry = CalculationEntry(
                    id=job_id,
                    timestamp=job_data.get('start_time', datetime.now().isoformat()),
                    smiles=job_data['smiles'],
                    formula=job_data['formula'],
                    method="ORCA_B3LYP",
                    basis_set="6-31G(d)",
                    charge=0,
                    multiplicity=1,
                    energy=job_data.get('result', {}).get('energy', 0.0),
                    geometry={},
                    computation_time_sec=job_data['computation_time_sec']
                )
                self.history.add_entry(entry)

def on_batch_job_failed(self, job_id, error):
    """배치 작업 실패"""
    print(f"[BATCH] Job {job_id} failed: {error}")
```

---

## 7️⃣ ORCA 계산 콜백 추가

```python
def run_orca_calculation(self, smiles):
    """
    배치 처리용 ORCA 계산 함수
    
    Args:
        smiles: SMILES 문자열
    
    Returns:
        {"energy": float, "converged": bool} 또는 None
    """
    if not hasattr(self, 'orca_thread'):
        return None
    
    try:
        # ORCA 계산 수행
        # (기존 ORCA 계산 로직 재사용)
        result = self.perform_orca_calculation(smiles)
        
        if result:
            return {
                "energy": result.energy if hasattr(result, 'energy') else 0.0,
                "converged": result.converged if hasattr(result, 'converged') else False
            }
    except:
        pass
    
    return None
```

---

## 8️⃣ 메뉴 항목 추가

```python
def create_menus(self):
    # ... 기존 메뉴 ...
    
    # Phase 4 메뉴
    phase4_menu = self.menuBar().addMenu("Phase 4")
    
    if LASSO_AVAILABLE:
        phase4_menu.addAction("Lasso Selection", self.on_lasso_mode_toggle)
    
    if COMPARATOR_AVAILABLE:
        phase4_menu.addAction("Compare Molecules", self.on_compare_molecules)
    
    if HISTORY_AVAILABLE:
        phase4_menu.addAction("Show History", self.on_show_history)
    
    if BATCH_AVAILABLE:
        phase4_menu.addAction("Batch Processing", self.on_batch_processing)
    
    phase4_menu.addSeparator()
    phase4_menu.addAction("About Phase 4", self.on_phase4_info)

def on_phase4_info(self):
    info = """
ChemDraw Pro Phase 4 - Advanced Features
========================================

1. Lasso Selection Tool
   - Free-form molecular selection in Theory layer
   - Automatic 3D popup triggering

2. Molecule Comparator
   - Tanimoto similarity scoring
   - Structural difference analysis

3. History Manager
   - Persistent calculation storage
   - Fast cache reload

4. ORCA Batch Processor
   - Sequential multi-molecule calculations
   - Automatic result export

See PHASE4_IMPLEMENTATION.md for details.
    """
    QMessageBox.information(self, "Phase 4 Features", info)
```

---

## ✅ 통합 체크리스트

- [ ] 모든 imports 추가
- [ ] ChemDrawCanvas에 Phase 4 객체 초기화
- [ ] Lasso 마우스 이벤트 처리
- [ ] Lasso paintEvent 통합
- [ ] Lasso 툴바 버튼 추가
- [ ] Comparator 백그라운드 스레드 연결
- [ ] History 저장 콜백 연결
- [ ] Batch 처리 스레드 연결
- [ ] 모든 신호-슬롯 연결 확인
- [ ] 메뉴 항목 추가
- [ ] 에러 처리 및 로깅

---

## 🧪 테스트 단계

1. **Lasso 선택 테스트**
   - Theory 레이어 진입
   - 라소 선택 버튼 클릭
   - 마우스로 자유형 경로 그리기
   - 선택된 분자 확인

2. **Comparator 테스트**
   - 두 분자 화면에 표시
   - 비교 버튼 클릭
   - 유사도 점수 확인

3. **History 테스트**
   - ORCA 계산 수행
   - 히스토리에 저장되는지 확인
   - 검색 기능 테스트
   - CSV 내보내기 확인

4. **Batch 테스트**
   - molecules.json 파일 생성
   - 배치 처리 시작
   - 진행률 표시 확인
   - 결과 내보내기 확인

---

**작성일**: 2026-02-06  
**상태**: Integration Guide  
**다음 단계**: draw.py에 위 코드 적용
