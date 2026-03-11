# batch_processor.py (v1.00 - Phase 4 ORCA Batch Processing)
"""
ChemGrid Pro Phase 4: ORCA Batch Processor
- Sequential calculation of multiple molecules
- Progress tracking and cancellation
- Automatic result export (JSON, CSV)

기술 제약:
- 모든 좌표: round(coord, 2)
- QThread 백그라운드 실행
- 진행률 시그널 발출
"""

import json
import os
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from PyQt6.QtCore import QThread, pyqtSignal, QObject


class BatchJobStatus(Enum):
    """배치 작업 상태"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchJob:
    """배치 작업 항목"""
    id: str
    smiles: str
    formula: str
    status: str = "pending"  # BatchJobStatus 값
    result: Optional[Dict] = None
    error_message: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    computation_time_sec: float = 0.0
    
    def to_dict(self):
        return asdict(self)


class BatchProcessor(QObject):
    """
    여러 분자에 대한 순차 ORCA 계산 관리
    
    Signals:
        job_started: 작업 시작 (job_id)
        job_completed: 작업 완료 (job_id, result)
        job_failed: 작업 실패 (job_id, error)
        progress: 진행률 (completed, total, percentage)
        batch_finished: 배치 완료 (results)
    """
    
    job_started = pyqtSignal(str)
    job_completed = pyqtSignal(str, dict)
    job_failed = pyqtSignal(str, str)
    progress = pyqtSignal(int, int, float)  # completed, total, percentage
    batch_finished = pyqtSignal(dict)  # summary
    
    def __init__(self, orca_calculator=None):
        """
        BatchProcessor 초기화
        
        Args:
            orca_calculator: OrcaCalculatorThread 인스턴스
        """
        super().__init__()
        self.orca_calculator = orca_calculator
        self.jobs: List[BatchJob] = []
        self.completed = 0
        self.failed = 0
        self.is_running = False
        self.should_cancel = False
    
    def add_job(self, smiles: str, formula: str) -> str:
        """
        배치에 작업 추가
        
        Args:
            smiles: SMILES 문자열
            formula: 분자식
        
        Returns:
            작업 ID
        """
        job_id = f"job_{len(self.jobs)}_{datetime.now().strftime('%H%M%S')}"
        job = BatchJob(
            id=job_id,
            smiles=smiles,
            formula=formula,
            status=BatchJobStatus.PENDING.value
        )
        self.jobs.append(job)
        return job_id
    
    def add_jobs_from_list(self, molecules: List[Tuple[str, str]]) -> int:
        """
        리스트에서 여러 작업 추가
        
        Args:
            molecules: [(smiles, formula), ...] 리스트
        
        Returns:
            추가된 작업 수
        """
        count = 0
        for smiles, formula in molecules:
            self.add_job(smiles, formula)
            count += 1
        
        print(f"[INFO] Added {count} batch jobs")
        return count
    
    def add_jobs_from_file(self, filepath: str) -> int:
        """
        파일에서 작업 목록 로드
        
        지원 형식:
        - JSON: {"molecules": [{"smiles": "...", "formula": "..."}, ...]}
        - CSV: smiles,formula 헤더 포함
        
        Args:
            filepath: 파일 경로
        
        Returns:
            추가된 작업 수
        """
        try:
            if filepath.endswith('.json'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                count = 0
                for mol in data.get('molecules', []):
                    self.add_job(mol['smiles'], mol['formula'])
                    count += 1
                
                print(f"[INFO] Loaded {count} molecules from JSON")
                return count
            
            elif filepath.endswith('.csv'):
                import csv
                
                count = 0
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.add_job(row['smiles'], row['formula'])
                        count += 1
                
                print(f"[INFO] Loaded {count} molecules from CSV")
                return count
        except Exception as e:
            print(f"[ERROR] Failed to load from file: {e}")
        
        return 0
    
    def run_batch(self, orca_calculator: Callable = None) -> Dict:
        """
        배치 처리 실행
        
        Args:
            orca_calculator: ORCA 계산 함수 또는 callable
        
        Returns:
            결과 요약 딕셔너리
        """
        if self.is_running:
            print("[WARNING] Batch already running")
            return {}
        
        self.is_running = True
        self.should_cancel = False
        self.completed = 0
        self.failed = 0
        
        start_time = time.time()
        results = {}
        
        for job in self.jobs:
            if self.should_cancel:
                break
            
            # 진행률 신호 발출
            self.progress.emit(
                self.completed,
                len(self.jobs),
                (self.completed / len(self.jobs) * 100) if self.jobs else 0
            )
            
            # 작업 실행
            self._run_job(job, orca_calculator)
            
            results[job.id] = job.to_dict()
            
            # 완료/실패 카운팅
            if job.status == BatchJobStatus.COMPLETED.value:
                self.completed += 1
            elif job.status == BatchJobStatus.FAILED.value:
                self.failed += 1
        
        # 배치 완료
        end_time = time.time()
        summary = {
            "total_jobs": len(self.jobs),
            "completed": self.completed,
            "failed": self.failed,
            "cancelled": len([j for j in self.jobs if j.status == BatchJobStatus.CANCELLED.value]),
            "total_time_sec": round(end_time - start_time, 2),
            "avg_time_per_job": round((end_time - start_time) / len(self.jobs), 2) if self.jobs else 0,
            "start_time": datetime.fromtimestamp(start_time).isoformat(),
            "end_time": datetime.fromtimestamp(end_time).isoformat(),
            "results": results
        }
        
        # 최종 신호
        self.progress.emit(len(self.jobs), len(self.jobs), 100.0)
        self.batch_finished.emit(summary)
        
        self.is_running = False
        return summary
    
    def _run_job(self, job: BatchJob, calculator: Callable = None):
        """
        개별 작업 실행
        
        Args:
            job: BatchJob
            calculator: ORCA 계산 함수
        """
        try:
            job.status = BatchJobStatus.RUNNING.value
            job.start_time = datetime.now().isoformat()
            
            self.job_started.emit(job.id)
            
            # 계산 수행
            if calculator:
                start = time.time()
                result = calculator(job.smiles)  # 외부 계산 함수 호출
                end = time.time()
                job.computation_time_sec = round(end - start, 2)
                
                if result:
                    job.status = BatchJobStatus.COMPLETED.value
                    job.result = result
                    self.job_completed.emit(job.id, result)
                else:
                    raise Exception("Calculation returned None")
            else:
                # 더미 결과 (테스트용)
                job.status = BatchJobStatus.COMPLETED.value
                job.result = {"energy": -1000.0, "converged": True}
                job.computation_time_sec = 0.1
                self.job_completed.emit(job.id, job.result)
        
        except Exception as e:
            job.status = BatchJobStatus.FAILED.value
            job.error_message = str(e)
            self.job_failed.emit(job.id, str(e))
            print(f"[ERROR] Job {job.id} failed: {e}")
        
        finally:
            job.end_time = datetime.now().isoformat()
    
    def cancel_batch(self):
        """배치 작업 취소"""
        self.should_cancel = True
        
        for job in self.jobs:
            if job.status == BatchJobStatus.PENDING.value:
                job.status = BatchJobStatus.CANCELLED.value
        
        print("[INFO] Batch cancellation requested")
    
    def get_job_status(self, job_id: str) -> Optional[BatchJob]:
        """
        작업 상태 조회
        
        Args:
            job_id: 작업 ID
        
        Returns:
            BatchJob 또는 None
        """
        for job in self.jobs:
            if job.id == job_id:
                return job
        
        return None
    
    def get_summary(self) -> Dict:
        """
        현재 배치 요약
        
        Returns:
            요약 딕셔너리
        """
        completed = len([j for j in self.jobs if j.status == BatchJobStatus.COMPLETED.value])
        failed = len([j for j in self.jobs if j.status == BatchJobStatus.FAILED.value])
        
        return {
            "total": len(self.jobs),
            "completed": completed,
            "failed": failed,
            "pending": len([j for j in self.jobs if j.status == BatchJobStatus.PENDING.value]),
            "progress_percent": (completed / len(self.jobs) * 100) if self.jobs else 0,
            "is_running": self.is_running
        }


class BatchProcessorThread(QThread):
    """
    배치 처리를 위한 백그라운드 스레드
    
    Signals:
        progress: 진행률 (completed, total, percentage)
        finished: 배치 완료 (summary)
        error: 에러 (message)
    """
    
    progress = pyqtSignal(int, int, float)  # completed, total, percent
    finished = pyqtSignal(dict)  # summary
    job_completed = pyqtSignal(str, dict)
    job_failed = pyqtSignal(str, str)
    error = pyqtSignal(str)
    
    def __init__(self, batch_processor: BatchProcessor, 
                 calculator: Callable = None):
        """
        배치 처리 스레드 초기화
        
        Args:
            batch_processor: BatchProcessor 인스턴스
            calculator: ORCA 계산 함수
        """
        super().__init__()
        self.batch_processor = batch_processor
        self.calculator = calculator
        
        # 신호 연결
        batch_processor.progress.connect(self.progress.emit)
        batch_processor.batch_finished.connect(self.finished.emit)
        batch_processor.job_completed.connect(self.job_completed.emit)
        batch_processor.job_failed.connect(self.job_failed.emit)
    
    def run(self):
        """스레드 실행"""
        try:
            summary = self.batch_processor.run_batch(self.calculator)
            self.finished.emit(summary)
        except Exception as e:
            self.error.emit(f"Batch thread error: {str(e)}")


# ============================================================================
# EXPORT FUNCTIONS
# ============================================================================

def export_batch_results_json(summary: Dict, output_path: str) -> bool:
    """
    배치 결과를 JSON으로 내보내기
    
    Args:
        summary: 배치 완료 요약
        output_path: 저장 경로
    
    Returns:
        성공 여부
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"[INFO] Batch results exported: {output_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Export failed: {e}")
        return False


def export_batch_results_csv(summary: Dict, output_path: str) -> bool:
    """
    배치 결과를 CSV로 내보내기
    
    Args:
        summary: 배치 완료 요약
        output_path: 저장 경로
    
    Returns:
        성공 여부
    """
    try:
        import csv
        
        results = summary.get('results', {})
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['job_id', 'smiles', 'formula', 'status', 'computation_time_sec', 'error']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for job_id, job_data in results.items():
                writer.writerow({
                    'job_id': job_data['id'],
                    'smiles': job_data['smiles'],
                    'formula': job_data['formula'],
                    'status': job_data['status'],
                    'computation_time_sec': job_data['computation_time_sec'],
                    'error': job_data['error_message']
                })
        
        print(f"[INFO] Batch results exported: {output_path}")
        return True
    except Exception as e:
        print(f"[ERROR] CSV export failed: {e}")
        return False


def generate_batch_report(summary: Dict) -> str:
    """
    배치 완료 보고서 생성
    
    Args:
        summary: 배치 완료 요약
    
    Returns:
        보고서 텍스트
    """
    report = f"""
====================================
ORCA Batch Processing Report
====================================

Start Time: {summary.get('start_time', 'N/A')}
End Time: {summary.get('end_time', 'N/A')}
Total Time: {summary.get('total_time_sec', 0.0):.2f} sec

Results:
  Total Jobs: {summary.get('total_jobs', 0)}
  Completed: {summary.get('completed', 0)}
  Failed: {summary.get('failed', 0)}
  Cancelled: {summary.get('cancelled', 0)}
  Success Rate: {(summary.get('completed', 0) / summary.get('total_jobs', 1) * 100):.1f}%

Performance:
  Average Time/Job: {summary.get('avg_time_per_job', 0.0):.2f} sec

====================================
"""
    return report
