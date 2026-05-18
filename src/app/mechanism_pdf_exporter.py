#!/usr/bin/env python3
"""
유기합성 경로 PDF 내보내기 (Organic Synthesis Mechanism Export to PDF).

합성 경로(SynthesisRoute)의 각 단계를 2D 구조 이미지 + 반응 화살표 + 조건으로
렌더링하여 A4 가로(landscape) PDF로 내보냄.

배치: 좌→우 흐름, 페이지 폭 초과 시 ㄹ자(snake) 형태로 줄바꿈.

Dependencies:
    - reportlab (PDF generation)
    - rdkit (2D structure rendering)
    - PIL/Pillow (image conversion)
"""

import io
import logging
import os
import tempfile
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── RDKit ──
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Draw
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# ── reportlab ──
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ── PIL ──
try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ── Project imports ──
from retrosynthesis_engine import SynthesisRoute, SynthesisStep
from building_blocks import get_building_block_info

# ═══════════════════════════════════════════════════════════
# 상수
# ═══════════════════════════════════════════════════════════

MOL_IMG_W = 150          # 분자 이미지 너비 (px → pt 변환)
MOL_IMG_H = 150          # 분자 이미지 높이
ARROW_W = 80             # 반응 화살표 영역 너비
STEP_GAP = 10            # 단계 사이 여백
ROW_GAP = 30             # 줄 간 여백 (ㄹ자 줄바꿈 시)
MARGIN_X = 40            # 좌우 여백
MARGIN_Y = 50            # 상하 여백
STEP_NUM_OFFSET_Y = 8    # 단계 번호 상단 오프셋
CONDITION_OFFSET_Y = 14  # 조건 텍스트 화살표 상단 오프셋

# 한글 폰트 경로 후보
_KOREAN_FONT_PATHS = [
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/System/Library/Fonts/AppleGothic.ttf",
]

_KOREAN_FONT_NAME = None  # 런타임 등록 후 저장


def _register_korean_font() -> Optional[str]:
    """시스템에서 한글 폰트를 찾아 reportlab에 등록. 성공 시 폰트 이름 반환."""
    global _KOREAN_FONT_NAME
    if _KOREAN_FONT_NAME is not None:
        return _KOREAN_FONT_NAME

    if not REPORTLAB_AVAILABLE:
        return None

    for fpath in _KOREAN_FONT_PATHS:
        if os.path.isfile(fpath):
            try:
                font_name = "KoreanGothic"
                pdfmetrics.registerFont(TTFont(font_name, fpath))
                _KOREAN_FONT_NAME = font_name
                logger.info("한글 폰트 등록 성공: %s", fpath)
                return font_name
            except Exception as e:
                logger.debug("폰트 등록 실패 (%s): %s", fpath, e)
                continue

    logger.warning("한글 폰트를 찾을 수 없음 — 기본 폰트 사용")
    _KOREAN_FONT_NAME = "Helvetica"
    return _KOREAN_FONT_NAME


# ═══════════════════════════════════════════════════════════
# Helper: SMILES → PNG bytes (via RDKit + PIL)
# ═══════════════════════════════════════════════════════════

def _smiles_to_png_bytes(smiles: str, width: int = MOL_IMG_W,
                         height: int = MOL_IMG_H) -> Optional[bytes]:
    """SMILES → PNG 이미지 bytes. 실패 시 None."""
    if not RDKIT_AVAILABLE or not PIL_AVAILABLE:
        return None
    # Rule N: isinstance 타입 가드
    if not isinstance(smiles, str) or not smiles.strip():
        logger.warning("_smiles_to_png_bytes: smiles가 유효하지 않습니다: %s", type(smiles))
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            # Rule L/M: SMILES 파싱 실패 시 경고 로그 (silent return 금지)
            logger.warning("SMILES 파싱 실패 (mechanism_pdf): %s", smiles)
            return None
        AllChem.Compute2DCoords(mol)
        img = Draw.MolToImage(mol, size=(width, height))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.debug("SMILES→PNG 실패 (%s): %s", smiles, e)
        return None


def _get_block_name_kr(smiles: str) -> str:
    """빌딩 블록의 한글 이름 반환. 없으면 SMILES 축약."""
    info = get_building_block_info(smiles)
    # Rule N: isinstance 타입 가드 — 외부 데이터 dict 검증
    if info and isinstance(info, dict):
        name = info.get("name_kr", info.get("name", smiles))
        if not isinstance(name, str):
            name = str(name) if name is not None else smiles
        return name
    # SMILES가 너무 길면 축약
    if len(smiles) > 25:
        return smiles[:22] + "..."
    return smiles


# ═══════════════════════════════════════════════════════════
# MechanismPDFExporter
# ═══════════════════════════════════════════════════════════

class MechanismPDFExporter:
    """합성 경로를 PDF로 내보내기.

    각 단계: [반응물 2D] ──→ [생성물 2D]
                        시약/조건

    단계 흐름은 좌→우, 페이지 폭 초과 시 ㄹ자(snake) 패턴으로 줄바꿈.
    """

    def __init__(self):
        self._font = _register_korean_font() or "Helvetica"

    # ──────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────

    def export_route(self, route: SynthesisRoute, output_path: str) -> bool:
        """합성 경로 전체를 PDF로 내보냄.

        Args:
            route: 내보낼 합성 경로 (SynthesisRoute)
            output_path: 저장할 PDF 파일 경로

        Returns:
            True 성공, False 실패
        """
        # Rule N: isinstance 타입 가드
        if not isinstance(route, SynthesisRoute):
            logger.warning("export_route: route가 SynthesisRoute가 아닙니다: %s", type(route))
            return False
        if not isinstance(output_path, str) or not output_path.strip():
            logger.warning("export_route: output_path가 유효하지 않습니다: %s", output_path)
            return False
        if not REPORTLAB_AVAILABLE:
            logger.error("reportlab이 설치되지 않았습니다.")
            return False
        if not RDKIT_AVAILABLE:
            logger.error("RDKit이 설치되지 않았습니다.")
            return False
        if not PIL_AVAILABLE:
            logger.error("Pillow(PIL)가 설치되지 않았습니다.")
            return False
        if not route or not route.steps:
            logger.error("내보낼 합성 경로가 비어있습니다.")
            return False

        try:
            page_w, page_h = landscape(A4)
            c = rl_canvas.Canvas(output_path, pagesize=landscape(A4))

            # ── 타이틀 페이지 헤더 ──
            self._draw_header(c, route, page_w, page_h)

            # ── 단계별 렌더링 (ㄹ자 배치) ──
            self._draw_steps_snake(c, route, page_w, page_h)

            c.save()
            logger.info("PDF 내보내기 완료: %s", output_path)
            return True

        except Exception as e:
            logger.error("PDF 내보내기 실패: %s", e, exc_info=True)
            return False

    # ──────────────────────────────────────────────────
    # Header
    # ──────────────────────────────────────────────────

    def _draw_header(self, c, route: SynthesisRoute,
                     page_w: float, page_h: float):
        """페이지 상단에 제목 + 요약 정보."""
        y = page_h - MARGIN_Y

        # 제목
        c.setFont(self._font, 16)
        c.setFillColor(colors.HexColor("#212121"))
        title = f"유기합성 경로 — {route.target_smiles}"
        if len(title) > 80:
            title = title[:77] + "..."
        c.drawString(MARGIN_X, y, title)
        y -= 20

        # 요약 라인
        c.setFont(self._font, 9)
        c.setFillColor(colors.HexColor("#616161"))
        summary = (
            f"총 {route.total_steps}단계 | "
            f"신뢰도 {route.score:.0%} | "
            f"빌딩블록: {', '.join(_get_block_name_kr(b) for b in route.building_blocks[:5])}"
        )
        if len(route.building_blocks) > 5:
            summary += f" 외 {len(route.building_blocks) - 5}개"
        c.drawString(MARGIN_X, y, summary)
        y -= 6

        # 구분선
        c.setStrokeColor(colors.HexColor("#BDBDBD"))
        c.setLineWidth(0.5)
        c.line(MARGIN_X, y, page_w - MARGIN_X, y)

    # ──────────────────────────────────────────────────
    # Snake-layout step rendering
    # ──────────────────────────────────────────────────

    def _draw_steps_snake(self, c, route: SynthesisRoute,
                          page_w: float, page_h: float):
        """ㄹ자 형태로 단계 배치.

        짝수 행: 좌→우
        홀수 행: 우→좌
        """
        usable_w = page_w - 2 * MARGIN_X
        # 한 단계의 총 가로 폭: 반응물 이미지 + 화살표 + 생성물 이미지
        # 첫 단계는 반응물 + 화살표 + 생성물
        # 이후 단계는 화살표 + 생성물 (이전 생성물 = 현재 반응물, 공유)
        # 하지만 반응물이 여러개일 수 있으므로 각 단계를 독립 블록으로 처리

        # 단계 블록 크기 계산
        step_block_w = MOL_IMG_W + ARROW_W + MOL_IMG_W  # ~380
        row_height = MOL_IMG_H + 40  # 이미지 + 하단 텍스트

        # 한 행에 들어가는 최대 단계 수
        max_per_row = max(1, int(usable_w / (step_block_w + STEP_GAP)))

        # 시작 Y (헤더 아래)
        start_y = page_h - MARGIN_Y - 50  # 헤더 영역 고려

        row = 0
        col = 0
        steps = route.steps

        for i, step in enumerate(steps):
            # ㄹ자: 짝수 행은 좌→우, 홀수 행은 우→좌
            if row % 2 == 0:
                x = MARGIN_X + col * (step_block_w + STEP_GAP)
            else:
                x = MARGIN_X + (max_per_row - 1 - col) * (step_block_w + STEP_GAP)

            y = start_y - row * (row_height + ROW_GAP)

            # 페이지 넘김 체크
            if y - row_height < MARGIN_Y:
                c.showPage()
                row = 0
                col = 0
                y = page_h - MARGIN_Y - 20
                if row % 2 == 0:
                    x = MARGIN_X + col * (step_block_w + STEP_GAP)
                else:
                    x = MARGIN_X + (max_per_row - 1 - col) * (step_block_w + STEP_GAP)

            # 단계 렌더링
            self._render_step(c, step, x, y, step_block_w)

            # ㄹ자 줄바꿈 연결 화살표 (행 끝 → 다음 행 시작)
            col += 1
            if col >= max_per_row:
                # 다음 행으로 이동 전, 수직 연결 화살표
                if i < len(steps) - 1:
                    self._draw_snake_connector(
                        c, x, y, row, max_per_row,
                        step_block_w, row_height, ROW_GAP
                    )
                col = 0
                row += 1

    # ──────────────────────────────────────────────────
    # Single step rendering
    # ──────────────────────────────────────────────────

    def _render_step(self, c, step: SynthesisStep,
                     x: float, y: float, block_w: float):
        """단일 단계 렌더링: [반응물] → [생성물]

        Args:
            c: reportlab Canvas
            step: 합성 단계
            x, y: 블록 좌상단 좌표 (y = top)
            block_w: 블록 총 너비
        """
        # ── 단계 번호 배지 ──
        c.setFont(self._font, 8)
        c.setFillColor(colors.HexColor("#1565C0"))
        c.drawString(x, y + STEP_NUM_OFFSET_Y,
                     f"Step {step.step_number}")

        # ── 반응 이름 (한글) ──
        c.setFont(self._font, 7)
        c.setFillColor(colors.HexColor("#424242"))
        transform_label = step.transform_name
        if len(transform_label) > 30:
            transform_label = transform_label[:27] + "..."
        c.drawString(x + 40, y + STEP_NUM_OFFSET_Y, transform_label)

        # ── 반응물 이미지 ──
        reactant_smi = ".".join(step.reactant_smiles)
        self._draw_mol_image(c, reactant_smi, x, y - MOL_IMG_H,
                             MOL_IMG_W, MOL_IMG_H)

        # 반응물 이름 (빌딩블록인 경우 한글)
        if len(step.reactant_smiles) == 1:
            rname = _get_block_name_kr(step.reactant_smiles[0])
        else:
            names = []
            for rs in step.reactant_smiles[:3]:
                names.append(_get_block_name_kr(rs))
            rname = " + ".join(names)
        if len(rname) > 30:
            rname = rname[:27] + "..."
        c.setFont(self._font, 6)
        c.setFillColor(colors.HexColor("#757575"))
        c.drawString(x, y - MOL_IMG_H - 10, rname)

        # ── 반응 화살표 + 조건 ──
        arrow_x1 = x + MOL_IMG_W + 5
        arrow_x2 = x + MOL_IMG_W + ARROW_W - 5
        arrow_y = y - MOL_IMG_H / 2
        self._draw_reaction_arrow(c, arrow_x1, arrow_y, arrow_x2, arrow_y,
                                  step.conditions)

        # ── 생성물 이미지 ──
        prod_x = x + MOL_IMG_W + ARROW_W
        self._draw_mol_image(c, step.product_smiles, prod_x,
                             y - MOL_IMG_H, MOL_IMG_W, MOL_IMG_H)

        # 생성물 이름
        pname = _get_block_name_kr(step.product_smiles)
        if len(pname) > 25:
            pname = pname[:22] + "..."
        c.setFont(self._font, 6)
        c.setFillColor(colors.HexColor("#757575"))
        c.drawString(prod_x, y - MOL_IMG_H - 10, pname)

        # 신뢰도 표시
        c.setFont(self._font, 6)
        conf_color = (
            "#4CAF50" if step.confidence >= 0.7
            else "#FF9800" if step.confidence >= 0.4
            else "#F44336"
        )
        c.setFillColor(colors.HexColor(conf_color))
        c.drawRightString(
            x + block_w, y - MOL_IMG_H - 10,
            f"신뢰도 {step.confidence:.0%}"
        )

    # ──────────────────────────────────────────────────
    # Molecule image drawing
    # ──────────────────────────────────────────────────

    def _draw_mol_image(self, c, smiles: str, x: float, y: float,
                        w: float, h: float):
        """분자 2D 이미지를 PDF 캔버스에 그림.

        Args:
            c: reportlab Canvas
            smiles: 분자 SMILES
            x, y: 이미지 좌하단 좌표
            w, h: 이미지 크기
        """
        # 배경 박스 (흰색 라운드 사각형)
        c.setStrokeColor(colors.HexColor("#E0E0E0"))
        c.setFillColor(colors.white)
        c.setLineWidth(0.5)
        c.roundRect(x, y, w, h, radius=6, fill=1, stroke=1)

        png_data = _smiles_to_png_bytes(smiles, int(w), int(h))
        if png_data is None:
            # 이미지 생성 실패 → 텍스트 대체
            c.setFont(self._font, 7)
            c.setFillColor(colors.HexColor("#F44336"))
            display_smi = smiles if len(smiles) <= 20 else smiles[:17] + "..."
            c.drawCentredString(x + w / 2, y + h / 2, display_smi)
            return

        # PNG bytes → reportlab ImageReader
        try:
            from reportlab.lib.utils import ImageReader
            img_reader = ImageReader(io.BytesIO(png_data))
            # 여백을 두고 이미지 배치
            pad = 4
            c.drawImage(img_reader, x + pad, y + pad,
                        width=w - 2 * pad, height=h - 2 * pad,
                        preserveAspectRatio=True, mask='auto')
        except Exception as e:
            logger.debug("이미지 삽입 실패: %s", e)
            c.setFont(self._font, 7)
            c.setFillColor(colors.HexColor("#F44336"))
            c.drawCentredString(x + w / 2, y + h / 2, "렌더링 실패")

    # ──────────────────────────────────────────────────
    # Reaction arrow
    # ──────────────────────────────────────────────────

    def _draw_reaction_arrow(self, c, x1: float, y1: float,
                             x2: float, y2: float,
                             conditions: str):
        """반응 화살표 + 조건 텍스트.

        Args:
            c: reportlab Canvas
            x1, y1: 화살표 시작점
            x2, y2: 화살표 끝점
            conditions: 화살표 위에 표시할 시약/조건
        """
        # 화살표 본체 (굵은 선)
        c.setStrokeColor(colors.HexColor("#333333"))
        c.setLineWidth(1.5)
        c.line(x1, y1, x2 - 8, y2)

        # 화살촉 (삼각형)
        from reportlab.lib.colors import HexColor
        c.setFillColor(HexColor("#333333"))
        arrow_path = c.beginPath()
        arrow_path.moveTo(x2, y2)
        arrow_path.lineTo(x2 - 8, y2 + 4)
        arrow_path.lineTo(x2 - 8, y2 - 4)
        arrow_path.close()
        c.drawPath(arrow_path, fill=1, stroke=0)

        # 조건 텍스트 (화살표 위)
        if conditions:
            mid_x = (x1 + x2) / 2
            # 조건 텍스트를 줄바꿈 처리 (너무 길면)
            cond_lines = self._wrap_conditions(conditions, max_chars=20)
            c.setFont(self._font, 5.5)
            c.setFillColor(colors.HexColor("#D84315"))
            for idx, line in enumerate(cond_lines):
                ty = y1 + CONDITION_OFFSET_Y + (len(cond_lines) - 1 - idx) * 7
                c.drawCentredString(mid_x, ty, line)

    # ──────────────────────────────────────────────────
    # Snake connector (행 전환 화살표)
    # ──────────────────────────────────────────────────

    def _draw_snake_connector(self, c, last_x: float, last_y: float,
                              row: int, max_per_row: int,
                              block_w: float, row_height: float,
                              row_gap: float):
        """ㄹ자 줄바꿈 시 수직 연결 화살표."""
        # 현재 행의 마지막 생성물 → 다음 행의 첫 반응물
        # 수직 아래로 내려가는 곡선 화살표
        if row % 2 == 0:
            # 짝수 행 끝(오른쪽) → 홀수 행 시작(오른쪽)
            cx = last_x + block_w
        else:
            # 홀수 행 끝(왼쪽) → 짝수 행 시작(왼쪽)
            cx = MARGIN_X + MOL_IMG_W / 2

        top_y = last_y - MOL_IMG_H - 15
        bot_y = top_y - row_gap + 5

        c.setStrokeColor(colors.HexColor("#78909C"))
        c.setLineWidth(1.0)
        c.setDash([3, 3])
        c.line(cx, top_y, cx, bot_y + 8)
        c.setDash([])

        # 작은 아래 화살촉
        c.setFillColor(colors.HexColor("#78909C"))
        arrow_path = c.beginPath()
        arrow_path.moveTo(cx, bot_y)
        arrow_path.lineTo(cx - 3, bot_y + 6)
        arrow_path.lineTo(cx + 3, bot_y + 6)
        arrow_path.close()
        c.drawPath(arrow_path, fill=1, stroke=0)

    # ──────────────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────────────

    @staticmethod
    def _wrap_conditions(text: str, max_chars: int = 20) -> List[str]:
        """긴 조건 텍스트를 여러 줄로 분할."""
        if not text:
            return []
        # '또는', '/' 등으로 먼저 분할 시도
        if len(text) <= max_chars:
            return [text]

        lines = []
        # 쉼표 기준 분할
        parts = text.split(", ")
        current = ""
        for part in parts:
            if current and len(current) + len(part) + 2 > max_chars:
                lines.append(current)
                current = part
            else:
                current = (current + ", " + part) if current else part
        if current:
            lines.append(current)

        # 최대 3줄까지만
        if len(lines) > 3:
            lines = lines[:3]
            lines[-1] = lines[-1][:max_chars - 3] + "..."

        return lines


# ═══════════════════════════════════════════════════════════
# Convenience function (for popup integration)
# ═══════════════════════════════════════════════════════════

def export_synthesis_route_pdf(route: SynthesisRoute,
                               output_path: Optional[str] = None) -> Tuple[bool, str]:
    """합성 경로를 PDF로 내보내는 편의 함수.

    Args:
        route: 내보낼 합성 경로
        output_path: 저장 경로 (None이면 임시 파일 생성)

    Returns:
        (성공 여부, 파일 경로 또는 에러 메시지)
    """
    if output_path is None:
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"chemgrid_synthesis_route.pdf"
        )

    exporter = MechanismPDFExporter()
    success = exporter.export_route(route, output_path)

    if success:
        return True, output_path
    else:
        return False, "PDF 내보내기 실패 — 로그를 확인하세요."
