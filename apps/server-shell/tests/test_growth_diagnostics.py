from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from growth_diagnostics import GrowthDiagnostics, SCHEMA


def test_prefix_is_stable():
    from growth_diagnostics import PREFIX
    assert PREFIX == '/api/server/v1/growth-diagnostics'


def test_report_file_name_contract(tmp_path):
    class C:
        curiosity_data_dir = str(tmp_path / 'curiosity')
        memoria_api_url = 'http://127.0.0.1:1'
        memoria_api_key = ''
        bdr_explorer_url = 'http://127.0.0.1:2'
    class Curiosity:
        def snapshot(self): return {'state': {'enabled': True}}
    class Knowledge:
        def recent(self, limit=1): return {'concepts': 0, 'observations': 0}
    d = GrowthDiagnostics(C(), Curiosity(), Knowledge())
    assert d.path.name == 'growth-report.json'
    assert d.path.parent.name == 'diagnostics'


def test_report_exposes_canonical_metrics(tmp_path):
    class C:
        curiosity_data_dir = str(tmp_path / 'curiosity')
        memoria_api_url = 'unused'
        memoria_api_key = ''
        bdr_explorer_url = 'unused'
    class Curiosity:
        def snapshot(self):
            return {'metrics': {'cycles': 12, 'searches': 7, 'pages_read': 5, 'discoveries': 3, 'jumps': 2, 'errors': 1}}
    class Knowledge:
        def recent(self, limit=1): return {'concepts': 9, 'observations': 4}

    curiosity_dir = Path(C.curiosity_data_dir)
    curiosity_dir.mkdir(parents=True)
    (curiosity_dir / 'events.jsonl').write_text(
        '\n'.join([
            '{"kind":"evidence"}',
            '{"kind":"evidence"}',
            '{"kind":"cycle"}',
        ]), encoding='utf-8'
    )

    d = GrowthDiagnostics(C(), Curiosity(), Knowledge())
    d._episodes = lambda: [
        {'event_type': 'server_knowledge_evidence'},
        {'event_type': 'server_knowledge_evidence'},
        {'event_type': 'chat'},
        {'event_type': 'chat'},
    ]
    d._explorer = lambda: {'statistics': {'total_entidades': 4}}

    report = d.report()
    assert report['schema'] == SCHEMA
    assert report['metrics']['bdr_history_rows'] == 4
    assert report['metrics']['bdr_knowledge_rows'] == 2
    assert report['metrics']['knowledge_observations'] == 4
    assert report['metrics']['knowledge_concepts'] == 9
    assert report['metrics']['curiosity_events'] == 3
    assert report['metrics']['web_evidence'] == 2
    assert report['metrics']['explorer_records'] == 4
    assert report['metrics']['cycles'] == 12
    assert report['metrics']['pages'] == 5
    assert report['rates']['evidence_to_learning'] == 2.0
    assert report['rates']['learning_to_bdr'] == 0.5
    assert report['rates']['bdr_to_explorer'] == 1.0


def test_zero_denominator_rates_are_null(tmp_path):
    class C:
        curiosity_data_dir = str(tmp_path / 'curiosity')
        memoria_api_url = 'unused'
        memoria_api_key = ''
        bdr_explorer_url = 'unused'
    class Curiosity:
        def snapshot(self): return {}
    class Knowledge:
        def recent(self, limit=1): return {'concepts': 0, 'observations': 0}
    d = GrowthDiagnostics(C(), Curiosity(), Knowledge())
    d._episodes = lambda: []
    d._explorer = lambda: {'statistics': {'total_entidades': 0}}
    report = d.report()
    assert report['rates']['evidence_to_learning'] is None
    assert report['rates']['learning_to_bdr'] is None
    assert report['rates']['bdr_to_explorer'] is None
