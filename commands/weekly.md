---
description: 주별 저널 생성 - 일별 저널 기반 종합 회고
argument-hint: "[YYYY-WNN] (기본값: 이번 주)"
allowed-tools: [Read, Write, Bash, Glob, Grep]
---

# Weekly Journal Generator

## Configuration

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/journal_config.py --get`

## Session Data

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --week ${ARGUMENTS:-$(date +%Y-W%V)}`

## Existing Daily Journals

!`ls $(python3 -c "import json; c=json.load(open('$HOME/.claude-memoir-journal/config.json')) if __import__('os').path.exists('$HOME/.claude-memoir-journal/config.json') else {}; print(c.get('output_dir','~/claude-memoir-journal').replace('~','$HOME'))")/$(date +%Y)/$(date +%m)/*.md 2>/dev/null || echo "No daily journals found"`

## Instructions

위 데이터를 기반으로 주별 종합 회고 저널을 생성하세요.

### 저널 저장 경로

설정의 `output_dir` 아래 `YYYY/YYYY-WNN.md` 형태로 저장하세요.
예: `~/claude-memoir-journal/2026/2026-W11.md`

### 작성 언어

설정의 `resolved_language` 값에 해당하는 언어로 전체 저널을 작성하세요.

### 데이터 활용 우선순위

1. 기존 일별 저널 파일이 있으면 우선 참조
2. 없는 날짜는 raw 세션 데이터에서 보충

### 마크다운 구조

```markdown
---
title: "YYYY-WNN 주간 회고"
date: YYYY-MM-DD
week: YYYY-WNN
tags: [자동생성태그들]
summary: "한줄 요약"
---

# YYYY-WNN 주간 회고

## 주간 요약
(5줄 이내, 이번 주의 핵심)

## 주요 성과
- 성과 1
- 성과 2

## 프로젝트별 진행
### [프로젝트명]
- 진행 사항 요약
- 주요 변경점

## 핵심 학습
(이번 주 배운 것들, 기술적 인사이트)

## 회고
### 잘한 점
- ...
### 개선할 점
- ...

## 다음 주 계획
- [ ] ...

## 주간 통계
| 항목 | 수치 |
|------|------|
| 총 세션 수 | N |
| 활동 일수 | N |
| 총 토큰 | N |
```

### 작성 원칙

1. 일별 저널 내용을 종합하되, 단순 나열이 아닌 **패턴과 트렌드** 도출
2. 회고 섹션에서 솔직한 자기 평가 제시
3. 다음 주 계획은 이번 주 작업 흐름에서 자연스럽게 도출
