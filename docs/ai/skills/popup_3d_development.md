# Skill: popup_3d.py 개발 가이드

## 파일 크기 주의
`popup_3d.py`는 ~5500줄의 대형 파일. 전체를 한번에 읽지 말고 필요한 섹션만 읽기.

## 주요 섹션 (줄 번호 대략적)
| 섹션 | 시작 줄 | 내용 |
|------|---------|------|
| CPK Colors/Radii | ~130 | VDW/Covalent 반경, CPK 색상 |
| GeminiAnalyzer | ~594 | Gemini API 래퍼 |
| Molecule3DData | ~660 | 3D 분자 데이터 클래스 |
| BallStickRenderer | ~750 | OpenGL Ball&Stick 렌더러 |
| SpaceFillingRenderer | ~900 | OpenGL Space-filling 렌더러 |
| PiOrbitalRenderer | ~970 | π 오비탈 렌더러 |
| AdvancedOrbitalRenderer | ~1100 | sp/sp2/sp3/d/f 혼성 오비탈 |
| Molecule3DViewer | ~1900 | QOpenGLWidget 메인 뷰어 |
| PropertiesPanel | ~2600 | 속성 탭 |
| SpectrumPanel | ~2700 | 스펙트럼 탭 (matplotlib) |
| VibrationPanel | ~3534 | 진동모드 탭 |
| AIAnalysisPanel | ~3597 | AI 분석 탭 (Gemini) |
| DockingEnergyPanel | ~4393 | 도킹 에너지 탭 |
| Molecule3DPopup | ~5013 | 통합 팝업 윈도우 |

## 새 탭 추가 패턴
```python
# 1. QWidget 서브클래스 정의
class NewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    def _init_ui(self):
        layout = QVBoxLayout()
        # ... UI 구성
        self.setLayout(layout)

# 2. Molecule3DPopup._init_ui()에서 탭 추가
self.tab_new = NewPanel()
self.tabs.addTab(self.tab_new, "🔬 새탭")

# 3. _load_data()에서 데이터 전달
self.tab_new.set_data(smiles, orca_info)
```

## OpenGL 렌더링 패턴
- 모든 OpenGL 호출은 `OPENGL_AVAILABLE` 가드 필수
- 원자: `gluSphere(quad, radius, slices, stacks)`
- 결합: `gluCylinder(quad, r1, r2, length, slices, stacks)` + glRotate/Translate
- 투명도: `glEnable(GL_BLEND)` + `glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)`
- 라이팅 끄기: `glDisable(GL_LIGHTING)` (선 그리기 전)
- 라이팅 켜기: `glEnable(GL_LIGHTING)` (구/실린더 전)

## 단백질 3D 시각화
`Molecule3DViewer`에 `set_protein_data(ca_atoms, binding_site)` 추가됨.
- Cα 백본: GL_LINE_STRIP (체인별 색상)
- 결합 부위: 반투명 구 (gluSphere, alpha=0.15)
- 접근 애니메이션: `start_dock_approach()` — 리간드가 결합 부위로 이동
