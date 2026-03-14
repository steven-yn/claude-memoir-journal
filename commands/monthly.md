---
description: 월별 저널 생성 - 주별 저널 기반 월간 리뷰
argument-hint: "[YYYY-MM] (기본값: 이번 달)"
allowed-tools: [Read, Write, Bash, Glob, Grep]
---

# Monthly Journal Generator

## Configuration

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/journal_config.py --get`

## Session Data

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --month ${ARGUMENTS:-$(date +%Y-%m)}`

## Existing Weekly Journals

!`ls $(python3 -c "import json; c=json.load(open('$HOME/.claude-memoir-journal/config.json')) if __import__('os').path.exists('$HOME/.claude-memoir-journal/config.json') else {}; print(c.get('output_dir','~/claude-memoir-journal').replace('~','$HOME'))")/$(date +%Y)/*.md 2>/dev/null || echo "No weekly journals found"`

## Existing Daily Journals

!`ls $(python3 -c "import json; c=json.load(open('$HOME/.claude-memoir-journal/config.json')) if __import__('os').path.exists('$HOME/.claude-memoir-journal/config.json') else {}; print(c.get('output_dir','~/claude-memoir-journal').replace('~','$HOME'))")/$(date +%Y)/$(date +%m)/*.md 2>/dev/null || echo "No daily journals found"`

## Instructions

위 데이터를 기반으로 월간 리뷰 저널을 생성하세요.

### 저널 저장 경로

설정의 `output_dir` 아래 `YYYY/YYYY-MM.md` 형태로 저장하세요.
예: `~/claude-memoir-journal/2026/2026-03.md`

### 작성 언어

설정의 `resolved_language` 값에 해당하는 언어로 전체 저널을 작성하세요.

### 데이터 활용 우선순위

1. 주별 저널 → 2. 일별 저널 → 3. raw 세션 데이터

### 마크다운 구조

```markdown
---
title: "YYYY-MM 월간 리뷰"
date: YYYY-MM-DD
month: YYYY-MM
tags: [자동생성태그들]
summary: "한줄 요약"
---

# YYYY-MM 월간 리뷰

## 월간 요약
(5-7줄, 이번 달의 핵심 성과와 방향)

## 주요 성과 TOP 5
1. ...
2. ...

## 프로젝트별 월간 진행
### [프로젝트명]
- 월초 상태 → 월말 상태
- 주요 마일스톤

## 기술 성장 트렌드
(이번 달 기술적으로 성장한 영역, 새로 익힌 기술/패턴)

## 핵심 학습 TOP 5
1. ...

## 회고
### 목표 달성도
- 달성한 것
- 미달성/이월된 것

### 잘한 점
- ...

### 개선할 점
- ...

## 다음 달 방향
- [ ] ...

## 월간 통계 대시보드
| 항목 | 수치 |
|------|------|
| 총 세션 수 | N |
| 활동 일수 | N |
| 총 토큰 | N |
| 가장 활발한 프로젝트 | ... |
```

### 작성 원칙

1. 월 단위 **큰 그림**과 **성장 트렌드**에 집중
2. 주별 데이터를 단순 합산이 아닌, 흐름과 패턴으로 분석
3. 다음 달 방향은 이번 달 회고에서 자연스럽게 도출
