from pathlib import Path
import sys
from types import SimpleNamespace

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from site_ingest import SiteIngestManager


class FakeCuriosity:
    def __init__(self):
        self.config = SimpleNamespace(curiosity_text_limit=5000)
        self.state = SimpleNamespace(pages_read=0)


def test_same_site_accepts_subdomains_and_rejects_other_hosts():
    assert SiteIngestManager._same_site("example.com", "https://example.com/a")
    assert SiteIngestManager._same_site("example.com", "https://docs.example.com/a")
    assert not SiteIngestManager._same_site("example.com", "https://example.net/a")


def test_page_from_html_extracts_visible_content_and_terms_once():
    curiosity = FakeCuriosity()
    manager = SiteIngestManager(curiosity)
    html = """
    <html><head><title>Motores BLDC</title><meta name='description' content='Controle BLDC'></head>
    <body>Motor BLDC controle BLDC motor controle eletrônico.</body></html>
    """
    page = manager._page_from_html("https://example.com/a", html)
    assert page["title"] == "Motores BLDC"
    assert "bldc" in page["terms"]
    assert curiosity.state.pages_read == 1


def test_clean_url_removes_fragments():
    assert SiteIngestManager._clean_url("https://example.com/a#parte") == "https://example.com/a"
