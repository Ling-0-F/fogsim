# 最终接口第一版：固定实例、状态操作、规则与事件

- 项目：Xu 等（2023）雾计算调度 Java→Python 复现。
- 文档版本：1.0.0；日期：2026-10-22。
- 状态：**用户已采用上一轮推荐，本接口设计作为实现基线；尚未编写或运行模拟器。**
- 承接：00—07 文档集 1.1.0、[08 事件读写表](08-EVENT-READ-WRITE.md)。同时刻处理以 [10](10-SIMULTANEOUS-EVENT-POLICY.md) 为准；实现后检查见 [11](11-VALIDATION-AFTER-0.1.md)。
- 本文中的签名用于约定职责、参数和返回值，不是已经存在的 Python API。类的具体写法、CLI 命令拼写、输出序列化布局可在编码时落实，不得借此改变已定语义。

## 1. 本轮确定什么

接口回答“由谁调用、交给它什么、返回什么、允许修改什么”。它不另建一份状态，也不重新决定事件先后。状态权威位置继续以 07 为准，四事件操作顺序继续以 08 为准。

| 分类 | 已确定的选择 | 依据 |
| --- | --- | --- |
| 复用输入 | 固定输入先读为可复用的 InstanceSpec，每轮新建运行对象 | Python 组织建议，承接既有重跑约定 |
| 规则接口 | 评分与选择分开；评分函数只读，选择组件写 priority | 借鉴 Java 的评分、覆盖和遍历行为，重新分配 Python 职责 |
| 就绪查询 | 返回同一 Task 对象的列表或空列表，不评分、不派发 | 用户此前已采用的 Python 拆分 |
| 状态提交 | 派发、预约、开始、任务完成、工作流登记分别设统一入口 | Python 显式操作；保留 08 已定修改时机 |
| 事件构造 | 四事件构造只保存引用和派生时间 | Python 调整；Java TaskVisitEvent 构造有派发副作用 |
| 事件管理 | 一个 EventQueue 管理全局堆及各设备暂存堆 | Python 集中管理，保留 Java 两层归并行为 |
| 运行结果 | 正常与失败明确区分，预测完成时间不能伪装实际完成 | 既有固定输入和失败约定 |

本轮完成的是接口第一版设计，不表示调用结果已经验证与 Java 等价。07、08 和旧总览里“接口尚待设计”的文字是较早快照；本文记录新的进度，未声称那些文件已自动同步改写。

## 2. 公共入口与一次运行

### 2.1 公共签名

| 接口 | 参数与返回值 | 允许发生的事 | 不允许隐含发生的事 |
| --- | --- | --- | --- |
| `load_fixed_instance(path) -> InstanceSpec` | 读取固定实例并验证输入 | 校验 ID、依赖、时长、资源资格和合法候选完整性；保留输入顺序 | 不建立上一轮可变状态，不采样、不运行事件 |
| `create_engine(spec, config) -> Engine` | 输入描述＋运行配置，返回 READY 的新引擎 | 建立本轮规范对象、引用与索引；初始状态；按约定安排全部固定工作流的到达事件 | 不自动执行到达或调用规则，不在构造时随机生成工作流 |
| `Engine.run() -> RunResult` | 在本引擎上执行一次 | 推进事件循环；正常完成或形成明确失败结果 | 不在同一对象上自动清空后再跑；第二次调用是接口使用错误 |
| `simulate(spec, config) -> RunResult` | 创建新引擎并运行一次 | 每次调用都建立全新的运行对象图 | 不复用旧队列、旧事件、旧规则运行缓存或旧日志 |

输入/配置错误在运行前明确报错；运行中的预期领域错误，例如事件耗尽但任务未完成、重复完成、预约不匹配，应结束为 FAILED 并记录原因。程序缺陷产生的非预期异常可以向调用方抛出，不能吞掉后返回成功。

### 2.2 关键类型的边界

| 类型 | 保存的内容与约束 |
| --- | --- |
| InstanceSpec | 资源、工作流、任务、依赖与全部合法选项时长；可复用输入描述，不含 dispatched、completed、priority、队列、预约、时钟或事件 |
| RunConfig | 路由/排序规则配置、详细日志开关、事件策略及必要运行选项；配置是描述，不携带上一轮规则的可变运行状态 |
| Engine | 本轮 SystemState、EventQueue、TraceRecorder；处理计数、运行状态和失败原因 |
| EventContext | 当前事件处理的协调入口；关联本轮状态操作、规则、日志和事件提交；供事件处理使用，不传给评分规则 |
| DecisionContext | ROUTING 或 SEQUENCING 的候选与受限状态；供选择和评分使用，不提供事件提交能力 |
| RunResult | 本轮状态、原因、最终时钟、完成数量、正常运行指标，以及独立的结果记录/日志快照；不暴露可继续调度的 Engine |

READY → RUNNING → SUCCEEDED 或 FAILED。第二次调用同一 Engine.run 不属于“重跑”。固定重跑应再次调用 simulate，或重新 create_engine。

### 2.3 初始化与重跑

| 操作 | 对象与状态 | RNG/seed |
| --- | --- | --- |
| 第一次初始化 | 从 InstanceSpec 建立新资源、工作流、任务、选项、事件、索引和日志；clock=0，缓存/计数=0，标记=False，pending_start=None | 固定输入模式不采样 |
| 同一固定实例重跑 | 再建一整套独立运行对象；保持输入、候选、设备和初始事件的约定顺序 | 不需要“重设 seed”才能恢复固定输入 |
| 以后随机实例重跑 | 先明确是复用已生成 InstanceSpec，还是重新生成输入 | RNG 状态、重新设种子、seed 轮换属于后续 instances/evaluation 设计，不能混为同一种 reset |

**构造完成不等于事件已经触发。** release_time=0 的工作流仍先位于 pending_arrivals，必须经过到达事件才成为 active。

## 3. 规范对象、身份与顺序

1. 一个运行中，每个任务只建立一个 Task。Workflow.tasks、父子引用、TaskOption.task、索引、事件和 Execution 都引用它。
2. 任务键为 `(workflow_id, task_id)`；文件/日志靠稳定 ID 对应，运行内检查同一对象时靠对象身份。
3. 资源展示 ID 全局唯一，例如 M0/E0/C0；Java 比较所用的设备、服务器数值 ID 按各自空间映射。设备 ID 和服务器 ID 可以同时为 0，不能强行统一成一个编号空间。
4. 当前默认映射为 M0 的设备数值 ID=0，E0 的服务器数值 ID=0，C0 的服务器数值 ID=1。服务器顺序为边缘后云；扩展时依列表建立映射并记录。
5. 工作流保留输入的全局整数 ID，不为了到达顺序重新编号。任务扫描保留输入列表顺序；映射到 Java 任务索引时记录该顺序。
6. 路由候选依次为合法本地选项、边缘列表、云列表。等待队列保持入队顺序，选中项移除后其余项目相对顺序不变。

Python 模型、Execution 和事件采用运行对象身份语义，避免 dataclass 自动递归比较整个工作流图。不要照搬 Java `Process.equals` 恒假、某些事件只按类/时间比较的行为作为去重机制。也不要调用 `TaskOption.compareTo`：该源码实现恒为 -1，实际选择依据是 `priorTo`。

## 4. 就绪查询与规则接口

### 4.1 查询和决策的签名

| 接口 | 输入与返回值 | 修改权限与前置条件 |
| --- | --- | --- |
| `ready_tasks(workflow, view) -> list[Task]` | 返回本轮同一 Task 对象，按工作流任务顺序；无结果为 `[]` | 工作流已激活；筛选未派发、未完成且全部前驱完成。完全只读，不调用规则 |
| `PriorityRule.priority(option, context) -> float` | 给一个候选计算本次分数 | 只读选项和情境；不写 priority、不派发、不改队列或规则外部状态 |
| `choose_route(context, rule) -> TaskOption` | 从有序合法候选中返回同一选项对象 | 选择组件逐项调用评分、覆盖各选项 priority、按平分规则选优并保存决策快照 |
| `choose_next(context, rule) -> TaskOption` | 从当前资源等待队列候选中返回同一选项对象 | 同样评分、覆盖 priority、记录选择；**不出队** |
| `is_preferred(candidate, incumbent) -> bool` | 当前候选是否替换已选项 | 只读；对应 Java TaskOption.priorTo，完全平分不替换 |

ready_tasks 返回空列表是正常查询结果；choose_route/choose_next 接到空候选则是调用方状态错误。事件应先判断是否存在合法任务/队列项，不能让选择函数静默返回任意默认资源。

### 4.2 情境内容

| 情境 | 提供内容 | 不提供内容 |
| --- | --- | --- |
| RoutingContext | `kind=ROUTING`、当前任务、有序候选、受限状态视图 | Engine、事件队列、未来工作流索引、输入文件的全量未来信息 |
| SequencingContext | `kind=SEQUENCING`、当前 Resource、有序队列候选、受限状态视图 | 出队/预约能力、未来工作流信息、完整可变 SystemState |
| 可见状态视图 | 当前时钟、资源状态及当前规则允许读取的已到达信息；可包含本事件中已经完成阶段更新后的事实 | pending_arrivals 及其数量、未来工作流/任务全集、完整 executions_by_task 等能旁路取得未来信息的内部索引 |

候选成员与顺序用 tuple 等只读容器表达，成员仍是本轮规范对象的引用，不是深拷贝。tuple 本身不能让成员字段不可修改：规则只读还须通过接口约束、受限包装和必要检查实现。不能把“容器不可变”宣传成完整隔离。

本地资源也用统一 Resource 传入情境，评分不再依赖 `server is None` 猜测本地执行。迁移 Java 特征时，须明确对应的是候选资源还是当前排序资源，不能只改参数名。

### 4.3 评分和选择的操作顺序

1. 取得有序候选；首项作为初始已选项。
2. 对首项评分并立即覆盖其 priority。
3. 顺序处理余项：评分、覆盖 priority，再调用 is_preferred 决定是否替换。
4. 保存每项当次分数及最终选择的快照，返回规范选项引用。

这借鉴 AbstractRule 的逐项行为。不要先排序整份候选、擅加任务 ID 或资源 ID 平分键，也不要认为所有旧 priority 都仍代表同一决策时刻。评分函数只读与选择函数会写 priority，是两种不同权限。

当前 FCFS：路由分数是候选资源 available_time 原值；排序分数是任务所属工作流 release_time。不是任务到达资源时间，也不使用 `max(clock, available_time)` 替换原值。分数与平分数值细节见 10。

### 4.4 保留两整轮后续路由

到达事件按入口顺序逐项“设入口全部选项 ready_time → 路由 → 派发”，每入口一次路由。

完成事件先处理资源队列，再调用一次纯就绪查询。有就绪任务 A、B 时，按 **A、B、A、B** 完成两整轮路由，保留第二轮选择，随后才逐项派发。没有任务时返回空列表，再独立检查工作流全部完成。

这是把 Java 的隐藏评分副作用显式化，不是删掉第二轮评分。省略重复纯扫描已采用；减少评分次数没有采用。

## 5. 状态操作接口

这些入口使跨字段修改集中，但不转移字段权威位置。例如 dispatch 操作可以协调多个对象，dispatched 仍只保存在 Task。

| 接口 | 前置检查 | 成功后的修改 | 时间/限制 |
| --- | --- | --- | --- |
| `state.activate_workflow(workflow) -> None` | 在 pending_arrivals；到达时刻匹配；没有重复激活 | pending 移入 active | 仅到达事件调用；不直接派发 |
| `ctx.dispatch(option) -> None` | 工作流已到达；任务未派发未完成、依赖满足；选项合法 | dispatched=True；提交上传完成的 TaskVisitEvent | 到达入口或完成事件的派发阶段；事件时间=当前派发时间+UT；不预约处理器 |
| `resource.enqueue(option) -> None` | 已到达该资源；不在队列、不已预约/执行/完成 | 追加同一选项；增加两个缓存 | TaskVisit 的忙/已预约分支 |
| `resource.remove_waiting(option) -> None` | 该对象确实位于本资源队列 | 按对象身份移除，更新两个缓存 | 排序选择之后；缺失时报错，不按“值相等”删除其他项 |
| `ctx.reserve_start(option, start_time) -> Execution` | 已派发未完成；不存在正式执行；目标资源无 pending_start；选项不在等待队列；start_time 合法 | 建立唯一 Execution；登记 executions_by_task；设置 pending_start；提交开始事件 | 接受确定安排时；不修改 available_time，不记录实际开始 |
| `resource.begin_execution(execution) -> None` | 预约正是该对象；执行已登记；时间/资源一致、任务未完成 | 清对应预约；available_time=execution.finish_time | 仅匹配的开始事件；不提前完成任务 |
| `ctx.finish_execution(execution) -> None` | 已实际开始，当前为其完成时刻；未完成、未重复登记任务记录 | completed=True；追加同一 Execution 至工作流完成记录；资源完成任务数加一 | 完成事件第一阶段；不自动登记整个工作流 |
| `state.register_completion(workflow) -> bool` | 全部任务完成、记录与标记一致 | 设置 completion_time；active 移到 completed；设置 completion_registered | 完成事件最后阶段；首次返回 True，已一致登记返回 False；不一致时报错 |

### 5.1 预约的两个调用路径

| 路径 | 安排开始之前 | start_time |
| --- | --- | --- |
| TaskVisit 直接开始 | available_time<=t 且 pending_start=None；选项不进入等待队列 | t |
| 完成事件从队列续接 | 队列非空且 pending_start=None；先 choose_next，后 remove_waiting | max(available_time,t) |

reserve_start 检查 start_time 不早于当前时钟、该选项到达时刻及资源已有可用时刻；派生计算/完成时间也必须有限。由事件处理协调出队和预约，在同一事件处理内完成，期间不能调用其他事件。

操作应先完成能做的合法性检查再提交；若提交失败，本轮必须以明确失败终止，不能继续使用半更新状态。不要求为了本模拟器引入数据库式事务框架。

同刻新开始事件可以先于旧完成事件处理。因此“下一项已经实际开始，而上一项的完成记录尚未追加”可能是源码事件顺序造成的短暂现象；不能用一个额外 busy 布尔值误判，也不能在旧完成事件里清掉别项预约或重写 available_time。

### 5.2 局部字段约束

- TaskOption.ready_time 初始 0；入口到达时设置该入口所有选项为 release_time；TaskVisit 只把选中选项改为 t。后继未选选项不统一刷新。
- priority 是最近一次评分；查询不写，选择组件按当次遍历覆盖。
- available_time 初始 0，只在实际开始时改为 finish_time。预约不提前写，完成事件不钳为当前时钟。
- 等待缓存按 Java 的 PT 与 PT+UT+DT 增减及运算顺序维护。Server 出队后空队归零，空队 getter 返回零；MobileDevice 始终相减并直接读取。不要为“统一接口”消掉资源类型差异。
- Execution 的选项和计划时间在接受安排后固定。尚未实际完成的 Execution 不进入 Workflow.completed_executions。
- 工作流已登记调用可幂等返回 False；**重复任务完成必须报错**。两者不是同一种重复处理政策。

## 6. 四事件接口与构造约束

| 事件构造 | 自动确定的信息 | 构造时禁止的修改 |
| --- | --- | --- |
| `JobArrivalEvent(workflow)` | time=release_time；owner=workflow.owner_device | 不激活工作流、不评分、不生成下一工作流 |
| `TaskVisitEvent(time, option)` | 显式上传后时间；owner 来自任务工作流 | 不修改 dispatched 或 ready_time，不入队 |
| `ProcessStartEvent(execution)` | time=start_time；owner 来自所执行任务 | 不清预约、不写 available_time |
| `ProcessFinishEvent(execution)` | time=finish_time；owner 来自所执行任务 | 不写 completed、不追加完成记录 |

四类事件统一为 `event.trigger(context) -> None`。trigger 依 08 的阶段调用操作；Engine 在调用前设置唯一系统时钟。新事件必须提交队列，不能直接内联调用其 trigger。

Java TaskVisitEvent 构造会设置 dispatch，Python 将这项副作用移到 ctx.dispatch，仍发生在安排上传完成事件时。Java TaskVisit 在判断忙闲前建立临时 Process，Python 只在接受开始安排时创建正式 Execution。行为对照要比较稳定事件边界，不应要求构造临时对象的次数相同。

## 7. EventQueue 与事件提交

| 接口 | 行为 |
| --- | --- |
| `compare_event_java(a, b) -> int` | 按 10 完整保留上传源码的比较返回分支，含异常平分返回；不是 Python 通用元组键 |
| `EventQueue.stage(event, staging_device) -> None` | 将事件放入指定生产设备的暂存堆；不直接放入全局堆 |
| `EventQueue.pop_next() -> Event \| None` | 先按设备列表顺序，把每个暂存堆按其 poll 次序逐项 offer 进全局堆，再从全局堆 poll 一项；全部为空返回 None |
| `EventQueue.has_pending() -> bool` | 检查全局堆和全部暂存堆；只读，不在这里悄悄归并 |
| `ctx.emit(event) -> None` | 按当前事件处理设备提交到对应暂存堆；保留生产设备与事件 owner 的区别 |

初始化不在事件处理情境中，由构建器按输入工作流顺序将到达事件 stage 到其 owner 设备；设备列表本身保持固定输入顺序。每次事件处理后都重新执行归并和单项弹出，不能预取一批同刻事件。

共享服务器场景中，当前完成事件的设备可能与选出的下一任务 owner 不同。新事件暂存于前者，事件载荷 owner 是后者。event.owner 决定下次 trigger 的设备；staging_device 决定归并路径，不能合并为同一字段。

当前一轮共用一对规则。将来按设备配置规则时，还须保留 Java “当前完成事件设备提供排序规则”的事实，不能自动改成下一任务 owner 的规则。

队列集中由 EventQueue 管理，不在 SystemState、MobileDevice 再建立可独立修改的一套事件队列。实现兼容堆、锁定目标 JDK 和验证边界详见 10。

## 8. 日志、实际发生记录与结果

`TraceRecorder.append(record) -> None` 只接受立即保存的 ID、数值、枚举和容器快照，不保存将随下一次评分或状态修改而变化的可变模型引用。日志从不供调度规则读取。

| 记录 | 内容与时机 |
| --- | --- |
| 最小生命周期记录 | 每轮始终记录派发、到达、实际开始、实际完成事实；保证必要 RunResult，不受详细日志开关影响 |
| 执行计划 | reserve_start 后可记录 start/compute_finish/finish 的确定计划；明确标为计划，存在 Execution 不代表已触发开始或完成 |
| 决策日志 | 每次选择的时间、类型、任务/资源、候选顺序、当次分数、选择；后继路由注明第 1/2 轮 |
| 事件日志 | 实际处理序号、类型、时间、owner/生产设备信息、状态前后快照及新安排事件 |
| 资源轨迹 | 队列与缓存、available_time、pending_start、实际执行区间 |

`trace_enabled=False` 可关闭详细事件/决策快照，不能让正常输出缺少任务必要时间记录，也不能改变评分次数、队列或调度结果。这是对既有输出约定的接口澄清，不新增一份模型调度状态。

RunResult 至少包含以下语义字段；文件序列化时保持相同含义：

| 字段组 | 约定 |
| --- | --- |
| status、reason | 成功/失败；失败原因及必要对象 ID，正常运行原因可为空 |
| final_clock_time、completed_workflow_count | 本轮最后实际事件时钟、已完成工作流数；时钟不写极大惩罚值 |
| makespan | 仅正常且全部输入完成时，max(completion)-min(release)；失败为缺失值，不拿预测 finish 补齐 |
| workflow_records | ID、owner、release、实际 completion、flow_time；未完成的完成时刻/flow_time 缺失 |
| task_records | 稳定任务键、资源、实际 dispatch/arrival/start/finish；未发生为缺失。执行计划单独表达，其中包含 compute_finish_time |
| detailed traces | 若启用则带事件、决策和资源轨迹快照；不包含可继续修改本轮调度的模型对象 |

最终成功记录可导出 03 的扁平任务时间列。compute_finish_time 由确定开始时刻和 PT 派生，不代表触发过第五类事件。失败记录须保留计划/实际区别，不能仅靠一串非空时间声称全部动作已发生。

## 9. 模块落点与依赖方向

| 位置（相对 src/fogsim） | 接口职责 |
| --- | --- |
| instances/spec.py、fixed.py | InstanceSpec、固定加载与验证 |
| config.py | RunConfig；配置验证与规则构建描述 |
| model/resource.py | 队列/缓存、pending_start、begin_execution 等局部操作 |
| model/execution.py | 不变执行计划字段 |
| simulation/state.py | 全局索引、激活、完成登记 |
| simulation/readiness.py | 只读 ready_tasks |
| rules/base.py、contexts.py、selection.py | 评分协议、受限情境、choose_route/choose_next/is_preferred |
| simulation/events.py | 四事件及已定处理顺序 |
| simulation/engine.py | create_engine、Engine、simulate、EventContext 与跨对象操作协调 |
| simulation/event_queue.py | 两层堆、归并、比较与提交 |
| simulation/trace.py、metrics.py | 快照与结果整理、正常指标 |

model 不反向依赖事件循环或规则。跨对象协调由引擎侧 EventContext 承接；类型注解可以使用前向引用/仅类型检查导入，构建器先建规范对象再连父子关系，避免为解决导入而复制模型对象。

## 10. 证据、差异与后续同步

### 10.1 Java 源码定位

材料：`Fog-Computing-multiDeviceDebug.zip`，SHA-256：`17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a`。

以下路径相对 ZIP 内 `Fog-Computing-multiDeviceDebug/`：

| 路径 | 本文依赖的事实 |
| --- | --- |
| src/mengxu/rule/AbstractRule.java | 逐项评分、覆盖 priority、初始首项和 priorTo 选择 |
| src/mengxu/taskscheduling/Task.java、TaskOption.java | 全工作流就绪扫描、路由包装、平分与 compareTo 陷阱 |
| src/mengxu/simulation/event/*.java | 构造副作用、四事件阶段、两轮路由和共享服务器的 owner/暂存差异 |
| src/mengxu/simulation/DynamicSimulation.java | 设备堆归并、全局弹出、时钟和 trigger |
| src/mengxu/taskscheduling/MobileDevice.java、Server.java | 队列缓存差异、完成与生成辅助行为 |

### 10.2 明确的 Python 调整

纯构造、显式派发、受限视图、规范对象身份、完成记录改存 Execution、显式预约和去重、全固定输入统计、明确失败状态，都是已采用的 Python 设计；不能写成 Java 已经这样实现。对可达边界是否改变结果，要用实现后的固定输入对照判断。

### 10.3 设计完成与待验证

本轮**最终接口第一版已设计完成**。待做的是实现和验证，包括字段走查、边界保护、兼容队列、日志无干扰和 Java 固定输入适配。Python/JDK 的具体版本、测试框架、CLI 和文件编码细节在实现准备阶段记录，不以未选择框架为由重新打开状态归属或事件先后设计。

以后整套文档同步时应更新：00 导航和进度；02 的上述模块职责；03 的记录/实际与计划说明；04 的 priority 修改者及接口链接；05 的下一步；06 的差异及目标运行环境；07 的修改入口链接；08 中“接口和同时刻策略待设计”的旧进度。本文未新增需由固定实例提供的运行字段。
