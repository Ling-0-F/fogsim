# 冻结设计实施记录：第 3 步

日期：2026-11-04（America/Los_Angeles）。从已交付 step2 ZIP 解压到独立 step3 工作副本。上传基线、step1 和 step2 ZIP 保持不变。本轮依据冻结设计 §§5、8–10、19 实现环境初始化、两遍输入生成和 TaskOption 建图，没有改变已确认语义。

| 模块 | 已实现 |
| --- | --- |
| `environment/build.py` | 按设备→边缘→云采环境；每台服务器依次上行、下行、算力；从数值快照建立全新 SystemState 和规范资源 |
| `instances/generation.py` | 共享输入流完成类型、间隔、权重及两遍生成；依邻接顺序累计；建立完整不可变 WorkflowInput/TaskInput/EdgeInput/OptionSpec；纯 release gate |
| `instances/materialize.py` | 用记录时长创建脱离索引的 Workflow/Task/TaskOption；引用本轮规范资源；填充物理值、XML/Java 映射及独立保留边映射 |
| `errors.py`、`numerics.py` | NumericDerivationError/NUMERIC_DERIVATION_ERROR；采样结果、累计、加法、除法提交前保护；未知程序异常不包装 |
| 测试与 `tools/check_step3.py` | 精确调用顺序、公式、拒绝及数值测试；20 标准模板实际生成；有限生成图复用原内核；原 Java 脚本输入业务核对 |

原固定加载、RunConfig、事件循环、比较器、堆、队列、预约、统计结果和 repeat 路径均未修改。新动态建图要求资源已有正有限的物理参数，旧固定路径仍允许参数未知为 None。

## API 与后续接纳边界

```python
from fogsim import (load_experiment_config, prepare_random_input, sample_environment,
                    build_environment, generate_workflow_input, release_rejection_reason,
                    materialize_workflow)
from fogsim.instances.generated import GenerationCause, CandidateRecord

config = load_experiment_config("configs/examples/step1_dynamic.json").single_run(0)
inputs = prepare_random_input(config)
environment = sample_environment(config.source.environment, inputs,
                                 parameter_source=config.fingerprint)
state = build_environment(environment)
cause = GenerationCause("initialize", environment.devices[0].id, 0.0)
candidate = generate_workflow_input(inputs, environment, cause, candidate_id=0)
record = CandidateRecord("1", candidate)  # 不可变完整输入；可加入独立归档
if release_rejection_reason(candidate, cause) is None:
    workflow = materialize_workflow(candidate,
        inputs.catalog.template(candidate.template_ref.dag_type_id), state,
        input_record_id=record.record_id)
    # workflow 尚未发布到 state，也没有 Arrival；发布属于第 5 步集中接纳。
```

调用者向生成器传入接纳前的 G 作为 candidate_id。生成器不持有 SystemState、计数或事件堆；它只推进已有 inputs.rng。release gate 返回 None 仅表示发布时间合格，不表示已正式接纳。第 5 步服务将统一检查 G+1 上限、记录实际接纳/拒绝、发布规范索引、更新 G/B、登记必要事实并 stage Arrival；本轮不伪造这些副作用已经实现。

先采完全部资源，再按设备顺序调用生成。20 模板集成测试和 Java 原 setup 核对已覆盖这条顺序；生产 Context 的首批调用编排及后续 after_arrival 钩子仍在第 5 步。build_environment 可从同一快照生成新对象，验证了资源参数保留与对象隔离的基础，但不是 reset/rerun/rotateSeed 的实现。

materialize_workflow 不重算、覆盖记录中的 PT/UT/DT，不进行重放文件装载。它检查模板、任务/边顺序、合法候选、规范资源、物理参数及本地零通信，并为每轮新建图。完成图发布前已经能获得完整不可变输入。运行图只持有来源 ID/哈希，不回引完整归档或 Context。

## 本轮落实的数值和顺序

第一遍逐任务采 workload、基础 data、再逐 children 采边，每边一次，并从 0.0 逐项加到 output_total。第二遍按各任务 parents 顺序读同一边值并逐项加到 input_total，再按合法本地、边缘、云顺序生成选项。两个总量不含基础 data；远程 UT=(基础data+input_total)/上行，PT=workload/算力，DT=(基础data+output_total)/下行。没有排序、fsum、通信复用或单位换算。

禁用本地仍采设备算力、workload/data/边值。无父/无子仍传输基础 data。同服务器父子保持 UT/DT，有限两任务手算案例由原内核实际完成于 5.5 和 9，makespan=7。

release<=clock 时完整候选仍生成，不提前退出、不重抽或回滚 RNG；gate 返回 REJECTED_RELEASE_NOT_FUTURE。零 delta、正 delta 被时钟加法舍掉均已测试，保留原 delta 而非倒算。非有限 release、累计/基础数据加法溢出、非正/非有限 PT（含下溢）、UT/DT 溢出抛 NumericDerivationError，不作为普通拒绝。未来便利入口对准备期失败结果的封装留在 Context 实现时完成。

本轮默认运行图边状态为 RETAINED，空邻接用空字典；两端字典分别复制，独立不可变输入不受运行字典修改影响。实际 release_edge_data 服务及 release_after_materialization 编排仍按第 7 步交付，当前 standalone API 不执行 run.edge_data_policy，也未宣称已验证 V20。最终阶段不能省略该服务。

## 实际执行与证据

项目根目录的实际命令（pytest 9.2.0 使用前两步建立的独立测试依赖目录）：

```text
PYTHONPATH=../../.test-deps:src python -m pytest -q tests/unit/test_environment_build.py tests/unit/test_workflow_generation.py tests/unit/test_materialize_workflow.py tests/integration/test_generated_kernel.py --junitxml=outputs/step3/contracts.xml
PYTHONPATH=../../.test-deps:src python -m pytest -q tests/unit tests/integration --junitxml=outputs/step3/python-regression.xml
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server PYTHONPATH=../../.test-deps:src python tools/check_step3.py
```

常规环境安装 `.[test]` 后可省略临时 PYTHONPATH；正常 JDK 17 可用 `python tools/check_step3.py --java /path/to/jdk17/bin/java`。本轮使用 CPython 3.12.14、pytest 9.2.0、Ubuntu OpenJDK 17.0.20+8，通过 jdk.compiler 模块编译，未要求特定厂商/更新号。

| 项目 | 实际结果及范围 |
| --- | --- |
| 新增测试 | **74 passed，0 failed/errors/skipped**。首批 49 passed；加入 20 标准模板和参数完整性检查后为最终计数 |
| Python 单元+集成 | **517 passed，0 failed/errors/skipped**；包含前两步、旧 CLI/repeat、14 固定配置完整结果与轨迹、原精度负例 |
| V06 | 精确角色调用顺序、资源数值、上下行分别调用、禁用本地仍采算力、同一输入流、初始运行状态与跨轮资源隔离通过 |
| V07 | 交错采样、每边一次、模板边序与采样边序不同、父/子累计顺序及舍入敏感案例通过 |
| V08 | 本地/边缘/云公式与顺序、其他设备不作候选、单点/无边/仅本地/禁本地、同服务器仍通信通过 |
| V11 本轮部分 | 完整生成后拒绝、原 delta 保留、RNG 继续推进、无自动重试/无索引副作用通过；实际动态 G/B、Arrival 钩子与拒绝后长期生成链随第 5 步验证 |
| 20 标准模板 | 每个模板为两个设备实际生成完整候选和独立运行图；边/总量/引用/共享服务器通过 |
| 原 Java 业务层核对 | **7 案例通过，首差均为空**：normal、local_disabled、local_only、first_device_rejected、all_devices_rejected、release_rounding、adjacency_accumulation |

Java 核对实际调用原 DynamicSimulation 构造和 setup、MobileDevice.generateWorkflowJob、Task 累计及 TaskOption 构造，源码/方法无 overlay，构建前核验 659 份原源码/依赖指纹。只通过 sampler 子类向两侧提供同一组脚本数值，不移植或比较 RNG 算法。原构造内的共享 RandomDataGenerator 引用也有检查。

核对比较资源值、逐项 sampler 调用、接纳工作流的任务物理值/总量/全部时长，以及 release gate 的 ID/数量预期。Python 的接纳计数和预计 Arrival 数只由工具测试编排计算，未作为生产服务实现；Java 原件实际产生的初始化 G/Arrival 与这些预期比较。额外时钟案例是直接调用生成方法的数值探针，不是假装已处理 Arrival。未触发任何 Java 事件，也未验证动态统计或调度轨迹。

原 Java mapClear 后观察不到完整边映射；本工具只保留脚本调用值和生成后数值，不导出拒绝者的完整 Java 候选。因此这不是第 4 步 V16 动态输入导出器，也不能替代 mapClear 前完整捕获和观察无干扰验证。Python 保留边映射是已确认差异。

证据在 `outputs/step3/`：测试 XML、checks.json、原构建/运行命令和输出、每案例 request/两侧 raw/完整 Python 候选/comparison。当前文件指纹为 current-files.json，真实汇总为 current-validation.json；旧 RELEASE-FILES、STEP1/STEP2-FILES 与历史 validation-manifest 仍是对应阶段的证据，不能描述当前工作副本。包为 step3 开发快照，未调用正式 release 门禁。

## 下一步

未发现必须调整冻结设计的问题。本轮 API 分层和 NumericDerivationError 是实现具体化，不改变语义。可按原顺序进入第 4 步 Java 完整动态输入导出与最小参考案例（V16）；随后第 5 步复用这些生成/建图接口接入集中接纳、Arrival、统计与 Context 生命周期。动态重放、清理、CLI、实验批次、完整 V01 和论文/GP 实验仍未实现或未执行，按对应步骤推进。
