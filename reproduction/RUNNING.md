# 重跑实验

以下 PowerShell 命令从仓库根目录执行，使用 Python 3.12 和 JDK 17。两份分发包足以完成这里列出的实验和对照。原 Java 源码、依赖及工作流 XML 在 references 包中。

```powershell
$repo = (Get-Location).Path
$expDir = Join-Path $repo 'reproduction'
$workDir = Join-Path $repo '.venv/fogsim-study'
python -m venv .venv
$py = (Resolve-Path '.venv/Scripts/python.exe').Path
& $py -m zipfile -e 'python实现/fogsim-0.4.0-B04.zip' $workDir
& $py -m zipfile -e 'python实现/fogsim-0.4.0-B04-references.zip' $workDir
Set-Location (Join-Path $workDir 'fogsim-0.4.0')
& $py -m pip install 'deap==1.4.4' 'numpy==2.5.4' 'moocore==0.3.2' 'pytest==9.2.0'
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = "$(Join-Path $PWD 'src');$(Join-Path $PWD 'tools')"
$env:OPENBLAS_NUM_THREADS = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$dax = (Resolve-Path 'references/java/Fog-Computing-multiDeviceDebug/src/mengxu/dax').Path
$out = Join-Path $workDir 'new-results'
New-Item -ItemType Directory -Path $out
```

**基础和跨语言检查。** 把下例的 JDK 路径替换为本机的 JDK 17。最后两个命令验证实验使用的七种基线和快速 GP 求值路径。每次使用新的输出目录。

```powershell
$env:FOGSIM_JAVA = 'C:\Program Files\Java\jdk-17\bin\java.exe'
$env:JAVA_TOOL_OPTIONS = '-Dsun.stderr.encoding=UTF-8 -Dsun.stdout.encoding=UTF-8 -Dfile.encoding=UTF-8'
& $py -m pytest -q tests/unit/test_events.py tests/unit/test_dax.py tests/unit/test_dynamic_statistics.py tests/unit/test_queue_lifecycle.py tests/unit/test_workflow_generation.py tests/integration/test_generated_kernel.py tests/gp/test_features.py --junitxml="$out/basic.xml"
& $py tools/run_v2_acceptance.py --output "$out/fixed"
& $py tools/validate_stage_d_b07.py --phase dynamic --java $env:FOGSIM_JAVA --output "$out/dynamic"
& $py tools/check_s9_b03_java.py --java $env:FOGSIM_JAVA --output "$out/operators"
& $py "$expDir/check_baselines.py" --dax $dax --out "$out/baseline-check"
& $py "$expDir/check_baselines.py" --scale small --devices 2 --seed 90000 --results-csv "$expDir/results/baselines.csv" --dax $dax --out "$out/baseline-check-small2"
& $py "$expDir/check_kernel.py" --cases data/cases --out "$out/gp-kernel.json"
```

**论文场景。** 以下三组运行产生本文报告的所有测试数据。工作进程数量只影响用时。基线程序可用 `--methods` 分组运行，合并时保留一行表头即可。本次运行按 FCFS、MaxMin、MinMin 与其余四种方法分成两组。

```powershell
& $py "$expDir/run_baselines.py" --dax $dax --out "$out/baselines.csv" --workers 5
& $py "$expDir/run_mtgp.py" --dax $dax --out "$out/pilot" --workers 5
& $py "$expDir/run_mtgp.py" --profile long --scales small --devices 1 --dax $dax --out "$out/long" --workers 3
& $py "$expDir/analyze.py" --results $out
```

`summary.csv` 每行是一个场景与方法。每个 MTGP 试次的 JSON 给出各代训练实例种子、每代最优规则、候选验证成绩和最终规则。表达式对按「排序树、路由树」存储。相邻的 CSV 给出该规则在预先指定的 30 个测试实例上的成绩。分析脚本检查预期场景、规则选择、种子覆盖、工作流计数和事件数，然后从原始记录重新计算汇总。

差值图可用 `python reproduction/plot.py --results reproduction/results` 从汇总表重建。此命令从仓库根目录运行，需要 Matplotlib 和 NumPy。

**表 VI 规模入口。** `run_mtgp.py --profile paper` 采用 1000 个体、51 代、10 精英和每场景 30 个演化种子。其余实例生成与验证协议沿用本实验的取值。九场景合计 13,770,000 个体代训练位置，另有验证与测试；同代重复规则共享一次适应度计算。本次交付实际执行了 `pilot` 和单场景 `long` 两个配置。Linux 可使用相同的 Python 脚本，环境变量 PYTHONPATH 的路径分隔符改为冒号。

同一入口可用 `--engine cuda` 或 `--engine musa` 进行 GPU 评价。固定 `--profile paper --scales small --devices 1`，RTX 3080 Ti 实测使用 `--workers 8 --lanes 32`，MTT S4000 使用 `--workers 2 --lanes 64`。可用 `--first-trial 26 --trial-count 1` 单独重跑第 26 个试次。两种 Linux 编译命令、Python 参考分数校验、各 30 次的完整记录和出图命令见 [GPU 搜索](gpu/README.md)。
