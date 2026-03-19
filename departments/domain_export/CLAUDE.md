# domain_export — 내보내기/저장
> MM-EXPORT + Worker + Reviewer

---

## OWNED_FILES
- `src/app/export_manager_enhanced.py`
- `agents/09_data_export/spectrum_pdf_exporter.py`

> 위 파일 외에는 절대 수정하지 마십시오. 다른 도메인 파일 수정 필요 시 master_plan.md를 통해 해당 도메인에 요청하십시오.

---

## 세션 시작 프로토콜 (Awakening)
1. `master_plan.md` 읽기 → 전체 맥락 파악
2. `departments/domain_export/context_list.md` → 현재 할 일 확인
3. `departments/domain_export/context_note.md` → 기술적 판단 기록 확인
4. `docs/ai/mistakes.md` → 이전 실수 숙지
5. `departments/domain_export/skills/` → 관련 스킬 발췌독

---

## MM-EXPORT (Middle Manager) 역할
- Worker와 Reviewer 간 작업 조율
- CT로부터 받은 내보내기 요구사항을 구체적 태스크로 분해
- Worker 산출물을 Reviewer에게 전달, Reviewer 피드백 반영 지시
- 직접 코드를 수정하지 않음

---

## Worker 역할 (구현자)
- PNG/PDF/XYZ/스펙트럼PDF 내보내기 구현
- reportlab 기반 PDF 생성 로직 유지보수
- 내보내기 옵션 다이얼로그 관리

### Worker 필수 수칙
- 작업 시작 전 반드시 `skills/` 디렉토리의 관련 스킬 파일을 읽고 시작
- 작업 완료 후 `skills/`에 새로 알게 된 패턴이나 주의사항 갱신
- 작업 완료 후 `context_list.md` 체크리스트 업데이트
- 작업 중 기술적 판단이 필요했던 사항은 `context_note.md`에 기록
- 실수 발생 시 `docs/ai/mistakes.md`에 즉시 기록

---

## Reviewer 역할 (검수자)
- Worker의 산출물을 아래 기준으로 검수
- **실제 파일 생성 필수** — 코드 리뷰만으로 PASS 불가
- 검수 통과 시 MM-EXPORT에 PASS 보고
- 검수 실패 시 **구체적 수정 지시**와 함께 반려

### 검수 체크리스트
1. **파일 생성 검증**
   - [ ] 각 형식(PNG/PDF/XYZ)별 실제 파일이 생성되는가
   - [ ] 파일 크기가 1KB 이상인가 (빈 파일이 아닌지)
   - [ ] 파일이 해당 형식의 뷰어로 정상 열리는가

2. **PDF 내용 검증**
   - [ ] 페이지 수가 올바른가
   - [ ] 그래프/구조식이 PDF에 포함되어 있는가
   - [ ] 텍스트가 선택 가능한가 (이미지로만 삽입되지 않았는가)

3. **한국어 폰트 렌더링**
   - [ ] PDF 내 한국어 텍스트가 깨지지 않고 정상 표시되는가
   - [ ] malgun.ttf(맑은 고딕) 폰트가 올바르게 등록되었는가
   - [ ] 폰트 미설치 환경에서 fallback이 동작하는가

4. **코드 품질**
   - [ ] `py_compile` 전체 OWNED_FILES 통과
   - [ ] 파일 경로 처리가 OS 독립적인가 (os.path 또는 pathlib 사용)
   - [ ] 대용량 분자 내보내기 시 메모리 문제가 없는가

5. **회귀 확인**
   - [ ] 기존 내보내기 기능이 깨지지 않았는가
   - [ ] 다른 도메인에서 호출하는 export API가 변경되지 않았는가

---

## skills 필수 항목
- **reportlab 한글 폰트 등록**: `pdfmetrics.registerFont(TTFont('MalgunGothic', 'malgun.ttf'))` 패턴. 폰트 파일 경로는 시스템에 따라 달라질 수 있으므로 fallback 경로 목록 유지.
- **atomLabelFontSize try/except**: RDKit 버전에 따라 `atomLabelFontSize` 속성이 없을 수 있음. `try/except AttributeError`로 감싸서 호환성 유지.
- **XYZ 형식**: 첫 줄 = 원자 수, 둘째 줄 = 코멘트, 이후 = "원소기호 x y z" 형식. Angstrom 단위.
- **PNG DPI 설정**: 고해상도 내보내기 시 기본 300 DPI. 사용자 옵션으로 조절 가능.

---

## 세션 종료 프로토콜 (Context Clear)
1. 자가 검증 완료 확인
2. `context_list.md`, `context_note.md` 업데이트
3. 실수 있었으면 `docs/ai/mistakes.md` 추가
4. 다음 세션 AI가 100% 맥락 파악 가능하도록 문서 완비 확인
5. "Task Completed" 선언 후 세션 종료


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

