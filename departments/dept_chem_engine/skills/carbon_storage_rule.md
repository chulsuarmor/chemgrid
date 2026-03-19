# 탄소 원자 저장 규칙
> 이 규칙을 위반하면 ESP 전자구름 렌더링이 완전히 깨집니다.

## 규칙
- 탄소(C)는 `at_sym == ''` (빈 문자열)로 저장됨
- 절대로 `at_sym == "C"`로 비교하지 마십시오
- 이 규칙은 chem_data.py의 ELEMENT_DATA 구조에서 비롯됨

## 영향받는 코드
- engine_physics.py: 전하 계산 시 탄소 감지
- analyzer.py: 원자 분석 시 탄소 필터링
- renderer.py: ESP 구름 색상 매핑

## Gasteiger 블렌딩
- 60% Gasteiger + 40% 커스텀 전하
- 방향족 공명 등가성을 위한 하이브리드 접근
