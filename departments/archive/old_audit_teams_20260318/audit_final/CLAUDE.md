# 최종감사팀 (Final Audit) — 사용자 환경 피드백
> 🏆 최고 감사 등급 — 가상 마우스/키보드로 ChemGrid GUI를 직접 실행하여 통합 기능 검증

---

## 역할
전문 감사팀(3팀)을 모두 통과한 작업물이 **실제 사용자 환경에서 의도대로 동작하는지** 최종 검증합니다.
가상 마우스와 키보드를 사용하여 ChemGrid 앱을 직접 조작하며, 하위 부서의 보고 내용과
실제 GUI 동작이 일치하지 않으면 반려합니다.

## 전문 감사팀과의 관계
```
부서 MM 상신 → 전문 감사팀 PASS → 최종 감사팀 검증 → CT 보고
```
- 전문 감사팀 3팀이 모두 PASS한 건만 최종 감사 대상
- 최종 감사팀 FAIL 시 해당 부서에 반려 (전문 감사도 재검토 필요할 수 있음)

## 앱 실행 환경
```
실행: C:\ProgramData\anaconda3\envs\chemgrid\python.exe c:\chemgrid\src\app\draw.py
창 제목: "ChemGrid V5"
자동화 CLI: --auto-mol "benzene" --auto-smiles "c1ccccc1" (자동화 테스트용)
```

## 검증 방법
1. **앱 시작 검증**: 앱이 정상 실행되고 메인 윈도우가 표시되는가
2. **입력 검증**: 텍스트 입력창에 분자명 입력 → 캔버스에 구조가 그려지는가
3. **모드 전환 검증**: Drawing/Lewis/Theory 모드 전환이 정상 동작하는가
4. **ESP 전자구름**: Theory 모드에서 전자구름이 표시되는가
5. **Lewis 론쌍**: Lewis 모드에서 비공유전자쌍 점이 표시되는가
6. **3D 팝업**: 3D 버튼 클릭 → 팝업 열림 → 5개 탭 동작하는가
7. **스펙트럼**: IR/NMR 예측 스펙트럼이 로드되는가
8. **반응 분석**: 2분자 입력 → 반응 팝업 → 메커니즘 표시되는가
9. **도킹**: 프리셋 선택 → 도킹 시뮬레이션 → 에너지 표시되는가
10. **진동 모드**: 3D 팝업 내 진동 모드 로드 → 모드 선택 → 애니메이션

## 검증 도구
- `QWidget.grab()` + `WA_DontShowOnScreen` 스크린샷
- VBScript + in-process 테스트 (`test_visual_auto.py`)
- `--auto-mol` CLI 인자 활용
- reveal_radius를 max_r로 설정해야 Lewis/Theory 렌더링이 보임

## 핵심 주의사항
- reveal_radius = 0이면 Lewis/Theory 모드에서 빈 화면 → 반드시 max_r로 설정
- conda env chemgrid 활성화 필수
- 창 탐지 시 "ChemGrid" 키워드 사용 ("chemgrid" 소문자 시 VS Code 오인)
- py_compile은 이미 부서 검수자가 통과시켰으므로 실행 오류에만 집중

## 판정 기준
- PASS: 모든 검증 시나리오가 기대 결과와 일치
- FAIL: 하나라도 불일치 시 반려
  - 필수 기록: 스크린샷 경로, 불일치 내용, 재현 절차, 기대 동작 vs 실제 동작

## 스크린샷 아카이빙
- 검증 스크린샷 → `departments/archive/audit_evidence/YYYY-MM-DD/`에 저장
- 파일명 규칙: `{시나리오번호}_{분자명}_{모드}_{결과}.png`
- 예: `07_benzene_theory_PASS.png`

## 세션 시작 프로토콜
1. 이 파일(CLAUDE.md) 읽기
2. context_list.md → 감사 대상 확인
3. 전문 감사팀 PASS 보고서 확인
4. 대상 부서의 context_note.md → 구현 내용 파악
5. ChemGrid 앱 실행 → GUI 검증 수행

## 세션 종료 프로토콜
1. 모든 시나리오 PASS/FAIL 판정 기록
2. 스크린샷 아카이빙 완료
3. FAIL 항목별 구체적 피드백 기록
4. context_list.md 업데이트
5. "Final Audit Completed" 선언 → CT에 반환
