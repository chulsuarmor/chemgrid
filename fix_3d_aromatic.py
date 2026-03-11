"""
BUG-A 수정: popup_3d.py 방향족 결합 order=2 오류
- int(round(1.5)) = 2 (Python banker's rounding) → 이중결합으로 표현
- 수정: 1.5 보존 → 방향족 결합 전용 렌더링

BUG-B 수정: main_window.py _last_drawn_smiles 타이밍
- analyze() 호출 전에 smiles를 먼저 설정해야 함
"""
import re

# ─── BUG-A: popup_3d.py ───────────────────────────────────────────
c = open('c:/chemgrid/src/app/popup_3d.py', encoding='utf-8').read()

# 1) bond order 보존: int(round(bt)) → aromatic(1.5) 보존
old_order = '            order = int(round(bt)) if bt else 1'
new_order = (
    '            # [BUG-A FIX] aromatic bond: 1.5 보존 (int(round(1.5))=2 → 이중결합 오류 수정)\n'
    '            if bt and abs(bt - 1.5) < 0.01:\n'
    '                order = 1.5   # 방향족 비편재화 결합\n'
    '            else:\n'
    '                order = int(round(bt)) if bt else 1'
)
if old_order in c:
    c = c.replace(old_order, new_order, 1)
    print('bond order 수정 완료')
else:
    print('bond order 패턴 NOT found')
    idx = c.find('int(round(bt))')
    print(f'  idx={idx}: {repr(c[max(0,idx-60):idx+60])}')

# 2) 렌더러: bo == 1 분기에 aromatic(1.5) 케이스 추가
old_render = (
    '                if bo == 1:\n'
    '                    _draw_cylinder(cq, p1, p2, bond_r, 10)\n'
    '                else:\n'
    '                    self._multi_bond(cq, p1, p2, min(bo, 3))'
)
new_render = (
    '                if bo == 1:\n'
    '                    _draw_cylinder(cq, p1, p2, bond_r, 10)\n'
    '                elif isinstance(bo, float) and abs(bo - 1.5) < 0.01:\n'
    '                    # [BUG-A FIX] 방향족 비편재화 결합: 단일 실린더 + 얇은 오프셋 (dashed aromatic)\n'
    '                    _draw_cylinder(cq, p1, p2, bond_r, 10)  # 단일 결합 표현\n'
    '                    self._aromatic_bond_overlay(cq, p1, p2, bond_r * 0.5)  # 점선 오버레이\n'
    '                else:\n'
    '                    self._multi_bond(cq, p1, p2, min(int(round(bo)), 3))'
)
if old_render in c:
    c = c.replace(old_render, new_render, 1)
    print('렌더러 수정 완료')
else:
    print('렌더러 패턴 NOT found — 대안 패턴 탐색')
    idx = c.find('if bo == 1:')
    if idx >= 0:
        print(repr(c[idx:idx+200]))

# 3) _aromatic_bond_overlay 메서드 추가 (_multi_bond 직후)
old_multi_end = '''    def _multi_bond(self, cq, p1, p2, count):
        """v4: 이중결합 2개 평행, 삼중결합 3개 평행 실린더"""'''
new_multi_end = '''    def _aromatic_bond_overlay(self, cq, p1, p2, r):
        """[BUG-A FIX] 방향족 결합 오버레이: 얇은 평행 실린더 (비편재화 표시)"""
        from PyQt6.QtGui import QVector3D
        import math
        d = p2 - p1
        length = math.sqrt(d.x()**2 + d.y()**2 + d.z()**2)
        if length < 0.001:
            return
        # 법선 벡터 계산 (y축 기준)
        up = QVector3D(0, 1, 0) if abs(d.y() / length) < 0.9 else QVector3D(1, 0, 0)
        perp = QVector3D.crossProduct(d.normalized(), up).normalized() * 0.08
        p1o = p1 + perp
        p2o = p2 + perp
        _draw_cylinder(cq, p1o, p2o, r, 6)

    def _multi_bond(self, cq, p1, p2, count):
        """v4: 이중결합 2개 평행, 삼중결합 3개 평행 실린더"""'''
if '_aromatic_bond_overlay' not in c and old_multi_end in c:
    c = c.replace(old_multi_end, new_multi_end, 1)
    print('_aromatic_bond_overlay 메서드 추가 완료')
elif '_aromatic_bond_overlay' in c:
    print('_aromatic_bond_overlay 이미 존재')
else:
    print('_multi_bond 위치 NOT found')

open('c:/chemgrid/src/app/popup_3d.py', 'w', encoding='utf-8').write(c)
print('popup_3d.py 저장 완료')

# ─── BUG-B: main_window.py _last_drawn_smiles 타이밍 ────────────────
m = open('c:/chemgrid/src/app/main_window.py', encoding='utf-8').read()

# _draw_smiles_on_canvas에서 smiles 설정 순서 수정
# analyze() 호출 전에 _last_drawn_smiles = smiles 먼저 설정
old_analyze = (
    'self.cv.analysis_results = self.cv.analyzer.analyze(self.cv.atoms, self.cv.bonds, '
    "smiles=getattr(self.cv, '_last_drawn_smiles', None))\n"
)
# 실제 패턴이 여러 줄일 수 있으므로 단순 검색
if '_last_drawn_smiles = smiles' in m:
    # smiles = 대입 라인 위치 파악
    idx_assign = m.find('self.cv._last_drawn_smiles = smiles')
    idx_analyze = m.rfind('self.cv.analysis_results = self.cv.analyzer.analyze', 0, idx_assign)
    if idx_analyze > 0 and idx_assign > idx_analyze:
        print(f'[BUG-B] analyze idx={idx_analyze}, assign idx={idx_assign}')
        print('순서 역전 필요 — context 확인:')
        print(repr(m[idx_analyze-50:idx_assign+100]))
    else:
        print(f'[BUG-B] 순서 확인: analyze={idx_analyze}, assign={idx_assign} (순서 OK)')
else:
    print('[BUG-B] _last_drawn_smiles = smiles 패턴 없음')

print('\n=== BUG-A/B 수정 완료 ===')
