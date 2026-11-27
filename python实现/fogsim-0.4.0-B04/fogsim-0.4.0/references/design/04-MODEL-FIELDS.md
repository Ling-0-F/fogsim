# 模型字段设计基线

文档版本：1.1.0；更新日期：2026-10-22（America/Los_Angeles）。状态：当前字段基线已随状态归属设计更新；完整归属、修改职责和重跑规则见 [07](07-STATE-OWNERSHIP.md)。状态归属表第一版设计已完成；尚未编码或运行对照。

返回 [总览](00-START-HERE.md)；输入信息见 [输入输出约定](03-INSTANCE-IO-CONTRACT.md)。

## 1. 阅读约定

- 固定：读取或构建时确定，一次模拟中不改变；不代表必须使用 frozen dataclass。
- 运行：随事件改变，重新运行时应恢复初始值。
- 预留：确定用途和名称，0.1 可以不启用；未知参数用 None。
- 派生：根据已有字段计算，通常不额外保存。
- 所有时间单位为秒。除说明外，数值参数和时间使用 Python float。
- 表中的初始值是设计建议。与 Java 的默认 0、-1 或 null 不同之处已注明，不能视为原源码原样声明。
- 集合必须每个实例独立创建，不能共享可变默认列表或字典。

## 2. 类型对应与对象引用

| Java 类型/表示 | Python 建议 | 说明 |
| --- | --- | --- |
| double | float | 常用 CPython 中通常同为 64 位双精度；Python 无内置 double 类型名 |
| Java float | 不作为这些 double 字段的对应 | Java float 是 32 位单精度 |
| boolean | bool | 布尔值 |
| int | int | Java 通常为 32 位有符号整数；Python int 可增长，当前 ID 不需模拟溢出 |
| List / LinkedList | list[...] | 保留遍历与移除语义，不能因为名字是队列就改为按入队次序直接出队 |
| Map<Integer, Double> | dict[str, float] | 手工任务 ID 采用字符串；未来 Java 对照需显式 ID 映射 |
| 基本类型 double 的未完成时间 | float 或 None | None 明确表示尚未完成；这是 Python 设计调整 |

Java 小写 float/double 是基本类型，Float/Double 为包装类。源码中的 procTime、readyTime 等实际声明为 double；“Java 对应字段”列不是类型名称。

文件中用 ID 连接信息；加载后模型建议使用对象引用。一个任务在工作流、候选选项、依赖和事件里必须引用同一个 Task。对象比较/哈希策略仍待接口设计，不能无意使用递归结构的默认字段相等比较替代 Java 引用身份。

## 3. Workflow（Java Job）

位置：`model/workflow.py`。

| 字段 | Python 类型 | Java 对应字段与类型 | 初始值/来源 | 类别与用途 |
| --- | --- | --- | --- | --- |
| id | int | id: int | 文件中的全局唯一 ID | 固定；例如 0 |
| owner_device | MobileDevice | mobileDevice: MobileDevice | 根据输入设备 ID 查找 | 固定；发布设备 |
| release_time | float | releaseTime: double | 输入 | 固定；工作流到达时刻 |
| tasks | list[Task] | taskList: List<Task> | 加载后建立 | 固定拓扑；运行时不清空以免影响调试和派生信息 |
| completion_time | float 或 None | completionTime: double | None | 运行；全部任务完成时设置；Java 原字段默认 0.0 |
| completed_executions | list[Execution] | processFinishEvents: List<ProcessFinishEvent> | 空列表 | 运行；任务完成时追加完成执行记录，减少对事件对象的耦合 |
| completion_registered | bool | hasAddToCompletedList: boolean | False | 运行；仅工作流完成登记操作置真，当前 0.1 中与全局完成集合一致 |
| weight | float 或 None | weight: double | 0.1 为 None | 预留；参数生成或使用权重的规则启用；不能把 None 传入权重运算 |

派生信息：

| 属性 | 定义 |
| --- | --- |
| task_count | len(tasks) |
| completed_task_count | len(completed_executions)；应与 completed=True 的任务数一致 |
| is_done | 全部任务 completed=True |
| flow_time | 完成后为 completion_time - release_time；未完成时为 None |

`completion_registered` 表示登记行为，区别于计算所得 is_done。任务完成操作同时维护 Task.completed、此工作流的完成记录和执行资源的完成计数；重复任务完成不能再追加或计数。工作流完成登记统一维护 completion_time、全局集合和登记标记。Java jobType 暂记在迁移表；当前链式也按 DAG 表达，严格 LINKED 分支如有需要再加入。criticalPathStartTask 的相关 CPOP 方法在本包中被注释，先记录，不创建无用途字段。

## 4. Task

位置：`model/task.py`。

| 字段 | Python 类型 | Java 对应字段与类型 | 初始值/来源 | 类别与用途 |
| --- | --- | --- | --- | --- |
| id | str | id: int | 输入，例如 A | 固定；工作流内唯一，Java 数字 ID 需映射 |
| workflow | Workflow | job: Job | 加载时建立引用 | 固定；所属工作流 |
| parents | list[Task] | parentTaskList: List<Task> | 从边列表建立 | 固定；前驱引用 |
| children | list[Task] | childTaskList: List<Task> | 从边列表建立 | 固定；后继引用 |
| options | list[TaskOption] | taskOptions: List<TaskOption> | 从输入时长与合法资源建立 | 固定候选集合；内部选项有运行字段 |
| dispatched | bool | dispatch: boolean | False | 运行；派发提交时置真，上传/排队/执行/完成后均保持真；Java 在 TaskVisitEvent 构造时置真 |
| completed | bool | complete: boolean | False | 运行；含下载的完成事件触发后为 True |

当前不另存 ready 布尔字段。工作流已到达后，根据未派发、未完成、全部前驱完成判断是否可路由。未来工作流即使所有入口无前驱，也不能提前调度。

### 4.1 后续参数字段

| 字段 | Python 类型 | Java 对应 | 0.1 初始值 | 含义与启用阶段 |
| --- | --- | --- | --- | --- |
| workload | float 或 None | workload: double | None | 工作量；实例生成阶段 |
| data_size | float 或 None | data: double | None | 任务自身数据量；实例生成阶段 |
| input_data_by_parent | dict[str, float] 或 None | inputDateMap: Map<Integer, Double> | None | 各前驱传入的数据量 |
| output_data_by_child | dict[str, float] 或 None | outputDateMap: Map<Integer, Double> | None | 向各后继传递的数据量 |
| total_input_data | float 或 None | totalInputData: double | None | 前驱传入总量 |
| total_output_data | float 或 None | totalOutputData: double | None | 向后继传出的总量 |

Java 构建期间使用 0/-1 等初始值，再采样赋值；Python 的 None 表达“此输入模式没有提供”。真实参数模式启用时须一起建立有效参数。

Java 在构建执行选项后调用 mapClear 清空输入输出映射，但保留总量。后续需明确保留映射或清理的策略，不能在映射清空后又从空映射重新计算总量。rank 等通过方法计算，暂不创建一组数值缓存。

## 5. TaskOption

位置：`model/task.py`。一个 Task 可有多个选项，但每个选项都指向同一个 Task。

| 字段 | Python 类型 | Java 对应字段与类型 | 初始值/来源 | 类别与用途 |
| --- | --- | --- | --- | --- |
| task | Task | task: Task | 构建传入 | 固定；所属任务 |
| resource | Resource | server: Server / mobileDevice: MobileDevice | 根据具体资源建立引用 | 固定；目标处理器，Python 统一表达 |
| processing_time | float | procTime: double | 固定输入 | 一次运行中固定；计算时间 |
| upload_time | float | uploadDelay: double | 固定输入 | 固定；本地为 0 |
| download_time | float | downloadDelay: double | 固定输入 | 固定；本地为 0 |
| ready_time | float | readyTime: double | 0.0 | 运行；按 Java 事件赋值，GP TWT 读取 |
| priority | float | priority: double | 0.0 | 运行；最近一次评分，每次决策覆盖 |

上述字段建议现在保留。Java 可通过 setter 修改 procTime，但当前固定时长模式在开始模拟后不修改它。

### 5.1 ready_time 的准确含义

它是源码复用的时间记录，不统一等同于任务满足依赖的时刻：

1. 初始为 0.0。
2. 工作流到达时，入口任务的全部候选选项被设为工作流 release_time。
3. 上传完成的 TaskVisitEvent 触发时，选中选项更新为事件时间。
4. 当前后继路由路径没有在评分前统一更新全部候选选项的该值。

保留这些赋值，不能为了命名整齐把所有候选统一改成当前时钟。TWT=clock_time-ready_time；完整的派发与到达历史另由 trace 保存。priority 仅为最近评分，不代表任务永久优先级。

## 6. Resource 公共部分

位置：`model/resource.py`。Resource 是 Python 的公共模型建议，Java 的 Server/MobileDevice 没有这个公共父类。ResourceType 建议同文件定义 MOBILE、EDGE、CLOUD 三种类型。

| 字段 | Python 类型 | Java 对应字段与类型 | 初始值/来源 | 类别与用途 |
| --- | --- | --- | --- | --- |
| id | str | Python 展示/引用标识 | M0、E0、C0 等 | 固定；全局唯一，不据字典序决定 Java 优先级 |
| numeric_id | int | Server.id / MobileDevice.id: int | 按 Java 兼容映射建立 | 固定；比较或导出 Java 时使用 |
| resource_type | ResourceType | Server.type: ServerType；MobileDevice 隐含类型 | 输入 | 固定；资源类型 |
| available_time | float | readyTime: double | 0.0 | 运行；最近已触发开始的执行确定的可用时刻；预约不提前改写 |
| waiting_queue | list[TaskOption] | queue: LinkedList<TaskOption> | 独立空列表 | 运行；已经到达、尚未开工的候选 |
| queued_processing_time | float | totalProcTimeInQueue: double | 0.0 | 运行缓存；队列中 PT 之和 |
| queued_total_time | float | totalProcTimeAndUpLoadAndDownLoadTimeInQueue: double | 0.0 | 运行缓存；队列中 PT+UT+DT 之和，保留源码运算次序 |
| completed_task_count | int | numTasksCompleted: int | 0 | 运行；由该处理器真正执行完成的任务数 |
| pending_start | Execution 或 None | Python 新增，无直接字段对应 | None | 运行；已接受但开始事件尚未触发的预约引用，每资源至多一个 |
| processing_rate | float 或 None | processingRate: double | 0.1 为 None | 预留；以后 workload/rate 计算 PT |

除 processing_rate 外，上述字段均纳入 0.1 当前设计；processing_rate 以后启用。当前 M0.numeric_id=0，E0.numeric_id=0，C0.numeric_id=1；移动设备与服务器是不同的 Java ID 空间。服务器数字 ID 的映射为全部边缘在前、云在后。资源展示 ID 仍然全局唯一。

### 6.1 队列缓存

源码复核后的准确行为：入队均加 PT 与 (PT+UT+DT)；Server 出队后为空则将两个缓存归零，仍非空则相减；MobileDevice 出队始终相减，没有空队归零分支。Server 空队读取返回零，MobileDevice 直接返回缓存。Python 基线按资源类型保留差异，为 WIQ/TTIQ 对照准备。全部缓存更新由资源队列操作完成，外部不能分别手工修改；浮点检查用容差，不静默重新 sum 或统一钳零。

缓存不包含正在执行的任务；queued_total_time 包含已完成的上传时长是源码特征定义，不表示出队后再上传一次。对浮点缓存的严格对照需要保留加减顺序；直接重新 sum 可能产生微小数值差异。

### 6.2 available_time

开始事件将其设为 Execution.finish_time，包含下载。空闲后该值可以早于当前时钟，不持续钳制为 max(当前时钟, available_time)。源码 MRT 直接取 readyTime，FCFS 路由也直接取它。

新增 pending_start 保存待开始 Execution 的引用，不另存 busy 布尔值。所有接受开始安排的路径都要检查并建立预约；对应开始事件核对后清除，再更新 available_time。已有预约时不能再安排第二项。具体职责见 07；其与 Java 同时刻边界路径的等价性尚待验证。

## 7. MobileDevice / Server 特有部分

| 对象与字段 | Python 类型 | Java 对应 | 初始值 | 阶段与用途 |
| --- | --- | --- | --- | --- |
| MobileDevice.can_process_tasks | bool | canProcessTask: boolean | True | 现在；本场景允许本地计算，Java 构造时 false 后由配置设置 |
| Server.upload_bandwidth | float 或 None | uploadBandwidth: double | None | 预留；计算上传时间 |
| Server.download_bandwidth | float 或 None | downloadBandwidth: double | None | 预留；计算下载时间 |

即使 can_process_tasks=True，也只允许处理本设备发布的工作流。移动设备不需要远程带宽字段来表示本地 UT/DT=0。

### 7.1 Java MobileDevice 中移出资源模型的职责

| Java 字段组 | 计划位置 | 说明 |
| --- | --- | --- |
| seed、randomDataGenerator、各 sampler、digraphGeneratorMX | instances/生成及随机数管理 | 保留共享关系、seed 与调用顺序的核对，不自动改为每设备独立随机流 |
| routingRule、sequencingRule | 模拟器规则配置 | 0.1 共用一对；后续可按设备索引 |
| eventQueue | Engine.event_queue / EventQueue | 资源不管理独立事件循环；Java 暂存归并与平分行为仍需对照 |
| systemState、simulation | 按事件上下文/引擎提供 | 具体接口待设计，避免资源反向持有整个实验入口 |
| numJobsRecorded、warmupJobs | 运行/评估配置 | 0.1 全部输入参与统计 |
| numJobsReleased、numJobsCompleted、throughput | 0.1 从 SystemState 容器派生；后续生成/评估统计另设计 | 生成数、到达数、完成数与纳入统计数不能合并 |
| beforeThroughput、afterThroughput、count、jobNotDone | Engine 运行控制及后续 evaluation | 0.1 用显式运行状态/原因；Java 各计数的精确重置在后续核对 |

numJobsReleased 当前在成功安排未来工作流时递增，不保证对应已经到达的数量。SEED_ROTATION 是常量/配置约定，不是每个资源需要维护的动态字段。

## 8. Execution（Java Process）

位置：`model/execution.py`。表示一次确定开工时间的执行计划/记录。创建时已知完成事件时间，不等于此时任务已经完成。

| 字段 | Python 类型 | Java 对应 | 建立方式 | 运行后是否修改 |
| --- | --- | --- | --- | --- |
| option | TaskOption | taskOption: TaskOption | 选中的选项 | 否 |
| start_time | float | startTime: double | 确定开工时刻 | 否 |
| compute_finish_time | float | Python 新增 | start_time+option.processing_time | 否 |
| finish_time | float | finishTime: double | compute_finish_time+option.download_time | 否 |

派生属性：task=option.task，resource=option.resource，duration=finish_time-start_time。原 Process.server 可以通过 option.resource 取得，不再保存重复资源引用。

只有 ProcessFinishEvent 真正触发才标记 Task.completed，并把同一 Execution 加入 Workflow.completed_executions。当前选择在确定开始安排被接受时建立 Execution，登记到 SystemState.executions_by_task 并供 pending_start 与开始事件引用；未被接受的临时试算不登记。Java 在 TaskVisitEvent 的忙闲判断前就建立临时 Process，这是已记录的结构差异。操作内部先后与签名仍待完整事件表/接口展开。

## 9. 日志与运行状态的区别

trace 需要按任务键记录 dispatch_time、arrival_time、start_time、compute_finish_time、finish_time，并保存各次评分和事件快照。它是调试记录，不是另一套供调度读取的独立权威状态。

事件队列归 Engine.event_queue，日志归 Engine.trace 持有的 TraceRecorder；SystemState 只管理本轮模型与全局集合/索引。日志立即复制评分与状态数值，执行计划时间不等于实际开始/完成动作。完整维护职责、初值、重跑与不变量见 07。

## 10. SystemState 字段补充

位置：simulation/state.py。以下固定了字段角色及当前建议类型；容器封装和接口签名尚未冻结。运行构建过程建立全部索引，固定重跑全部重建。

| 字段或属性 | Python 建议类型 | 初始值/来源 | 当前用途 |
| --- | --- | --- | --- |
| clock_time | float | 0.0 | Engine 在触发事件前推进的唯一时钟 |
| mobile_devices / servers | list[MobileDevice] / list[Server] | 按输入和约定顺序建立 | 资源注册引用，保持遍历语义 |
| resources_by_id | dict[str, Resource] | 资源展示 ID 索引 | 全局唯一 ID 定位，同资源只建一个对象 |
| workflows_by_id | dict[int, Workflow] | 全部固定输入 | 内部完整索引，不直接交给规则 |
| tasks_by_key | dict[tuple[int, str], Task] | 全部任务 | 用工作流与任务组合键定位同一 Task |
| pending_arrivals | dict[int, Workflow] | 全部工作流，保留输入顺序 | 尚未处理到达事件；包括 t=0 待到达工作流 |
| active_workflows | dict[int, Workflow] | 空 | 已到达、未完成登记；到达加入、登记移出 |
| completed_workflows | dict[int, Workflow] | 空 | 按实际登记顺序保存完成工作流引用 |
| executions_by_task | dict[tuple[int, str], Execution] | 空 | 接受开始安排时登记，包含尚未开始与尚未完成的执行安排 |
| 已到达/完成数量、最终 makespan | 派生属性或 metrics 结果 | 由容器/模型计算 | 不独立保存可变同义计数；最终指标只在正常完成后确认 |

当前工作流由 pending、active、completed 三个互斥集合覆盖；历史已到达成员范围由 active 与 completed 派生。规则的受限只读状态不暴露未来集合、数量或完整内部索引。

## 11. Engine 与重跑边界

Engine 持有 SystemState、EventQueue、TraceRecorder，另保存 processed_event_count、run_status、stop_reason。初始化完成后分别为 0、READY、None；状态值的实现类型留给接口设计。事件构造只保存参数，模型构造不隐式生成未来工作流或修改共享 sampler。

固定实例重跑从同一 InstanceSpec 新建全部运行对象，重新连接拓扑、选项、索引和事件；任务标记、所有选项时间/评分、资源队列/缓存/预约、完成记录、时钟、计数和日志均回到初态。seed 配置与 RNG 内部状态后续归运行/评估配置及实例生成组件，固定重跑不依赖重设 seed。
