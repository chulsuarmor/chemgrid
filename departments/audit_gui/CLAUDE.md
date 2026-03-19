# audit_gui — GUI 실행 감사팀
> 3인 체제: 팀장(TL) + 실행관(E1) + 분석관(A1)

---

## 역할
**실제로 앱을 띄우고 모든 기능을 조작하여 스크린샷을 캡처**하고,
캡처된 이미지를 분석하여 시각적 정확성을 판정.
코드를 보지 않고 **화면만** 검증한다 (사용자 시점 블랙박스 감사).

## 팀 구성

### 팀장 (TL-GUI)
- E1의 스크린샷과 A1의 분석 결과를 **교차확인**
- 스크린샷에서 A1이 놓친 문제를 독립적으로 재검토
- 최종 감사 보고서 서명 및 CT 상신
- HTML 리포트 생성 감독
- ⛔ 직접 코드 수정 금지

### 실행관 (E1-EXEC)
- **실제 디스플레이에서** 앱을 실행 (headless 금지)
- 모든 기능을 순차 조작하며 스크린샷 캡처
- **필수 캡처 체크리스트** (아래 참조)
- 스크린샷을 `screenshots/gui_audit_YYYYMMDD/` 에 저장
- 캡처 시 파일명에 분자명+기능명 포함 (예: `benzene_pi_orbital.png`)

### 분석관 (A1-ANALYZE)
- E1이 캡처한 스크린샷을 **1장씩 열어서 확인**
- 각 스크린샷에 대해 판정:
  - 3D 구조가 보이는가? (빈 화면/검은 화면 아닌가?)
  - 오비탈 로브가 올바른 색상(+blue/-red)으로 표시되는가?
  - 결합 위치가 정확한가?
  - 텍스트가 깨지지 않았는가?
  - 스펙트럼 그래프에 피크가 있는가?
- pixel 분석: 3D viewport 영역의 색상 다양성 확인
- 판정 결과를 `evidence/gui_analysis_YYYYMMDD.md`에 기록

## 필수 캡처 체크리스트 (E1이 반드시 수행)

### A. 2D 캔버스 (5분자 × 3뷰 = 15장)
- [ ] benzene: Drawing / Theory / Lewis
- [ ] aspirin: Drawing / Theory / Lewis
- [ ] caffeine: Drawing / Theory / Lewis
- [ ] ferrocene: Drawing / Theory / Lewis
- [ ] ethanol: Drawing / Theory / Lewis

### B. 3D 팝업 — Ball-and-Stick (3장)
- [ ] benzene 3D 기본 뷰
- [ ] aspirin 3D 기본 뷰
- [ ] ferrocene 3D (배위결합 점선)

### C. 오비탈 시각화 (6장) ← 가장 중요
- [ ] benzene π 오비탈 (sp2) — 파란/빨간 로브 수직 확인
- [ ] benzene 혼성 오비탈 (자동)
- [ ] ethanol σ/π 오비탈 분해
- [ ] ferrocene d-오비탈 (있는 경우)
- [ ] ORCA cube 파일 분자 오비탈 (있는 경우)
- [ ] 오비탈 OFF 상태 비교 캡처

### D. 스펙트럼 (5장)
- [ ] benzene IR 스펙트럼
- [ ] benzene Raman 스펙트럼
- [ ] aspirin ¹H NMR
- [ ] caffeine ¹³C NMR
- [ ] benzene UV-Vis

### E. 진동 모드 (2장)
- [ ] benzene 진동 모드 탭 (모드 선택 시 애니메이션)
- [ ] aspirin 진동 모드 (bond strain 색상)

### F. 도킹 (3장)
- [ ] aspirin + COX-2 도킹 결과
- [ ] 수용체 정보 패널
- [ ] 상호작용 3D 뷰 (수소결합 파란선 등)

### G. 합성/반응 (2장)
- [ ] aspirin 역합성 경로
- [ ] benzene 반응 메커니즘 (화살표)

### H. PDF 저장 (1장 + 파일)
- [ ] PDF 내보내기 → 파일 열어서 확인

**총 최소 37장**

## 증거 없는 PASS는 자동 FAIL
스크린샷 없이 "GUI 정상"이라고 보고하면 **자동 FAIL** 처리.
반드시 `screenshots/` 폴더에 PNG 파일 + `evidence/`에 분석표가 있어야 유효한 감사.

## 실행 방법
```bash
# 앱 실행 (실제 디스플레이 필수)
/c/ProgramData/anaconda3/envs/chemgrid/python.exe src/app/draw.py

# 자동화 테스트 (2D + 일부 팝업)
PYTHONIOENCODING=utf-8 /c/ProgramData/anaconda3/envs/chemgrid/python.exe src/app/tests/test_visual_auto.py

# 3D 전용 테스트 (OpenGL 필요, headless 불가)
/c/ProgramData/anaconda3/envs/chemgrid/python.exe src/app/tests/test_visual_3d.py
```

## 세션 프로토콜
1. CLAUDE.md 읽기
2. context_list.md → 현재 감사 요청 확인
3. E1: 앱 실행 → 체크리스트 순회 → 스크린샷 캡처
4. A1: 스크린샷 1장씩 열어 판독 → 분석표 작성
5. TL: 교차확인 → 서명 → HTML 리포트 생성
6. context_list.md + evidence/ + screenshots/ 업데이트 → 세션 종료


## 감사 자동 트리거 (v3 업데이트)
- MM이 "내부 QA PASS" 선언 시 자동으로 감사 상신 수신
- CT가 수동 트리거하지 않아도 됨
- 감사 FAIL → MM에 직접 반려 (CT 경유 불필요)
- 감사 PASS → CT에 최종 보고
- CT 월권 감사는 항상 수행 (감사팀 = CT 직속 상위)

