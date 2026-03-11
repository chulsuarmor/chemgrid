# 📋 🧊 입체 구조(3D) — Task List
## 최종 업데이트: 2026-03-01 01:20

### Phase 6-1A: 기본 리팩토링 (완료)
- [x] C2: `from PyQt6.QtOpenGL import GL` 제거
- [x] OpenGL CompatibilityProfile 수정
- [x] glMaterialfv 기반 재질 색상 렌더링
- [x] 실린더 회전 수학 수정
- [x] GLU Quadric 재사용/cleanup
- [x] 줌 메커니즘 수정 (scale 기반)
- [x] 우클릭 팬(Pan) 구현
- [x] M3 수정: 좌표 우선순위 (ORCA > RDKit > VSEPR > 2D)
- [x] QPainter 2.5D 폴백
- [x] Avogadro 스타일 다크 UI + 2광원 조명

### Phase 7: 통합 3D 분석 팝업 (완료)
- [x] ORCA .out 파서 (OrcaOutputParser)
- [x] PubChem API 클라이언트
- [x] Gemini AI 분석기
- [x] 탭 패널 UI (속성/스펙트럼/진동모드/AI분석)
- [x] 진동 모드 3D 화살표 + QTimer sin 애니메이션
- [x] 결합 길이/각도 측정 도구
- [x] ORCA .out 파일 로드 다이얼로그
- [x] 구문 체크 통과 (ast.parse)
- [x] conda 환경 임포트 검증

### Phase 6-3: Manager 긴급 명령 v3 (완료)
- [x] AI 피크 분석 오버레이 + 토글 버튼
- [x] 진동 모드 3D 애니메이션 동작 확인
- [x] AST 검증 + 24개 키워드 확인

### Phase 6-4: Manager 긴급 명령 v4 (완료 ✅)
- [x] **명령 1: 원자 크기 확대 + CPK 색상 강화**
  - [x] ATOM_SCALE 0.35→0.85 (약 2.4배 확대)
  - [x] BOND_RADIUS 0.10→0.08 (원자와 대비)
  - [x] CPK C색상: (0.56,0.56,0.56)→(0.20,0.20,0.20) 진한 회색
  - [x] Material ambient r*0.3→r*0.4, specular 0.4→0.6, shininess 40→60
- [x] **명령 2: 다중결합 표현**
  - [x] _perpendicular_offset() 수직 오프셋 벡터 계산 메서드 신규
  - [x] 이중결합: 2개 대칭 평행 실린더 (offset=0.12)
  - [x] 삼중결합: 중앙 1개 + 양쪽 2개 (offset=0.15)
- [x] **명령 3: PropertiesPanel 오류 핸들링 개선**
  - [x] update_rdkit(): 개별 Descriptor try/except 감싸기
  - [x] update_pubchem(): "오프라인 — PubChem 조회 불가" 메시지
  - [x] update_orca(): "ORCA 결과 없음 — 📂 버튼으로 .out 파일 로드" 메시지
  - [x] update_measurements(): 예외 안전 래핑
- [x] **명령 4: AI 오버레이 유지** (v3에서 이미 완료 확인)
- [x] AST 검증 통과 (popup_3d.py + chem_data.py)
- [x] 15개 키워드 존재 확인: ALL PASSED ✅

### 향후 (Phase 7+)
- [ ] PDF 내보내기 (대학 분석장비급 레이아웃)
- [ ] 원자 클릭 → 정보 팝업 (hover/select)
- [ ] Wire-frame 렌더링 모드
- [ ] google.genai 패키지 전환
- [ ] PubChem 조회 비동기화 (QThread)

### 블로커
- (없음)

### 검증 기록
- [2026-02-28 23:28] Phase 7 검증 완료
- [2026-03-01 00:39] Phase 6-3 검증 완료
- [2026-03-01 01:20] Phase 6-4 검증 완료
  - `ast.parse`: popup_3d.py ✅, chem_data.py ✅
  - 15개 키워드 존재 확인: ALL PASSED ✅
  - **v4 명령 4건 모두 완료**
