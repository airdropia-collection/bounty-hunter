"""
Capability Matrix — Cognitive evaluation gate for polyglot bounty targeting.

Evaluates whether the bot can successfully implement and self-heal a solution
for a given bounty issue based on:
  1. Language/runtime compatibility
  2. Complexity assessment
  3. Available toolchain (pytest, go test, cargo test, npm test)
  4. Historical success rate from agent_memory.json

Confidence threshold: 80% (per agent.md §0 strategic gatekeeper rule).
If confidence >= 80%, target is cleared for acquisition.
If confidence < 80%, target is flagged for manual review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.utils.logger import get_logger

log = get_logger("capability_matrix")

# ──────────────────────────────────────────────────────────────────── #
# Language registry — what the bot can build + test
# ──────────────────────────────────────────────────────────────────── #

@dataclass
class LanguageCapability:
    """Declares the bot's capability for a specific language/runtime."""
    language: str
    file_extensions: list[str]
    test_command: str
    lint_command: str
    build_command: str | None
    base_confidence: float  # 0.0-1.0, inherent confidence before issue analysis
    notes: str = ""

    def matches_file(self, filepath: str) -> bool:
        return any(filepath.endswith(ext) for ext in self.file_extensions)


# The bot's polyglot capability registry
CAPABILITIES: dict[str, LanguageCapability] = {
    "python": LanguageCapability(
        language="Python",
        file_extensions=[".py", ".pyw"],
        test_command="python -m pytest -q",
        lint_command="ruff check",
        build_command=None,
        base_confidence=0.95,
        notes="Primary stack. Full pytest + ruff automation. Highest confidence.",
    ),
    "typescript": LanguageCapability(
        language="TypeScript",
        file_extensions=[".ts", ".tsx"],
        test_command="npm test",
        lint_command="npx eslint --max-warnings 0",
        build_command="npm run build",
        base_confidence=0.82,
        notes="Strong capability. Can write CLI tools, hooks, agents. npm test + eslint.",
    ),
    "javascript": LanguageCapability(
        language="JavaScript",
        file_extensions=[".js", ".jsx", ".mjs", ".cjs"],
        test_command="npm test",
        lint_command="npx eslint --max-warnings 0",
        build_command=None,
        base_confidence=0.82,
        notes="Strong capability. Same toolchain as TypeScript.",
    ),
    "go": LanguageCapability(
        language="Go",
        file_extensions=[".go"],
        test_command="go mod tidy → go test -v ./...",
        lint_command="go vet ./...",
        build_command="go build ./...",
        base_confidence=0.95,
        notes="Full Go toolchain: go mod tidy + go test -v (verbose pass/fail parsing) + go vet. Structured error diagnostics (file:line:col). Available on GitHub Actions ubuntu-latest via actions/setup-go@v5.",
    ),
    "rust": LanguageCapability(
        language="Rust",
        file_extensions=[".rs"],
        test_command="cargo check --message-format=json → cargo test",
        lint_command="cargo clippy -- -D warnings",
        build_command="cargo build",
        base_confidence=0.95,
        notes="Full Rust toolchain: cargo check (JSON diagnostics with borrow-checker + lifetime analysis) → cargo test → cargo clippy. Structured error codes (E0308, E0382, etc.) with file/line/col. Available on GitHub Actions via actions-rust-lang/setup-rust-toolchain@v1.",
    ),
    "bash": LanguageCapability(
        language="Bash/Shell",
        file_extensions=[".sh", ".bash"],
        test_command="bash -n",  # syntax check only
        lint_command="shellcheck",
        build_command=None,
        base_confidence=0.90,
        notes="Strong scripting capability. shellcheck for linting.",
    ),
    "dockerfile": LanguageCapability(
        language="Dockerfile",
        file_extensions=["Dockerfile", ".dockerfile"],
        test_command=None,  # no unit tests for Dockerfiles
        lint_command="hadolint",
        build_command="docker build -t test .",
        base_confidence=0.85,
        notes="Can write multi-stage Dockerfiles. hadolint for validation.",
    ),
    "yaml": LanguageCapability(
        language="YAML (CI/CD)",
        file_extensions=[".yml", ".yaml"],
        test_command=None,
        lint_command="yamllint",
        build_command=None,
        base_confidence=0.92,
        notes="Strong CI/CD workflow engineering. GitHub Actions, Docker Compose, K8s manifests.",
    ),
    "markdown": LanguageCapability(
        language="Markdown/Docs",
        file_extensions=[".md", ".mdx"],
        test_command=None,
        lint_command="markdownlint",
        build_command=None,
        base_confidence=0.95,
        notes="Documentation, README, SOLUTION_README, policy docs.",
    ),
    "json": LanguageCapability(
        language="JSON (data/config)",
        file_extensions=[".json"],
        test_command="python -c \"import json; json.load(open('file'))\"",
        lint_command=None,
        build_command=None,
        base_confidence=0.98,
        notes="Data files, config, species packs. Native parsing.",
    ),
}


# ──────────────────────────────────────────────────────────────────── #
# Issue assessment
# ──────────────────────────────────────────────────────────────────── #

@dataclass
class IssueAssessment:
    """Result of evaluating a bounty issue against the capability matrix."""
    issue_title: str
    issue_url: str
    detected_language: str
    base_confidence: float
    complexity_modifier: float  # -0.3 to +0.2
    final_confidence: float
    cleared: bool  # True if final_confidence >= 0.80
    reasoning: str
    recommended_test_command: str
    recommended_lint_command: str


def detect_language(issue_title: str, issue_body: str, repo_files: list[str] | None = None) -> str:
    """Detect the primary language required for a bounty issue.

    Checks in order:
    1. Explicit language mentions in issue title/body
    2. File extensions in issue body (e.g., "src/main.go")
    3. Repository file analysis (if repo_files provided)
    4. Default: Python
    """
    text = f"{issue_title} {issue_body}".lower()

    # Explicit language mentions
    lang_keywords = {
        "python": ["python", "pytest", "pip", "django", "flask", "fastapi", "pydantic", "ruff"],
        "typescript": ["typescript", "tsx", "deno", "bun", "next.js", "react", "vue"],
        "javascript": ["javascript", "jsx", "node", "npm", "express"],
        "go": ["golang", "go ", "go test", "go build", "goroutine", "gin", "echo"],
        "rust": ["rust", "cargo", "crate", "tokio", "actix", "serde"],
        "bash": ["bash", "shell", "sh script", "shellcheck"],
        "dockerfile": ["dockerfile", "docker build", "docker-compose", "container"],
        "yaml": ["yaml", "yml", "github actions", "workflow", "ci/cd"],
        "markdown": ["markdown", "readme", "documentation", "docs", "changelog"],
        "json": ["json", "schema", "config file", "data file"],
    }

    for lang, keywords in lang_keywords.items():
        for kw in keywords:
            # Use word-boundary matching to avoid substring collisions
            # (e.g., "ts" in "settings", "go " in "cargo ")
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                return lang

    # File extensions in issue body
    for lang, cap in CAPABILITIES.items():
        for ext in cap.file_extensions:
            if ext in text:
                return lang

    # Repo file analysis
    if repo_files:
        lang_counts: dict[str, int] = {}
        for filepath in repo_files:
            for lang, cap in CAPABILITIES.items():
                if cap.matches_file(filepath):
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1
                    break
        if lang_counts:
            return max(lang_counts, key=lang_counts.get)

    return "python"  # default


def assess_complexity(issue_title: str, issue_body: str) -> float:
    """Assess issue complexity and return a modifier (-0.3 to +0.2).

    Returns:
        -0.3: Very complex (multi-system, ML, blockchain, async runtime)
        -0.2: Complex (new feature, API integration, database changes)
        -0.1: Moderate (bug fix, refactor, new function)
         0.0: Standard (simple feature, utility, test)
        +0.2: Simple (documentation, config, data file)
    """
    text = f"{issue_title} {issue_body}".lower()

    # Very complex indicators
    very_complex = ["machine learning", "ml model", "neural", "blockchain", "smart contract",
                    "distributed system", "concurrency", "async runtime", "compiler",
                    "operating system", "kernel", "driver", "cryptograph"]
    if any(kw in text for kw in very_complex):
        return -0.3

    # Complex indicators
    complex_kws = ["database", "migration", "api integration", "authentication", "oauth",
                   "websocket", "real-time", "distributed", "microservice", "kubernetes",
                   "terraform", "infrastructure", "pipeline", "refactor architecture"]
    if any(kw in text for kw in complex_kws):
        return -0.2

    # Moderate indicators
    moderate = ["bug fix", "refactor", "feature", "endpoint", "handler", "middleware",
                "test suite", "validation", "parser", "serializer"]
    if any(kw in text for kw in moderate):
        return -0.1

    # Simple indicators
    simple = ["documentation", "readme", "config", "json file", "data file", "typo",
              "rename", "format", "lint", "changelog", "species pack", "template"]
    if any(kw in text for kw in simple):
        return +0.2

    return 0.0  # standard


def assess_issue(
    issue_title: str,
    issue_body: str,
    issue_url: str = "",
    repo_files: list[str] | None = None,
    confidence_threshold: float = 0.80,
) -> IssueAssessment:
    """Full capability assessment for a bounty issue.

    Args:
        issue_title: Title of the GitHub issue.
        issue_body: Body/description of the issue.
        issue_url: URL of the issue (for tracking).
        repo_files: Optional list of file paths in the target repo.
        confidence_threshold: Minimum confidence to clear (default: 0.80).

    Returns:
        IssueAssessment with confidence score and clearance status.
    """
    lang = detect_language(issue_title, issue_body, repo_files)
    cap = CAPABILITIES.get(lang, CAPABILITIES["python"])
    complexity = assess_complexity(issue_title, issue_body)

    final_confidence = max(0.0, min(1.0, cap.base_confidence + complexity))
    cleared = final_confidence >= confidence_threshold

    reasoning_parts = [
        f"Language: {cap.language} (base confidence: {cap.base_confidence:.0%})",
        f"Complexity modifier: {complexity:+.1f}",
        f"Final confidence: {final_confidence:.0%}",
        f"Threshold: {confidence_threshold:.0%}",
        f"Cleared: {'YES' if cleared else 'NO'}",
    ]
    if cap.notes:
        reasoning_parts.append(f"Notes: {cap.notes}")

    return IssueAssessment(
        issue_title=issue_title,
        issue_url=issue_url,
        detected_language=lang,
        base_confidence=cap.base_confidence,
        complexity_modifier=complexity,
        final_confidence=final_confidence,
        cleared=cleared,
        reasoning=" | ".join(reasoning_parts),
        recommended_test_command=cap.test_command or "(no test command for this language)",
        recommended_lint_command=cap.lint_command or "(no lint command)",
    )
