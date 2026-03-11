"""
claude_client.py - ChemGrid Claude Sonnet 4.6 Prefix Caching 클라이언트
=======================================================================
목적:
  - Anthropic Claude API의 Prefix Caching을 활용하여 비용 최대 90% 절감
  - masterplan.md, mistakes.md를 매 요청 시 메시지 최상단(Prefix)에 자동 배치
  - cache_creation_input_tokens / cache_read_input_tokens 로깅
  - Append Only 정책으로 캐시 브레이크포인트 보존

Anthropic Prefix Caching 원리:
  - 메시지의 앞부분(Prefix)이 변하지 않으면 캐시 히트 발생 → 비용 90% 절감
  - cache_control: {"type": "ephemeral"} 마킹으로 캐시 포인트 지정
  - 최대 4개 캐시 브레이크포인트 지원
  - 1번 브레이크포인트: 시스템 프롬프트 (가장 정적, 가장 중요)
  - 2번 브레이크포인트: masterplan.md (세션 내 거의 불변)
  - 3번 브레이크포인트: mistakes.md (append only로 앞부분 불변 유지)
  - 4번 브레이크포인트: 대용량 코드 분석 시 코드 블록

사용법:
  from claude_client import ClaudeClient, append_only_write
  
  client = ClaudeClient()
  response = client.chat("분광 그래프 렌더링 코드를 분석해줘")
  print(f"캐시 절감: {response.cache_stats}")
"""

import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("[claude_client] WARNING: anthropic 패키지 미설치. 'pip install anthropic' 실행 필요")

from dotenv import load_dotenv

load_dotenv()

# ─── 프로젝트 루트 경로 ──────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent  # chemgrid/
MASTERPLAN_PATH = PROJECT_ROOT / "master_plan.md"
MISTAKES_PATH = PROJECT_ROOT / "docs" / "ai" / "mistakes.md"
CACHE_LOG_PATH = PROJECT_ROOT / "memory" / "cache_stats.jsonl"

# ─── 시스템 프롬프트 (정적 - 캐시 1번 포인트) ────────────────────────────────
SYSTEM_PROMPT_STATIC = """
당신은 ChemGrid 프로젝트의 Claude Sonnet 4.6 자율 코딩 에이전트입니다.

[역할 및 권한]
- 코드 품질 판단 및 자율 최적화 권한 보유
- 에러 자가 복구, 리팩토링, 타입 안정성 개선은 독자 판단으로 수행
- 화학/물리 수식(E[ρ], DFT 로직), 아키텍처 설계 변경은 Plan 모드 승인 후 진행

[캐시 운용 규칙]
- masterplan.md, mistakes.md는 절대 내용 삭제/중간 삽입 금지 → Append Only
- 앞부분이 1자라도 바뀌면 캐시 브레이크포인트가 깨짐
- 대용량 코드 분석 시 '분석 단계'와 '수정 단계'를 명확히 분리

[출력 형식]
- 모든 코드 변경은 변경 전/후를 명시
- 캐시 히트 상태를 응답 마지막에 보고: [Cache: HIT/MISS, saved: N tokens]
""".strip()


# ─── Append Only 파일 쓰기 헬퍼 ───────────────────────────────────────────────
def append_only_write(filepath: Path, content: str, section_header: str = "") -> bool:
    """
    masterplan.md / mistakes.md 전용 Append Only 쓰기.
    기존 내용을 절대 변경하지 않고 파일 끝에만 추가.
    캐시 브레이크포인트 보존이 목적.
    
    Args:
        filepath: 파일 경로
        content: 추가할 내용
        section_header: 섹션 헤더 (예: "## 2026-03-10 업데이트")
    
    Returns:
        bool: 성공 여부
    """
    try:
        filepath = Path(filepath)
        
        # 기존 내용의 마지막 줄 확인 (빈 줄 중복 방지)
        existing = filepath.read_text(encoding="utf-8") if filepath.exists() else ""
        
        separator = "\n\n" if existing and not existing.endswith("\n\n") else ""
        
        if section_header:
            addition = f"{separator}---\n{section_header}\n{content}\n"
        else:
            addition = f"{separator}{content}\n"
        
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(addition)
        
        print(f"[append_only] ✅ {filepath.name}에 {len(content)}자 추가 완료 (기존 내용 보존)")
        return True
        
    except Exception as e:
        print(f"[append_only] ❌ 오류: {e}")
        return False


def append_mistake(mistake_title: str, situation: str, wrong: str, correct: str) -> bool:
    """
    mistakes.md에 새로운 실수 항목을 Append Only로 추가.
    
    Args:
        mistake_title: 실수 제목
        situation: 어떤 작업 중이었나
        wrong: 무엇을 잘못했나
        correct: 앞으로 어떻게 해야 하나
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    content = f"""## [{date_str}] {mistake_title}
- **상황:** {situation}
- **실수 내용:** {wrong}
- **올바른 방법:** {correct}"""
    
    return append_only_write(
        MISTAKES_PATH,
        content,
        section_header=""  # 내용 자체에 헤더 포함
    )


def append_masterplan_feedback(to_agent: str, feedback: str) -> bool:
    """
    master_plan.md의 Manager's Feedback 섹션에 Append Only로 피드백 추가.
    """
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"- **[{date_str}] To {to_agent}:** {feedback}"
    
    return append_only_write(
        MASTERPLAN_PATH,
        content,
        section_header=f"### 🔄 Manager Feedback ({date_str})"
    )


# ─── 캐시 통계 로거 ───────────────────────────────────────────────────────────
def log_cache_stats(
    creation_tokens: int,
    read_tokens: int,
    input_tokens: int,
    output_tokens: int,
    model: str,
    task_hint: str = ""
):
    """cache_creation_input_tokens, cache_read_input_tokens를 JSONL 파일에 기록."""
    CACHE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # 비용 절감 계산 (Claude Sonnet 기준)
    # - 일반 입력: $3/MTok
    # - 캐시 쓰기: $3.75/MTok (25% 비쌈)
    # - 캐시 읽기: $0.30/MTok (90% 절감)
    PRICE_INPUT = 3.0 / 1_000_000
    PRICE_CACHE_WRITE = 3.75 / 1_000_000
    PRICE_CACHE_READ = 0.30 / 1_000_000
    PRICE_OUTPUT = 15.0 / 1_000_000
    
    cost_without_cache = (input_tokens + creation_tokens + read_tokens) * PRICE_INPUT
    cost_with_cache = (
        input_tokens * PRICE_INPUT
        + creation_tokens * PRICE_CACHE_WRITE
        + read_tokens * PRICE_CACHE_READ
        + output_tokens * PRICE_OUTPUT
    )
    saved = cost_without_cache - cost_with_cache
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "task": task_hint,
        "tokens": {
            "input": input_tokens,
            "output": output_tokens,
            "cache_creation": creation_tokens,
            "cache_read": read_tokens,
        },
        "cost_usd": {
            "with_cache": round(cost_with_cache, 6),
            "without_cache": round(cost_without_cache, 6),
            "saved": round(saved, 6),
        },
        "cache_hit": read_tokens > 0,
    }
    
    with open(CACHE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    status = "✅ HIT" if read_tokens > 0 else "❌ MISS (캐시 생성)"
    print(f"[cache] {status} | creation={creation_tokens:,} read={read_tokens:,} | 절감=${saved:.4f}")
    return entry


# ─── Claude 클라이언트 메인 클래스 ───────────────────────────────────────────
class ClaudeClient:
    """
    Anthropic Claude API Prefix Caching 최적화 클라이언트.
    
    캐시 브레이크포인트 배치 전략:
      BP1: 시스템 프롬프트 (완전 정적)
      BP2: masterplan.md 내용 (Append Only로 앞부분 불변)
      BP3: mistakes.md 내용 (Append Only로 앞부분 불변)
      BP4: 대용량 코드 분석 시 코드 블록 (선택적)
    """
    
    def __init__(self, model: str = "claude-sonnet-4-5"):
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic 패키지가 설치되지 않았습니다. 'pip install anthropic' 실행")
        
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다")
        
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self._masterplan_cache = None
        self._mistakes_cache = None
        self._last_file_mtime = {}
    
    def _load_static_doc(self, filepath: Path) -> str:
        """정적 문서(masterplan.md, mistakes.md)를 읽어 캐시."""
        filepath = Path(filepath)
        if not filepath.exists():
            return f"[파일 없음: {filepath.name}]"
        
        current_mtime = filepath.stat().st_mtime
        cached_mtime = self._last_file_mtime.get(str(filepath), 0)
        
        if current_mtime != cached_mtime:
            content = filepath.read_text(encoding="utf-8")
            self._last_file_mtime[str(filepath)] = current_mtime
            print(f"[cache] {filepath.name} 로드 ({len(content):,}자) → 캐시 재생성 예정")
            return content
        
        # mtime 동일 = 파일 변경 없음 = 기존 캐시 유효
        if filepath == MASTERPLAN_PATH:
            return self._masterplan_cache or filepath.read_text(encoding="utf-8")
        return self._mistakes_cache or filepath.read_text(encoding="utf-8")
    
    def _build_system_with_cache(self) -> list:
        """
        Prefix Caching용 시스템 프롬프트 블록 구성.
        
        반환값: system 블록 리스트 (캐시 마킹 포함)
        BP1: SYSTEM_PROMPT_STATIC (영구 캐시)
        BP2: masterplan.md (Append Only 문서)
        BP3: mistakes.md (Append Only 문서)
        """
        masterplan_content = self._load_static_doc(MASTERPLAN_PATH)
        mistakes_content = self._load_static_doc(MISTAKES_PATH)
        
        system_blocks = [
            # BP1: 시스템 프롬프트 (완전 정적 → 최우선 캐시)
            {
                "type": "text",
                "text": SYSTEM_PROMPT_STATIC,
                "cache_control": {"type": "ephemeral"}
            },
            # BP2: masterplan.md (Append Only → 앞부분 불변 → 캐시 유지)
            {
                "type": "text",
                "text": f"=== master_plan.md ===\n{masterplan_content}",
                "cache_control": {"type": "ephemeral"}
            },
            # BP3: mistakes.md (Append Only → 앞부분 불변 → 캐시 유지)
            {
                "type": "text",
                "text": f"=== docs/ai/mistakes.md ===\n{mistakes_content}",
                "cache_control": {"type": "ephemeral"}
            },
        ]
        
        return system_blocks
    
    def chat(
        self,
        user_message: str,
        code_context: Optional[str] = None,
        task_hint: str = "",
        max_tokens: int = 4096,
    ) -> dict:
        """
        Prefix Caching이 활성화된 Claude API 호출.
        
        Args:
            user_message: 사용자 메시지
            code_context: 대용량 코드 분석 시 코드 블록 (BP4 캐시 포인트)
            task_hint: 로그용 작업 힌트
            max_tokens: 최대 출력 토큰
        
        Returns:
            dict: {
                "content": 응답 텍스트,
                "cache_stats": {creation, read, saved_usd},
                "usage": 전체 사용량
            }
        """
        # 시스템 프롬프트 구성 (BP1~BP3)
        system_blocks = self._build_system_with_cache()
        
        # 사용자 메시지 구성
        user_content = []
        
        # BP4: 대용량 코드 분석 시 코드 블록도 캐시 (선택적)
        if code_context and len(code_context) > 2000:
            user_content.append({
                "type": "text",
                "text": f"=== 분석 대상 코드 ===\n{code_context}",
                "cache_control": {"type": "ephemeral"}
            })
        elif code_context:
            user_content.append({
                "type": "text",
                "text": f"=== 분석 대상 코드 ===\n{code_context}"
            })
        
        user_content.append({
            "type": "text",
            "text": user_message
        })
        
        # API 호출 (캐시 활성화)
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_blocks,
                messages=[
                    {"role": "user", "content": user_content}
                ],
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
            )
            
            # 캐시 통계 추출
            usage = response.usage
            creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
            read = getattr(usage, "cache_read_input_tokens", 0) or 0
            
            # 로깅
            stats = log_cache_stats(
                creation_tokens=creation,
                read_tokens=read,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                model=self.model,
                task_hint=task_hint
            )
            
            content_text = response.content[0].text if response.content else ""
            
            return {
                "content": content_text,
                "cache_stats": {
                    "creation_tokens": creation,
                    "read_tokens": read,
                    "saved_usd": stats["cost_usd"]["saved"],
                    "cache_hit": read > 0,
                },
                "usage": {
                    "input": usage.input_tokens,
                    "output": usage.output_tokens,
                    "cache_creation": creation,
                    "cache_read": read,
                }
            }
            
        except anthropic.APIError as e:
            print(f"[claude_client] API 오류: {e}")
            raise
    
    def analyze_then_modify(
        self,
        analyze_prompt: str,
        code_to_analyze: str,
        task_hint: str = ""
    ) -> tuple[str, str]:
        """
        캐시 브레이크포인트 인식 2단계 처리:
        1단계 (분석): 코드 분석만 수행 (코드 블록 캐시됨)
        2단계 (수정): 1단계 분석 결과를 바탕으로 수정 지시
        
        분석/수정 단계 분리로 이전 대화의 맥락이 캐시된 상태를 유지.
        
        Returns:
            tuple[str, str]: (분석 결과, 수정 지시)
        """
        print(f"[claude_client] 📊 1단계: 분석 단계 시작 (코드 {len(code_to_analyze):,}자)")
        
        # 1단계: 분석 (코드 블록 BP4 캐시)
        analysis = self.chat(
            user_message=analyze_prompt + "\n\n[지시] 현재는 분석만 수행하고, 코드를 수정하지 마세요.",
            code_context=code_to_analyze,
            task_hint=f"{task_hint}:분석",
        )
        
        print(f"[claude_client] ✏️ 2단계: 수정 단계 시작")
        
        # 2단계: 수정 (이전 분석 결과 활용, 코드 블록 캐시 재사용)
        modification = self.chat(
            user_message=(
                f"이전 분석 결과:\n{analysis['content']}\n\n"
                "위 분석을 바탕으로 실제 코드 수정을 수행하세요."
            ),
            code_context=code_to_analyze,
            task_hint=f"{task_hint}:수정",
        )
        
        return analysis["content"], modification["content"]


# ─── 캐시 통계 리포트 함수 ────────────────────────────────────────────────────
def print_cache_report(last_n: int = 10):
    """최근 N개 API 호출의 캐시 통계를 출력."""
    if not CACHE_LOG_PATH.exists():
        print("[cache_report] 로그 파일 없음 (아직 API 호출 없음)")
        return
    
    lines = CACHE_LOG_PATH.read_text(encoding="utf-8").strip().split("\n")
    recent = [json.loads(l) for l in lines[-last_n:] if l]
    
    total_creation = sum(r["tokens"]["cache_creation"] for r in recent)
    total_read = sum(r["tokens"]["cache_read"] for r in recent)
    total_saved = sum(r["cost_usd"]["saved"] for r in recent)
    hit_rate = sum(1 for r in recent if r["cache_hit"]) / len(recent) * 100 if recent else 0
    
    print(f"\n{'='*50}")
    print(f"📊 Claude Prefix Caching 통계 (최근 {len(recent)}회)")
    print(f"{'='*50}")
    print(f"  캐시 히트율:    {hit_rate:.1f}%")
    print(f"  캐시 생성 토큰: {total_creation:,}")
    print(f"  캐시 읽기 토큰: {total_read:,}")
    print(f"  총 절감액:      ${total_saved:.4f} USD")
    print(f"{'='*50}\n")


# ─── FastAPI 엔드포인트용 래퍼 함수 ───────────────────────────────────────────
_client_instance: Optional["ClaudeClient"] = None

def get_claude_client() -> Optional["ClaudeClient"]:
    """싱글톤 패턴으로 ClaudeClient 인스턴스 반환."""
    global _client_instance
    if _client_instance is None and ANTHROPIC_AVAILABLE:
        try:
            _client_instance = ClaudeClient()
        except RuntimeError as e:
            print(f"[claude_client] 초기화 실패: {e}")
            return None
    return _client_instance


# ─── 직접 실행 시 테스트 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Claude Prefix Caching 테스트 ===")
    
    client = get_claude_client()
    if not client:
        print("ANTHROPIC_API_KEY를 .env에 설정하세요")
        exit(1)
    
    # 테스트 1: 기본 호출 (캐시 미스 - 처음 호출)
    print("\n[테스트 1] 첫 번째 호출 (캐시 MISS 예상)")
    result = client.chat(
        user_message="현재 분광 분석 그래프의 주요 문제점이 무엇인지 한 줄로 요약해.",
        task_hint="spec_graph_test"
    )
    print(f"응답: {result['content'][:100]}...")
    
    # 테스트 2: 동일한 시스템 프롬프트로 두 번째 호출 (캐시 히트 예상)
    print("\n[테스트 2] 두 번째 호출 (캐시 HIT 예상)")
    result2 = client.chat(
        user_message="H-NMR 피크-구조 매핑 구현 시 가장 중요한 점 한 줄 요약.",
        task_hint="nmr_mapping_test"
    )
    print(f"응답: {result2['content'][:100]}...")
    
    print_cache_report(last_n=5)
