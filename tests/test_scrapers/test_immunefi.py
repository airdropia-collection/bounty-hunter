"""Tests for the Immunefi scraper."""
from src.scrapers.immunefi import ImmunefiScraper


# Sample HTML mimicking Immunefi's Next.js __NEXT_DATA__ format.
# Real Immunefi pages embed JSON with escaped quotes: \"key\":\"value\"
# This test HTML replicates that format.
SAMPLE_HTML = r"""
<html>
<script id="__NEXT_DATA__">
{
  \"bounties\": [
    {
      \"project\": \"LayerZero\",
      \"slug\": \"layerzero\",
      \"maxBounty\": 15000000,
      \"technologies\": [\"Solidity\"]
    },
    {
      \"project\": \"Aave\",
      \"slug\": \"aave\",
      \"maxBounty\": 1000000,
      \"technologies\": []
    },
    {
      \"project\": \"TestProject\",
      \"slug\": \"test\",
      \"maxBounty\": 0,
      \"technologies\": []
    }
  ]
}
</script>
</html>
"""


def test_parse_bounties_extracts_projects():
    scraper = ImmunefiScraper()
    bounties = scraper._parse_bounties(SAMPLE_HTML)
    # Should find LayerZero and Aave (skip TestProject with maxBounty=0)
    assert len(bounties) >= 2
    names = [b.project_name for b in bounties]
    assert "LayerZero" in names
    assert "Aave" in names


def test_parse_bounties_max_payout():
    scraper = ImmunefiScraper()
    bounties = scraper._parse_bounties(SAMPLE_HTML)
    lz = [b for b in bounties if b.project_name == "LayerZero"]
    assert len(lz) == 1
    assert lz[0].max_payout_usd == 15_000_000


def test_parse_bounties_url():
    scraper = ImmunefiScraper()
    bounties = scraper._parse_bounties(SAMPLE_HTML)
    lz = [b for b in bounties if b.project_name == "LayerZero"][0]
    assert lz.url == "https://immunefi.com/bounty/layerzero"


def test_parse_bounties_id():
    scraper = ImmunefiScraper()
    bounties = scraper._parse_bounties(SAMPLE_HTML)
    lz = [b for b in bounties if b.project_name == "LayerZero"][0]
    assert lz.id == "immunefi-layerzero"


def test_parse_bounties_platform():
    scraper = ImmunefiScraper()
    bounties = scraper._parse_bounties(SAMPLE_HTML)
    for b in bounties:
        assert b.platform == "immunefi"


def test_parse_bounties_skips_zero_payout():
    scraper = ImmunefiScraper()
    bounties = scraper._parse_bounties(SAMPLE_HTML)
    # TestProject has maxBounty=0, should be skipped
    names = [b.project_name for b in bounties]
    assert "TestProject" not in names


def test_parse_bounties_tech_stack():
    scraper = ImmunefiScraper()
    bounties = scraper._parse_bounties(SAMPLE_HTML)
    lz = [b for b in bounties if b.project_name == "LayerZero"][0]
    assert "Solidity" in lz.tech_stack


def test_parse_bounties_high_value_tag():
    scraper = ImmunefiScraper()
    bounties = scraper._parse_bounties(SAMPLE_HTML)
    lz = [b for b in bounties if b.project_name == "LayerZero"][0]
    assert "high-value" in lz.tags  # $15M >= $1M


def test_parse_empty_html():
    scraper = ImmunefiScraper()
    bounties = scraper._parse_bounties("<html></html>")
    assert bounties == []


def test_filter_by_payout():
    scraper = ImmunefiScraper()
    bounties = scraper._parse_bounties(SAMPLE_HTML)
    filtered = scraper.filter_by_payout(bounties, min_usd=5_000_000)
    names = [b.project_name for b in filtered]
    assert "LayerZero" in names  # $15M
    assert "Aave" not in names   # $1M < $5M
