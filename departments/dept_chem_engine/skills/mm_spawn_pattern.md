# MM Spawn Pattern (공통 스킬)

## 문제
MM이 분석만 하고 기획자(P)를 spawn하지 않는 패턴 반복 발생 (2026-03-18, Wave 3 전 부서).

## 원인
- MM 컨텍스트가 분석 단계에서 이미 많이 소모됨
- "승인 대기" 습관 → 자율 모드에서는 불필요

## 올바른 패턴
MM 세션에서 반드시:
1. 분석 (context_list 읽기, 코드 분석)
2. **즉시** Agent(P-XXX) spawn → 구현 위임
3. P 완료 후 **즉시** Agent(R-XXX) spawn → 검증
4. R PASS → SUBMIT 보고서 작성

"승인 대기" 단계 없음. 분석이 끝나면 바로 P를 spawn할 것.
