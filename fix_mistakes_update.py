new_entry = """

---

## [2026-03-10] BUG-3 전자구름 편재화 — 진짜 근본 원인 최종 발견 (20회 시도 끝)

**상황**: cp- ([cH-]1cccc1), tropylium (C1=CC=CC=C[CH+]1) 등 이온성 공명 분자에서 전자구름이 일부 탄소에 집중

**진단 결과 (render_test_report.py → charge diagnostic)**:
```
Cp-:       charges=[0.065, 0.036, 0.021, 0.021, 0.036]  ring_all_size=0  aro_in_ring=0
Tropylium: charges=[-0.032, -0.013, -0.018, -0.018, -0.013, -0.032, -0.054]  ring_all_size=0
Benzene:   charges=[0.0, 0.0, 0.0, ...]  ring_all_size=0  (균등하지만 ring 미감지)
```

**진짜 근본 원인 (인과 체인)**:
1. `ChemicalAnalyzer.analyze()` 내부에서 `generate_smiles()` 호출
2. `generate_smiles()`가 cp-/Tropylium 같은 **이온화된 방향족 구조**에서 실패
   - 오류: `Explicit valence for atom # 2 C, 4, is greater than permitted`
3. SMILES 생성 실패 → RDKit으로 ring/aromatic 분석 불가
4. `ring_atoms_all = {}`, `aromatic = {}` → 모두 빈 set
5. renderer.py에서 ring 원자를 식별할 수 없으므로 Gasteiger 전하 그대로 사용
6. Gasteiger 전하는 cp-에서 [0.065, 0.036, 0.021, 0.021, 0.036] (불균등) → 구름 크기 차이 → 편재화

**이전에 시도한 잘못된 방법들 (21회 실패)**:
- renderer.py raw_strength 조건 수정 (ring_atoms_all이 비어있어 효과 없음)
- ionic_bias_uniform 추가 (analyze() 결과가 이미 틀려서 효과 없음)
- aromatic set 확장 (aromatic set 자체가 generate_smiles 실패로 비어있음)
- charge normalization (근본적인 ring detection 실패를 우회하지 못함)

**올바른 해결 방법 (다음 세션에서 구현)**:
```python
# analyzer.py ChemicalAnalyzer.analyze() 수정
# 방법 1: analyze()에 smiles 파라미터 추가
def analyze(self, atoms, bonds, smiles=None):
    # generate_smiles() 대신 외부에서 제공된 smiles 우선 사용
    if smiles:
        self._cached_smiles = smiles
    else:
        self._cached_smiles = self._generate_smiles_safe(atoms, bonds)
    # _cached_smiles로 RDKit ring/aromatic 분석
    
# 방법 2: canvas가 이론적 구조 전환 시 _last_drawn_smiles를 analyze()에 주입
# layer_logic.py 또는 main_window.py에서:
results = analyzer.analyze(atoms, bonds, smiles=canvas._last_drawn_smiles)
```

**시각 검증 결과 (render_test_report.html)**:
- Benzene: GREEN 전자구름 균등 분포 ✅ (영향 없음 - generate_smiles가 C1=C=C=C=C=C=1 생성하지만 charge는 0)
- Naphthalene: GREEN 전자구름 균등 분포 ✅
- cp-: 단일 GREEN 점만 표시 ❌ (RED 균등 분포여야 함)
- Tropylium: 미확인 (동일 원인으로 오류 예상)

**수정 파일 (다음 세션)**: `src/app/analyzer.py` `ChemicalAnalyzer.analyze()` — smiles 파라미터 추가
"""

with open('docs/ai/mistakes.md', 'a', encoding='utf-8') as f:
    f.write(new_entry)
print('mistakes.md 최종 근본원인 기록 완료')
