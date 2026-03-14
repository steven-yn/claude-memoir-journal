---
description: 일별 저널 생성 - Claude Code 세션 기반 핵심 인사이트
argument-hint: "[YYYY-MM-DD] (기본값: 오늘)"
allowed-tools: [Read, Write, Bash, Glob, Grep]
---

# Daily Journal Generator

## Configuration

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/journal_config.py --get`

## Session Data

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --date ${ARGUMENTS:-$(date +%Y-%m-%d)}`

## Instructions

위 세션 데이터와 설정을 기반으로 일별 개발 저널을 생성하세요.

### 저널 저장 경로

설정의 `output_dir`를 확인하고, `YYYY/MM/YYYY-MM-DD.md` 형태로 저장하세요.
예: `~/claude-memoir-journal/2026/03/2026-03-14.md`

경로에 `~`가 포함되어 있으면 홈 디렉토리로 확장하세요.

### 작성 언어

설정의 `resolved_language` 값에 해당하는 언어로 전체 저널을 작성하세요.
- `ko` → 한국어, `en` → English, `ja` → 日本語, etc.
- 섹션 제목, 본문, 요약 모두 해당 언어로 작성

### 마크다운 구조

```markdown
---
title: "YYYY-MM-DD 개발 일지"
date: YYYY-MM-DD
tags: [자동생성태그들]
summary: "한줄 요약"
---

# YYYY-MM-DD 개발 일지

## 오늘의 요약
(3줄 이내, 핵심만)

## 프로젝트별 작업
### [프로젝트명]
- 브랜치: feat/...
- 핵심 작업 내용 정리

## 학습한 내용
(새로 알게 된 것, 인사이트 — raw 로그가 아닌 정제된 내용)

## 해결한 문제
(문제 → 접근 → 해결 구조)

## 내일 할 일
- [ ] ...

## 통계
| 항목 | 수치 |
|------|------|
| 세션 수 | N |
| 총 토큰 | N |
```

### 작성 원칙

1. **핵심 인사이트 정제**: raw 로그 복사가 아닌, 의미 있는 내용만 추출
2. **블로그 재활용 가능**: 자연스러운 문체, 기술 블로그 포스트로 변환 가능한 수준
3. **코드 스니펫**: 설정의 `include_code_snippets`가 true이면, 핵심적인 코드만 `max_code_snippet_lines` 이내로 포함
4. **토큰 통계**: `include_token_stats`가 true이면 통계 섹션 포함
5. **태그**: `tags_auto_generate`가 true이면 작업 내용 기반 태그 자동 생성
6. **YAML frontmatter**: `blog_frontmatter`가 true이면 포함

세션 데이터가 없으면 해당 날짜에 Claude Code 세션이 없다고 알려주세요.
