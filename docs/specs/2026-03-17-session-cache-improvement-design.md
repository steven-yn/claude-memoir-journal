# Session Cache Improvement Design

> 세션 캐시 개선: 2-Tier 캐시 + 백그라운드 요약 + 파이프라인 병렬화

## 배경

### 문제
- 저널 생성(`/journal-daily` 등) 시 data-analyst 에이전트가 raw 세션 데이터를 처음부터 분석하므로 시간이 오래 걸림
- 현재 캐시(`session_cache.py`)는 메타데이터(쿼리 목록, 도구 카운트, 수정 파일)만 저장하여 분석 단계를 단축시키지 못함

### 목표
- 세션 종료 시 Claude가 백그라운드에서 구조화된 요약을 사전 생성
- 저널 생성 시 사전 요약이 있으면 data-analyst를 스킵하여 속도 대폭 개선
- 사전 요약이 없는 세션은 병렬 분석으로 합리적인 속도 유지

## 설계

### 1. 2-Tier 캐시 구조

캐시를 두 단계로 분리한다.

**Level 1 (즉시, Python)**: 기존과 동일한 메타데이터 캐시
- 훅에서 10초 내 완료
- 파일: `~/.claude-memoir-journal/cache/{session_id}.json`
- 포맷: 기존 `session_cache.py` 출력과 동일

**Level 2 (백그라운드, Claude)**: 구조화된 요약 캐시
- 백그라운드에서 Claude(Haiku)가 생성
- 파일: `~/.claude-memoir-journal/cache/{session_id}.summary.json`
- 포맷:

```json
{
  "session_id": "uuid",
  "project": "/path/to/project",
  "project_name": "project-name",
  "summarized_at": "2026-03-17T15:30:00+09:00",
  "summary": {
    "one_line": "한줄 요약",
    "topics": [
      {
        "title": "주제명",
        "category": "feature|bugfix|refactor|learning|config|devops",
        "description": "무엇을 했는지 2-3문장",
        "key_decisions": ["결정사항1", "결정사항2"],
        "insights": ["인사이트1"],
        "difficulties": ["어려움1"],
        "files_involved": ["file1.py", "file2.ts"]
      }
    ],
    "overall_learnings": ["세션 전체에서 배운 점"],
    "tags": ["tag1", "tag2"]
  }
}
```

**저널 생성 시 우선순위:**
1. Level 2 있음 → 바로 사용 (data-analyst 스킵)
2. Level 1만 있음 → 병렬 에이전트로 요약 생성
3. 캐시 없음 → 세션 파싱 + 요약 (병렬)

### 2. 훅 + 백그라운드 요약 파이프라인

세션 종료 시 실행되는 흐름:

```
Session End (Stop / /clear)
    ↓
Hook → session_cache.py (10초 내 완료)
    ├─ 1. 메타데이터 추출 (Level 1 캐시 저장) ← 기존과 동일
    ├─ 2. 대화 내용 추출 (conversation_blocks)
    ├─ 3. 추출 내용을 임시 파일로 저장
    └─ 4. session_summarize.py를 백그라운드로 spawn (nohup &)
              ↓ (detached, 타임아웃 없음)
         session_summarize.py:
           ├─ 임시 파일에서 대화 내용 읽기
           ├─ 프롬프트 조합 (data-analyst + guideline + 세션 데이터 + 출력 포맷)
           ├─ echo "프롬프트" | claude -p --model haiku (stdin 파이프)
           ├─ 응답을 Level 2 캐시로 저장
           └─ 임시 파일 정리
```

**에이전트 + 지침 연동:**

`session_summarize.py`는 프롬프트를 다음 순서로 조합한다:

1. `agents/data-analyst.md` — 분석 에이전트 지침
2. `rules/guideline.md` — 문서 작성 가이드
3. 추출된 세션 대화 내용 — `conversation_blocks`
4. 출력 포맷 지정 — Level 2 JSON 스키마

이를 통해:
- data-analyst 에이전트를 수정하면 캐시 요약에도 자동 반영
- `guideline.md`의 원칙(누락 없음, 인사이트 중심 등)이 캐시에도 적용
- 저널 생성 시 data-analyst를 다시 돌리지 않아도 동일한 품질 보장

**대화 내용 추출 범위** (session_parser.py의 `parse_session_file` 확장):
- `user_queries`: 기존과 동일 (최대 20개)
- `conversation_blocks`: 새로 추가 — 사용자 질문 + 어시스턴트 텍스트 응답을 페어로 추출 (도구 호출 결과 제외)
  - 최대 30개 페어
  - 각 query 최대 200자, 각 response 최대 500자로 절삭
  - 50자 미만의 짧은 응답은 제외

**프롬프트 전달 방식:**

조합된 프롬프트가 OS argument length limit을 초과할 수 있으므로, `claude` CLI 호출 시 프롬프트를 stdin으로 파이프한다:

```
echo "프롬프트" | claude -p --model haiku
```

**동시 실행 방지:**

Stop 훅과 SessionEnd 훅이 거의 동시에 발생할 수 있다. 같은 session_id에 대해 두 개의 백그라운드 프로세스가 충돌하지 않도록:
- `session_summarize.py` 시작 시 lock 파일(`{session_id}.summary.lock`)을 생성
- lock 파일이 이미 존재하면 즉시 종료
- 완료 또는 실패 시 lock 파일 삭제

**에러 로깅:**

백그라운드 프로세스의 실패를 진단할 수 있도록 `~/.claude-memoir-journal/cache/summarize.log`에 에러를 append한다:

```
[2026-03-17T15:30:00] session_id=abc123 error=claude_cli_timeout
```

로그 파일은 최대 1000줄을 유지하고, 초과 시 오래된 줄부터 삭제한다.

### 3. 저널 생성 파이프라인 개선

**현재 (순차, 모든 세션 raw 처리):**
```
collect_sessions.py → data-analyst → journal-writer → verifier → editor
```

**개선 (캐시 활용 + 병렬):**
```
collect_sessions.py --check-summary
    ↓
세션별 캐시 확인
    ├─ Level 2 있음 → 바로 수집
    ├─ Level 1만 있음 ─┐
    └─ 캐시 없음 ──────┤
                        ↓
              병렬 data-analyst 에이전트
              (세션별 독립 실행)
                        ↓
         전체 요약 병합 (merge)
                        ↓
              journal-writer → verifier → editor
```

**일별 / 주별 / 월별 차별화:**

| 유형 | 우선 입력 | 폴백 시 |
|------|----------|---------|
| 일별 | 해당 날짜 세션들의 Level 2 캐시 | 캐시 미스 세션은 병렬 data-analyst |
| 주별 | 일별 저널 파일들 | 일별 저널 없는 날짜 → Level 2 캐시 → 병렬 data-analyst |
| 월별 | 주별 저널 파일들 | 주별 저널 없는 주 → 일별 저널 → Level 2 캐시 → 병렬 data-analyst |

주별/월별도 하위 저널이 없어서 세션 데이터로 폴백할 때 Level 2 캐시를 동일하게 활용한다.

**병렬 처리 상세 (캐시 미스 시):**
```
세션 A (캐시 없음) ──→ Agent 1: data-analyst ──┐
세션 B (캐시 없음) ──→ Agent 2: data-analyst ──┤── merge ──→ journal-writer
세션 C (Level 2)   ──→ 캐시에서 직접 로드 ─────┘
```

### 4. 폴백 전략

**폴백 체인:**
```
Level 2 캐시 있음? ──yes──→ 사용
       │ no
Level 1 캐시 있음? ──yes──→ 저널 생성 시 data-analyst 실행
       │ no
세션 JSONL 존재?   ──yes──→ 파싱 + data-analyst 실행
       │ no
       └──→ 해당 세션 스킵, 경고 출력
```

어떤 상황에서도 저널 생성이 중단되지 않는다.

**`/clear` 후 재실행:**

`/clear` 후 동일 session_id로 세션이 계속될 수 있다. 이 경우:
- Level 1 캐시는 `merge_cache`로 기존과 새 데이터를 병합 (기존 동작)
- Level 2 캐시는 기존 파일을 삭제하고, 병합된 Level 1 데이터를 기반으로 재생성

**백그라운드 요약 실패 케이스:**

| 실패 상황 | 처리 |
|----------|------|
| `claude` CLI 없음/인증 만료 | Level 1만 저장, 에러 로그 기록 |
| 자체 타임아웃 초과 | 프로세스 종료, Level 1으로 폴백 |
| 응답이 JSON 파싱 불가 | Level 1만 유지, 다음 저널 생성 시 재분석 |
| 세션이 너무 짧음 (`summary_min_queries` 미만) | 요약 스킵 |

**자체 타임아웃:**

`session_summarize.py`는 `signal.SIGALRM`을 사용하여 `summary_timeout` + 10초 후 자동 종료한다. claude CLI의 `timeout` 파라미터와 별개로, 프로세스 전체가 무한히 걸리는 것을 방지한다.

### 5. 설정 추가

`config.json`에 다음 항목을 추가한다:

| 키 | 기본값 | 설명 |
|----|--------|------|
| `background_summary` | `true` | 백그라운드 요약 활성화 여부 |
| `summary_model` | `"haiku"` | 요약에 사용할 모델 |
| `summary_timeout` | `120` | 백그라운드 요약 타임아웃(초) |
| `summary_min_queries` | `3` | 이 이상의 쿼리가 있는 세션만 요약 |

## 변경 대상 파일

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `scripts/session_parser.py` | 수정 | `parse_session_file`에 `conversation_blocks` 추출 추가 |
| `scripts/session_cache.py` | 수정 | 대화 내용 임시 파일 저장, 백그라운드 프로세스 spawn |
| `scripts/session_summarize.py` | 신규 | 백그라운드 요약 스크립트 (claude CLI 호출, lock, 로깅, 타임아웃) |
| `scripts/collect_sessions.py` | 수정 | `--check-summary` 플래그 추가, Level 2 캐시 로드 |
| `scripts/journal_config.py` | 수정 | 새 설정 키 추가 |
| `commands/daily.md` | 수정 | 캐시 히트/미스 분기, 병렬 에이전트, 병합 로직 |
| `commands/weekly.md` | 수정 | 일별 저널 + Level 2 캐시 우선 참조 로직 |
| `commands/monthly.md` | 수정 | 주별 저널 + Level 2 캐시 우선 참조 로직 |
| `commands/status.md` | 수정 | Level 2 캐시 현황 표시 |
| `hooks/hooks.json` | 확인 | 기존 훅 유지 (session_cache.py가 백그라운드 spawn 담당) |
| `agents/data-analyst.md` | 확인 | 기존 유지, 백그라운드 요약에서도 재활용 |
