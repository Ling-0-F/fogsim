# 冻结设计实施记录：第 5 步

日期：2026-11-05（America/Los_Angeles）。从当前上传的 `fogsim-0.2.1-step4.zip` 解压到独立 step5 副本；基线 SHA-256 为 `e858f1424410fef3e5180151153c86e4d04edb7238ed6ab687b5b4cd062e6b8d`。原始 ZIP、标准 DAX 和 references 内原 Java 源文件未修改。本轮实现冻结设计 §§9–13、17 的集中接纳、动态事件接入、Java 统计及生命周期，验证 V09–V15。

## 实际改动

| 模块 | 作用 |
| --- | --- |
| `instances/source.py` | 完整候选来源协议和 RandomWorkflowSource；只使用既有共享输入流及冻结目录，不持有运行登记权限 |
| `simulation/admission.py` | 单一接纳点；完整生成后判断 release；准备规范图后发布索引、任务事实、G/B 和 Arrival；保存独立不可变候选/尝试/接纳映射 |
| `simulation/statistics.py` | G、B、R、按设备生成/物理完成/统计完成及独立 recorded_workflows；原保护顺序和严格阈值 |
| `simulation/dynamic.py` | 复用原四事件与 EventContext；单次归并后检查目标/耗尽/预算；事件后检查保护；明确失败及部分轨迹 |
| `simulation/context.py` | 新建、reset、rerun、rotate_seed；一条 RNG、冻结参数、保留资源数值及 B、每轮重建对象；准备失败保留诊断 |
| `simulation/dynamic_result.py`、`errors.py`、公共导出 | DynamicRunResult 扩展旧 RunResult；PreparationError/稳定失败码；新建及单轮便利入口 |
| 原 state/trace/events/event_queue/engine | 新工作流登记、动态任务事实登记、Arrival/首次完成回调、merge_staging/poll_global；固定默认回调为空操作 |
| 测试、`tools/check_step5.py`、Java Step5Probe | 80 项新增测试；9 个受控业务输入案例；原 Java 50 项运行探针；独立快速 API 示例 |

未重构整个目录或替换原比较器、两层堆、路由/排序公式、Visit/Start/Finish 的调度机制。旧 RunConfig、固定加载、create_engine/simulate、旧结果字段及 repeat 路径继续保持。DynamicRunResult 是独立扩展类型，旧固定结果没有增加必需字段。

## 已实现契约

一次尝试完整调用类型、间隔、权重和两遍生成后才执行接纳。拒绝保存完整 CandidateRecord 和 GenerationAttempt，原因固定为 REJECTED_RELEASE_NOT_FUTURE；不占 ID，不写索引/任务事实，不变更 G/B，不发 Arrival，不重抽、不回滚 RNG。初始化继续其他设备。每个实际 Arrival 在全部入口 Visit 派发后，仅由其 owner 进行一次后续尝试；Finish 不生成，G 到达 N+W 不截断来源。

成功接纳先构造完整脱离索引的图并校验，再发布规范 Workflow/Task 索引和任务事实；G 加一，所属设备生成数加一，使用增加后的 G 更新 B；最后 stage Arrival。输入归档先于事件可见，保留边数据与运行字典不共享可变存储。Task XML 字符串 ID 和 Java 顺序编号分开保存。候选只引用本轮规范共享资源，不为设备复制服务器。

物理完成由原 SystemState.register_completion 首次登记，全部实际完成者保存在 completed_workflows。仅首次成功回调统计：完成时 G>W、ID>=0、release<=B 才进入独立 recorded_workflows 并增加 R。没有 ID>=W 或 ID<N+W 条件。B 是赋值而非最大值；G 严格小于 N+W 时才更新，因此可以下降，达到门槛后冻结。早期工作流可入选；未入选完成者不补录。

动态循环每次先按设备顺序排空暂存堆，然后检查统计目标、事件耗尽、额外预算，再 poll 一条。最后一个达标事件完整执行，并在下一次循环归并后停止，不继续处理剩余同刻事件或排空系统。事件后按原顺序检查全局累计非统计事件计数>400000、允许本地的设备队列>400、服务器队列>400、G>500*(N+W)。主原因按这个顺序确定，同时保留全部命中。全局非统计事件计数不是连续停滞长度，不因某次完成而重设。

首次命中保护即 FAILED；保留实际时钟和诊断队列，正式 makespan/mean_flow_time 为空。同一事件同时达标和触发保护仍失败，遵循冻结设计明确采用的 Python 差异。正常指标只按统计集合计算，flow time 按登记顺序逐项加；指标累计溢出同样明确失败并保留物理完成事实。事件耗尽、额外预算和数值/状态失败分别命名；未知程序异常原样传播。

trace 关闭时 events/decisions 为空，但任务 dispatch/arrival/plan/actual Start/finish 事实仍登记。未实际发生的 Start/finish 保持空值，计划时刻不冒充实际时刻。规则视图不含 Context、来源、归档或未到达工作流；规范 Workflow/Task 无这些对象的回引用。

## 生命周期与 API

```python
from fogsim import load_experiment_config, create_dynamic_context, simulate_dynamic

config = load_experiment_config("configs/examples/step5_dynamic.json")
context = create_dynamic_context(config)  # 首个 READY Engine，不自动 run
first = context.run()                    # 当前 Engine 只运行一次
archive = context.input_archive          # 独立不可变输入；不依赖运行边映射
rng_state = context.snapshot_rng()       # 带 Python/原生状态版本的真实状态

ready = context.reset(-1)                # 保留环境数值和 B，重设 seed 起点，不 run
second = context.run()
third = context.rerun()                  # 继续当前随机流；重新准备并 run
ready = context.rotate_seed()            # signed64 回绕加10000，重设起点，不 run
fresh = simulate_dynamic(config)         # 全新上下文的一次便利运行
```

快速示例使用 `examples/step5/dax/` 的两任务调试图，不替换标准 dax/。该示例实际运行成功，首轮 7 条事件、2 个接纳工作流、1 个统计完成者；reset/rerun API 也已执行。

| 操作 | 环境数值 | RNG 起点 | B | 自动运行 |
| --- | --- | --- | --- | --- |
| create_dynamic_context | 新采样 | 编码 seed，先消费资源前缀 | 0 | 否 |
| reset(seed)/reset() | 保留 | 指定/当前公开 seed 的编码起点，不重采资源 | 保留 | 否 |
| rerun() | 保留 | 当前状态继续 | 保留 | 是 |
| rotate_seed() | 保留 | 公开 signed64 回绕加10000后的起点 | 保留 | 否 |

每轮重新建立 Resource、Task、Workflow、TaskOption、SystemState、Engine、统计、队列、执行索引和 trace。只有数值快照、冻结 sampler/模板和上下文唯一 RNG 被复用。新建首轮与 reset 首轮的输入前缀不同；不能把 reset 当作从头重复。Context 的 config、inputs、environment、public_seed、engine 属性只读，当前 seed 由 public_seed 表示；config 保存初始请求。更改参数应新建 Context。

RUNNING 时禁止生命周期操作。准备新一轮会把旧 READY Engine 标记 SUPERSEDED，防止旧入口稍后推进同一 RNG；已结束的 Engine 仍只能执行一次。Context 只持有当前运行图，不自动积累所有旧 Engine；调用方保存的旧结果保持独立。当前 Engine 的 rng_start/rng_ready/rng_final 保留真实 RngStateSnapshot；结果中另给指纹用于核对，指纹不代替状态。

创建/reset 准备期的领域失败抛 PreparationError，携带 context、engine、FAILED result；simulate_dynamic 与 rerun 将其归一化为失败结果。已保存的完整环境继续保留；若资源采样在完整环境快照建立前失败，则没有完整数值可复用，显式下一轮会重新尝试建立快照。这仅是 Python 准备失败恢复，不声称对应原 Java 异常尾部行为。配置、文件或调用错误保留 InputError/EngineUsageError；程序异常不包装成 PreparationError。

release_after_materialization 已能作为配置契约出现，但本轮执行入口在采样前明确拒绝该策略；使用 retain。实际清理服务及策略编排依原顺序在第 7 步交付，没有悄悄忽略开关或标为完成。

## V09–V15 验证范围

| 验收 | 已执行验证 |
| --- | --- |
| V09 | 同模板多工作流无 Task/边字典共享；同轮规范服务器共享；跨轮资源/任务/选项隔离；owner/staging 分离；Java 原 PF 续接组件探针 |
| V10 | 多入口全部派发后一次生成；Finish 不生成；G 超过 N+W 仍生成；单一共享输入 RNG，无设备选择抽样 |
| V11 | 初始化首设备拒绝不阻止他设备；全部拒绝、Arrival 内拒绝、零间隔和正间隔被时钟舍掉；完整消耗、无重试、正式 ID 连续 |
| V12 | G=W 与 G>W，B 下降及 G=N+W，早期/大 ID，release=B/超过B，不补录；物理/统计集合和指标范围分离 |
| V13 | 达标事件完整执行，最后归并，同刻事件保留，预算与目标优先级；trace 开关事实一致，失败正式指标为空 |
| V14 | 400/401，400000/400001，生成阈值等号/超一，多保护主次序，禁本地跳过设备保护，同事件达标+保护；真实402入口图触发设备/服务器401队列；指标累计溢出 |
| V15 | fresh/reset/rerun/rotate 的资源参数、对象隔离、B、RNG 起点、signed64 两端与回绕；无资源重采样/无 DAX 重读；失败后继续、单次使用及 RUNNING 禁止操作 |

本轮实际新编译并运行原 Java：28 个生命周期操作（4 个 seed×7 次操作）、6 次接纳边界、5 个完成筛选边界、10 个保护边界和1个 owner/staging 续接探针，共 **50 项通过**。源码无 overlay。为隔离具体条件，组件探针明确注入 G/B、计数、队列及最小工作流状态；不是声称这些状态都自然可达。生命周期探针为了直接观察 B 延续，明确设置 B 并使用 N=1/W=0，避免 setup 重写 B；不把注入初始状态称为正常 fresh 实验。RNG 以 Java 自己的种子起点及前后状态核对，不与 Python 同 seed 逐值配对。

`tools/check_step5.py` 还把第 4 步 input 中的环境和候选值展开成**测试专用业务 sampler 脚本**，通过本轮真实 Python 随机来源、两遍生成、集中接纳及四事件执行，再读独立 Java reference 作比较。source 不读取参考决策/停止时间/完成结果。不是生产重放加载器，也不自动补采样；脚本耗尽或顺序不符会报错。9 个案例的完整生成输入、尝试/消费顺序、事件、各次评分/选择、交错 DECISION/EMIT、最终资源缓存/队列及 G/B/R、成功指标均无首差。两项未达标案例按 Python 明确失败对照，报告 EXPECTED_DIFFERENCE_CONFIRMED。

大型 trace 的重复全图快照及既有规则只读全图指纹扫描开销明显。核对工具使用专用 recorder，仅不保留它不比较的 before/after 重复图；保留所有实际事件、决策、动作及最终状态。两个标准大型案例在工具内只执行已知的原 FCFS priority，省略重复的全图变更指纹计算，**生产保护和生产 trace 未改**，状态/队列不变量继续检查。小图测试已比较完整生产方式与该工具方式的全部规范化轨迹和事实；`native_multiple_types` 还额外完成了生产完整 priority guard 方式，结果与工具方式逐项一致，证据在 `outputs/step5/full-guard-native/`。这些是限定 FCFS 的业务对照，不是任意自定义规则/GP 的保护等价或性能验收。

## 第 4 步参考字段勘误

原 `DynamicCapture.event` 的字段 `producer_device_id` 取 `event.getMobileDevice()`。在原 Java 服务器续接路径，ProcessStart 的此值是**任务所属设备，即事件 owner**；写入堆的设备来自调用 addEvent 的当前设备，二者可能不同。字段名称容易误导。

本轮保留历史参考字节，在比较中明确将该旧字段映射为 Python owner，不把它当作 staging device。50 项 Java 探针中的原 ProcessFinishEvent.trigger 实际证明：M0 调用 addEvent 写入自身暂存堆，产生 owner=M1 的 ProcessStart；Python 动态续接测试也核对同一关系。后续第 6 步的参考归一化必须沿用这个明确映射；若扩展导出元数据，应显式另存 owner/staging，不能根据旧字段名猜测。输入格式、ID 和冻结调度语义无需更改。

## 真实执行结果与复跑

本次使用 CPython 3.12.14、pytest 9.2.0、Ubuntu OpenJDK 17.0.20+8；编译器使用现有 jdk.compiler 模块。Java/source/JAR/编译器指纹和完整命令在构建报告中，不要求特定更新号/厂商。

实际最终测试命令（在项目根；临时 test-deps 位于交付工程外）：

```bash
PYTHONPATH=../../test-deps:src python -m pytest -q tests/unit/test_dynamic_context.py tests/unit/test_dynamic_admission.py tests/unit/test_dynamic_statistics.py tests/integration/test_dynamic_business_oracle.py --junitxml=outputs/step5/contracts.xml
PYTHONPATH=../../test-deps:src python -m pytest -q tests/unit tests/integration --junitxml=outputs/step5/python-regression.xml
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server python tools/check_step5.py --output outputs/step5-final
```

常规环境安装 `.[test]` 后可省略 PYTHONPATH；正常 JDK 17 用 --java 或 FOGSIM_JAVA，不需要此环境专用库路径。输出到新目录可复跑：

```bash
python tools/check_step5.py --java /path/to/jdk17/bin/java --output outputs/step5-rerun
```

| 检查 | 结果 |
| --- | --- |
| 新增契约/集成 | **80 passed，0 failed/errors/skipped** |
| Python 单元及集成回归 | **670 passed，0 failed/errors/skipped**；包括旧 CLI/repeat、14 个固定配置完整结果/轨迹及原精度负例 |
| 新运行的 Java 探针 | **50 项通过**，无源 overlay；生命周期与人工组件状态分开记录 |
| 受控业务对照 | **9 个案例通过**：7 个正常结果、2 个预期失败；共 96 次尝试、1,128 条事件、1,008 次决策，全部首差为空 |
| recorder/FCFS 工具方式 | 小图完整保护/trace 等价；大型 native_multiple_types 完整 priority guard 与工具方式等价 |
| 快速 API 示例 | 实际成功运行；新建、reset、rerun 均可使用 |

初次新增 Admission 测试有 3 个失败：其中环境来源指纹错误地包含 trace 等运行诊断配置，已改为只由环境及 sampler 有效参数计算；另外两个是新测试假设错误（把 resources 中的子串 source 当成反向引用、在随机不同上传量下预设某台设备先到）。现改为检查真实可达对象及生产设备关系；未调整旧测试预期、调度或 Java 结果。大型完整诊断验证曾手动中止，不能算通过；最终完整性以 step5-final 的 checks 和正式 XML 为准。保留了已完成的大型完整 priority guard 证据。

当前运行证据：`outputs/step5/` 的测试 XML、额外完整保护对照和当前汇总；`outputs/step5-final/` 的 Java 编译/运行/原始探针及9案例两侧比较。当前文件指纹为 `STEP5-FILES.json`、`outputs/step5/current-files.json`，汇总为 `outputs/step5/current-validation.json`，相对 step4 的改动为 `CHANGES-STEP5.patch`。旧 RELEASE/STEP1–4 清单只描述历史阶段。

## 未执行与下一步

没有发现必须更改冻结设计的调度语义。第 4 步参考元数据命名问题及本轮诊断指纹修正均已明确记录，没有静默改变原输入或预期行为。

生产重放来源/加载器、参考模式限制、覆盖不足诊断、固定投影及完整动态跨语言 V17–V19 仍未实现或未执行。这里的受控 sampler 对照不能替代它们。第 6 步可直接接入 WorkflowSource 和 AdmissionService，在同一真实调用位置逐条提供完整输入，并消费第 4 步独立 input/reference。完成后再按第 7 步交付实际边清理服务、完整 CLI/重复实验/完整 V01；GP 和论文训练实验仍在范围外。
