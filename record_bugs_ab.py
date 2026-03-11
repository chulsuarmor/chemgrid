"""BUG-A, BUG-B 실수 기록"""

entry = '''
---

## [2026-03-10] BUG-A: 3D 팝업 방향족 결합 전부 이중결합으로 표현

**상황**: 벤젠, 나프탈렌 등 방향족 분자를 3D 팝업에서 보면 C-C 결합이 전부 이중결합으로 표현됨

**근본 원인** (`src/app/popup_3d.py`):
```python
# BEFORE (버그)
bt = bond.GetBondTypeAsDouble()  # 방향족 결합 = 1.5 반환
order = int(round(bt)) if bt else 1  # int(round(1.5)) = 2 ← Python banker's rounding!
```
- Python의 banker's rounding: `round(1.5) = 2` (짝수 반올림)
- 방향족 결합 1.5 → 2 (이중결합)로 저장 → 3D에서 모두 이중결합으로 표현

**해결**:
```python
# AFTER (수정)
if bt and abs(bt - 1.5) < 0.01:
    order = 1.5   # 방향족 비편재화 결합 보존
else:
    order = int(round(bt)) if bt else 1
```
- 렌더러에 `elif isinstance(bo, float) and abs(bo - 1.5) < 0.01:` 분기 추가
- `_aromatic_bond_overlay()` 메서드로 단일 + 얇은 평행 실린더 표현

**교훈**: Python `int(round(1.5)) = 2` — banker's rounding 함정
  화학에서 1.5 bond order는 반드시 float로 보존하고 별도 처리할 것
  절대 `int(round(bt))` 직접 변환 금지

**수정 파일**: `src/app/popup_3d.py` (2026-03-10)

---

## [2026-03-10] BUG-B: _last_drawn_smiles 타이밍 버그 (stale SMILES 주입)

**상황**: 텍스트로 분자 입력 후 이론적 구조 분석 시 이전(stale) SMILES가 analyze()에 주입됨

**근본 원인** (`src/app/main_window.py` `_draw_smiles_on_canvas()`):
```python
# BEFORE (버그) - 순서가 역전됨
self.cv.analysis_results = self.cv.analyzer.analyze(
    self.cv.atoms, self.cv.bonds,
    smiles=getattr(self.cv, '_last_drawn_smiles', None)  # ← 이전 smiles! 새 smiles 아님
)
self.cv._last_drawn_smiles = smiles  # ← 너무 늦게 설정
```

**해결**:
```python
# AFTER (수정) - smiles 먼저 설정 후 analyze
self.cv._last_drawn_smiles = smiles   # ← 먼저 설정
self.cv._last_drawn_mol_name = mol_name
self.cv.analysis_results = self.cv.analyzer.analyze(
    self.cv.atoms, self.cv.bonds, smiles=smiles  # ← 현재 smiles 직접 주입
)
```

**교훈**: 분자 정보는 항상 analyze() 호출 전에 완전히 설정할 것
  `getattr(self.cv, '_last_drawn_smiles', None)` 패턴 대신
  직접 변수 전달 방식 사용 (순서 버그 예방)

**수정 파일**: `src/app/main_window.py` (2026-03-10)
'''

with open('docs/ai/mistakes.md', 'a', encoding='utf-8') as f:
    f.write(entry)
print('mistakes.md BUG-A/B 기록 완료')

# context_list.md 업데이트
try:
    c = open('context_list.md', encoding='utf-8').read()
    # 체크리스트 항목 추가
    new_items = '''
## 2026-03-10 세션 2 완료 항목

- [x] BUG-A: 3D 방향족 결합 이중결합 오류 수정 (popup_3d.py)
  - int(round(1.5))=2 버그 → 1.5 float 보존 + _aromatic_bond_overlay
- [x] BUG-B: _last_drawn_smiles 타이밍 버그 수정 (main_window.py)
  - analyze() 호출 전 smiles 먼저 설정
- [x] IR 스펙트럼 검증 완료 (에탄올: O-H 15%, T<50% PASS)
- [x] NMR 검증 완료 (벤젠: 7.3ppm 방향족 H PASS)

## 미완료 / 다음 세션 항목

- [ ] 실제 ChemGrid 구동 시 3D 벤젠 방향족 결합 시각 확인 (코드 수정 완료, 눈으로 확인 필요)
- [ ] 분광분석 PDF 출력 전체 데이터 검증
- [ ] AI 텍스트 분자 생성기 Google API 연동 (BUG-4)
- [ ] 대형 분자(hemoglobin 등) SMILES 인식 개선 (BUG-3 후속)
'''
    open('context_list.md', 'a', encoding='utf-8').write(new_items)
    print('context_list.md 업데이트 완료')
except Exception as e:
    print(f'context_list.md 오류: {e}')

print('\n=== 최종 업데이트 완료 ===')
