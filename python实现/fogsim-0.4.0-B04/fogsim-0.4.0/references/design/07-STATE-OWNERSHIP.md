# 状态归属表与关键设计说明

文档集版本：1.1.0；更新日期：2026-10-22（America/Los_Angeles）。

状态：**本轮范围内的状态归属表第一版设计已完成，作为当前 Python 设计基线。** 这里的完成表示已明确权威位置、引用关系、修改职责和时机、初始值、固定重跑恢复方式及不变量；不表示实现完成或 Java/Python 行为对照通过。完整事件读写表、接口与同时刻比较策略仍是后续独立设计工作。

返回 [总览](00-START-HERE.md)；进度见 [05](05-PROGRESS-AND-NEXT.md)；字段名称与类型见 [04](04-MODEL-FIELDS.md)；职责见 [02](02-FILE-STRUCTURE.md)；输入输出见 [03](03-INSTANCE-IO-CONTRACT.md)；源码证据与差异见 [06](06-JAVA-MAPPING-AND-SEMANTICS.md)。

## 1. 当前边界与证据等级

- 0.1 先实现固定输入、单任务和链式工作流；0.2 验收分叉汇合、竞争、同时刻事件及 Java/Python 对照。所有运行验收仍未开始。
- 本文使用当前提供的七份既有 Markdown、阅读计划及 Java 压缩包。图片仅作导航。原始材料指纹见 06；本轮没有新增论文语义结论。
- **源码事实**：从当前压缩包的生效 Java 语句静态核对，不等于运行证据。
- **Python 设计基线**：本轮选择的组织方式、保护操作及重跑方式；明确记录与 Java 的结构或行为差异。
- **尚待验证**：需要具体实例、Java 调试入口或运行轨迹才能确认的等价性和边界行为。
- 本文不展开完整四事件读写矩阵，不冻结方法签名、JSON 键名、Python 类型实现方式或事件堆比较键。

## 2. 状态归属、对象引用与快照

状态归属回答“哪个位置保存的值是权威，由谁负责维护”；持有引用回答“哪个对象能够找到它”。持有引用不自动获得修改权限。

例如 Workflow.tasks、TaskOption.task、Task.parents/children 和事件可以引用同一个 Task；它们读取同一份 Task.completed。事件若另外保存一个可独立修改的 task_completed，才形成容易失步的运行状态副本。

容器有自己的归属：Resource 管理等待队列成员关系，Workflow 管理已完成执行成员关系，SystemState 管理全局生命周期成员关系。容器中的元素引用同一个模型对象，不复制其可变字段。索引负责定位，不另存派发或完成标记。

trace 保存当时的数值快照，属于历史证据；它不构成供调度读取的第二套实时状态。不可变 InstanceSpec 可跨轮复用，其中的输入数值也不属于上一轮运行状态。

## 3. 共同维护约定

1. 固定实例加载器读取并验证 InstanceSpec；运行构建过程再建立独立模型对象、拓扑和索引。模型构造不隐式启动事件循环、生成下一工作流或修改共享 sampler。
2. 一轮运行中，任务标记与模型状态只由指定职责操作修改；规则函数读取候选情境并返回分数，由评分选择组件保存 priority。
3. “派发操作”“任务完成操作”“开始安排操作”“工作流完成登记操作”是职责名称，接口另行设计。
4. 跨字段一致性在一次职责操作完成后的稳定观察点成立。操作内部不对外暴露半完成状态；失败的提交应中止运行并说明原因，不能继续使用半更新状态。
5. 固定重跑从同一个 InstanceSpec 新建整套运行对象。所有事件、选项、拓扑、索引、预约都连接本轮对象；不能只恢复两个任务布尔值后继续使用旧事件或旧队列。
6. 保留输入和约定的遍历顺序；不用无序集合迭代或新增 ID 平分键改变选择结果。

## 4. 模型局部状态

以下表格均为 Python 设计基线；具体源码事实集中解释于第 7 节。时间单位为秒。

### 4.1 Task、TaskOption、Workflow 与 Execution

| 状态或字段 | 唯一权威保存位置 | 引用或读取者 | 允许修改者与修改时机 | 初始值 | 固定实例重跑恢复方式 | 必须保持的不变量 |
| --- | --- | --- | --- | --- | --- | --- |
| Task.dispatched | 对应 Task | 就绪检查、TaskOption、事件、调试读取 | 派发操作；选定资源并提交上传完成事件时置真 | False | 新建 Task，恢复 False | 一轮内只由假变真；上传、排队、执行和完成后均保持真；每任务只派发一次 |
| Task.completed | 对应 Task | 后继就绪检查、Workflow、统计 | 任务完成操作；含下载的完成事件真正触发时置真 | False | 新建 Task，恢复 False | completed 为真必然 dispatched 为真；与该任务完成记录同步；一轮内不回退 |
| TaskOption.ready_time | 对应 TaskOption | TWT、规则评分、诊断 | 工作流到达处理设置入口全部选项；任务到达处理设置选中选项，具体赋值见 7.2 | 0.0 | 全部选项重建并恢复零 | 不统一解释为依赖满足时刻；不擅自刷新后继全部选项 |
| TaskOption.priority | 对应 TaskOption | 当前候选比较；决策日志立即复制数值 | 评分选择组件；每次决策对实际候选逐项重算并覆盖 | 0.0 | 全部选项重建并恢复零 | 本次选择只使用本次评分；零分不能用来判断是否评分；路由分数可被排序分数覆盖 |
| Workflow.completed_executions | 对应 Workflow 的有序列表 | NTR、完成检查、统计输出；引用同一 Execution | 任务完成操作；完成事件触发且该任务尚未完成时追加 | 每工作流独立空列表 | 新建空列表 | 每任务至多一条；实际完成处理顺序；长度等于本工作流 completed=True 的任务数 |
| Workflow.completion_time | 对应 Workflow | flow_time、makespan、输出 | 工作流完成登记操作；全部任务完成后设置 | None | 恢复 None | 完成后等于任务 finish_time 最大值；完成登记后不覆盖 |
| Workflow.completion_registered | 对应 Workflow | 完成登记操作、状态检查 | SystemState 的完成登记操作统一置真 | False | 恢复 False | 当前无 warm-up 模式中，等价于该工作流在 completed_workflows 中 |
| Execution.option/start_time/compute_finish_time/finish_time | 对应 Execution 对象 | 开始/完成事件、资源预约、执行索引、Workflow 完成记录 | 接受一个确定开始安排时建立；建立后不修改 | 未安排时没有对象 | 丢弃旧 Execution，按本轮安排重建 | compute_finish_time=start_time+PT；finish_time=compute_finish_time+DT；对象存在不表示任务已经开始或完成 |

固定字段继续归各自模型对象：Workflow 的 ID、owner_device、release_time、tasks；Task 的 ID、workflow、parents、children、options；TaskOption 的 task、resource、三项时长；Resource 的 ID、类型和能力参数。由构建过程赋值，一轮内不变，重跑按同一输入重建。04 中后续参数字段仍为预留；未知值用 None，尚未启用的规则不得读取它们参与运算。

当前可路由条件由“工作流已经进入 active_workflows、任务未派发、未完成、全部前驱完成”派生，不另存 ready 布尔字段。

### 4.2 Resource

| 状态或字段 | 唯一权威保存位置 | 引用或读取者 | 允许修改者与修改时机 | 初始值 | 固定实例重跑恢复方式 | 必须保持的不变量 |
| --- | --- | --- | --- | --- | --- | --- |
| available_time | 对应 Resource | FCFS 路由、MRT、开始安排检查 | 开始处理；开始事件触发时设为此次 Execution.finish_time | 0.0 | 恢复零 | 下载计入占用；空闲后允许早于当前时钟；完成处理不得将它改写为当前时钟 |
| waiting_queue | 对应 Resource 的有序列表 | 排序情境只读引用选项 | 资源入队/出队操作；已到达但不能开始时入队，选中并接受开始安排时出队 | 独立空列表 | 新建空列表 | 成员已到达、已派发、未完成且目标为本资源；每任务至多一项；已出队预约不再留队 |
| queued_processing_time | 对应 Resource 缓存字段 | WIQ、诊断 | 仅资源队列操作同步更新 | 0.0 | 恢复零 | 数学含义为等待队列 PT 总和；不含预约或执行项目；浮点一致性用容差检查 |
| queued_total_time | 对应 Resource 缓存字段 | TTIQ、诊断 | 仅资源队列操作同步更新 | 0.0 | 恢复零 | 数学含义为各队列项 PT+UT+DT 总和；保留 Java 运算次序和资源类型差异 |
| completed_task_count | 对应 Resource | 资源统计、检查 | 任务完成操作；本资源执行真正完成且未重复登记时加一 | 0 | 恢复零 | 等于本资源实际完成的任务数；不是其发布工作流的完成数 |
| pending_start（新增） | 对应 Resource；值为一个 Execution 引用 | 开始安排检查、开始事件、诊断 | 开始安排操作设置；对应开始事件核对身份后清除 | None | 恢复 None | 每资源最多一项待开始预约；与一条待处理开始事件引用同一 Execution |

队列成员变化和两个缓存变化必须通过同一队列操作完成。出队不存在的项目、重复入队等应报告状态错误，不允许缓存与成员关系分别被外部修改。

## 5. 系统全局状态

SystemState 管理运行模型的集合和索引；Engine 持有 SystemState 引用。规则情境提供受限的只读信息范围，不把完整内部索引作为规则可访问接口。

| 状态或字段 | 唯一权威保存位置 | 引用或读取者 | 允许修改者与修改时机 | 初始值 | 固定实例重跑恢复方式 | 必须保持的不变量 |
| --- | --- | --- | --- | --- | --- | --- |
| clock_time | SystemState.clock_time | 事件处理、规则可见状态、trace | Engine；取出下一事件后、触发前推进 | 0.0 | 恢复零 | 一轮内不倒退；触发时等于该事件时间；验证容差不改变排序语义 |
| 资源列表、resources_by_id | SystemState 的资源注册与索引 | Workflow、TaskOption、事件、当前情境引用同一资源 | 运行构建过程建立 | 按输入与约定顺序建立 | 重建并重新连接引用 | 同一个资源 ID 定位同一对象；M0/E0 数字 ID 都为零也不能混淆 |
| workflows_by_id、tasks_by_key | SystemState 完整对象索引 | 构建、事件定位、检查、输出；规则不直接获得完整索引 | 运行构建过程建立 | 从全部固定输入建立 | 重建 | 任务键为 (workflow_id, task_id)；与拓扑和选项引用同一 Task |
| pending_arrivals | SystemState 有序映射；保存未处理到达事件的工作流引用 | 初始化、到达处理；规则不可见 | 初始化加入；到达处理移出 | 全部输入工作流 | 从全部输入重建 | 到达事件尚未处理；允许 release_time 等于 clock_time |
| active_workflows | SystemState 有序映射；保存已到达、未完成登记工作流引用 | 就绪检查、当前决策情境 | 到达处理加入；工作流完成登记移出 | 空 | 新建空映射 | 只有其中的工作流可产生当前路由候选；不含未来或已登记完成项目 |
| completed_workflows | SystemState 有序映射；按实际登记顺序保存引用 | metrics、输出、完成检查 | 工作流完成登记操作加入 | 空 | 新建空映射 | 每工作流一项；任务全部完成；与 completion_registered 一致 |
| executions_by_task（新增） | SystemState 执行登记索引；值为 Execution 引用 | 开始/完成处理、Workflow 完成记录、输出 | 开始安排被接受时登记，运行结束前保留 | 空 | 新建空索引 | 当前非抢占、无重试模型每任务至多一个；登记不表示已开始或完成 |
| 输入数、未到达数、已到达数、完成工作流数等 | 从上述容器派生，不另存可变同义计数 | 结束检查、metrics、输出 | 无独立修改者 | 从初始容器计算 | 重新计算 | 已到达数量=len(active)+len(completed)，完成数量=len(completed) |
| makespan、flow_time 等派生结果 | metrics 读取模型计算；输出仅为结果快照 | 正常结束后的调用者 | 无独立实时修改者 | 未完成时无最终 makespan；未完成工作流 flow_time 为 None | 按本轮重新计算 | 0.1 全部输入参与；异常结果不能伪装正常完成指标 |

稳定观察点满足：全部工作流由 pending_arrivals、active_workflows、completed_workflows 三个互不重叠的成员集合组成，三者并集等于 workflows_by_id 的成员集合。

“已经到达过”的成员范围由 active 与 completed 合并派生，不另存一个可独立修改的 arrived 集合；实际到达顺序由 trace 记录。不能把这两个容器的拼接顺序当作历史到达顺序。

初始化时 release_time=0 的工作流也先在 pending_arrivals 中；等它的到达事件真正处理后才移入 active_workflows。仅凭 release_time<=clock_time 不能替代到达操作。

资源索引用全局唯一展示 ID。numeric_id 保留 Java 比较语义，但移动设备和服务器属于不同数字 ID 空间。任务索引必须使用工作流 ID 与任务 ID 的组合键。

## 6. 事件、日志与运行控制

| 状态或字段 | 唯一权威保存位置 | 引用或读取者 | 允许修改者与修改时机 | 初始值 | 固定实例重跑恢复方式 | 必须保持的不变量 |
| --- | --- | --- | --- | --- | --- | --- |
| 待处理事件队列 | Engine.event_queue 持有的 EventQueue | Engine 取事件；事件处理通过受控入口提交事件 | EventQueue 维护内部结构，Engine 驱动入队/取出 | 构建时为空；初始化完成后每工作流一条到达事件 | 新建队列并重新安排到达事件 | 事件只引用本轮对象；稳定观察点每预约对应一条开始事件；比较规则统一归 EventQueue |
| 事件对象的数据与模型引用 | 对应事件对象 | Engine、处理逻辑、trace | 创建时赋值，已入队事件的时间和比较相关数据不随意修改 | 尚未安排时没有对象 | 丢弃旧事件并重建 | 事件引用模型，不保存独立任务状态副本；Python 构造只保存参数 |
| processed_event_count | Engine.processed_event_count | trace 保存序号快照 | Engine；每处理一条事件递增一次 | 0 | 恢复零 | 表示实际处理顺序，不自动成为事件堆的平分键 |
| 事件/评分/队列快照、任务时间 trace | Engine.trace 持有的 TraceRecorder | 输出、轨迹比较与调试 | 各职责操作经记录器追加；评分时立即复制数值，实际事件触发时记录动作 | 空记录 | 新建记录器，旧轮输出独立保留 | 历史快照不随 priority 改变；日志开关不改变调度；计划与实际触发含义分开 |
| run_status、stop_reason | Engine 的运行控制字段 | 入口、输出、评估层 | Engine；初始化、启动、正常完成或异常时修改 | 初始化后 READY；原因为 None | 新建运行控制状态 | 只有全部输入完成才为正常完成；事件耗尽仍有未完成任务则失败 |

run_status 的实现类型和方法签名留给接口设计；其归属与生命周期已确定。异常时保留可诊断的模型、时钟和日志，不用把 clock_time 改为极大值来表达失败。后续训练异常惩罚如何映射到目标值由 evaluation 另行设计。

事件队列归 Engine/EventQueue；执行安排由 SystemState 登记、Execution 保存时间字段；已完成执行列表归 Workflow；调试历史归 TraceRecorder。资源不反向持有整个实验入口，也不自行管理另一套可独立启动的事件循环。

Java 的设备暂存队列与全局队列归并可能影响同时刻事件插入顺序。Python 集中事件管理的职责选择已完成；内部是否需要兼容归并机制，要在事件表和比较策略中确定并验证，不能据此宣称严格轨迹一致。

## 7. 关键选择的源码事实、理由与限制

以下路径均相对于 Java 压缩包内的 Fog-Computing-multiDeviceDebug/；文件不依赖本次临时解压路径。

### 7.1 派发与任务完成标记

源码事实：src/mengxu/simulation/event/TaskVisitEvent.java 的带时间构造函数立即调用 task.setDispatch(true)，上传完成的 trigger 才设置 readyTime。ProcessFinishEvent.trigger 才设置 complete=true。因此上传期间 dispatched 就应为真，不能等到到达、开始或完成时才设置。

Python 基线：明确的派发操作协调资格检查、选项选择、标记和事件提交；构造事件只保存参数。Task.completed、Workflow.completed_executions 和对应 Resource.completed_task_count 由同一次任务完成操作维护。

理由：Task.dispatched 是任务级的唯一防重复派发状态，所有候选引用同一 Task 才能共同看到它；日志、事件不能另外维护一份标记。

### 7.2 ready_time 与 priority

源码事实：JobArrivalEvent.trigger 设置入口全部选项为 releaseTime；TaskVisitEvent.trigger 设置选中选项为到达时间；Task.java/TaskOption.java 的后继路由路径没有统一刷新全部选项的 readyTime。JobShopAttribute 中 TWT=clockTime-readyTime。

Python 基线：保留上述赋值位置。后继尚未到达时，选项可能仍为初始零；这不是一个应按字段名称自动修正的错误。真实派发/到达/开始历史由 trace 保存。

源码事实：src/mengxu/rule/AbstractRule.java 的 nextTaskOption/priorTask 会重新评分并覆盖候选 priority；TaskOption.priorTo 按小分数优先，再比较工作流发布时间、所属设备数字 ID 和工作流 ID，完全相同保留先遍历候选。

Python 基线：priority 只表示最近一次评分，允许排序评分覆盖路由评分；每次决策重新评分，日志保存当次快照，不新增永久任务优先级。

补充事实：ProcessFinishEvent 的非空 DAG 后继路径会在条件判断和后续取值中重复调用带路由评分的 getNextDag；TaskOption.getNextDag 本身也会查询就绪任务。完整调用次数及日志对照在事件设计中继续核对，不能把整个调用链视为纯只读查询。

### 7.3 资源时间与队列缓存

源码事实：Process 构造计算 finishTime=startTime+procTime+downloadDelay；ProcessStartEvent.trigger 才把资源 readyTime 设置为该值。完成处理没有把 readyTime 持续钳制为当前时钟。FCFS 路由与 MRT 直接读取它。

Python 基线：available_time 保留“最近已触发开始的执行所确定的可用时间”，允许空闲后早于时钟；预约不提前改写它。等待队列缓存只含尚在队列的项目，已出队预约与正在执行的项目均不计入。

源码事实：Server.java、MobileDevice.java 入队均累加 PT 和 (PT+UT+DT)，但空队清理有差异：

| 情况 | Server | MobileDevice |
| --- | --- | --- |
| 出队后仍有项目 | 减去相应时长 | 减去相应时长 |
| 出队后为空 | 两个缓存直接归零 | 仍执行减法，无空队归零分支 |
| 空队读取缓存 | 返回零 | 直接返回缓存值 |

Python 基线按资源类型保留差异。数学上缓存是队列时长总和；浮点检查用容差，不通过重新 sum、统一钳零或改运算顺序静默改变评分输入。本地空队可能出现浮点残差是数值推断，具体残差和评分影响尚待运行验证。

queued_total_time 包含已经完成上传的 UT，是源码特征定义，不表示出队后再次上传。

### 7.4 完成执行记录与工作流登记

源码事实：Job.java 保存 ProcessFinishEvent 列表，追加方法不去重，超量时打印错误；isDone 检查任务 complete。ProcessFinishEvent 的 DAG 分支检查 isDone 和登记标记；远程 LINKED 分支没有同样的保护。MobileDevice.completeJob 还包含统计筛选逻辑。

Python 基线：完成列表存同一 Execution 的引用；任务重复完成报告状态错误，不能再次追加或计数；已登记工作流再次请求登记时不重复加入。若标记与集合不一致，应报告不变量破坏，不能静默掩盖。

最终任务完成后，工作流登记操作统一设置 completion_time、将其从 active 移入 completed 并设置 completion_registered。在稳定观察点，登记标记与 completed 集合一致。这里采用当前全部输入参与、无 warm-up 的约定，不把它推广成 Java 原统计窗口的行为。

理由：is_done 是任务状态的派生结果，completion_registered 是登记动作的保护，两者不同。工作流级标记不能防止同一任务被重复追加完成记录。

### 7.5 Execution 的建立与历史

源码事实：TaskVisitEvent 在判断是否需要排队前先构造临时 Process；该对象不一定对应一个被接受的开始安排。

Python 基线：只有确定开始安排被接受后，才创建并登记正式 Execution。等待队列继续保存 TaskOption。开始事件、完成事件、资源预约与完成历史共同引用这一 Execution；只有完成事件触发才把它加入 Workflow.completed_executions。

理由：把临时估计登记成执行或完成，会使计数、NTR 和日志混淆。Execution 内的时间是已确定安排的时间；开始或完成动作是否实际发生，分别由事件生命周期、预约与 Task.completed 判断。trace 在实际触发时记录事实，不通过已经计算出的 finish_time 宣称提前完成。

### 7.6 同时刻待开始预约

源码事实：MobileDevice.canAddToQueue(Process) 只从 simulation.getEventQueue() 的迭代器取第一个元素检查，使用 if 而非遍历；没有检查全部全局事件或设备暂存事件。TaskVisitEvent/ProcessStartEvent 比较中存在开始事件先于同刻到达事件的明确分支。完整比较与堆行为未完成运行对照。

Python 基线增加 Resource.pending_start，类型为 Execution 或 None：

1. 接受开始安排前确认本资源没有其他 pending_start。直接开始还要求 available_time<=clock_time；从队列接受安排时，确定 start_time>=max(clock_time, available_time)。
2. 同一次操作完成必要的出队及缓存更新、建立 Execution、登记 executions_by_task、设置 pending_start、提交开始事件。不能只在直接开始路径检查预约。
3. 对应开始事件触发时核对预约对象身份，清除预约、更新 available_time 并安排完成事件。其他完成事件不能随意清除这项预约。
4. 已有预约时，新的到达任务进入等待队列；完成处理也不能再安排第二个待开始项目。后续排序和选中时机由完整事件表展开。

例如同刻两个任务先后到达空闲 E0：第一个安排开始后 available_time 可能仍为旧值；第二个通过 pending_start 看到已有预约并等待。资源上的执行占用区间包含计算和下载，允许上一项结束时下一项开始。

理由：保持 available_time 的 FCFS/MRT 语义，同时显式表达“动作已安排但未触发”。预约字段保存执行引用，可检查身份，不新增容易失步的 busy 布尔值。

尚待验证：此保护与 Java 的比较、暂存队列归并、canAddToQueue 组合在具体实例中的行为是否一致。它是已选定的 Python 设计调整，不是已证明无差异的直译；如果发现轨迹差异，应记录具体触发条件后再决定兼容方案。

### 7.7 工作流集合与未来信息

源码事实：SystemState.addJobToSystem 在 releaseTime>clockTime 时接纳新生成工作流，立即放入 jobsInSystem 并增加生成计数；该字段包含未来工作流。JobArrivalEvent 的构造只保存参数。因此 jobsInSystem 不能直接解释为“已经到达”。

Python 基线通过 pending/active/completed 显式表达到达生命周期。固定输入可接纳 t=0；规则只获得已到达范围、当前候选和资源状态，不能读取未来实例数量、到达时间或拓扑。完整内部索引用于定位和检查，不等于规则接口。

## 8. 初始化、固定重跑与 RNG/seed

### 8.1 固定实例

首次初始化分为读取验证 InstanceSpec、建立本轮运行对象、设置初值和索引、安排每个工作流的到达事件。模型构造与运行初始化职责分开，不在构造资源时隐式启动随机生成。

固定重跑复用同一 InstanceSpec，重建 Task/TaskOption/Workflow/Resource、SystemState、Execution 索引、事件队列、日志和运行控制。全部运行对象之间重新连接，上一轮日志作为独立输出保留。固定重跑不靠 seed 恢复实例参数，也不使用 Java clone 作为新运行图的替代。

### 8.2 后续随机阶段的归属

| 状态或操作 | 权威归属与修改者 | 初始与恢复约定 | 当前阶段 |
| --- | --- | --- | --- |
| seed 配置、轮换策略 | 运行/评估配置；评估层决定选择或轮换 | 显式给定；轮换时使用明确新 seed，不能随固定重跑隐式改变 | 后续启用，不向 0.1 输入新增必需字段 |
| RNG 内部状态、生成进度和生成 ID 计数 | 实例生成组件；生成操作推进，重设操作恢复 | 按明确随机流与 seed 初始化；同 seed 重生成需还原调用顺序和共享关系 | 后续接口及 Java 对照待完成 |
| 已到达/完成数量 | 当前 SystemState 容器派生 | 本轮对象重建后重新计算 | 0.1 使用 |
| warm-up、记录窗口与统计计数 | 运行/评估配置和后续统计状态 | 由未来评估设计明确恢复条件 | 0.1 不启用；生成数、完成数、纳入统计数不得合并 |

固定重跑、新 seed 生成、同 seed 重生成和继续当前随机流是四种不同操作。共享 RNG 时只共享一个生成器引用，不能未经核对改成每设备独立流。Resource 不承接随机生成、GP 评估或 seed 轮换职责。

### 8.3 Java 静态核对边界

- DynamicSimulation 构造时创建并重设 RNG、采样设备和服务器参数，最后调用 setup 安排首次工作流。
- MobileDevice 构造会修改传入 interReleaseTimeSampler 的 mean=100，并建立 DigraphGeneratorMX；不是仅保存构造参数。
- DynamicSimulation.rerun 调用 resetStateforRerun、setup、run，没有调用 reseed；reset(seed) 调用 reseed 后清状态；rotateSeed 增加 SEED_ROTATION=10000 后重设并清状态。
- SystemState.reset/resetforRerun 清时钟、集合和相关计数，重置资源/设备；清 firstArriveJobRecordedTime 的语句被注释。
- reset 不重新构造资源参数；首次构造调用了资源采样。因此注释声称“同 seed 得到同实例”尚需完整随机调用链和运行验证，不能仅凭方法名称或注释确认。

## 9. 稳定观察点的不变量

| 范围 | 需要检查的关系 |
| --- | --- |
| 对象身份 | 每个任务键对应一个 Task；拓扑、选项、事件和索引引用它；事件和预约不得串入旧轮对象 |
| 生命周期 | pending、active、completed 互斥且覆盖全部输入；已登记完成工作流全部任务完成；未来入口不得派发 |
| 任务与记录 | completed 蕴含 dispatched；每任务至多一个正式 Execution、一个完成记录；完成记录数等于任务完成数 |
| 资源占用 | 被接受执行的占用区间包含下载且不重叠；每资源最多一个 pending_start；开始事件与预约一致 |
| 等待队列 | 每项目标为该资源且已到达、已派发、未完成；预约/正在执行项目不在等待队列；缓存按规定操作维护 |
| 工作流登记 | 当前 0.1 中 completion_registered 等价于在 completed_workflows；completion_time 为完成任务时间最大值 |
| 全局任务计数 | 所有资源 completed_task_count 之和=所有工作流完成执行数之和=completed=True 的任务总数 |
| 时钟与日志 | 时钟不倒退；日志序号只记录实际处理顺序；关闭日志不改变选择和事件排序 |
| 正常结束 | 全部输入工作流完成才成功；事件耗尽但仍有未完成任务则失败；正常结果使用本轮数据 |

浮点容差用于检查缓存及结果，不自动成为事件比较相等规则；资源队列空时的具体缓存差异按 7.3 保留。

## 10. 设计完成度、后续任务与文档分工

| 项目 | 当前结论 |
| --- | --- |
| 权威位置、引用者、修改职责/时机、初值、固定重跑、不变量 | 本轮状态归属设计已完成 |
| pending_start、生命周期集合、executions_by_task 的选择 | 已纳入当前 Python 设计基线；预约与 Java 的行为等价性尚待验证 |
| Java 构造副作用、队列差异、核心赋值位置 | 已静态核对并记录；没有运行验证 |
| 四事件完整读写、操作先后与产出事件 | 尚未完成，是下一项独立设计任务 |
| 同时刻完整比较、堆平分、设备事件归并兼容性 | 尚未定稿与验证，不能自行加入稳定序号后称严格一致 |
| 对象相等/哈希、类型导入、加载器/规则/事件签名与序列化 | 尚未完成接口设计；不改变已选定的状态归属 |
| Python 实现、Java 固定入口、测试及运行对照 | 尚未开始 |

下一次从四种事件的完整读写表开始，使用本文的修改职责约束逐项展开；之后设计接口并走查固定链完整字段生命周期，再进入编码。若发现归属冲突，记录原因并同步修订，不能把设计基线理解为不可修改。

04 维护字段名称、类型、初值和 Java 对应；本文维护权威归属、维护职责及理由。02 维护文件职责，03 维护输入输出，05 维护进度与待办，06 维护源码证据和差异。避免复制出两套可独立演变的完整状态表。

## 11. 本次变更与检查

- 从 1.0.0 的空模板形成完整状态归属设计，新增 pending_start、SystemState 生命周期集合与执行索引说明。
- 补正本地设备与服务器队列清理差异；记录任务派发构造副作用、临时 Process、工作流完成保护及 Java 重跑限制。
- 已将 00—06 的进度、字段、职责和证据边界与本文衔接，文档集统一为 1.1.0。
- 本次检查为文档交叉引用、字段/归属一致性、JSON 示例可解析性、来源指纹和源码文本核对；未运行 Java 或 Python 模拟器，未进行运行验收。
