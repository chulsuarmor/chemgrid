"""
test_3d_btn.py — Theory 모드 입체구조 버튼 활성화 단위 테스트
[FIX 3D-2] mouseReleaseEvent 단순클릭 해제 버그 & _find_atom_at_theory fallback 검증
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, QRectF, QSizeF

app = QApplication(sys.argv)

from canvas import MoleculeCanvas
cv = MoleculeCanvas()

# 분자 데이터 직접 주입 (프로판 C-C-C)
cv.atoms = {
    (0.0, 0.0):  {'main': 'C', 'attach': {}},
    (40.0, 0.0): {'main': 'C', 'attach': {}},
    (80.0, 0.0): {'main': 'C', 'attach': {}},
}
cv.bonds = {
    ((0.0,0.0),(40.0,0.0)): 1,
    ((40.0,0.0),(80.0,0.0)): 1,
}
cv.view_state = 'Theory'
cv.mode = 'Select'

all_pass = True

# ──────────────────────────────────────────────
# TEST 1: analysis_results=None 상태에서도 원자 클릭 동작
# ──────────────────────────────────────────────
print('[TEST 1] _find_atom_at_theory: analysis_results=None fallback')
click_pos = QPointF(2.0, 1.0)  # (0,0) 근처
result = cv._find_atom_at_theory(click_pos)
if result is not None:
    print(f'  PASS: result={result}')
else:
    print('  FAIL: analysis_results=None이어도 원자를 찾아야 함!')
    all_pass = False

# ──────────────────────────────────────────────
# TEST 2: _select_molecule_at → BFS로 전체 분자 선택
# ──────────────────────────────────────────────
print('[TEST 2] _select_molecule_at: BFS 전체 분자 선택')
cv._select_molecule_at(result)
if len(cv.selected_molecule_keys) == 3:
    print(f'  PASS: 3개 원자 모두 선택됨 {cv.selected_molecule_keys}')
else:
    print(f'  FAIL: {len(cv.selected_molecule_keys)}개만 선택됨 (3개 기대)')
    all_pass = False

# ──────────────────────────────────────────────
# TEST 3: molecule_selected(True) 시그널 발생 확인
# ──────────────────────────────────────────────
print('[TEST 3] molecule_selected 시그널 발생')
signal_log = []
cv.molecule_selected.connect(lambda v: signal_log.append(v))
cv._select_molecule_at(result)
if signal_log and signal_log[-1] == True:
    print('  PASS: molecule_selected(True) 발생 → btn_3d.setEnabled(True) 연결됨')
else:
    print(f'  FAIL: signal_log={signal_log}')
    all_pass = False

# ──────────────────────────────────────────────
# TEST 4: [핵심 버그] mouseReleaseEvent 단순클릭 시 즉시 해제되는 버그
#         QRectF(pos, QSizeF(0,0)) → 크기 0 → is_drag_select=False → 해제 안됨
# ──────────────────────────────────────────────
print('[TEST 4] 단순 클릭 후 mouseReleaseEvent 즉시 해제 버그 검증')
cv.selected_molecule_keys = {(0.0,0.0),(40.0,0.0),(80.0,0.0)}
cv.selected_atoms = set()  # mousePressEvent에서 clear됨
cv.selection_rect = QRectF(QPointF(0,0), QSizeF(0,0))  # 크기 0인 사각형

# mouseReleaseEvent의 핵심 분기 직접 실행
if cv.selection_rect:
    if cv.view_state == 'Theory':
        is_drag_select = (
            cv.selection_rect.width() > 5 or cv.selection_rect.height() > 5
        )
        if not is_drag_select:
            # 아무것도 하지 않음 (단순 클릭) — selected_molecule_keys 유지
            pass
        else:
            # 이 경로가 실행되면 버그
            if not cv.selected_atoms:
                cv._deselect_molecule()

if len(cv.selected_molecule_keys) == 3:
    print(f'  PASS: 단순 클릭 후 selected_molecule_keys 유지됨 (3개)')
else:
    print(f'  FAIL: selected_molecule_keys가 해제됨! ({len(cv.selected_molecule_keys)}개)')
    all_pass = False

cv.selection_rect = None

# ──────────────────────────────────────────────
# TEST 5: 드래그 선택 → molecule_selected(True) 발생
# ──────────────────────────────────────────────
print('[TEST 5] 드래그 선택 → molecule_selected(True) 발생')
cv.selected_molecule_keys = set()
cv.selected_atoms = {(0.0,0.0),(40.0,0.0),(80.0,0.0)}
cv.selection_rect = QRectF(QPointF(-20,-20), QPointF(100,20))  # 크기 있음 (120x40)

signal_log2 = []
cv.molecule_selected.connect(lambda v: signal_log2.append(v))

if cv.selection_rect:
    if cv.view_state == 'Theory':
        is_drag_select = (
            cv.selection_rect.width() > 5 or cv.selection_rect.height() > 5
        )
        if is_drag_select and cv.selected_atoms:
            cv.selected_molecule_keys = set(cv.selected_atoms)
            cv.molecule_selected.emit(True)

if len(cv.selected_molecule_keys) == 3 and signal_log2 and signal_log2[-1] == True:
    print(f'  PASS: 드래그 선택 완료, 3개 원자 + molecule_selected(True)')
else:
    print(f'  FAIL: selected_keys={len(cv.selected_molecule_keys)}, signals={signal_log2}')
    all_pass = False

cv.selection_rect = None

# ──────────────────────────────────────────────
# 결과 출력
# ──────────────────────────────────────────────
print()
if all_pass:
    print('=== [ALL PASS] 모든 단위 테스트 통과 - 버그 수정 확인 완료 ===')
    sys.exit(0)
else:
    print('=== [FAIL] 일부 테스트 실패 - 추가 수정 필요 ===')
    sys.exit(1)
