# S9-B03 命令与环境

主目录outputs/step9/B03/commands保存argv/cwd/有限环境、退出码、耗时、原stdout/stderr。Java源快照、共同输入和编译/运行原记录在java-final。完整回归使用独立恢复副本；新生成的旧模式结果另存legacy-current及索引，历史证据不覆盖。

## 来源准备

从当前来源B02 ZIP独立解压到B03工作目录，读取B02报告/协议/正式acceptance作为既定结论。执行restore_sources.py restore --source-dir 当前来源目录，恢复索引三组。没有重新运行B02原包或其完整正式双seed配置确认同结果。B03修改后的兼容检查属于新源码检查。

## 中断与工程规模调整

components-dev在35项已完成后，首个本地双树动态评估耗时过长，Ctrl-C结束命令（130）；最后提交的计划/个体/活动配置保留，不能当完整结果。另用development/S9-B03/diagnose-run-initial.py在3秒转储真实堆栈、5秒受控中止并保存partial和异常；最初脚本随后加可选输出参数，初版原源码另存。轻量诊断的result/input立即移到diagnostic-light并附说明，原partial/exception未覆盖。精确场景差异见PLAN.md及initial-scene-configs。

一次计数案例的测试断言把subtree来源误当parent来源，发生KeyError，改为按字段类型读取后通过；没有改生产算子。一次wheel命令缺本地路径./标记失败，保留原stdout/stderr并以正确路径构建。正式冻结后生产源码未改。

## acceptance.json

```json
{
  "argv": [
    "python",
    "tools/accept_s9_b03.py"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 11.903056188999471,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "acceptance.stdout.txt",
  "stderr": "acceptance.stderr.txt"
}
```

## components-dev-light.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests/training/test_b03.py",
    "-q",
    "--basetemp",
    "outputs/step9/B03/cases-dev-light",
    "--junitxml",
    "outputs/step9/B03/unit-dev-light.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 7.076681341999574,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"
  },
  "stdout": "components-dev-light.stdout.txt",
  "stderr": "components-dev-light.stderr.txt"
}
```

## components-dev.interruption.json

```json
{
  "classification": "CONTROLLER_CANCELLED_DIAGNOSTIC",
  "exit_code": 130,
  "reason": "single local diagnostic trial exceeded reasonable time; Ctrl-C delivered to test command, not a domain infeasibility",
  "capture_complete": false,
  "last_committed_evaluation": "cases-dev/test_real_dual_trial_shared_se0/trial/evaluations/000000/evaluation.json",
  "last_completed_tests": 35
}
```

## counts-dev.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests/training/test_b03.py::test_breeding_same_parent_exclusive_cross_call_counts_and_tail",
    "-q",
    "--basetemp",
    "outputs/step9/B03/counts-dev",
    "--junitxml",
    "outputs/step9/B03/counts-dev.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 1,
  "duration_seconds": 0.5735009269992588,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"
  },
  "stdout": "counts-dev.stdout.txt",
  "stderr": "counts-dev.stderr.txt"
}
```

## diagnostic-light.json

```json
{
  "argv": [
    "python",
    "development/S9-B03/diagnose-run.py"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 0.4204130369998893,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "diagnostic-light.stdout.txt",
  "stderr": "diagnostic-light.stderr.txt"
}
```

## diagnostic.json

```json
{
  "argv": [
    "python",
    "development/S9-B03/diagnose-run.py"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 1,
  "duration_seconds": 7.73974631999954,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "diagnostic.stdout.txt",
  "stderr": "diagnostic.stderr.txt"
}
```

## dual-first.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "train",
    "--config",
    "configs/training/smoke-dual.json",
    "--output",
    "outputs/step9/B03/dual-first"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 25.672903585000313,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "dual-first.stdout.txt",
  "stderr": "dual-first.stderr.txt"
}
```

## dual-repeat.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "train",
    "--config",
    "configs/training/smoke-dual.json",
    "--output",
    "outputs/step9/B03/dual-repeat"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 24.23450452200086,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "dual-repeat.stdout.txt",
  "stderr": "dual-repeat.stderr.txt"
}
```

## independent-selected.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "evaluate",
    "--rules",
    "outputs/step9/B03/dual-first/trial-0001/selected_rule.json",
    "--plan",
    "outputs/step9/B03/dual-first/plans/test.json",
    "--output",
    "outputs/step9/B03/independent-selected"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 0.46798711300107243,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src"
  },
  "stdout": "independent-selected.stdout.txt",
  "stderr": "independent-selected.stderr.txt"
}
```

## java-dev.json

```json
{
  "argv": [
    "python",
    "tools/check_s9_b03_java.py",
    "--java",
    "/workspace/scratch/bbcb33cd13e3/dependency-tools/jdk-17.0.21+9/bin/java",
    "--output",
    "outputs/step9/B03/java-dev"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 7.329851960999804,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "java-dev.stdout.txt",
  "stderr": "java-dev.stderr.txt"
}
```

## java-final.json

```json
{
  "argv": [
    "python",
    "tools/check_s9_b03_java.py",
    "--java",
    "/workspace/scratch/bbcb33cd13e3/dependency-tools/jdk-17.0.21+9/bin/java",
    "--output",
    "outputs/step9/B03/java-final"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 7.419076935999328,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "java-final.stdout.txt",
  "stderr": "java-final.stderr.txt"
}
```

## output-protection.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "train",
    "--config",
    "configs/training/smoke-dual.json",
    "--output",
    "outputs/step9/B03/dual-first"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 2,
  "duration_seconds": 0.2880643379994581,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "output-protection.stdout.txt",
  "stderr": "output-protection.stderr.txt"
}
```

## preflight-final.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "validate",
    "--config",
    "configs/training/smoke-dual.json",
    "--output",
    "outputs/step9/B03/preflight-final"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 0.18812368299950322,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "preflight-final.stdout.txt",
  "stderr": "preflight-final.stderr.txt"
}
```

## regression.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests",
    "-q",
    "--basetemp",
    "../../b03/fogsim-0.4.0/outputs/step9/B03/regression-cases",
    "--junitxml",
    "../../b03/fogsim-0.4.0/outputs/step9/B03/regression.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03-regression/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 158.96054967399868,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "FOGSIM_JAVA": "/workspace/scratch/bbcb33cd13e3/dependency-tools/jdk-17.0.21+9/bin/java"
  },
  "stdout": "regression.stdout.txt",
  "stderr": "regression.stderr.txt"
}
```

## schema-final.json

```json
{
  "argv": [
    "python",
    "development/S9-B03/check-schemas.py"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 0.38838985199981835,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "schema-final.stdout.txt",
  "stderr": "schema-final.stderr.txt"
}
```

## training-dev.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests/training",
    "-q",
    "--basetemp",
    "outputs/step9/B03/training-dev",
    "--junitxml",
    "outputs/step9/B03/training-dev.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 26.362034897998456,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"
  },
  "stdout": "training-dev.stdout.txt",
  "stderr": "training-dev.stderr.txt"
}
```

## unit-final.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests/training",
    "-q",
    "--basetemp",
    "outputs/step9/B03/cases-final",
    "--junitxml",
    "outputs/step9/B03/unit-final.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 26.571417982999264,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"
  },
  "stdout": "unit-final.stdout.txt",
  "stderr": "unit-final.stderr.txt"
}
```

## wheel-build-initial.json

```json
{
  "argv": [
    "python",
    "-m",
    "pip",
    "wheel",
    "--no-deps",
    "--no-build-isolation",
    "b03-wheel-source",
    "--wheel-dir",
    "b03/fogsim-0.4.0/development/S9-B03/dist"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3",
  "exit_code": 1,
  "reason": "local directory missing ./ marker; corrected wheel-build.json uses ./b03-wheel-source"
}
```

## wheel-build.json

```json
{
  "argv": [
    "python",
    "-m",
    "pip",
    "wheel",
    "--no-deps",
    "--no-build-isolation",
    "./b03-wheel-source",
    "--wheel-dir",
    "b03/fogsim-0.4.0/development/S9-B03/dist"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3",
  "exit_code": 0,
  "duration_seconds": 4.199715279999509,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {},
  "stdout": "wheel-build.stdout.txt",
  "stderr": "wheel-build.stderr.txt"
}
```

## wheel-install.json

```json
{
  "argv": [
    "python",
    "-m",
    "pip",
    "install",
    "--no-deps",
    "--target",
    "../../dependency-tools/b03-installed",
    "development/S9-B03/dist/fogsim_reproduction-0.4.0-py3-none-any.whl"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/b03/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 4.362763574999917,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps"
  },
  "stdout": "wheel-install.stdout.txt",
  "stderr": "wheel-install.stderr.txt"
}
```

