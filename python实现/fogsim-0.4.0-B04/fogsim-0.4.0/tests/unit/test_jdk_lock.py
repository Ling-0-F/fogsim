"""JDK 17 family is required; update version/vendor/source are evidence only."""
import hashlib
from types import SimpleNamespace
import sys
import zipfile
import pytest
from conftest import ROOT
sys.path.insert(0, str(ROOT / "tools"))
import java_support


def fake_jdk(monkeypatch, tmp_path, specification="17", runtime="17.0.20.1+1", vendor="Eclipse Adoptium"):
    java = tmp_path / "bin/java"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"fake executable: subprocess is mocked")
    stderr = (f"    java.class.path = \n    java.specification.version = {specification}\n"
              f"    java.runtime.version = {runtime}\n    java.vendor = {vendor}\n")
    monkeypatch.setattr(java_support.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="", stderr=stderr))
    return java


@pytest.mark.parametrize("runtime,vendor", [
    ("17.0.16+8", "Eclipse Adoptium"),
    ("17.0.20.1+1", "Eclipse Adoptium"),
    ("17.0.20+8", "Another OpenJDK vendor"),
])
def test_java17_update_vendor_and_source_changes_are_allowed(monkeypatch, tmp_path, runtime, vendor):
    java = fake_jdk(monkeypatch, tmp_path, runtime=runtime, vendor=vendor)
    source = tmp_path / "lib/src.zip"; source.parent.mkdir()
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("java.base/java/util/PriorityQueue.java", b"different source snapshot")
    result = java_support.reference_jdk(java)
    assert result["runtime_version"] == runtime and result["vendor"] == vendor
    assert result["priority_queue_source_sha256"] == hashlib.sha256(b"different source snapshot").hexdigest()
    assert result["matches_historical_priority_queue_source"] is False
    assert result["matches_historical_runtime"] == (runtime == "17.0.16+8" and vendor == "Eclipse Adoptium")


@pytest.mark.parametrize("specification", ["1.8", "11", "18", "21", "unknown"])
def test_non_java17_is_rejected(monkeypatch, tmp_path, specification):
    java = fake_jdk(monkeypatch, tmp_path, specification=specification)
    with pytest.raises(RuntimeError, match="require JDK 17"):
        java_support.reference_jdk(java)


def test_source_archive_is_optional(monkeypatch, tmp_path):
    java = fake_jdk(monkeypatch, tmp_path)
    result = java_support.reference_jdk(java)
    assert result["priority_queue_source_sha256"] is None
    assert result["priority_queue_source_status"] == "unavailable"
    assert result["matches_historical_priority_queue_source"] is None


def test_unreadable_source_is_reported_without_blocking_runtime_tests(monkeypatch, tmp_path):
    java = fake_jdk(monkeypatch, tmp_path)
    source = tmp_path / "lib/src.zip"; source.parent.mkdir(); source.write_bytes(b"invalid ZIP")
    result = java_support.reference_jdk(java)
    assert result["priority_queue_source_status"] == "unreadable"
    assert "BadZipFile" in result["priority_queue_source_error"]
