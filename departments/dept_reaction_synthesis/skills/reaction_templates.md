# 반응 메커니즘 템플릿 가이드

## 50+ 반응 템플릿
reaction_mechanisms.py에 정의된 반응 유형:
- 친핵성 치환 (SN1, SN2)
- 제거 반응 (E1, E2)
- 친전자성 첨가 (Markovnikov, anti-Markovnikov)
- 에스테르화 (Fischer)
- 산화/환원 반응
- 방향족 치환 (EAS, NAS)

## 곡선 화살표 (Electron Pushing)
- arrow_generator.py (dept_rendering 소유)와 협업
- 이 부서는 메커니즘 로직만, 시각화는 rendering에 위임

## popup_reaction.py v3.0
- 교과서 스타일 반응 시각화
- 다단계 반응 경로 표시
