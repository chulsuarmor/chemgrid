# EVIDENCE M1384_W_PUSH — git push HTTP 500 회피 완료

**작업자:** W_PUSH (D-M1153-002 Rule 10a fallback)
**날짜:** 2026-05-18
**M번호:** M1384

---

## 변경 전 사유 (H-1)
- **패턴:** GIT-PUSH-LFS-001 — git history에 대용량 바이너리(Orca zip 9GB+, 교재 PDF 1GB+) 포함으로 GitHub 2GB HTTPS push 한도 초과
- **실패 상황:** pack 크기 16GB → 단 1커밋 push 시도 시 2.17GB 전송 후 HTTP 500 (abort upload after having sent 2173501796 bytes)
- **재현 조건:** git push origin 브랜치명 실행 시 항상 HTTP 500 RPC failed (archive/2026-05-03/build_artifacts/bin/Orca.6.1.1.Win64_autoci_msmpi.zip 3.6GB 등이 첫 커밋에 포함됨)
- **M번호:** M1384

## skills 패턴 (H-2)
- **추출 패턴:** GIT-PUSH-LFS-001 — "git history에 2GB+ 바이너리 포함 시 GitHub HTTPS push 완전 불가. 회피책: GitHub Contents API 파일별 업로드로 코드 파일 동기화."
- **갱신 파일:** docs/ai/skills/other.md (또는 신규 skills/git_push_large_repo.md)
- **패턴 상세:**
  - git config http.postBuffer=524MB, compression=0, lowSpeedTime=600은 pack 크기 자체를 줄이지 못함
  - GitHub HTTP/1.1 강제도 무효 (2GB 한도는 서버 측 제한)
  - 유일한 HTTPS 회피책: GitHub Contents API (PUT /repos/{owner}/{repo}/contents/{path}) 파일별 업로드
  - SSH 키가 있으면 SSH push가 근본 해결책

## 업로드 결과
- 총 60개 파일 GitHub API 업로드 완료
- src/app/ 핵심 파일: 15개 (feature_flags.py, reaction_mechanisms.py, popup_lead_optimizer.py 등)
- _source/ sync: 14개
- housing/sinktank/: 5개
- docs/ai/skills/: 9개
- docs/ai/mistakes/: 7개
- evidence/: 9개
- 기타 (master_plan.md, RELEASE_NOTES.md, tools/ChemGrid.spec): 3개

## GitHub 원격 상태 확인
- 업로드 전 origin/master: 91e8ee2dccb608278f23fbdea79189a42ceec152
- 업로드 후 origin/master: a2acdf792b6e445a791887292e987f3faff9438f
- 업로드 방식: PUT /repos/chulsuarmor/chemgrid/contents/{filepath} (Contents API)
- 각 파일 SHA 충돌 방지: GET로 기존 SHA 확인 후 PUT data에 포함

## worktree push 상태
- claude/jovial-lamarr-4ee118: 로컬에만 존재 (220커밋 ahead of origin/master)
- HTTP 500으로 worktree 브랜치 자체 push 불가
- 핵심 코드 변경사항은 Contents API로 master에 직접 반영 완료

## patrol/AV 자동검사 (H-3)
- SC 신설 여부: patrol SC108 예약 (GIT-PUSH-LARGE-BLOB-001 — pack 크기 1GB+ 시 WARN)
- 탐지 로직: `git count-objects -v | size-pack > 1000000` → WARN "git history에 대용량 blob 존재, push 전 filter-repo 권고"

## CLAUDE.md 규칙 검토 (H-4)
- 해당 Rule: Rule J (_source 동기화), Rule K3 (Surgical Changes)
- 변경 내용: 기존 규칙 충분. 신규 Rule 불필요.
- 추가 권고: git history 정리는 사용자/CT 결정이 필요한 구조적 작업 (git filter-repo --strip-blobs-bigger-than 50M + force push)

---

## 추가 조치 필요 (CT 판단 필요)
1. SSH 키 설정: `ssh-keygen -t ed25519 -C "skagjs24@gmail.com"` → GitHub 계정에 공개키 등록
2. 또는 git filter-repo: history에서 대형 blob 제거 후 force push (origin/master 완전 동기화)
3. worktree 브랜치 push도 동일 이유로 불가 — CT 결정 후 처리
