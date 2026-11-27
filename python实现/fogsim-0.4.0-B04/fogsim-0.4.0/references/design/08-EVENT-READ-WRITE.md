# 四类事件读写表：Java 源码事实与 Python 设计基线

- 项目：雾计算论文阅读／Xu 等（2023）Java→Python 复现。
- 本文档版本：1.0.0；更新日期：2026-10-22（America/Los_Angeles）。
- 文档位置：新增第 08 号专题，承接 00—07 文档集 1.1.0；本文可以单独阅读。
- 当前状态：**事件读写表第一版设计已完成。** 用户已确认既有状态归属基线，并采用“就绪查询与路由拆分、无就绪任务返回空列表”的新增建议。
- 完成边界：已明确四事件的触发时间、读取、修改、规则调用、新事件、构造副作用和主要操作先后；最终接口、同时刻比较策略、Python 实现及 Java/Python 运行验证尚未完成。
- 证据等级：Java 结论来自当前 ZIP 的源码静态核对；Python 结论属于本轮设计基线。没有运行验收通过记录。

## 1. 与既有文档的关系及确认事项

00—07 中，00 维护总览，01 维护版本与验收，02 维护文件职责，03 维护输入输出，04 维护字段，05 维护进度，06 维护源码语义，07 维护状态归属。本文记录事件如何使用这些状态，不再复制完整状态归属表。

本文是上述 1.1.0 快照之后的进度增量。此前 00、05、07 中“事件表尚未完成”的表述属于较早状态；本次已推进到“事件读写表第一版设计完成”。本轮按要求仅交付这一份新增 Markdown，未重新发布或声称已经同步更新整套旧文档。

| 事项 | 本轮结论 |
| --- | --- |
| 07 中已经纳入基线的状态归属与 Python 调整 | 用户已确认；继续采用 |
| 就绪查询和路由选择拆分 | 已采用；查询只读模型，评分选择才覆盖 priority |
| 无就绪任务时的查询返回值 | 已采用空列表；不把空列表解释为工作流完成 |
| 减少 Java 重复路由评分 | 本轮不包含这项优化；首次源码对照以保留原评分次数和顺序为基线 |
| 最终函数名、参数、返回类型封装、对象比较实现 | 后续接口设计；本文职责名称不是已冻结的代码签名 |
| 同时刻完整比较、堆平分和 Java 设备事件归并兼容性 | 后续专项设计与验证；本文不自行加入最终事件排序键 |

## 2. 阅读约定与公共事件外层

### 2.1 名称与时间

| Java 名称 | Python 名称或含义 |
| --- | --- |
| Job / Process | Workflow / Execution |
| Task.dispatch / Task.complete | Task.dispatched / Task.completed |
| 资源 readyTime | Resource.available_time |
| TaskOption.readyTime | TaskOption.ready_time |
| Job.processFinishEvents | Workflow.completed_executions，Python 改存同一 Execution 的引用 |
| t | 当前事件时间，正常触发时等于系统时钟 |
| UT / PT / DT | 上传、计算、下载时长，单位秒 |

下载计入资源占用，finish_time=start_time+PT+DT。compute_finish_time=start_time+PT 是 Python 调试字段，不要求新增计算结束事件。任务上传时尚未占用处理器；接受具体开始安排后才建立待开始预约。

### 2.2 主循环负责的读写

源码事实：DynamicSimulation.run 先调用 mobiledeviceHaveEvent，把各设备暂存队列中的事件逐项收集到全局队列；弹出下一事件后设置 clockTime，再调用 event.trigger(event.getMobileDevice())。事件中新建的事件通常先存入设备暂存队列，并非立即触发。

Python 基线：Engine 取出事件并推进 SystemState.clock_time，驱动事件处理；Engine 持有 EventQueue、TraceRecorder 和运行控制。四事件自身不各维护一份时钟。事件处理序号只记录实际处理顺序，不自动参与堆平分。

Java 主循环外围还有 beforeThroughput、afterThroughput、count 和异常保护的更新，特定条件下写极大 clockTime 并清全局队列；这些不是四事件 trigger 内部的状态修改。Python 当前固定输入按 07 使用明确正常/失败状态，不把异常惩罚值混入模型时钟。

### 2.3 构造、安排与触发分开

事件对象已经存在、事件已经入队、事件已经触发，是三个不同阶段。下文分别记录构造副作用和触发读写。“修改”包含辅助方法、评分选择以及构造新事件造成的间接修改。

## 3. Java 源码事实：事件构造表

时间列按当前正常调用路径填写。源码另有显式传入 time 的重载，不应仅凭默认构造推断所有调用都自动满足时间一致性。

| 事件 | 正常路径事件时间 | 构造保存的信息 | 构造时修改模型状态 |
| --- | --- | --- | --- |
| JobArrivalEvent | job.releaseTime | Job、事件所属设备、事件时间 | 无任务或资源状态副作用 |
| TaskVisitEvent | 入口为 job.releaseTime+UT；后续任务为完成事件 t+UT | 选中 TaskOption、事件所属设备、时间 | 立即设置 task.dispatch=true |
| ProcessStartEvent | process.startTime | Process、事件所属设备、时间 | 不修改资源 readyTime |
| ProcessFinishEvent | process.finishTime | Process、事件所属设备、时间 | 不设置任务完成，不追加完成记录 |

TaskVisitEvent 的不显式传时间重载直接取 option.readyTime，不会自动加 UT。Python 派发操作应明确计算上传后到达时间，不能照名称猜测重载的功能。

Python 已确认的结构调整：事件构造只保存参数；Task.dispatched 在明确的派发提交操作中设置，时机仍是安排上传完成事件时，而不是等上传结束才设。以下第 4—6 节仍如实记录 Java 构造副作用，不能将 Python 调整倒写成 Java 源码行为。

## 4. Java 源码事实：DAG 事件读写总表

当前 Python 链式实例也按 DAG 表达。Java LINKED 分支的独立差异在第 6.4 节列出。

| 事件及触发含义 | 主要读取 | 直接及间接修改 | 规则调用 | 新事件及时间 |
| --- | --- | --- | --- | --- |
| JobArrivalEvent：工作流到达 | Job 类型、任务列表、前驱列表、入口选项、releaseTime；路由规则所需状态 | 按入口顺序：设置该入口全部选项 readyTime=releaseTime；评分覆盖 priority；构造 TaskVisitEvent 时把该任务 dispatch 置真；之后调用生成器 | 每个入口任务一次路由选择 | 每入口一条 TaskVisitEvent(releaseTime+UT)；生成器接纳下一工作流后再安排其 JobArrivalEvent |
| TaskVisitEvent：上传完成并到达资源 | 选中选项、目标资源、PT/DT、资源 readyTime；必要时读取全局堆待开始检查信息 | 先令选中选项 readyTime=t；构造临时 Process；资源忙或检查不通过则入队并增加两个缓存，否则安排开始 | 不调用路由或排序 | 直接开始分支产生 ProcessStartEvent(t)；排队分支无新事件 |
| ProcessStartEvent：执行开始 | Process 的目标资源和 finishTime | 资源 readyTime=process.finishTime；不标记任务完成 | 不调用规则 | 一条 ProcessFinishEvent(process.finishTime) |
| ProcessFinishEvent：含下载的执行完成 | Process、任务、Job；资源队列和 readyTime；工作流任务完成/派发标记及前驱；规则所需状态；工作流完成统计条件 | 追加完成事件、任务 complete=true、执行资源完成任务数加一；再排序出队并更新缓存、安排开始；随后查询并路由当前工作流任务，或检查完成登记 | 队列非空则排序；有可派发任务时路由，源码非空分支重复两轮 | 至多一条队列后续开始事件；若干条任务到达事件；登记工作流本身不产生新完成事件 |

DAG 入口识别方法 getFirstArriveReadyTask 只依据前驱列表为空；不是根据资源是否空闲筛入口，也没有 Task.getNextDag 那样的未完成/未派发筛选。正常路径假定到达事件只处理一次。

规则读取随具体规则变化。当前 0.1 的 FCFS 路由读资源 readyTime，FCFS 排序读任务所属 Job.releaseTime。AbstractRule 在遍历候选时覆盖 TaskOption.priority；TaskOption.priorTo 再处理分数及平分。GP 启用后还会读取当前时钟、队列/缓存、选项时间、工作流完成记录等特征，不能把全部规则调用都描述成无状态修改的查询。

## 5. Java 源码事实：完成事件的操作顺序

### 5.1 DAG 路径

| 顺序 | 操作 | 读取和修改的关键点 |
| --- | --- | --- |
| 1 | 记录本任务完成 | 向 Job 完成事件列表追加当前事件；task.complete=true；执行资源 numTasksCompleted 加一 |
| 2 | 非空资源等待队列调用排序 | 评分时选中项仍在队列中，priority 被覆盖；即使只有一项也调用排序 |
| 3 | 选中项出队、更新缓存、安排开始 | processStartTime=max(resource.readyTime,t)；创建 Process 和开始事件；此时开始事件尚未触发，不更新资源 readyTime |
| 4 | 调用 option.getNextDag 查询并路由 | 先扫描整个当前工作流，判断未完成、未派发、全部前驱完成；包装方法随后为这些任务选择资源 |
| 5A：第 4 步非空 | 再次调用同一包装方法，然后提交任务到达事件 | 重新查询并重新路由，使用第二轮结果；按该结果逐项构造 TaskVisitEvent(t+UT)，构造时标记派发 |
| 5B：第 4 步为空 | 检查工作流全部完成与登记标记 | job.isDone 且未登记才设 completionTime=process.finishTime、调用 completeJob，随后登记标记置真 |

5A 与 5B 是互斥分支。排序出队先于后续路由，因此后续路由看到的是已缩短的队列和已更新缓存，而新安排的开始事件尚未修改资源时间。Python 不能为了方便把安排开始直接替换为内联执行开始事件。

### 5.2 查询为空不等于工作流完成

Task.getNextDag 遍历的是整个 Job.taskList，不只查看刚完成任务的直接子任务。它跳过已完成或已派发任务，检查剩余任务的全部前驱；当前没有可派发任务就返回 null。

例如 B、C 都已派发，B 完成而 C 仍在执行，D 等待 B/C：此时没有可派发任务，但工作流未完成。Java 随后还要调用 job.isDone；Python 采用空列表后也必须保留独立的全部完成判断。

### 5.3 重复评分的实际顺序

Task.getNextDag 本身查询就绪任务；TaskOption.getNextDag 包装了查询和路由。ProcessFinishEvent 在判断 null 时已经调用了一次包装方法，非空后又调用一次。因此，对于就绪列表 A、B，实际路由调用顺序是 A、B、A、B，最终使用第二轮选项；不是 A、A、B、B。任务到达事件在两轮选择结束后才逐项提交。

TaskOption.getNextDag 内部还重复调用 Task.getNextDag，造成更多纯查询。纯扫描次数和修改 priority 的评分次数必须区分。首次 Python 对照保留评分次数、整批顺序和结果提交阶段，不要求保留没有副作用的重复扫描。

### 5.4 共享服务器与设备归属

服务器队列可能包含其他设备的任务。Java 服务器完成分支使用当前完成事件所属设备的排序规则选下一任务；新开始事件被加入当前设备的暂存队列，但事件携带被选任务的所属设备，主循环按该携带信息触发。

Python 当前每轮共用一对规则，仍需按 Task.workflow.owner_device 识别任务归属，以 option.resource 识别执行资源。事件暂存位置、工作流发布设备、实际执行资源不是同一概念。以后按设备配置规则时，要另行核对上述 Java 规则来源。

## 6. Java 源码事实：辅助写入与边界

### 6.1 下一工作流生成

DAG 到达事件调用 generateWorkflowJob。该方法读取时钟、DAX、sampler/RNG、资源能力、本地计算资格和全局生成计数，推进随机流并创建未来工作流及选项。接纳成功后加入 jobsInSystem、增加全局和设备生成计数，按条件更新 firstArriveJobRecordedTime，安排下一到达事件。

jobsInSystem 因此包含未来工作流，不能等同于“已经到达”。SystemState.addJobToSystem 当前要求 releaseTime>clockTime；固定输入 t=0 对照需要单独适配，不能静默改变输入时间。

### 6.2 队列操作

入队累加 PT 及 (PT+UT+DT)。Server 出队后为空时两个缓存归零，非空则相减；MobileDevice 出队始终相减，无空队归零分支。Server 空队读取返回零，MobileDevice 直接返回缓存。

等待队列不含已出队的预约或执行项目。缓存包含已完成上传的 UT 是源码特征定义，不表示出队后再上传。Python 按资源类型保留维护差异和浮点运算顺序；数值检查用容差，但不以检查为由静默统一钳零或重新求和。

TaskVisitEvent 调用的 canAddToQueue 实际实现位于 MobileDevice：它只检查全局事件堆迭代器的第一个元素，使用 if 而非遍历，也没有遍历全部设备暂存事件。不能据此宣称 Java 已有充分预约保护。

### 6.3 工作流完成登记与统计

Job.addProcessFinishEvent 只追加，超量时打印错误，没有去重。completeJob 检查全部任务完成后增加设备工作流完成计数；满足 allNumJobsReleased>warmupJobs、job.id>=0、releaseTime<=firstArriveJobRecordedTime 才增加 throughput、重置设备 count 并加入 jobsCompleted。未完成时增加 jobNotDone；方法末尾仍移出 jobsInSystem。

调用者随后设置 hasAddToCompletedList，即使统计筛选没有把 Job 加入 jobsCompleted。因此 Java 登记标记与统计完成集合不能普遍视为等价。当前有效完成路径中清理 Job 任务列表的调用被注释，不把清空拓扑当作正常完成步骤。

Python 0.1 使用全部固定输入参与统计的已定约定；completion_registered 与 completed_workflows 对应的是本轮正常完成登记，而不是原 Java 训练统计筛选的原样表达。

### 6.4 LINKED 独立差异

| 位置 | Java LINKED 分支事实 |
| --- | --- |
| 到达 | 直接取 taskList 第一项；之后调用 generateJob，而不是 DAG 的 generateWorkflowJob |
| 后继 | getNext 从直接子任务中找一个前驱全部完成的任务，缺少 DAG 查询同样的未完成/未派发筛选 |
| 本地完成 | 检查 job.isDone 及登记标记后登记 |
| 远程完成 | 没有同样的外层完成和重复登记保护；调用 completeJob 后设置标记 |
| generateJob | 当前构造的 Job 类型实际是 DAG，且不根据 addJobToSystem 返回值决定是否增加设备计数和安排事件 |

Python 当前链式工作流继续按 DAG 表达，不为这些旧分支再引入一套独立行为。

## 7. Python 已确定的职责拆分

### 7.1 纯就绪查询

查询只针对当前已经到达、处于 active_workflows 的工作流。按约定任务顺序筛选未派发、未完成且全部前驱完成的任务，返回同一 Task 对象的列表；无结果时返回空列表。

查询本身不调用路由规则，不修改 priority、ready_time、任务标记、资源队列、预约或完成记录，不另存持久 ready 布尔状态。该列表是本次处理中的临时计算结果，不是一套可独立修改的全局就绪状态。

### 7.2 路由选择与派发提交

路由选择接收就绪任务及可见决策情境，对合法 TaskOption 评分、覆盖 priority，并按既有分数方向和平分基线选出同一选项对象。决策日志立即复制本次分数。

派发提交另行负责检查防重复派发、设置 Task.dispatched，并安排 TaskVisitEvent。派发不占用处理器，也不建立 pending_start；只有接受确定开始安排才预约资源。

### 7.3 本轮保留的首次对照调用约定

职责拆分本身已采用；把两次路由减少为一次未纳入本次优化。完成事件查询得到非空就绪列表后，首次对照按整批顺序显式路由两轮，使用第二轮选项列表，之后再逐项提交任务到达事件。

这样，重复路由从查询内部副作用变成事件流程中的显式调用。纯查询可只做一次；当前规则按基线只读取模型并由选择组件覆盖评分，不在两轮间修改任务派发资格、资源占用或队列成员。

如果以后将两轮合并为一轮，应单独记录变更，检查特征/分数、选择、逐调用日志及规则副作用；不能仅凭“看起来重复”就称为已证明等价。

## 8. Python 事件读写表：当前设计基线

以下使用职责名称描述，不是代码或已冻结接口。所有提交在稳定观察点保持 07 的一致性；操作失败不得继续使用半更新状态。

### 8.1 JobArrivalEvent／工作流到达

| 项目 | 确定的处理规则 |
| --- | --- |
| 触发与时间 | 初始化为每个固定工作流安排一条事件，时间为 release_time，允许 t=0 |
| 前置检查 | 本轮工作流仍在 pending_arrivals，事件尚未重复处理；对象及设备归属一致 |
| 读取 | 工作流 release_time、任务/前驱、入口选项；规则可见的已到达信息及当前资源状态 |
| 修改与顺序 | 先从 pending_arrivals 移到 active_workflows；按任务顺序处理未派发未完成的无前驱入口：设置该入口全部选项 ready_time=release_time，路由评分覆盖 priority，提交派发时 dispatched=True |
| 规则调用 | 每入口一次路由选择；本事件不调用排序 |
| 新事件 | 每入口一条 TaskVisitEvent，时间 release_time+选中选项.upload_time |
| Java 借鉴与调整 | 保留入口时间、评分/派发顺序和上传延迟；生命周期集合及显式派发属于 Python 基线；固定输入不在这里随机生成下一工作流 |

到达事件中新建任务到达事件，只安排未来动作；不提前将任务加入资源等待队列，不提前建立 Execution 或资源预约。

### 8.2 TaskVisitEvent／上传完成并到达资源

| 项目 | 确定的处理规则 |
| --- | --- |
| 触发与时间 | 派发时按派发时间+upload_time 安排；任务到达选定资源时处理 |
| 前置检查 | 工作流已经到达；任务已派发未完成；选项、目标资源与本轮对象一致；检查重复到达、重复入队或重复执行安排 |
| 读取 | TaskOption、目标 Resource、时钟、available_time、pending_start；必要的一致性成员关系 |
| 先行修改 | 选中选项 ready_time=t；不刷新该任务其他选项 |
| 排队分支 | 若 available_time>t 或 pending_start 非空，则通过资源入队操作加入 waiting_queue，同步增加两项缓存；不建立正式 Execution |
| 直接开始分支 | 若 available_time<=t 且没有预约，接受 start_time=t 的确定安排；建立 Execution，登记 executions_by_task，设置 resource.pending_start，提交开始事件 |
| 规则调用 | 不调用路由或排序；不因队列长度变化主动重新评分 |
| 新事件 | 直接开始分支一条 ProcessStartEvent(t)；排队分支无新事件 |
| Java 借鉴与调整 | 保留选项到达时间、直接开始/排队分支；Python 用显式预约保护，正式 Execution 在安排被接受后才创建 |

available_time 仍在开始事件触发时更新。预约只是保存同一 Execution 引用，不提前改变 FCFS 路由或 MRT 的资源时间值。

### 8.3 ProcessStartEvent／执行开始

| 项目 | 确定的处理规则 |
| --- | --- |
| 触发与时间 | 已接受执行安排的 start_time；可能与安排它的事件同刻，但仍通过 EventQueue 触发 |
| 前置检查 | Execution 已登记；resource.pending_start 正是该 Execution；任务与资源身份一致且任务未完成；开始时间与事件安排一致 |
| 读取 | Execution.option/resource/start_time/finish_time、对应预约和任务状态 |
| 修改与顺序 | 核对并清除对应 pending_start；将 available_time 设为 Execution.finish_time；安排完成事件；记录实际开始 |
| 规则调用 | 无 |
| 新事件 | 一条 ProcessFinishEvent，时间为 start_time+PT+DT |
| Java 借鉴与调整 | 保留此时才更新资源可用时间和下载占用；清除预约与日志属于 Python 基线 |

此时 Task.completed 仍为 False，Execution 不加入 Workflow.completed_executions。计算结束时间可记录为计划字段或派生字段，不据此提前标记完成。

### 8.4 ProcessFinishEvent／含下载的执行完成

| 项目 | 确定的处理规则 |
| --- | --- |
| 触发与时间 | Execution.finish_time，即计算与下载均已完成 |
| 前置检查 | Execution 为本轮已接受安排；任务未被重复完成；资源/工作流引用一致 |
| 读取 | Execution、Task/Workflow；资源队列、缓存、available_time、pending_start；任务派发/完成和前驱状态；队列及候选选项的时长、规则可见状态；工作流登记标记 |
| 修改阶段 1 | 任务完成操作同步设置 Task.completed=True，向 Workflow.completed_executions 追加同一 Execution，Resource.completed_task_count 加一；记录实际完成 |
| 修改阶段 2 | 资源等待队列非空且没有其他 pending_start 时，调用排序；评分时选中项尚在队列。接受安排时出队并同步更新缓存；确定 start_time=max(available_time,t)，建立并登记下一 Execution、设置预约、提交开始事件 |
| 修改阶段 3 | 在上述队列处理之后，纯查询当前工作流全部可派发任务。结果非空时按第 7.3 节整批两轮路由，使用第二轮结果，再按顺序提交 TaskVisitEvent(t+UT)，同时标记派发 |
| 修改阶段 4 | 查询为空时另外检查工作流是否全部完成；全部完成且尚未登记，才统一设置 completion_time、从 active 移入 completed、设置 completion_registered。仍有上传/排队/执行任务时不登记 |
| 规则调用 | 队列非空且可接受下一安排时一次排序，包括仅一项的情况；非空可派发列表按首次对照约定进行两轮路由 |
| 新事件 | 至多一条从该资源等待队列选出的 ProcessStartEvent，以及若干 TaskVisitEvent；工作流登记无独立完成事件 |
| Java 借鉴与调整 | 保留完成、排序出队、后续路由的阶段顺序；Python 增加预约和去重一致性保护，使用完成执行引用与全部输入统计约定 |

完成事件不把 available_time 改成当前时钟，不清除可能属于另一项执行的 pending_start。若开始事件已在同刻先行更新资源时间，队列下一项的开始时间仍按 max(available_time,t) 计算。

完成登记操作对已经登记的工作流不追加第二项；若标记与集合不一致则报告状态错误。重复任务完成必须报错，不能再次追加完成记录或增加计数。Workflow.tasks 与拓扑保留，便于派生检查和调试。

## 9. 统一职责与不变量

| 状态组 | 维护职责与检查 |
| --- | --- |
| 时钟与事件 | Engine 推进唯一 clock_time，EventQueue 管理排序及待处理事件；所有事件仅引用本轮对象 |
| 任务与选项 | 派发操作写 dispatched；完成操作写 completed；选项时间仅在指定到达位置写；评分选择组件覆盖 priority |
| 队列与缓存 | 资源入队/出队统一更新成员与缓存；按资源类型保留 Java 细节；已预约/执行项不留在等待队列 |
| 执行与预约 | 接受确定开始安排时创建一次 Execution 并登记；事件、预约、完成历史引用同一对象；每资源最多一个 pending_start |
| 工作流生命周期 | pending/active/completed 互斥且覆盖输入；未来工作流不可路由；全部任务完成后登记一次 |
| 日志 | TraceRecorder 记录事件、决策、分数、队列/缓存、预约与任务实际时间；快照不被后续评分覆盖；日志不参与调度 |

稳定观察点应满足：每任务至多一次派发、一个正式 Execution 和一条完成记录；completed 蕴含 dispatched；各资源完成任务数之和等于各工作流完成执行数之和，也等于已完成任务总数。

资源占用区间含计算与下载且不重叠；开始安排对应唯一预约和开始事件。空查询不能替代 is_done。浮点容差用于检查，不改变事件排序或静默改写评分输入。

首次初始化及固定重跑继续从同一 InstanceSpec 新建全部运行对象、事件、索引、队列、缓存、预约和日志；不在这里引入随机 seed 重设或轮换。

## 10. Java 借鉴、Python 调整与验证范围

| 类别 | 本文采用内容 | 当前证据 |
| --- | --- | --- |
| 借鉴 Java | 四事件生命周期、入口选项时间、上传到达、含下载完成、队列先于后续路由、原评分/平分与调用阶段 | 源码静态核对 |
| Python 职责组织 | 事件构造只存参数、显式派发、纯就绪查询、独立路由选择、资源统一操作、完成记录用 Execution | 已纳入当前设计，尚未实现 |
| Python 已定保护 | pending_start、重复派发/完成/登记检查、跨字段一致性 | 设计已定；边界行为与 Java 的差异需运行对照 |
| 固定输入模式 | 初始化预排到达、t=0、全部输入完成终止、无 warm-up | 既有采用约定；Java 固定输入适配入口待实现 |
| 查询返回与重复调用 | 查询返回 Task 列表及空列表；首次对照显式保留两轮评分 | 本轮采用职责拆分；减少评分次数未纳入优化 |
| 同时刻比较与归并 | 记录新事件可能与当前事件同刻；保留源码顺序影响的识别 | 最终 Python 比较策略尚未确定，未运行对照 |

源码的 compareTo 还包含同类平分与特殊返回分支。本文不以“时间+类型+递增编号”替代它并声称严格等价；完整比较表和堆行为留下一步专项设计。接口和比较策略可能促使有记录地修订本文，但不影响本轮第一版事件读写设计的完成状态。

## 11. 源码定位与材料身份

当前 Java ZIP：Fog-Computing-multiDeviceDebug.zip。

SHA-256：`17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a`。

下列路径相对于 ZIP 内的 Fog-Computing-multiDeviceDebug/，不依赖本次临时解压目录。

| 源码路径 | 本文核对内容 |
| --- | --- |
| src/mengxu/simulation/DynamicSimulation.java | setup、事件归并、run、时钟、统计/异常外层 |
| src/mengxu/simulation/event/AbstractEvent.java | 事件时间与所属设备、trigger 入口 |
| src/mengxu/simulation/event/JobArrivalEvent.java | 到达、入口时间、路由、后续生成、构造与比较 |
| src/mengxu/simulation/event/TaskVisitEvent.java | 构造派发副作用、到达时间、临时 Process、排队/开始 |
| src/mengxu/simulation/event/ProcessStartEvent.java | 可用时间更新及完成事件安排 |
| src/mengxu/simulation/event/ProcessFinishEvent.java | 完成顺序、排序出队、两轮后续路由、登记及 LINKED 差异 |
| src/mengxu/taskscheduling/Task.java | getNext/getNextDag、任务状态与路由入口 |
| src/mengxu/taskscheduling/TaskOption.java | 查询包装与路由、priority 及平分 |
| src/mengxu/taskscheduling/Job.java | 入口识别、完成记录追加、isDone、登记字段 |
| src/mengxu/taskscheduling/Process.java | 执行开始与含下载的完成时间 |
| src/mengxu/taskscheduling/MobileDevice.java | 生成、队列、完成统计、canAddToQueue |
| src/mengxu/taskscheduling/Server.java | 服务器队列与缓存维护 |
| src/mengxu/simulation/state/SystemState.java | 未来工作流接纳、计数、记录窗口与完成集合 |
| src/mengxu/rule/AbstractRule.java | 候选评分覆盖及路由/排序选择 |
| src/mengxu/algorithm/FCFS.java | 当前 0.1 两种评分读取 |

本对话已静态核对主事件及辅助调用；本轮保存前核对当前 ZIP 身份、主要源文件字节、文档表格与字段一致性。没有运行 Java 调度程序、Python 模拟器、固定链验收或 Java/Python 轨迹对照。既有固定 E0 链式 makespan=13 仍只是手算基准。

## 12. 当前进度与下一次续接

| 工作 | 当前状态 |
| --- | --- |
| 固定输入输出基本约定 | 已采用；最终键名/格式仍待接口确定 |
| 模型字段与状态归属 | 第一版设计已完成，作为当前基线 |
| 四事件读写表 | **第一版设计已完成；本文件为事件专题当前基线** |
| 纯查询与路由拆分、空列表返回 | 已采用 |
| 减少重复评分次数 | 未纳入本次优化；首次对照保留两轮原顺序 |
| 最终接口与对象相等/哈希等落地细节 | 下一阶段设计 |
| 同时刻完整比较、堆平分与归并兼容性 | 下一阶段专项设计与后续运行验证 |
| 固定链完整字段走查 | 待接口与比较约定后继续；没有运行证据 |
| Python 编码、Java 固定入口、测试和行为等价性验证 | 尚未开始 |

下一次先依据本文与 07 确定接口及同时刻比较策略，再走查固定链完整字段生命周期；按后续指令进入编码，逐功能实现和验证。状态归属或事件流程若因具体证据调整，应记录原因和影响，保持单一当前基线。

后续整套更新时，应同步：00 的总览和导航；02 的 readiness/selection/event 职责；04 的 priority 修改者说明；05 的事件完成状态与下一项；06 的源码调用记录和调整；07 中事件表未完成的旧进度。本轮这一份新增文档已经明确上述增量，不声称旧文件已自动改写。
