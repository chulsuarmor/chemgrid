# 시각적 피드백 QA 부서 기술 노트
> 최종 업데이트: 2026-03-18 | P-VF + R-VF Cascade #3 Wave 4

---

## 수정파일
- `src/app/tests/test_visual_auto.py` (OWNED) — v2 → v3 업그레이드
- `_source/tests/test_visual_auto.py` (DUAL SYNC)

## 기획자 보고 (P-VF)

### 변경 사항
1. **36개 시나리오 확장** (기존 32개 → 36개)
   - 섹션 H 추가: ReactionPopup (텍스트북 스타일 반응경로), SynthesisPopup (역합성)
   - 섹션 I 추가: Caffeine (퓨린고리 + 카르보닐 복합분자 Drawing/Theory)
   - 오비탈 모드 캡처를 최대 2장으로 제한하여 총 36장 목표

2. **아카이브 시스템 신규 구축**
   - `archive_screenshots()` 함수 추가
   - 실행 완료 시 `departments/archive/screenshots/YYYY-MM-DD.zip`에 자동 아카이브
   - PNG 파일 + results.json 포함

3. **API 정합성 수정**
   - ReactionPopup: `smiles_list=["..."], names=["..."]` 시그니처 준수
   - SynthesisPopup: `target_smiles="...", target_name="..."` 시그니처 준수
   - bare except → `except Exception` 정리

### 시나리오 매핑 (36장)
| 섹션 | 번호 | 내용 | 수량 |
|------|------|------|------|
| A | A01-A07 | Drawing/Theory (빈화면, 에탄, 에탄올, 벤젠, 프로판, 수동그리기) | 7 |
| B | B01-B03b | Lewis (물, 아세트산, 암모니아 + 확대) | 6 |
| C | C01-C06 | 3D팝업 (속성, 스펙트럼5종, IR복귀, 진동, 오비탈2, 도킹, AI) | 12 |
| D | — | PDF 6페이지 (검사만, 스크린샷 없음) | 0 |
| E | E01-E02 | 반응경로 (Drawing, Theory) | 2 |
| F | F01-F03 | 아스피린 (Drawing, Theory, Lewis) | 3 |
| G | G01-G02 | 아스피린 3D (Ball&Stick, 오비탈) | 2 |
| H | H01-H02 | ReactionPopup + SynthesisPopup | 2 |
| I | I01-I02 | 카페인 (Drawing, Theory) | 2 |
| **합계** | | | **36** |

## 검수자 판정 (R-VF)

| 검증 항목 | 결과 |
|-----------|------|
| py_compile | PASS |
| ast.parse | PASS (8 functions) |
| _source/ 동기화 | PASS (바이트 일치) |
| OWNED_FILES 준수 | PASS (test_visual_auto.py만 수정) |
| 타 부서 파일 침범 | 없음 |

**R-VF 최종 판정: PASS**

## 감사 요청
- 전문감사(audit_professional_final_review)에 상신 요청
- 실제 GUI 실행 테스트는 다음 VF 세션에서 수행 필요 (conda chemgrid 환경)

## 기술적 판단 기록
- C섹션 오비탈: combo.count()가 동적이므로 min(count, 2)로 제한하여 총 36장 유지
- SynthesisPopup은 _start_search()를 생성자에서 호출하므로 headless에서 스레드가 시작됨; grab 전 processEvents 3회로 충분
- PDF 검증은 스크린샷 없이 바이트 크기/페이지 수 체크만 수행 (matplotlib Agg 백엔드)

## 발견된 문제 / 블로커
(없음)

## 타 부서 요청 사항
(없음)
