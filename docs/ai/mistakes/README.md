# mistakes/ 재귀 계열화 (2026-04-22)

## 언제 무엇을 읽는가?
- 모든 작업 시작 전 → `docs/ai/mistakes.md` 인덱스 (목차)
- 특정 코드 도메인 작업 시 → 관련 계열 폴더 전체 (README.md + 모든 .txt)

## 현재 계열 (7개)
1. rendering_regression/ — src/app/renderer.py, canvas.py, popup_3d.py 수정 시 (5건)
2. path_destruction/ — 파일 이동/삭제/rename 시 (1건)
3. hook_bypass/ — .claude/hooks/, Agent spawn, 권한 변경 시 (4건)
4. workflow_serial/ — Worker 분배, 감사 호출, Ralph Loop 시 (2건)
5. orca_remote/ — ORCA 실행, WSL, 배포 시 (3건)
6. context_exhaustion/ — 세션 10시간+, 장기 루프 시 (1건)
7. misc/ — 기타 (M148~M155 등)

## 신규 사고 기록 규칙
- 새 M번호 → 적절한 계열 폴더 선택 → 짧은 txt (200자 이내)
- 계열에 포함 안되면 misc/에 먼저 넣고, 3건 이상 누적되면 신규 계열 분리
- 기록 후 docs/ai/mistakes.md 인덱스 하단 "전체 매핑 테이블"에 추가
