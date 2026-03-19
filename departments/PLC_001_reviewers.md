# 전학공 #1 — 검수자(R) 직렬 교차학습
> 실시일: 2026-03-18 | Cascade #3 사후
> 참여 대상: R-UI, R-CHEM, R-RENDER, R-3D, R-SPEC, R-RXTN, R-ORCA, R-DOCK, R-EXPORT, R-VFB, R-TEST, R-ALPHA

---

## 1. 검수 표준 프로토콜 (Cascade #3에서 확립)

### 필수 검증 3단계
```
1단계: py_compile + ast.parse (모든 수정 파일)
2단계: _source/ 동기화 검증 (MD5 또는 diff)
3단계: 기능 정합성 테스트 (도메인별 특화)
```

**교훈**: Cascade #2에서 R검수 0회 부서가 3개 존재 → Cascade #3에서 전 부서 R검수 PASS 달성.

---

## 2. 도메인별 기능 정합성 검증 우수 사례

### R-UI: 10분자 headless 테스트
- 10개 대표 분자 SMILES를 headless 로드 → analysis() 호출 → 필수 키('smiles', 'atoms', 'theory_data') 존재 확인
- subTest 패턴으로 1개 실패 시에도 나머지 계속 실행

### R-CHEM: CRC Handbook 교차검증
- 15개 bond length를 CRC Handbook 97th Edition과 직접 대조 (±0.01Å)
- Gasteiger NaN 필터 → 전이금속(Fe, Ru) 포함 분자에서도 크래시 없음 확인

### R-RENDER: 구조 화학 교과서 대조
- partial charge color: δ- = red, δ+ = blue (Clayden 표준)
- CHARGE_THRESHOLD=0.10 → sp3 포화 탄소 필터링 확인

### R-3D: orbital colormap 검증
- +phase=Blue, -phase=Red → Atkins/Clayden 교과서 확인
- Ferrocene geometry: Cp ring radius 1.21Å, Fe-Cp distance 1.66Å (CSD 데이터 기반)

### R-SPEC: 4분자 IR/NMR 교차검증
- Norbornane, Pyridine, Acetone, Ethanol의 peak 위치를 Silverstein 참고서와 비교
- =C-H false positive 제거 확인 (acetone에서 C-H stretch 미생성)

### R-DOCK: 화학적 거리 기준 확인
- H-bond 3.5Å, hydrophobic 4.0Å, pi-stacking 5.5Å, salt bridge 4.0Å, halogen bond 3.5Å
- SpatialHash 셀 크기(5.5Å)가 최대 거리 기준을 커버하는지 확인

### R-ALPHA: ADMET 기준 검증
- Lipinski RO5: MW<500, LogP<5, HBD<5, HBA<10
- Veber: TPSA<140Å², RotBonds<10
- PAINS 6 패턴이 실제 알려진 false-positive scaffolds와 일치하는지 확인

---

## 3. 검수자 공통 실수 방지

### 실수 1: "py_compile만으로 검증 완료" 주장
- **잘못**: 문법 오류만 잡음, 로직 오류는 미감지
- **올바른 방법**: py_compile + 기능 테스트 + 교과서/문헌 교차검증

### 실수 2: _source/ 동기화 확인 누락
- **잘못**: src/app/ 수정만 확인하고 _source/ 미확인
- **올바른 방법**: 수정된 모든 .py 파일의 _source/ 대응 파일 diff 확인

### 실수 3: PASS 판정 후 구체적 근거 미기록
- **잘못**: "PASS" 한 줄만 기록
- **올바른 방법**: 검증 방법 + 검증 데이터 + 비교 기준 모두 context_note.md에 기록

### 실수 4: 코드 수정 시도
- **잘못**: R-agent가 버그를 발견하고 직접 수정
- **올바른 방법**: FAIL 판정 + 구체적 수정 지침을 MM에 반환. 코드 수정은 절대 금지

---

## 4. Cascade #4 검수 지침

1. **3단계 검증 필수**: py_compile → _source/ sync → 기능 테스트
2. **PASS/FAIL 근거**: 검증 방법, 데이터, 비교 기준 모두 기록
3. **문헌 교차검증**: 화학 데이터는 CRC/Silverstein/Clayden 등 1차 출처와 대조
4. **거리/각도 기준**: 도킹, 오비탈 등 물리량은 표준값 범위 내인지 확인
5. **코드 수정 절대 금지**: 발견한 문제는 FAIL + 수정 지침으로만 보고
