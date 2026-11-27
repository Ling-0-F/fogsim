# 冻结设计实施记录：第 6 步（V17–V19）

日期：2026-11-05，America/Los_Angeles。直接基线为本轮提供的 `fogsim-0.2.1-step5.zip`，SHA-256 `e441aa5cd2e0767532260ab2b9d280896c437ff03772151ffe347a284083592b`。在独立副本开发，原 ZIP、原 Java 源码及 step4 input/reference/manifest 均不覆盖。冻结设计按用户确认执行，历史“初稿”文字不影响冻结状态。

本轮实际可访问来源共8份：step5、step4、verified、Java源码ZIP、冻结设计MD、原设计ZIP、学习计划及论文PDF。仅使用这些来源；step5内已包含所需第4步案例，无需从其他私人文件补全。659份Java源码/依赖与上传Java ZIP逐字节一致，见 `outputs/step6/source-audit.json`。

## 实际改动

| 模块 | 作用 |
| --- | --- |
| `replay/spec.py`、`loader.py`、`_decode.py` | 生产 schema-v1 加载；不可变归档/初态/capture/配置；严格字段、JSON数组、整数、有限数值、顺序、引用、候选完整性、capture校验；无 tools 运行依赖 |
| `replay/source.py` | 单一全局attempt游标；真实生成调用核对phase/owner/触发工作流/clock/拟用ID；记录读取位置、通过核对位置及失败详情；不搜索、不采样 |
| `replay/engine.py`、`simulation/admission.py` | 复用DynamicEngine原事件循环及集中接纳；release判定后、提交前核对observed acceptance；准备失败保留Engine/部分结果；仅新增输出快照的暂存事件计数 |
| `replay/audit.py` | 独立累计/公式binary64审计；差异报告不覆盖记录PT/UT/DT |
| `replay/export.py` | 成功接纳记录→旧InstanceSpec/JSON；独立fixed_projection语义损失清单 |
| `validation/dynamic_compare.py` | 执行结束后核对消费、事件、决策、交错动作、每个post-trigger状态、最终状态/统计/正常指标；绑定独立参考与原manifest哈希 |
| `tools/check_step6.py`、测试、示例配置 | V17–V19验证工具、原始结果和负例；不替代正式CLI/实验编排 |
| `tools/java_support.py` | 保留现有javac路径；固定编译入口另支持现有jdk.compiler模块（无javac launcher环境），记录模块SHA和命令；原Java方法/适配语义不变 |

`WorkflowSource.generate`、旧固定入口和随机Context生命周期保留。AdmissionService仅增加可选的提交前来源核对钩子，RandomWorkflowSource未改。ReplayEngine继承动态循环，只扩展诊断快照/结果，未另写调度器。共享RNG、seed/reset/rerun/rotate、B、原事件/保护次序未改。

## 使用与模式

```python
from fogsim import (load_replay_input, create_replay_engine, simulate_replay,
                    export_fixed_instance, load_experiment_config, simulate_replay_config)

inp = load_replay_input("input.json")
result = simulate_replay(inp)             # 只执行input；比较为NOT_COMPARED
engine = create_replay_engine(inp)         # 新对象图、来源位置从0开始，READY
result = engine.run()                      # 当前Engine只能run一次
fixed = export_fixed_instance(inp)         # fixed.to_dict()为旧JSON，损失标记另存清单
checked = simulate_replay_config(load_experiment_config("configs/examples/step6_verify.json"))
reused = simulate_replay_config(load_experiment_config("configs/examples/step6_reuse.json"))
```

单独input API默认按录制行为运行，允许没有reference；此时绝不报告轨迹通过。现有experiment配置的verify_reference仍要求reference_path；`simulate_replay_config`先执行、再读参考/manifest并比较。reuse_inputs不读取reference，即使配置给了reference_path；它始终标记新实验，原参考一致性结论关闭。单轮适配器明确拒绝未展开的repeat；后续编排使用现有`single_run`并为每轮创建新引擎，不推进上一轮游标。

verify_reference不允许更换行为规则；初始B、环境、N/W、统计、事件和保护条件来自记录。reuse_inputs只允许现有FCFS/fixed_resource路由及FCFS排序，目标须对全部设备合法；不开放来源/N/W/环境/seed覆盖。trace、额外预算和不变量检查为诊断选项；实际边清理仍明确拒绝，留第7步。原录制预算与额外预算取较小值，不延长原限制。

完整归档始终保存拒绝、未到达和未完成者。正常停止允许未消费尾部；严格复核一个原Java完整捕获时另外要求实际消费数量及诊断event_sequence与原记录一致。录制event_sequence不会安排事件；测试将其改为999，实际调度保持原样，事后比较发现消费证据差异。

`REPLAY_INPUT_INVALID`、`REPLAY_CAPTURE_INCOMPLETE`属于输入错误。`REPLAY_INPUT_EXHAUSTED`、`REPLAY_INPUT_DIVERGENCE`及既有`EVENTS_EXHAUSTED_BEFORE_TARGET`保留不同原因；后两种来源失败保存实际请求、下一record、读取/核对位置、部分事件和任务事实。换规则的来源不足/错位标记INPUT_COVERAGE_INSUFFICIENT，不断言调度错误；不自动采样或循环。complete=true仅表示捕获完整。诊断可显式`require_complete=False`加载完整attempt组成的部分捕获，但不能通过完整验收或导出正式固定投影。

## V17–V19与证据

最终汇总见 `outputs/step6/current-validation.json`。Python针对性127项及单元/集成797项通过，0失败/错误/跳过。跨语言V17共9例：7例NORMAL_PARITY_PASSED、2例EXPECTED_DIFFERENCE_CONFIRMED；每种语言1128事件、1008决策、96次尝试。V19为6个非空投影、10条规则路径正常通过，另1例为空投影表示限制；两个大型固定投影未执行。逐例分类以该汇总及原始报告为准。

- V17：生产重放使用独立第4步Java捕获及原清单，不使用第5步sampler展开工具。Java参考来自上阶段独立原动态入口；本轮未重新导出动态Java参考。保留完整生产trace和规则全图只读保护，无test-only recorder/priority绕过。
- V18：缺尾记录、不完整捕获、真实事件内来源错位、准备期用尽、换规则覆盖不足、无事件未达标均有测试/报告；不补输入。纯input执行、参考篡改、无RNG创建/推进、对象身份/运行图隔离、固定兼容均已核对。
- V19：本轮实际编译并运行原Java固定适配器，六个非空小型投影在两侧运行到所有输入完成，共十条规则路径。两个native_*大型投影不在最终V19验证范围；首次扩大验证在native_multiple_types固定Python运行时手动中断，保留INTERRUPTED报告，其已完成的动态比较单独保留。FCFS及有服务器时的fixed_resource分别对照；比较loaded_model、完整固定轨迹/状态/动作/结果。投影指标只表示固定全集，绝不与原动态统计指标混比。

V16历史字段`producer_device_id`明确映射为事件owner。Python raw继续分别保存owner/staging；历史参考没有staging证据，因此不能宣称逐条跨语言staging一致。第4步只有post-trigger状态，没有pre-trigger快照，本轮不伪造前态。Java jobsInSystem映射到Python按接纳顺序的pending+active；Java物理完成ID按接纳顺序观察，统计完成顺序原样保留。Java默认未完成时间0→None；Java边映射已清空、Python保留这一差异单列，不隐藏调度字段。

完整正常通过要求完整capture、来源足够、受支持规则/统计条件、两侧成功、完整manifest绑定且首差为空。无参考为NOT_COMPARED；缺完整溯源绑定为NOT_EXECUTED；预期异常单列EXPECTED_DIFFERENCE_CONFIRMED，不计正常跨语言通过。浮点比较abs=1e-9/rel=1e-12，priority有符号零区分，ID/计数/顺序精确；容差不参与调度。

## 实际命令及环境

CPython 3.12.14、pytest 9.2.0、Ubuntu OpenJDK 17.0.20+8。测试依赖安装在工程外。当前环境Java须设置LD_LIBRARY_PATH，无javac launcher时用已有jdk.compiler；正常JDK17可直接指定`--java`。构建清单保存完整命令、JDK/模块/源码/JAR指纹、编译及JVM原始输出。

```bash
PYTHONPATH=../../test-deps:src python -m pytest -q tests/unit/test_replay.py --junitxml=outputs/step6/replay-tests.xml
PYTHONPATH=../../test-deps:src python -m pytest -q tests/unit tests/integration --junitxml=outputs/step6/python-regression.xml
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server PYTHONPATH=src python tools/check_step6.py --output outputs/step6/acceptance
```

开发初轮新测试119通过/1失败：测试错误地期待dataclass未知构造参数抛InputError（实际TypeError）；已改为通过正式配置解析器验证禁止N/W覆盖，未改旧测试预期或调度行为。新增直接输入时长转binary64及覆盖/比较诊断完善后，针对性和完整Python单元/集成均再次通过；最终小型跨语言复跑另存`outputs/step6/final-small/`，命令在`checks.json`。最终大图仅动态重放命令为`python tools/check_step6.py --output outputs/step6/large-dynamic --cases native_standard_dax --skip-fixed`（沿用上述环境变量）。工具默认跳过native_*大型固定投影；显式`--include-large-fixed`可扩大V19，但完整图保护开销很高，不默认执行。

## 边界与第7步衔接

未发现需要调整冻结设计的源码冲突或关键语义问题。全部接纳为空时，旧固定格式要求非空工作流集，导出明确InputError；该例只验证表示限制，不声称执行了空固定实例。固定JSON不能保存拒绝/动态调用位置/统计窗口及完整物理字段，`projection-manifest.json`列出损失；Java规则仅FCFS/fixed_resource，物理1.0占位不支持真实物理特征或GP一致性结论。

未执行完整V01、96固定扫查/完整组件oracle重跑、实际边清理、完整CLI、批次编排、GP及论文实验。本轮Python回归和新投影Java对照不冒充这些门禁。第7步可直接围绕`ReplayInput.archive`保留不可变归档，新增实际清理服务/策略，再接入`simulate_replay_config`与独立游标的repeat编排，最后执行完整V01/CLI/批次门禁。

相对step5的文本补丁为`CHANGES-STEP6.patch`；当前文件清单为`STEP6-FILES.json`。旧STEP1–5/RELEASE清单和输出仅表示各自历史阶段。
