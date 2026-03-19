# 전문적학습공동체(전학공) 운영 매뉴얼
> Professional Learning Community (PLC) Operations Manual

---

## 1. 개요
전학공은 같은 직렬(기획자/검수자/감사팀)의 에이전트들이 주기적으로 모여 자신들의 mistakes.md 및 skills 내용을 공유하는 교차학습 체계입니다.

**목적**: 각 부서에서 약간씩 다른 도메인의 비슷한 업무를 수행하면서 발견한 긍정적 개선사항을 서로 공유하여 전문성 신장 속도를 가속시킴.

---

## 2. 트리거 조건
전학공은 다음 조건이 **모두** 충족된 후에만 실시합니다:
1. ✅ 전체 부서의 MM→P→R 사이클 완료
2. ✅ 전문감사팀(Professional Audit) 검수 완료
3. ✅ 최종감사팀(Final Audit)의 **사용자 환경 피드백** 완료 (실제 ChemGrid 앱 실행 + GUI 전체검사 + 스크린샷)
4. ✅ 최종감사팀 → CT(컨트롤 타워)에게 보고 완료
5. ✅ **CT가 전체 전학공 명령 하달**

---

## 3. 실시 순서 (직렬별 순차)

### Phase A: 기획자(Planner) 전학공
- **참여자**: P-UI, P-CHEM, P-RENDER, P-3D, P-SPEC, P-RXTN, P-DFT, P-DOCK, P-EXPORT, P-VF, P-TEST, P-ALPHA
- **공유 내용**:
  - 각 부서 `mistakes.md`에서 기획 단계 관련 교훈
  - 각 부서 `skills/`에서 구현 패턴, 코딩 기법
  - 듀얼 코드베이스 동기화 노하우
  - py_compile/ast.parse 사전 검증 습관
- **산출물**: 공유된 개선사항을 각자 부서의 skills/에 반영

### Phase B: 검수자(Reviewer) 전학공
- **참여자**: R-UI, R-CHEM, R-RENDER, R-3D, R-SPEC, R-RXTN, R-DFT, R-DOCK, R-EXPORT, R-VF, R-TEST, R-ALPHA
- **공유 내용**:
  - 검증 방법론 (py_compile, ast.parse, headless test 기법)
  - PASS/FAIL 판정 기준 통일
  - 놓치기 쉬운 검증 포인트 (듀얼 동기화, import 누락 등)
  - 반려 시 구체적 수정사항 기술 방법
- **산출물**: 검수 체크리스트 표준화, 공통 검증 패턴 공유

### Phase C: 감사팀(Auditor) 전학공
- **참여자**: audit_popup_qa, audit_integration_qa, audit_rendering_qa, audit_visual_feedback, audit_professional_pharma, audit_professional_spectral, audit_final
- **공유 내용**:
  - 감사 기준 및 WARN/FAIL 판정 근거
  - 외부 참조 데이터 활용법 (NIST, PubChem, Silverstein, CRC Handbook)
  - GUI 시각 검증 기법 (QWidget.grab(), WA_DontShowOnScreen)
  - 부서 간 통합 검증 포인트
- **산출물**: 감사 품질 기준 표준화, 교차 참조 데이터 소스 공유

---

## 4. 공유 원칙
- ❌ 너무 지엽적인 부서 고유 사항은 제외
- ✅ 다른 부서에도 적용 가능한 **긍정적 개선사항** 중심으로 공유
- ✅ 실수 반복 방지를 위한 **공통 패턴** 공유
- ✅ 각 부서의 도메인 특성을 존중하되, 범용 교훈 추출

---

## 5. 전학공 완료 후 프로세스
1. 각 직렬별 전학공 결과를 CT에게 요약 보고
2. CT가 master_plan.md의 미구현 방향성 검토
3. CT가 새로운 전체 업무지침 하달 → 다음 Cascade 디스패치
4. 전체 루프 재시작

---

## 6. 전학공 실시 기록 양식
```markdown
## 전학공 #N — [직렬명] (YYYY-MM-DD)
### 참여 에이전트
- (목록)
### 공유된 개선사항
1. [부서명] → [교훈/개선사항]
2. ...
### 채택 결과
- [어떤 부서가 어떤 개선사항을 자기 skills에 반영했는지]
### CT 보고 완료: [Y/N]
```
