# 雾计算工作流调度复现：0.2 第一阶段（0.2.0a1）

本项目按提供的设计文档及 Xu 等（2023）配套 `multiDeviceDebug` Java 源码实现固定实例模拟器。Python 源码位于 `src/fogsim/`，没有运行时第三方依赖；本次新增 Java 固定实例适配器和离线轨迹对照工具。

已经实现固定 JSON 加载与校验、独立运行对象图、四类事件、两层 Java 兼容堆、FCFS 路由与排序、固定资源调试规则、预约及去重保护、事件/决策快照、失败结果和固定实例重跑。当前完整验收范围是单任务及链式工作流。

本次验证：**145项测试通过，0失败、0跳过**。四个现有配置的 Java/Python 固定模式对照通过，共22条事件、8次决策；首个调度差异均为 `null`。0.1 的4组行为结果保持不变，原有3,797条输出的局部oracle也继续通过。见 [验收记录](docs/VALIDATION.md) 和 [对照总报告](outputs/parity/summary.json)。

这是0.2的第一阶段。复杂DAG、完整竞争与同刻交错验收尚未完成；多设备完整集成是后续扩展，未自动增加为本轮必需项。DAX/随机生成、GP和论文规模实验仍未实现。本次对照结论只覆盖指定参考环境和四个现有配置。

## 本次新增：Java/Python 对照

```powershell
.\.venv\Scripts\python.exe tools/run_fixed_parity.py --java "C:\path\to\jdk-17\bin\java.exe"
```

本机项目内已有参考JDK时，可省略 `--java`；工具也支持 `FOGSIM_JAVA` 或 PATH。必须使用包含 `javac` 的JDK 17。默认运行4个随附配置；可用 `--config configs/chain_fcfs.json` 选择案例，用 `--output outputs/my_parity` 指定证据目录。

适配器编译原Java调度类，保留原四事件、评分选择、比较器、等待队列、`canAddToQueue` 和设备归并。两份构造函数增量只用于跳过随机采样与隐式setup；固定到达、全输入统计、停止条件和观察日志由独立适配代码负责。Java没有加入Python的 `pending_start` 保护。详细改动和证据边界见 [适配说明](docs/JAVA-FIXED-ADAPTER.md)。

每个案例保存 `java-raw.json`、`python-raw.json`、两份规范化副本、`comparison.json`、输入/配置/ID映射及SHA清单。构建证据包含源码哈希、两份补丁、编译命令和输出。

只对已有轨迹重新比较：

```powershell
.\.venv\Scripts\python.exe -m fogsim.validation.trace_compare outputs/parity/chain_fcfs/python-raw.json outputs/parity/chain_fcfs/java-raw.json --output outputs/parity/chain_fcfs/recompare.json
```

按事件实际顺序比较：事件标识→处理前状态→事件内部交错的决策/发出事件→处理后状态→最终记录。不会排序日志、补齐缺失调用或按时间容差重新配对事件。正常案例首差为 `null`；检测到差异时保存事件序号、阶段、字段路径和两边数值。已保存的 [人工故障注入报告](outputs/parity/fault_injection/comparison.json) 展示首差定位能力，不是实际调度失败。

原始表示差异保留在raw文件：Java未完成时间默认0.0；Java待开始Process由事件观察得到，不是资源预约字段。两项映射在比较报告中明确列出，未完成时间的非零异常和多条待开始事件不会被隐藏。

## 环境与安装

- Python **3.11 或更新版本**；本次实际执行为 Windows x64、CPython **3.12.12**。
- Python 模拟器不需要 Java；测试依赖 `pytest`，本次版本 **9.1.1**。
- Java固定实例适配器及局部oracle使用 **Eclipse Temurin OpenJDK 17.0.16+8**。完整版本及源文件指纹见 [Java 参考说明](docs/JAVA-REFERENCE.md)。编译使用原ZIP随附的依赖jar，无需另外安装Maven或Gradle。

在本 README 所在目录执行（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m fogsim --config configs/chain_remote.json --output outputs/chain_remote.json
.\.venv\Scripts\python.exe -m pytest -q
```

Linux/macOS 将 `.\.venv\Scripts\python.exe` 换成 `.venv/bin/python`。安装后也可使用 `fogsim` 命令。不需激活环境即可执行上述命令。

当前工作目录里的 `.venv` 和参考JDK仅用于本次验证，不放入交付ZIP。交付包包含原Java源文件及非javadoc依赖jar，以便重新编译适配器；解压后请建立Python环境，并指定自己的JDK17。

## 运行实例

| 配置 | 实例/路由 | 手算及实际结果 |
| --- | --- | --- |
| `configs/single_local.json` | 单任务，固定 M0 | A 完成 3；makespan=3 |
| `configs/single_local_release5.json` | 同一任务在 t=5 发布 | A 完成 8；makespan=3 |
| `configs/chain_remote.json` | A→B，固定 E0 | A 完成 6，B 完成 13；makespan=13 |
| `configs/chain_fcfs.json` | 同一 A→B 输入，源码 FCFS | A 在 M0 完成 10，B 在 E0 完成 17；makespan=17 |

```powershell
.\.venv\Scripts\python.exe -m fogsim --config configs/chain_fcfs.json --output outputs/chain_fcfs.json
.\.venv\Scripts\python.exe -m fogsim --instance data/cases/chain_remote.json --fixed-resource E0 --repeat 2 --output outputs/repeat.json
.\.venv\Scripts\python.exe -m fogsim --config configs/chain_remote.json --no-trace --output outputs/no_trace.json
```

`--repeat` 每次重新构建对象图，输出 `runs` 及完整结果是否一致的 `identical`。同一 Engine 的 `run()` 只能调用一次；固定重跑不涉及 RNG 或 seed。

配置中的 `instance` **相对于配置文件所在目录**解析；`--instance` 和 `--output` 相对于命令当前工作目录解析。完整 CLI 帮助：`python -m fogsim --help`。

退出码：0=成功，1=模拟运行失败（输出含原因），2=输入/配置错误。非预期程序异常向调用方抛出。

## Python API

```python
from fogsim import load_fixed_instance, RunConfig, simulate, create_engine

spec = load_fixed_instance("data/cases/chain_remote.json")
config = RunConfig(routing_kind="fixed_resource", fixed_resource_id="E0")
result = simulate(spec, config)
assert result.status == "SUCCEEDED" and result.makespan == 13.0

# 调试时可检查引擎持有的规范对象；每轮建立全新对象。
engine = create_engine(spec, config)
result2 = engine.run()
assert result2.to_dict() == result.to_dict()
```

## 输入与输出契约

实例采用设计 03 的 JSON 字段：`time_unit`、`resources`、`workflows`；工作流内含 `tasks`、`dependencies` 和每项合法候选的 `execution_times`。参考 [链式完整输入](data/cases/chain_remote.json)。

加载器拒绝重复 ID/JSON 键、缺失或多余候选、不合法设备归属、非有限或负时间、非正计算时间、非零本地通信、非法边及环。未知字段直接报错，包括混入输入的运行状态。至少一个移动设备、一个工作流、每个工作流一个任务；布尔值不当作数值时间或整数工作流 ID。

路由候选按合法本地、边缘、云构建；设备及同类型服务器保留输入顺序。服务器数字 ID 为边缘后云，设备另有独立 ID 空间。工作流 ID 不随到达顺序重编号。

结果 JSON 包含：

- `status`、`reason`、`final_clock_time`、完成数量、事件数量及 `makespan`。
- `workflow_records`：发布、实际完成及 flow time。
- `task_records`：实际派发/到达/开始/完成时间；未发生为 `null`。`plan` 单独保存预约时计算的计划时间。
- `compute_finish_time`：由实际开始加 PT 派生的计算结束时刻，**不是第五类事件或已观测计算完成的证明**。
- `events`：实际事件顺序、处理前后状态、新发事件的 owner 与 staging_device、错误。
- `events.actions`：事件内部实际发生的决策与发出事件的交错顺序，仅供对照，不参与调度。
- `decisions`：候选顺序、即时分数、选择、路由轮次、所属事件/决策序号、候选状态与资源快照。

详细日志关闭仍保留必要任务事实；失败运行的 makespan 为 `null`，计划完成时间不会填入实际完成。日志与返回结果都是独立快照，不参与规则或事件决策。

## 调度语义

- FCFS 路由读取原始 `available_time`，排序读取工作流 `release_time`；小分数优先，随后按 release、设备数值 ID、工作流 ID 平分；完全平分保留先遍历项。
- `priority` 使用 Java `Double.compare` 语义；事件时间使用精确普通比较，不用测试容差合并时间。
- 完成后先处理资源等待队列，再对整个工作流就绪列表路由两整轮，使用第二轮结果后派发。
- 上传不占处理器。计算与下载占用 `[start, finish)`；后继即使使用同一服务器仍有其 UT/DT。
- `pending_start` 仅保存待开始 Execution；实际 Start 才更新 `available_time`，旧 Finish 不清他项预约或回写资源时间。
- Server 空队缓存归零；MobileDevice 保留逐项减法残差。两个缓存均保留 Java 加法/减法括号和顺序。
- 同刻事件保留原异常比较分支及两层 `offer/poll`；不添加稳定序号。每处理一条事件前重新归并设备暂存堆。
- 规则情境不含未来工作流索引/数量；共享规范引用采用每次评分前后对象图检查。该接口面向可信规则扩展，不是运行任意不可信 Python 的安全沙箱。

## 验证与证据

```powershell
.\.venv\Scripts\python.exe tools/validate.py
```

该命令执行测试（含固定Java对照）、四组Python实例并生成 `outputs/validation-manifest.json`，保存源码快照哈希、输入哈希、配置/顺序映射及真实结果。详见 [验收记录](docs/VALIDATION.md)。原始证据包括 `outputs/pytest-console.txt`、`outputs/pytest-results.xml`、`outputs/parity/` 和 `outputs/java_oracle/`。0.1证据保留在 `outputs/v0.1/`，旧的 `fogsim-0.1.0.zip` 保持不变。

Java 局部对照可独立执行：

```powershell
.\.venv\Scripts\python.exe tools/run_java_oracle.py --java "C:\path\to\jdk-17\bin\java.exe"
```

pytest自动查找本地参考JDK或PATH中的Java；也可设置 `FOGSIM_JAVA`。缺少Java时依赖Java的测试显式skip，不能报告为通过；找到非JDK17时明确报错。以本次保存报告为准，本次没有跳过测试。

oracle 从随附 Java 原文件直接抽取比较器、`priorTo` 和缓存方法，放入只提供数据的最小支架，调用真实 `java.util.PriorityQueue`。它验证指定样例的组件行为，**没有运行完整原 Java 调度器**。

## 文件导航

| 目录/文档 | 内容 |
| --- | --- |
| `src/fogsim/` | 模型、加载、规则、事件、引擎及 CLI |
| `data/cases/`、`configs/` | 固定输入与分离的运行规则 |
| `tests/unit/`、`tests/integration/`、`tests/parity/` | 组件、完整单任务/链式及局部 Java oracle |
| `tools/validate.py`、`tools/run_java_oracle.py` | 完整验证与局部oracle工具 |
| `tools/run_fixed_parity.py`、`tools/java_support.py`、`tools/java/` | 固定Java入口、构建支架、构造补丁及观察代码 |
| `src/fogsim/validation/trace_compare.py` | 不参与调度的逐事件/逐决策对照器 |
| [JAVA-FIXED-ADAPTER](docs/JAVA-FIXED-ADAPTER.md) | 适配改动清单、日志映射、运行证据和限制 |
| [IMPLEMENTATION-NOTES](docs/IMPLEMENTATION-NOTES.md) | 问题、证据、采用方式、影响和待验证事项 |
| [JAVA-REFERENCE](docs/JAVA-REFERENCE.md) | 锁定参考 JDK、源码/二进制指纹及兼容边界 |
| [VALIDATION](docs/VALIDATION.md) | 设计 11 验收映射、实际结果、未执行项目 |
| [SOURCES](docs/SOURCES.md) | 材料可访问性及阅读记录 |
| [java_mapping](docs/java_mapping.md)、[semantics](docs/semantics.md)、[roadmap](docs/roadmap.md) | 实现定位、语义与后续事项 |
| `references/design/` | 12 份原始设计快照，保留原文 |

设计00—07中“尚未编码”等是旧快照。当前实现及验证进度以本README、VALIDATION和IMPLEMENTATION-NOTES为准；08—11的增量设计优先于旧进度描述。交付ZIP不包含完整参考JDK、虚拟环境和原论文副本。
