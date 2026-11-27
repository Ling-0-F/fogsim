# 雾计算工作流调度复现：0.2.1 step7 开发快照

> **step7 当前状态**：工作流级实际边映射清理、三种动态重复模式与重放独立游标、完整新CLI及Python独立输入导出已实现。V20/V21及完整V01的本轮实际结果见 [第7步记录](docs/STEP7-PROGRESS.md) 与 `outputs/step7/current-validation.json`。旧固定API/CLI/repeat、冻结调度及RNG语义保持。

> step6 历史快照：生产动态重放、严格输入校验、参考/复用模式限制、覆盖诊断及旧固定投影已实现；复用第5步真实动态内核。127项新增、Python单元/集成共797项通过。本轮V17–V19逐例结果、Java实际执行范围、命令及边界见[第6步记录](docs/STEP6-PROGRESS.md)和`outputs/step6/current-validation.json`。实际边清理、完整CLI/批次和完整V01留第7步。

> step5 历史快照：集中接纳、动态 Arrival、Java 兼容统计、明确失败和 Context 生命周期已实现。80 项新增及 Python 共 670 项通过；50 项原 Java 探针、9 个受控业务案例通过。API、诊断保护的验证范围和参考字段勘误见 [第 5 步记录](docs/STEP5-PROGRESS.md)。其后续实现与当前状态以第6步记录为准。

> step4 历史快照：Java 原动态输入导出与 V16 已完成。9 个案例通过观察无干扰/完整性检查，另有中断拒绝检查；新增 73 项和 Python 单元/集成共 590 项通过。详见 [第 4 步记录](docs/STEP4-PROGRESS.md)。第 5 步 Python 动态接入、第 6 步重放及完整 V01 尚未完成；下方 step1–3/0.2.1 为历史记录。

> step3 历史快照：环境采样、两遍完整输入生成及 TaskOption 建图已实现；新增 74 项及 Python 单元/集成共 517 项通过，7 个原 Java 脚本输入业务案例通过。API、证据和接纳边界见 [第 3 步记录](docs/STEP3-PROGRESS.md)。完整动态事件/统计、Java 输入导出和重放仍按后续步骤推进。

> step2 历史记录：DAX 目录/解析、sampler 和输入流准备的实现及当时测试见 [第 2 步记录](docs/STEP2-PROGRESS.md)。当前进度以上方 step3 为准；下方完整跨语言调度结果属于原 0.2.1 历史证据。

> step1 历史记录：新配置、不可变输入及身份映射的实现选择和当时验证见 [第 1 步记录](docs/STEP1-PROGRESS.md)。当前进度以上方 step2 说明为准；以下 286 项及完整跨语言调度结果仍是原 0.2.1 的历史验收证据。

按提供的设计及 Xu 等（2023）Java 源码实现固定输入模拟器。已完成本轮 V2-01～V2-05：正式 14 配置及 96 组固定扫查，共每种语言 3,469 条事件、2,021 次决策逐项一致。最终 286 项测试通过，0 失败、0 错误、0 跳过。环境为 Linux x86_64、CPython 3.12.14、pytest 9.2.0、Temurin 17.0.16+8。

**已知边界：** PT 虽然大于 0，仍可能因浮点精度使总执行区间归零。实测原 Java 在此输入上安排重叠执行；旧 Python 串行执行，两侧结果不同。当前版本在接受此类计划前返回明确 FAILED，不将该负例报告为跨语言通过。说明、触发输入、首差与修改文件见 [问题及修正](docs/ISSUES-AND-FIXES.md)，正式结果见 [完整验收记录](docs/VALIDATION.md)。

实现包括固定 JSON、规范对象、四事件、两层 Java 兼容堆、FCFS、固定资源调试路由、预约/去重、事件/决策日志、失败与全新对象重跑。DAX、原始随机生成与训练统计、GP、论文规模实验属于后续阶段。

优先复跑完整验收：

```text
python tools/validate.py
```

只运行 V2 正式对照、扫查和边界：

```text
python tools/run_v2_acceptance.py --java /path/to/jdk-17.0.16+8/bin/java
```

设置 `FOGSIM_JAVA` 后可省略 `--java`。完整验收要求 **JDK 主版本 17**，允许不同更新版本及厂商，例如用户使用的 Temurin 17.0.20.1+1。工具记录实际 vendor、build、可取得的 PriorityQueue 源码哈希，不将它们作为版本拒绝条件。17.0.16+8 仅标识本次实际验证的参考环境；其他 17 更新版本应在本机运行验收。无 JDK 时直接 pytest 可 skip，但正式 validate/release 会失败，不会发布“验收通过”。

## 本次新增：Java/Python 对照

```powershell
.\.venv\Scripts\python.exe tools/run_fixed_parity.py --java "C:\path\to\jdk-17\bin\java.exe"
```

本机项目内已有参考JDK时，可省略 `--java`；工具也支持 `FOGSIM_JAVA` 或 PATH。必须使用包含 `javac` 的 JDK 17；`lib/src.zip` 可选，存在时记录源码指纹。默认运行14个正式配置；可用 `--config configs/chain_fcfs.json` 选择案例，用 `--output outputs/my_parity` 指定证据目录。

适配器编译原Java调度类，保留原四事件、评分选择、比较器、等待队列、`canAddToQueue` 和设备归并。两份构造函数增量只用于跳过随机采样与隐式setup；固定到达、全输入统计、停止条件和观察日志由独立适配代码负责。Java没有加入Python的 `pending_start` 保护。详细改动和证据边界见 [适配说明](docs/JAVA-FIXED-ADAPTER.md)。

每个案例保存 `java-raw.json`、`python-raw.json`、两份规范化副本、`comparison.json`、输入/配置/ID映射及SHA清单。构建证据包含源码哈希、两份补丁、编译命令和输出。

只对已有轨迹重新比较：

```powershell
.\.venv\Scripts\python.exe -m fogsim.validation.trace_compare outputs/parity/chain_fcfs/python-raw.json outputs/parity/chain_fcfs/java-raw.json --output outputs/parity/chain_fcfs/recompare.json
```

按事件实际顺序比较：事件标识→处理前状态→事件内部交错的决策/发出事件→处理后状态→最终记录。不会排序日志、补齐缺失调用或按时间容差重新配对事件。正常案例首差为 `null`；检测到差异时保存事件序号、阶段、字段路径和两边数值。已保存的 [人工故障注入报告](outputs/parity/fault_injection/comparison.json) 展示首差定位能力，不是实际调度失败。

原始表示差异保留在raw文件：Java未完成时间默认0.0；Java待开始Process由事件观察得到，不是资源预约字段。两项映射在比较报告中明确列出，未完成时间的非零异常和多条待开始事件不会被隐藏。

## 环境与安装

- Python **3.11 或更新版本**；本次实际执行为 Linux x86_64、CPython **3.12.14**。
- Python 模拟器不需要 Java；测试依赖 `pytest`，本次版本 **9.2.0**。
- Java固定实例适配器及局部oracle使用 **Eclipse Temurin OpenJDK 17.0.16+8**。完整版本及源文件指纹见 [Java 参考说明](docs/JAVA-REFERENCE.md)。编译使用原ZIP随附的依赖jar，无需另外安装Maven或Gradle。

在本 README 所在目录执行（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m fogsim --config configs/chain_remote.json --output outputs/chain_remote.json
.\.venv\Scripts\python.exe -m pytest -q
```

Linux/macOS 将 `.\.venv\Scripts\python.exe` 换成 `.venv/bin/python`。安装后也可使用 `fogsim` 命令。不需激活环境即可执行上述命令。

虚拟环境和参考 JDK 不放入交付 ZIP。交付包包含原Java源文件及非javadoc依赖jar，以便重新编译适配器；解压后请建立Python环境，并指定自己的JDK17。

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

运行接受 Execution 时还要求 `(start+PT)+DT > start`，防止整体执行时长被浮点精度吞掉。

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

该命令执行测试（含固定 Java 对照及 V2 gate）、14 组 Python 实例并生成 `outputs/validation-manifest.json`，保存源码快照哈希、输入哈希、配置/顺序映射及真实结果。详见 [验收记录](docs/VALIDATION.md)。原始证据包括 `outputs/pytest-console.txt`、`outputs/pytest-results.xml`、`outputs/v2/`、`outputs/issues/`、`outputs/parity/` 和 `outputs/java_oracle/`。0.1证据保留在 `outputs/v0.1/`，旧的 `fogsim-0.1.0.zip` 保持不变。

Java 局部对照可独立执行：

```powershell
.\.venv\Scripts\python.exe tools/run_java_oracle.py --java "C:\path\to\jdk-17\bin\java.exe"
```

pytest自动查找本地参考JDK或PATH中的Java；也可设置 `FOGSIM_JAVA`。缺少Java时依赖Java的测试显式skip，不能报告为通过；找到主版本非 17 的 Java 时明确报错。以本次保存报告为准，本次没有跳过测试。

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
| [JAVA-REFERENCE](docs/JAVA-REFERENCE.md) | 参考 JDK 记录、JDK 17 主版本要求及兼容边界 |
| [VALIDATION](docs/VALIDATION.md) | 设计 11 验收映射、实际结果、未执行项目 |
| [SOURCES](docs/SOURCES.md) | 材料可访问性及阅读记录 |
| [java_mapping](docs/java_mapping.md)、[semantics](docs/semantics.md)、[roadmap](docs/roadmap.md) | 实现定位、语义与后续事项 |
| `references/design/` | 12 份原始设计快照，保留原文 |

设计00—07中“尚未编码”等是旧快照。当前实现及验证进度以本README、VALIDATION和IMPLEMENTATION-NOTES为准；08—11的增量设计优先于旧进度描述。交付ZIP不包含完整参考JDK、虚拟环境和原论文副本。

正式验收的全部输入/预期与 V2 映射见 docs/VALIDATION.md；相对 0.2.0a1 的文本改动见 CHANGES-FROM-0.2.0a1.patch。历史输出中的旧路径/版本为原运行记录，当前源码与最终快照以 validation-manifest 和 RELEASE-FILES 为准。

0.2.1 撤回 0.2.0 额外加入的具体 JDK build/vendor/源码强制锁定；详见 [JDK 17 兼容说明](docs/JDK17-COMPATIBILITY.md)。零 skip、完整 Java 真实对照和 V2 验收门禁继续保留。
