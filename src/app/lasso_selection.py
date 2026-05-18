# lasso_selection.py — LassoSelectionRenderer (Theory layer 전용)
# layer_logic.py에서 분리됨 (2026-02-28)
# draw.py에서 Lasso Select가 주석처리되어 현재 미사용
# 향후 재활성화 시 이 파일을 import하여 사용

from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtCore import Qt, QPointF


class LassoSelectionRenderer:
    """
    자유형 선택(Lasso) 도구 - Theory 레이어용
    - 경로 저장 및 교차 검사로 분자 선택
    - 선택된 원자/결합 하이라이트 처리
    - 3D 팝업 트리거

    기술 제약:
    - 모든 좌표: round(coord, 2)
    - Theory 레이어에서만 작동
    """

    def __init__(self):
        self.lasso_path = QPainterPath()
        self.points = []
        self.selected_atoms = set()
        self.selected_bonds = set()
        self.is_drawing = False

    def start_lasso(self, point):
        """라소 드로잉 시작"""
        self.lasso_path = QPainterPath()
        self.points = []
        self.selected_atoms.clear()
        self.selected_bonds.clear()
        self.is_drawing = True

        self.lasso_path.moveTo(point)
        self.points.append((round(point.x(), 2), round(point.y(), 2)))

    def add_point_to_lasso(self, point):
        """라소 경로에 점 추가"""
        if not self.is_drawing:
            return

        point_rounded = (round(point.x(), 2), round(point.y(), 2))
        self.lasso_path.lineTo(point)
        self.points.append(point_rounded)

    def end_lasso(self, point):
        """라소 드로잉 종료 및 선택 범위 결정"""
        if not self.is_drawing:
            return False

        self.lasso_path.closeSubpath()
        self.is_drawing = False

        if len(self.points) < 3:
            self.lasso_path = QPainterPath()
            self.points = []
            return False

        return True

    def is_point_inside_lasso(self, point):
        """
        점이 라소 영역 내부에 있는지 확인 (Ray casting 알고리즘)
        좌표는 rounded
        """
        if len(self.points) < 3:
            return False

        px, py = round(point.x(), 2), round(point.y(), 2)

        inside = False
        p1x, p1y = self.points[0]

        for i in range(1, len(self.points) + 1):
            p2x, p2y = self.points[i % len(self.points)]

            if py > min(p1y, p2y):
                if py <= max(p1y, p2y):
                    if px <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (py - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or px <= xinters:
                            inside = not inside

            p1x, p1y = p2x, p2y

        return inside

    def select_molecules_in_lasso(self, atoms, bonds, analysis, t_map):
        """
        라소 내부의 분자 선택

        Args:
            atoms: 원자 데이터 {pos_key: {...}}
            bonds: 결합 데이터 {(k1, k2): order}
            analysis: 분석 데이터
            t_map: 이론적 좌표 맵

        Returns:
            (selected_atoms, selected_bonds) 튜플
        """
        self.selected_atoms.clear()
        self.selected_bonds.clear()

        for pt_key in atoms.keys():
            # Rule N: isinstance guard for t_map
            if not isinstance(t_map, dict): t_map = {}
            center = t_map.get(pt_key, QPointF(*pt_key))
            if self.is_point_inside_lasso(center):
                self.selected_atoms.add(pt_key)

        for (k1, k2) in bonds.keys():
            if k1 in self.selected_atoms and k2 in self.selected_atoms:
                self.selected_bonds.add((k1, k2))

        return (self.selected_atoms, self.selected_bonds)

    def render_lasso_overlay(self, painter, alpha=0.3):
        """라소 시각화 및 선택 영역 표시"""
        if len(self.points) < 2:
            return

        painter.save()

        painter.setPen(QPen(QColor(0, 100, 255), 2.0, Qt.PenStyle.DashLine))
        painter.drawPath(self.lasso_path)

        painter.setOpacity(alpha)
        painter.fillPath(self.lasso_path, QColor(0, 100, 255, 100))

        painter.setOpacity(1.0)
        painter.setBrush(QColor(0, 150, 255))
        painter.setPen(Qt.PenStyle.NoPen)
        for pt in self.points:
            painter.drawEllipse(QPointF(pt[0], pt[1]), 3, 3)

        painter.restore()

    def render_selection_highlight(self, painter, selected_atoms,
                                   selected_bonds, t_map, atoms, bonds):
        """선택된 원자와 결합 하이라이트 처리"""
        painter.save()

        painter.setPen(QPen(QColor(255, 200, 0), 4.0))
        for (k1, k2) in selected_bonds:
            # Rule N: isinstance guard for t_map
            if not isinstance(t_map, dict): t_map = {}
            p1 = t_map.get(k1, QPointF(*k1))
            p2 = t_map.get(k2, QPointF(*k2))
            painter.drawLine(p1, p2)

        painter.setPen(QPen(QColor(255, 100, 0), 2.0))
        painter.setBrush(QColor(255, 200, 0, 80))
        for pt_key in selected_atoms:
            center = t_map.get(pt_key, QPointF(*pt_key))
            painter.drawEllipse(center, 18, 18)

        painter.restore()

    def get_selected_smiles(self, selected_atoms, atoms, bonds):
        """
        선택된 분자 SMILES 문자열 생성
        (ORCA 계산 및 비교에 사용)

        Returns:
            SMILES 문자열 또는 None
        """
        if not selected_atoms:
            return None

        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem

            _base_mol = Chem.MolFromSmiles("C")
            if _base_mol is None:
                logger.warning("Failed to parse base SMILES 'C' for lasso selection")
                return None
            emol = Chem.EditableMol(_base_mol)

            atom_list = list(selected_atoms)
            if atom_list:
                # Rule N: isinstance guard for atoms
                if not isinstance(atoms, dict): atoms = {}
                atoms_list = [(pt, atoms.get(pt, {}).get("main", "C"))
                              for pt in atom_list]

                smiles = None
                # TODO: RDKit을 사용한 정확한 SMILES 생성
                return smiles
        except Exception:
            return None

    def clear_selection(self):
        """선택 제거"""
        self.lasso_path = QPainterPath()
        self.points = []
        self.selected_atoms.clear()
        self.selected_bonds.clear()
        self.is_drawing = False
