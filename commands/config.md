---
description: 저널 설정 조회/수정
argument-hint: "[show|set key value]"
allowed-tools: [Bash]
---

# Journal Configuration

## Current Config

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/journal_config.py --get`

## Instructions

사용자의 요청에 따라 설정을 조회하거나 수정하세요.

### 사용법

- 인자 없음 또는 `show`: 현재 설정 표시 (위에 이미 로드됨)
- `set key value`: 설정값 변경

### 설정 변경 시

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/journal_config.py --set <key> <value>
```

### 사용 가능한 설정 키

| 키 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `output_dir` | string | `~/claude-memoir-journal` | 저널 저장 경로 |
| `language` | string | `auto` | 작성 언어 (auto/ko/en/ja 등) |
| `include_token_stats` | bool | `true` | 토큰 통계 포함 여부 |
| `include_code_snippets` | bool | `true` | 코드 스니펫 포함 여부 |
| `max_code_snippet_lines` | int | `10` | 스니펫 최대 줄 수 |
| `blog_frontmatter` | bool | `true` | YAML frontmatter 포함 여부 |
| `tags_auto_generate` | bool | `true` | 태그 자동 생성 여부 |
| `exclude_projects` | list | `[]` | 제외할 프로젝트 경로 (JSON 배열) |

인자가 `$ARGUMENTS`이면 위 표를 보여주고, `set`으로 시작하면 해당 설정을 변경하세요.
