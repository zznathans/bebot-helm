"""
Load generate-gcp-secret.py (hyphenated filename) as a module
so tests can import from it normally.
"""
import importlib.util
import sys
from pathlib import Path

_script_path = Path(__file__).parent.parent / "generate-gcp-secret.py"
_spec = importlib.util.spec_from_file_location("generate_gcp_secret", _script_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["generate_gcp_secret"] = _mod
