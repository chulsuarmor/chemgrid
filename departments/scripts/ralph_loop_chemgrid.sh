#!/bin/bash
# ============================================================
# Ralph Loop v4 — ChemGrid Harness-over-Harness Trigger-Based Orchestration
# ============================================================
# 사용법: bash departments/scripts/ralph_loop_chemgrid.sh
# 중지: touch departments/scripts/STOP_LOOP
# ============================================================
# v4 변경: 10분 타이머 → 트리거 기반, 3-에이전트 체제, 2계층 감사
# ============================================================

WATCHDOG_INTERVAL=1800  # 30분 watchdog (작업 없을 때만)
COOLDOWN=10             # 트리거 시 최소 쿨다운 (초)
MAX_TURNS=150           # 감사 포함 증가
LOG_DIR="/c/chemgrid/departments/scripts/logs"
mkdir -p "$LOG_DIR"

CT_PROMPT='당신은 ChemGrid의 Control Tower(최종 관리자)입니다. 모델: Opus 4.6.

## 🚨 절대 규칙: 직접 구현 금지
코드 작성, 파일 생성(.md 제외), 스크립트 실행을 절대 하지 마십시오.
모든 구현은 Agent 도구(model: "opus")로 중간관리자를 spawn하여 위임합니다.

## 초기화
1. C:\chemgrid\departments\master_plan.md 읽기 — §10 Command Dispatch Table
2. C:\chemgrid\departments\ARCHITECTURE.md 읽기 — 트리거 기반 프로토콜
3. C:\chemgrid\docs\ai\mistakes.md 읽기 — 반복 실수 방지

## 트리거 기반 순찰 사이클

### Step 1: 부서 상태 스캔
12개 부서의 context_list.md를 순회하며 상태 확인:
- 🔴 PENDING: 새 작업 대기 중 → MM spawn 필요
- 📤 SUBMIT: 상신 대기 중 → 전문 감사팀 spawn 필요
- ✅ AUDIT_PASS: 감사 통과 → 최종 감사 또는 CT 보고

### Step 2: 작업 디스패치
PENDING이 있는 부서에 대해 Agent(model: "opus", run_in_background: true)로 MM을 spawn합니다.
MM spawn 시 프롬프트에 반드시 포함:
- 해당 부서 CLAUDE.md 경로
- PENDING 태스크 내용
- "직접 코딩 금지. Agent로 기획자(P)를 spawn하고, 완료 후 검수자(R)를 spawn하십시오."
- "검수자 PASS 후 상신 보고서(📤 SUBMIT)를 context_note.md에 작성하십시오."

### Step 3: 감사 디스패치
📤 SUBMIT이 있는 부서에 대해:
1. 해당 부서의 전문 감사팀(audit_professional_{domain}) spawn
2. 전문 감사 PASS → 최종 감사팀(audit_final) spawn
3. 최종 감사 PASS → master_plan.md §10 업데이트

### Step 4: 반려 처리
감사 FAIL 시:
1. 감사 피드백을 해당 부서 context_list.md에 🔴 PENDING으로 기록
2. 해당 부서 MM을 재spawn (최대 3회)

### Step 5: 문서 업데이트 + exit
- master_plan.md §10 디스패치 테이블 업데이트
- mistakes.md에 새 패턴 추가 (발견 시)
- 모든 처리 완료 후 즉시 exit (컨텍스트 클리어)

## 종료
절대 대화를 길게 이어가지 마십시오. 환각 방지를 위해 반드시 exit.'

LOOP_COUNT=0

while true; do
    LOOP_COUNT=$((LOOP_COUNT + 1))
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$LOG_DIR/ralph_chemgrid_${TIMESTAMP}.log"

    echo "========================================" | tee -a "$LOG_FILE"
    echo "[Ralph Loop v4] Cycle #${LOOP_COUNT} at $(date)" | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"

    # Run Control Tower
    cd /c/chemgrid
    claude --dangerously-skip-permissions \
        -p "$CT_PROMPT" \
        --max-turns "$MAX_TURNS" \
        --model "claude-opus-4-6" \
        2>&1 | tee -a "$LOG_FILE"

    EXIT_CODE=$?
    echo "[Ralph Loop v4] CT exited with code $EXIT_CODE at $(date)" | tee -a "$LOG_FILE"

    # Check stop signal
    if [ -f "/c/chemgrid/departments/scripts/STOP_LOOP" ]; then
        echo "[Ralph Loop v4] STOP_LOOP detected. Exiting." | tee -a "$LOG_FILE"
        rm -f "/c/chemgrid/departments/scripts/STOP_LOOP"
        break
    fi

    # Trigger-based: check for PENDING or SUBMIT items
    PENDING_COUNT=$(grep -rl "PENDING\|SUBMIT" /c/chemgrid/departments/dept_*/context_list.md 2>/dev/null | wc -l)

    if [ "$PENDING_COUNT" -gt 0 ]; then
        echo "[Ralph Loop v4] $PENDING_COUNT depts have work. Restarting after cooldown." | tee -a "$LOG_FILE"
        sleep "$COOLDOWN"
    else
        echo "[Ralph Loop v4] No pending work. Watchdog sleep ${WATCHDOG_INTERVAL}s..." | tee -a "$LOG_FILE"
        sleep "$WATCHDOG_INTERVAL"
    fi
done

echo "[Ralph Loop v4] Loop terminated after $LOOP_COUNT cycles."
