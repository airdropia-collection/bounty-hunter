"""
Natural Developer Persona — text humanization layer for external git artifacts.

Closes the sync gap between the bot's internal telemetry (rich with emoji,
bot signatures, markdown tables, AI prefaces) and the external PR/commit
text that upstream maintainers see. All external text is sanitized through
this module before reaching the GitHub API.

Rules are read from ``src.config.CONFIG.NATURAL_PERSONA`` (single source
of truth). This module is the ONLY consumer of those rules — callers
never reach into the config dict directly.

Public API
~~~~~~~~~~

Sanitizers (idempotent, never raise, always return a str):
    - ``sanitize_commit_message(msg)``
    - ``sanitize_pr_title(title)``
    - ``sanitize_pr_body(body)``

Builders (construct new text from semantic inputs):
    - ``build_commit_message(kind, subject, scope=None, body=None, issue_ref=None)``
    - ``build_pr_title(subject, issue_ref=None)``
    - ``build_pr_body(what, why, how=None, issue_ref=None, testing_notes=None)``

CLI entry point:
    - ``python -m src.utils.persona --kind commit --text "fix: ..."``
    - ``python -m src.utils.persona --kind pr_title --text "..."``
    - ``python -m src.utils.persona --kind pr_body --text "..."``

Used by:
    - ``.github/workflows/submit-pr.yml`` (persona-filter step before API call)
    - Any future src/ module that emits external git text

Preserves:
    - ``polyglot_runner.py`` (untouched)
    - ``memory_registry.py`` (untouched)
    - ``telegram.py`` (internal telemetry — emoji OK, never routed here)
    - All workflow_dispatch triggers (untouched)
    - ``state.json`` persistence (untouched)
"""
from __future__ import annotations

import argparse
import re
import sys

from src.config import CONFIG
from src.utils.logger import get_logger

log = get_logger("persona")


# ──────────────────────────────────────────────────────────────────── #
# Internal helpers
# ──────────────────────────────────────────────────────────────────── #

# Match any emoji pictograph / symbol / dingbat (broad Unicode blocks).
# We compile once — performance matters because sanitize_pr_body may be
# called on long PR descriptions with many emoji.
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002700-\U000027BF"  # dingbats
    "\U0001F900-\U0001F9FF"  # supplemental symbols & pictographs
    "\U00002600-\U000026FF"  # misc symbols
    "\U0001FA70-\U0001FAFF"  # symbols & pictographs extended-A
    "]+",
    flags=re.UNICODE,
)

# Match GitHub-flavored markdown tables: a header row, a separator row
# of dashes/colons, then 1+ data rows. We strip the entire block.
_MARKDOWN_TABLE_RE = re.compile(
    r"(?:^[ \t]*\|[^\n]+\|[ \t]*\n)"            # header row
    r"(?:^[ \t]*\|[\s:|-]+\|[ \t]*\n)"           # separator row
    r"(?:^[ \t]*\|[^\n]+\|[ \t]*\n)+",           # one or more data rows
    flags=re.MULTILINE,
)

# Match leading/trailing whitespace and 3+ blank lines
_BLANK_RUN_RE = re.compile(r"\n{3,}")

# Match a markdown heading line at start of body
_LEADING_HEADING_RE = re.compile(r"^\s*#{1,6}\s+.*?\n", flags=re.MULTILINE)


def _strip_emoji(text: str) -> str:
    """Remove all emoji pictographs from ``text``."""
    return _EMOJI_RE.sub("", text)


def _strip_markdown_tables(text: str) -> str:
    """Remove GFM markdown table blocks from ``text``."""
    return _MARKDOWN_TABLE_RE.sub("", text)


def _collapse_blank_lines(text: str) -> str:
    """Collapse 3+ consecutive newlines down to exactly 2."""
    return _BLANK_RUN_RE.sub("\n\n", text).strip()


def _strip_forbidden_phrases(text: str) -> str:
    """Remove AI-typical phrases from ``text``.

    Each forbidden phrase is removed along with any trailing punctuation
    and whitespace. The search is case-insensitive. Loops until no more
    matches (idempotent against nested phrases like
    "Here is the fix: As an AI I'd be happy to").
    """
    forbidden: tuple[str, ...] = CONFIG.get_persona_rule("pr_body_forbidden_phrases") or ()
    if not forbidden:
        return text
    # Build one regex matching any forbidden phrase followed by optional
    # punctuation/whitespace. Word-boundary safe.
    pattern = r"(?i)\b(?:" + "|".join(re.escape(p) for p in forbidden) + r")\b[\s,.;:!?\-]*"
    # Loop to ensure idempotency against nested phrases
    prev = None
    out = text
    while prev != out:
        prev = out
        out = re.sub(pattern, "", out)
    return out


def _strip_forbidden_prefixes(text: str) -> str:
    """Remove markdown heading signatures and 'This PR' openers from body start."""
    forbidden_prefixes: tuple[str, ...] = CONFIG.get_persona_rule("pr_body_forbidden_prefixes") or ()
    if not forbidden_prefixes:
        return text
    out = text
    # Strip leading heading lines like "## Summary\n"
    out = _LEADING_HEADING_RE.sub("", out, count=1) if out.lstrip().startswith("#") else out
    # Strip literal forbidden prefix lines (case-insensitive) at the very start
    for prefix in forbidden_prefixes:
        if out.lstrip().lower().startswith(prefix.lower()):
            # Remove the prefix and any trailing newline
            idx = out.lower().find(prefix.lower())
            # Find end of the line containing the prefix
            line_end = out.find("\n", idx + len(prefix))
            if line_end == -1:
                out = ""
            else:
                out = out[line_end + 1 :]
            break
    return out


def _strip_signature_blocklist(text: str) -> str:
    """Remove any literal signature strings from the blocklist."""
    blocklist: tuple[str, ...] = CONFIG.get_persona_rule("signature_blocklist") or ()
    out = text
    for sig in blocklist:
        out = out.replace(sig, "")
    return out


# ──────────────────────────────────────────────────────────────────── #
# Sanitizers — idempotent, never raise
# ──────────────────────────────────────────────────────────────────── #

def sanitize_commit_message(msg: str) -> str:
    """Sanitize a commit message to natural conventional-commit style.

    Enforces:
        - No emoji, no bot signatures
        - Subject line ≤ ``commit_max_subject_length`` (default 72)
        - Body line wrap ≤ ``commit_max_body_line_length`` (default 100)
        - Lowercase, imperative mood for the subject (best-effort — we
          don't rewrite grammar, just strip AI markers)
        - No "🤖 bot:" / "AI:" prefixes

    Idempotent: ``sanitize_commit_message(sanitize_commit_message(x)) == sanitize_commit_message(x)``.
    Never raises — on unexpected input, returns the original message
    with only the safe transformations applied.
    """
    if not msg or not isinstance(msg, str):
        return ""

    # 1. Strip emoji + bot signatures from the whole message
    out = _strip_emoji(msg)
    out = _strip_signature_blocklist(out)

    # 2. Strip AI preface sentences from the subject line
    #    "Here is the fix: foo" -> "foo"
    #    "🤖 bot: Here is the fix: foo" -> "foo" (nested prefaces)
    #    Loops to ensure idempotency.
    preface_re = re.compile(
        r"^\s*(?:Here is|Below is|I have|I've|AI|Bot)[^:\n]*:\s*",
        flags=re.IGNORECASE,
    )
    # Split into subject + body
    parts = out.split("\n", 1)
    subject = parts[0]
    body = parts[1] if len(parts) > 1 else ""

    # Loop the preface stripping until stable (handles nested prefaces)
    prev_subject = None
    while prev_subject != subject:
        prev_subject = subject
        subject = preface_re.sub("", subject).strip()
    # 3. Lowercase the first word if it's an uppercase conventional-commit type
    #    "Fix: foo" -> "fix: foo"  (preserve proper nouns later in subject)
    type_match = re.match(r"^([A-Z]+)([\(:])", subject)
    if type_match:
        subject = type_match.group(1).lower() + subject[len(type_match.group(1)):]

    # 4. Enforce subject length — truncate at last word boundary
    max_subject: int = CONFIG.get_persona_rule("commit_max_subject_length") or 72
    if len(subject) > max_subject:
        truncated = subject[:max_subject]
        # Walk back to last space
        last_space = truncated.rfind(" ")
        if last_space > 20:  # don't over-truncate
            truncated = truncated[:last_space]
        subject = truncated

    # 5. Wrap body lines
    max_body_line: int = CONFIG.get_persona_rule("commit_max_body_line_length") or 100
    if body:
        wrapped_lines: list[str] = []
        for raw_line in body.split("\n"):
            if len(raw_line) <= max_body_line:
                wrapped_lines.append(raw_line)
            else:
                # Soft-wrap long lines at word boundaries
                words = raw_line.split(" ")
                current = ""
                for w in words:
                    if current and len(current) + 1 + len(w) > max_body_line:
                        wrapped_lines.append(current)
                        current = w
                    else:
                        current = f"{current} {w}".strip()
                if current:
                    wrapped_lines.append(current)
        body = "\n".join(wrapped_lines)

    # 6. Recombine + collapse blank runs
    out = subject if not body else f"{subject}\n\n{body.lstrip()}"
    out = _collapse_blank_lines(out)
    return out


def sanitize_pr_title(title: str) -> str:
    """Sanitize a PR title to natural developer style.

    Strips:
        - ``[BOUNTY $X]`` / ``[$X USD]`` prefixes
        - Leading emoji and "AI:" / "Bot:" prefixes
        - "Here is the fix:" preface sentences
        - Trailing ``(bot)`` suffixes
        - Bot signature strings

    Enforces:
        - Max length ``pr_title_max_length`` (default 80)

    Preserves:
        - Issue references like "(#123)" / "closes #456"
        - Proper nouns and original case (after stripping prefixes)
    """
    if not title or not isinstance(title, str):
        return ""

    out = title

    # 1. Apply each strip pattern from the centralized config
    strip_patterns: tuple[str, ...] = CONFIG.get_persona_rule("pr_title_strip_patterns") or ()
    for pat in strip_patterns:
        out = re.sub(pat, "", out, flags=re.IGNORECASE).strip()

    # 2. Strip emoji + signatures
    out = _strip_emoji(out)
    out = _strip_signature_blocklist(out)

    # 3. Strip leading AI preface: "Here is the fix for the bug: <real title>"
    #    Loop to handle nested prefaces like "🤖 bot: Here is the fix: <title>".
    preface_re = re.compile(
        r"^\s*(?:Here is|Below is|I have|I've)\b[^:\n]*:\s*",
        flags=re.IGNORECASE,
    )
    prev = None
    while prev != out:
        prev = out
        out = preface_re.sub("", out).strip()

    # 4. Collapse internal whitespace
    out = re.sub(r"\s+", " ", out).strip()

    # 5. Enforce max length — truncate at last word boundary, preserve trailing (#N) if possible
    max_len: int = CONFIG.get_persona_rule("pr_title_max_length") or 80
    if len(out) > max_len:
        # Try to preserve a trailing issue ref like " (#123)"
        ref_match = re.search(r"\s*\(#\d+\)$", out)
        ref_suffix = ref_match.group(0) if ref_match else ""
        if ref_suffix:
            main = out[: -len(ref_suffix)]
            budget = max_len - len(ref_suffix)
            if budget > 20:
                truncated = main[:budget]
                last_space = truncated.rfind(" ")
                if last_space > 20:
                    truncated = truncated[:last_space]
                out = truncated + ref_suffix
        else:
            truncated = out[:max_len]
            last_space = truncated.rfind(" ")
            if last_space > 20:
                truncated = truncated[:last_space]
            out = truncated

    return out


def sanitize_pr_body(body: str) -> str:
    """Sanitize a PR body to natural developer prose.

    Strips:
        - Markdown table blocks (template signature)
        - AI preface phrases ("As an AI", "Here is the", "I'd be happy to", etc.)
        - Markdown heading prefixes at body start ("## Summary", "## Description")
        - "This PR" / "This pull request" opener sentences
        - All emoji and bot signature strings

    Enforces:
        - Max length ``pr_body_max_length`` (default 2000 chars)

    Preserves:
        - Code blocks (```` ``` ```` fenced) — we don't touch their contents
        - Issue references (``closes #123``, ``fixes #456``)
        - Natural prose with paragraph breaks
    """
    if not body or not isinstance(body, str):
        return ""

    out = body

    # 1. Protect fenced code blocks from later transformations
    code_blocks: list[str] = []
    def _stash_code(m: re.Match[str]) -> str:
        code_blocks.append(m.group(0))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"
    out = re.sub(
        r"```[\s\S]*?```|`[^`\n]+`",
        _stash_code,
        out,
    )

    # 2. Strip markdown tables
    if CONFIG.get_persona_rule("pr_body_strip_markdown_tables"):
        out = _strip_markdown_tables(out)

    # 3. Strip emoji
    if CONFIG.get_persona_rule("pr_body_strip_emoji"):
        out = _strip_emoji(out)

    # 4. Strip bot signatures
    out = _strip_signature_blocklist(out)

    # 5. Strip forbidden AI phrases (sentence-level)
    out = _strip_forbidden_phrases(out)

    # 6. Strip leading heading / "This PR" opener
    out = _strip_forbidden_prefixes(out)

    # 7. Restore code blocks
    for i, block in enumerate(code_blocks):
        out = out.replace(f"\x00CODEBLOCK{i}\x00", block)

    # 8. Collapse blank-line runs + trim
    out = _collapse_blank_lines(out)

    # 9. Enforce max length — hard truncate at paragraph boundary if needed
    max_len: int = CONFIG.get_persona_rule("pr_body_max_length") or 2000
    if len(out) > max_len:
        # Find the last paragraph break before max_len
        truncated = out[:max_len]
        last_break = max(
            truncated.rfind("\n\n"),
            truncated.rfind("\n"),
        )
        if last_break > max_len // 2:
            truncated = truncated[:last_break]
        out = truncated.rstrip() + "\n\n(truncated)"

    return out


# ──────────────────────────────────────────────────────────────────── #
# Builders — construct new text from semantic inputs
# ──────────────────────────────────────────────────────────────────── #

def build_commit_message(
    kind: str,
    subject: str,
    scope: str | None = None,
    body: str | None = None,
    issue_ref: int | None = None,
) -> str:
    """Build a conventional commit message.

    Format: ``<kind>(<scope>): <subject>``
            optional body paragraphs
            optional "Refs #<issue_ref>"

    Args:
        kind: One of ``CONFIG.NATURAL_PERSONA["commit_types"]``
              (fix, feat, chore, docs, refactor, test, perf, build, ci, style).
        subject: Imperative-mood description, lowercase first word
                 (e.g., "resolve TTL metric background goroutine leak").
        scope: Optional scope (e.g., "metrics", "auth", "api").
        body: Optional multi-paragraph body explaining why (not what).
        issue_ref: Optional GitHub issue number to reference.

    Returns:
        A sanitized commit message string.

    Raises:
        ValueError: If ``kind`` is not in the allowed commit_types.
    """
    allowed: tuple[str, ...] = CONFIG.get_persona_rule("commit_types") or ()
    if kind not in allowed:
        raise ValueError(
            f"commit kind '{kind}' not in allowed types {allowed}"
        )

    # Build subject line
    head = kind if not scope else f"{kind}({scope})"
    # Strip trailing period from subject
    subject = subject.rstrip(".").strip()
    msg = f"{head}: {subject}"

    # Append body
    if body:
        body = body.strip()
        if body:
            msg = f"{msg}\n\n{body}"

    # Append issue ref
    if issue_ref:
        msg = f"{msg}\n\nRefs #{issue_ref}"

    return sanitize_commit_message(msg)


def build_pr_title(
    subject: str,
    issue_ref: int | None = None,
) -> str:
    """Build a natural PR title.

    Format: ``<subject>`` or ``<subject> (#<issue_ref>)``

    The subject should be a short imperative phrase describing the change
    (e.g., "Prevent TTL metric goroutine leak under high load").
    """
    subject = subject.strip().rstrip(".")
    if issue_ref:
        title = f"{subject} (#{issue_ref})"
    else:
        title = subject
    return sanitize_pr_title(title)


def build_pr_body(
    what: str,
    why: str,
    how: str | None = None,
    issue_ref: int | None = None,
    testing_notes: str | None = None,
) -> str:
    """Build a natural PR description.

    Produces a short prose PR body in a professional open-source tone.
    No markdown headings, no tables, no emoji. The description explains
    the *what* and the *why* — the *how* is optional and only included
    if the implementation isn't obvious from the diff.

    Args:
        what: One or two sentences describing the change.
        why: One or two sentences explaining the motivation (bug, perf,
             feature request, etc.).
        how: Optional short note on the implementation approach.
        issue_ref: Optional GitHub issue number ("Closes #N").
        testing_notes: Optional short note on how the change was verified.

    Returns:
        A sanitized PR body string.
    """
    paragraphs: list[str] = []

    what = what.strip()
    why = why.strip()
    if what:
        paragraphs.append(what)
    if why:
        paragraphs.append(why)
    if how and how.strip():
        paragraphs.append(how.strip())
    if testing_notes and testing_notes.strip():
        paragraphs.append(testing_notes.strip())

    body = "\n\n".join(paragraphs)

    if issue_ref:
        body = f"{body}\n\nCloses #{issue_ref}"

    return sanitize_pr_body(body)


# ──────────────────────────────────────────────────────────────────── #
# CLI — used by .github/workflows/submit-pr.yml to filter inputs
# ──────────────────────────────────────────────────────────────────── #

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="persona",
        description="Natural Developer Persona filter for external git artifacts.",
    )
    p.add_argument(
        "--kind",
        required=True,
        choices=["commit", "pr_title", "pr_body"],
        help="What kind of text to sanitize.",
    )
    p.add_argument(
        "--text",
        required=True,
        help="The raw text to sanitize. Read from stdin if '--text -' is given.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON {original, sanitized, changed} for workflow consumption.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # Allow stdin: --text -
    if args.text == "-":
        raw = sys.stdin.read()
    else:
        raw = args.text

    sanitizers = {
        "commit": sanitize_commit_message,
        "pr_title": sanitize_pr_title,
        "pr_body": sanitize_pr_body,
    }
    sanitizer = sanitizers[args.kind]
    cleaned = sanitizer(raw)
    changed = cleaned != raw

    if args.json:
        import json
        print(json.dumps({
            "original": raw,
            "sanitized": cleaned,
            "changed": changed,
            "kind": args.kind,
        }, indent=2))
    else:
        print(cleaned)

    return 0


if __name__ == "__main__":
    sys.exit(main())
