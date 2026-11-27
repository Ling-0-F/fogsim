"""Compile original Java classes with two audited constructor-only overlays."""
from __future__ import annotations
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "references/java/Fog-Computing-multiDeviceDebug"
ADAPTER = ROOT / "tools/java"
REFERENCE_RUNTIME = "17.0.16+8"
REFERENCE_VENDOR = "Eclipse Adoptium"
PRIORITY_QUEUE_SHA256 = "92f97c6625f4cd1994765acbd718e8a6f7c7697e5e65974a1d78d5e37e284ca8"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def java_tools(explicit=None, *, allow_compiler_module=True):
    java = explicit or os.environ.get("FOGSIM_JAVA")
    if not java:
        directory = ROOT / "references/jdk/jdk-17.0.16+8/bin"
        bundled = next((directory / name for name in ("java", "java.exe") if (directory / name).exists()), None)
        java = str(bundled) if bundled else shutil.which("java")
    if not java:
        raise RuntimeError("JDK 17 missing: pass --java or set FOGSIM_JAVA")
    java = Path(java).resolve()
    javac = java.with_name("javac.exe" if java.suffix == ".exe" else "javac")
    if not javac.is_file():
        if allow_compiler_module and (java.parent.parent / "lib/modules").is_file():
            # The current image has jdk.compiler but omits its javac launcher.
            # Ordinary callers keep their existing explicit-launcher contract.
            return java, None
        raise RuntimeError(f"JDK compiler missing: {javac}")
    return java, javac


def reference_jdk(java):
    """Require Java 17; record update/vendor/source without pinning the user's JDK.

    The historical reference identifies where earlier results were obtained.
    Other Java 17 builds must pass the actual oracle/parity tests themselves.
    """
    version = subprocess.run([str(java), "-XshowSettings:properties", "-version"],
                             capture_output=True, text=True, check=True)
    properties = {key.strip(): value.strip() for line in version.stderr.splitlines() if " = " in line
                  for key, value in [line.split(" = ", 1)]}
    if properties.get("java.specification.version") != "17":
        raise RuntimeError(f"Java reference tests require JDK 17; "
                           f"got specification {properties.get('java.specification.version')} "
                           f"(runtime {properties.get('java.runtime.version')})")
    source = Path(java).resolve().parent.parent / "lib/src.zip"
    pq_sha, source_status, source_error = None, "unavailable", None
    if source.is_file():
        try:
            with zipfile.ZipFile(source) as archive:
                pq_sha = hashlib.sha256(archive.read("java.base/java/util/PriorityQueue.java")).hexdigest()
            source_status = "recorded"
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            source_status, source_error = "unreadable", f"{type(exc).__name__}: {exc}"
    return {"version_output": version.stdout + version.stderr,
            "specification_version": properties["java.specification.version"],
            "runtime_version": properties.get("java.runtime.version"), "vendor": properties.get("java.vendor"),
            "os_arch": properties.get("os.arch"), "priority_queue_source_sha256": pq_sha,
            "priority_queue_source_status": source_status, "priority_queue_source_error": source_error,
            "matches_historical_runtime": (properties.get("java.runtime.version") == REFERENCE_RUNTIME
                                           and properties.get("java.vendor") == REFERENCE_VENDOR),
            "matches_historical_priority_queue_source": None if pq_sha is None else pq_sha == PRIORITY_QUEUE_SHA256,
            "java_sha256": sha(java)}


def prepare_and_compile(output, java=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    java, javac = java_tools(java, allow_compiler_module=True)
    reference = reference_jdk(java)
    (output / "java-version.txt").write_text(reference["version_output"], encoding="utf-8")
    files = {}
    for path in sorted((ORIGINAL / "src").rglob("*.java")):
        files[str(path.relative_to(ORIGINAL)).replace("\\", "/")] = sha(path)
    jars = sorted(p for p in (ORIGINAL / "libraries").glob("*.jar") if "javadoc" not in p.name)
    if not files or not jars:
        raise RuntimeError("Original Java source/dependencies missing; restore the supplied Java ZIP")
    overlays = []
    patches = []
    for name, package in (("MobileDevice", "taskscheduling"), ("DynamicSimulation", "simulation")):
        relative = Path("mengxu") / package / f"{name}.java"
        original = ORIGINAL / "src" / relative
        text = original.read_text(encoding="utf-8")
        addition = (ADAPTER / "constructors" / f"{name}.java.inc").read_text(encoding="utf-8")
        anchor = f"public class {name} {{"
        if text.count(anchor) != 1:
            raise RuntimeError(f"unexpected source shape: {original}")
        modified = text.replace(anchor, anchor + "\n\n" + addition, 1)
        target = output / "overlay" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(modified, encoding="utf-8")
        diff = "".join(difflib.unified_diff(text.splitlines(True), modified.splitlines(True),
                        fromfile=f"original/{relative.as_posix()}", tofile=f"overlay/{relative.as_posix()}"))
        (output / f"{name}.patch").write_text(diff, encoding="utf-8")
        patches.append({"class": name, "kind": "constructor addition only",
                        "original_sha256": sha(original), "overlay_sha256": sha(target),
                        "patch": f"{name}.patch"})
        overlays.append(target)
    inputs = {"original_sources": files,
              "libraries": {p.name: sha(p) for p in jars},
              "adapter_sources": {str(p.relative_to(ADAPTER)).replace("\\", "/"): sha(p)
                                  for p in sorted(ADAPTER.rglob("*")) if p.is_file()},
              "java_version": reference["version_output"], "reference_jdk": reference,
              "javac_sha256": sha(javac) if javac else None,
              "compiler_modules_sha256": sha(java.parent.parent / "lib/modules") if javac is None else None,
              "overlays": patches}
    fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    # Each source snapshot has its own class directory; stale classes cannot contaminate a build.
    classes = output / "classes" / fingerprint[:16]
    classes.mkdir(parents=True, exist_ok=True)
    classpath = os.pathsep.join(str(p) for p in jars)
    sourcepath = os.pathsep.join(str(p) for p in (output / "overlay", ORIGINAL / "src", ADAPTER / "src"))
    compiler = ([str(javac), "-J-Duser.language=en", "-J-Dfile.encoding=UTF-8"] if javac else
                [str(java), "-Duser.language=en", "-Dfile.encoding=UTF-8", "-m", "jdk.compiler/com.sun.tools.javac.Main"])
    command = [*compiler, "-encoding", "UTF-8", "-d", str(classes), "-cp", classpath,
               "-sourcepath", sourcepath, *map(str, overlays),
               *map(str, sorted((ADAPTER / "src").rglob("*.java")))]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (output / "javac-stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "javac-stderr.txt").write_text(result.stderr, encoding="utf-8")
    manifest = dict(inputs, fingerprint=fingerprint, command=command, javac_exit_code=result.returncode,
                    runtime_classpath=os.pathsep.join([str(classes), classpath]))
    (output / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"javac failed; see {output / 'javac-stderr.txt'}\n{result.stderr[-5000:]}")
    return java, manifest["runtime_classpath"], manifest
