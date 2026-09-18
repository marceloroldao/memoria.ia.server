from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_explorer_evicts_outside_viewport_and_does_not_turn_node_click_into_drag():
    app = (ROOT / "apps/bdr-explorer/explorer/static/app.js").read_text(encoding="utf-8")
    assert 'map.replaceChildren()' in app
    assert '.filter((v) => visible(v.p))' in app
    assert 'group.addEventListener("pointerdown", (event) => event.stopPropagation())' in app
    assert 'showNode(node, group)' in app
    assert 'temporal_index' in app
    assert '/api/server/v1/format-bdr' in app


def test_explorer_exposes_temporal_controls_and_guarded_format_button():
    html = (ROOT / "apps/bdr-explorer/explorer/static/index.html").read_text(encoding="utf-8")
    assert 'id="format-bdr"' in html
    assert 'id="time-older"' in html
    assert 'id="time-newer"' in html
    assert 'viewport + LOD + tempo' in html


def test_server_format_route_requires_explicit_formatar_and_resets_learning_cursor():
    server = (ROOT / "apps/server-shell/server.py").read_text(encoding="utf-8")
    assert 'path=="/api/server/v1/format-bdr"' in server
    assert '!="FORMATAR"' in server
    assert 'self.knowledge.reset()' in server
    assert 'self.learner.reset_to_current_end()' in server
