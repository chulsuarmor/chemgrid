"""
workflow_tracker.py - DryLab/PolymerLab 워크플로우 상태 추적기.

학생이 보고서 생성 전에 올바른 사고 과정(분석→도킹→유도체→합성)을
거쳤는지 추적합니다.

NOTE: 워크플로우 추적기는 ADVISORY(권고) 역할만 합니다.
- 모든 기능(Drawing/Lewis/Theory/3D 등)에 자유롭게 접근 가능
- 보고서 내보내기도 항상 가능 (미완료 시 확인 대화상자 표시)
- 워크플로우 완료 시 DryLab 버튼 강조 + 알림 표시

Debug mode: CHEMGRID_DEBUG=1 환경변수 설정 시 확인 대화상자 생략.
"""
import os
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


def _is_debug_mode() -> bool:
    """CHEMGRID_DEBUG=1이면 True 반환 (게이트 우회용)."""
    return os.environ.get("CHEMGRID_DEBUG", "0") == "1"


@dataclass
class DryLabWorkflowData:
    """DryLab 워크플로우에서 수집된 학생의 사고 과정 데이터."""
    # Step 1: 구조체 분석
    molecule_smiles: str = ""
    molecule_name: str = ""

    # Step 2: 도킹 시뮬레��션
    receptor_name: str = ""
    receptor_pdb_id: str = ""
    docking_affinity: float = 0.0
    docking_reason: str = ""  # 왜 이 수용체를 선택했는지

    # Step 3: 유도체 설계
    derivative_smiles: str = ""
    derivative_description: str = ""
    design_goal: str = ""  # 항암, BBB 투과, 대사안정성 등

    # Step 4: 합성 경로
    synthesis_route_count: int = 0
    synthesis_steps: int = 0


@dataclass
class PolymerLabWorkflowData:
    """PolymerLab 워크플로우에서 수집된 학생의 사고 과정 데이터."""
    # Step 1: 모노머 구조
    monomer_smiles: str = ""
    monomer_name: str = ""

    # Step 2: 고분자 변환 (목적 기반)
    transformation_goal: str = ""  # 표면 접지력 향상, 내열성 등
    polymer_props: Dict[str, Any] = field(default_factory=dict)

    # Step 3: 합성 경로
    synthesis_route_count: int = 0
    synthesis_steps: int = 0


class WorkflowTracker(QObject):
    """DryLab/PolymerLab 보고서 생성 조건을 추적하는 상태 머신.

    각 단계가 완료될 때마다 시그널을 방출하여 UI 업데이트를 트리거합니다.
    """

    # 상태 변경 시그널: 특정 단계가 완료되었을 때 방출
    drylab_step_completed = pyqtSignal(str)       # step name
    polymerlab_step_completed = pyqtSignal(str)   # step name
    drylab_ready = pyqtSignal()                   # 모든 DryLab 단계 완료
    polymerlab_ready = pyqtSignal()               # 모든 PolymerLab 단계 완료

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        # DryLab 워크플로우 단계
        self._drylab_steps: Dict[str, bool] = {
            'structure_analyzed': False,    # Step 1: 분자 로딩 + 분석 완료
            'docking_performed': False,     # Step 2: 도킹 시뮬레이션 실행
            'derivative_designed': False,   # Step 3: 리드 최적화 사용 (목표 설정)
            'synthesis_analyzed': False,    # Step 4: 역합성 경로 분석
        }

        # PolymerLab 워크플로우 단계
        self._polymerlab_steps: Dict[str, bool] = {
            'monomer_loaded': False,        # Step 1: 모노머 구조 입력
            'polymer_transformed': False,   # Step 2: 목적 기반 고분자 분석
            'synthesis_analyzed': False,    # Step 3: 합성 경로 분석
        }

        # 워크플로우 데이터 (보고서에 포함할 사고 과정)
        self._drylab_data = DryLabWorkflowData()
        self._polymerlab_data = PolymerLabWorkflowData()

    # ══════════════════════════════════════════════════
    #  DryLab 워크플로우 상태 업데이트 메서드
    # ══════════════════════════════════════════════════

    def set_structure_analyzed(self, smiles: str, name: str = "") -> None:
        """Step 1: 분자 구조 분석 완료."""
        self._drylab_steps['structure_analyzed'] = True
        self._drylab_data.molecule_smiles = smiles
        self._drylab_data.molecule_name = name
        logger.info("[WorkflowTracker] DryLab step 1 complete: structure_analyzed (%s)", name or smiles[:30])
        self.drylab_step_completed.emit('structure_analyzed')
        self._check_drylab_ready()

    def set_docking_performed(self, receptor_name: str = "", pdb_id: str = "",
                              affinity: float = 0.0, reason: str = "") -> None:
        """Step 2: 도킹 시뮬레이션 완료."""
        self._drylab_steps['docking_performed'] = True
        self._drylab_data.receptor_name = receptor_name
        self._drylab_data.receptor_pdb_id = pdb_id
        self._drylab_data.docking_affinity = affinity
        self._drylab_data.docking_reason = reason
        logger.info("[WorkflowTracker] DryLab step 2 complete: docking_performed (receptor=%s)", receptor_name)
        self.drylab_step_completed.emit('docking_performed')
        self._check_drylab_ready()

    def set_derivative_designed(self, derivative_smiles: str = "",
                                description: str = "", goal: str = "") -> None:
        """Step 3: 유도체 설계 완료 (리드 최적화)."""
        self._drylab_steps['derivative_designed'] = True
        self._drylab_data.derivative_smiles = derivative_smiles
        self._drylab_data.derivative_description = description
        self._drylab_data.design_goal = goal
        logger.info("[WorkflowTracker] DryLab step 3 complete: derivative_designed (goal=%s)", goal)
        self.drylab_step_completed.emit('derivative_designed')
        self._check_drylab_ready()

    def set_synthesis_analyzed(self, route_count: int = 0, steps: int = 0) -> None:
        """Step 4: 합성 경로 분석 완료."""
        self._drylab_steps['synthesis_analyzed'] = True
        self._drylab_data.synthesis_route_count = route_count
        self._drylab_data.synthesis_steps = steps
        logger.info("[WorkflowTracker] DryLab step 4 complete: synthesis_analyzed (%d routes)", route_count)
        self.drylab_step_completed.emit('synthesis_analyzed')
        self._check_drylab_ready()

    # ══════════════════════════════════════════════════
    #  PolymerLab 워크플로우 상태 업데이트 메서드
    # ══════════════════════════════════════════════════

    def set_monomer_loaded(self, smiles: str, name: str = "") -> None:
        """Step 1: 모노머 구조 입력 완료."""
        self._polymerlab_steps['monomer_loaded'] = True
        self._polymerlab_data.monomer_smiles = smiles
        self._polymerlab_data.monomer_name = name
        logger.info("[WorkflowTracker] PolymerLab step 1 complete: monomer_loaded (%s)", name or smiles[:30])
        self.polymerlab_step_completed.emit('monomer_loaded')
        self._check_polymerlab_ready()

    def set_polymer_transformed(self, goal: str = "", props: Optional[Dict[str, Any]] = None) -> None:
        """Step 2: 목적 기반 고분자 변환 완료."""
        self._polymerlab_steps['polymer_transformed'] = True
        self._polymerlab_data.transformation_goal = goal
        self._polymerlab_data.polymer_props = props or {}
        logger.info("[WorkflowTracker] PolymerLab step 2 complete: polymer_transformed (goal=%s)", goal)
        self.polymerlab_step_completed.emit('polymer_transformed')
        self._check_polymerlab_ready()

    def set_polymer_synthesis_analyzed(self, route_count: int = 0, steps: int = 0) -> None:
        """Step 3: 고분자 합성 경로 분석 완료."""
        self._polymerlab_steps['synthesis_analyzed'] = True
        self._polymerlab_data.synthesis_route_count = route_count
        self._polymerlab_data.synthesis_steps = steps
        logger.info("[WorkflowTracker] PolymerLab step 3 complete: synthesis_analyzed (%d routes)", route_count)
        self.polymerlab_step_completed.emit('synthesis_analyzed')
        self._check_polymerlab_ready()

    # ══════════════════════════════════════════════════
    #  상태 조회 메서드
    # ══════════════════════════════════════════════════

    def is_drylab_ready(self) -> bool:
        """DryLab 보고서 생성 가능 여부. Debug 모드에서는 항상 True."""
        if _is_debug_mode():
            return True
        return all(self._drylab_steps.values())

    def is_polymerlab_ready(self) -> bool:
        """PolymerLab 보고서 생성 가능 여부. Debug 모드에서는 항상 True."""
        if _is_debug_mode():
            return True
        return all(self._polymerlab_steps.values())

    def get_drylab_steps(self) -> Dict[str, bool]:
        """현재 DryLab 워크플로우 단계 상태 반환."""
        return dict(self._drylab_steps)

    def get_polymerlab_steps(self) -> Dict[str, bool]:
        """현재 PolymerLab 워크플로우 단계 상태 반환."""
        return dict(self._polymerlab_steps)

    def get_drylab_data(self) -> DryLabWorkflowData:
        """DryLab 워크플로우에서 수집된 데이터 반환."""
        return self._drylab_data

    def get_polymerlab_data(self) -> PolymerLabWorkflowData:
        """PolymerLab 워크플로우에서 수집된 데이터 반환."""
        return self._polymerlab_data

    def get_completed_steps_count(self, workflow: str = "drylab") -> tuple:
        """완료된 단계 수와 총 단계 수 반환. Returns (completed, total)."""
        if workflow == "drylab":
            steps = self._drylab_steps
        else:
            steps = self._polymerlab_steps
        completed = sum(1 for v in steps.values() if v)
        return (completed, len(steps))

    def get_missing_steps_tooltip(self, workflow: str = "drylab") -> str:
        """미완료 단계를 설명하는 툴팁 문자열 반환."""
        if workflow == "drylab":
            steps = self._drylab_steps
            labels = {
                'structure_analyzed': '1단계: 구조체 분석',
                'docking_performed': '2단계: 도킹 시뮬레이션',
                'derivative_designed': '3단계: 유도체 설계 (리드 최적화)',
                'synthesis_analyzed': '4단계: 합성 경로 분석',
            }
        else:
            steps = self._polymerlab_steps
            labels = {
                'monomer_loaded': '1단계: 모노머 구조 입력',
                'polymer_transformed': '2단계: 목적 기반 고분자 변환',
                'synthesis_analyzed': '3단계: 합성 경로 분석',
            }

        missing = [labels[k] for k, v in steps.items() if not v]
        if not missing:
            return "보고서 생성 준비 완료!"

        return "미완료 단계:\n" + "\n".join(f"  - {m}" for m in missing)

    def get_missing_steps_list(self, workflow: str = "drylab") -> list:
        """미완료 단계 라벨 리스트 반환 (UI 대화상자용)."""
        if workflow == "drylab":
            steps = self._drylab_steps
            labels = {
                'structure_analyzed': '1단계: 구조체 분석',
                'docking_performed': '2단계: 도킹 시뮬레이션',
                'derivative_designed': '3단계: 유도체 설계 (리드 최적화)',
                'synthesis_analyzed': '4단계: 합성 경로 분석',
            }
        else:
            steps = self._polymerlab_steps
            labels = {
                'monomer_loaded': '1단계: 모노머 구조 입력',
                'polymer_transformed': '2단계: 목적 기반 고분자 변환',
                'synthesis_analyzed': '3단계: 합성 경로 분석',
            }
        return [labels[k] for k, v in steps.items() if not v]

    # ══════════════════════════════════════════════════
    #  리셋 메서드
    # ══════════════════════════════════════════════════

    def reset_drylab(self) -> None:
        """DryLab 워크플로우 상태 초기화 (새 분자 시작 시)."""
        for key in self._drylab_steps:
            self._drylab_steps[key] = False
        self._drylab_data = DryLabWorkflowData()
        logger.info("[WorkflowTracker] DryLab workflow reset")

    def reset_polymerlab(self) -> None:
        """PolymerLab 워크플로우 상태 초기화."""
        for key in self._polymerlab_steps:
            self._polymerlab_steps[key] = False
        self._polymerlab_data = PolymerLabWorkflowData()
        logger.info("[WorkflowTracker] PolymerLab workflow reset")

    def reset_all(self) -> None:
        """모든 워크플로우 상태 초기화."""
        self.reset_drylab()
        self.reset_polymerlab()

    # ══════════════════════════════════════════════════
    #  내부 헬퍼
    # ══════════════════════════════════════════════════

    def _check_drylab_ready(self) -> None:
        """DryLab 모든 단계 완료 시 시그널 방출."""
        if all(self._drylab_steps.values()):
            logger.info("[WorkflowTracker] DryLab workflow COMPLETE - report export enabled")
            self.drylab_ready.emit()

    def _check_polymerlab_ready(self) -> None:
        """PolymerLab 모든 단계 완료 시 시그널 방출."""
        if all(self._polymerlab_steps.values()):
            logger.info("[WorkflowTracker] PolymerLab workflow COMPLETE - report export enabled")
            self.polymerlab_ready.emit()
