from pathlib import Path
import random
import sys

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from web_walker import LinkCollector, WebWalker


def test_link_collector_resolves_relative_links():
    parser = LinkCollector("https://example.org/path/page")
    parser.feed('<a href="/next">Next</a><a href="https://other.example/a">Other</a>')
    urls = [url for _, url in parser.links]
    assert "https://example.org/next" in urls
    assert "https://other.example/a" in urls


def test_walker_uses_frontier_before_seed():
    walker = WebWalker(random.Random(1), seeds=["https://seed.example/"], domain_cooldown_seconds=0)
    walker.offer("A", "https://a.example/page")
    result = walker.next_candidates(1)
    assert result == [("A", "https://a.example/page")]


def test_walker_can_extract_and_enqueue_links():
    walker = WebWalker(random.Random(2), seeds=[], domain_cooldown_seconds=0)
    count = walker.offer_page_links(
        "https://example.org/start",
        '<a href="/one">One</a><a href="https://two.example/x">Two</a>',
        max_links=5,
    )
    assert count == 2
    candidates = walker.next_candidates(2)
    assert len(candidates) == 2
    assert {url for _, url in candidates} == {"https://example.org/one", "https://two.example/x"}
