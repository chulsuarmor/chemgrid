# domain_reaction_anim — 3D 반응 메커니즘 애니메이션
> MM-REACTION_ANIM + Worker + Reviewer

## OWNED_FILES
- src/app/reaction_animation_engine.py (신규)
- src/app/popup_reaction_animation.py (신규)

## Worker: 보간 기반 반응 애니메이션 프레임 생성, 특수 반응(SN2/flip/양성자전달) 구현
## Reviewer: 전이상태 구조 화학 정확성 (Clayden/March 대조), 결합각/결합길이 검증
## 필수: skills/ 읽고 시작, 작업 후 mistakes.md + skills/ 갱신

## 핵심 기술
- RDKit EmbedMolecule + 선형 보간 (1차)
- ORCA IRC/NEB 궤적 파싱 (2차)
- QTimer 30ms 프레임 루프 (popup_3d 패턴 재사용)
- 전이상태: 점선 결합 표시
- 결합 변화: 색상 그라데이션 (회색→빨강 끊김, 회색→초록 형성)


## 팀 내부 QA 루프 (필수)
1. Worker 작업 완료 → MM이 Reviewer(검수자) spawn
2. Reviewer: 도메인 기준(체크리스트) 대조 → PASS/FAIL
3. FAIL → 구체적 수정 지시 + Worker 재spawn (MM 선에서 해결)
4. PASS → 감사팀에 자동 상신 (CT 개입 없음)
5. 3회 FAIL 후에도 미해결 → CT 에스컬레이션

## CT에 올리지 않는 것
- 사소한 버그 수정 (팀 내부에서 해결)
- 코드 스타일/포맷 문제
- py_compile 에러 (Worker가 직접 수정)
- 단순 반복 작업

