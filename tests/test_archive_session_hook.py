"""CLAUDE-BETA-LAUNCH-FINAL-001 §D：`/clear` session-history hook 的可重現
harness——`.claude/hooks/archive_session.py` 在真實的暫存 git repo（bare
origin ＋ clone）上端到端執行，驗證：

- session → /clear → exactly one 新 archive；第二次 /clear 再多 exactly one；
  同一個 payload 重跑不重複（idempotent resume）。
- 不依賴 master：在任意已存在於 origin 的 branch 上都照常 commit＋push。
- 絕不建立 branch、絕不切換 branch（HEAD 所在 branch 前後一致、origin 的
  branch 集合前後一致）。
- origin 上沒有這條 branch → 不 push、明確失敗（exit 1），只留本地 commit。
- detached HEAD → 不 commit（避免孤兒 commit）、明確失敗，檔案留在
  working tree，下一次在 branch 上 /clear 時被找回。
- 卡在其他 branch 上（root cause：推到已 merge 的 branch）的 archive，下一次
  /clear 時以獨立的 recover commit 帶回目前 branch。
- push 被拒 → 明確失敗，不假裝成功。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "archive_session.py"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="需要 git")


def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout.strip()


@pytest.fixture
def repos(tmp_path: Path):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", "-b", "master", str(origin)],
                   check=True, capture_output=True)
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    git(work, "config", "user.name", "Test")
    git(work, "config", "user.email", "test@example.com")
    git(work, "checkout", "-b", "master")
    hook_dir = work / ".claude" / "hooks"
    hook_dir.mkdir(parents=True)
    shutil.copy(HOOK, hook_dir / "archive_session.py")
    (work / "README").write_text("x\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "init")
    git(work, "push", "-u", "origin", "master")
    return origin, work


class Transcript:
    """最小的 Claude Code transcript jsonl：OWNER／Claude 對話＋ /clear 邊界。"""

    def __init__(self, path: Path, session_id: str):
        self.path = path
        self.session_id = session_id
        self.n = 0
        path.write_text("")

    def _append(self, rec: dict) -> None:
        self.n += 1
        rec.setdefault("uuid", f"u{self.n}")
        rec.setdefault("sessionId", self.session_id)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def say(self, owner: str, claude: str, ts: str) -> None:
        self._append({"type": "user", "timestamp": ts,
                      "message": {"role": "user", "content": owner}})
        self._append({"type": "assistant", "timestamp": ts,
                      "message": {"role": "assistant",
                                  "content": [{"type": "text", "text": claude}]}})

    def clear(self, ts: str) -> None:
        self._append({"type": "user", "timestamp": ts, "message": {
            "role": "user",
            "content": "<command-name>/clear</command-name>\n"
                       "<command-message>clear</command-message>\n"
                       "<command-args></command-args>"}})


def run_hook(work: Path, transcript: Transcript) -> subprocess.CompletedProcess:
    payload = {"session_id": transcript.session_id,
               "transcript_path": str(transcript.path), "cwd": str(work),
               "permission_mode": "default", "hook_event_name": "SessionEnd",
               "reason": "clear"}
    return subprocess.run(
        ["python3", str(work / ".claude" / "hooks" / "archive_session.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env={**os.environ, "SESSION_HISTORY_TZ": "Asia/Taipei"})


def archives(repo: Path, ref: str = "HEAD") -> list[str]:
    out = git(repo, "ls-tree", "-r", "--name-only", ref, "--", "session-history", check=False)
    return sorted(out.splitlines())


def remote_heads(origin: Path) -> set[str]:
    return set(git(origin, "for-each-ref", "--format=%(refname:short)", "refs/heads").split())


def test_each_clear_archives_exactly_one_file_and_reruns_do_not_duplicate(repos, tmp_path):
    origin, work = repos
    t = Transcript(tmp_path / "t.jsonl", "sess-aaaa1111")
    t.say("第一段問題", "第一段回答", "2026-09-28T01:00:00Z")

    r = run_hook(work, t)
    assert r.returncode == 0, r.stderr
    first = archives(work)
    assert len(first) == 1
    assert archives(origin, "master") == first                   # 真的推上去了

    rerun = run_hook(work, t)                                     # 同一個 payload 重跑
    assert rerun.returncode == 0, rerun.stderr
    assert archives(work) == first

    t.clear("2026-09-28T01:05:00Z")
    t.say("第二段問題", "第二段回答", "2026-09-28T02:00:00Z")
    r2 = run_hook(work, t)
    assert r2.returncode == 0, r2.stderr
    second = archives(work)
    assert len(second) == 2 and set(first) < set(second)
    new = (work / (set(second) - set(first)).pop()).read_text()
    assert "第二段問題" in new and "第一段問題" not in new
    assert "session: sess-aaaa1111" in new                       # session identity
    assert "2026-09-28 10:00" in new                             # 台灣時間 timestamp
    assert archives(origin, "master") == second
    assert int(git(work, "rev-list", "--count", "HEAD")) == 3    # init + 兩次 archive


def test_works_on_any_existing_branch_without_creating_or_switching_branches(repos, tmp_path):
    origin, work = repos
    git(work, "checkout", "-b", "claude/some-ephemeral-x1y2")
    git(work, "push", "-u", "origin", "claude/some-ephemeral-x1y2")
    heads_before = remote_heads(origin)
    t = Transcript(tmp_path / "t.jsonl", "sess-bbbb2222")
    t.say("問", "答", "2026-09-28T03:00:00Z")

    r = run_hook(work, t)
    assert r.returncode == 0, r.stderr
    assert git(work, "rev-parse", "--abbrev-ref", "HEAD") == "claude/some-ephemeral-x1y2"
    assert remote_heads(origin) == heads_before
    assert len(archives(origin, "claude/some-ephemeral-x1y2")) == 1
    assert archives(origin, "master") == []                      # 不偷推 master


def test_branch_missing_on_origin_is_never_created(repos, tmp_path):
    origin, work = repos
    git(work, "checkout", "-b", "local-only")
    heads_before = remote_heads(origin)
    t = Transcript(tmp_path / "t.jsonl", "sess-cccc3333")
    t.say("問", "答", "2026-09-28T04:00:00Z")

    r = run_hook(work, t)
    assert r.returncode == 1
    assert "does not exist and this hook never creates branches" in r.stderr
    assert remote_heads(origin) == heads_before
    assert len(archives(work)) == 1                              # 本地 commit 還在


def test_detached_head_commits_nothing_and_the_next_clear_recovers_it(repos, tmp_path):
    origin, work = repos
    git(work, "checkout", "--detach")
    t = Transcript(tmp_path / "t.jsonl", "sess-dddd4444")
    t.say("detached 時的對話", "答", "2026-09-28T05:00:00Z")

    r = run_hook(work, t)
    assert r.returncode == 1
    assert "detached HEAD" in r.stderr
    assert archives(work) == []
    leftover = list((work / "session-history").glob("*.md"))
    assert len(leftover) == 1                                    # 沒遺失，留在 working tree

    git(work, "checkout", "master")
    t.clear("2026-09-28T05:05:00Z")
    t.say("回到 branch 之後", "答", "2026-09-28T06:00:00Z")
    r2 = run_hook(work, t)
    assert r2.returncode == 0, r2.stderr
    assert "recovered:" in r2.stderr
    assert len(archives(origin, "master")) == 2
    subjects = git(work, "log", "--format=%s", "-2").splitlines()
    assert subjects[1] == "session history: recover 1 stranded archive(s)"
    assert subjects[0].startswith("session history: ")


def test_archive_stranded_on_a_merged_branch_is_carried_forward(repos, tmp_path):
    """Root cause 重現：archive 被推到一條已經 merge 完、之後沒人再用的
    branch。下一次在別的 branch 上 /clear，要把它帶回來——用 `git show`，
    不 checkout 那條 branch。"""
    origin, work = repos
    git(work, "checkout", "-b", "feature/done")
    git(work, "push", "-u", "origin", "feature/done")
    t1 = Transcript(tmp_path / "t1.jsonl", "sess-eeee5555")
    t1.say("在舊 branch 上的對話", "答", "2026-09-28T07:00:00Z")
    assert run_hook(work, t1).returncode == 0
    stranded = archives(work)
    assert archives(origin, "master") == []                      # 卡在 feature/done

    git(work, "checkout", "master")
    t2 = Transcript(tmp_path / "t2.jsonl", "sess-ffff6666")
    t2.say("新 session", "答", "2026-09-28T08:00:00Z")
    r = run_hook(work, t2)
    assert r.returncode == 0, r.stderr
    assert git(work, "rev-parse", "--abbrev-ref", "HEAD") == "master"
    on_master = archives(origin, "master")
    assert len(on_master) == 2 and set(stranded) <= set(on_master)

    # 再 /clear 一次：已經帶回來的不會再被「找回」第二次。
    t2.clear("2026-09-28T08:05:00Z")
    t2.say("第二段", "答", "2026-09-28T09:00:00Z")
    r2 = run_hook(work, t2)
    assert r2.returncode == 0, r2.stderr
    assert "recovered:" not in r2.stderr
    assert len(archives(origin, "master")) == 3


def test_rejected_push_fails_loudly(repos, tmp_path):
    origin, work = repos
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(origin), str(other)], check=True, capture_output=True)
    git(other, "config", "user.name", "Other")
    git(other, "config", "user.email", "other@example.com")
    (other / "README").write_text("changed elsewhere\n")
    git(other, "commit", "-am", "remote moved on")
    git(other, "push", "origin", "master")

    t = Transcript(tmp_path / "t.jsonl", "sess-gggg7777")
    t.say("問", "答", "2026-09-28T10:00:00Z")
    r = run_hook(work, t)
    assert r.returncode == 1
    assert "FAIL: git push failed" in r.stderr
    assert "ARCHIVED" not in r.stderr


def test_non_clear_reasons_are_ignored(repos, tmp_path):
    _, work = repos
    t = Transcript(tmp_path / "t.jsonl", "sess-hhhh8888")
    t.say("問", "答", "2026-09-28T11:00:00Z")
    payload = {"session_id": t.session_id, "transcript_path": str(t.path),
               "cwd": str(work), "reason": "logout"}
    r = subprocess.run(["python3", str(work / ".claude" / "hooks" / "archive_session.py")],
                       input=json.dumps(payload), capture_output=True, text=True)
    assert r.returncode == 0
    assert archives(work) == []
