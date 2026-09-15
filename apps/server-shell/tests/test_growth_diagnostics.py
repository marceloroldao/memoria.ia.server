from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from growth_diagnostics import GrowthDiagnostics

def test_prefix_is_stable():
    from growth_diagnostics import PREFIX
    assert PREFIX == '/api/server/v1/growth-diagnostics'

def test_report_file_name_contract(tmp_path):
    class C: curiosity_data_dir=str(tmp_path/'curiosity'); memoria_api_url='http://127.0.0.1:1'; memoria_api_key=''; bdr_explorer_url='http://127.0.0.1:2'
    class Curiosity:
        def snapshot(self): return {'state':{'enabled':True}}
    class Knowledge:
        def recent(self,limit=1): return {'concepts':0,'observations':0}
    d=GrowthDiagnostics(C(),Curiosity(),Knowledge())
    assert d.path.name == 'growth-report.json'
    assert d.path.parent.name == 'diagnostics'
