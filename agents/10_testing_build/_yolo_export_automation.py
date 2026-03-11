
import sys
import os
import math
import shutil
import logging
from pathlib import Path
from datetime import datetime

# =========================================================================================
# 1. 환경 설정 및 의존성 임포트
# =========================================================================================

# 현재 스크립트 위치 기준 프로젝트 루트 설정
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = _SCRIPT_DIR / "integrated"

# integrated 폴더를 sys.path에 추가하여 모듈 임포트 가능하게 함
sys.path.insert(0, str(_PROJECT_ROOT))

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="[YOLO] %(message)s")
logger = logging.getLogger("YOLO_EXPORT")

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import QPointF, QTimer, QSize
    from PyQt6.QtGui import QPainter, QImage
except ImportError:
    logger.error("PyQt6 is required. Please install it: pip install PyQt6")
    sys.exit(1)

# 프로젝트 모듈 임포트
try:
    from main_window import MainWindow
    from spectrum_pdf_exporter import SpectrumPDFExporter, SpectrumMetadata, SpectrumData, SpectrumPeakData
    # 필요한 경우 추가 모듈 임포트
except ImportError as e:
    logger.error(f"Failed to import project modules: {e}")
    sys.exit(1)

# =========================================================================================
# 2. Mock 좌표 데이터 (RDKit 없이 구조 생성)
# =========================================================================================

def get_benzene_coords(center_x=400, center_y=300, scale=40):
    """벤젠 고리 좌표 생성"""
    coords = {}
    for i in range(6):
        angle = math.radians(i * 60 - 30)  # -30도로 시작하여 뾰족한 부분이 위로 가게
        x = center_x + scale * math.cos(angle)
        y = center_y + scale * math.sin(angle)
        coords[i] = (round(x, 2), round(y, 2))
    return coords

def create_mock_molecule(name):
    """이름에 따라 분자 좌표와 결합 정보 반환"""
    atoms = {}
    bonds = {}
    
    # 기본 벤젠 고리 (중심 (400, 300))
    base_coords = get_benzene_coords()
    
    if name == "Benzene":
        for i, pos in base_coords.items():
            atoms[pos] = {"main": "C", "attach": {}}
        # 이중 결합 (Kekule)
        bonds[(base_coords[0], base_coords[1])] = 2
        bonds[(base_coords[1], base_coords[2])] = 1
        bonds[(base_coords[2], base_coords[3])] = 2
        bonds[(base_coords[3], base_coords[4])] = 1
        bonds[(base_coords[4], base_coords[5])] = 2
        bonds[(base_coords[5], base_coords[0])] = 1
        
    elif name == "Nitrobenzene":
        # 벤젠 + NO2
        for i, pos in base_coords.items():
            atoms[pos] = {"main": "C", "attach": {}}
        
        # NO2 치환기 (0번 탄소 위)
        n_pos = (base_coords[0][0], base_coords[0][1] - 40)
        o1_pos = (n_pos[0] - 20, n_pos[1] - 20)
        o2_pos = (n_pos[0] + 20, n_pos[1] - 20)
        
        atoms[n_pos] = {"main": "N", "attach": {}, "charge": "+"}
        atoms[o1_pos] = {"main": "O", "attach": {}, "charge": "-"}
        atoms[o2_pos] = {"main": "O", "attach": {}}
        
        # 결합
        bonds[(base_coords[0], base_coords[1])] = 2
        bonds[(base_coords[1], base_coords[2])] = 1
        bonds[(base_coords[2], base_coords[3])] = 2
        bonds[(base_coords[3], base_coords[4])] = 1
        bonds[(base_coords[4], base_coords[5])] = 2
        bonds[(base_coords[5], base_coords[0])] = 1
        
        bonds[(base_coords[0], n_pos)] = 1
        bonds[(n_pos, o1_pos)] = 1
        bonds[(n_pos, o2_pos)] = 2

    # 다른 분자들은 간단히 C-C 체인으로 대체 (시간/복잡도 절약)
    else:
        # Cis-2-Butene, Norbornane 등... 간단한 체인
        start_x, start_y = 300, 300
        prev_pos = None
        for i in range(4):
            x = start_x + i * 40
            y = start_y
            pos = (float(x), float(y))
            atoms[pos] = {"main": "C", "attach": {}}
            if prev_pos:
                bonds[(prev_pos, pos)] = 1
            prev_pos = pos
            
    return atoms, bonds

# =========================================================================================
# 3. 자동화 로직
# =========================================================================================

class YoloAutomation:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = MainWindow()
        self.window.show() # 렌더링을 위해 필요
        
        # 저장 경로 설정
        self.output_dir = _SCRIPT_DIR / "yolo_outputs"
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.molecules = [
            "Benzene", "Nitrobenzene", "Cis-2-Butene", "Norbornane", 
            "Cubane", "Ferrocene", "Glyceraldehyde", "Thiophene", 
            "Tropylium Cation", "Ospirane"
        ]
        
    def run(self):
        logger.info("Starting YOLO Automation...")
        
        success_count = 0
        
        for mol_name in self.molecules:
            try:
                logger.info(f"Processing: {mol_name}")
                
                # 1. 캔버스 초기화
                self.window.cv.atoms = {}
                self.window.cv.bonds = {}
                self.window.cv.strokes = []
                self.window.cv.arrows = []
                self.window.cv.text_boxes = []
                self.window.cv.analysis_results = None # 결과 초기화
                
                # 2. 분자 그리기 (Mock 데이터 주입)
                atoms, bonds = create_mock_molecule(mol_name)
                # 좌표 키를 QPointF가 아닌 튜플로 변환 (이미 튜플임)
                self.window.cv.atoms = atoms
                self.window.cv.bonds = bonds
                
                # 3. 뷰 업데이트 및 렌더링 대기
                self.window.cv.view_state = "Drawing"
                self.window.cv.update()
                self.process_events()
                
                # 4. 분석 실행 (가짜 분석 결과 주입 가능하면 주입)
                # self.window.cv.analyzer.analyze() 호출이 실제로는 mouseReleaseEvent에서 일어남
                # 여기서는 강제로 analyze 호출
                if hasattr(self.window.cv, 'analyzer'):
                    self.window.cv.analysis_results = self.window.cv.analyzer.analyze(atoms, bonds)
                
                # 5. PDF 내보내기 (구조 & 스펙트럼)
                self.export_molecule_pdf(mol_name)
                
                success_count += 1
                logger.info(f"Successfully processed {mol_name}")
                
            except Exception as e:
                logger.error(f"Failed to process {mol_name}: {e}")
                import traceback
                traceback.print_exc()

        logger.info(f"Completed: {success_count}/{len(self.molecules)}")
        self.window.close()
        
    def process_events(self):
        """UI 이벤트 처리하여 렌더링 갱신"""
        self.app.processEvents()
        QTimer.singleShot(100, lambda: None) # 잠시 대기
        self.app.processEvents()

    def export_molecule_pdf(self, mol_name):
        """구조 및 스펙트럼 PDF 생성"""
        
        # 메타데이터 생성
        metadata = SpectrumMetadata(
            molecule_name=mol_name,
            molecular_formula="C6H6" if mol_name == "Benzene" else "Unknown",
            smiles="c1ccccc1" if mol_name == "Benzene" else "C",
            calculation_method="B3LYP/6-31G(d) [YOLO]",
            final_energy=-232.123456
        )
        
        exporter = SpectrumPDFExporter(metadata)
        
        # 1. Lewis 구조 캡처
        self.window.switch_view("Lewis")
        self.process_events()
        lewis_img_path = self.output_dir / f"{mol_name}_Lewis.png"
        self.capture_canvas(lewis_img_path)
        
        exporter.add_spectrum("Lewis Structure", SpectrumData(
            spectrum_type="Lewis Structure",
            peaks=[],
            image_path=str(lewis_img_path)
        ))
        
        # 2. Theory 구조 캡처
        self.window.switch_view("Theory")
        self.process_events()
        theory_img_path = self.output_dir / f"{mol_name}_Theory.png"
        self.capture_canvas(theory_img_path)
        
        exporter.add_spectrum("Theory Structure", SpectrumData(
            spectrum_type="Theory Structure",
            peaks=[],
            image_path=str(theory_img_path)
        ))
        
        # 3. 스펙트럼 데이터 (Mock)
        # IR Spectrum
        ir_peaks = [
            SpectrumPeakData(3050, 20, "C-H stretch"),
            SpectrumPeakData(1600, 80, "C=C stretch"),
            SpectrumPeakData(1450, 40, "C-C stretch"),
            SpectrumPeakData(750, 90, "C-H bend")
        ]
        exporter.add_spectrum("IR Spectrum", SpectrumData(
            spectrum_type="IR Spectrum",
            peaks=ir_peaks,
            image_path=None # 그래프 이미지가 없으면 테이블만 출력됨
        ))
        
        # NMR Spectrum
        nmr_peaks = [
            SpectrumPeakData(7.26, 100, "Benzene H", unit="ppm"),
        ]
        exporter.add_spectrum("1H NMR", SpectrumData(
            spectrum_type="1H NMR",
            peaks=nmr_peaks,
            image_path=None
        ))

        # PDF 저장
        pdf_path = self.output_dir / f"{mol_name}_Report.pdf"
        exporter.export_to_pdf(str(pdf_path))
        logger.info(f"Exported PDF: {pdf_path}")
        
        # 원래 뷰로 복귀
        self.window.switch_view("Drawing")

    def capture_canvas(self, path):
        """현재 캔버스 상태를 이미지로 저장"""
        # grab()은 위젯 전체를 캡처
        pixmap = self.window.cv.grab()
        pixmap.save(str(path))

if __name__ == "__main__":
    if not os.path.exists("integrated"):
        logger.error("Error: 'integrated' directory not found. Run this script from the parent directory.")
        sys.exit(1)
        
    automation = YoloAutomation()
    automation.run()
