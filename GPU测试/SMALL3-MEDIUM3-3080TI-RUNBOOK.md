# RTX 3080 Ti GPU 运行手册：Small 3 与 Medium 3

文档日期：2026-11-26

目标：在 NVIDIA RTX 3080 Ti 上使用 CUDA 后端完成 Small 3 和 Medium 3 的 30 次独立论文规模演化，并与现有 CPU 结果逐 trial 比较。

## 1. 实验目标与固定口径

本实验不跑 `pilot`，直接运行 `paper` profile：

| 项目 | 固定值 |
| --- | --- |
| 搜索规模 | 1,000 个体 × 51 代 |
| 独立演化 | 30 个种子，`50001–50030` |
| 精英数 | 10 |
| 锦标赛大小 | 7 |
| 验证种子 | `80000–80002` |
| 测试种子 | `90000–90029` |
| Small 3 | 3 台移动设备、20 台边缘服务器、20 台云服务器 |
| Medium 3 | 3 台移动设备、30 台边缘服务器、30 台云服务器 |
| CUDA 默认并发 | 8 个 trial 进程 |
| CUDA 默认 block 宽度 | 32 threads |

CPU 基线位于：

- Small 3：`result_text/small3-paper-20261120-093754/small3-paper-20261120-093754/`
- Medium 3：`result_text/medium3-paper-128570140/medium3-paper-128570140/`

CPU 基线的 30 次演化汇总：

| 场景 | CPU 测试均值 ± 样本标准差 |
| --- | ---: |
| Small 3 | 1485.9537 ± 61.7999 秒 |
| Medium 3 | 2048.8301 ± 122.5173 秒 |

这里的均值口径为：先对每个 trial 的 30 条测试 makespan 取算术平均，再对 30 个 trial 的均值计算算术平均和样本标准差。

## 2. 租用配置和已知前提

计划租用的实例配置：

| 项目 | 配置 |
| --- | --- |
| GPU | NVIDIA RTX 3080 Ti |
| 显存 | 12 GB |
| GPU 计算能力 | 8.6，编译目标 `sm_86` |
| CPU | Intel Xeon Gold 6248 |
| CPU 配额 | 10 核 |
| 系统内存 | 30 GB |
| 系统盘 | 30 GB |
| 数据盘 | 50 GB |
| 操作系统 | Ubuntu 22.04 |
| 镜像 | Miniconda / Conda3 |
| 镜像默认 Python | 3.11 |
| 镜像 CUDA | 11.8 |

重要前提：

1. **不能直接使用镜像默认的 Python 3.11 环境。** B04 离线训练包固定的是 CPython 3.12 轮子，且此前 CPU 基线也使用 Python 3.12。需要创建独立的 Python 3.12 Conda 环境。
2. 镜像标记 CUDA 11.8 不代表一定安装了带 `nvcc` 的 CUDA Toolkit。开始实验前必须实际执行 `nvcc --version`。
3. CUDA 11.8 可以编译 RTX 3080 Ti 所需的 `sm_86`，但要保留 `--fmad=false`，避免浮点乘加融合改变结果。
4. 两个场景必须串行运行，不能同时争用同一块 GPU。
5. 使用当前 GPU 版本 `reproduction`，不要使用旧的 `reproduction.zip`。旧压缩包没有 GPU 后端。

## 3. 源码与包版本

本次文档对应工作区的基线：

```text
Git commit: bbf1c95fe00717b595017f0b837fddd922311232
```

关键文件 SHA-256：

```text
16c0dc68fd8a0ff5f7be5f8bc955f9ae8127c3eb108960b8a13452c4c3c3fdf4  reproduction/run_mtgp.py
c48b0ca323ed7d804381f711d66be10b902f543ff9bf479922434269bf502481  reproduction/paper.py
8bb81f92a695d7390c530c4bf572d617baada53c814c0040b3bef68694ab445d  reproduction/gpu/fitness.cu
513acc396131ed320b153acb22eff151e8598d13b3adc4160e440e927d40b96f  reproduction/gpu/fitness_core.hpp
88de961757627ef0583f8b0c71e67dc82436d9a168fc2de4d2b50e2e3ce4c10f  reproduction/gpu/fitness_device.hpp
aef8f3716081134ace44c4b633d0a7962a566740057362ef26524a4ac474df5a  reproduction/gpu/trainer.py
050625603620be9f181d35287f24a897a523c671491088529c79336d6cae4daa  fogsim-0.4.0-B04.zip
10b01496e782750a0943c50891123e432f5967fcd6a15cb97a6f48f92b319f08  fogsim-0.4.0-B04-references.zip
```

如果远端源码来自 Git 仓库，还必须记录：

```bash
git rev-parse HEAD
git status --short
```

## 4. 十一歩执行流程

以下命令默认在 AutoDL 数据盘 `/root/autodl-tmp/fogsim-gpu` 下执行。如果实际数据盘路径不同，只替换 `WORK` 变量。

### 第 1 步：建立工作目录和实验记录

```bash
export WORK=/root/autodl-tmp/fogsim-gpu
mkdir -p "$WORK"/archives
mkdir -p "$WORK"/checks
mkdir -p "$WORK"/gpu-build
mkdir -p "$WORK"/logs
mkdir -p "$WORK"/runs
mkdir -p "$WORK"/study

cd "$WORK"
pwd
date -Iseconds | tee checks/runbook-started-at.txt
```

目录用途：

```text
archives/  上传的源码和分发包
checks/    环境、哈希和完整性检查
gpu-build/ CUDA 动态库
logs/      正式运行日志
runs/      Small 3 和 Medium 3 的正式输出
study/     B04 主包与 references 的合并解压目录
```

### 第 2 步：核对租用硬件和系统环境

将以下输出保存到 `checks/environment.txt`：

```bash
{
  date -Iseconds
  hostname
  uname -a
  lscpu
  free -h
  df -h
  nproc
  gcc --version
  nvidia-smi
  nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap \
    --format=csv,noheader
  conda --version
  echo "nvcc:"
  command -v nvcc || true
  nvcc --version || true
} 2>&1 | tee checks/environment.txt
```

通过条件：

- GPU 名称为 RTX 3080 Ti。
- 显存约 12,288 MiB。
- compute capability 为 8.6。
- 系统内存不少于 30 GB。
- 数据盘可用空间不少于 20 GB。
- `nvidia-smi` 正常工作。

`nvcc --version` 如果失败，继续检查常见路径：

```bash
ls -l /usr/local/cuda/bin/nvcc
ls -l /usr/local/cuda-11.8/bin/nvcc
```

如果只在常见路径找到 `nvcc`，可以显式设置：

```bash
export NVCC=/usr/local/cuda-11.8/bin/nvcc
```

如果系统确实没有 `nvcc`，停止后续步骤。需要安装 CUDA 11.8 Toolkit 或换用带 CUDA Toolkit 的镜像，并记录实际版本。

### 第 3 步：上传源码并验证哈希

上传以下内容到远端：

```text
当前仓库中的 reproduction/
fogsim-0.4.0-B04.zip
fogsim-0.4.0-B04-references.zip
```

建议放置为：

```text
$WORK/reproduction/
$WORK/archives/fogsim-0.4.0-B04.zip
$WORK/archives/fogsim-0.4.0-B04-references.zip
```

在 `$WORK` 下验证：

```bash
sha256sum \
  reproduction/run_mtgp.py \
  reproduction/paper.py \
  reproduction/gpu/fitness.cu \
  reproduction/gpu/fitness_core.hpp \
  reproduction/gpu/fitness_device.hpp \
  reproduction/gpu/trainer.py \
  archives/fogsim-0.4.0-B04.zip \
  archives/fogsim-0.4.0-B04-references.zip \
  | tee checks/source-sha256.txt
```

与第 3 节列出的哈希逐项比较。不要使用根目录旧的 `reproduction.zip` 运行 GPU；该压缩包是 CPU-only 快照。

如果上传的是 Git 仓库工作区：

```bash
git rev-parse HEAD | tee checks/source-commit.txt
git status --short | tee checks/source-status.txt
```

### 第 4 步：创建 Python 3.12 Conda 环境

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda create -n fogsim-gpu-py312 python=3.12 pip -y
conda activate fogsim-gpu-py312
python --version | tee "$WORK/checks/python-version.txt"
python -m pip --version | tee "$WORK/checks/pip-version.txt"
```

目标是 CPython 3.12。3.12.16 与当前验证记录一致；若 Conda 无法精确解析该版本，可使用最新的 3.12 补丁版本，但必须记录实际版本。

环境创建后，每次新终端都需要重新执行：

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate fogsim-gpu-py312
```

### 第 5 步：解压 B04 并安装锁定依赖

两个包都包含统一的顶层目录 `fogsim-0.4.0/`，必须解压到同一个新目录：

```bash
cd "$WORK"
python -m zipfile -e archives/fogsim-0.4.0-B04.zip study
python -m zipfile -e archives/fogsim-0.4.0-B04-references.zip study

export STUDY_PKG="$WORK/study/fogsim-0.4.0"
test -f "$STUDY_PKG/development/S9-B02/requirements-train.lock"
test -d "$STUDY_PKG/development/S9-B02/wheels"
```

安装 B04 固定依赖：

```bash
python -m pip install \
  --no-index \
  --require-hashes \
  --find-links "$STUDY_PKG/development/S9-B02/wheels" \
  -r "$STUDY_PKG/development/S9-B02/requirements-train.lock" \
  2>&1 | tee "$WORK/checks/pip-install.txt"

python -m pip check | tee "$WORK/checks/pip-check.txt"
```

验证关键包：

```bash
python - <<'PY' | tee "$WORK/checks/python-packages.txt"
import cffi
import deap
import moocore
import numpy
import platform
import sys

print("python:", sys.version)
print("platform:", platform.platform())
print("cffi:", cffi.__version__)
print("deap:", deap.__version__)
print("moocore:", getattr(moocore, "__version__", "installed"))
print("numpy:", numpy.__version__)
PY
```

### 第 6 步：设置路径、DAX 和线程变量

```bash
cd "$WORK"
export STUDY_PKG="$WORK/study/fogsim-0.4.0"
export PYTHONPATH="$STUDY_PKG/src:$WORK/reproduction"
export PYTHONUTF8=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

export DAX="$STUDY_PKG/references/java/Fog-Computing-multiDeviceDebug/src/mengxu/dax"
export CUDA_LIBRARY="$WORK/gpu-build/libfogsim_cuda.so"
export FOGSIM_CUDA_LIBRARY="$CUDA_LIBRARY"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
```

检查 DAX：

```bash
test -d "$DAX"
find "$DAX" -maxdepth 1 -type f -name '*.xml' | sort | head
find "$DAX" -maxdepth 1 -type f -name '*.xml' | wc -l | tee "$WORK/checks/dax-file-count.txt"
```

检查 Python 导入：

```bash
cd "$WORK/reproduction"
python - <<'PY' | tee "$WORK/checks/imports.txt"
import fogsim
import gpu
from paper import SCALES

print("fogsim:", fogsim.__file__)
print("gpu:", gpu.__file__)
print("SCALES:", SCALES)
PY
```

### 第 7 步：检查 nvcc 并编译 CUDA 11.8 动态库

如果第 2 步没有设置 `NVCC`，使用 PATH 中的版本：

```bash
export NVCC="${NVCC:-$(command -v nvcc)}"
test -n "$NVCC"
"$NVCC" --version | tee "$WORK/checks/nvcc-version.txt"
```

编译：

```bash
mkdir -p "$WORK/gpu-build"

"$NVCC" \
  -O2 \
  -std=c++17 \
  --fmad=false \
  -arch=sm_86 \
  -Xcompiler=-fPIC \
  -shared \
  "$WORK/reproduction/gpu/fitness.cu" \
  -o "$CUDA_LIBRARY" \
  2>&1 | tee "$WORK/checks/nvcc-build.txt"

test -f "$CUDA_LIBRARY"
sha256sum "$CUDA_LIBRARY" | tee "$WORK/checks/cuda-library-sha256.txt"
ldd "$CUDA_LIBRARY"
```

不得删除 `--fmad=false`。该选项用于保持与 Python/B04 参考路径一致的浮点运算顺序。

### 第 8 步：加载 CUDA 库并执行内核门禁

先用 `ctypes` 确认动态库和入口可加载：

```bash
cd "$WORK/reproduction"
python - <<'PY' | tee "$WORK/checks/cuda-load.txt"
import ctypes
import os

path = os.environ["FOGSIM_CUDA_LIBRARY"]
library = ctypes.CDLL(path)
print("loaded:", path)
print("full_fitness:", library.full_fitness)
PY
```

执行已有的固定初代参考检查：

```bash
cd "$WORK/reproduction"
python -m gpu.calibrate \
  --engine cuda \
  --dax "$DAX" \
  --check-only \
  2>&1 | tee "$WORK/checks/cuda-kernel-check.txt"
```

预期输出：

```text
All 1,000 GPU fitness values equal the archived Python reference.
```

这一步不是 Small 3/Medium 3 的 trial，而是确认：

- CUDA Runtime 能加载。
- 内核能启动。
- ABI 和数据布局正常。
- 1,000 个初代适应度与 B04 Python 参考逐值相同。

若这一步失败，不启动正式运行。

### 第 9 步：正式运行 Small 3

固定参数：

```text
engine=cuda
profile=paper
scale=small
devices=3
workers=8
lanes=32
```

先创建可恢复的终端会话，避免断开 SSH 后进程被终止：

```bash
tmux new -s fogsim-gpu
```

如果同名会话已经存在，使用：

```bash
tmux attach -t fogsim-gpu
```

启动：

```bash
cd "$WORK"
source /root/miniconda3/etc/profile.d/conda.sh
conda activate fogsim-gpu-py312

export STUDY_PKG="$WORK/study/fogsim-0.4.0"
export PYTHONPATH="$STUDY_PKG/src:$WORK/reproduction"
export PYTHONUTF8=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export DAX="$STUDY_PKG/references/java/Fog-Computing-multiDeviceDebug/src/mengxu/dax"
export CUDA_LIBRARY="$WORK/gpu-build/libfogsim_cuda.so"
export FOGSIM_CUDA_LIBRARY="$CUDA_LIBRARY"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"

STAMP=$(date +%Y%m%d-%H%M%S)
SMALL_OUT="$WORK/runs/small3-paper-gpu-$STAMP"
SMALL_LOG="$WORK/logs/small3-paper-gpu-$STAMP.log"

(
  echo "START=$(date -Iseconds)"
  python -u reproduction/run_mtgp.py \
    --engine cuda \
    --profile paper \
    --scales small \
    --devices 3 \
    --workers 8 \
    --lanes 32 \
    --dax "$DAX" \
    --out "$SMALL_OUT"
  RC=$?
  echo "GPU_EXIT=$RC"
  echo "END=$(date -Iseconds)"
  exit "$RC"
) > "$SMALL_LOG" 2>&1 &

echo "$!" | tee "$WORK/checks/small3-pid.txt"
echo "$SMALL_OUT" | tee "$WORK/checks/small3-output-path.txt"
echo "$SMALL_LOG" | tee "$WORK/checks/small3-log-path.txt"
```

监控：

```bash
tail -f "$SMALL_LOG"
```

另一个终端可观察：

```bash
nvidia-smi
ps -o pid,ppid,stat,etime,%cpu,%mem,cmd -p "$(cat "$WORK/checks/small3-pid.txt")"
```

只运行一个场景，不要在 Small 3 未结束时启动 Medium 3。

### 第 10 步：检查 Small 3，然后正式运行 Medium 3

Small 3 完成条件：

```bash
grep 'GPU_EXIT=0' "$SMALL_LOG"

find "$SMALL_OUT" -maxdepth 1 -type f -name 'small-3-trial-*.json' | wc -l
find "$SMALL_OUT" -maxdepth 1 -type f -name 'small-3-trial-*.csv' | wc -l
```

两项计数都应为 30。

执行完整性检查：

```bash
cd "$WORK/reproduction"
python - "$SMALL_OUT" small 3 <<'PY' | tee "$WORK/checks/small3-completeness.txt"
import csv
import json
import math
import statistics
import sys
from pathlib import Path

root = Path(sys.argv[1])
scale = sys.argv[2]
devices = int(sys.argv[3])
jsons = sorted(root.glob(f"{scale}-{devices}-trial-*.json"))
expected = set(range(90000, 90030))
assert len(jsons) == 30, f"Expected 30 JSON files, found {len(jsons)}"

means = []
for path in jsons:
    record = json.loads(path.read_text(encoding="utf-8"))
    with path.with_suffix(".csv").open(encoding="utf-8", newline="") as handle:
        tests = list(csv.DictReader(handle))
    assert record["scale"] == scale and record["devices"] == devices
    assert record["population"] == 1000 and record["generations"] == 51
    assert len(record["history"]) == 51
    assert record["validation_seeds"] == [80000, 80001, 80002]
    assert len(record["validation"]) == len({tuple(v["pair"]) for v in record["validation"]})
    selected = [record["selected"]["sequencing"], record["selected"]["routing"]]
    winner = min(record["validation"], key=lambda v: statistics.fmean(v["makespans"]))
    assert selected == winner["pair"]
    assert {int(row["seed"]) for row in tests} == expected
    values = [float(row["makespan"]) for row in tests]
    assert all(math.isfinite(value) and value > 0 for value in values)
    means.append(statistics.fmean(values))

print("trials:", len(means))
print("test_mean:", statistics.fmean(means))
print("test_sd:", statistics.stdev(means))
print("test_min:", min(means))
print("test_max:", max(means))
PY
```

Small 3 通过后再启动 Medium 3：

```bash
cd "$WORK"
source /root/miniconda3/etc/profile.d/conda.sh
conda activate fogsim-gpu-py312

export STUDY_PKG="$WORK/study/fogsim-0.4.0"
export PYTHONPATH="$STUDY_PKG/src:$WORK/reproduction"
export PYTHONUTF8=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export DAX="$STUDY_PKG/references/java/Fog-Computing-multiDeviceDebug/src/mengxu/dax"
export CUDA_LIBRARY="$WORK/gpu-build/libfogsim_cuda.so"
export FOGSIM_CUDA_LIBRARY="$CUDA_LIBRARY"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"

STAMP=$(date +%Y%m%d-%H%M%S)
MEDIUM_OUT="$WORK/runs/medium3-paper-gpu-$STAMP"
MEDIUM_LOG="$WORK/logs/medium3-paper-gpu-$STAMP.log"

(
  echo "START=$(date -Iseconds)"
  python -u reproduction/run_mtgp.py \
    --engine cuda \
    --profile paper \
    --scales medium \
    --devices 3 \
    --workers 8 \
    --lanes 32 \
    --dax "$DAX" \
    --out "$MEDIUM_OUT"
  RC=$?
  echo "GPU_EXIT=$RC"
  echo "END=$(date -Iseconds)"
  exit "$RC"
) > "$MEDIUM_LOG" 2>&1 &

echo "$!" | tee "$WORK/checks/medium3-pid.txt"
echo "$MEDIUM_OUT" | tee "$WORK/checks/medium3-output-path.txt"
echo "$MEDIUM_LOG" | tee "$WORK/checks/medium3-log-path.txt"
```

监控：

```bash
tail -f "$MEDIUM_LOG"
```

Medium 3 完成后执行同样检查，将脚本参数替换为：

```bash
python - "$MEDIUM_OUT" medium 3 <<'PY'
```

其余脚本内容与 Small 3 相同。最终应得到：

- 30 个 `medium-3-trial-*.json`。
- 30 个 `medium-3-trial-*.csv`。
- 日志末尾 `GPU_EXIT=0`。

### 第 11 步：汇总、CPU/GPU 对照和归档

先记录所有 GPU 结果哈希：

```bash
find "$SMALL_OUT" -maxdepth 1 -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > "$WORK/checks/small3-gpu-results.sha256"

find "$MEDIUM_OUT" -maxdepth 1 -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > "$WORK/checks/medium3-gpu-results.sha256"
```

计算与 CPU 基线相同的 30-trial 汇总：

```bash
cd "$WORK/reproduction"
python - "$SMALL_OUT" "$MEDIUM_OUT" <<'PY' | tee "$WORK/checks/gpu-summary.txt"
import csv
import json
import statistics
import sys
from pathlib import Path

for root_text, scale in zip(sys.argv[1:], ("small", "medium")):
    root = Path(root_text)
    trials = []
    for path in sorted(root.glob(f"{scale}-3-trial-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        with path.with_suffix(".csv").open(encoding="utf-8", newline="") as handle:
            values = [float(row["makespan"]) for row in csv.DictReader(handle)]
        trials.append(statistics.fmean(values))
    print(scale, "3")
    print("  trials:", len(trials))
    print("  test_mean:", statistics.fmean(trials))
    print("  test_sd:", statistics.stdev(trials))
    print("  test_min:", min(trials))
    print("  test_max:", max(trials))
PY
```

### CPU/GPU 判定

将 CPU 的 30 个 trial 和 GPU 的 30 个 trial 按 `trial`、`evolution_seed` 和测试 seed 配对。

先把两份 CPU 基线上传或复制到 GPU 实例。建议放置为：

```bash
export CPU_SMALL_DIR="$WORK/cpu-baseline/small3"
export CPU_MEDIUM_DIR="$WORK/cpu-baseline/medium3"
test -d "$CPU_SMALL_DIR"
test -d "$CPU_MEDIUM_DIR"
```

其中：

```text
Small CPU 基线原目录：result_text/small3-paper-20261120-093754/small3-paper-20261120-093754
Medium CPU 基线原目录：result_text/medium3-paper-128570140/medium3-paper-128570140
```

Medium CPU 基线在 `trial-*` 子目录中，GPU 输出是平铺文件，因此不能直接对整个目录执行 `diff -rq`。使用下面的脚本按文件名配对，逐字节检查 JSON 和 CSV：

```bash
python - "$CPU_SMALL_DIR" "$SMALL_OUT" "$CPU_MEDIUM_DIR" "$MEDIUM_OUT" <<'PY'
import sys
from pathlib import Path

pairs = (
    ("small", Path(sys.argv[1]), Path(sys.argv[2]), "small-3-trial-"),
    ("medium", Path(sys.argv[3]), Path(sys.argv[4]), "medium-3-trial-"),
)

for label, cpu_root, gpu_root, prefix in pairs:
    for suffix in (".json", ".csv"):
        cpu_files = {path.name: path for path in cpu_root.rglob(prefix + "*" + suffix)}
        gpu_files = {path.name: path for path in gpu_root.rglob(prefix + "*" + suffix)}
        assert len(cpu_files) == 30, (label, suffix, "CPU count", len(cpu_files))
        assert len(gpu_files) == 30, (label, suffix, "GPU count", len(gpu_files))
        assert set(cpu_files) == set(gpu_files), (label, suffix, "filenames differ")
        differences = [
            name
            for name in sorted(cpu_files)
            if cpu_files[name].read_bytes() != gpu_files[name].read_bytes()
        ]
        print(label, suffix, "files=30", "byte_equal=", not differences)
        if differences:
            print("  first_differences:", differences[:5])
PY
```

判定顺序：

1. JSON 和 CSV 全部逐字节相同：可以判定 CPU/GPU 的规则演化、验证选择、测试 makespan 和输出序列一致。
2. 全部字段语义相同但仅有格式差异：比较解析后的 JSON 和 CSV 字段，确认浮点值完全相同。
3. 出现差异时，先定位最早的 trial 和 generation，比较该代最佳规则、`unique` 数和训练 makespan。
4. 如果训练轨迹相同而测试数值不同，检查测试 seed、输入任务数、事件数以及浮点运算语义。

不要只比较最终 30-trial 均值。均值接近不能证明过程相同；必须检查逐 trial 记录。

最后归档：

```bash
cd "$WORK"
ARCHIVE_STAMP=$(date +%Y%m%d-%H%M%S)
ARCHIVE="$WORK/fogsim-gpu-evidence-$ARCHIVE_STAMP.tar.gz"

tar -czf "$ARCHIVE" checks logs runs

sha256sum "$ARCHIVE"
```

归档中应包含：

- 环境快照。
- Python、依赖和 nvcc 版本。
- 源码和分发包哈希。
- CUDA 动态库哈希。
- 两个正式运行日志。
- 两套 JSON/CSV。
- 汇总和完整性检查输出。

## 5. 运行期间禁止事项

- 不要在 Small 3 未完成时同时启动 Medium 3。
- 不要修改 `--profile paper`、场景、seed 范围或测试集。
- 不要在运行中修改源码、B04 包或 CUDA 库。
- 不要复用非空 `--out` 目录。
- 不要把旧 `reproduction.zip` 当作 GPU 代码上传。
- 不要删除 `--fmad=false`。
- 不要根据测试集选冠军；最终规则只能由验证集选择。

## 6. 预期故障与处理

### `Cannot load .../libfogsim_cuda.so`

检查：

```bash
file "$FOGSIM_CUDA_LIBRARY"
ldd "$FOGSIM_CUDA_LIBRARY"
echo "$LD_LIBRARY_PATH"
```

确认 `FOGSIM_CUDA_LIBRARY` 是绝对路径，且 `libcudart` 可解析。

### `nvcc: command not found`

停止实验，查找 `/usr/local/cuda*/bin/nvcc`。找不到时安装 CUDA 11.8 Toolkit 或更换镜像。

### CUDA out of memory

保留已有日志，不覆盖原目录。用新的输出目录将 `--workers` 从 8 降为 6 后重跑。先检查是否误把两个场景同时启动。

### CPU 内存不足或系统明显过载

保留日志，用新的输出目录将 `--workers` 降为 6。不要修改 `lanes` 或算法语义。

### 结果数量不足

确认日志是否出现 `GPU_EXIT=0`。缺失 trial 时保留原目录，不要手工拼接结果；在新目录重跑，并记录原因。
