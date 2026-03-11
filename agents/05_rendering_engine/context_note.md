# 📝 🌈 렌더링 엔진 — Technical Notes
## 기술적 판단 및 결정 기록

---

### [2026-03-01] Phase 6-3: 공명구조 균등화 + 사용자 LP 제외

#### 1. 명령 1: 공명구조 전자구름 균등화 (이슈 #3B)

**문제:** 오각고리 방향족 음이온 등 공명구조에서 전자구름이 불균등 (일부 파랑, 일부 빨강)

**해결:** `_render_atom_clouds_inner()` 내부에서:
1. `charges` dict를 `dict(charges)`로 **복사** (원본 오염 방지 — context_plan 지시 준수)
2. `results["rings"]` 또는 `aromatic` set에서 고리 원자 감지
3. 고리 내 모든 원자의 전하 평균 계산 → 동일 값으로 대입
4. 결과: 공명 고리 원자들이 **동일 색상**으로 렌더링됨

**설계 결정:**
- rings 데이터가 있으면 rings 사용, 없으면 aromatic set fallback → 두 가지 데이터 소스 호환
- 모든 고리를 하나로 합쳐(union) 전체 평균 → 나프탈렌 등 융합 고리에서도 전체 동등 처리
- 복사본만 수정하므로 `results["charges"]` 원본은 보존됨 (다른 렌더링 단계에 영향 없음)

#### 2. 명령 2: 사용자 비공유전자쌍 전자구름 제외 (이슈 #4)

**문제:** 사용자가 반응 메커니즘 표기용으로 추가한 비공유전자쌍(점 2개)이 전자구름 색상에 영향

**해결:** `_render_atom_clouds_inner()` 렌더링 루프 시작 부분에서:
- `atom_data.get("user_lp")` → True이면 skip
- `atom_data.get("main") == "LP"` → LP 원소 기호이면 skip

**설계 결정:**
- 기존 `at_main = atoms.get(pt_key, {}).get("main", "C")`를 `atom_data = atoms.get(pt_key, {})` + `at_main = atom_data.get("main", "C")`로 리팩토링하여 dict 조회 1회 감소
- LP 원자는 렌더링 순서(`_build_render_order`)에는 포함되지만 실제 그리기에서 skip → 성능 영향 무시 가능

#### 3. 자가 검증 결과
- AST parse: OK
- save/restore: 6:6 BALANCED (코드 내 실제 호출 기준, 주석/독스트링 제외)
- 신규 로직 존재: ring_atoms_all, avg_charge, user_lp, dict(charges), Resonance equalization 로그 — 전항목 FOUND

---

### [2026-03-01] U7 긴급 수정: 전자구름 색상 누출 방지 + CPK 원소 색상

#### 1. 문제 분석
사용자 보고: "산소(O)가 파랗게, 산소 옆 C/H가 빨갛게 표기됨"

**원인 A (해결):** `draw_clouds()` → `_render_atom_clouds()` 내부에서 `painter.setBrush()` / `painter.setPen()`으로 전하 기반 색상을 설정한 후, painter 상태를 복원하지 않음. 이후 `layer_logic.py`의 원자 라벨 렌더링에서 해당 색상이 잔류.

**원인 B (해결):** Lewis/Theory 원자 렌더링에서 `atom_color = Qt.GlobalColor.black`으로 모든 원소를 동일 색으로 그리고 있음. 전자구름 색이 원소 색으로 오인됨.

#### 2. 수정 내용

**STEP 1: painter.save()/restore()**
- `draw_clouds()` 전체를 `painter.save()` / `try: ... finally: painter.restore()`로 감싸 전자구름 렌더링 후 painter 상태가 반드시 복원되도록 함
- 코드 레벨 검증: save=5, restore=5 — 완벽 균형 (기존 4:4 → 5:5)

**STEP 2: ELEMENT_COLORS + get_element_color()**
- 모듈 상단에 `ELEMENT_COLORS: Dict[str, QColor]` — 20개 원소 CPK 표준 색상
- `get_element_color(element, is_selected)` — 공용 함수
- Agent 03이 `layer_logic.py`에서 `from renderer import get_element_color` 하여 사용
- Agent 02가 `draw.py`에서 `from renderer import get_element_color` 하여 사용

#### 3. save/restore 현황 (전체 5쌍)
| 메서드 | save | restore | 비고 |
|--------|------|---------|------|
| `draw_dft_density_clouds()` | ✅ | ✅ | 기존 |
| `draw_charge_indicator()` | ✅ | ✅ | 기존 |
| `draw_clouds()` | ✅ | ✅ | **U7 신규** (try/finally) |
| `draw_crosshairs_v32()` | ✅ | ✅ | 기존 |
| `draw_stereo_labels()` | ✅ | ✅ | 기존 |

#### 4. ELEMENT_COLORS 설계 결정
- QColor를 dict에 직접 저장 (Qt 초기화 전에 QColor 생성이 필요하므로, 앱 시작 시 자동 생성)
- `get_element_color()`에서 `QColor(...)` 복사본 반환 — 호출자가 반환값을 수정해도 원본 dict 영향 없음
- 선택 하이라이트: Material Blue (#2196F3) — 기존 Qt.GlobalColor.blue 대신 더 부드러운 색상

---

### [2026-02-28] renderer.py v4.0 리팩토링

#### 1. draw_clouds() 분리 전략
`draw_clouds()`를 완전히 별개 함수로 분리하지 않고, **CloudRenderer 클래스 내 @staticmethod 헬퍼**로 분리.
- 이유: `draw_clouds()`가 results dict, charges, atoms 등 공유 컨텍스트가 많아 독립 함수로 빼면 파라미터가 과도하게 많아짐
- 결과: 오케스트레이터(draw_clouds) + 8개 내부 헬퍼

분리된 메서드:
| 메서드 | 역할 |
|--------|------|
| `_calculate_local_contrast()` | 고리 탄소 전하 범위 계산 |
| `_calculate_bond_stats()` | 평균 결합 길이 / 최대 구름 반지름 |
| `_calculate_density_stats()` | ESP 밀도 min/max |
| `_build_render_order()` | 치환기→고리 순서 결정 |
| `_render_atom_clouds()` | 원자별 가우시안 루프 (핵심) |
| `_atom_scales()` | 원자별 cloud_scale/density_scale |
| `_calculate_charge_color()` | 원자 하나의 (QColor, alpha) 결정 |
| `_store_crosshair_data()` | 조준선 좌표 results에 저장 |

#### 2. DFTDensityRenderer 통합
- `DFTDensityRenderer` 클래스를 삭제하고 모든 메서드를 `CloudRenderer`로 이동
- `DFTDensityRenderer = CloudRenderer` 별칭으로 **하위 호환성 100% 유지**
- draw.py 등 외부에서 `from renderer import DFTDensityRenderer` 해도 정상 동작

#### 3. print 제거 → logging
- 기존: 매 프레임 `print()` 15회+ 호출 → **심각한 성능 저하**
- 변경: `logging.getLogger(__name__)` + `logger.debug()`
- 효과: 기본 로그레벨(WARNING)에서는 출력 없음 → 성능 회복
- 디버깅 필요 시: `logging.basicConfig(level=logging.DEBUG)` 설정

#### 4. QPen import 누락 버그 수정
- `draw_crosshairs_v32()`에서 `QPen` 사용하나 import 누락되어 있었음
- `from PyQt6.QtGui import ... QPen` 추가로 해결

#### 5. 주의사항
- `layer_logic.py`의 `LewisRenderer` 내 print문은 **Agent 03 도메인** → 수정하지 않음
- `_calculate_charge_color()` 파라미터가 18개로 많음 → 향후 dataclass로 묶는 것 고려
- `_render_atom_clouds()` 내부 densities 매칭이 O(n²) → 대형 분자에서 최적화 필요 가능성
