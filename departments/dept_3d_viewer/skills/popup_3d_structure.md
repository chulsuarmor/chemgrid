# popup_3d.py 구조 가이드
> 5500+ 라인의 대형 모듈. 수정 전 반드시 이 가이드를 읽으십시오.

## 5개 탭 구조
1. **Properties** — 결합 길이, 결합 각도, 물성
2. **Spectra** — IR/Raman/NMR/UV-Vis 5종 스펙트럼
3. **Vibration** — 27~49개 진동 모드 애니메이션
4. **AI Analysis** — Gemini API 분석 (선택적)
5. **Docking** — AutoDock Vina 에너지 + 상호작용

## 최소 창 크기
- 800x600px 강제 (QWidget.setMinimumSize)

## 3D 좌표 정규화
- 모든 좌표 round(2) 적용
- PyOpenGL 기반 Ball&Stick 렌더링

## scikit-image 의존성
- marching_cubes for isosurface mesh
- Fallback: scatter-point if unavailable

## 오비탈 렌더러 구분 (CRITICAL)
- **PiOrbitalRenderer** (sp2 π 오비탈 모드): gluSphere 물방울형 로브 + 납작 디스크 π cloud
  - `_draw_p_orbital_lobes()`: glPushMatrix → glTranslatef → glRotatef → glScalef(0.78, 0.78, 1.40) → gluSphere
  - `_draw_ring_pi_cloud()`: gluSphere(sq, 1.0, 28, 18) + glScalef로 납작 원판
  - **절대 MC 점밀도로 변환하지 말 것** — 사용자가 승인한 시각적 결과물
- **AdvancedOrbitalRenderer** (전체 오비탈/혼성 모드): MC 점밀도 방식
  - `_lobe()`: Monte Carlo rejection sampling + GL_POINTS
  - 개구리알 문제 해결 필요 시 점 밀도/분포 조정
