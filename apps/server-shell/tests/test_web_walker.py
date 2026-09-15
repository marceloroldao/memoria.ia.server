from pathlib import Path
import random, sys
SHELL_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SHELL_DIR))
from web_walker import LinkCollector, WebWalker, canonical_url

def test_link_collector_resolves_relative_links():
    parser=LinkCollector("https://example.org/path/page"); parser.feed('<a href="/next">Next</a><a href="https://other.example/a">Other</a>'); urls=[url for _,url in parser.links]
    assert "https://example.org/next" in urls and "https://other.example/a" in urls

def test_walker_uses_frontier_before_seed():
    walker=WebWalker(random.Random(1),seeds=["https://seed.example/"],domain_cooldown_seconds=0); walker.offer("A","https://a.example/page"); assert walker.next_candidates(1)==[("A","https://a.example/page")]

def test_walker_can_extract_and_enqueue_links():
    walker=WebWalker(random.Random(2),seeds=[],domain_cooldown_seconds=0); count=walker.offer_page_links("https://example.org/start",'<a href="/one">One</a><a href="https://two.example/x">Two</a>',max_links=5); candidates=walker.next_candidates(2)
    assert count==2 and {url for _,url in candidates}=={"https://example.org/one","https://two.example/x"}

def test_canonical_url_removes_tracking_and_fragment():
    assert canonical_url("HTTPS://Example.org/a?utm_source=x&id=7#frag")=="https://example.org/a?id=7"

def test_duplicate_tracking_urls_enter_frontier_once():
    walker=WebWalker(random.Random(3),seeds=[],domain_cooldown_seconds=0); walker.offer("A","https://example.org/a?utm_source=x"); walker.offer("A2","https://example.org/a?utm_source=y")
    assert len(walker.frontier)==1

def test_binary_assets_are_not_enqueued():
    walker=WebWalker(random.Random(4),seeds=[],domain_cooldown_seconds=0); count=walker.offer_page_links("https://example.org/",'<a href="/paper">Paper</a><a href="/photo.jpg">Photo</a>',max_links=5)
    assert count==1
