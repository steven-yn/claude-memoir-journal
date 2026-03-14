---
description: 저널 현황 조회 - 최근 저널, 미작성 날짜, 캐시 현황
allowed-tools: [Bash, Read, Glob]
---

# Journal Status

## Configuration

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/journal_config.py --get`

## Recent Journals

!`find $(python3 -c "import json,os; c=json.load(open(os.path.expanduser('~/.claude-memoir-journal/config.json'))) if os.path.exists(os.path.expanduser('~/.claude-memoir-journal/config.json')) else {}; print(os.path.expanduser(c.get('output_dir','~/claude-memoir-journal')))")  -name '*.md' -type f 2>/dev/null | sort -r | head -20 || echo "No journals found"`

## Cache Status

!`ls -la ~/.claude-memoir-journal/cache/*.json 2>/dev/null | wc -l && echo "cached sessions" || echo "0 cached sessions"`

## Recent Sessions (Last 7 days)

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --week $(date +%Y-W%V) 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Sessions: {d[\"total_sessions\"]}'); print(f'Tokens: {d[\"total_tokens\"]}')" || echo "No session data available"`

## Instructions

위 정보를 기반으로 저널 현황을 보기 좋게 요약하세요:

1. **최근 저널 목록**: 파일명과 날짜
2. **미작성 날짜**: 세션은 있지만 저널이 없는 날짜 식별
3. **캐시 현황**: 캐시된 세션 수
4. **이번 주 통계**: 세션 수, 토큰 사용량

미작성 날짜가 있으면 `/journal-daily YYYY-MM-DD`로 생성할 수 있다고 안내하세요.
