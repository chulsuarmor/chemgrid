#!/usr/bin/env python3
"""
DryLab AI Reviewer — PDF 품질 검증 모듈.

DryLab Report PDF를 학술 논문 기준으로 검수하여
PASS/FAIL 판정, 점수, 이슈 목록, 개선 제안을 반환합니다.

10가지 검증 항목:
  1. 페이지 수 (최소 10페이지)
  2. Figure 번호 매기기
  3. Table 번호 매기기
  4. 14개 섹션 헤더 존재
  5. 빈 섹션 없음 (고찰/결론 제외)
  6. 이미지 품질 (200x200 px 이상)
  7. 참고문헌 5건 이상
  8. 한국어 텍스트 포함
  9. 분자 구조 이미지 (첫 3페이지)
 10. 스펙트럼 그래프 3개 이상

Dependencies:
    - PyMuPDF (fitz)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── PyMuPDF ──
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False


# ── 결과 데이터클래스 ──
@dataclass
class ReviewResult:
    """DryLab 보고서 검증 결과."""
    passed: bool = False
    score: float = 0.0
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """사람이 읽을 수 있는 요약 문자열 반환."""
        status = "PASS" if self.passed else "FAIL"
        lines = [f"[{status}] 점수: {self.score:.1f}/100"]
        if self.issues:
            lines.append("\n이슈:")
            for i, issue in enumerate(self.issues, 1):
                lines.append(f"  {i}. {issue}")
        if self.suggestions:
            lines.append("\n개선 제안:")
            for i, sug in enumerate(self.suggestions, 1):
                lines.append(f"  {i}. {sug}")
        return "\n".join(lines)


# ── exporter 실제 Part 헤더와 동기화 (DW5-P0-002/005 fix 2026-05-12) ──
EXPECTED_SECTION_HEADERS = [
    # (번호, 한국어 키워드, 영어 키워드) — PDF 텍스트에서 검색용
    # 실제 exporter 섹션: Part 1~8 기반 (초록/Abstract 섹션 없음)
    ("1", "\uc2dc\uc791 \ubb3c\uc9c8", "Part 1"),
    ("2", "\uc218\uc6a9\uccb4", "Part 2"),
    ("3", "\uc720\ub3c4\uccb4 \uc124\uacc4", "Part 3"),
    ("4", "\uc720\ub3c4\uccb4 \uc7ac\ubd84\uc11d", "Part 4"),
    ("5", "\ud569\uc131 \uc124\uacc4", "Part 5"),
    ("7", "\uace0\ucc30", "Discussion"),
    ("8", "\ucc38\uace0\ubb38\ud5cc", "References"),
    ("P1", "\uc774\ub860\uc801 \ubd84\uc11d", "Theoretical"),
    ("P2", "\ub3c5\ud0b9", "Docking"),
    ("P3", "ADMET", "ADMET"),
]
# 표지(Section 0)는 번호 없이 제목만 있으므로 별도 검증

# 고찰/결론은 의도적으로 빈 섹션 (Part 7 = Discussion/Conclusion)
BLANK_SECTIONS = {"7"}

# 스펙트럼 관련 키워드
SPECTRUM_KEYWORDS = ["IR", "NMR", "UV-Vis", "Raman", "스펙트럼", "Spectrum",
                     "spectrum", "적외선", "자외선", "라만"]


class DryLabReportReviewer:
    """DryLab 보고서 PDF 품질 검증기."""

    # 각 검증 항목별 배점 (총합 100)
    WEIGHTS = {
        "page_count": 10,
        "figure_numbering": 8,
        "table_numbering": 7,
        "sections_present": 15,
        "no_empty_sections": 10,
        "image_quality": 10,
        "references": 10,
        "korean_text": 10,
        "molecular_structure": 10,
        "spectrum_graphs": 10,
    }
    PASS_THRESHOLD = 70.0

    def __init__(self):
        if not FITZ_AVAILABLE:
            raise ImportError(
                "PyMuPDF(fitz)가 설치되지 않았습니다. "
                "'pip install PyMuPDF' 로 설치하세요."
            )

    def review(self, pdf_path: str) -> ReviewResult:
        """
        PDF 파일을 분석하여 ReviewResult를 반환합니다.

        Parameters
        ----------
        pdf_path : str
            검증할 DryLab Report PDF 경로.

        Returns
        -------
        ReviewResult
            passed, score, issues, suggestions 포함.
        """
        result = ReviewResult()

        # N코드: 외부 입력 타입 가드
        if not isinstance(pdf_path, str) or not pdf_path.strip():
            logger.warning("review: pdf_path 타입/값 불일치 (type=%s)",
                           type(pdf_path).__name__)
            result.issues.append("PDF 경로가 유효하지 않습니다.")
            return result

        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:
            result.issues.append(f"PDF 열기 실패: {exc}")
            return result

        try:
            # 모든 페이지 텍스트 수집
            page_texts: List[str] = []
            page_images: List[list] = []
            for page in doc:
                page_texts.append(page.get_text())
                page_images.append(page.get_images(full=True))

            full_text = "\n".join(page_texts)
            total_pages = len(page_texts)

            # 개별 검증 수행 — 각 함수는 (score_ratio, issues, suggestions) 반환
            checks = {
                "page_count": self._check_page_count(total_pages),
                "figure_numbering": self._check_figure_numbering(full_text),
                "table_numbering": self._check_table_numbering(full_text),
                "sections_present": self._check_sections(full_text),
                "no_empty_sections": self._check_empty_sections(
                    page_texts, full_text
                ),
                "image_quality": self._check_image_quality(doc, page_images),
                "references": self._check_references(full_text),
                "korean_text": self._check_korean_text(full_text),
                "molecular_structure": self._check_molecular_structure(
                    page_images, total_pages
                ),
                "spectrum_graphs": self._check_spectrum_graphs(
                    full_text, page_images
                ),
            }

            # 점수 합산
            total_score = 0.0
            for key, (ratio, issues, suggestions) in checks.items():
                weight = self.WEIGHTS[key]
                total_score += ratio * weight
                result.issues.extend(issues)
                result.suggestions.extend(suggestions)

            result.score = round(total_score, 1)
            result.passed = result.score >= self.PASS_THRESHOLD

        except Exception as exc:
            logger.error("DryLab review error: %s", exc, exc_info=True)
            result.issues.append(f"검증 중 오류 발생: {exc}")
        finally:
            doc.close()

        return result

    # ──────────────────────────────────────────────────────────────
    # 개별 검증 함수들 — 반환: (score_ratio 0~1, issues, suggestions)
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _check_page_count(
        total_pages: int,
    ) -> Tuple[float, List[str], List[str]]:
        """1. 페이지 수 검증 (최소 10페이지)."""
        # N코드: 타입 가드
        if not isinstance(total_pages, int):
            logger.warning("_check_page_count: total_pages 타입 불일치 (expected int, got %s)",
                           type(total_pages).__name__)
            try:
                total_pages = int(total_pages)
            except (TypeError, ValueError):
                total_pages = 0
        issues: List[str] = []
        suggestions: List[str] = []
        if total_pages >= 10:
            return (1.0, issues, suggestions)
        ratio = total_pages / 10.0
        issues.append(
            f"페이지 수 부족: {total_pages}페이지 (최소 10페이지 필요)"
        )
        suggestions.append(
            "섹션별 내용을 보강하거나, 그래프/구조식을 추가하세요."
        )
        return (ratio, issues, suggestions)

    @staticmethod
    def _check_figure_numbering(
        full_text: str,
    ) -> Tuple[float, List[str], List[str]]:
        """2. Figure 번호 매기기 검증."""
        # N코드: 타입 가드
        if not isinstance(full_text, str):
            logger.warning("_check_figure_numbering: full_text 타입 불일치 (expected str, got %s)",
                           type(full_text).__name__)
            return (0.0, ["full_text 타입 오류"], [])
        issues: List[str] = []
        suggestions: List[str] = []

        # "Figure N." 또는 "그림 N." 패턴
        fig_pattern = re.compile(
            r"(?:Figure|Fig\.|그림)\s*(\d+)", re.IGNORECASE
        )
        matches = fig_pattern.findall(full_text)

        if not matches:
            # Figure가 없는 건 이미지가 있는데 캡션이 없는 것일 수 있음
            issues.append("Figure 캡션이 발견되지 않았습니다.")
            suggestions.append(
                "모든 그림에 'Figure N.' 형식의 캡션을 추가하세요."
            )
            return (0.0, issues, suggestions)

        # 번호 연속성 체크
        nums = sorted(set(int(n) for n in matches))
        expected = list(range(1, nums[-1] + 1))
        missing = set(expected) - set(nums)

        if missing:
            issues.append(
                f"Figure 번호 누락: {sorted(missing)} "
                f"(발견된 번호: {nums})"
            )
            ratio = 1.0 - len(missing) / len(expected)
            return (max(0.0, ratio), issues, suggestions)

        return (1.0, issues, suggestions)

    @staticmethod
    def _check_table_numbering(
        full_text: str,
    ) -> Tuple[float, List[str], List[str]]:
        """3. Table 번호 매기기 검증."""
        # N코드: 타입 가드
        if not isinstance(full_text, str):
            logger.warning("_check_table_numbering: full_text 타입 불일치 (expected str, got %s)",
                           type(full_text).__name__)
            return (0.0, ["full_text 타입 오류"], [])
        issues: List[str] = []
        suggestions: List[str] = []

        tbl_pattern = re.compile(
            r"(?:Table|표)\s*(\d+)", re.IGNORECASE
        )
        matches = tbl_pattern.findall(full_text)

        if not matches:
            # 테이블이 없을 수 있으므로 경미한 감점만
            suggestions.append(
                "데이터를 표로 정리하고 'Table N.' 캡션을 추가하면 "
                "보고서 품질이 향상됩니다."
            )
            return (0.5, issues, suggestions)

        nums = sorted(set(int(n) for n in matches))
        expected = list(range(1, nums[-1] + 1))
        missing = set(expected) - set(nums)

        if missing:
            issues.append(
                f"Table 번호 누락: {sorted(missing)} "
                f"(발견된 번호: {nums})"
            )
            ratio = 1.0 - len(missing) / len(expected)
            return (max(0.0, ratio), issues, suggestions)

        return (1.0, issues, suggestions)

    @staticmethod
    def _check_sections(
        full_text: str,
    ) -> Tuple[float, List[str], List[str]]:
        """4. 14개 섹션 헤더 존재 검증."""
        # N코드: 타입 가드
        if not isinstance(full_text, str):
            logger.warning("_check_sections: full_text 타입 불일치 (expected str, got %s)",
                           type(full_text).__name__)
            return (0.0, ["full_text 타입 오류"], [])
        issues: List[str] = []
        suggestions: List[str] = []
        found = 0
        missing_sections: List[str] = []

        for num, kr_keyword, en_keyword in EXPECTED_SECTION_HEADERS:
            # "N. 한국어" 또는 "N. English" 패턴 검색
            pattern_kr = f"{num}." in full_text and kr_keyword in full_text
            pattern_en = f"{num}." in full_text and en_keyword in full_text
            # 좀 더 유연하게: 번호 없이 키워드만 있어도 인정
            keyword_only = kr_keyword in full_text or en_keyword in full_text

            if pattern_kr or pattern_en or keyword_only:
                found += 1
            else:
                missing_sections.append(f"{num}. {kr_keyword} ({en_keyword})")

        total = len(EXPECTED_SECTION_HEADERS)
        if missing_sections:
            issues.append(
                f"누락된 섹션 ({len(missing_sections)}개): "
                + ", ".join(missing_sections)
            )
            suggestions.append(
                "DryLab 보고서는 14개 섹션 구조를 갖추어야 합니다."
            )

        ratio = found / total if total > 0 else 0.0
        return (ratio, issues, suggestions)

    @staticmethod
    def _check_empty_sections(
        page_texts: List[str], full_text: str,
    ) -> Tuple[float, List[str], List[str]]:
        """5. 빈 섹션 검증 (고찰/결론 제외)."""
        # N코드: 타입 가드
        if not isinstance(page_texts, list):
            logger.warning("_check_empty_sections: page_texts 타입 불일치 (expected list, got %s)",
                           type(page_texts).__name__)
            return (0.0, ["page_texts 타입 오류"], [])
        if not isinstance(full_text, str):
            logger.warning("_check_empty_sections: full_text 타입 불일치 (expected str, got %s)",
                           type(full_text).__name__)
            return (0.0, ["full_text 타입 오류"], [])
        issues: List[str] = []
        suggestions: List[str] = []

        # 섹션 간 텍스트 길이로 빈 섹션 판단
        empty_found = 0
        checked = 0

        for i, (num, kr_kw, en_kw) in enumerate(EXPECTED_SECTION_HEADERS):
            if num in BLANK_SECTIONS:
                continue  # 고찰/결론은 빈 것이 정상

            checked += 1
            # 해당 섹션과 다음 섹션 사이의 텍스트 길이 추정
            # 키워드 위치 찾기
            kr_pos = full_text.find(kr_kw)
            en_pos = full_text.find(en_kw)
            start = max(kr_pos, en_pos)

            if start < 0:
                continue  # 섹션 자체가 없으면 _check_sections에서 처리

            # 다음 섹션 시작점 찾기
            end = len(full_text)
            if i + 1 < len(EXPECTED_SECTION_HEADERS):
                next_num, next_kr, next_en = EXPECTED_SECTION_HEADERS[i + 1]
                next_kr_pos = full_text.find(next_kr, start + len(kr_kw))
                next_en_pos = full_text.find(next_en, start + len(en_kw))
                candidates = [p for p in [next_kr_pos, next_en_pos] if p > 0]
                if candidates:
                    end = min(candidates)

            section_text = full_text[start:end].strip()
            # 섹션 제목 자체 길이를 빼고 내용이 50자 미만이면 빈 섹션
            content_len = len(section_text) - len(kr_kw) - len(en_kw) - 10
            if content_len < 50:
                empty_found += 1
                issues.append(
                    f"섹션 {num}. {kr_kw} 의 내용이 너무 짧습니다 "
                    f"(약 {max(0, content_len)}자)"
                )

        if checked == 0:
            return (0.0, issues, suggestions)

        ratio = 1.0 - (empty_found / checked)
        if empty_found > 0:
            suggestions.append(
                "내용이 부족한 섹션에 분석 결과와 설명을 추가하세요."
            )
        return (max(0.0, ratio), issues, suggestions)

    @staticmethod
    def _check_image_quality(
        doc, page_images: List[list],
    ) -> Tuple[float, List[str], List[str]]:
        """6. 이미지 품질 검증 (200x200 px 이상)."""
        # N코드: 타입 가드
        if not isinstance(page_images, list):
            logger.warning("_check_image_quality: page_images 타입 불일치 (expected list, got %s)",
                           type(page_images).__name__)
            return (0.0, ["page_images 타입 오류"], [])
        if doc is None:
            logger.warning("_check_image_quality: doc is None")
            return (0.0, ["PDF 문서 객체가 None"], [])
        issues: List[str] = []
        suggestions: List[str] = []
        total_images = 0
        small_images = 0

        for page_idx, images in enumerate(page_images):
            for img_info in images:
                total_images += 1
                try:
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    if base_image:
                        # Rule N: isinstance guard for base_image
                        if not isinstance(base_image, dict): base_image = {}
                        w = base_image.get("width", 0)
                        h = base_image.get("height", 0)
                        if w < 200 or h < 200:
                            small_images += 1
                except Exception as e:
                    logger.warning("Image extraction failed: %s", e)

        if total_images == 0:
            issues.append("PDF에 이미지가 없습니다.")
            suggestions.append(
                "분자 구조, 스펙트럼 그래프 등의 이미지를 포함하세요."
            )
            return (0.0, issues, suggestions)

        if small_images > 0:
            issues.append(
                f"저품질 이미지 {small_images}개 발견 "
                f"(200x200 px 미만, 전체 {total_images}개 중)"
            )
            suggestions.append(
                "이미지를 300 DPI 이상으로 생성하여 품질을 높이세요."
            )

        good = total_images - small_images
        ratio = good / total_images if total_images > 0 else 0.0
        return (ratio, issues, suggestions)

    @staticmethod
    def _check_references(
        full_text: str,
    ) -> Tuple[float, List[str], List[str]]:
        """7. 참고문헌 5건 이상 검증."""
        # N코드: 타입 가드
        if not isinstance(full_text, str):
            logger.warning("_check_references: full_text 타입 불일치 (expected str, got %s)",
                           type(full_text).__name__)
            return (0.0, ["full_text 타입 오류"], [])
        issues: List[str] = []
        suggestions: List[str] = []

        # 참고문헌 섹션 찾기
        ref_start = -1
        for marker in ["13. 참고문헌", "13. References", "참고문헌"]:
            pos = full_text.find(marker)
            if pos >= 0:
                ref_start = pos
                break

        if ref_start < 0:
            issues.append("참고문헌 섹션을 찾을 수 없습니다.")
            return (0.0, issues, suggestions)

        ref_text = full_text[ref_start:]

        # [N] 패턴 또는 번호 매긴 참고문헌 카운트
        bracket_refs = re.findall(r"\[\d+\]", ref_text)
        # 줄 단위 참고문헌도 고려 (번호. 저자...)
        line_refs = re.findall(
            r"^\s*\d+[\.\)]\s+\S", ref_text, re.MULTILINE
        )
        ref_count = max(len(set(bracket_refs)), len(line_refs))

        if ref_count >= 5:
            return (1.0, issues, suggestions)

        ratio = ref_count / 5.0
        issues.append(
            f"참고문헌 {ref_count}건 (최소 5건 필요)"
        )
        suggestions.append(
            "NIST, PubChem, 교과서 등의 참고문헌을 추가하세요."
        )
        return (ratio, issues, suggestions)

    @staticmethod
    def _check_korean_text(
        full_text: str,
    ) -> Tuple[float, List[str], List[str]]:
        """8. 한국어 텍스트 포함 검증."""
        # N코드: 타입 가드
        if not isinstance(full_text, str):
            logger.warning("_check_korean_text: full_text 타입 불일치 (expected str, got %s)",
                           type(full_text).__name__)
            return (0.0, ["full_text 타입 오류"], [])
        issues: List[str] = []
        suggestions: List[str] = []

        # 한글 유니코드 범위: AC00-D7A3 (완성형), 3131-318E (자모)
        korean_chars = re.findall(r"[\uAC00-\uD7A3]", full_text)
        kr_count = len(korean_chars)

        if kr_count >= 50:
            return (1.0, issues, suggestions)

        if kr_count > 0:
            ratio = min(1.0, kr_count / 50.0)
            issues.append(
                f"한국어 텍스트가 부족합니다 ({kr_count}자, 최소 50자 권장)"
            )
        else:
            ratio = 0.0
            issues.append("한국어 텍스트가 없습니다 (영문 전용 보고서)")

        suggestions.append(
            "DryLab 보고서는 한국어 학술 논문 양식을 따릅니다. "
            "섹션 제목과 본문에 한국어를 포함하세요."
        )
        return (ratio, issues, suggestions)

    @staticmethod
    def _check_molecular_structure(
        page_images: List[list], total_pages: int,
    ) -> Tuple[float, List[str], List[str]]:
        """9. 분자 구조 이미지 (첫 3페이지 내)."""
        # N코드: 타입 가드
        if not isinstance(page_images, list):
            logger.warning("_check_molecular_structure: page_images 타입 불일치 (expected list, got %s)",
                           type(page_images).__name__)
            return (0.0, ["page_images 타입 오류"], [])
        if not isinstance(total_pages, int):
            logger.warning("_check_molecular_structure: total_pages 타입 불일치 (expected int, got %s)",
                           type(total_pages).__name__)
            try:
                total_pages = int(total_pages)
            except (TypeError, ValueError):
                total_pages = 0
        issues: List[str] = []
        suggestions: List[str] = []

        # 첫 3페이지에서 이미지가 1개 이상 있으면 분자 구조로 간주
        check_pages = min(3, total_pages)
        images_in_first3 = 0
        for i in range(check_pages):
            images_in_first3 += len(page_images[i])

        if images_in_first3 >= 1:
            return (1.0, issues, suggestions)

        issues.append(
            "첫 3페이지에 분자 구조 이미지가 없습니다."
        )
        suggestions.append(
            "표지 또는 초록에 RDKit 생성 분자 구조 이미지를 포함하세요."
        )
        return (0.0, issues, suggestions)

    @staticmethod
    def _check_spectrum_graphs(
        full_text: str, page_images: List[list],
    ) -> Tuple[float, List[str], List[str]]:
        """10. 스펙트럼 그래프 3개 이상 검증."""
        # N코드: 타입 가드
        if not isinstance(full_text, str):
            logger.warning("_check_spectrum_graphs: full_text 타입 불일치 (expected str, got %s)",
                           type(full_text).__name__)
            return (0.0, ["full_text 타입 오류"], [])
        if not isinstance(page_images, list):
            logger.warning("_check_spectrum_graphs: page_images 타입 불일치 (expected list, got %s)",
                           type(page_images).__name__)
            return (0.0, ["page_images 타입 오류"], [])
        issues: List[str] = []
        suggestions: List[str] = []

        # 스펙트럼 관련 키워드 근처에 Figure가 있는지 확인
        spectrum_mentions = 0
        for kw in SPECTRUM_KEYWORDS:
            if kw.lower() in full_text.lower():
                spectrum_mentions += 1

        # 분광 분석 섹션(Section 5) 이후 이미지 수 확인
        # 전체 이미지에서 분광 관련 이미지 추정
        total_images = sum(len(imgs) for imgs in page_images)

        # 스펙트럼 Figure 캡션 카운트
        spectrum_fig_pattern = re.compile(
            r"(?:Figure|Fig\.|그림)\s*\d+.*?"
            r"(?:IR|NMR|UV|Vis|Raman|스펙트럼|spectrum|적외선|자외선|라만)",
            re.IGNORECASE,
        )
        spectrum_figs = spectrum_fig_pattern.findall(full_text)
        n_spectrum = len(spectrum_figs)

        # 캡션이 없더라도 키워드가 풍부하고 이미지가 있으면 부분 점수
        if n_spectrum >= 3:
            return (1.0, issues, suggestions)

        # 스펙트럼 키워드가 3개 이상이고 전체 이미지가 충분하면 부분 인정
        if spectrum_mentions >= 3 and total_images >= 5:
            ratio = min(1.0, 0.5 + n_spectrum * 0.2)
            if n_spectrum < 3:
                suggestions.append(
                    "스펙트럼 Figure에 'IR', 'NMR', 'UV-Vis' 등의 "
                    "캡션을 명시하세요."
                )
            return (ratio, issues, suggestions)

        ratio = n_spectrum / 3.0
        issues.append(
            f"스펙트럼 그래프 {n_spectrum}개 (최소 3개 필요: IR/NMR/UV-Vis)"
        )
        suggestions.append(
            "IR, NMR, UV-Vis 스펙트럼 그래프를 각각 Figure로 "
            "포함하고 캡션을 추가하세요."
        )
        return (max(0.0, ratio), issues, suggestions)


# ── 편의 함수 ──
def review_drylab_report(pdf_path: str) -> ReviewResult:
    """
    DryLab 보고서 PDF를 검증하는 편의 함수.

    Parameters
    ----------
    pdf_path : str
        검증할 PDF 파일 경로.

    Returns
    -------
    ReviewResult
        검증 결과.
    """
    # N코드: 외부 입력 타입 가드
    if not isinstance(pdf_path, str) or not pdf_path.strip():
        logger.warning("review_drylab_report: pdf_path 타입/값 불일치 (type=%s)",
                       type(pdf_path).__name__)
        result = ReviewResult()
        result.issues.append("PDF 경로가 유효하지 않습니다.")
        return result
    reviewer = DryLabReportReviewer()
    return reviewer.review(pdf_path)
