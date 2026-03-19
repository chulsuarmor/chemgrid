# 3D 뷰어/궤도함수 부서 기술 노트
> 최종 업데이트: 2026-03-18 | Cascade #3 Wave 2 P-3D 세션

## 기술적 판단 기록

### [2026-03-18] Cascade #3 Wave 2: 3D-R01 오비탈 시각화 개선

**진단**: popup_molorbital.py의 기존 TASK-3D-007 gradient isosurface 코드 분석.

**발견된 문제 2가지**:
1. **비표준 colormap**: HOMO=Blues/Reds, LUMO=Oranges/Purples 사용 중. 화학 교과서(Atkins, Clayden) 및 GaussView/Avogadro 표준은 모든 오비탈에서 +phase=blue, -phase=red 통일. 오비탈 정체(HOMO/LUMO)는 제목 레이블로 구분.
2. **거리 기반 gradient만 사용**: face 중심→분자 중심 거리로 색상 강도를 결정. 실제 orbital amplitude 보간이 가능하면 더 물리적으로 의미 있는 gradient 생성 가능.

**해결 (FIX-3D-007v2)**:
1. 모든 오비탈에 `pos_cmap=Blues`, `neg_cmap=Reds` 통일 적용 (화학 convention 준수)
2. `_interpolate_amplitude_at_points()` 정적 메서드 추가:
   - scipy.ndimage.map_coordinates로 cube grid 데이터에서 face centroid 위치의 실제 orbital amplitude를 trilinear 보간
   - scipy 미설치 시 기존 거리 기반 fallback 자동 적용
3. `_compute_gradient_colors()`: amplitude 보간 우선, 실패 시 거리 기반 fallback

**설계 판단 근거**:
- Trilinear interpolation은 isosurface 상에서 wavefunction magnitude 변화를 직접 반영 → nodal plane 근처에서 자연스러운 색상 감쇠
- scipy가 대부분의 과학 Python 환경에 설치되어 있으므로 실용적
- order=1 (bilinear) 사용으로 계산 비용 최소화

### [2026-03-18] Cascade #3 Wave 2: 3D-R02 진동 애니메이션 검증

**진단 결과 (수정 불필요)**:
- `start_vibration()` / `stop_vibration()` / `_vib_tick()`: 3개 뷰어 클래스(BallStickRenderer, FallbackRenderer2D, Molecule3DViewer) 모두 정상 구현
- displacement vectors 연결: `vibration_engine.py` → `VibrationPanel.get_displacement_vectors()` → `_on_vib_mode_selected()` → `viewer.start_vibration(vectors, amp)` 체인 정상
- bond strain 색상 코딩 (TASK-3D-005): OpenGL/QPainter 양쪽 모두 정상 동작
  - 신장(strain>2%): gray→red, 압축(strain<-2%): gray→blue
  - ±15% clamp으로 비물리적 overshoot 방지
- 타이머: 30ms (~33fps), sin wave 진동, phase 0.1 rad/frame → 주기 ~1.9초
- 원자 변위 + 결합 신축이 동기화됨 (displaced_positions 맵 공유)
- 인덱스 안전 가드: `idx < len(vib_vectors)` 체크 일관 적용

**결론**: TASK-3D-005의 bond strain 시각화와 진동 애니메이션은 완성 상태. 추가 수정 불필요.

### [2026-03-18] TASK-3D-006: 메탈로센 3D 렌더링 진단 및 해결

**진단 방법**: 5개 타겟 분자(norbornane, adamantane, ferrocene, cubane, spiropentane)에 대해 `generate_3d_full_from_smiles()` 호출 후 atom_positions, bonds, Z spread 검증.

**결과**: norbornane/adamantane/cubane/spiropentane는 기존 5단계 임베딩 전략으로 정상 처리. ferrocene만 문제 발견.

**ferrocene 근본 원인**:
- SMILES `[Fe+2].[cH-]1cccc1.[cH-]1cccc1`는 이온성 복합체 (3개 disconnected fragments)
- RDKit EmbedMolecule는 각 fragment를 독립적으로 임베딩 → 두 Cp 고리가 동일 좌표에 겹침
- Fe 원자는 어떤 bond도 없음 (원점에 고정)
- MMFF/UFF 최적화가 Fe2+2 타입을 인식하지 못함 → 물리적 배치 불가

**해결 설계 판단**:
1. BFS 기반 ring finder 시도 → 실패 (visited 방문 기록이 이미 방문한 노드로의 경로를 차단)
2. **Connected component 기반 접근 채택**: 금속 제외한 heavy atoms의 연결 성분이 곧 Cp 고리
3. 금속-탄소 배위 결합은 order=0.5로 표현 → 렌더러에서 dashed cylinder로 시각화
4. Cp 고리 배치: 정오각형 (r=1.21 A), Fe-Cp distance=1.66 A, 두번째 고리는 36도 회전 (staggered)

### [2026-03-18] TASK-3D-005: bond stretching 시각화

**판단**: 진동 시 bonds가 이미 displaced_positions를 사용하여 물리적으로 정확히 늘어남.
다만 "어떤 결합이 늘어나는지" 시각적 피드백 없음.
-> equilibrium vs displaced bond length의 strain 비율로 색상 코딩 추가.

**색상 매핑 설계**:
- strain threshold: +/-2% 미만은 색상 변화 없음 (시각적 노이즈 방지)
- 최대 +/-15% strain 기준 clamp (비물리적 overshoot 방지)
- 신장: gray->red, 압축: gray->blue (화학 convention과 일치)

### [2026-03-18] TASK-3D-007: gradient isosurface (v1 -> v2로 업그레이드됨)

**v1 판단** (이전 세션): face 중심점에서 분자 중심까지의 거리 기반 gradient colormap 적용.
**v2 판단** (이번 세션): amplitude 보간 우선 + 거리 fallback. 상세는 위 3D-R01 섹션 참조.

## 발견된 문제 / 블로커
(없음)

## 타 부서 요청 사항
(없음)
