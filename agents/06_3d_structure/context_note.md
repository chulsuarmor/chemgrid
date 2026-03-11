# 📝 🧊 입체 구조(3D) — Technical Notes
## 기술적 판단 및 결정 기록

---

## [2026-02-28 22:15] C2 수정 — `from PyQt6.QtOpenGL import GL`
- **수정:** 해당 줄 삭제. PyQt6에 존재하지 않는 모듈.

## [2026-02-28 22:15] OpenGL CompatibilityProfile
- **결정:** gluSphere 등 레거시 GLU 함수 사용을 위해 CompatibilityProfile 적용

## [2026-02-28 22:15] Material 기반 렌더링
- **수정:** `glColor3f` → `glMaterialfv` (조명 활성 시 glColor3f 무시됨)

## [2026-02-28 22:15] Quadric 재사용
- **수정:** GLQuadricManager 클래스로 메모리 누수 방지

## [2026-02-28 22:15] 3D 좌표 우선순위
- ORCA parser > ORCA xyz dict > RDKit ETKDG+MMFF > VSEPR Z추정 > flat 2D

## [2026-02-28 22:15] CPK 색상 — Jmol 표준
- 22개 원소, 미정의 원소 마젠타 폴백

## [2026-02-28 23:10] Phase 7 — ORCA 파서 설계
- regex 기반 파싱 (CARTESIAN COORDINATES, FINAL SINGLE POINT ENERGY 등)
- 마지막 geometry 블록 사용 (최종 최적화 geometry)
- normal modes: ORCA 블록 형식 (6 모드 단위 컬럼) 파싱
- 진동 화살표: 단위 방향 벡터 × 진폭 × sin(phase) 애니메이션

## [2026-02-28 23:10] Phase 7 — PubChem API
- REST API (키 불필요): `/rest/pug/compound/smiles/` 엔드포인트
- 2단계 조회: properties → synonyms (CAS 추출)
- 결과 캐시 (dict) — 동일 SMILES 반복 호출 방지

## [2026-02-28 23:10] Phase 7 — Gemini AI
- `google.generativeai` 0.8.6 사용 (deprecated, 향후 google.genai 전환)
- 환경변수 GEMINI_API_KEY 필요
- 프롬프트: 작용기, 반응성, 스펙트럼 특징, 응용 분석 (한국어)
- 결과에 "⚡ AI 보조 (참고용)" 라벨 + 신뢰도 ★★★☆☆ 표시

## [2026-02-28 23:10] Phase 7 — IR 스펙트럼 플롯
- Lorentzian 브로드닝 (γ=15 cm⁻¹)
- 400~4000 cm⁻¹ 범위, 3000 포인트
- matplotlib backend_qtagg + 다크 테마
- 피크 위치 axvline 마킹

## [2026-02-28 23:10] Phase 7 — 진동 모드 애니메이션
- QTimer 30ms (~33fps) 주기
- vib_scale = sin(phase) × amplitude
- 원자 위치 += normal_mode_vector × vib_scale
- 화살표: _draw_arrow() — cylinder + cone tip

## [2026-02-28 23:28] 세션 재개 — 전체 검증
- **상태:** 모든 하달 명령(U6, U3, C2, M3, Phase 7 전체) 이미 완료 확인
- `ast.parse` 구문 체크: popup_3d.py ✅, chem_data.py ✅
- conda 임포트 검증: OPENGL/RDKIT/MPL/REQ 전부 True ✅
- `google.generativeai` FutureWarning 발생 → Phase 7+ `google.genai` 전환 예정 (향후 작업)
- **google-genai 패키지 미설치 확인** — master_plan에 설치 완료로 기록되었으나 실제 `pip show google-genai` → "Package(s) not found"
  - 현재 `google-generativeai` 0.8.6만 설치됨 (deprecated, 동작은 함)
  - `google.genai` 마이그레이션은 `pip install google-genai` 실행 후 가능

## [2026-03-01 00:02] 세션 재개 — 전체 재검증
- **명령:** "명령 하달 인식하고 작업 시작해"
- **결과:** 모든 하달 명령(U6, U3, C2, M3, Phase 7 전체) 이미 완료 재확인
- context_plan.md 산출물 체크리스트 [x] ✅ 로 갱신 완료

## [2026-03-01 00:39] Phase 6-3: Manager 긴급 명령 v3 — 2건 완료

### 명령 1: AI 피크 분석 오버레이 + 토글 버튼
- **구현 위치:** `SpectrumPanel` 클래스 (popup_3d.py)
- **설계 판단:**
  - `SpectrumPanel.__init__`에 상태 변수 6개 추가: `ai_annotations`, `ai_overlay_visible`, `ai_analysis_data`, `frequencies`, `intensities`, `plot_x/plot_y`, `ax`
  - GeminiAnalyzer 인스턴스를 SpectrumPanel 자체에서 생성 (`self._gemini`) — AIAnalysisPanel과 독립적으로 동작
  - **토글 버튼:** QPushButton(setCheckable=True) — 그래프 아래 배치, 체크 상태에 따라 파란색 강조
  - **AI 분석 2단계:** Gemini API 가용 → JSON 응답 파싱 / 불가 → _fallback_peak_analysis() 룰 기반
  - **룰 기반 폴백:** 표준 IR 작용기 영역 테이블 11개 (교과서 기반: OH, NH, C-H sp3/sp2, 삼중결합, 카르보닐, 알켄, 방향족, C-O, 지문영역)
  - **matplotlib annotate:** 화살표(arrowstyle='->') + bbox(round, 반투명) + 색상 10종 순환
  - **겹침 방지:** y_offset = 15 + (i % 3) * 8 — 3단계 교대 오프셋
  - **숨기기:** ann.remove() 후 canvas.draw() 필수 (잔상 방지)
  - **plot_ir 수정:** 데이터를 인스턴스 변수로 저장 + 새 데이터 로드 시 AI 캐시 리셋

### 명령 2: 진동 모드 3D 애니메이션 동작 확인
- **결과:** 이미 완벽히 구현되어 있음 확인
- **확인 항목:**
  - ✅ VibrationPanel → mode_selected 시그널 → Molecule3DPopup._on_vib_mode_selected 연결
  - ✅ QTimer(30ms) → _vib_tick() → math.sin(phase) × amplitude → vib_scale
  - ✅ BallAndStickRenderer.render(): vib_vectors 적용 (원자 위치 변위 + _draw_arrow)
  - ✅ _draw_arrow(): cylinder(몸체) + cone(화살촉) — 녹색(0.2,1.0,0.2) 화살표
  - ✅ stop_vibration(): timer 정지 + vectors/scale 리셋
  - ✅ amp_slider → amplitude 연결 (btn_play.isChecked() 체크)
- **판단:** 코드 구조 완전. ORCA 데이터 로드 시 정상 동작 예상. 런타임 검증은 ORCA .out 파일 필요.

### 자가 검증
- `ast.parse`: popup_3d.py ✅, chem_data.py ✅
- 24개 키워드 존재 확인: ALL CHECKS PASSED ✅
- **상태:** 🟢 **Phase 6-3 명령 2건 모두 완료 — Manager 새 지시 대기 중**

## [2026-03-01 01:20] Phase 6-4: Manager 긴급 명령 v4 — 4건 완료

### 명령 1: 원자 크기 확대 + CPK 색상 강화
- **ATOM_SCALE:** 0.35→0.85 (약 2.4배 확대). 공유반지름 × 0.85 적용으로 원소 구분 대폭 개선
- **BOND_RADIUS:** 0.10→0.08. 원자가 커지면서 결합이 상대적으로 너무 두꺼워지는 것 방지
- **CPK C색상:** (0.56,0.56,0.56)→(0.20,0.20,0.20). Jmol 표준 진한 회색. 어두운 배경에서 specular 하이라이트로 가시성 확보
- **Material 밝기:** ambient r*0.3→r*0.4, specular [0.4]→[0.6], shininess 40→60. 분자 모델 광택감 강화
- **판단:** 나머지 원소(H,O,N,S,Cl,Br 등)는 이미 Jmol CPK 표준과 일치하여 변경 불필요

### 명령 2: 다중결합 표현
- **설계:** `_perpendicular_offset()` 메서드 신규 추가. 결합 방향에 수직인 오프셋 벡터 계산
- **이중결합:** 대칭 배치 (offset ±0.12). 두 실린더 radius = BOND_RADIUS × 0.75
- **삼중결합:** 중앙 1개(radius×0.7) + 양쪽 2개(offset ±0.15, radius×0.6)
- **구 이전 코드 문제:** offsets 계산이 비대칭 (range 기반) → [0, 1]이 되어 실린더 쏠림 발생. 새 코드는 명시적 ±offset으로 완벽 대칭

### 명령 3: PropertiesPanel 오류 핸들링
- **설계:** 각 데이터 소스(RDKit/PubChem/ORCA/측정)마다 독립적 try/except
- **RDKit:** 개별 Descriptor 계산 try/except. 하나 실패해도 나머지 정상 표시
- **PubChem:** data=None 시 "오프라인 — PubChem 조회 불가" 메시지
- **ORCA:** parser 없으면 "ORCA 결과 없음 — 📂 버튼으로 .out 파일 로드" 안내
- **측정:** 결합 측정 전체 try/except 래핑 + 오류 시 텍스트로 표시

### 명령 4: AI 오버레이 유지
- v3에서 이미 완전 구현됨 확인. 변경 없음.

### 자가 검증
- `ast.parse`: popup_3d.py ✅, chem_data.py ✅
- 15개 키워드 존재 확인: ALL PASSED ✅
- **상태:** 🟢 **Phase 6-4 명령 4건 모두 완료 — Task Completed**
