# Skill: 사용자 환경 자체 검증 자동 (M626)

> 작성: Worker AA2 M626 (2026-04-27)
> Rule OO 신설 근거 | mistakes M626 매핑 | FP-26 P-USR-ENV-UNVERIFIED 차단

## 핵심 원칙

사용자 직접 인용 (M626 신설 근거):
"내 피드백 html처럼 자체적으로 잘못된 부분을 사용자 환경에서 검증할 수 있는가다... Kimi 활용하고, 이걸 하네스 근간에 넣어"

코드 컴파일 PASS != 사용자 환경 작동 PASS.
캡처 PNG 크기만 봐서는 실제 GUI 결함 0% 탐지 불가.
하네스가 자동으로 사용자 환경 격분 패턴을 검증해야 한다.

## 5단계 검증 파이프라인

| 단계 | 검증 | 트리거 | 차단 FP |
|------|------|--------|---------|
| 1 | 픽셀 분석 | PNG 생성 후 자동 | FP-05 P-SIZE / FP-06 P-MODAL |
| 2 | 시나리오 (popup_ghost) | popup_*_open*.png | FP-11 P-SKIP-WIDGET / FP-12 P-UNTESTED / FP-19 P-POPUP-GHOST |
| 3 | tofu 박스 (Rule Q) | Kimi vision 위임 | Q (한국어 폰트 깨짐) |
| 4 | cycle_html 비교 | cycle_*.html 생성 후 | FP-18 P-META-SHALLOW |
| 5 | Kimi K2.6 Vision LLM | 매 사이클 PoC | FP-26 P-USR-ENV-UNVERIFIED |

## 자동 발화 메커니즘

### Hook 진입점
- `.claude/hooks/user_env_verify.py` (PostToolUse:Edit|Write 등록)
- `housing/sinktank/user_env_auto_verify.py` (실제 검증 모듈)

### settings.json 등록
```json
"PostToolUse": [{
  "matcher": "Edit|Write",
  "hooks": [{"command": "python .claude/hooks/user_env_verify.py"}]
}]
```

### Ralph Loop 통합
```bash
# Phase 4.7h (ralph_loop_local.sh + ralph_loop_web.sh)
python /c/chemgrid/housing/sinktank/user_env_auto_verify.py --scan-recent
```

## REAL-GUI-CAPTURE-MANDATORY-001 (M842 신설)

> 근거: M842 사용자 격분 LV.40 — "M824~M840 17 cycle ChemGrid 실 가동 0회 = 깡통"

### 규칙
1. 모든 Worker의 popup 검증은 QT_QPA_PLATFORM=offscreen QWidget.grab().save() PNG 필수
2. 코드 읽기(grep/Read)만으로 "popup DONE" 보고 금지
3. 최소 5 popup type × 5 molecule = 25 PNG. 미만 시 fabrication 간주
4. pixmap.isNull() 체크 + grab().save() 반환값 확인 의무
5. cycle_html에 img 태그 실제 PNG 경로만 허용 (placeholder URL 금지)

### 캡처 스크립트 패턴
```python
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
# ... QApplication 초기화 후
popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
popup.show()
QApplication.processEvents()
pixmap = popup.grab()
assert not pixmap.isNull(), f"Null pixmap for {popup_name}"
pixmap.save(f"M###_captures/{popup_name}.png", "PNG")
```

### Patrol SC101
M842 이후 모든 사이클 보고서에서:
- PNG count < 20이면 SC101 WARN (REAL-GUI-FABRICATION)
- cycle_html에 img src가 M###_captures/*.png 패턴이 아닌 경우 WARN

## 5 시나리오 자동 분류

파일명 기반 시나리오 매핑 (`detect_scenario_from_filename`):

| 시나리오 | 파일명 패턴 | Kimi 프롬프트 |
|---------|------------|--------------|
| popup_3d | `popup_3d`, `viewer3d`, `_3d_` | 6 탭 보이는가 / ghost인가 / 3D 렌더 품질 |
| lewis_theory | `lewis`, `theory`, `_layer_` | atom label tofu / NH2 subscript / ESP cloud 색상 |
| drylab_pdf | `drylab`, `_pdf_` | 빈 페이지 / 글자 겹침 / 스펙트럼 라벨 / 폰트 |
| conf_slide | `conf`, `slide`, `presentation` | 한국어 누락 / 영어 잔존 / 폰트 / 학술용어 |
| cycle_html | `cycle_*.html` | 사용자 index.html 수준 (다크+카드+격분+img5) |
| general | 기타 | 표준 격분 5건 추출 |

## Kimi K2.6 Vision 통합

### 모델 선택
- `moonshotai/kimi-k2.5` (기본): 비-추론, 응답 빠름, vision 지원
- `moonshotai/kimi-k2.6` (옵션): 추론 모드, content null 시 reasoning fallback

### API 구조 (OpenRouter)
```python
messages = [{
    "role": "user",
    "content": [
        {"type": "text", "text": "이 chemgrid 캡처에서 격분 5건 추출"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
    ]
}]
```

### 의무 헤더 (Rule I 보존)
- HTTP-Referer: `https://chemgrid.local`
- X-Title: `ChemGrid`
- Authorization: `Bearer ${OPENROUTER_API_KEY}` (.env)

### 응답 처리
1. JSON 파싱 시도 (list of strings)
2. dict 형식 fallback ({"anger_5": [...]})
3. line-split fallback (Rule M silent failure 금지)

## REJECT/WARN 자동 등록

### pending_fixes.txt 자동 추가
```
P0|AUTO|N/A|user_env_verify|USR-AUTO-PIXEL-{ts} {timestamp} PNG pixel REJECT: ... |path
P1|AUTO|N/A|user_env_verify|USR-AUTO-KIMI-{ts}-{i} {ts} Kimi vision anger #i ...|path
P1|AUTO|N/A|user_env_verify|USR-AUTO-CYCLE_HTML_USER_ENV {ts} cycle_html missing user_env_section|path
```

### 누적 로그
- `.claude/user_env_log.jsonl`: JSON Lines, 매 검증마다 1줄
- 필드: ts, ts_iso, file, type, scenario, verdicts, overall

## 매직넘버 (Rule I 의무 주석)

| 변수 | 값 | 의미 |
|------|-----|------|
| _MIN_PNG_SIZE_BYTES | 1024 | 1KB 미만 = 빈 화면 (FP-05) |
| _MONOCHROME_THRESHOLD | 0.95 | 95% 단색 = 빈 화면 (FP-05) |
| _MODAL_GRAY_RATIO | 0.70 | 회색 70%+ = 모달만 (FP-06) |
| _USER_INDEX_MIN_IMGS | 5 | cycle_html img 임베드 최소 (Rule CC) |
| _KIMI_TIMEOUT_SEC | 30 | Kimi vision HTTP 타임아웃 |
| _SCAN_RECENT_SEC | 3600 | 최근 1시간 (단위: 초) |
| _SCAN_RECENT_LIMIT | 5 | 비용 제한 사이클당 5건 |
| _POPUP_CAPTURE_MIN_BYTES | 4096 | 4KB 미만 팝업 = ghost (FP-19) |

## CLI 직접 호출

```bash
# 단일 PNG
python housing/sinktank/user_env_auto_verify.py --png capture.png --scenario popup_3d

# 단일 HTML
python housing/sinktank/user_env_auto_verify.py --html docs/reports/cycle_reports/cycle_*.html

# 최근 1시간 PNG 일괄 (ralph_loop가 호출)
python housing/sinktank/user_env_auto_verify.py --scan-recent

# Kimi 호출 생략 (오프라인/픽셀만)
python housing/sinktank/user_env_auto_verify.py --png capture.png --no-kimi
```

## patrol SC72 자동 감시

`G7-SC72`: 다음 6요소 검증 (WARN 비차단):

1. `housing/sinktank/user_env_auto_verify.py` 모듈 존재
2. `.claude/hooks/user_env_verify.py` hook 진입점 존재
3. `.claude/settings.json` PostToolUse Edit|Write에 등록
4. `multi_llm.kimi_vision_audit()` 메서드 존재
5. `docs/ai/skills/user_env_auto_verify.md` 체화 파일 존재
6. `.claude/user_env_log.jsonl` 누적 0건 아님 (FP-26 차단)

## FP-26 P-USR-ENV-UNVERIFIED 차단 패턴

거짓 PASS: "py_compile PASS + 캡처 PNG 생성됨 → PASS 보고"
실제 결함: 빈 화면 / ghost popup / cycle_html 미달 / 격분 5건 미커버

차단 메커니즘:
- 매 PNG 생성 시 hook 자동 발화
- Kimi vision으로 5건 격분 추출
- WARN/REJECT 시 pending_fixes 자동 P0/P1 등록
- patrol SC72 매 사이클 검증

## 비용 (M624 통합)

- K2.5 vision 1024px 입력: 약 $0.0015/호출 (대략 추정)
- 사이클당 5건 최대 = $0.0075/사이클
- M624 `tools/openrouter_usage_check.py` 잔액 < $0.20 시 자동 알림

## 체화 4단계 의무

1. CLAUDE.md Rule OO 등록 (1줄)
2. mistakes.md M626 + FP-26 권고 등록
3. patrol SC72 + AV check_html_quality 6번째 체크 추가
4. ralph_loop_local/web Phase 4.7h 통합 + cron_meta_check MC-7

## M854 Capture Popup Rule: Modal exec is a harness blocker
- In screenshot/evidence harnesses, set `CHEMGRID_CAPTURE_MODE=1` and `CHEMGRID_SKIP_OLLAMA_FALLBACK=1` before importing the app.
- Popup slots used by click-based capture must return control to the harness. In capture/headless mode, use `popup.show()` plus a retained reference instead of `popup.exec()`.
- Heavy local LLMs listed as forbidden by CT must not auto-load during foreground evidence capture. If no-route/no-data fallback is needed, render an explicit fallback/SIMULATION_MODE message and let AV decide REJECT instead of stalling the cycle.
- A QTimer inside the harness is ineffective if the clicked slot enters a modal `exec()` before the timer is installed.

## M879 Dual User-Env Foreground Reject Gate
- Paired user-environment reports must classify targeted foreground probes as BLOCKED, not PASS, when visible clicks reach a popup/window but animation frames or counters do not advance.
- Foreground JSON evidence must include visible-window mode, `offscreen=false`, actual click/QTest/button input, target detection before relative coordinates, render-settle proof, and `direct_code_call_evidence=false`.
- ORCA remote banners must follow the body health contract: degraded `/health` with missing ORCA binary or API key cannot show blue `[REMOTE_DFT]`, and any runtime NameError blocks promotion until a new foreground probe runs.
- CLI pattern: `python housing/sinktank/user_env_auto_verify.py --dual-report --out-dir docs/reports/user_env_dual_verify_YYYYMMDD/WORKER_ID`.

## M881 Dual-Report Pending Fix Integration
- `--dual-report` blockers must be persisted to both `docs/ai/pending_fixes.txt` and `docs/reports/pending_fixes.txt`; a BLOCKED report without pending-fix entries is an audit_integration REJECT.
- Stable pending IDs use `USR-AUTO-DUAL-{BLOCKER_CODE}-{hash(code|message|evidence_path)}` so reruns skip existing unresolved blockers instead of appending duplicate spam.
- Each pending-fix line must include the dual report JSON path and the direct blocker evidence path, including F12 frame/no-promotion blockers, ORCA degraded/name-error blockers, and HTML quality blocker codes.
- `REPORT.md` must record appended/skipped counts for each pending-fix target and must keep `full_app_pass: NOT_CLAIMED` while these blockers remain unresolved.

---

## M1360 PERSONA-CRITIC-KEY-001 패턴 (D-M1153-002-W19 추가)

| 패턴명 | 원칙 |
|--------|------|
| PERSONA-CRITIC-KEY-001 | Rule TT-b에서 OPENROUTER_API_KEY 미설정 시 base 패턴 fallback이 허용되어 있으나, 이는 기능적 degradation(P1). base 패턴만으로는 anger_simulator 189건 중 고난도 한국어 패턴 커버 불가. .env에 OPENROUTER_API_KEY 등록 권장. 미설정 시 patrol SC107 P-PERSONA-KEY-MISSING WARN 발생(비차단). evaluate_answers() 5/5 PASS 기준은 fallback 환경에서도 적용되나 품질 보장 수준이 낮음을 인지. M1360 기원. |

**SC107 탐지 조건**:
```python
# SC107 P-PERSONA-KEY-MISSING (patrol.py 추가 예정)
if not os.environ.get('OPENROUTER_API_KEY'):
    issues.append("SC107 WARN: OPENROUTER_API_KEY 미설정 — Kimi K2.6 base 패턴 fallback (Rule TT-b 허용, P1)")
```

*갱신: 2026-05-18 / Worker W19 / M1360*
*연동: Rule TT-b | patrol SC107 P-PERSONA-KEY-MISSING | prevention_matrix_20260518.md #20*
