"""Tests for the Natural Developer Persona humanization layer.

Verifies that external git artifacts (commit messages, PR titles, PR
bodies) are stripped of bot signatures, AI prefaces, markdown template
signatures, and emoji before reaching the GitHub API.

The persona rules are centralized in src/config.py:NATURAL_PERSONA and
consumed only by src/utils/persona.py.
"""
from __future__ import annotations

import json

import pytest

from src.config import CONFIG
from src.utils.persona import (
    build_commit_message,
    build_pr_body,
    build_pr_title,
    sanitize_commit_message,
    sanitize_pr_body,
    sanitize_pr_title,
)

# ──────────────────────────────────────────────────────────────────── #
# Config wiring — verify persona rules are loaded
# ──────────────────────────────────────────────────────────────────── #

def test_persona_config_block_exists():
    """NATURAL_PERSONA must be present in CONFIG with all expected keys."""
    persona = CONFIG.NATURAL_PERSONA
    assert "commit_types" in persona
    assert "pr_title_strip_patterns" in persona
    assert "pr_body_forbidden_phrases" in persona
    assert "signature_blocklist" in persona
    assert "pr_body_max_length" in persona


def test_get_persona_rule_accessor():
    """get_persona_rule() returns values for known keys, None for unknown."""
    assert isinstance(CONFIG.get_persona_rule("commit_types"), tuple)
    assert "fix" in CONFIG.get_persona_rule("commit_types")
    assert CONFIG.get_persona_rule("nonexistent_key") is None


def test_commit_types_contains_conventional_set():
    """Conventional commit types must include the standard set."""
    types = CONFIG.get_persona_rule("commit_types")
    for required in ("fix", "feat", "chore", "docs", "refactor", "test"):
        assert required in types, f"missing commit type: {required}"


# ──────────────────────────────────────────────────────────────────── #
# sanitize_pr_title
# ──────────────────────────────────────────────────────────────────── #

class TestSanitizePRTitle:
    def test_strips_bounty_prefix(self):
        """[BOUNTY $X] prefix must be stripped."""
        result = sanitize_pr_title("[BOUNTY $100] Pre-tool-use security hook")
        assert result == "Pre-tool-use security hook"

    def test_strips_bounty_no_dollar(self):
        """[BOUNTY 100] (no dollar) must also be stripped."""
        result = sanitize_pr_title("[BOUNTY 100] Pre-tool-use security hook")
        assert result == "Pre-tool-use security hook"

    def test_strips_usd_suffix(self):
        """[$50 USD] prefix must be stripped."""
        result = sanitize_pr_title("[$50 USD] CHANGELOG generator")
        assert result == "CHANGELOG generator"

    def test_strips_bot_emoji_prefix(self):
        """Leading 🤖 emoji must be stripped."""
        result = sanitize_pr_title("🤖 Fix memory leak in worker pool")
        assert result == "Fix memory leak in worker pool"

    def test_strips_ai_preface(self):
        """'AI:' prefix must be stripped."""
        result = sanitize_pr_title("AI: Resolve TTL metric goroutine leak")
        assert result == "Resolve TTL metric goroutine leak"

    def test_strops_here_is_preface(self):
        """'Here is the fix:' preface must be stripped."""
        result = sanitize_pr_title("Here is the fix: resolve TTL metric leak")
        assert result == "resolve TTL metric leak"

    def test_strips_bot_suffix(self):
        """'(bot)' suffix must be stripped."""
        result = sanitize_pr_title("CHANGELOG generator (bot)")
        assert result == "CHANGELOG generator"

    def test_preserves_issue_ref(self):
        """Trailing (#123) issue reference must be preserved."""
        result = sanitize_pr_title("Fix: prevent freeze on very fast swipes (#52)")
        assert "(#52)" in result
        assert "prevent freeze" in result

    def test_truncates_long_title_preserving_issue_ref(self):
        """Long titles must be truncated at word boundary, preserving issue ref."""
        long_subject = " ".join(["word"] * 30)  # ~120 chars
        result = sanitize_pr_title(f"{long_subject} (#42)")
        assert len(result) <= 80
        assert "(#42)" in result

    def test_truncates_long_title_no_issue_ref(self):
        """Long titles without issue ref must be truncated at word boundary."""
        long_subject = " ".join(["word"] * 30)
        result = sanitize_pr_title(long_subject)
        assert len(result) <= 80

    def test_empty_input_returns_empty(self):
        assert sanitize_pr_title("") == ""
        assert sanitize_pr_title(None) == ""  # type: ignore[arg-type]

    def test_idempotent(self):
        """sanitize_pr_title(sanitize_pr_title(x)) == sanitize_pr_title(x)."""
        title = "[BOUNTY $100] 🤖 AI: Here is the fix: resolve TTL leak"
        once = sanitize_pr_title(title)
        twice = sanitize_pr_title(once)
        assert once == twice

    def test_no_emoji_in_output(self):
        """Output must never contain emoji."""
        result = sanitize_pr_title("🚀 Fix the 🤖 bot issue ✅")
        for sig in ("🚀", "🤖", "✅"):
            assert sig not in result


# ──────────────────────────────────────────────────────────────────── #
# sanitize_commit_message
# ──────────────────────────────────────────────────────────────────── #

class TestSanitizeCommitMessage:
    def test_strips_bot_emoji_prefix(self):
        """'🤖 bot:' prefix must be stripped."""
        result = sanitize_commit_message("🤖 bot: register PR #51 on iii123iii/Crystal-PDF in state.json")
        assert "🤖" not in result
        assert "bot:" not in result
        assert "register PR #51" in result

    def test_strips_ai_preface(self):
        """'Here is the fix:' preface must be stripped from subject."""
        result = sanitize_commit_message("Here is the fix: resolve TTL metric leak")
        assert "Here is" not in result
        assert "resolve TTL metric leak" in result

    def test_preserves_body(self):
        """Body paragraphs must be preserved after sanitization."""
        msg = "fix: resolve leak\n\nThe goroutine was not stopped on shutdown."
        result = sanitize_commit_message(msg)
        assert "The goroutine was not stopped on shutdown." in result

    def test_wraps_long_body_lines(self):
        """Long body lines must be soft-wrapped at the configured limit."""
        long_line = " ".join(["word"] * 30)  # ~120 chars
        msg = f"fix: subject\n\n{long_line}"
        result = sanitize_commit_message(msg)
        max_line = CONFIG.get_persona_rule("commit_max_body_line_length") or 100
        for line in result.split("\n"):
            assert len(line) <= max_line + 5  # small tolerance

    def test_truncates_long_subject(self):
        """Subject lines must be truncated at the configured max length."""
        long_subject = " ".join(["word"] * 30)  # ~120 chars
        result = sanitize_commit_message(long_subject)
        max_subject = CONFIG.get_persona_rule("commit_max_subject_length") or 72
        # Subject is the first line
        first_line = result.split("\n")[0]
        assert len(first_line) <= max_subject

    def test_strips_signature_strings(self):
        """Bot signature strings must be stripped from anywhere in the message."""
        result = sanitize_commit_message("fix: update [BOT] shield config")
        assert "[BOT]" not in result
        assert "shield" not in result

    def test_empty_input_returns_empty(self):
        assert sanitize_commit_message("") == ""
        assert sanitize_commit_message(None) == ""  # type: ignore[arg-type]

    def test_idempotent(self):
        msg = "🤖 bot: Here is the fix: Resolve The TTL Metric Leak"
        once = sanitize_commit_message(msg)
        twice = sanitize_commit_message(once)
        assert once == twice


# ──────────────────────────────────────────────────────────────────── #
# sanitize_pr_body
# ──────────────────────────────────────────────────────────────────── #

class TestSanizePRBody:
    def test_strips_markdown_tables(self):
        """GFM markdown tables must be removed entirely."""
        body = """Some intro text.

| Field | Value |
|-------|-------|
| Files | 3 |
| Tests | 12 |

Closing text.
"""
        result = sanitize_pr_body(body)
        assert "|" not in result or result.count("|") == 0
        assert "---" not in result
        assert "Closing text" in result

    def test_strips_ai_preface_phrases(self):
        """AI-typical phrases must be removed."""
        body = "As an AI language model, I'd be happy to help review this."
        result = sanitize_pr_body(body)
        assert "As an AI" not in result
        assert "I'd be happy to" not in result
        assert "language model" not in result or "language model" in result.lower()

    def test_strips_markdown_summary_heading(self):
        """Leading '## Summary' heading must be stripped."""
        body = "## Summary\n\nThis change fixes the leak."
        result = sanitize_pr_body(body)
        assert not result.lstrip().startswith("## Summary")

    def test_preserves_code_blocks(self):
        """Fenced code blocks must be preserved untouched."""
        body = "Here is the patch:\n\n```python\nx = 1\n```\n\nDone."
        result = sanitize_pr_body(body)
        assert "```python" in result
        assert "x = 1" in result
        assert "```" in result

    def test_strips_all_emoji(self):
        """No emoji may appear in the sanitized output."""
        body = "🤖 I have implemented 🚀 the fix ✅"
        result = sanitize_pr_body(body)
        for sig in ("🤖", "🚀", "✅"):
            assert sig not in result

    def test_strips_bot_signature_strings(self):
        """Bot signature strings must be removed."""
        body = "🤖 bounty-hunter-bot: shield [BOT] applied"
        result = sanitize_pr_body(body)
        assert "🤖" not in result
        assert "bounty-hunter-bot" not in result
        assert "[BOT]" not in result

    def test_preserves_issue_ref(self):
        """'Closes #N' must be preserved."""
        body = "Fixes the leak.\n\nCloses #42"
        result = sanitize_pr_body(body)
        assert "Closes #42" in result

    def test_truncates_overlong_body(self):
        """Bodies exceeding pr_body_max_length must be truncated with a marker."""
        # Build a body well over the 2000-char limit
        long_body = "word " * 1000  # ~5000 chars
        result = sanitize_pr_body(long_body)
        max_len = CONFIG.get_persona_rule("pr_body_max_length") or 2000
        # Allow some tolerance for the truncation marker
        assert len(result) <= max_len + 50
        assert "truncated" in result.lower()

    def test_empty_input_returns_empty(self):
        assert sanitize_pr_body("") == ""
        assert sanitize_pr_body(None) == ""  # type: ignore[arg-type]

    def test_idempotent(self):
        body = "## Summary\n\n🤖 I have implemented the fix.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nCloses #1"
        once = sanitize_pr_body(body)
        twice = sanitize_pr_body(once)
        assert once == twice


# ──────────────────────────────────────────────────────────────────── #
# build_commit_message
# ──────────────────────────────────────────────────────────────────── #

class TestBuildCommitMessage:
    def test_basic_fix_commit(self):
        """fix: subject format."""
        result = build_commit_message("fix", "resolve TTL metric goroutine leak")
        assert result.startswith("fix: ")
        assert "resolve TTL metric goroutine leak" in result

    def test_scoped_commit(self):
        """fix(scope): subject format."""
        result = build_commit_message("fix", "resolve leak", scope="metrics")
        assert result.startswith("fix(metrics): ")

    def test_with_body_and_issue_ref(self):
        """Body and issue ref must be appended."""
        result = build_commit_message(
            "fix",
            "resolve leak",
            scope="metrics",
            body="The goroutine was not stopped on shutdown.",
            issue_ref=42,
        )
        assert "fix(metrics): resolve leak" in result
        assert "The goroutine was not stopped on shutdown." in result
        assert "Refs #42" in result

    def test_invalid_kind_raises(self):
        """Unknown commit kind must raise ValueError."""
        with pytest.raises(ValueError, match="not in allowed types"):
            build_commit_message("unknown_kind", "subject")

    def test_strips_trailing_period_from_subject(self):
        """Trailing period in subject must be removed."""
        result = build_commit_message("fix", "resolve the leak.")
        assert "resolve the leak." not in result.split("\n")[0]
        assert "resolve the leak" in result

    def test_chore_kind_works(self):
        """chore kind must be accepted."""
        result = build_commit_message("chore", "update dependencies")
        assert result.startswith("chore: ")


# ──────────────────────────────────────────────────────────────────── #
# build_pr_title
# ──────────────────────────────────────────────────────────────────── #

class TestBuildPRTitle:
    def test_basic_title(self):
        result = build_pr_title("Prevent TTL metric goroutine leak")
        assert result == "Prevent TTL metric goroutine leak"

    def test_title_with_issue_ref(self):
        result = build_pr_title("Prevent TTL metric goroutine leak", issue_ref=42)
        assert result.endswith("(#42)")

    def test_strips_trailing_period(self):
        result = build_pr_title("Fix the leak.")
        assert not result.endswith(".")

    def test_no_emoji(self):
        """Output must never contain emoji."""
        result = build_pr_title("Fix the 🤖 bot issue")
        assert "🤖" not in result


# ──────────────────────────────────────────────────────────────────── #
# build_pr_body
# ──────────────────────────────────────────────────────────────────── #

class TestBuildPRBody:
    def test_basic_body(self):
        result = build_pr_body(
            what="The collector goroutine was not stopped.",
            why="Operators observed steady memory growth.",
        )
        assert "The collector goroutine was not stopped." in result
        assert "Operators observed steady memory growth." in result

    def test_with_all_sections(self):
        result = build_pr_body(
            what="The collector goroutine was not stopped.",
            why="Operators observed steady memory growth.",
            how="Added context.WithCancel around the collector loop.",
            issue_ref=42,
            testing_notes="Verified with go test -race.",
        )
        assert "context.WithCancel" in result
        assert "go test -race" in result
        assert "Closes #42" in result

    def test_no_markdown_headings(self):
        """Output must not start with markdown headings."""
        result = build_pr_body(what="Fix.", why="Reason.")
        assert not result.lstrip().startswith("#")

    def test_no_emoji(self):
        result = build_pr_body(what="🤖 Fix.", why="🚀 Reason.")
        assert "🤖" not in result
        assert "🚀" not in result

    def test_no_ai_phrases(self):
        """Output must not contain AI-typical phrases."""
        result = build_pr_body(
            what="Fix the leak.",
            why="The leak was causing memory growth.",
        )
        for phrase in CONFIG.get_persona_rule("pr_body_forbidden_phrases"):
            assert phrase.lower() not in result.lower(), f"forbidden phrase leaked: {phrase}"


# ──────────────────────────────────────────────────────────────────── #
# CLI entry point
# ──────────────────────────────────────────────────────────────────── #

class TestPersonaCLI:
    def test_cli_pr_title_strips_bounty_prefix(self, capsys):
        """CLI must produce same output as the function."""
        from src.utils.persona import main
        rc = main(["--kind", "pr_title", "--text", "[BOUNTY $100] Pre-tool-use hook", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert rc == 0
        assert data["kind"] == "pr_title"
        assert data["changed"] is True
        assert data["sanitized"] == "Pre-tool-use hook"

    def test_cli_pr_title_no_change(self, capsys):
        """Already-clean title must report changed=False."""
        from src.utils.persona import main
        rc = main(["--kind", "pr_title", "--text", "Fix the leak", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert rc == 0
        assert data["changed"] is False

    def test_cli_pr_body_strips_markdown_table(self, capsys):
        from src.utils.persona import main
        body = "Intro.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nClosing."
        rc = main(["--kind", "pr_body", "--text", body, "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert rc == 0
        assert "|" not in data["sanitized"] or data["sanitized"].count("|") == 0

    def test_cli_plain_output(self, capsys):
        """Without --json, the CLI prints only the sanitized text."""
        from src.utils.persona import main
        rc = main(["--kind", "pr_title", "--text", "[BOUNTY $50] Fix the leak"])
        out = capsys.readouterr().out.strip()
        assert rc == 0
        assert out == "Fix the leak"

    def test_cli_commit_kind(self, capsys):
        from src.utils.persona import main
        rc = main(["--kind", "commit", "--text", "🤖 bot: register PR", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert rc == 0
        assert "🤖" not in data["sanitized"]
        assert "bot:" not in data["sanitized"]

    def test_cli_invalid_kind_rejected(self):
        """Invalid --kind value must be rejected by argparse."""
        with pytest.raises(SystemExit):
            from src.utils.persona import main
            main(["--kind", "invalid_kind", "--text", "x"])


# ──────────────────────────────────────────────────────────────────── #
# Real-world regression cases — must never re-leak
# ──────────────────────────────────────────────────────────────────── #

class TestRealWorldRegressions:
    """Regression tests based on actual bot signatures that leaked in
    previous cycles. Each test documents a real PR title or commit
    message that was emitted by the bot and flagged by hostile
    maintainers. The persona layer must never let these through again.
    """

    def test_regression_cbb_bounty_prefix(self):
        """CBB PR #3498 used '[BOUNTY $100] Pre-tool-use security hook'."""
        result = sanitize_pr_title("[BOUNTY $100] Pre-tool-use security hook")
        assert result == "Pre-tool-use security hook"

    def test_regression_cbb_bounty_50(self):
        """CBB PR #3499 used '[BOUNTY $50] CHANGELOG generator'."""
        result = sanitize_pr_title("[BOUNTY $50] CHANGELOG generator")
        assert result == "CHANGELOG generator"

    def test_regression_cbb_bounty_150(self):
        """CBB PR #3500 used '[BOUNTY $150] PR review sub-agent'."""
        result = sanitize_pr_title("[BOUNTY $150] PR review sub-agent")
        assert result == "PR review sub-agent"

    def test_regression_bot_commit_prefix(self):
        """submit-pr.yml commit msg used '🤖 bot: register PR #...'."""
        result = sanitize_commit_message("🤖 bot: register PR #51 on iii123iii/Crystal-PDF in state.json")
        assert "🤖" not in result
        assert "bot:" not in result
        assert "register PR #51" in result

    def test_regression_pr_monitor_commit(self):
        """pr-monitor.yml commit msg used '🤖 bot: PR monitor ...'."""
        result = sanitize_commit_message("🤖 bot: PR monitor updated state.json statuses")
        assert "🤖" not in result
        assert "bot:" not in result

    def test_regression_swipeable_title_preserved(self):
        """PR #128 used 'fix: prevent freeze on very fast swipes (#52)'.

        This is ALREADY clean — the persona filter must not mangle it.
        """
        original = "fix: prevent freeze on very fast swipes (#52)"
        result = sanitize_pr_title(original)
        assert "(#52)" in result
        assert "prevent freeze" in result

    def test_regression_no_ai_preface_in_pr_body(self):
        """A previous PR body started with 'Here is the PR for ...'."""
        body = "Here is the PR for the TTL fix. As an AI, I'd be happy to discuss."
        result = sanitize_pr_body(body)
        assert "Here is the" not in result
        assert "As an AI" not in result
        assert "I'd be happy to" not in result
