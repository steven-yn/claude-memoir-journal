# Session Cache Improvement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세션 종료 시 Claude가 백그라운드에서 구조화된 요약을 생성하고, 저널 생성 시 이를 활용하여 속도를 대폭 개선한다.

**Architecture:** 2-Tier 캐시 (Level 1: 메타데이터, Level 2: Claude 구조화 요약). 훅에서 Level 1 저장 후 백그라운드로 `session_summarize.py` spawn. 저널 생성 시 Level 2가 있으면 data-analyst 스킵, 없으면 병렬 분석.

**Tech Stack:** Python 3, Claude CLI (`claude -p --model haiku`), 기존 플러그인 인프라

**Spec:** `docs/specs/2026-03-17-session-cache-improvement-design.md`

---

## File Structure

| 파일 | 유형 | 역할 |
|------|------|------|
| `scripts/session_parser.py` | 수정 | `conversation_blocks` 추출 추가 |
| `scripts/session_cache.py` | 수정 | 대화 내용 임시 저장 + 백그라운드 프로세스 spawn |
| `scripts/session_summarize.py` | 신규 | 백그라운드 요약 (claude CLI 호출, Level 2 캐시 저장) |
| `scripts/collect_sessions.py` | 수정 | `--check-summary` 플래그, Level 2 캐시 로드 |
| `scripts/journal_config.py` | 수정 | 새 설정 키 4개 추가 |
| `commands/daily.md` | 수정 | 캐시 히트/미스 분기 + 병렬 에이전트 + 병합 |
| `commands/weekly.md` | 경미 수정 | 일별 저널 우선 참조 강화 |
| `commands/monthly.md` | 경미 수정 | 주별 저널 우선 참조 강화 |
| `commands/status.md` | 수정 | Level 2 캐시 현황 표시 |

---

## Chunk 1: 데이터 추출 계층 (session_parser + session_cache)

### Task 1: session_parser.py — conversation_blocks 추출 추가

`session_parser.py`의 `parse_session_file` 함수를 확장하여, 기존 `conversation_summary` 외에 `conversation_blocks` (사용자 질문 + 어시스턴트 텍스트 응답 페어)를 추출한다.

**Files:**
- Modify: `scripts/session_parser.py:54-132`

- [ ] **Step 1: `parse_session_file`에 conversation_blocks 수집 로직 추가**

현재 `conversation_summary`는 assistant 텍스트만 최대 10개 수집한다. `conversation_blocks`는 user query + assistant response를 페어로 수집한다.

`parse_session_file` 함수 내부, `conversation_summary` 관련 변수 선언 아래에 추가:

```python
conversation_blocks: list[dict[str, str]] = []
current_user_query: str | None = None
```

`entry_type == "user"` 블록에서 `user_queries.append(text)` 다음에 추가:

```python
current_user_query = text
```

`entry_type == "assistant"` 블록 내, `elif block.get("type") == "text":` 안에서 `conversation_summary` 수집 직후에 추가:

```python
if current_user_query and text and len(text) > 50:
    conversation_blocks.append({
        "query": current_user_query[:200],
        "response": text[:500],
    })
    current_user_query = None
```

반환 딕셔너리에 추가:

```python
"conversation_blocks": conversation_blocks[:30],
```

- [ ] **Step 2: 변경 검증**

Run: `python3 -c "from session_parser import parse_session_file; print('import ok')"`
Expected: `import ok`

- [ ] **Step 3: Commit**

```bash
git add scripts/session_parser.py
git commit -m "feat: session_parser에 conversation_blocks 추출 추가"
```

---

### Task 2: session_cache.py — 대화 내용 임시 저장 + 백그라운드 spawn

Level 1 캐시 저장 후, 대화 내용을 임시 파일에 저장하고 `session_summarize.py`를 백그라운드로 실행한다.

**Files:**
- Modify: `scripts/session_cache.py:1-144`

- [ ] **Step 1: import 추가 및 상수 정의**

파일 상단 import 영역에 추가:

```python
import os
import subprocess
import tempfile
```

`CACHE_DIR` 상수 아래에 추가:

```python
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT", str(Path(__file__).parent.parent))
```

- [ ] **Step 2: 백그라운드 spawn 함수 작성**

`merge_cache` 함수 아래, `check_journal_reminder` 위에 추가:

```python
def spawn_background_summary(session_id: str, content_path: str) -> None:
    """Spawn background process to generate Level 2 summary cache."""
    try:
        from journal_config import load_config

        config = load_config()
        if not config.get("background_summary", True):
            return

        summary_file = CACHE_DIR / f"{session_id}.summary.json"
        if summary_file.exists():
            return

        min_queries = config.get("summary_min_queries", 3)
        # Quick check: read content file to count queries
        try:
            with open(content_path) as f:
                content_data = json.load(f)
            if len(content_data.get("conversation_blocks", [])) < min_queries:
                Path(content_path).unlink(missing_ok=True)
                return
        except (json.JSONDecodeError, OSError):
            return

        summarize_script = Path(PLUGIN_ROOT) / "scripts" / "session_summarize.py"
        if not summarize_script.exists():
            return

        subprocess.Popen(
            [
                "python3",
                str(summarize_script),
                "--session-id", session_id,
                "--content-path", content_path,
                "--plugin-root", PLUGIN_ROOT,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass
```

- [ ] **Step 3: main 함수에 conversation_blocks 저장 + spawn 로직 추가**

`main` 함수 내, `with open(cache_file, "w") as f:` 블록 뒤 (Level 1 캐시 저장 후), `except Exception` 앞에 추가:

```python
        # Save conversation content to temp file and spawn background summarizer
        conversation_blocks = parsed.get("conversation_blocks", [])
        if conversation_blocks:
            content_data = {
                "session_id": session_id,
                "project": cwd,
                "project_name": Path(cwd).name if cwd else "unknown",
                "git_branch": parsed["git_branch"],
                "user_queries": parsed["user_queries"],
                "files_modified": parsed["files_modified"],
                "tools_used": parsed["tools_used"],
                "token_usage": parsed["token_usage"],
                "conversation_blocks": conversation_blocks,
            }
            tmp_dir = Path(tempfile.gettempdir()) / "memoir-journal-summary"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            content_path = tmp_dir / f"{session_id}.json"
            with open(content_path, "w") as cf:
                json.dump(content_data, cf, ensure_ascii=False)
            spawn_background_summary(session_id, str(content_path))
```

- [ ] **Step 4: 변경 검증**

Run: `python3 -c "import session_cache; print('import ok')"`  (scripts/ 디렉토리에서)
Expected: `import ok`

- [ ] **Step 5: Commit**

```bash
git add scripts/session_cache.py
git commit -m "feat: session_cache에 대화 내용 임시 저장 및 백그라운드 spawn 추가"
```

---

## Chunk 2: 백그라운드 요약 스크립트 (session_summarize.py)

### Task 3: session_summarize.py 신규 생성

Claude CLI를 호출하여 세션 데이터를 구조화된 요약(Level 2 캐시)으로 변환하는 백그라운드 스크립트.

**Files:**
- Create: `scripts/session_summarize.py`

- [ ] **Step 1: 스크립트 작성**

```python
#!/usr/bin/env python3
"""Background session summarizer — generates Level 2 cache using Claude CLI.

Spawned by session_cache.py after Stop/SessionEnd hooks.
Reads extracted conversation content, calls claude CLI with data-analyst
agent instructions, and saves structured summary to cache.
"""

import argparse
import json
import signal
import subprocess
import sys
from pathlib import Path

CACHE_DIR = Path.home() / ".claude-memoir-journal" / "cache"

LEVEL2_SCHEMA = """{
  "session_id": "string",
  "project": "string",
  "summarized_at": "ISO 8601 timestamp",
  "summary": {
    "one_line": "한줄 요약 (50자 이내)",
    "topics": [
      {
        "title": "주제명",
        "category": "feature|bugfix|refactor|learning|config|devops|research",
        "description": "무엇을 했는지 2-3문장",
        "key_decisions": ["결정사항"],
        "insights": ["인사이트"],
        "difficulties": ["어려움"],
        "files_involved": ["파일 경로"]
      }
    ],
    "overall_learnings": ["세션 전체에서 배운 점"],
    "tags": ["태그"]
  }
}"""


def load_text_file(path: Path) -> str:
    """Load a text file, returning empty string on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def build_prompt(
    content_data: dict,
    analyst_prompt: str,
    guideline: str,
) -> str:
    """Compose the summarization prompt from components."""
    session_json = json.dumps(content_data, ensure_ascii=False, indent=2)

    return f"""당신은 Claude Code 세션 데이터를 분석하여 구조화된 요약을 생성하는 전문가입니다.

## 분석 지침

{analyst_prompt}

## 작성 가이드

{guideline}

## 세션 데이터

{session_json}

## 출력 지시

위 세션 데이터를 분석하여 아래 JSON 스키마에 맞는 **JSON만** 출력하세요.
마크다운 코드 블록이나 설명 없이, 순수 JSON만 출력하세요.

스키마:
{LEVEL2_SCHEMA}

중요:
- session_id와 project는 세션 데이터에서 그대로 사용
- summarized_at은 현재 시각 (ISO 8601)
- topics는 세션에서 식별된 독립적인 작업/주제별로 생성
- 세션 데이터에 근거 없는 내용은 포함하지 마세요
- 한국어로 작성하되, 기술 용어는 원어 유지
"""


def call_claude(prompt: str, model: str, timeout: int) -> str | None:
    """Call claude CLI in print mode and return the response."""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model, "--no-input"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def parse_json_response(response: str) -> dict | None:
    """Extract JSON from claude response, handling markdown code blocks."""
    text = response.strip()
    # Strip markdown code block if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def main() -> None:
    # Self-timeout: kill this process after max duration
    def timeout_handler(signum, frame):
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Background session summarizer")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--content-path", required=True)
    parser.add_argument("--plugin-root", required=True)
    args = parser.parse_args()

    plugin_root = Path(args.plugin_root)
    content_path = Path(args.content_path)

    # Load config for timeout and model
    sys.path.insert(0, str(plugin_root / "scripts"))
    try:
        from journal_config import load_config
        config = load_config()
    except Exception:
        config = {}

    timeout = config.get("summary_timeout", 120)
    model = config.get("summary_model", "haiku")

    # Set self-destruct timer
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout + 10)

    # Load content data
    if not content_path.exists():
        sys.exit(0)

    try:
        with open(content_path) as f:
            content_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        content_path.unlink(missing_ok=True)
        sys.exit(1)

    # Check if Level 2 already exists
    summary_file = CACHE_DIR / f"{args.session_id}.summary.json"
    if summary_file.exists():
        content_path.unlink(missing_ok=True)
        sys.exit(0)

    # Load agent prompt and guideline
    analyst_prompt = load_text_file(plugin_root / "agents" / "data-analyst.md")
    guideline = load_text_file(plugin_root / "rules" / "guideline.md")

    # Build and execute prompt
    prompt = build_prompt(content_data, analyst_prompt, guideline)
    response = call_claude(prompt, model, timeout)

    if not response:
        content_path.unlink(missing_ok=True)
        sys.exit(1)

    # Parse response
    summary = parse_json_response(response)
    if not summary:
        content_path.unlink(missing_ok=True)
        sys.exit(1)

    # Ensure required fields
    summary["session_id"] = args.session_id
    summary["project"] = content_data.get("project", "")

    # Save Level 2 cache
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(summary_file, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Cleanup temp file
    content_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행 권한 부여**

Run: `chmod +x scripts/session_summarize.py`

- [ ] **Step 3: import 검증**

Run: `cd scripts && python3 -c "import session_summarize; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add scripts/session_summarize.py
git commit -m "feat: 백그라운드 세션 요약 스크립트 추가 (Level 2 캐시 생성)"
```

---

## Chunk 3: 설정 및 수집 계층 (journal_config + collect_sessions)

### Task 4: journal_config.py — 새 설정 키 추가

**Files:**
- Modify: `scripts/journal_config.py:13-22`

- [ ] **Step 1: DEFAULT_CONFIG에 새 키 추가**

`DEFAULT_CONFIG` 딕셔너리에 다음 4개 항목을 추가 (`"exclude_projects"` 앞에):

```python
    "background_summary": True,
    "summary_model": "haiku",
    "summary_timeout": 120,
    "summary_min_queries": 3,
```

- [ ] **Step 2: Commit**

```bash
git add scripts/journal_config.py
git commit -m "feat: 백그라운드 요약 관련 설정 키 4개 추가"
```

---

### Task 5: collect_sessions.py — Level 2 캐시 로드 + --check-summary 플래그

`collect_sessions.py`가 Level 2 캐시를 인식하고, 저널 생성 커맨드에 캐시 상태를 전달한다.

**Files:**
- Modify: `scripts/collect_sessions.py:110-172`

- [ ] **Step 1: Level 2 캐시 로드 함수 추가**

`try_load_cache` 함수 아래에 추가:

```python
def try_load_summary(session_id: str) -> dict | None:
    """Try to load Level 2 (Claude-generated summary) cache."""
    if not validate_session_id(session_id):
        return None
    summary_file = CACHE_DIR / f"{session_id}.summary.json"
    if summary_file.exists():
        try:
            with open(summary_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None
```

- [ ] **Step 2: collect 함수에 check_summary 파라미터 추가**

`collect` 함수 시그니처 변경:

```python
def collect(start: datetime, end: datetime, exclude_projects: list[str], check_summary: bool = False) -> dict:
```

`collect` 함수 내부, 세션 반복문에서 `cached = try_load_cache(sid)` 앞에 Level 2 확인 추가:

```python
        # Try Level 2 summary first (if check_summary mode)
        if check_summary:
            summary = try_load_summary(sid)
            if summary:
                session_data = {
                    "session_id": sid,
                    "project": meta["project"],
                    "project_name": meta["project_name"],
                    "displays": meta.get("displays", []),
                    "has_summary": True,
                    "summary": summary.get("summary", {}),
                    "token_usage": cached.get("token_usage", {}) if (cached := try_load_cache(sid)) else {},
                }
                sessions.append(session_data)
                total_input += session_data["token_usage"].get("input", 0)
                total_output += session_data["token_usage"].get("output", 0)
                continue
```

기존 `cached = try_load_cache(sid)` 블록에 `has_summary` 필드 추가:

```python
        cached = try_load_cache(sid)
        if cached:
            cached["displays"] = meta.get("displays", [])
            cached["has_summary"] = False
            sessions.append(cached)
```

세션 파일 파싱 후에도 동일하게:

```python
            session_data = {
                ...
                "has_summary": False,
                ...
            }
```

- [ ] **Step 3: CLI에 --check-summary 플래그 추가**

`main` 함수의 `parser.add_argument` 영역에 추가:

```python
    parser.add_argument("--check-summary", action="store_true",
                       help="Check for Level 2 summary cache and include if available")
```

`result = collect(...)` 호출 변경:

```python
    result = collect(start, end, args.exclude, check_summary=args.check_summary)
```

- [ ] **Step 4: 검증**

Run: `cd scripts && python3 collect_sessions.py --date 2026-03-17 --check-summary`
Expected: JSON 출력 (세션이 있으면 `has_summary` 필드 포함)

- [ ] **Step 5: Commit**

```bash
git add scripts/collect_sessions.py
git commit -m "feat: collect_sessions에 Level 2 캐시 로드 및 --check-summary 플래그 추가"
```

---

## Chunk 4: 커맨드 파일 업데이트 (daily, weekly, monthly, status)

### Task 6: commands/daily.md — 캐시 히트/미스 분기 + 병렬 에이전트

저널 생성 시 Level 2 캐시가 있는 세션은 data-analyst를 스킵하고, 없는 세션만 병렬로 분석한다.

**Files:**
- Modify: `commands/daily.md`

- [ ] **Step 1: Session Data 수집을 --check-summary 모드로 변경**

기존:

```
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --date ${ARGUMENTS:-$(date +%Y-%m-%d)}`
```

변경:

```
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --date ${ARGUMENTS:-$(date +%Y-%m-%d)} --check-summary`
```

- [ ] **Step 2: Instructions 섹션의 에이전트 파이프라인 로직 변경**

기존 4단계 파이프라인 설명을 다음으로 교체:

```markdown
### 에이전트 파이프라인 (캐시 활용 + 병렬 분석)

각 단계를 **Agent 도구를 사용하여 서브에이전트로** 실행하세요. 서브에이전트는 독립된 컨텍스트에서 작업하므로 메인 컨텍스트가 보호됩니다.

**임시 작업 디렉토리**: 파이프라인 시작 전 `$TMPDIR/memoir-journal-pipeline/` 디렉토리를 생성하세요.

#### Step 0: 캐시 상태 분석

세션 데이터의 각 세션에서 `has_summary` 필드를 확인하세요:
- `has_summary: true` → Level 2 캐시가 있는 세션. `summary` 필드의 내용을 바로 사용
- `has_summary: false` → 캐시 미스. data-analyst 에이전트로 분석 필요

#### Step 1: 데이터 분석

**모든 세션이 `has_summary: true`인 경우:**
- data-analyst 단계를 **스킵**합니다
- 각 세션의 `summary` 필드를 수집하여 `$TMPDIR/memoir-journal-pipeline/1-analysis.md`에 다음 형식으로 저장:

```
## 분류 결과

### 항목 N: [topic.title]
- 유형: [topic.category]
- 관련 파일: [topic.files_involved]
- 요약: [topic.description]
- 핵심 결정: [topic.key_decisions]
- 인사이트: [topic.insights]
```

**캐시 미스가 있는 경우:**
- 캐시 미스 세션들을 **각각 독립적인 data-analyst Agent로 병렬 실행**
- 각 Agent에 해당 세션 1개의 데이터만 전달 (프롬프트에 agents/data-analyst.md 지침 포함)
- 캐시 히트 세션의 `summary` + 캐시 미스 세션의 분석 결과를 병합하여 `1-analysis.md`에 저장

#### Step 2-4: 기존 파이프라인

2. **journal-writer** — `1-analysis.md`를 읽고 저널 초안 작성. Agent 프롬프트 텍스트 첫 줄에 반드시 `ultrathink`를 포함하세요. 결과를 `$TMPDIR/memoir-journal-pipeline/2-draft.md`에 저장
3. **verifier** — `2-draft.md`를 읽고 + 원본 세션 데이터와 대조하여 완성도와 사실 정확성 검증. 결과를 `$TMPDIR/memoir-journal-pipeline/3-verified.md`에 저장
4. **editor** — `3-verified.md`를 읽고 최종 편집. Agent 프롬프트 텍스트 첫 줄에 반드시 `ultrathink`를 포함하세요. 결과를 `$TMPDIR/memoir-journal-pipeline/4-final.md`에 저장
```

각 Agent 호출 시 프롬프트에 포함할 내용은 기존과 동일.

- [ ] **Step 3: Commit**

```bash
git add commands/daily.md
git commit -m "feat: daily 커맨드에 Level 2 캐시 활용 및 병렬 분석 로직 추가"
```

---

### Task 7: commands/weekly.md — 일별 저널 우선 참조 강화

**Files:**
- Modify: `commands/weekly.md`

- [ ] **Step 1: Session Data 수집을 --check-summary 모드로 변경**

기존:

```
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --week ${ARGUMENTS:-$(date +%Y-W%V)}`
```

변경:

```
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --week ${ARGUMENTS:-$(date +%Y-W%V)} --check-summary`
```

- [ ] **Step 2: 데이터 활용 우선순위 섹션 보강**

기존 `데이터 활용 우선순위` 섹션을 다음으로 교체:

```markdown
### 데이터 활용 우선순위

1. **기존 일별 저널 파일**이 있으면 최우선 참조 — 이미 정제된 인사이트이므로 data-analyst를 거칠 필요 없음
2. 일별 저널이 없는 날짜의 세션 중 `has_summary: true` → Level 2 캐시 요약 직접 사용
3. `has_summary: false` 세션 → data-analyst Agent로 분석 (병렬 가능)

일별 저널과 Level 2 캐시로 모든 날짜가 커버되면, data-analyst 단계를 스킵하고 바로 journal-writer로 진행하세요.
```

- [ ] **Step 3: Commit**

```bash
git add commands/weekly.md
git commit -m "feat: weekly 커맨드에 Level 2 캐시 우선순위 로직 추가"
```

---

### Task 8: commands/monthly.md — 주별 저널 우선 참조 강화

**Files:**
- Modify: `commands/monthly.md`

- [ ] **Step 1: Session Data 수집을 --check-summary 모드로 변경**

기존:

```
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --month ${ARGUMENTS:-$(date +%Y-%m)}`
```

변경:

```
!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/collect_sessions.py --month ${ARGUMENTS:-$(date +%Y-%m)} --check-summary`
```

- [ ] **Step 2: 데이터 활용 우선순위 섹션 보강**

기존 `데이터 활용 우선순위` 섹션을 다음으로 교체:

```markdown
### 데이터 활용 우선순위

1. **주별 저널** → 2. **일별 저널** → 3. `has_summary: true` 세션의 Level 2 캐시 → 4. raw 세션 data-analyst 분석

상위 데이터로 모든 기간이 커버되면 하위 단계는 스킵하세요.
```

- [ ] **Step 3: Commit**

```bash
git add commands/monthly.md
git commit -m "feat: monthly 커맨드에 Level 2 캐시 우선순위 로직 추가"
```

---

### Task 9: commands/status.md — Level 2 캐시 현황 표시

**Files:**
- Modify: `commands/status.md`

- [ ] **Step 1: Level 2 Cache Status 섹션 추가**

기존 `## Cache Status` 섹션 아래에 추가:

```markdown
## Summary Cache Status (Level 2)

!`ls ~/.claude-memoir-journal/cache/*.summary.json 2>/dev/null | wc -l | tr -d ' '`
```

- [ ] **Step 2: Instructions에 Level 2 현황 안내 추가**

`3. **캐시 현황**` 항목을 다음으로 변경:

```markdown
3. **캐시 현황**: Level 1 (메타데이터) 캐시 수와 Level 2 (Claude 요약) 캐시 수를 구분하여 표시. Level 2가 Level 1보다 적으면 "요약 캐시가 아직 생성 중인 세션이 있습니다"로 안내
```

- [ ] **Step 3: Commit**

```bash
git add commands/status.md
git commit -m "feat: status 커맨드에 Level 2 캐시 현황 표시 추가"
```

---

## Chunk 5: 통합 검증

### Task 10: 전체 통합 검증

모든 변경 사항이 올바르게 동작하는지 검증한다.

- [ ] **Step 1: Python import 체인 검증**

Run:

```bash
cd scripts
python3 -c "
from session_parser import parse_session_file
from session_cache import spawn_background_summary
from collect_sessions import try_load_summary, collect
from journal_config import load_config, DEFAULT_CONFIG
assert 'background_summary' in DEFAULT_CONFIG
assert 'summary_model' in DEFAULT_CONFIG
assert 'summary_timeout' in DEFAULT_CONFIG
assert 'summary_min_queries' in DEFAULT_CONFIG
print('All imports and config keys OK')
"
```

Expected: `All imports and config keys OK`

- [ ] **Step 2: collect_sessions --check-summary 동작 확인**

Run:

```bash
cd scripts
python3 collect_sessions.py --date $(date +%Y-%m-%d) --check-summary 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for s in data.get('sessions', []):
    print(f\"  {s['session_id'][:8]}... has_summary={s.get('has_summary', 'N/A')}\")
print(f'Total: {data[\"total_sessions\"]} sessions')
"
```

Expected: 각 세션에 `has_summary` 필드가 표시됨

- [ ] **Step 3: session_summarize.py 독립 실행 검증 (dry run)**

Run:

```bash
cd scripts
python3 session_summarize.py --help
```

Expected: `usage: session_summarize.py [-h] --session-id ... --content-path ... --plugin-root ...`

- [ ] **Step 4: 최종 커밋 (필요시)**

변경 사항이 있으면 커밋:

```bash
git add -A
git commit -m "fix: 통합 검증 후 수정 사항 반영"
```
