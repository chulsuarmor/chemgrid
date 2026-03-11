from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QPainterPath, QFontMetrics, QBrush 
from PyQt6.QtCore import Qt, QPointF, QRectF
import math
from rdkit import Chem # [추가] 이론적 구조의 결합 타입 판별을 위해 필수

class LewisRenderer:
    @staticmethod
    def get_bond_gap(pt_key, atoms_data):
        """
        결합선이 원소 기호로부터 얼마나 떨어져야 하는지 계산
        수소처럼 명확한 간격을 확보
        """
        if pt_key not in atoms_data:
            return 0
        
        atom = atoms_data[pt_key]
        symbol = atom.get("main", "C")
        
        # 빈 문자열("")인 경우 "C"로 간주 (루이스 구조에서 탄소 표시)
        if not symbol or symbol.strip() == "":
            symbol = "C"
        
        # 원소 기호가 있는 경우 gap 계산
        if symbol:
            font = QFont("Arial", 14, QFont.Weight.Bold)
            fm = QFontMetrics(font)
            text_width = fm.horizontalAdvance(symbol)
            text_height = fm.height()
            
            # 텍스트 크기의 절반 + 넉넉한 여백 (수소처럼 명확한 간격)
            base_gap = max(text_width, text_height) / 2
            return base_gap + 8  # 여백을 더 크게
        
        return 0
    
    @staticmethod
    def render(painter, atoms, bonds, analysis, selected_atoms=None, selected_bonds=None):
        """
        루이스 구조 렌더러 v2.0
        - 터미널 비탄소 원소 우선 표시
        - Z-order: 결합 → 기호
        - VSEPR 기반 정확한 배치
        - 선택 표시: 파란색 하이라이트
        """
        if not analysis: return
        print("\n[LEWIS RENDERER v2.0 ACTIVATED]")
        t_map = analysis.get("theory_data", {}).get("map", {})
        adj = analysis.get("adj", {})
        atoms_data = analysis.get("atoms", {})
        
        # [신규] 선택 표시를 위한 기본값 설정
        if selected_atoms is None:
            selected_atoms = set()
        if selected_bonds is None:
            selected_bonds = set()
        
        painter.save()
        
        # === STAGE 1: 결합선 렌더링 (간격 적용) ===
        for (k1, k2), v in analysis.get("bonds", {}).items():
            # [신규] 선택 여부에 따라 색상 변경
            is_selected = (k1, k2) in selected_bonds or (k2, k1) in selected_bonds
            line_color = Qt.GlobalColor.blue if is_selected else Qt.GlobalColor.black
            line_width = 2.8 if is_selected else 2.2
            painter.setPen(QPen(line_color, line_width))
            # 이론적 좌표 사용
            p1_orig = t_map.get(k1, QPointF(*k1))
            p2_orig = t_map.get(k2, QPointF(*k2))
            
            # 방향 벡터 계산
            vec = p2_orig - p1_orig
            length = math.hypot(vec.x(), vec.y())
            if length == 0:
                continue
            
            unit = vec / length
            
            # 각 원소에서의 간격 계산
            gap1 = LewisRenderer.get_bond_gap(k1, atoms_data)
            gap2 = LewisRenderer.get_bond_gap(k2, atoms_data)
            
            # 간격을 적용한 시작점과 끝점
            p1 = p1_orig + unit * gap1
            p2 = p2_orig - unit * gap2
            
            # 결합 차수 판별
            order = v if isinstance(v, int) else (2 if "DOUBLE" in str(v) else 1)

            # [TASK 1] 지능형 Offset: C=C만 짧은 선 적용
            elem1 = atoms_data.get(k1, {}).get("main", "C")
            elem2 = atoms_data.get(k2, {}).get("main", "C")
            is_cc_bond = (elem1 in ["C", ""] and elem2 in ["C", ""])

            # 단일 결합
            painter.drawLine(p1, p2)

            # 다중 결합
            if order >= 2:
                perp = QPointF(-vec.y(), vec.x()) / length * 4.5

                if is_cc_bond:
                    # C=C: 한쪽 선을 짧게
                    p1_short = p1_orig + unit * (gap1 + 3)
                    p2_short = p2_orig - unit * (gap2 + 3)
                    painter.drawLine(p1_short + perp, p2_short + perp)
                else:
                    # N=O, C=N: 평행선 (간격 적용)
                    p1_offset = p1_orig + unit * gap1
                    p2_offset = p2_orig - unit * gap2
                    painter.drawLine(p1_offset + perp, p2_offset + perp)

                if order == 3:
                    if is_cc_bond:
                        p1_short = p1_orig + unit * (gap1 + 3)
                        p2_short = p2_orig - unit * (gap2 + 3)
                        painter.drawLine(p1_short - perp, p2_short - perp)
                    else:
                        p1_offset = p1_orig + unit * gap1
                        p2_offset = p2_orig - unit * gap2
                        painter.drawLine(p1_offset - perp, p2_offset - perp)
        
        print(" -> Bonds rendered with gap support")
        
        # === STAGE 2: 원자 기호 출력 (테두리 없이, 선택 표시 포함) ===
        for pt_key, atom_data in analysis["atoms"].items():
            symbol = atom_data.get("main", "C")
            if not symbol or symbol.strip() == "":
                symbol = "C"
            center = t_map.get(pt_key, QPointF(*pt_key))
            
            # [신규] 선택 여부에 따라 색상 변경
            is_selected = pt_key in selected_atoms
            atom_color = Qt.GlobalColor.blue if is_selected else Qt.GlobalColor.black
            
            # 기호 그리기 (선택 시 파란색, 미선택 시 검은색)
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            painter.setPen(atom_color)
            fm = QFontMetrics(painter.font())
            text_w = fm.horizontalAdvance(symbol)
            text_h = fm.height()
            
            text_rect = QRectF(center.x() - text_w/2, center.y() - text_h/2, text_w, text_h)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, symbol)
            
            # [신규] 선택된 원자에 파란색 테두리 추가
            if is_selected:
                painter.setPen(QPen(Qt.GlobalColor.blue, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(center.x() - text_w/2 - 3, center.y() - text_h/2 - 2, text_w + 6, text_h + 4))
        
        print(" -> Atom symbols rendered")
        
        # === STAGE 3: 수소 및 비공유전자쌍 렌더링 ===
        for pt_key, atom_data in analysis["atoms"].items():
            # [TASK 2] 수소 보정: 전하가 있는 원자는 수소 생성 차단
            formal_charge = atom_data.get("formal_charge", 0)
            has_charge = formal_charge != 0

            # 전하가 있는 산소/질소 등에는 수소를 추가하지 않음
            if "h_count" in atom_data and not has_charge:
                # [Step 3 수정] 이론적 좌표 전달 (정다각형 형태에 맞춘 H/LP 배치)
                LewisRenderer.draw_vsepr_extensions(painter, pt_key, atom_data, analysis, t_map)
        
        painter.restore()
        print("[LEWIS RENDERER COMPLETE]\n")

    @staticmethod
    def draw_lone_pair(painter, center, direction):
        """비공유 전자쌍(..) 렌더링 - ChemDraw 스타일"""
        painter.save()
        
        # 비공유전자쌍 위치 (원자에서 약간 떨어진 곳)
        pos = center + direction * 22
        
        # 수직 방향 벡터 (두 점을 좌우로 배치)
        perp = QPointF(-direction.y(), direction.x()) * 3.5
        
        # 두 개의 점 (검은색, 약간 큼직하게)
        painter.setBrush(Qt.GlobalColor.black)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(pos + perp, 2.5, 2.5)
        painter.drawEllipse(pos - perp, 2.5, 2.5)
        
        painter.restore()

    @staticmethod
    def draw_vsepr_extensions(painter, pos_tuple, data, analysis, t_map):
        """
        VSEPR 기반 수소 및 비공유전자쌍 배치 v2.0
        - 정확한 사면체/평면 기하 구조 반영
        - 기존 결합 방향을 고려한 최적 배치
        """
        # [Step 3 수정] 이론적 좌표 사용 (t_map이 있으면 우선 적용)
        center = t_map.get(pos_tuple, QPointF(*pos_tuple))
        adj_info = analysis.get("adj", {}).get(pos_tuple, [])
        
        # [STEP 1] 기존 결합 방향 벡터 수집
        existing_vectors = []
        for neighbor_pos, _ in adj_info:
            # [Step 3 수정] 이웃 원자도 이론적 좌표 사용
            neighbor_center = t_map.get(neighbor_pos, QPointF(*neighbor_pos))
            vec = neighbor_center - center
            mag = math.hypot(vec.x(), vec.y())
            if mag > 0:
                normalized = vec / mag
                angle = math.degrees(math.atan2(normalized.y(), normalized.x()))
                existing_vectors.append((normalized, angle))
        
        # [STEP 2] 수소와 비공유전자쌍 개수
        h_count = data.get("h_count", 0)
        lp_count = data.get("lp_count", 0)
        total_extensions = h_count + lp_count
        
        if total_extensions == 0:
            return
        
        # [STEP 3] VSEPR 기하 구조에 따른 각도 배분
        total_groups = len(existing_vectors) + total_extensions
        
        # 기하 구조별 표준 각도
        if total_groups == 2:
            ideal_angle_step = 180  # 선형
        elif total_groups == 3:
            ideal_angle_step = 120  # 평면 삼각형
        elif total_groups == 4:
            ideal_angle_step = 109.5  # 사면체 (2D 근사: 109.5)
        else:
            ideal_angle_step = 90  # 기타
        
        # [STEP 4] 빈 공간 찾기
        occupied_angles = [angle for _, angle in existing_vectors]
        
        # 기존 결합들의 평균 반대 방향을 시작점으로
        if occupied_angles:
            avg_x = sum(math.cos(math.radians(a)) for a in occupied_angles) / len(occupied_angles)
            avg_y = sum(math.sin(math.radians(a)) for a in occupied_angles) / len(occupied_angles)
            base_angle = math.degrees(math.atan2(-avg_y, -avg_x))
        else:
            base_angle = -90  # 위쪽
        
        # [STEP 5] 확장 요소들 배치
        for i in range(total_extensions):
            # 각도 분산 (중심에서 좌우로 펼침)
            offset = (i - (total_extensions - 1) / 2) * (ideal_angle_step / 2)
            target_angle = base_angle + offset
            rad = math.radians(target_angle)
            direction = QPointF(math.cos(rad), math.sin(rad))
            
            # 수소 우선 배치, 이후 비공유전자쌍
            if i < h_count:
                LewisRenderer.draw_h_bond(painter, center, direction)
            else:
                LewisRenderer.draw_lone_pair(painter, center, direction)

    @staticmethod
    def draw_h_bond(painter, center, direction):
        """수소 결합선과 H 기호 렌더링 (ChemDraw 스타일)"""
        # 결합선 시작/끝점
        start = center + direction * 18
        end = center + direction * 38
        
        # 결합선 그리기
        painter.setPen(QPen(Qt.GlobalColor.black, 2.0))
        painter.drawLine(start, end)
        
        # 수소 기호 위치
        h_pos = end + direction * 10
        
        # H 기호 (테두리 없이)
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.setPen(Qt.GlobalColor.black)
        fm = QFontMetrics(painter.font())
        text_w = fm.horizontalAdvance("H")
        text_h = fm.height()
        
        text_rect = QRectF(h_pos.x() - text_w/2, h_pos.y() - text_h/2, text_w, text_h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "H")

# [해결] 불필요한 중복 메서드와 가짜 TheoryRenderer(Line 95-141)를 삭제했습니다.
# 아래의 실제 MMFF94 기반 TheoryRenderer가 활성화됩니다.

class TheoryRenderer:
    @staticmethod
    def get_bond_gap(pt_key, atoms_data):
        """
        결합선이 원소 기호로부터 얼마나 떨어져야 하는지 계산
        Theory 레이어에서는 비탄소 원소만 표시
        """
        if pt_key not in atoms_data:
            return 0
        
        atom = atoms_data[pt_key]
        symbol = atom.get("main", "C")
        
        # 원소 기호가 있고 C가 아닌 경우 (Theory는 비탄소만 표시)
        if symbol and symbol.strip() and symbol != "C":
            font = QFont("Arial", 14, QFont.Weight.Bold)
            fm = QFontMetrics(font)
            text_width = fm.horizontalAdvance(symbol)
            text_height = fm.height()
            
            # 텍스트 크기의 절반 + 넉넉한 여백 (수소처럼 명확한 간격)
            base_gap = max(text_width, text_height) / 2
            return base_gap + 8  # 여백을 더 크게
        
        return 0
    
    @staticmethod
    def render(painter, atoms, bonds, analysis, selected_atoms=None, selected_bonds=None):
        """
        [Step 4 개선] 이론적 구조 레이어: MMFF94 최적 좌표 + 원소 표기 + 입체 표현
        - 선택 표시: 파란색 하이라이트
        """
        t_data = analysis.get("theory_data")
        if not t_data: return

        painter.save()
        painter.setOpacity(1.0)
        
        coords = t_data["coords"]
        t_map = t_data.get("map", {})
        atoms_data = analysis.get("atoms", {})
        
        # [신규] 선택 표시를 위한 기본값 설정
        if selected_atoms is None:
            selected_atoms = set()
        if selected_bonds is None:
            selected_bonds = set()
        
        # === STAGE 1: 결합선 렌더링 (웨지/대쉬 포함, 간격 적용) ===
        for (k1, k2), v in bonds.items():
            # [신규] 선택 여부에 따라 색상 변경
            is_selected = (k1, k2) in selected_bonds or (k2, k1) in selected_bonds
            line_color = Qt.GlobalColor.blue if is_selected else Qt.GlobalColor.black
            # [TASK 1] 선 두께 정규화: Drawing 레이어와 동일하게 2.2
            line_width = 2.8 if is_selected else 2.2
            painter.setPen(QPen(line_color, line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            # 이론적 좌표 사용
            p1_orig = t_map.get(k1, QPointF(*k1))
            p2_orig = t_map.get(k2, QPointF(*k2))
            
            # 방향 벡터 계산
            vec = p2_orig - p1_orig
            length = math.hypot(vec.x(), vec.y())
            if length == 0:
                continue
            
            unit = vec / length
            
            # 각 원소에서의 간격 계산
            gap1 = TheoryRenderer.get_bond_gap(k1, atoms_data)
            gap2 = TheoryRenderer.get_bond_gap(k2, atoms_data)
            
            # 간격을 적용한 시작점과 끝점
            p1 = p1_orig + unit * gap1
            p2 = p2_orig - unit * gap2
            
            # 결합 타입 판별
            if isinstance(v, tuple) and len(v) >= 3:
                # 웨지/대쉬 입체 결합
                bond_mode = v[2]
                if bond_mode == "Wedge":
                    # 웨지 (채워진 삼각형)
                    perp = QPointF(-vec.y(), vec.x()) / length * 5
                    painter.setBrush(painter.pen().color())
                    from PyQt6.QtGui import QPolygonF
                    poly = QPolygonF([p1, p2 + perp, p2 - perp])
                    painter.drawPolygon(poly)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                elif bond_mode == "Dash":
                    # 대쉬 (계단식 바코드)
                    perp = QPointF(-vec.y(), vec.x()) / length
                    for i in range(8):
                        f = i / 7.0
                        w = i * 0.8
                        ps = p1 + (p2 - p1) * f
                        painter.drawLine(ps + perp * w, ps - perp * w)
                else:
                    painter.drawLine(p1, p2)
            else:
                # 일반 결합
                order = v if isinstance(v, int) else 1

                # [TASK 1] 지능형 Offset: C=C만 짧은 선 적용
                elem1 = atoms_data.get(k1, {}).get("main", "C")
                elem2 = atoms_data.get(k2, {}).get("main", "C")
                is_cc_bond = (elem1 in ["C", ""] and elem2 in ["C", ""])

                painter.drawLine(p1, p2)

                # 다중 결합
                if order >= 2:
                    perp = QPointF(-vec.y(), vec.x()) / length * 4.5

                    if is_cc_bond:
                        # C=C: 한쪽 선을 짧게
                        p1_short = p1_orig + unit * (gap1 + 3)
                        p2_short = p2_orig - unit * (gap2 + 3)
                        painter.drawLine(p1_short + perp, p2_short + perp)
                    else:
                        # N=O, C=N: 평행선 (간격 적용)
                        painter.drawLine(p1 + perp, p2 + perp)

                    if order == 3:
                        if is_cc_bond:
                            p1_short = p1_orig + unit * (gap1 + 3)
                            p2_short = p2_orig - unit * (gap2 + 3)
                            painter.drawLine(p1_short - perp, p2_short - perp)
                        else:
                            painter.drawLine(p1 - perp, p2 - perp)
        
        # === STAGE 2: 원소 기호 렌더링 (비탄소만, 테두리 없이, 선택 표시 포함) ===
        for pt_key, atom_data in analysis.get("atoms", {}).items():
            symbol = atom_data.get("main", "C")
            if not symbol or symbol.strip() == "" or symbol == "C":
                continue  # 탄소는 생략
            
            center = t_map.get(pt_key, QPointF(*pt_key))
            
            # [신규] 선택 여부에 따라 색상 변경
            is_selected = pt_key in selected_atoms
            atom_color = Qt.GlobalColor.blue if is_selected else Qt.GlobalColor.black
            
            # 기호 그리기 (선택 시 파란색, 미선택 시 검은색)
            painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            painter.setPen(atom_color)
            fm = QFontMetrics(painter.font())
            text_w = fm.horizontalAdvance(symbol)
            text_h = fm.height()
            
            text_rect = QRectF(center.x() - text_w/2, center.y() - text_h/2, text_w, text_h)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, symbol)
            
            # [신규] 선택된 원자에 파란색 테두리 추가
            if is_selected:
                painter.setPen(QPen(Qt.GlobalColor.blue, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(center.x() - text_w/2 - 3, center.y() - text_h/2 - 2, text_w + 6, text_h + 4))
        
        painter.restore()

class TransitionEffect:
    @staticmethod
    def apply_circular_reveal(painter, radius, center_pt):
        # [핵심] PPT 스타일 원형 확장 클리핑 패스
        path = QPainterPath()
        path.addEllipse(center_pt, radius, radius)
        painter.setClipPath(path)


# ============================================================================
# [PHASE 4] LASSO SELECTION RENDERER (Theory layer 전용)
# ============================================================================

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
        self.lasso_path = QPainterPath()  # 사용자가 그린 경로
        self.points = []  # 경로상의 점들 (2D)
        self.selected_atoms = set()  # 선택된 원자 좌표
        self.selected_bonds = set()  # 선택된 결합
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
        
        # 경로 닫기
        self.lasso_path.closeSubpath()
        self.is_drawing = False
        
        # 최소 3개 이상의 점이 있어야 유효
        if len(self.points) < 3:
            self.lasso_path = QPainterPath()
            self.points = []
            return False
        
        return True
    
    def is_point_inside_lasso(self, point):
        """
        점이 라소 영역 내부에 있는지 확인
        - Ray casting 알고리즘 사용
        - 좌표는 rounded
        """
        if len(self.points) < 3:
            return False
        
        px, py = round(point.x(), 2), round(point.y(), 2)
        
        # Ray casting: 수평 광선 오른쪽으로 쏘기
        inside = False
        p1x, p1y = self.points[0]
        
        for i in range(1, len(self.points) + 1):
            p2x, p2y = self.points[i % len(self.points)]
            
            # 교차점 계산
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
        
        # 1. 라소 내부의 원자 찾기
        for pt_key in atoms.keys():
            # 이론적 좌표 사용
            center = t_map.get(pt_key, QPointF(*pt_key))
            if self.is_point_inside_lasso(center):
                self.selected_atoms.add(pt_key)
        
        # 2. 양 끝점이 모두 선택된 결합 선택
        for (k1, k2) in bonds.keys():
            if k1 in self.selected_atoms and k2 in self.selected_atoms:
                self.selected_bonds.add((k1, k2))
        
        return (self.selected_atoms, self.selected_bonds)
    
    def render_lasso_overlay(self, painter, alpha=0.3):
        """
        라소 시각화 및 선택 영역 표시
        
        Args:
            painter: QPainter 인스턴스
            alpha: 투명도 (0.0 ~ 1.0)
        """
        if len(self.points) < 2:
            return
        
        painter.save()
        
        # 라소 경로 그리기 (파란 점선)
        painter.setPen(QPen(QColor(0, 100, 255), 2.0, Qt.PenStyle.DashLine))
        painter.drawPath(self.lasso_path)
        
        # 라소 내부 채우기 (투명한 파란색)
        painter.setOpacity(alpha)
        painter.fillPath(self.lasso_path, QColor(0, 100, 255, 100))
        
        # 라소 경로상의 점들 표시 (작은 원)
        painter.setOpacity(1.0)
        painter.setBrush(QColor(0, 150, 255))
        painter.setPen(Qt.PenStyle.NoPen)
        for pt in self.points:
            painter.drawEllipse(QPointF(pt[0], pt[1]), 3, 3)
        
        painter.restore()
    
    def render_selection_highlight(self, painter, selected_atoms, 
                                   selected_bonds, t_map, atoms, bonds):
        """
        선택된 원자와 결합 하이라이트 처리
        
        Args:
            painter: QPainter 인스턴스
            selected_atoms: 선택된 원자 좌표 set
            selected_bonds: 선택된 결합 set
            t_map: 이론적 좌표 맵
            atoms: 원자 데이터
            bonds: 결합 데이터
        """
        painter.save()
        
        # 1. 선택된 결합 강조 (더 굵은 선)
        painter.setPen(QPen(QColor(255, 200, 0), 4.0))
        for (k1, k2) in selected_bonds:
            p1 = t_map.get(k1, QPointF(*k1))
            p2 = t_map.get(k2, QPointF(*k2))
            painter.drawLine(p1, p2)
        
        # 2. 선택된 원자 강조 (원형 하이라이트)
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
            
            # 부분 분자 구성
            emol = Chem.EditableMol(Chem.MolFromSmiles("C"))  # 더미 분자
            
            # 선택된 원자를 기반으로 submol 생성
            atom_list = list(selected_atoms)
            if atom_list:
                # 좌표를 원자 인덱스로 매핑
                atoms_list = [(pt, atoms.get(pt, {}).get("main", "C")) 
                              for pt in atom_list]
                
                # SMILES로 변환 (간단한 구현)
                smiles = None
                # TODO: RDKit을 사용한 정확한 SMILES 생성
                return smiles
        except:
            return None
    
    def clear_selection(self):
        """선택 제거"""
        self.lasso_path = QPainterPath()
        self.points = []
        self.selected_atoms.clear()
        self.selected_bonds.clear()
        self.is_drawing = False