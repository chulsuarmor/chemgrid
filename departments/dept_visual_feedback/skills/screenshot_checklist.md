# 스크린샷 검증 체크리스트
> dept_visual_feedback Worker가 시각적 검증 시 사용하는 체크리스트

## 실행 방법
```bash
cd /c/chemgrid/src/app && PYTHONIOENCODING=utf-8 python tests/test_visual_auto.py
```

## 36개 시나리오 판정 기준

### ESP 전자구름
- [ ] sp3 필터: ethane/propane = 구름 없음
- [ ] 색상: ethanol O=red, C=O C=blue
- [ ] Lewis 모드에서 ESP 구름 표시되면 FAIL (Theory만 허용)

### Lewis 론쌍
- [ ] H2O: O에 론쌍 2쌍
- [ ] 아세트산: O에 론쌍
- [ ] NH3: N에 론쌍 1쌍

### 스펙트럼
- [ ] 5종 크기 일관성: 1178x245px (±10px 허용)
- [ ] 탭 전환 후 크기 보존

### 3D 뷰어
- [ ] Ball&Stick 렌더링 정상
- [ ] 결합 길이 측정값 표시

### 진동 모드
- [ ] 27+ 모드 표시
- [ ] 원자 진동 애니메이션

### 도킹
- [ ] RCSB PDB 검색 UI
- [ ] Vina 스코어 표시

### PDF
- [ ] 6페이지 출력 완성

### 궤도함수
- [ ] 6가지 모드 렌더링

## 판정 기준
- PASS: 기대 요소 모두 렌더링, 레이아웃 정상
- FAIL: 누락, 겹침, 잘못된 색상, 크기 불일치
- WARN: 미세 차이 (폰트 등) → 수동 확인 필요

## 이미지 읽기
Read 도구로 .png 파일을 열어 시각적으로 확인합니다.
Claude는 멀티모달이므로 이미지 내용을 직접 판정할 수 있습니다.
