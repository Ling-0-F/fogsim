# S9-B02 完整命令与环境

实际命令的 argv/cwd/环境/退出码/耗时及原stdout/stderr在outputs/step9/B02/commands。原Java编译执行argv与配置在java-final。历史同名运行已保留于initial-*或pre-cli-*；正式检查使用最终source-freeze.json。

源码最终冻结后执行99项专项、45项Java局部对照、单树整套首跑/复跑与新恢复副本5908项回归。schema检查脚本随包：development/S9-B02/check-schemas.py（实际jsonschema版本在schema-final.json）。

## cli-non-object-after.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "evaluate",
    "--rules",
    "outputs/step9/B02/non-object-rules.json",
    "--plan",
    "outputs/step9/B02/pre-cli-single-first/plans/test.json",
    "--output",
    "outputs/step9/B02/non-object-should-not-exist"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 2,
  "duration_seconds": 0.14889004299993758,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "cli-non-object-after.stdout.txt",
  "stderr": "cli-non-object-after.stderr.txt"
}
```

## cli-non-object-before.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "evaluate",
    "--rules",
    "outputs/step9/B02/non-object-rules.json",
    "--plan",
    "outputs/step9/B02/single-first/plans/test.json",
    "--output",
    "outputs/step9/B02/non-object-should-not-exist"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 1,
  "duration_seconds": 0.17866612099987833,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "cli-non-object-before.stdout.txt",
  "stderr": "cli-non-object-before.stderr.txt"
}
```

## components-pre-final-r2.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests/training",
    "-q",
    "--basetemp",
    "outputs/step9/B02/cases-pre-final-r2",
    "--junitxml",
    "outputs/step9/B02/unit-pre-final-r2.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 1,
  "duration_seconds": 19.013447468999857,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"
  },
  "stdout": "components-pre-final-r2.stdout.txt",
  "stderr": "components-pre-final-r2.stderr.txt"
}
```

## components-pre-final.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests/training",
    "-q",
    "--basetemp",
    "outputs/step9/B02/cases-pre-final",
    "--junitxml",
    "outputs/step9/B02/unit-pre-final.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 2,
  "duration_seconds": 0.7181846959997529,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"
  },
  "stdout": "components-pre-final.stdout.txt",
  "stderr": "components-pre-final.stderr.txt"
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
    "outputs/step9/B02/single-first/trial-0001/selected_rule.json",
    "--plan",
    "outputs/step9/B02/single-first/plans/test.json",
    "--output",
    "outputs/step9/B02/independent-selected"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 0.6009790390003218,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src"
  },
  "stdout": "independent-selected.stdout.txt",
  "stderr": "independent-selected.stderr.txt"
}
```

## initial-java-final.json

```json
{
  "argv": [
    "python",
    "tools/check_s9_b02_java.py",
    "--java",
    "/workspace/scratch/bbcb33cd13e3/dependency-tools/jdk-17.0.21+9/bin/java",
    "--output",
    "outputs/step9/B02/java-final"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 8.282395113999883,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "java-final.stdout.txt",
  "stderr": "java-final.stderr.txt"
}
```

## initial-regression.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests",
    "-q",
    "--basetemp",
    "../../work/fogsim-0.4.0/outputs/step9/B02/regression-cases",
    "--junitxml",
    "../../work/fogsim-0.4.0/outputs/step9/B02/regression.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/regression/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 155.25944797300008,
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

## initial-single-first.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "train",
    "--config",
    "configs/training/smoke-single.json",
    "--output",
    "outputs/step9/B02/single-first"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 28.156944192000083,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "single-first.stdout.txt",
  "stderr": "single-first.stderr.txt"
}
```

## initial-unit-final.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests/training",
    "-q",
    "--basetemp",
    "outputs/step9/B02/cases-final",
    "--junitxml",
    "outputs/step9/B02/unit-final.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 1,
  "duration_seconds": 18.71417648500028,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"
  },
  "stdout": "unit-final.stdout.txt",
  "stderr": "unit-final.stderr.txt"
}
```

## java-final.json

```json
{
  "argv": [
    "python",
    "tools/check_s9_b02_java.py",
    "--java",
    "/workspace/scratch/bbcb33cd13e3/dependency-tools/jdk-17.0.21+9/bin/java",
    "--output",
    "outputs/step9/B02/java-final"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 8.875320197000292,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "java-final.stdout.txt",
  "stderr": "java-final.stderr.txt"
}
```

## locked-install.json

```json
{
  "argv": [
    "python",
    "-m",
    "pip",
    "install",
    "--no-index",
    "--find-links",
    "development/S9-B02/wheels",
    "--require-hashes",
    "-r",
    "development/S9-B02/requirements-train.lock",
    "--target",
    "../../dependency-tools/b02-locked",
    "--ignore-installed",
    "--report",
    "outputs/step9/B02/dependency-install.json"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 2.13672824699961,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "locked-install.stdout.txt",
  "stderr": "locked-install.stderr.txt"
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
    "configs/training/smoke-single.json",
    "--output",
    "outputs/step9/B02/single-first"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 2,
  "duration_seconds": 0.3346559020001223,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "output-protection.stdout.txt",
  "stderr": "output-protection.stderr.txt"
}
```

## pre-cli-acceptance.json

```json
{
  "argv": [
    "python",
    "tools/accept_s9_b02.py"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 15.9429076360002,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "acceptance.stdout.txt",
  "stderr": "acceptance.stderr.txt"
}
```

## pre-cli-independent-selected.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "evaluate",
    "--rules",
    "outputs/step9/B02/single-first/trial-0001/selected_rule.json",
    "--plan",
    "outputs/step9/B02/single-first/plans/test.json",
    "--output",
    "outputs/step9/B02/independent-selected"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 0.6488294590003534,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src"
  },
  "stdout": "independent-selected.stdout.txt",
  "stderr": "independent-selected.stderr.txt"
}
```

## pre-cli-java-final.json

```json
{
  "argv": [
    "python",
    "tools/check_s9_b02_java.py",
    "--java",
    "/workspace/scratch/bbcb33cd13e3/dependency-tools/jdk-17.0.21+9/bin/java",
    "--output",
    "outputs/step9/B02/java-final"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 8.45089778900001,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "java-final.stdout.txt",
  "stderr": "java-final.stderr.txt"
}
```

## pre-cli-regression-final.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests",
    "-q",
    "--basetemp",
    "../../work/fogsim-0.4.0/outputs/step9/B02/regression-final-cases",
    "--junitxml",
    "../../work/fogsim-0.4.0/outputs/step9/B02/regression-final.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/regression-final/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 150.2031231660003,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "FOGSIM_JAVA": "/workspace/scratch/bbcb33cd13e3/dependency-tools/jdk-17.0.21+9/bin/java"
  },
  "stdout": "regression-final.stdout.txt",
  "stderr": "regression-final.stderr.txt"
}
```

## pre-cli-single-first.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "train",
    "--config",
    "configs/training/smoke-single.json",
    "--output",
    "outputs/step9/B02/single-first"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 29.62816650600007,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "single-first.stdout.txt",
  "stderr": "single-first.stderr.txt"
}
```

## pre-cli-single-repeat.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "train",
    "--config",
    "configs/training/smoke-single.json",
    "--output",
    "outputs/step9/B02/single-repeat"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 29.108085771999868,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "single-repeat.stdout.txt",
  "stderr": "single-repeat.stderr.txt"
}
```

## pre-cli-unit-final.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests/training",
    "-q",
    "--basetemp",
    "outputs/step9/B02/cases-final",
    "--junitxml",
    "outputs/step9/B02/unit-final.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 19.928717376999884,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"
  },
  "stdout": "unit-final.stdout.txt",
  "stderr": "unit-final.stderr.txt"
}
```

## regression-final.json

```json
{
  "argv": [
    "python",
    "-m",
    "pytest",
    "tests",
    "-q",
    "--basetemp",
    "../../work/fogsim-0.4.0/outputs/step9/B02/regression-final-cases",
    "--junitxml",
    "../../work/fogsim-0.4.0/outputs/step9/B02/regression-final.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/regression-cli/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 156.5021377830003,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:../../work/fogsim-0.4.0/.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "FOGSIM_JAVA": "/workspace/scratch/bbcb33cd13e3/dependency-tools/jdk-17.0.21+9/bin/java"
  },
  "stdout": "regression-final.stdout.txt",
  "stderr": "regression-final.stderr.txt"
}
```

## schema-final.json

```json
{
  "argv": [
    "python",
    "development/S9-B02/check-schemas.py"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 0.42333526499987784,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "schema-final.stdout.txt",
  "stderr": "schema-final.stderr.txt"
}
```

## single-first.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "train",
    "--config",
    "configs/training/smoke-single.json",
    "--output",
    "outputs/step9/B02/single-first"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 29.88962344599986,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "single-first.stdout.txt",
  "stderr": "single-first.stderr.txt"
}
```

## single-repeat.json

```json
{
  "argv": [
    "python",
    "-m",
    "fogsim.training.cli",
    "train",
    "--config",
    "configs/training/smoke-single.json",
    "--output",
    "outputs/step9/B02/single-repeat"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 30.866463871999713,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "single-repeat.stdout.txt",
  "stderr": "single-repeat.stderr.txt"
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
    "outputs/step9/B02/cases-final",
    "--junitxml",
    "outputs/step9/B02/unit-final.xml"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 20.672333694999907,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"
  },
  "stdout": "unit-final.stdout.txt",
  "stderr": "unit-final.stderr.txt"
}
```

## wheel-build-final.json

```json
{
  "argv": [
    "python",
    "-m",
    "pip",
    "wheel",
    "--no-deps",
    "--no-build-isolation",
    ".",
    "--wheel-dir",
    "development/S9-B02/dist"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 5.786809544999869,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "wheel-build-final.stdout.txt",
  "stderr": "wheel-build-final.stderr.txt"
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
    ".",
    "--wheel-dir",
    "development/S9-B02/dist"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 6.0433945330000824,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "wheel-build.stdout.txt",
  "stderr": "wheel-build.stderr.txt"
}
```

## wheel-install-final.json

```json
{
  "argv": [
    "python",
    "-m",
    "pip",
    "install",
    "--no-deps",
    "--target",
    "../../dependency-tools/b02-cli-installed",
    "development/S9-B02/dist/fogsim_reproduction-0.4.0-py3-none-any.whl"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 3.767591437000192,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "wheel-install-final.stdout.txt",
  "stderr": "wheel-install-final.stderr.txt"
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
    "../../dependency-tools/b02-installed",
    "development/S9-B02/dist/fogsim_reproduction-0.4.0-py3-none-any.whl"
  ],
  "cwd": "/workspace/scratch/bbcb33cd13e3/work/fogsim-0.4.0",
  "exit_code": 0,
  "duration_seconds": 4.283933122000235,
  "python": "3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]",
  "platform": "Linux-6.18.57-x86_64-with-glibc2.41",
  "environment": {
    "PYTHONPATH": "src:tools:.b02-deps"
  },
  "stdout": "wheel-install.stdout.txt",
  "stderr": "wheel-install.stderr.txt"
}
```

## 来源准备与清理

从当前B01-source-dedup附件独立解压，build_source_distribution.py verify检查11662文件；restore_sources.py按摘要dry-run/restore/verify恢复3373成员。字节/摘要在preparation/source-attachments.json，基线检查在preparation/baseline.json。当前src没有被旧来源覆盖。

DEAP及实际传递依赖通过精确锁和轮子重新离线安装，--require-hashes结果见locked-install记录与dependency-install.json。JDK17下载版本摘要沿用B01锁，实际新编译环境见java-final/build/environment.json。三个完整旧回归分别在独立恢复目录进行；新结果在legacy-initial、legacy-final、legacy-cli-final，原历史证据不被覆盖。

pip wheel产生的build与egg-info已清理；最终source-freeze核验无差异。CLI非对象输入修复前退出1、修复后退出2的原记录都保留。完整配置正式首跑/复跑的416条与先前624条额外同规模运行分列；未执行双树与论文规模。
