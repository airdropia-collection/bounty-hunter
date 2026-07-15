"""Tests for the contract downloader."""
from src.analyzers.contract_downloader import ContractDownloader


def test_cache_key_generation():
    key = ContractDownloader._cache_key("https://github.com/owner/repo")
    assert "github" in key
    assert len(key) <= 100


def test_cache_key_sanitizes_special_chars():
    key = ContractDownloader._cache_key("https://example.com/path?query=1&x=2")
    assert "?" not in key
    assert "&" not in key


def test_download_unknown_source_type():
    dl = ContractDownloader(etherscan_api_key="")
    # Unknown URL type should return None
    result = dl.download("ftp://example.com/file.sol")
    assert result is None


def test_download_caches_results(tmp_path, monkeypatch):
    """Downloaded source should be cached for re-use."""
    monkeypatch.setattr("src.analyzers.contract_downloader.CACHE_DIR", tmp_path / "contracts")
    dl = ContractDownloader(etherscan_api_key="")

    # Manually create a cache file
    cache_file = tmp_path / "contracts" / "test_key.sol"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("cached source code")

    # Mock _cache_key to return our key
    monkeypatch.setattr(ContractDownloader, "_cache_key", lambda _, url: "test_key")

    result = dl.download("https://example.com/anything")
    assert result == "cached source code"


def test_download_github_invalid_url():
    dl = ContractDownloader(etherscan_api_key="")
    result = dl.download("https://github.com/")
    assert result is None
