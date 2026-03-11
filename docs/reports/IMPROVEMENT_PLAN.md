# 🚀 ChemDraw Pro: 개선 계획 (Improvement Roadmap)

**작성일**: 2026-02-06 10:41 GMT+9  
**목표**: 초기 명세 대비 75.2 → 90+ 달성  
**기간**: 3개월 (Phase별 1주 집중)

---

## 📊 개선 전략 (Improvement Strategy)

### 우선순위 기반 분류

| 우선순위 | 항목 | 점수 증가 | 난이도 | 예상 시간 |
|---------|------|---------|-------|---------|
| 🔴 P0 | 오류 처리 & 사용자 안내 | +8점 | 중 | 1주 |
| 🟠 P1 | 성능 최적화 (렌더링) | +7점 | 중상 | 1.5주 |
| 🟠 P1 | SMILES 정확도 개선 | +6점 | 중 | 1주 |
| 🟡 P2 | 실시간 동기화 (IUPAC) | +5점 | 중 | 1주 |
| 🟡 P2 | 3D 좌표 최적화 | +4점 | 상 | 1.5주 |
| 🟢 P3 | OpenGL 안정성 | +3점 | 중상 | 5일 |

---

## 🔴 P0: 오류 처리 & 사용자 안내 시스템

### 목표
- 모든 예외를 사용자 친화적으로 처리
- 에러 로깅 시스템 구축
- 점수: +8점 (78 → 86점)

### 구현 계획

#### 1. 중앙 집중식 오류 처리 (ErrorHandler 클래스)

```python
# error_handler.py (신규)
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import pyqtSignal, QObject
import traceback
import logging
from datetime import datetime

class ErrorHandler(QObject):
    """중앙 집중식 오류 처리 및 로깅"""
    error_occurred = pyqtSignal(str, str)  # (title, message)
    
    _instance = None
    
    def __init__(self):
        super().__init__()
        self.setup_logging()
    
    @staticmethod
    def instance():
        if ErrorHandler._instance is None:
            ErrorHandler._instance = ErrorHandler()
        return ErrorHandler._instance
    
    def setup_logging(self):
        """로깅 설정"""
        log_file = f"chemDraw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logging.basicConfig(
            filename=log_file,
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
    
    def handle_error(self, error_type: str, exception: Exception, 
                     context: str = "", show_dialog: bool = True):
        """
        오류 처리
        
        Args:
            error_type: "ORCA", "PHASE_B", "PHASE_C", "PHASE_D" 등
            exception: Exception 객체
            context: 오류 발생 위치 설명
            show_dialog: 사용자 팝업 표시 여부
        """
        # 로깅
        error_msg = f"[{error_type}] {context}\n{traceback.format_exc()}"
        logging.error(error_msg)
        
        # 사용자 메시지
        user_msg = self._get_user_friendly_message(error_type, str(exception))
        
        # 신호 발출
        self.error_occurred.emit(error_type, user_msg)
        
        # 팝업 표시
        if show_dialog:
            QMessageBox.critical(None, f"오류: {error_type}", user_msg)
    
    def _get_user_friendly_message(self, error_type: str, exception_str: str) -> str:
        """오류 타입별 사용자 친화적 메시지 생성"""
        messages = {
            "ORCA": """
            ORCA 계산 중 오류가 발생했습니다:
            - 분자 구조를 확인하세요
            - Orca.exe 경로를 확인하세요
            - 충분한 디스크 공간이 있는지 확인하세요
            """,
            "PHASE_B": """
            ESP 계산 중 오류가 발생했습니다:
            - 전자 밀도 데이터가 누락되었을 수 있습니다
            - ORCA 계산을 다시 시도하세요
            """,
            "PHASE_C": """
            3D 뷰어를 열 수 없습니다:
            - OpenGL이 지원되지 않는 시스템일 수 있습니다
            - GPU 드라이버를 업데이트하세요
            """,
            "PHASE_D": """
            IUPAC 분석 중 오류가 발생했습니다:
            - 분자식이 유효하지 않을 수 있습니다
            - RDKit 버전을 확인하세요
            """,
        }
        return messages.get(error_type, exception_str)

# draw.py에서 사용
ErrorHandler.instance().handle_error(
    "ORCA", 
    exception,
    "ORCA 계산 시작 중"
)
```

#### 2. 각 Phase의 오류 처리 개선

```python
# orca_interface.py 수정
def _parse_out_file(out_path: Path) -> OrcaCalculationResult:
    """ORCA output 파일 파싱 + 에러 처리"""
    try:
        # ... 파싱 로직
        if not result.converged:
            ErrorHandler.instance().handle_error(
                "ORCA",
                RuntimeError("수렴 실패"),
                "ORCA 최적화 미수렴",
                show_dialog=True
            )
        return result
    except Exception as e:
        ErrorHandler.instance().handle_error("ORCA", e, "Output 파일 파싱")
        return OrcaCalculationResult(...)
```

#### 3. 사용자 알림 대시보드

```python
# status_panel.py (신규)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton

class StatusPanel(QWidget):
    """계산 상태 및 오류 표시 패널"""
    def __init__(self):
        super().__init__()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.clear_btn = QPushButton("로그 지우기")
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.log_text)
        layout.addWidget(self.clear_btn)
        
        ErrorHandler.instance().error_occurred.connect(self.on_error)
    
    def on_error(self, error_type: str, message: str):
        """오류 표시"""
        self.log_text.append(f"❌ [{error_type}] {message}")
```

### 예상 점수 증가: +8점

---

## 🟠 P1: 성능 최적화 (렌더링 & 캐싱)

### 목표
- ESP 렌더링: 60 FPS 달성
- 대규모 분자 (200+ 원자) 지원
- 점수: +7점 (73 → 80점)

### 구현 계획

#### 1. Radial Gradient 개선 (더 많은 stops)

```python
# renderer.py 수정
class CloudRenderer:
    @staticmethod
    def draw_esp_cloud(painter, esp_map, center, radius):
        """개선된 ESP 클라우드 렌더링 (더 부드러운 gradient)"""
        gradient = QRadialGradient(center, radius)
        
        # 기존: 16 stops
        # 개선: 64 stops (4배 부드러움)
        for i in range(64):
            position = i / 63.0
            # 거리에 따른 ESP 값 보간
            esp_value = max(esp_map.values()) * (1 - position**2)  # 제곱근 감소
            color = CloudRenderer._esp_to_color(esp_value)
            gradient.setColorAt(position, color)
        
        painter.setBrush(gradient)
        painter.drawEllipse(center, radius, radius)
```

#### 2. 계산 캐싱 개선 (메모리 제한)

```python
# renderer.py 수정
from functools import lru_cache
import sys

class CloudRenderer:
    _esp_cache = {}
    _cache_size_limit = 100 * 1024 * 1024  # 100MB
    _current_cache_size = 0
    
    @staticmethod
    def _get_cache_key(densities, atom_positions):
        """캐시 키 생성 (분자 고유 ID)"""
        import hashlib
        data = f"{len(densities)}{len(atom_positions)}".encode()
        return hashlib.md5(data).hexdigest()
    
    @staticmethod
    def draw_clouds_cached(painter, analysis):
        """캐시된 ESP 맵 사용"""
        key = CloudRenderer._get_cache_key(...)
        
        if key in CloudRenderer._esp_cache:
            esp_map = CloudRenderer._esp_cache[key]
        else:
            # 캐시 크기 초과 시 가장 오래된 항목 삭제
            if CloudRenderer._current_cache_size > CloudRenderer._cache_size_limit:
                CloudRenderer._esp_cache.clear()
                CloudRenderer._current_cache_size = 0
            
            # 새 계산
            esp_map = CloudRenderer._calculate_esp(...)
            CloudRenderer._esp_cache[key] = esp_map
        
        CloudRenderer.draw_clouds(painter, {...}, esp_map)
```

#### 3. OpenGL 기반 렌더링 (옵션)

```python
# render_gl.py (신규 - OpenGL 기반 고속 렌더링)
from PyQt6.QtOpenGL import QOpenGLWidget

class GLESPRenderer(QOpenGLWidget):
    """OpenGL 기반 ESP 렌더링 (GPU 가속)"""
    
    def initializeGL(self):
        """OpenGL 초기화"""
        glClearColor(1.0, 1.0, 1.0, 1.0)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        # 쉐이더 컴파일
        self.shader_program = self._compile_shaders()
    
    def paintGL(self):
        """GPU에서 고속 렌더링"""
        glClear(GL_COLOR_BUFFER_BIT)
        
        # VAO/VBO를 통한 배치 렌더링
        glDrawArrays(GL_TRIANGLES, 0, self.vertex_count)
    
    def _compile_shaders(self):
        """OpenGL 쉐이더 컴파일"""
        # Fragment shader로 ESP 값 실시간 계산
        frag_src = """
        varying vec2 fragCoord;
        void main() {
            float esp = calculate_esp(fragCoord);
            gl_FragColor = vec4(esp_to_color(esp), 1.0);
        }
        """
        # 쉐이더 컴파일 로직...
```

### 예상 점수 증가: +7점

---

## 🟠 P1: SMILES 생성 정확도 개선

### 목표
- RDKit 기반 정교한 SMILES 생성
- 웨지/대쉬 정보 보존
- 점수: +6점 (78 → 84점)

### 구현 계획

#### 1. 개선된 SMILES 생성 (draw.py)

```python
# draw.py 수정
def get_smiles(self) -> str:
    """
    RDKit 기반 정교한 SMILES 생성
    - 웨지/대쉬 정보 보존
    - 복잡한 분자 지원
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        
        # 1. RWMol 생성
        editmol = Chem.RWMol(Chem.Mol())
        
        # 2. 원자 추가 (명시적 수소 포함)
        coord_to_idx = {}
        for coord_key, atom_data in self.atoms.items():
            symbol = atom_data.get('main', 'C')
            if not symbol:
                symbol = 'C'
            
            atom = Chem.Atom(symbol)
            
            # 수소 명시화 (RDKit이 인식 가능)
            if symbol == 'H':
                atom.SetExplicitHs(1)
            
            idx = editmol.AddAtom(atom)
            coord_to_idx[coord_key] = idx
        
        # 3. 결합 추가 (웨지/대쉬 정보 포함)
        for (k1, k2), bond_data in self.bonds.items():
            if k1 not in coord_to_idx or k2 not in coord_to_idx:
                continue
            
            idx1 = coord_to_idx[k1]
            idx2 = coord_to_idx[k2]
            
            # 결합 타입 및 입체화학 정보
            if isinstance(bond_data, tuple):
                # Wedge/Dash: (p1, p2, "Wedge"/"Dash")
                _, _, stereo_type = bond_data
                bond_type = Chem.BondType.SINGLE
                
                if stereo_type == "Wedge":
                    stereo = Chem.BondStereo.WEDGE
                elif stereo_type == "Dash":
                    stereo = Chem.BondStereo.WEDGEDASHTAIL
                else:
                    stereo = Chem.BondStereo.STEREONONE
            else:
                # 일반 결합
                bond_type = {
                    1: Chem.BondType.SINGLE,
                    2: Chem.BondType.DOUBLE,
                    3: Chem.BondType.TRIPLE
                }.get(bond_data, Chem.BondType.SINGLE)
                stereo = Chem.BondStereo.STEREONONE
            
            editmol.AddBond(idx1, idx2, bond_type)
            
            # 입체화학 정보 적용
            bond = editmol.GetBondBetweenAtoms(idx1, idx2)
            if bond:
                bond.SetStereo(stereo)
        
        # 4. SMILES 생성
        mol = editmol.GetMol()
        Chem.SanitizeMol(mol)
        Chem.AssignStereochemistry(mol, force=True, cleanIt=True)
        
        smiles = Chem.MolToSmiles(mol)
        
        # 5. 검증 (SMILES → 분자 → SMILES 왕복)
        test_mol = Chem.MolFromSmiles(smiles)
        if test_mol is None:
            raise ValueError(f"Generated SMILES is invalid: {smiles}")
        
        return smiles if smiles else "C"
    
    except Exception as e:
        ErrorHandler.instance().handle_error("SMILES", e, "SMILES 생성")
        return "C"
```

#### 2. SMILES 검증 시스템

```python
# smiles_validator.py (신규)
from rdkit import Chem

class SMILESValidator:
    """SMILES 유효성 검사 및 표준화"""
    
    @staticmethod
    def validate_and_normalize(smiles: str) -> tuple[bool, str, str]:
        """
        Returns:
            (is_valid, normalized_smiles, error_message)
        """
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return False, "", f"Invalid SMILES: {smiles}"
            
            # 표준화
            Chem.SanitizeMol(mol)
            normalized = Chem.MolToSmiles(mol)
            
            return True, normalized, ""
        except Exception as e:
            return False, "", str(e)
```

### 예상 점수 증가: +6점

---

## 🟡 P2: 실시간 동기화 (IUPAC)

### 목표
- 분자 수정 후 0.5초 내 IUPAC 업데이트
- 캐싱 메커니즘 구현
- 점수: +5점 (75 → 80점)

### 구현 계획

#### 1. IUPAC 캐싱 및 증분 업데이트

```python
# iupac_analyzer.py 수정
from collections import OrderedDict

class IUPACAnalyzer:
    """개선된 IUPAC 분석기 (캐싱 및 증분 업데이트)"""
    
    _cache = OrderedDict()  # (smiles, method) -> IUPACName
    _cache_max_size = 100
    
    @staticmethod
    def analyze_cached(mol: Chem.Mol, smiles: str) -> IUPACName:
        """캐시된 분석"""
        key = (smiles, "rdkit")
        
        if key in IUPACAnalyzer._cache:
            return IUPACAnalyzer._cache[key]
        
        # 새 분석
        result = IUPACAnalyzer.analyze(mol)
        
        # 캐시 추가 (크기 제한)
        if len(IUPACAnalyzer._cache) >= IUPACAnalyzer._cache_max_size:
            IUPACAnalyzer._cache.popitem(last=False)  # FIFO 제거
        
        IUPACAnalyzer._cache[key] = result
        return result
```

#### 2. 백그라운드 스레드 최적화

```python
# iupac_analyzer.py 수정
class IUPACAnalyzerThread(QThread):
    """개선된 IUPAC 분석 스레드"""
    
    progress = pyqtSignal(str)
    result = pyqtSignal(IUPACName)
    error = pyqtSignal(str)
    
    def __init__(self, smiles: str, use_cache: bool = True):
        super().__init__()
        self.smiles = smiles
        self.use_cache = use_cache
    
    def run(self):
        """백그라운드에서 IUPAC 분석 실행"""
        try:
            self.progress.emit("IUPAC 분석 시작...")
            
            mol = Chem.MolFromSmiles(self.smiles)
            if mol is None:
                self.error.emit(f"Invalid SMILES: {self.smiles}")
                return
            
            # 캐시 사용
            if self.use_cache:
                result = IUPACAnalyzer.analyze_cached(mol, self.smiles)
            else:
                result = IUPACAnalyzer.analyze(mol)
            
            self.progress.emit(f"완료: {result.iupac_name}")
            self.result.emit(result)
        
        except Exception as e:
            self.error.emit(f"분석 오류: {str(e)}")
```

#### 3. 드로잉 캔버스 통합

```python
# draw.py 수정
def on_molecule_updated(self):
    """분자 수정 시 호출 (0.5초 지연)"""
    
    # 이전 요청 취소
    if hasattr(self, '_iupac_timer') and self._iupac_timer.isActive():
        self._iupac_timer.stop()
    
    # 새 요청 (0.5초 후)
    from PyQt6.QtCore import QTimer
    self._iupac_timer = QTimer()
    self._iupac_timer.setSingleShot(True)
    self._iupac_timer.timeout.connect(self._start_iupac_analysis)
    self._iupac_timer.start(500)  # 0.5초 지연
    
    if self.phase_manager:
        try:
            self.phase_manager.on_molecule_updated(
                self.atoms, 
                self.bonds, 
                self.analysis_results
            )
        except Exception as e:
            ErrorHandler.instance().handle_error("Integration", e)

def _start_iupac_analysis(self):
    """IUPAC 분석 시작"""
    smiles = self.get_smiles()
    
    # 이전 스레드 종료
    if hasattr(self, '_iupac_thread') and self._iupac_thread.isRunning():
        self._iupac_thread.quit()
        self._iupac_thread.wait()
    
    # 새 스레드 시작
    from iupac_analyzer import IUPACAnalyzerThread
    self._iupac_thread = IUPACAnalyzerThread(smiles, use_cache=True)
    self._iupac_thread.result.connect(self._on_iupac_result)
    self._iupac_thread.start()

def _on_iupac_result(self, iupac_name):
    """IUPAC 결과 처리"""
    self.iupac_result = iupac_name
    self.update()  # 캔버스 갱신
```

### 예상 점수 증가: +5점

---

## 🟡 P2: 3D 좌표 최적화

### 목표
- RDKit/MMFF94로 3D 기하 최적화
- 입체 구조 정확도 향상
- 점수: +4점 (72 → 76점)

### 구현 계획

```python
# molecule_3d_optimizer.py (신규)
from rdkit import Chem
from rdkit.Chem import AllChem
import numpy as np

class Molecule3DOptimizer:
    """3D 분자 기하 최적화"""
    
    @staticmethod
    def optimize_3d(smiles: str, num_conformers: int = 5) -> Chem.Mol:
        """
        SMILES → 최적화된 3D 구조
        
        Returns:
            최저 에너지 입체이성질체가 포함된 Chem.Mol
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        
        # 수소 추가
        mol = Chem.AddHs(mol)
        
        # 여러 conformer 생성
        AllChem.EmbedMolecule(mol, numConfs=num_conformers, 
                              randomSeed=42, useRandomCoords=False)
        
        if mol.GetNumConformers() == 0:
            return None
        
        # MMFF94 포스필드로 최적화
        props = AllChem.MMFFGetMoleculeProperties(mol)
        if props is None:
            # MMFF94 불가능 시 UFF 사용
            props = AllChem.UFFGetMoleculeProperties(mol)
        
        # 모든 conformer 최적화
        energies = []
        for conf_id in range(mol.GetNumConformers()):
            ff = AllChem.MMFFGetMoleculeForceField(mol, props, confId=conf_id)
            if ff is None:
                ff = AllChem.UFFGetMoleculeForceField(mol, confId=conf_id)
            
            ff.Initialize()
            ff.Minimize(maxIts=1000)
            energies.append(ff.CalcEnergy())
        
        # 최저 에너지 conformer 선택
        min_idx = np.argmin(energies)
        best_conf = mol.GetConformer(min_idx)
        
        # 수소 제거 (선택적)
        mol = Chem.RemoveHs(mol)
        
        return mol, best_conf.GetPositions()
```

### 예상 점수 증가: +4점

---

## 🟢 P3: OpenGL 안정성 개선

### 목표
- OpenGL 폴백 메커니즘 강화
- 호환성 테스트
- 점수: +3점

### 구현 계획

```python
# popup_3d.py 수정
class Molecule3DPopup:
    def __init__(self, mol_data):
        super().__init__()
        
        # OpenGL 지원 여부 확인
        fmt = QSurfaceFormat()
        fmt.setVersion(2, 0)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        
        try:
            self.gl_widget = GLMoleculeViewer(mol_data)
            self.gl_widget.setFormat(fmt)
            self.use_gl = True
        except Exception as e:
            # OpenGL 불가능 시 폴백
            logging.warning(f"OpenGL 초기화 실패: {e}. 소프트웨어 렌더링 사용")
            self.gl_widget = FallbackMoleculeViewer(mol_data)
            self.use_gl = False
```

---

## 📊 최종 목표 (Final Score)

| Phase | 현재 | P0 | P1 | P2 | P3 | 최종 |
|-------|------|----|----|----|----|------|
| Phase A | 78 | +2 | +4 | - | - | **84** |
| Phase B | 73 | +2 | +7 | - | - | **82** |
| Phase C | 72 | +1 | - | +4 | +3 | **80** |
| Phase D | 75 | +1 | - | +5 | - | **81** |
| Integration | 75 | +2 | - | - | - | **77** |
| **종합** | **75.2** | **+8** | **+11** | **+9** | **+3** | **≈86** |

---

## 🗓️ 구현 일정

```
Week 1 (P0): 오류 처리 시스템
- ErrorHandler 클래스 구현
- 각 Phase 에러 처리 통합
- 로깅 시스템 구축
- ✓ 목표: +8점

Week 2-3 (P1): 성능 최적화
- Radial gradient 개선
- 캐싱 메커니즘
- SMILES 정확도 개선
- ✓ 목표: +13점

Week 3-4 (P2): 실시간 동기화 & 3D 최적화
- IUPAC 캐싱
- 3D 구조 최적화 (RDKit)
- ✓ 목표: +9점

Week 4 (P3): 안정성
- OpenGL 폴백
- 호환성 테스트
- ✓ 목표: +3점

Final: 테스트 & 검증
- 통합 테스트
- 성능 벤치마크
- 버그 수정
```

---

## 🎯 성공 지표 (Success Metrics)

- ✅ 모든 오류가 사용자에게 명확하게 표시
- ✅ ESP 렌더링이 60 FPS 이상
- ✅ 분자 수정 후 0.5초 내 IUPAC 업데이트
- ✅ 200+ 원자 분자 지원
- ✅ OpenGL 없는 시스템에서도 작동
- ✅ 종합 평가 점수 ≥ 86점

