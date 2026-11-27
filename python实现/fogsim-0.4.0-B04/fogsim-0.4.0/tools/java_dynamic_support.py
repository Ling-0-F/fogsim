"""Build the original dynamic path with strictly additive observation calls.

Unlike the fixed adapter, no constructor, comparator, sampler formula, event
trigger, admission condition or stop condition is replaced. Baseline has no
source overlay. Each edit is anchored exactly once and a unified diff is saved.
"""
from pathlib import Path
import difflib
import hashlib
import json
import os
import shutil
import subprocess
from java_support import ROOT, ORIGINAL, reference_jdk, sha


EDITS = {
    'mengxu/taskscheduling/MobileDevice.java': [
        ('        int jobID = systemState.getAllNumJobsReleased();',
         '        fogsim.adapter.DynamicCapture.beforeClear(this, DAGTypeID, daxpath, releaseTime, weight, taskList);\n'),
        ('        boolean couldAdd = systemState.addJobToSystem(job);',
         '\n        fogsim.adapter.DynamicCapture.afterAdmission(this, job, couldAdd);'),
        ('            eventQueue.add(new JobArrivalEvent(job,this));',
         '\n            fogsim.adapter.DynamicCapture.afterGeneratedArrival(this, job);'),
        ('        this.eventQueue.add(event);',
         '\n        fogsim.adapter.DynamicCapture.afterStage(this, event);'),
    ],
    'mengxu/simulation/DynamicSimulation.java': [
        ('            nextEvent.trigger(nextEvent.getMobileDevice()); //nextEvent includes many different types of events',
         '            fogsim.adapter.DynamicCapture.beforeEvent(this);\n'),
        ('            nextEvent.trigger(nextEvent.getMobileDevice()); //nextEvent includes many different types of events',
         '\n            fogsim.adapter.DynamicCapture.afterEvent(this);'),
    ],
}


def observation_overlay(relative, original):
    result = original
    for anchor, addition in EDITS[relative]:
        anchored = '\n' + anchor + '\n'
        if 'afterGeneratedArrival' in addition:
            anchored = '        if(couldAdd){\n            numJobsReleased++;\n//        this.systemState.addAllNumJobsReleased();\n' + anchor + '\n'
        if result.count(anchored) != 1:
            raise RuntimeError(f'expected one observation anchor in {relative}: {anchor}')
        replacement = addition + anchor if 'beforeClear' in addition or 'beforeEvent' in addition else anchor + addition
        if 'afterGeneratedArrival' in addition:
            result = result.replace(anchored, anchored.rstrip('\n') + addition + '\n', 1)
        else:
            result = result.replace(anchored, '\n' + replacement + '\n', 1)
    return result


def compile_dynamic(output, explicit=None):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    executable = explicit or os.environ.get('FOGSIM_JAVA') or shutil.which('java')
    if not executable:
        raise RuntimeError('JDK 17 missing: pass --java or set FOGSIM_JAVA')
    java = Path(executable).resolve()
    version = reference_jdk(java)
    integrity = json.loads((ROOT / 'outputs/source-integrity-v2.json').read_text())['files']
    for relative, expected in integrity.items():
        if sha(ORIGINAL / relative) != expected:
            raise RuntimeError(f'original source changed: {relative}')
    mains = sorted((ROOT / 'tools/java/step4').rglob('*.java'))
    codec = ROOT / 'tools/java/src/fogsim/adapter/Json.java'
    jars = sorted(p for p in (ORIGINAL / 'libraries').glob('*.jar') if 'javadoc' not in p.name)
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in
              [*sorted((ORIGINAL / 'src').rglob('*.java')), *jars, *mains, codec,
               ROOT / 'tools/java_dynamic_support.py', ROOT / 'tools/export_java_dynamic.py',
               ROOT / 'tools/dynamic_export_contract.py']}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    javac = java.with_name('javac.exe' if java.suffix == '.exe' else 'javac')
    compiler = [str(javac)] if javac.is_file() else [str(java), '-m', 'jdk.compiler/com.sun.tools.javac.Main']
    classpath = os.pathsep.join(str(p) for p in jars)
    builds = {}
    for kind in ('baseline', 'observed'):
        folder = output / kind; folder.mkdir(exist_ok=True)
        overlay = folder / 'overlay'; patches = []
        if kind == 'observed':
            for relative in EDITS:
                source = ORIGINAL / 'src' / relative
                original = source.read_text(encoding='utf-8')
                modified = observation_overlay(relative, original)
                target = overlay / relative; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(modified, encoding='utf-8')
                diff = ''.join(difflib.unified_diff(original.splitlines(True), modified.splitlines(True),
                               fromfile=f'original/{relative}', tofile=f'overlay/{relative}'))
                patch = folder / (source.stem + '.patch'); patch.write_text(diff, encoding='utf-8')
                patches.append({'source': relative, 'original_sha256': sha(source),
                                'overlay_sha256': sha(target), 'patch_sha256': sha(patch)})
        classes = folder / 'classes' / fingerprint[:16]; classes.mkdir(parents=True, exist_ok=True)
        sourcepath = os.pathsep.join(map(str, [overlay, ORIGINAL / 'src', ROOT / 'tools/java/step4']))
        command = [*compiler, '-encoding', 'UTF-8', '-cp', classpath, '-sourcepath', sourcepath,
                   '-d', str(classes), *map(str, mains), str(codec)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (folder / 'javac-stdout.txt').write_text(result.stdout)
        (folder / 'javac-stderr.txt').write_text(result.stderr)
        builds[kind] = {'command': command, 'exit_code': result.returncode, 'patches': patches,
                        'classpath': os.pathsep.join([str(classes), classpath])}
        if result.returncode:
            raise RuntimeError(f'{kind} compilation failed: see {folder}/javac-stderr.txt')
    manifest = {'fingerprint': fingerprint, 'reference_jdk': version, 'inputs': hashes,
                'compiler_executable_sha256': sha(javac if javac.is_file() else java),
                'compiler_modules_sha256': sha(java.parent.parent / 'lib/modules') if not javac.is_file() else None,
                'original_integrity_files': len(integrity), 'builds': builds}
    (output / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return java, manifest
