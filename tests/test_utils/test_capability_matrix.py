"""Tests for the capability matrix (polyglot targeting gate)."""
from __future__ import annotations

from src.utils.capability_matrix import (
    assess_complexity,
    assess_issue,
    detect_language,
)


# ──────────────────────────────────────────────────────────────────── #
# detect_language
# ──────────────────────────────────────────────────────────────────── #
def test_detect_python_from_title():
    assert detect_language("Build a Python CLI tool", "") == "python"

def test_detect_python_from_keywords():
    assert detect_language("Add pytest tests", "Using pydantic models") == "python"

def test_detect_typescript():
    assert detect_language("Create a React component in TypeScript", "") == "typescript"

def test_detect_go():
    assert detect_language("Fix goroutine leak in Go service", "") == "go"

def test_detect_rust():
    assert detect_language("Implement cargo build optimization", "") == "rust"

def test_detect_bash():
    assert detect_language("Write a bash script for deployment", "") == "bash"

def test_detect_dockerfile():
    assert detect_language("Optimize Dockerfile for smaller image", "") == "dockerfile"

def test_detect_yaml():
    assert detect_language("Update GitHub Actions workflow YAML", "") == "yaml"

def test_detect_markdown():
    assert detect_language("Write README documentation", "") == "markdown"

def test_detect_json():
    assert detect_language("Add JSON config file for settings", "") == "json"

def test_detect_from_file_extensions():
    assert detect_language("", "Edit src/main.go to fix bug") == "go"

def test_detect_from_repo_files():
    files = ["src/main.py", "tests/test_main.py", "setup.py"]
    assert detect_language("Build feature", "", repo_files=files) == "python"

def test_detect_defaults_to_python():
    assert detect_language("Generic task", "No language specified") == "python"


# ──────────────────────────────────────────────────────────────────── #
# assess_complexity
# ──────────────────────────────────────────────────────────────────── #
def test_complexity_very_complex_ml():
    assert assess_complexity("Machine learning model", "") == -0.3

def test_complexity_very_complex_blockchain():
    assert assess_complexity("Smart contract audit", "") == -0.3

def test_complexity_complex_database():
    assert assess_complexity("Database migration", "") == -0.2

def test_complexity_complex_api():
    assert assess_complexity("OAuth authentication integration", "") == -0.2

def test_complexity_moderate_bug_fix():
    assert assess_complexity("Bug fix in parser", "") == -0.1

def test_complexity_simple_docs():
    assert assess_complexity("Write documentation", "") == 0.2

def test_complexity_simple_config():
    assert assess_complexity("Add JSON config file", "") == 0.2

def test_complexity_standard_default():
    assert assess_complexity("Add a utility function", "") == 0.0


# ──────────────────────────────────────────────────────────────────── #
# assess_issue
# ──────────────────────────────────────────────────────────────────── #
def test_assess_python_feature_cleared():
    result = assess_issue(
        "Add a utility function for string parsing",
        "Write a Python function that parses strings",
    )
    assert result.detected_language == "python"
    assert result.final_confidence >= 0.80
    assert result.cleared is True

def test_assess_rust_complex_not_cleared():
    result = assess_issue(
        "Implement machine learning inference engine in Rust",
        "Build a neural network inference runtime using tokio",
    )
    assert result.detected_language == "rust"
    assert result.final_confidence < 0.80
    assert result.cleared is False

def test_assess_go_bug_fix_cleared():
    result = assess_issue(
        "Bug fix in Go HTTP handler",
        "Fix goroutine leak in the HTTP middleware",
    )
    assert result.detected_language == "go"
    # Go base=0.80, complexity "bug fix" = -0.1 → 0.70, NOT cleared
    assert result.cleared is False

def test_assess_go_simple_cleared():
    result = assess_issue(
        "Add JSON config file for Go service",
        "Create a JSON configuration schema",
    )
    assert result.detected_language in ("go", "json")
    assert result.final_confidence >= 0.80

def test_assess_typescript_component_cleared():
    result = assess_issue(
        "Create a React component in TypeScript",
        "Build a dashboard widget component",
    )
    assert result.detected_language == "typescript"
    assert result.final_confidence >= 0.80
    assert result.cleared is True

def test_assess_bash_script_cleared():
    result = assess_issue(
        "Write a bash script for deployment automation",
        "Create a shell script that automates Docker deployment",
    )
    assert result.detected_language == "bash"
    assert result.final_confidence >= 0.80
    assert result.cleared is True

def test_assess_markdown_docs_cleared():
    result = assess_issue(
        "Write comprehensive README documentation",
        "Create README.md with installation and usage guide",
    )
    assert result.detected_language == "markdown"
    assert result.final_confidence >= 0.95
    assert result.cleared is True

def test_assess_returns_test_commands():
    result = assess_issue("Add Python pytest tests", "")
    assert "pytest" in result.recommended_test_command
    assert "ruff" in result.recommended_lint_command

def test_assess_reasoning_contains_confidence():
    result = assess_issue("Python feature", "Build a utility function")
    assert "confidence" in result.reasoning.lower()
    assert "cleared" in result.reasoning.lower()

def test_assess_custom_threshold():
    result = assess_issue(
        "Complex ML model in Rust",
        "Implement neural network with tokio async runtime",
        confidence_threshold=0.50,  # lower threshold
    )
    assert result.final_confidence < 0.50  # 0.78-0.3=0.48
    assert result.cleared is False  # 0.48 < 0.50 threshold
