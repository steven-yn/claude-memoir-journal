#!/usr/bin/env python3
"""Background session summarizer: generates Level 2 structured summaries using Claude CLI.

Called as a detached background process by session_cache.py.
Reads conversation data from a temp file, sends it to Claude CLI for summarization,
and saves the result as a Level 2 summary cache file.

Usage: python3 session_summarize.py <session_id> <data_file_path> <plugin_root>
"""

import json
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

CACHE_DIR = Path.home() / ".claude-memoir-journal" / "cache"
LOG_FILE = CACHE_DIR / "summarize.log"
MAX_LOG_LINES = 1000

LEVEL2_SCHEMA = """\
Output ONLY valid JSON matching this schema (no markdown fences, no explanation):
{
  "one_line": "한줄 요약",
  "topics": [
    {
      "title": "주제명",
      "category": "feature|bugfix|refactor|learning|config|devops",
      "description": "무엇을 했는지 2-3문장",
      "key_decisions": ["결정사항1"],
      "insights": ["인사이트1"],
      "difficulties": ["어려움1"],
      "files_involved": ["file1.py"]
    }
  ],
  "overall_learnings": ["세션 전체에서 배운 점"],
  "tags": ["tag1", "tag2"]
}"""


def log(session_id: str, message: str) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().isoformat(timespec="seconds")
        line = f"[{ts}] session_id={session_id} {message}\n"
        with open(LOG_FILE, "a") as f:
            f.write(line)
        trim_log()
    except OSError:
        pass


def trim_log() -> None:
    try:
        if not LOG_FILE.exists():
            return
        lines = LOG_FILE.read_text().splitlines()
        if len(lines) > MAX_LOG_LINES:
            LOG_FILE.write_text("\n".join(lines[-MAX_LOG_LINES:]) + "\n")
    except OSError:
        pass


def acquire_lock(session_id: str) -> bool:
    lock_file = CACHE_DIR / f"{session_id}.summary.lock"
    if lock_file.exists():
        try:
            pid = int(lock_file.read_text().strip())
            os.kill(pid, 0)
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            lock_file.unlink(missing_ok=True)
    lock_file.write_text(str(os.getpid()))
    return True


def release_lock(session_id: str) -> None:
    lock_file = CACHE_DIR / f"{session_id}.summary.lock"
    lock_file.unlink(missing_ok=True)


def setup_timeout(timeout_seconds: int) -> None:
    if hasattr(signal, "SIGALRM"):
        def handler(signum, frame):
            raise TimeoutError("Self-timeout exceeded")
        signal.signal(signal.SIGALRM, handler)
        signal.alarm(timeout_seconds)
    else:
        def timeout_fn():
            os._exit(1)
        timer = threading.Timer(timeout_seconds, timeout_fn)
        timer.daemon = True
        timer.start()


def build_prompt(plugin_root: Path, conv_data: dict) -> str:
    parts = []

    analyst_file = plugin_root / "agents" / "data-analyst.md"
    if analyst_file.exists():
        parts.append(f"## 분석 지침\n\n{analyst_file.read_text()}")

    guideline_file = plugin_root / "rules" / "guideline.md"
    if guideline_file.exists():
        parts.append(f"## 작성 가이드\n\n{guideline_file.read_text()}")

    session_section = "## 세션 데이터\n\n"
    meta_fields = ["session_id", "project", "project_name", "user_queries", "files_modified", "tools_used", "git_branch"]
    meta = {k: conv_data[k] for k in meta_fields if k in conv_data}
    session_section += f"### 메타데이터\n```json\n{json.dumps(meta, ensure_ascii=False, indent=2)}\n```\n\n"

    blocks = conv_data.get("conversation_blocks", [])
    if blocks:
        session_section += "### 대화 내용\n\n"
        for i, block in enumerate(blocks, 1):
            session_section += f"**Q{i}**: {block['query']}\n\n**A{i}**: {block['response']}\n\n---\n\n"
    parts.append(session_section)

    parts.append(f"## 출력 형식\n\n{LEVEL2_SCHEMA}")

    return "\n\n".join(parts)


def run_claude(prompt: str, model: str, timeout: int) -> str:
    result = subprocess.run(
        ["claude", "-p", "--no-session-persistence", "--model", model, "--output-format", "text"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {result.stderr[:200]}")
    return result.stdout.strip()


def parse_summary_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1 if lines[0].startswith("```") else 0
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end])
    return json.loads(text)


def main() -> None:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <session_id> <data_file_path> <plugin_root>", file=sys.stderr)
        sys.exit(1)

    session_id = sys.argv[1]
    data_file = Path(sys.argv[2])
    plugin_root = Path(sys.argv[3])

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not acquire_lock(session_id):
        log(session_id, "status=skipped reason=lock_exists")
        sys.exit(0)

    try:
        from journal_config import load_config
        config = load_config()
        model = config.get("summary_model", "haiku")
        timeout = config.get("summary_timeout", 120)
        min_queries = config.get("summary_min_queries", 3)

        setup_timeout(timeout + 10)

        if not data_file.exists():
            log(session_id, "status=skipped reason=data_file_missing")
            return

        with open(data_file) as f:
            conv_data = json.load(f)

        if len(conv_data.get("user_queries", [])) < min_queries:
            log(session_id, "status=skipped reason=too_few_queries")
            return

        prompt = build_prompt(plugin_root, conv_data)
        raw_response = run_claude(prompt, model, timeout)
        summary_content = parse_summary_response(raw_response)

        result = {
            "session_id": session_id,
            "project": conv_data.get("project", ""),
            "project_name": conv_data.get("project_name", ""),
            "summarized_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "summary": summary_content,
        }

        summary_file = CACHE_DIR / f"{session_id}.summary.json"
        with open(summary_file, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        log(session_id, "status=success")

    except TimeoutError:
        log(session_id, "error=self_timeout")
    except json.JSONDecodeError as e:
        log(session_id, f"error=json_parse_failed detail={e}")
    except subprocess.TimeoutExpired:
        log(session_id, "error=claude_cli_timeout")
    except FileNotFoundError:
        log(session_id, "error=claude_cli_not_found")
    except Exception as e:
        log(session_id, f"error=unexpected detail={type(e).__name__}:{e}")
    finally:
        release_lock(session_id)
        if data_file.exists():
            data_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
