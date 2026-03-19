# ChemGrid 자동 시각 피드백 루프 시스템
> 최종 업데이트: 2026-03-14

## 1. 시스템 개요

### 원리
PyQt6 `QWidget.grab()`을 사용하여 **화면을 뺏지 않고** 실제 렌더링 결과를 PNG로 캡처.
AI가 이미지를 분석하여 코드 수정 → 재캡처 → 재분석 루프 수행.

### 핵심 파일
- **테스트 스크립트**: `src/app/tests/test_visual_auto.py`
- **스크린샷 출력**: `src/app/tests/screenshots/`
- **결과 JSON**: `src/app/tests/screenshots/results.json`

### 실행 방법
```bash
cd C:/chemgrid/src/app
PYTHONIOENCODING=utf-8 C:/ProgramData/anaconda3/envs/chemgrid/python.exe tests/test_visual_auto.py
```

### 핵심 기법
```python
# 오프스크린 렌더링 (화면 안 뺏김)
win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
win.show()

# 애니메이션 클리핑 우회 (Lewis/Theory 전환 시 필수)
max_r = math.hypot(canvas.width(), canvas.height()) * 1.2
canvas._reveal_radius = max_r  # 원형 클리핑 해제

# 캡처
pixmap = widget.grab()
pixmap.save("screenshot.png", "PNG")
```

## 2. 테스트 커버리지 (36개 스크린샷)

### A. Drawing/Theory Layer 전자구름 (ESP)
| 테스트 | 파일 | 검증 포인트 |
|--------|------|------------|
| A01 | A01_initial | 빈 캔버스 |
| A02-03 | A02_ethane_draw, A03_ethane_theory | sp3 포화탄화수소 → 전자구름 없음 |
| A04 | A04_ethanol_theory | O에만 빨간 구름, C는 없음 |
| A05 | A05_benzene_theory | 방향족 전체 빨간 구름 |
| A06 | A06_propane_theory | sp3 → 전자구름 없음 |
| A07 | A07_manual_ethane_theory | 수동 그리기 → SMILES 자동인식 → 구름 없음 |

**ESP 색상 기준 (Gasteiger charge)**:
- ABS_SCALE = 0.35, NEUTRAL_ZONE = 0.15
- 음전하(δ-): RED (O, F, 음이온)
- 양전하(δ+): BLUE (C=O의 C)
- 중성: GREEN (|normalized| < 0.15)

### B. Lewis Structure (비공유전자쌍)
| 테스트 | 파일 | 검증 포인트 |
|--------|------|------------|
| B01/B01b | B01_water_lewis, B01b_water_lewis_zoom | H2O: O-H 2개 + LP 2쌍 |
| B02/B02b | B02_acetic_lewis, B02b_acetic_lewis_zoom | 아세트산: =O LP 2쌍, -OH LP 2쌍 + H |
| B03/B03b | B03_ammonia_lewis, B03b_ammonia_lewis_zoom | NH3: N-H 3개 + LP 1쌍 |

**Lewis 수정 내역**:
- [FIX-LEWIS] canvas.py: ESP 전자구름이 Lewis 모드에서 렌더링되던 버그 수정
- 3곳 수정 (LAYER 2 애니메이션, LAYER 3 메인, LAYER 4 Drawing)
- `self.view_state == "Theory"` 조건 추가

### C. 3D Popup
| 테스트 | 파일 | 검증 포인트 |
|--------|------|------------|
| C01 | C01_3d_popup | Ball&Stick 3D 구조, 결합측정 |
| C02_* | C02_spec_IR~UV-Vis | 5종 스펙트럼 전체 패널 채움 |
| C02_spec_IR_return | IR 복귀 크기 | 탭 전환 후 크기 유지 |
| C03 | C03_vibration_tab | 27개 진동모드 (경험적 계산) |
| C04_0~5 | C04_orbital_* | 6종 오비탈 모드 |
| C05 | C05_docking_tab | AutoDock Vina 도킹 UI |
| C06 | C06_ai_tab | AI 분석 탭 |

### D. PDF Export
- 6페이지 통합 PDF (구조식 + IR + Raman + 1H NMR + 13C NMR + UV-Vis)

### E. Reaction Pathway
- 복수 분자 Drawing → Theory 전환 → 반응 분석 버튼

### F-G. Complex Molecule (Aspirin)
- 13원자 아스피린 전체 레이어 + 3D + 오비탈

## 3. 현재 상태 및 남은 과제

### PASS (정상 동작)
- [x] sp3 포화탄화수소 전자구름 필터링
- [x] 에탄올/벤젠 ESP 색상
- [x] Lewis 비공유전자쌍 점 렌더링
- [x] Lewis에서 ESP 구름 제거
- [x] 스펙트럼 5종 크기 통일 (1178x245px)
- [x] 스펙트럼 탭 전환 후 크기 유지
- [x] PDF 6페이지 내보내기
- [x] 수동 그리기 → SMILES 인식 → 3D 전환
- [x] 3D Ball&Stick 정상 렌더링
- [x] 진동모드 27개 로드 (경험적 계산)
- [x] 도킹 UI 표시

### TODO (개선 필요)
- [ ] **전체 오비탈 표현**: 현재 원자별 개별 p-로브(dumbbell). 사용자 요청: "연결된 형태로 색이 그라데이션처럼 변화하며 전자밀도 표현" → ORCA cube 파일 기반 isosurface 필요
- [ ] **반응 경로 굽은 화살표**: 전자 이동을 유기화학 교재처럼 표현 (electron pushing arrows)
- [ ] **도킹 시뮬레이션 실제 실행**: AutoDock Vina 미설치 시 실제 도킹 불가
- [ ] **진동모드 결합 신축**: 현재 원자만 진동, 결합 길이 변화 미반영
- [ ] **Drawing 레이어 전자구름**: 현재 Drawing 모드에서도 ESP가 보였으나 비활성화됨

## 4. 피드백 루프 실행 방법

```
1. 테스트 실행:  python tests/test_visual_auto.py
2. results.json 확인 → errors 배열 체크
3. 스크린샷 PNG 파일을 Read 도구로 분석
4. 문제 발견 → 코드 수정 (src/app/ + _source/ 동시)
5. 다시 1번으로 돌아감
```

### 주의사항
- `_reveal_radius`를 강제 설정해야 Lewis/Theory 클리핑 우회됨
- `processEvents()` 최소 2회 호출 필요 (레이아웃 계산)
- PYTHONIOENCODING=utf-8 필수 (Windows cp949 인코딩 회피)
- `_source/`와 `src/app/` 양쪽 모두 수정 동기화 필수
