---
description: 월별 저널 생성 - 주별 저널 기반 월간 리뷰
argument-hint: "[YYYY-MM] (기본값: 이번 달)"
allowed-tools: [Read, Write, Bash, Glob, Grep]
---

# Monthly Journal Generator

## Configuration

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/journal_config.py --get`

## Session Data

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --month ${ARGUMENTS:-$(date +%Y-%m)} --check-summary`

## Existing Weekly Journals

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/find_journals.py --weekly $(echo ${ARGUMENTS:-$(date +%Y-%m)} | cut -d'-' -f1)`

## Existing Daily Journals

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/find_journals.py --daily ${ARGUMENTS:-$(date +%Y-%m)}`

## Instructions

<!-- ultrathink: 월간 데이터를 깊이 분석하여 성장 흐름과 큰 그림을 도출합니다 -->

**세션 데이터가 없는 경우**: 위 세션 데이터의 `total_sessions`가 0이고 주별/일별 저널도 없으면, 해당 달에 Claude Code 세션이 없다고 사용자에게 알리고 파이프라인을 실행하지 마세요.

위 데이터를 기반으로 아래 에이전트 파이프라인을 실행하여 월간 저널을 생성하세요.

### 에이전트 파이프라인 (서브에이전트 격리 실행)

각 단계를 **Agent 도구를 사용하여 서브에이전트로** 실행하세요. 서브에이전트는 독립된 컨텍스트에서 작업하므로 메인 컨텍스트가 보호됩니다.

**임시 작업 디렉토리**: 파이프라인 시작 전 `$TMPDIR/memoir-journal-pipeline/` 디렉토리를 생성하세요. 각 단계의 출력을 이 디렉토리에 파일로 저장하고, 다음 단계의 서브에이전트가 해당 파일을 읽도록 합니다.

1. **data-analyst** — Agent 도구로 실행. 세션 데이터 + 기존 주별/일별 저널 내용을 프롬프트에 포함하여 독립 항목으로 분류. 결과를 `$TMPDIR/memoir-journal-pipeline/1-analysis.md`에 저장
2. **journal-writer** — Agent 도구로 실행. `1-analysis.md`를 읽고 + 아래 마크다운 구조/설정을 포함하여 저널 초안 작성. 주별 데이터를 단순 합산이 아닌 **성장 흐름과 큰 그림**으로 종합할 것을 지시. Agent 프롬프트 텍스트 첫 줄에 반드시 `ultrathink`를 포함하세요. 결과를 `$TMPDIR/memoir-journal-pipeline/2-draft.md`에 저장
3. **verifier** — Agent 도구로 실행. `2-draft.md`를 읽고 + 원본 세션 데이터와 대조하여 완성도(누락 검토)와 사실 정확성을 검증. 문제가 있으면 수정한 최종본을, 없으면 원본 그대로 `$TMPDIR/memoir-journal-pipeline/3-verified.md`에 저장
4. **editor** — Agent 도구로 실행. `3-verified.md`를 읽고 + 작성 언어 설정을 포함하여 최종 편집. Agent 프롬프트 텍스트 첫 줄에 반드시 `ultrathink`를 포함하세요. 결과를 `$TMPDIR/memoir-journal-pipeline/4-final.md`에 저장

각 Agent 호출 시 프롬프트에 포함할 내용:
- 해당 에이전트의 역할 설명 (agents/ 디렉토리 참조)
- 읽어야 할 입력 파일 경로
- 출력을 저장할 파일 경로
- 원본 세션 데이터가 필요한 단계(3)는 세션 데이터도 프롬프트에 포함

파이프라인 완료 후, `4-final.md`의 내용을 저널 파일로 저장하세요.

### 저널 저장 경로

설정의 `output_dir` 아래 `YYYY/YYYY-MM.md` 형태로 저장하세요.
예: `~/claude-memoir-journal/2026/2026-03.md`

### 작성 언어

설정의 `resolved_language` 값에 해당하는 언어로 전체 저널을 작성하세요.

### 데이터 활용 우선순위

1. 주별 저널 → 2. 일별 저널 → 3. Level 2 캐시 (`has_summary: true`인 세션의 `summary_data`) → 4. data-analyst 분석

### 마크다운 구조

```markdown
---
title: "YYYY-MM 월간 회고"
date: YYYY-MM-DD
month: YYYY-MM
tags: [자동생성태그들]
summary: "한줄 요약"
---

# YYYY-MM 월간 회고

## 이번 달 요약
(한 달을 관통하는 핵심 흐름과 방향)

## 주요 성과
(이번 달 이룬 것들, 의미 있었던 결과물)

## 성장과 변화
(이번 달 새로 배운 것, 달라진 점, 넓어진 시야)

## 회고

### Keep (잘한 점)
- ...

### Problem (아쉬운 점)
- ...

### Try (시도해볼것)
- ... (상상해서 채울 필요 없음. 쓸말이 없으면 빈칸으로 둘것)

### Action Plan (목표)
- ... (상상해서 채울 필요 없음. 쓸말이 없으면 빈칸으로 둘것)

## 월간 통계
| 항목 | 수치 |
|------|------|
| 총 세션 수 | N |
| 활동 일수 | N |
| 총 토큰 | N |
```
