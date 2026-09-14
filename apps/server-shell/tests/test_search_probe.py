from pathlib import Path
import sys

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from search_probe import SearchProbe


def test_search_probe_accepts_html_and_lite_style_links():
    html = '''
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Alpha</a>
    <a class="result-link" href="https://example.org/b">Beta</a>
    '''
    parser = SearchProbe()
    parser.feed(html)
    assert ("Alpha", "https://example.com/a") in parser.links
    assert ("Beta", "https://example.org/b") in parser.links


def test_search_probe_ignores_navigation_links():
    parser = SearchProbe()
    parser.feed('<a href="https://duckduckgo.com/about">About</a>')
    assert parser.links == []
