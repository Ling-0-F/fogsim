import importlib.util
from pathlib import Path
import pytest


def test_original_java_methods_and_reference_heap():
    path=Path(__file__).resolve().parents[2]/"tools/run_java_oracle.py"
    spec=importlib.util.spec_from_file_location("java_oracle",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if not module.find_java():pytest.skip("JDK missing: set FOGSIM_JAVA; no Java parity claim")
    report=module.run_oracle()
    assert report["passed"] and report["comparison_output_count"]>2000
