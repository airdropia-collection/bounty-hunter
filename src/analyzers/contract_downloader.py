"""
Source code downloader (multi-language).

Fetches source code from GitHub repos for any programming language.
Originally built for Solidity smart contract audits (Immunefi/Code4rena/
Sherlock), now extended to handle general software bugs from IssueHunt
and Dework (JavaScript, TypeScript, Python, Java, Go, Rust, C++, etc.).

Data sources:
1. GitHub repos — for any language (IssueHunt, Dework, Code4rena, Sherlock)
2. Etherscan — for Solidity contracts on Ethereum (Immunefi)

Caches downloads to avoid re-fetching.

Language detection:
- Inspects repo tree to find files with known extensions
- Returns the dominant language's source files concatenated
- Falls back to "any source file" if no known language detected
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from src.utils.logger import get_logger
from src.utils.retry import retry_network

log = get_logger("contract_downloader")  # keep logger name for backward compat

CACHE_DIR = Path("cache/contracts")


# --------------------------------------------------------------------------- #
# Language registry — maps language name to file extensions
# --------------------------------------------------------------------------- #
LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    # Smart contracts
    "solidity": [".sol"],
    # Web/frontend
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "typescript": [".ts", ".tsx", ".mts", ".cts"],
    "vue": [".vue"],
    "svelte": [".svelte"],
    # Backend/scripting
    "python": [".py"],
    "ruby": [".rb"],
    "php": [".php"],
    "perl": [".pl", ".pm"],
    "lua": [".lua"],
    # Systems
    "go": [".go"],
    "rust": [".rs"],
    "c": [".c", ".h"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"],
    "objc": [".m", ".mm"],
    "swift": [".swift"],
    "kotlin": [".kt", ".kts"],
    "java": [".java"],
    "scala": [".scala"],
    "csharp": [".cs"],
    # JVM
    "clojure": [".clj", ".cljs", ".cljc"],
    # Functional
    "haskell": [".hs"],
    "elixir": [".ex", ".exs"],
    "erlang": [".erl"],
    "ocaml": [".ml", ".mli"],
    "fsharp": [".fs", ".fsx", ".fsi"],
    # Shell/config
    "shell": [".sh", ".bash", ".zsh"],
    "powershell": [".ps1", ".psm1"],
    # Mobile
    "dart": [".dart"],
    # Other
    "julia": [".jl"],
    "r": [".r", ".R"],
    "nim": [".nim"],
    "crystal": [".cr"],
    "zig": [".zig"],
}

# Reverse map: extension → language (for detection)
EXTENSION_TO_LANG: dict[str, str] = {}
for lang, exts in LANGUAGE_EXTENSIONS.items():
    for ext in exts:
        EXTENSION_TO_LANG[ext.lower()] = lang

# Directories to skip when scanning a repo
SKIP_DIRS = {
    "node_modules", "vendor", "dist", "build", "target", ".git",
    "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "coverage", ".nyc_output",
    "pod", "Carthage", "DerivedData", ".build",
    "test", "tests", "__tests__", "spec", "specs", "fixtures",
    "mock", "mocks", "stubs", "examples", "docs", "doc",
    ".github", ".vscode", ".idea", ".circleci",
}

# File path substrings that indicate test/mock files (skip these)
SKIP_PATH_PATTERNS = re.compile(
    r"(?:^|/)(?:test|tests|__tests__|spec|specs|fixtures|mock|mocks|stubs)/",
    re.IGNORECASE,
)


class ContractDownloader:
    """Downloads source code from GitHub or Etherscan (multi-language)."""

    def __init__(self, etherscan_api_key: str | None = None):
        self.etherscan_key = etherscan_api_key or os.getenv("ETHERSCAN_API_KEY", "")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def download(self, source_url: str) -> str | None:
        """Download source code. Returns concatenated source or None.

        For GitHub URLs: detects dominant language + fetches up to 10 source files
        For Etherscan addresses: fetches verified Solidity contract source
        """
        # Check cache first
        cache_key = self._cache_key(source_url)
        cache_path = CACHE_DIR / f"{cache_key}.src"
        if cache_path.exists():
            log.debug("cache hit: %s", cache_path)
            return cache_path.read_text(encoding="utf-8")

        # Determine source type
        if "github.com" in source_url:
            source = self._download_github(source_url)
        elif source_url.startswith("0x") and len(source_url) == 42:
            source = self._download_etherscan(source_url)
        elif "etherscan" in source_url:
            addr_match = re.search(r"0x[a-fA-F0-9]{40}", source_url)
            if addr_match:
                source = self._download_etherscan(addr_match.group())
            else:
                log.warning("could not extract address from %s", source_url)
                return None
        else:
            log.warning("unknown source type: %s", source_url)
            return None

        if source:
            cache_path.write_text(source, encoding="utf-8")
            log.info("downloaded %d chars from %s", len(source), source_url)

        return source

    @retry_network(max_attempts=2, base_delay=1.0, max_delay=5.0)
    def _download_github(self, url: str) -> str | None:
        """Download from GitHub repo. Returns concatenated source files.

        Detects the repo's dominant language from file extensions, then
        fetches up to 10 source files of that language (skipping tests/mocks).
        Falls back to "any source file" if no known language is detected.
        """
        import httpx

        # Parse GitHub URL: https://github.com/owner/repo/issues/123 → owner/repo
        match = re.match(r"https://github\.com/([^/]+)/([^/]+)", url)
        if not match:
            log.warning("could not parse GitHub URL: %s", url)
            return None

        owner, repo = match.group(1), match.group(2)
        repo = repo.replace(".git", "")

        # Get repo tree (try main first, then master)
        api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/main?recursive=1"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "bounty-hunter",
        }
        gh_pat = os.getenv("GH_PAT", "")
        if gh_pat:
            headers["Authorization"] = f"Bearer {gh_pat}"

        resp = httpx.get(api_url, headers=headers, timeout=30)
        if resp.status_code == 404:
            api_url = api_url.replace("/main?", "/master?")
            resp = httpx.get(api_url, headers=headers, timeout=30)

        if resp.status_code != 200:
            log.warning("GitHub API %d for %s", resp.status_code, api_url)
            return None

        tree = resp.json().get("tree", [])
        if not tree:
            log.info("empty repo tree for %s/%s", owner, repo)
            return None

        # Detect dominant language from file extensions
        lang = self._detect_language(tree)
        if lang:
            log.info("detected language: %s for %s/%s", lang, owner, repo)
            extensions = LANGUAGE_EXTENSIONS[lang]
        else:
            log.info("no known language detected for %s/%s — fetching any source", owner, repo)
            extensions = None  # fetch any source file

        # Filter source files (skip tests/mocks/vendor)
        source_files = []
        for f in tree:
            path = f.get("path", "")
            if not path or f.get("type") != "blob":
                continue
            # Skip if path matches test/mock patterns
            if SKIP_PATH_PATTERNS.search(path):
                continue
            # Skip if any path component is in SKIP_DIRS
            parts = path.lower().split("/")
            if any(p in SKIP_DIRS for p in parts):
                continue
            # Match by extension
            ext = Path(path).suffix.lower()
            if extensions:
                if ext in extensions:
                    source_files.append(f)
            else:
                # No known language — accept any file with a code-like extension
                if ext and ext in EXTENSION_TO_LANG:
                    source_files.append(f)
        # Limit to first 10 files
        source_files = source_files[:10]

        if not source_files:
            log.info("no source files found in %s/%s (lang=%s)", owner, repo, lang or "any")
            return None

        # Determine branch for raw URLs
        branch = "main" if "/main?" in api_url else "master"

        # Download each file
        sources = []
        for f in source_files:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{f['path']}"
            try:
                file_resp = httpx.get(raw_url, headers={"User-Agent": "bounty-hunter"}, timeout=15)
                if file_resp.status_code == 200:
                    sources.append(f"// File: {f['path']}\n{file_resp.text}")
            except Exception as exc:
                log.debug("failed to fetch %s: %s", f["path"], exc)

        return "\n\n".join(sources) if sources else None

    def _detect_language(self, tree: list[dict]) -> str | None:
        """Detect dominant language from repo tree by counting file extensions.

        Returns the language name (e.g. "python", "typescript") or None
        if no recognized language files are found.
        """
        from collections import Counter
        counts: Counter[str] = Counter()
        for f in tree:
            path = f.get("path", "")
            if not path or f.get("type") != "blob":
                continue
            # Skip test/mock/vendor files for language detection
            if SKIP_PATH_PATTERNS.search(path):
                continue
            parts = path.lower().split("/")
            if any(p in SKIP_DIRS for p in parts):
                continue
            ext = Path(path).suffix.lower()
            if ext in EXTENSION_TO_LANG:
                counts[EXTENSION_TO_LANG[ext]] += 1

        if not counts:
            return None

        # Return the most common language
        return counts.most_common(1)[0][0]

    @retry_network(max_attempts=2, base_delay=1.0, max_delay=5.0)
    def _download_etherscan(self, address: str) -> str | None:
        """Download verified Solidity contract source from Etherscan."""
        if not self.etherscan_key:
            log.warning("no ETHERSCAN_API_KEY — can't fetch contract source")
            return None

        import httpx

        url = "https://api.etherscan.io/api"
        params = {
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
            "apikey": self.etherscan_key,
        }
        resp = httpx.get(url, params=params, timeout=30)
        data = resp.json()

        if data.get("status") != "1":
            log.warning("Etherscan API error: %s", data.get("message", "unknown"))
            return None

        result = data.get("result", [])
        if not result:
            return None

        source_code = result[0].get("SourceCode", "")
        if not source_code:
            log.info("contract %s is not verified on Etherscan", address)
            return None

        return source_code

    @staticmethod
    def _cache_key(url: str) -> str:
        """Generate cache key from URL."""
        key = url.replace("https://", "").replace("http://", "")
        key = re.sub(r"[^a-zA-Z0-9]", "_", key)
        return key[:100]
