# Process / Testing / Other Mistakes (58 entries)
> 2 critical serial violations (audit bypass -> user got broken deliverables).
> Key lesson: Worker -> audit 3 teams -> AV -> CT -> user. Skip any step = instant reject.
> except:pass 262 incidents. SMILES pipeline loss. See: CLAUDE.md Rule A, M, T

### [2026-05-18] M1384 — git push HTTP 500 RPC failed (GIT-PUSH-LFS-001)
- **상황:** W_PUSH 임무. git config postBuffer=524MB/compression=0/lowSpeedTime=600 설정 후에도 HTTP 500 RPC failed 반복.
- **실수 (시스템 결함):** git history에 Orca zip (3.6GB/3.5GB/1.9GB) + 교재 PDF 포함으로 pack 16GB. GitHub HTTPS 2GB 한도 초과. 단 1커밋 push도 2.17GB 전송 후 abort.
- **올바른 방법:** (1) Contents API PUT 파일별 업로드 (60개 완료). (2) 근본 해결: git filter-repo + force push (CT 결정). (3) 장기: SSH 키 등록.
- **체화:** GITHUB-API-FALLBACK-001 패턴 등록. SC108 pack 1GB+ WARN 예약.

### [2026-05-18] M1393 — README worktree 신규 생성 + orphan branch commit-tree 패턴
- **상황:** D-M1153-002-W_README. worktree `jovial-lamarr-4ee118`에 README.md 없음. HEAD 커밋 오브젝트 missing(51d3a671 dangling). git status "fatal: bad object HEAD".
- **실수:** `git add` + `git commit` 불가. `git write-tree` 실패 (인덱스 오브젝트 missing).
- **올바른 방법:** (1) `git hash-object -w` 로 새 파일 등록 → (2) `git read-tree master` 로 베이스 인덱스 로드 → (3) `git update-index --add --cacheinfo` → (4) `git write-tree` → (5) `git commit-tree <tree> -p <master_sha>` → (6) `git update-ref refs/heads/<branch> <new_commit>`. 이후 `git read-tree master` 로 main repo 인덱스 복구.
- **체화:** worktree orphan 상태에서 commit-tree 직접 사용 패턴 확립.

### [2026-05-18] M1394 — _source DESYNC 10파일 재누적 → W_SYNC2 재dispatch (허위 동기 선언)
- **상황:** W_SYNC (1차) 처리 후 W184/W188/W189/W191/W7r/W_FONT 변경분이 _source에 흡수 안 됨. audit_integration M1375 REJECT 블로커. 10파일 DIFFER 잔존.
- **실수:** W184/W189/W191 commit message에 "_source 동기화 완료" 허위 선언. filecmp 미검증 후 commit.
- **올바른 방법:** src/app/*.py 수정 즉시 shutil.copy2 + filecmp.cmp(shallow=False) IDENTICAL 확인 후 같은 commit에 포함. commit message에 diff -q IDENTICAL N/N 근거 명시.
- **체화:** SOURCE-SYNC-DEFER-001 패턴 반복. W_SYNC2 결과: 10/10 IDENTICAL, py_compile 95/95 PASS.

### [2026-05-18] M1389 — _source DESYNC 6파일 누적 → COND_PASS BLOCKING (W_SYNC 별도 dispatch)
- **상황:** D-M1153-002 audit_theory M1376 COND_PASS — src/app 6파일 수정 후 _source 미동기화. W_SYNC 별도 dispatch 필요.
- **실수:** Rule J "_source 즉시 복사" 미이행. Worker가 src/app commit 후 _source sync를 빠뜨림.
- **올바른 방법:** src/app/*.py 수정 즉시 shutil.copy2 후 diff -q IDENTICAL 확인을 같은 commit에 포함.
- **체화:** SOURCE-SYNC-DEFER-001 패턴 재확인. MENU.md Pre-work diff -q 항목 준수 의무.

### [2026-05-18] M1385 — deploy trigger 사전 준비 패턴 (W_BUILD 대기)
- **상황:** W_DEPLOY rc2 — W_BUILD 완료 전 gh release create 실행 차단 필요.
- **패턴:** precondition 3종(log존재+exe mtime>BUILD_SPAWN_EPOCH+exe size>=100MB) 미충족 시 exit=2 반환. silent return 금지(Rule M).
- **올바른 방법:** release_trigger_rc2.py precondition → create → upload → sha256 → evidence 순. Rule JJ creationflags=CREATE_NO_WINDOW 필수.
- **체화:** deploy 스크립트는 항상 precondition 3종 + Rule JJ + exit코드 의미 명시.

### [2026-05-18] M1379-W193 — engine_dashboard.html data:image/svg hook 차단 (M1359 미적용)
- **상황:** W193 임무 — 38 엔진 health dashboard HTML 생성. 초안 작성 시 img src를 data:image/svg+xml URI로 삽입.
- **실수:** user_env_verify.py hook L82 `HTML_PLACEHOLDER_OR_DATA_SVG_PROMOTION` 즉시 차단. M1359 교훈("data:image/* 완전 금지") 미적용.
- **올바른 방법:** housing/evidence/D-M1034-W32/captures/*.png 실존 파일 상대경로 사용. hook 차단 후 즉시 전체 data URI → 실존 PNG 교체.
- **체화:** M1359 체화 완료 확인 의무 — engine_dashboard 등 독립 HTML도 동일 rule 적용.

### [2026-05-18] M1383 — SHELL-CLEANUP-001: evidence 빈 디렉터리 누적 방치 패턴
- **상황:** W_CLEAN 임무 — D-M1153-002 cycle 진행 중 housing/evidence에 빈 디렉터리(SHELL) 10건 발견. W20r INDEX 기준 21건 검출 중 이미 채워진 11건 제외. D-M1091(6건)/D-M1090(2건) archive 이동, M1376/M1382 .gitkeep 처리.
- **실수:** Worker가 evidence 디렉터리 mkdir 후 내부 파일 기록 없이 종료. 빈 디렉터리가 git에 잔존하여 FP-38 깡통 패턴 누적. M1366(evidence SHELL 21건)에서 최초 기록되었으나 정리 Worker 미발동.
- **올바른 방법:** evidence 디렉터리 생성 즉시 evidence.md 또는 .json 1건 이상 기록. 완료된 cycle (D-M1091/D-M1090)의 SHELL은 archive/YYYY-MM-DD/SHELL_cleanup_M번호/ 이동 후 MANIFEST.md 작성.
- **체화:** SHELL-CLEANUP-001 패턴 — evidence 생성 즉시 내부 파일 필수. patrol.py evidence_shell_check SC 신설 권고. H-4: Rule V 완료 조건에 "evidence 파일 1건+" 추가 검토.

### [2026-05-18] M1371 — tools/ChemGrid.spec excludes=[] 공백 패턴
- **상황:** W192 PyInstaller spec audit — tools/ChemGrid.spec의 excludes 리스트가 완전히 비어 있음. torch(1164MB), transformers(86MB), pyarrow(84MB) 등 ML/dev 패키지가 env에 설치되어 있어 빌드 시 번들될 위험.
- **실수:** spec 신규 생성 시 기본 exclude list 없이 `excludes=[]` 그대로 방치. ChemGrid_Lite.spec은 잘 채워져 있으나 tools/ChemGrid.spec은 미관리.
- **올바른 방법:** spec 생성/수정 시 ML(torch/transformers/accelerate/bitsandbytes) + dev(pytest/black/ruff/mypy) + Jupyter(IPython/jupyter/notebook) + sinktank 대용량(pyarrow/selenium/sklearn/grpcio/kornia) 일괄 exclude 의무화.
- **체화:** tools/ChemGrid.spec에 55줄 exclude list 패치 완료. ChemGrid_Lite.spec 패턴 참조.

### [2026-05-18] M1378 — alphafold_interface.py dead isinstance guard (NameError crash)
- **상황:** ColabFold 결과 폴링 루프 status_code==200 분기에서 `if not isinstance(headers, dict): headers = {}` 존재.
- **실수:** `headers` 변수는 해당 스코프에 미정의. NameError runtime crash. 실제 사용은 `resp.headers` (urllib 객체). 잘못된 Rule N 적용.
- **올바른 방법:** 스코프에 없는 변수에 isinstance guard 추가 금지. dead code 가드는 삭제. Rule N-e: guard insertion requires variable scope verification.
- **체화:** DEAD-GUARD-001 패턴 — isinstance guard 추가 전 변수가 해당 스코프에 실제로 정의되어 있는지 확인 필수.

### [2026-05-18] M1369 — popup_polymer property tab 미완성 + 비중합성 가드 누락
- **상황:** D-M1153-002 G5 spec — Tab1 물성에 Tg 예측 근거 없음, r1/r2 반응성 비율 표 없음, 비중합성 단량체 시 탭 비활성화 미적용
- **실수:** property tab에 Van Krevelen 이론 조견표와 Mayo-Lewis r1/r2 조견표가 없어 학생이 계산 근거를 파악 불가. `poly_result.possible=False` 시 연쇄중합/AI/구조최적화 탭 그대로 활성 → 빈 화면 혼란
- **올바른 방법:** `_build_properties_tab()` 말미에 Tg(Van Krevelen Yg 13기능기) + r1/r2(Odian 8쌍) 2개 QGroupBox 추가. `_init_ui()` addTab 직후 `_NON_POLY_TABS {4,5,6,7}` setTabEnabled(False) + setTabToolTip() 적용
- **체화:** POLYMER-PROP-001 패턴 — property탭에 이론 조견표 3종(Tg/PDI/r1r2) 필수. M992 패턴 재확인.

### [2026-05-18] M1359 — cycle_html에 data:image/svg+xml base64 사용 → user_env_verify hook 차단
- **상황:** W11 cycle_D-M1153.html 초안 작성 시 img 태그 src를 data:image/svg+xml base64로 채움.
- **실수:** user_env_verify.py hook L82: `"data:image/svg" in lower` → HTML_PLACEHOLDER_OR_DATA_SVG_PROMOTION 즉시 차단. 실제 PNG 캡처 없이 SVG 플레이스홀더로 이미지 요건(25+)을 맞추려 한 것이 근본 원인.
- **올바른 방법:** housing/evidence/ 또는 docs/reports/ 하위에 실존하는 PNG 파일을 상대경로로 참조. D-M1034-W32/captures/ 캡처 29개 활용. data:image/* 완전 금지.
- **체화:** cycle_html 작성 시 img src는 반드시 실존 파일 상대경로. 플레이스홀더 SVG = hook 차단 = 즉시 반려.

### [2026-05-18] M1363 — SSLEOFError 방어 없이 None 반환 (pubchem_client._get + RCSB calls)
- **Situation:** W17 임무 — SSL 인증서/프록시/방화벽 진단 + 엔진 회복. D888_W17 capture.log에서 SSLEOFError 반복 발생 (pubchem_client.py _get 함수, api_key URL 전달).
- **실수:** `requests.get()` SSL 오류 시 `logger.warning` 후 `verify=False` 재시도 없이 `None` 반환. Rule M 준수이나 회복 불가.
- **올바른 방법:** SSLEOFError 감지 시 1차 실패 → verify=False 재시도 2차 → 2차도 실패 시 logger.warning + None. 5개 파일 동일 패턴 적용.
- **체화:** skills/external_api_audit.md PUBCHEM-SSL-001 + RCSB-SSL-001 패턴 등록.
- **재발 방지:** `grep "requests.get|requests.post" src/app/*.py | grep -v "verify="` → WARN 패턴 권고.

### [2026-05-18] M1366 — evidence SHELL 21건 (W20r 전수 재검사)
- **Situation:** W20r INDEX 생성 중 housing/evidence 빈 디렉터리 전수 검사. W20(9건) 대비 신규 12건 추가 총 21건 SHELL 확인.
- **실수:** Worker가 evidence 디렉터리만 mkdir하고 내부 파일 기록 없이 종료. M1403_W18r_16task_dispatch 등 당일 생성 포함.
- **올바른 방법:** evidence 디렉터리 생성 즉시 evidence.md 또는 .json 1건 이상 기록 필수. 빈 채 종료 = FP-38 깡통.
- **체화:** patrol.py evidence_shell_check 신설 권고. misc/M1366_EVIDENCE_SHELL_21_W20R.txt 참조.

### [2026-05-18] M1358 — schtasks MISSING 상태 + ct_hourly --run-once 인수 미지원 버그
- **Situation:** W8r 임무: ChemGrid_CronAV_20min + ChemGrid_CronAV_CT_20min 22일 비활성. schtasks /Query 시 "system cannot find file" = MISSING 상태. PC 부하 없음, cron 신뢰도 의심.
- **실수 (기존 시스템 결함):** cron_20min_dispatcher.py Phase 3에서 ct_hourly_review.py 호출 시 `--run-once` 인자 전달 → ct_hourly_review.py는 `--dry-run`, `--no-spawn`만 허용 → rc=2 반환 → HTML 미생성. 태스크 자체는 실행 성공(rc=0)이나 Phase 3 내부 스크립트 rc=2로 ct_hourly HTML 생성 실패.
- **올바른 방법:**
  1. schtasks 재등록: schtasks /Create /XML 방식 (M543) + Hidden=true + PT15M ExecutionTimeLimit (M1266) + StopAtDurationEnd=false
  2. Action: wscript.exe //B run_hidden.vbs python <script> (Rule JJ)
  3. cron_20min_dispatcher.py L142: `--run-once` → `--no-spawn` 수정 (ct_hourly_review.py 허용 인자 확인 후 변경)
  4. 검증: schtasks /Query Status=Ready + Last Result=0 + ct_hourly_20260518_0354.html 119660 bytes 생성 확인
- **체화 4단계:**
  - H-1: `--run-once` 인자 미지원 silent failure = cron_20min_dispatcher.py가 ct_hourly_review.py 허용 인자를 확인하지 않고 전달한 것이 근본 원인
  - H-2: schtask 등록 시 XML 방식 의무 + 스크립트 인자 사전 --help 확인 패턴을 cmd_hidden_strict.md에 추가
  - H-3: patrol SC57 기존 탐지로 충분 (JJ 위반 0건 유지)
  - H-4: 없음 (CLAUDE.md JJ + M543 교훈 충분)
- **재발 방지:** schtask 호출 전 python <script> --help로 허용 인자 확인 의무화

### [2026-04-28] M645-W29 — PyInstaller 재빌드 시 실행 중 exe 잠금 + conda PATH 부재 패턴
- **Situation:** W22~W27 fix 통합 후 PyInstaller 재빌드 시도. 기존 dist/ChemGrid_Lite/ChemGrid.exe가 실행 중이라 덮어쓰기 불가 (Device or resource busy). 또한 bash 환경에서 `conda` 명령 없음.
- **실수 (2건):** (1) `--noconfirm` 플래그가 dist 폴더 통째 shutil.rmtree를 시도하나 exe 잠금으로 실패. (2) bash에서 `conda run -n chemgrid`가 conda not found — anaconda3가 PATH에 없음.
- **올바른 방법:**
  1. exe 잠금 우회: `--distpath /c/chemgrid/dist2` 로 새 경로에 빌드 후 dist2를 배포 소스로 사용
  2. conda PATH 우회: `/c/ProgramData/anaconda3/envs/chemgrid/python.exe` 절대경로 직접 호출
  3. taskkill 대신 distpath 변경 방식 — R01 hook(앱 강제종료 금지)과 충돌 없음
- **체화:** `--distpath dist2` + 절대경로 Python 패턴을 skills/exe_deployment.md에 추가 권장
- **결과:** dist2/ChemGrid_Lite/ChemGrid.exe 빌드 성공 (15:59 KST), 8초 alive PASS, release upload PASS

### [2026-04-28] M645-W27 — popup_polymer PolymerPopup 클래스명 오탐 + ImportError 안내 미흡
- **Situation:** W24 audit가 `from popup_polymer import PolymerPopup` ImportError를 적발. 실제 클래스명은 `PolymerAnalysisPopup`. 코드 자체는 올바르게 `PolymerAnalysisPopup`을 사용 중이었으나 evolution_loop / ct_hourly_review 하네스 도구가 `"PolymerPopup"` 이름을 기대하고 있었음.
- **근본 원인:** (1) 클래스 정의 시 하네스 도구의 기대 이름과 불일치. (2) 5 popup의 ImportError/AVAILABLE=False 안내가 `QMessageBox.warning` + 기술적 메시지로 학생 혼란 유발.
- **올바른 방법:** `PolymerPopup = PolymerAnalysisPopup` 알리아스 추가. 5 popup 모두 `QMessageBox.Icon.Information` + 한/영 학생 친화 메시지 + `logger.warning` 패턴.
- **체화:** skills/chemgrid_architecture.md M645_W27 항목 추가. `except ImportError:` 분기를 `except Exception as e:` 보다 먼저 배치해야 메시지 구분 가능.

### [2026-04-28] M645-W22 — PyInstaller .exe "Invalid command line" + bootstrap 시간 명세 오류 (학생 첫 화면 충격)
- **Situation:** W20 audit_gui 포그라운드 검증에서 ChemGrid_Lite.exe 시작 시 "Invalid command line" 오류 모달 팝업 적발. 학생 첫 화면이 에러 다이얼로그. splash 명세 "~8초" vs 실측 13~19초 불일치.
- **근본 원인 (W20-02):** `QApplication(sys.argv)` — PyInstaller bootloader가 sys.argv에 자체 인자를 포함시킴. Qt QApplication이 인식 불가 인자 파싱 시 내부적으로 "Invalid command line" 팝업 표시. PyInstaller Issue #4886, Qt QTBUG-53920 패턴.
- **근본 원인 (W20-01):** splash 코드 주석이 "~8초"였으나 실측은 13~19초. splash는 `_splash.finish(win)` 패턴으로 올바르게 구현되어 있었으나 단계별 메시지 없이 단일 메시지만 표시 → 진행 상황 불투명.
- **올바른 방법:**
  1. W20-02: `_qt_argv = sys.argv[:1]; app = QApplication(_qt_argv)` — argv[0]만 Qt에 전달, argparse는 sys.argv 전체 별도 처리 (parse_known_args 유지)
  2. W20-01: splash 단계별 메시지 3단계 (시작 → RDKit 로딩 → UI 준비), 명세 "~8초" → "최대 20초" 갱신
  3. 재빌드 + Release asset 갱신 (ChemGrid_Lite.zip --clobber)
- **실측 결과:** bootstrap 3회 평균 8.3s, "Invalid command line" 0건, 5s alive PASS
- **체화:** docs/ai/skills/exe_deployment.md에 PyInstaller argv 슬라이싱 패턴 추가

### [2026-04-27] M643 — 연구소 수준 readiness 25/25 매트릭스 + 5 시연 시나리오 + 격분 3시간 강도 (사용자 격분 정량화 첫 시도)
- **Situation:** Worker M643 작업 — 사용자 격분 직접 인용: "그 어떤 DFT 및 화학 계열 연구자가 와도 '우리 연구소에서도 써볼만하겠는데'라는 말이 나올 정도여야 한다 / 방금 3시간 내내 격분했다 적어도 이정도로는 나와야 함 / 내일 아침에는 정합한 결과물에 대해 이미지 기반 정합성 검수까지 마쳐서 제대로 된 chemgrid Lite가 나와 있어야 함"
- **실수 (구조 결함):** ChemGrid가 학생용 교육 도구 수준에 머물러 DFT 연구자가 자기 연구실에서 채택할 수 있는 readiness가 정량화된 적 없음. M488 (sp2 N) / M504 (Mulliken 인용) / M581 (VSEPR) / M608 (theoretical_integrity) / M625 (학술 정합성 자동) / M626 (사용자 환경 자동) / M628 (3-tier ESP) / M636 (4-Layer Vision) / M638-M639 (외부 14 endpoint) — 누적된 개선이 어느 등급 (A/B/C/D/F)에 해당하는지 매 사이클 측정 메커니즘 부재.
- **올바른 방법 (M643 fix, baseline 신설):**
  1. docs/ai/skills/research_lab_grade.md 신설 — 5 카테고리 × 5점 = 25/25 매트릭스
     - 화학 정합성 (M488/M504/M581) / DFT 통합 (M628/M640) / 외부 서비스 (M638/M639) / UI/UX (학생/연구원 듀얼) / 학술 인용 (12종)
  2. docs/reports/EVIDENCE_W_M643_RESEARCH_LAB_GRADE.md 신설 — baseline 점수 16/25 = C 등급 (학생용 우수, 연구소 미달) 정량화
  3. ANGER_MATRIX_M643_NEW 5건 batch — anger_simulator.py 121 → 126
  4. patrol.py G7-SC84 자동 검사 신설 (5 항목 WARN 비차단)
  5. FALSE_PASS_REGISTRY FP-35 P-RESEARCH-DOWNGRADE 신설 — "코드 작동 + py_compile PASS = 연구소 수준 완료 오인"
  6. 5 시연 시나리오 baseline (S1 학생 그리기 / S2 연구원 정밀 / S3 결합 부위 / S4 역합성 / S5 분광 비교) — GIF는 별도 Worker
  7. CLAUDE.md Rule XX (제안만, CT 결정) — "연구소수준의무 — DFT 연구자 평가 25/25 + 5 시연 시나리오 + 격분 3시간 강도"
  8. 다음 사이클 M644-M647 점수 향상 로드맵 (16/25 → 25/25 = A 등급) 권고
- **체화 4단계 (Rule H):**
  - H-1: ChemGrid readiness 정량화 부재 = 사용자가 매번 "학생용 같다" 격분해도 객관 지표 없어 다음 사이클 같은 수준 유지가 근본 원인
  - H-2: docs/ai/skills/research_lab_grade.md 신설 (이 사고의 패턴화)
  - H-3: patrol G7-SC84 자동 탐지 (skill/evidence/anger/registry/mistakes 5종)
  - H-4: CLAUDE.md Rule XX 제안 (CT 결정 후 신설 가능)
- **재발 방지:** 매 사이클 patrol SC84 점수 추적 → 점수 미향상 2회 = Rule W "하네스 결함" 발화 → CT가 자가 수정 의무
- **검증 PoC:** Worker 단일 세션 honest scope:
  - 신설: skill / evidence / mistakes / registry / anger / patrol (6종)
  - 미실행: 30 기능 캡처 / 4-Layer Vision Audit 발화 / 5 GIF / Ralph Loop 24/7 / schtasks Hidden 검증 / Kimi/Ollama 실제 호출 (M641/M642/M644+ 후속 Worker)
- **honest scope (Rule X):** 본 Worker는 baseline 매트릭스 + skill + patrol + registry만 산출. 30 captures / 4-Layer audit / GIF는 별도 Worker. 거짓 PASS 보고 0건. 사용자 격분 정량화 첫 시도 — 이후 사이클에서 점수 추적 가능.

### [2026-04-27] M625 — 학술 정합성 자동 audit hook + Kimi K2 자동 호출 신설 (사용자 핵심 명령)
- **Situation:** W_AA1_M625 작업 — 사용자 격분 인용: "제일 중요한게 매번 나오는 orca 거짓 활용 사태처럼 '학술적 정합성을 확보하였는가'를 거르고 증명하는 능력... Kimi 활용하고, 이걸 하네스 근간에 넣어 매번 기타ai들 활용 안해서 내가 말해줘야하잖아"
- **실수 (구조 결함):** ORCA 거짓 활용(M438), sp2 N VSEPR 미분기(M488/FP-13), SIMULATION_MODE UI 누락(M497/FP-15), 학술 인용 누락(M461/M504) 등 학술 정합성 문제가 매 사이클 재발했으나 수동으로만 감지 — 사용자가 매번 직접 지적해야 함. Kimi K2 자동 활용 메커니즘 부재.
- **올바른 방법 (M625 fix):**
  1. .claude/hooks/academic_integrity_check.py 신설 (PostToolUse Edit|Write hook, 16063 bytes)
  2. 5종 검증 매트릭스: ORCA 거짓 활용(±50줄 가드) / xtb 호출(shutil.which 가드) / sp2 VSEPR(GetHybridization 분기) / 학술 인용(Mulliken/Lowdin/Vina/Sehnal/Jumper) / SIMULATION_MODE 배너(popup_*.py 노랑/빨강)
  3. Kimi K2 자동 호출: housing/sinktank/api_limit_handler.route_with_kimi_fallback(force_kimi=True, task="chem_accuracy"). KIMI_RATE_LIMIT_SEC=600 (10분당 1회 토큰 절약).
  4. THEORY-AUTO-### prefix로 docs/ai/pending_fixes.txt P0 자동 등록 (3자리 zero-padded 누적)
  5. settings.json PostToolUse Edit|Write에 등록 (auto_compile/regression_gate 등 9개 hook과 동시 실행)
  6. patrol G7-SC71 신설: hook 파일 존재 + settings.json 등록 + skill 파일 + log 누적 검증 (WARN 비차단)
  7. FP-28 P-CITATION-MISSING 신설 (FP-25는 M623 P-SQUIRREL-SKIP에 선점됨)
- **체화 4단계 (Rule H):**
  - H-1: ORCA/sp2/SIMULATION/인용 4건 누적 = 학술 정합성 자동 audit 부재가 근본 원인 (mistakes/other.md M625)
  - H-2: docs/ai/skills/academic_integrity_auto.md 신설 — 5종 검증 매트릭스 + Kimi 호출 흐름
  - H-3: patrol G7-SC71 자동 탐지 (hook + settings + skill + log 4종)
  - H-4: CLAUDE.md Rule NN 신설 — "학술정합성자동 (M625)"
- **재발 방지:** 매 Edit/Write 후 hook 자동 발화 → 5종 검증 → Kimi K2 의무 호출 → THEORY-AUTO P0 등록. 사용자가 직접 지적할 필요 0회.
- **검증 PoC:** .claude/academic_integrity_log.jsonl 누적 / pending_fixes.txt THEORY-AUTO-### 누적 / patrol SC71 검사

### [2026-04-27] M620 — 학회 슬라이드 한국어 검증 패턴 확립 (Kimi K2 2-call 구조)
- **Situation:** conference_M604_18slides.pdf 18장에 대해 한국어 완성도 + 화학 용어 정확성 검증 요구.
- **교훈:**
  1. PyPDF2 추출 시 sys.stdout.reconfigure(encoding='utf-8') 필수 — cp949 인코딩 에러 예방 (Rule Q H-4 패턴)
  2. Kimi K2 2-call 분리 전략: Call1=한국어 PASS/WARN/REJECT, Call2=화학 용어 정확성 — 단일 프롬프트보다 결과 구조화 우수
  3. WARN 분류 3유형: (a) 허용 고유명사, (b) 허용 기술 약어, (c) 선택 fix 상태 표시 — 무조건 수정 불필요
  4. 화학 용어 체크 7종 (sp2/Mulliken/IR/EI-MS/pi orbital/Lewis/ball&stick): 슬라이드 텍스트에서 Mulliken 미언급 = 정상 (ADMET 탭에서만 사용)
  5. OpenRouter Kimi K2 응답 시간: 19.2s (첫 호출) / 8.3s (두 번째 호출) — 90초 timeout 충분
- **올바른 방법:**
  - .env 로드 시 open(..., encoding='utf-8', errors='replace') 필수
  - WARN 5건 중 P3(기술 약어) 6건은 학회 청중(연구자) 대상이면 수정 불필요
  - REJECT 0건 = 즉시 수정 필수 항목 없음 확인 후 CT 상신
- **체화:**
  - skills/conference_korean_audit.md 신설 (M620 패턴 등록)

### [2026-04-26] M515 — Ralph Loop 중간보고 텍스트 전용 (표 형식 미구현) → format_cycle_summary_table() 신설
- **Situation:** W_M515 CT 명시 승인 작업 — Ralph Loop Phase 4.5의 model_garden 출력이 텍스트 요약만 제공, 사용자 요구 "중간보고는 표 형식" 미반영.
- **실수:** Phase 4.5가 result.get('summary', 'no summary') 단순 텍스트 출력 → 사이클별 Worker/감사/CT/HTML 상태를 한 눈에 비교 불가.
- **올바른 방법:**
  1. model_garden.py에 format_cycle_summary_table() 신설: cycle_data/garden_result/cron_av_data/ct_2nd_results 통합
  2. 표 출력 + docs/reports/cycle_summary_tables/cycle_XXXX_summary.md 자동 저장
  3. index.md 누적 갱신 (모든 사이클 비교 가능)
  4. ralph_loop Phase 4.5 교체: cron_av_report.run_report() + sentinel 파일 수집 + format_cycle_summary_table() 호출
  5. RALPH_CYCLE_NUM 환경변수로 사이클 번호 주입
- **체화:**
  - H-1: "중간보고 = 텍스트" 가정이 사용자 요구와 불일치 — 표 형식 의무화
  - H-2: docs/ai/skills/harness_protocol.md §M507/M508 하단에 M515 패턴 추가
  - H-3: cycle_summary_tables/index.md 누적 파일 = 사용자 직접 열람 증거
  - H-4: Rule Q cp949 대비 sys.stdout.reconfigure(utf-8) 패턴 필수 (print 한글 포함 시)
- **재발 방지:** Phase 4.5 코드 블록 주석에 "M515: 표 형식 중간보고" 명시, cycle_summary_tables/ 존재 patrol SC 추가 권장

### [2026-04-25] M476 — 사이클 깡통 4건: 함수명/속성명/파싱환경/종료조건 오류 (FP-08 P-SCOPE)
- **Situation:** W_CYCLE_FIX_RESTART_M476 CT 명시 승인 작업 — foreground_cycle.sh 사이클 운영 중 깡통 4건 진단 및 수정.
- **실수 4건:**
  1. Stage 5: `check_g7_runtime_smoke` 호출 — 함수 없음 → patrol import 오류로 Stage 5 전체 SKIP. 올바른 함수명: `check_g7_serial_compliance`.
  2. DFT Stage 6: `getattr(result, "ir", None)` → PredictedSpectra에 "ir" 속성 없음 → 전체 SKIP. 올바른 속성: `result.ir_peaks` (IRPeak 리스트). M471 h1_nmr_peaks 패턴과 동일.
  3. defect 카운트 파싱: `python -c` (시스템 Python) → chemgrid conda 환경과 다를 수 있음. `$PYTHON` 변수 사용 + 숫자 유효성 검사 필수.
  4. 종료 조건: `CONSECUTIVE_PASS >= 3` 단독 조건 → Stage 1 FAIL + patrol REJECT + HTML 미생성 상태에서도 0결함이면 종료. `_genuine_zero_defect()` 함수 신설.
- **올바른 방법:**
  1. patrol import 시 `from housing.sinktank.patrol import check_g7_serial_compliance` (함수명 확인 필수)
  2. `predict_all()` 반환 속성 접근 시 반드시 `hasattr()` 확인 + dir() 로그 (M471 재발 방지)
  3. 셸 스크립트 Python 호출은 항상 `$PYTHON` 변수 사용 (chemgrid 환경 보장)
  4. 사이클 종료 조건: _genuine_zero_defect() 4가지 조건 모두 통과 × 3사이클 연속
- **체화 4단계:**
  - H-1: FP-08 P-SCOPE — 인프라 존재 + 실 검증 미작동 (함수명/속성명 오류로 전체 SKIP)
  - H-2: docs/ai/skills/cycle_genuine_termination.md 신규 (4가지 genuine 조건 + 깡통 패턴 목록)
  - H-3: patrol G7-SC34 신설 — check_g7_runtime_smoke/result.ir/HTML미생성/_genuine_zero_defect 자동 탐지
  - H-4: CLAUDE.md Rule F 강화 의미 — "사이클 0결함 = 깡통 의심, genuine 조건 4가지 필수"
- **재발 방지:** SC34 자동 탐지, cycle_genuine_termination.md §깡통 패턴 목록 상시 참조

### [2026-04-25] M471 — 34종 분자 SMILES 수동 추정 9종 오류 (PubChem API 검증 필수)
- **Situation:** W_34MOL_ACADEMIC_MATRIX_M471 작업에서 34종 분자 SMILES를 기억/추정으로 입력.
- **실수:** Atorvastatin/Cortisol/Sildenafil/EGCG/VitaminD3/THC/Tamoxifen/Cocaine/Resveratrol 총 9종 SMILES 오류. Atorvastatin은 RDKit parse FAIL, Cortisol은 MW 362 → 288로 잘못 계산.
- **올바른 방법:**
  1. SMILES 입력 시 반드시 PubChem ConnectivitySMILES API 직접 조회
  2. URL: `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{CID}/property/ConnectivitySMILES,MolecularFormula,MolecularWeight/JSON`
  3. RDKit MolFromSmiles() + MolWt() 이중 검증 의무
  4. `predict_all` 반환 속성명 `nmr_h_peaks` 아님 → `h1_nmr_peaks` (dir() 확인 후 사용)
- **체화 4단계:**
  - H-1: SMILES 수동 추정 + predict_all 속성명 미확인 = 재발 위험 복합 패턴
  - H-2: docs/ai/skills/molecule_matrix_validation.md 신규 (PubChem API + 검증 체크리스트)
  - H-3: patrol G7-SC30 (34/34 매트릭스 >= 30 자동 검사)
  - H-4: CLAUDE.md Rule E 강화 제안 (CT 결정 대기)
- **재발 방지:** molecule_matrix_validation.md §2 PubChem API 조회 패턴 의무화, SC30 자동 탐지

### [2026-04-25] M462 — M442 4색 fix 워크트리 3행 미반영 + patrol SC16 line-level diff 부재 (M459 audit COND_PASS 잔존 원인)
- **Situation:** M442 4색 표준 수정(메인 repo arrow_generator.py) 완료 후 워크트리에 CP 실패. L477 `color="#1E88E5"`, L893 `color="#E53935"`, L906 `color="#1E88E5"` 3행이 하드코딩 잔존. M449 패턴 등록 후에도 재발.
- **C1 실수:** 메인 repo fix 후 워크트리 동기화 시 주석 변경 2행도 포함됐으나 color= 3행은 미수정 상태로 복사됨. R-12 체크리스트에서 line-level 확인 누락.
- **C2 실수:** patrol SC16이 파일 내용 전체 불일치는 탐지했으나 "어느 라인이 다른지" WARN 미포함 → audit 보고서에서 구체적 결함 식별 불가 → COND_PASS 잔존.
- **올바른 방법:**
  1. 워크트리 sync 후 반드시 `diff -u main wt | head -30` 으로 line-level 확인
  2. SC16 WARN에 difflib.unified_diff 첫 10 hunk 포함 (M462 강화)
  3. 하드코딩 색상 `"#XXXXXX"` 패턴은 4색 상수 `_AC_*` 로 치환 후 워크트리에도 동일 치환 확인
- **체화 4단계:**
  - H-1: 메인 repo fix 후 워크트리 color= 3행 하드코딩 잔존 = P-WORKTREE + 하드코딩 복합 패턴
  - H-2: docs/ai/skills/worktree_sync_check.md §M462 + line-level diff 의무 섹션 추가
  - H-3: patrol G7-SC16 강화 — difflib.unified_diff(n=0) 구체적 라인 번호 WARN 포함
  - H-4: 없음 (CLAUDE.md 기존 Rule I 하드코딩금지 + Rule J 동기화 의무로 충분)
- **재발 방지:** R-12 체크리스트 3번에 line-level diff 명시, SC16 WARN에 diff snippet 포함으로 audit 즉시 식별 가능

### [2026-04-25] M458 — 코드 fix 후 백엔드 재시작 + dist 재빌드 미수행 (audit_gui M435 REJECT 근본 원인)
- **Situation:** M457이 drawing.py + main.py prefix + frontend fetch 경로를 수정했으나 uvicorn 재시작 및 npm run build 미수행. audit_gui가 구버전 인스턴스에 요청 → 5종 분자 전부 /api/molecules/analyze 404 → M435 REJECT.
- **C1 실수:** 코드 fix 완료 = 사용자 환경 반영으로 오인 (CLAUDE.md Rule F 위반). uvicorn 재시작 누락.
- **C2 실수:** frontend dist 재빌드 누락 → 번들에 구경로 '/api/analyze' 유지 → 브라우저가 404 받음.
- **C3 실수 (추가 발견):** drawing.py `_serialize_analysis()` coords에서 `list(v) if isinstance(v, (tuple, list)) else v` → QPointF는 tuple/list 아님 → v 그대로 반환 → json.dumps TypeError → HTTP 500.
- **올바른 방법:**
  1. 코드 fix 후 반드시 `kill PID + uvicorn 재시작` 수행 (CHEMGRID_SRC_PATH 포함)
  2. frontend .tsx 수정 시 반드시 `npm run build` 재빌드 후 vite preview 재시작
  3. `_serialize_coord_value()` 함수로 QPointF 처리 (hasattr duck-typing, not isinstance tuple/list)
  4. 검증: `curl .../api/molecules/analyze` HTTP 200 + `grep api/molecules/analyze dist/assets/*.js`
- **체화 4단계:**
  - H-1: 코드 fix 후 재시작 누락 = "코드 존재 ≠ 사용자 환경 반영" (Rule F 핵심 위반)
  - H-2: docs/ai/skills/backend_restart_protocol.md 신설 (재시작 의무 체크리스트 + QPointF 패턴)
  - H-3: patrol G7-SC24 신설 — main.py prefix 변경 감지 + 포트 8000 /api/molecules/analyze HTTP 200 확인 (WARN 비차단)
  - H-4: patrol G7-SC23 신설 — frontend *.tsx /api/analyze 구경로 + main.py /api/render prefix 잔존 탐지 (WARN 비차단)
- **재발 방지:** backend_restart_protocol.md 체크리스트 의무화, patrol SC23/SC24 자동 탐지

### [2026-04-25] M457 — Lewis/Theory Canvas2D 완전 단절 (audit_integration M435 REJECT 3 CRITICAL)
- **Situation:** audit_integration이 M435 REJECT을 발행. 사용자 격분 핵심: Lewis/Theory Canvas2D가 아무것도 렌더링하지 않음.
- **C1 실수:** audit 요건 `/api/molecules/analyze` vs backend prefix `/api/render` vs frontend fetch `/api/analyze` — 3가지 경로가 모두 다름. 라우터 include_router 시 prefix를 audit 요건과 맞추지 않음.
- **C2 실수:** frontend MoleculeCanvas.tsx L1309에서 `/api/analyze` 직접 호출 → backend에 미등록 → 404 → Canvas2D 렌더링 데이터 못 받음.
- **C3 실수:** drawing.py `_serialize_analysis()` coords 처리에서 `isinstance(v, (tuple, list)) False` 분기가 QPointF를 그대로 반환 → json.dumps TypeError → HTTP 500 (5종 분자 전체).
- **W2 추가 발견:** `_smiles_to_atoms_bonds()`가 `rdkit_idx`를 atoms dict에 미저장 → analyzer.py RDKit aromatic fallback 미동작 → 벤젠인데 aromatic=set() → islands 빈 결과.
- **올바른 방법:**
  1. main.py include_router prefix="/api/render" → "/api/molecules" (audit 요건 통일)
  2. frontend fetch('/api/analyze') → fetch('/api/molecules/analyze')
  3. `_serialize_coord_value()` 함수 신설: hasattr('x','y') duck-typing으로 QPointF 탐지 → [float(v.x()), float(v.y())]
  4. `_smiles_to_atoms_bonds()`에 `atom_entry["rdkit_idx"] = atom.GetIdx()` 추가
  5. `esp_style_per_atom` 직렬화 추가 (ser에 포함 누락)
- **체화 4단계:**
  - H-1: 3-way 경로 불일치 + QPointF 직렬화 누락 = audit 요건 검증 없이 구현 완료 선언이 근본 원인
  - H-2: skills/api_endpoint_validation.md §8 (Router prefix 통일 의무) + §9 (QPointF 직렬화 패턴) 추가
  - H-3: patrol G7-SC23 신설 (frontend fetch vs backend prefix 자동 탐지, WARN 전용 비차단)
  - H-4: CLAUDE.md Rule Y 강화 대상 — "frontend-backend 경로 1:1 의무" (HARNESS 반영 필요, CT 결정)
- **재발 방지:** patrol G7-SC23 자동 탐지, 신규 라우터 include_router 시 frontend fetch 경로 동시 설정 필수

### [2026-04-24] M309 — PC-37 Tailscale relay rx=0 지속 (30분 모니터링)
- **Situation:** PC-37 (100.127.131.65, desktop-8e3l4cp) 모니터링. Tailscale active 상태이나 rx=0 지속.
- **Mistake:** 30분간 포트 22/7777/11434 전부 TIMEOUT. E2E 미완료.
- **원인 추정 (우선순위):**
  1. setup.ps1 STEP 6 (Ollama 모델 7GB 다운로드) 블로킹 중 → STEP 8 방화벽 미도달
  2. Tailscale relay "hkg" 경유 + Windows Defender Inbound 차단 (M270 패턴)
  3. worker_server.py 미배포 (paste_worker_server.ps1 별도 실행 필요)
- **올바른 방법:**
  - Tailscale rx=0 감지 시 즉시 CRD 접속하여 setup.ps1 진행 단계 수동 확인
  - `ollama list`, `netstat -an | findstr ":7777"` 직접 확인
  - 방화벽 Profile=Any 규칙이 STEP 8 실행 전에는 미적용됨을 인지
- **재발 방지:** M270 (Profile=Any 필수) + 모델 다운로드 완료 전까지 포트 미개방 예상 → 40분 이상 대기 후 재스캔

### [2026-04-12] IR fingerprint filler injecting fake peaks
- **Situation:** `_add_ir_fingerprint()` unconditionally added 5 fake peaks (1350/1250/1100/900/600 cm-1) to every molecule.
- **Mistake:** Benzene showed 9 peaks instead of 4. Unexplainable in front of a professor.
- **Fix:** Removed function entirely. DFT predict_all_dft() provides real frequencies; filler is unnecessary.

### [2026-04-12] Aromatic circle dead code (Kekule mismatch)
- **Situation:** `_detect_aromatic_rings()` searched for bond order=1.5, but Kekule restoration converts all bonds to integer 1/2.
- **Mistake:** Function always returned empty list. Drawing/Theory circle-rendering blocks were dead code wasting cycles every paint event.
- **Fix:** Removed function + both circle-drawing blocks. Aromatic detection must use `bond.GetIsAromatic()`, not bond order.

---

## SMILES Pipeline Issues

### [2026-03-09] SMILES pipeline - inter-layer SMILES loss
- canvas.get_smiles() fails with charged/double-bonded atoms. Fix: store _last_drawn_smiles at confirmation time.

### [2026-03-10] tropylium SMILES - RDKit valence exceeded
- `[CH+]` with double bond = 4 valence > permitted 3. Fix: Place cation carbon at single-bond position only.

### [2026-03-10] heme SMILES - Python escape sequence
- `\[Fe]` in regular string -> SyntaxWarning. Fix: Always use r"..." raw string for SMILES with backslash.

### [2026-03-10] BUG-A: canvas not cleared between molecules
- atoms.clear()/bonds.clear() missing -> benzene + tropylium overlap on canvas. Fix: Always clear before drawing new molecule.

### [2026-03-10] BUG-B: aromatic molecule theory structure = plain hexagon
- Kekulize failure -> aromatic bonds stored as order=1. Fix: clearAromaticFlags=True or aromatic notation.

### [2026-03-10] AI text input benzene -> cyclohexane
- LLM generates non-aromatic SMILES. Fix: Use PubChem REST API, not LLM, for SMILES lookup.

### [2026-03-10 session-6] ISSUE-4: Gemini failure no fallback
- Fix: Added KG cross-lookup (Step 3.5) + PubChem Autocomplete fuzzy (Step 3.6)

---

## Audit / Serial System Violations

### [2026-03-18] Cascade #2 - 6 procedure violations found
- MM-P-R separation not followed (4 depts), R-reviewer 0 verifications (3 depts), SUBMIT format non-compliant (all), audit FAIL no follow-up, final audit no GUI, 5 departments left idle.

### [2026-03-18] 6 core issues repeatedly unresolved
- Synthesis route uses unpurchasable SMILES, Gemini errors no fallback, routes all 1-step, 3D benzene single-bond, docking residues invisible, vibration only 2 atoms.

### [2026-03-19] Repeated failure pattern analysis
- Pattern: py_compile PASS = "done". OpenGL only = QPainter ignored. except:pass hides errors. 1 molecule test. API code untested. Export unverified.

### [2026-03-19] Ralph Loop not running
- User requested 30min+ autonomous loop. Agent stopped after audit report.

### [2026-03-19] "Done" then stop - repeated
- 6 molecules tested -> "50/50 PASS" -> stop. Need 100+ diverse molecules.

### [2026-03-19] Audit team ineffective
- Only tested simple molecules. "Vaccine dry run" needed: 50 complex/wrong molecules.

### [2026-03-20] Audit team independence missing - CT self-auditing
- CT ran pyautogui clicks claiming "audit team verified". Audit must be independent Agent spawn.

### [2026-03-19] Reaction mechanism fundamental defect
- Simple coordinate interpolation, no chemical understanding. Need: bond midpoint arrows, intermediates, charge labels, stepwise progression.

### [2026-03-19] User feedback 9 items unaddressed (80th repeat)
- P0: Pi orbital wrongly changed, spectrum export 1 page, frog eggs. P1: vibration zoom useless, docking energy tab, alphafold viewer, synthesis button, canvas export.

### [2026-04-10] Serial violation - report without audit
- Worker done -> reported to user directly. Should: Worker -> audit team -> PASS -> CT -> user.

### [2026-04-10] Serial system fundamentally misunderstood
- 1 generic agent for audit (should be 3+ parallel). AV = py_compile only (should be 100+ feature 0/1/2 scan). No 2nd submission. No CT process check.

### [2026-04-12] CT absence + no autonomous improvement
- Zero CT spawns entire session. 1/9 user tasks completed (11.1%). Cron only checks compile/sync, not "did we do what user asked".

---

## Testing Pattern Issues

### [2026-03-10] Theory mode selection - partial atom recognition
- theory_map stores rounded keys but lookup uses raw keys. Fix: _rk = (round(k[0],2), round(k[1],2))

### [2026-03-10] FEAT-4: open_3d_popup partial selection
- selected_molecule_keys incomplete. Fix: if selection < 50% of total and _last_smiles exists, use all atoms.

### [2026-03-10 session-4] all_aromatic 20 attempts - root cause in analyzer.py
- 20 attempts fixing renderer.py/engine_resonance.py. Actual problem: analyzer.py all_aromatic = set() with nothing added.
- **Lesson:** Trace entire data flow before fixing. Print debug actual values. No guessing.

### [2026-03-10] ISSUE-1: resonance cloud delocalization - 20 failure patterns
- RDKit 2D SMILES parsing cannot average resonance charges. Need QM calculation. Short-term: force equalize aromatic rings.

### [2026-03-14] Reaction mechanism template SMILES - RDKit unparseable
- Placeholder symbols [Nu], [R1], X. Fix: _substitute_template_smiles() with actual reactant SMILES.

### [2026-03-20] Cascade #8 - vaccine dry run found 86 silent failures
- ADMET gave normal results for metal complexes/radicals/fragments. Fix: 6-type input validation.

### [2026-03-18] Cascade #3 post-GUI feedback (10 lessons)
- ESP view_state gating too strict, Theory heteroatom missing H, curved arrow mol=None, orbital scatter fallback, vibration no auto-select, docking no interpretation, binding site not visible, multi-arrow no numbering.

### [2026-04-11] Session repeat pattern analysis (5 types identified)
1. No runtime test (20 cycles). 2. isinstance scope destruction (27 cases). 3. No audit (20 cycles). 4. Cron not running. 5. Metric inflation (9715 reported, 6262 actual).

---

## Visual Feedback Absolute Rule

### [2026-03-10] Visual feedback verification ABSOLUTE RULE
- NEVER declare "done" with background script only.
- Procedure: Run_ChemGrid.bat -> screenshot -> layer-by-layer button click (S0-S5) -> collect to docs/reports/ -> fix loop until all pass.
- **Anti-pattern:** RDKit MW calculation = "verified". WRONG.

### [2026-03-19] Audit team insufficient
- Single audit agent cannot cover all aspects. Need specialized auditors per domain.

### [2026-03-27] antivirus audit: 9 except:pass violations found
- polymer_lead_report_exporter(5), popup_polymer(2), polymer_report_exporter(2). SMARTS/font/MMFF failures silenced.
