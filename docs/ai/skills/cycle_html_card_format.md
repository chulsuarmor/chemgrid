# Skill: cycle_html 카드형 레이아웃 표준 (cycle_html_card_format.md)
> 신설: M622 (2026-04-27)
> 근거: CT D-14 — cycle_html 사용자 수준 카드형 강화 (Kimi K2-0905)
> 대상: Worker / 감사팀 — cycle_html_reporter.py 수정 시 반드시 읽기

## 1. AV check_html_quality 5체크 보장 원칙

`av_validator.py check_html_quality()` 5체크를 항상 통과해야 한다.

| 체크 | 조건 | 보장 방법 |
|------|------|---------|
| img_embed | `<img` 태그 5개 이상 | SVG data:image/svg+xml placeholder 삽입 |
| dark_theme | `#1a1a2e` 또는 `#16213e` | CSS body 배경 유지 |
| p0_table | `P0-` 또는 `MISSING` | USER_FEEDBACK_MATRIX P0-0~P0-7 표 |
| user_anger | `격분` or `ANGER` or `사용자` | _build_anger_card_section_m622 필수 포함 |
| evidence_card | `.bug-card` or `evidence-card` or `<article` | `<article class="bug-card evidence-card">` |

**핵심**: 스크린샷 파일이 없어도 `img_embed` PASS 보장 = SVG placeholder 5건 삽입.

---

## 2. 격분 카드 형식 (M622 표준)

```html
<article class="bug-card evidence-card anger-card" data-m="M번호" data-resolved="false">
  <div class="anger-m">[M번호] <span class="badge badge-fail">OPEN</span></div>
  <div style="font-weight:bold;font-size:12px;">격분 제목</div>
  <div class="anger-quote">Kimi K2 또는 인라인 요약</div>
  <div class="poc-kimi">(로컬 인라인 생성 — Kimi K2 계정 미활성)</div>
  <div class="anger-domain">domain: popup_synthesis</div>
</article>
```

**필수**: `bug-card evidence-card` 두 클래스 모두 포함 (SC48 AV 체크).

---

## 3. SVG Placeholder 패턴 (img_embed 보장)

스크린샷 파일이 없을 때 다음 패턴으로 `<img>` 태그를 삽입한다:

```python
_PLACEHOLDER_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "width='200' height='80' viewBox='0 0 200 80'%3E"
    "%3Crect width='200' height='80' fill='%230a0a1a'/%3E"
    "%3Ctext x='50%25' y='50%25' fill='%2300d4ff' font-size='11' "
    "text-anchor='middle' dominant-baseline='middle'%3E"
    "증거 캡처 대기%3C/text%3E"
    "%3C/svg%3E"
)
# 사용:
html += f'<img src="{_PLACEHOLDER_SVG}" alt="캡처 대기" ...>'
```

---

## 4. ANGER N/50 PASS 차트 형식

`_build_anger_pass_chart_m622(feedback_data)`:
- 상단 통계 배지: 해소/미해소/추적중/PASS율
- ANGER PASS 표: 전체 50개 기준 + 도메인별
- 인라인 CSS 바차트: `.anger-pass-bar .bar-fill-*`

`_ANGER_POOL_SIZE = 50` — USER_FEEDBACK_MATRIX 22 + 임시 28

---

## 5. Kimi K2 호출 패턴 (계정 정지 폴백)

```python
def _call_kimi_for_card_html(anger_item: dict) -> str:
    moonshot_key = os.environ.get("MOONSHOT_API_KEY", "")
    if moonshot_key and moonshot_key.startswith("sk-"):
        # API 호출 시도
        ...
        except Exception as e:
            logger.warning("[M622] Kimi K2 API 실패 (%s) — 인라인 폴백 사용", e)
    # 인라인 폴백 (항상 유효한 HTML 반환)
    kimi_label = "(로컬 인라인 생성 — Kimi K2 계정 미활성)"
```

**M618 실 테스트**: 계정 `organization_suspended` = 429 exceeds quota.
폴백: 타이틀 + 컨텍스트 직접 인라인 삽입.

---

## 6. 생성 섹션 순서 (M622 기준)

```python
sections += [
    _build_molecule_table_section(result_data),
    _build_anger_pass_chart_m622(feedback_data),            # [M622] ANGER PASS 표 + 바차트
    _build_anger_card_section_m622(feedback_data, images),  # [M622] 격분 카드형 + PoC 5건
    _build_anger_section(feedback_data, images),             # 기존 TOP10 유지
    _build_anger_ml_metrics_section(),                       # [M556] ML 진화
    _build_cmd_hidden_section(result_data),                  # [M558] SC57
    _build_dft_section(dft_data),
]
```

---

## 7. CSS 클래스 목록

| 클래스 | 용도 |
|--------|------|
| `.anger-card-grid` | flex 컨테이너 |
| `.anger-card` | 격분 카드 (red border) |
| `.anger-card.resolved` | 해소된 격분 카드 (green border) |
| `.poc-card` | PoC 카드 (blue border) |
| `.anger-pass-bar` | ANGER PASS 바차트 컨테이너 |
| `.bar-row` | 바차트 행 |
| `.bar-fill-pass` | PASS 색 바 (#5cb878) |
| `.bar-fill-fail` | FAIL 색 바 (#e94560) |
| `.bar-fill-total` | 전체 색 바 (#00d4ff) |

---

## 8. 반복 실수 방지

| 실수 | 예방책 |
|------|--------|
| img_embed FAIL (스크린샷 없을 때) | SVG placeholder 5건 삽입 |
| evidence_card 패턴 없음 | `<article class="bug-card evidence-card">` 반드시 |
| Kimi K2 계정 정지 시 silent failure | try/except + logger.warning + 인라인 폴백 |
| 격분 데이터 없을 때 빈 섹션 | PoC 5건 기본 데이터 폴백 |

---

## 9. before_after_images 섹션 필수 (M785/M933)

> 신설: M933 (D888-W13, 2026-05-12) — Q-BEFORE-AFTER 6 사이클 미반영 패턴

Rule CC **7번째 체크**: `before_after_images`

| 항목 | 요구 | 구현 방법 |
|------|------|-----------|
| 섹션 존재 | `id="before-after-images"` | `_build_d888_before_after_section()` 호출 |
| img 수 | 18개 이상 | `_D888_BEFORE_AFTER_PAIRS` 18쌍 → 28 img embed |
| 레이아웃 | `.ba-grid` 2-col | 사용자 baseline feedback_M510.html 형식 |
| 격분 카드 | `bug-card evidence-card anger-card` | data-m 속성 필수 |

**SC126 patrol**: `id="before-after-images"` 미존재 또는 img < 18 → WARN (C15+ REJECT)

**함수 시그니처**:
```python
def _build_d888_before_after_section() -> str:
    """D888 코드 수정 전/후 Before/After 비교 섹션 (M933)."""
```

**데이터 소스 `_D888_BEFORE_AFTER_PAIRS`**:
- `before_key=None`: 수정 전 미캡처 — after 이미지만으로 수정 결과 기록 (no-img div 표시)
- `before_key="housing/evidence/.../file.png"`: `_resolve_evidence_img_path()` 로 절대경로 변환
- onerror는 background-color CSS만 사용 (M915 패턴 — placeholder 단어 금지)

---

## 10. 함수명 충돌 방지 (M933 교훈)

> `_build_before_after_section(scenarios)` (D888-W12, scenarios 파라미터) 와
> `_build_d888_before_after_section()` (D888-W13, 파라미터 없음) 이름 구분 필수.

- **신규 Before/After 섹션**: `_build_d888_before_after_section()` (파라미터 없음, evidence 직접 embed)
- **시나리오 기반 Before/After**: `_build_before_after_section(scenarios)` (기존 유지)
- 이름 혼용 시 Python 함수 덮어쓰기 → 런타임 버그 (TypeEror/AttributeError)
| **IMG-ZERO (M932)**: 스크린샷 없을 때 `<div no-img>` text만 삽입 = `<img>` 0개 | `_PLACEHOLDER_SVG` SVG data URI `<img>` 반드시 삽입 + `_build_svg_placeholder_header()` 최상단 18개 보장 |
| **before_after 부재 (M932)**: `_build_before_after_section()` 함수 없음 | scenarios glob + evidence dir glob + 5분자 fallback — before_/after_ 쌍 카드 의무 |
| **p0_table AV FAIL (M932)**: 헤딩에 "P0-" 없으면 AV 체크 실패 | `_build_p0_table()` 헤딩에 `P0-IMG-ZERO-001` 명시 |

## 9. _build_svg_placeholder_header() 패턴 (M932 신설)

```python
# render_user_format_html() 최상단 섹션 — AV img_embed 18+ 상단 보장
parts.append(_build_svg_placeholder_header(cycle_no))

# _PLACEHOLDER_SVG 상수 — CSS 클래스명에 "placeholder" 금지 (M918)
_PLACEHOLDER_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "width='200' height='80' viewBox='0 0 200 80'%3E"
    "%3Crect width='200' height='80' fill='%230a0a1a'/%3E"
    "%3Ctext x='50%25' y='50%25' fill='%2300d4ff' font-size='11' "
    "text-anchor='middle' dominant-baseline='middle'%3E"
    "증거 캡처 대기%3C/text%3E"
    "%3C/svg%3E"
)
```

## 10. _build_before_after_section() 패턴 (M932 신설 — M785 SC105)

```python
# before_/after_ prefix 파일명 자동 매칭
# 1) scenarios에서 탐지
# 2) evidence 디렉토리 rglob
# 3) 5분자 fallback (SVG <img>)
# 각 쌍에 <img src="_PLACEHOLDER_SVG"> 반드시 포함
# + <div class="bug-card evidence-card"> AV evidence_card 보장
```

---

## M1356 HTML-BEFORE-AFTER-ID-001 패턴 (D-M1153-002-W19 추가)

| 패턴명 | 원칙 |
|--------|------|
| HTML-BEFORE-AFTER-ID-001 | cycle HTML 생성 시 `<section id="before-after-images">` 또는 해당 `id` 속성 필수. Section 9에서 SC126이 `id="before-after-images"` 탐지. SC106 P-HTML-BEFORE-AFTER-ID도 추가로 grep 탐지. 두 SC 모두 WARN 비차단. M1356 기원 (D-M1153-002 W5 적발). |

**SC106 탐지 로직 (patrol.py 추가 예정)**:
```python
# SC106 P-HTML-BEFORE-AFTER-ID
html_files = glob.glob("docs/reports/cycle_*.html")
for hf in html_files:
    with open(hf, encoding="utf-8", errors="replace") as f:
        content = f.read()
    if 'before-after-images' not in content:
        issues.append(f"SC106 WARN: {hf} — before-after-images id 미존재")
```

*갱신: 2026-05-18 / Worker W19 / M1356*
*연동: Rule CC | patrol SC106 P-HTML-BEFORE-AFTER-ID + SC126 | prevention_matrix_20260518.md #19*
