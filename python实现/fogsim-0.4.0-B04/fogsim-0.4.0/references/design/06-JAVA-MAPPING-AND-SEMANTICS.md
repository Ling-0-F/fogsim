# Java 对照路径、已核对语义与证据边界

文档版本：1.1.0；更新日期：2026-10-22（America/Los_Angeles）。本文件记录源码静态检查结论，不宣称 Java 已运行、源码整体正确或 Python 已复现。

返回 [总览](00-START-HERE.md)；待办见 [当前进度](05-PROGRESS-AND-NEXT.md)；状态归属设计见 [07](07-STATE-OWNERSHIP.md)。

## 1. 原始材料与指纹

原始材料是当前对话上传的三个文件。SHA-256 用于核对以后是否仍然使用同一份输入：

| 文件 | SHA-256 |
| --- | --- |
| Fog-Computing-Java-to-Python-Study-Plan-2026-10-08.md | `221353e11d7f8493d3afd9b2aa02537f0be4f4073193b45cbe161ea839589e0a` |
| Fog-Computing-multiDeviceDebug.zip | `17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a` |
| Xu 等 - 2023 - Genetic Programming for Dynamic Workflow Scheduling in Fog Computing.zh-CN.dual.pdf | `0fe716a44ca8d63013406d641e0b7dea652dc17f23614554f86c30b9937a9305` |

来源和对话中的临时工作路径不作为新对话的可用性保证。本组文档没有打包复制原压缩包或论文。

## 2. 路径映射

以下 Java 路径相对于解压后的 `Fog-Computing-multiDeviceDebug/`；Python 路径相对于拟建 `src/fogsim/`。

| Java 路径 | Python 计划位置 | 对照内容 |
| --- | --- | --- |
| src/mengxu/taskscheduling/Job.java | model/workflow.py | 归属、到达、任务与完成记录 |
| src/mengxu/taskscheduling/Task.java | model/task.py、simulation/readiness.py | 状态、依赖、选择入口 |
| src/mengxu/taskscheduling/TaskOption.java | model/task.py、rules/selection.py | 候选参数、时间、评分和平分 |
| src/mengxu/taskscheduling/Server.java | model/resource.py | 资源参数、队列、缓存和重置 |
| src/mengxu/taskscheduling/MobileDevice.java | model/resource.py、instances、simulation、evaluation | 拆分本地处理、生成、规则和统计职责 |
| src/mengxu/taskscheduling/Process.java | model/execution.py | 一次执行的时间记录 |
| src/mengxu/simulation/state/SystemState.java | simulation/state.py | 全局时钟、生命周期集合、索引与登记；归属已按 07 设计 |
| src/mengxu/simulation/DynamicSimulation.java | simulation/engine.py、metrics.py | 主循环、收集事件、重跑、指标 |
| src/mengxu/simulation/event/AbstractEvent.java | simulation/events.py、event_queue.py | 事件接口和比较 |
| src/mengxu/simulation/event/JobArrivalEvent.java | simulation/events.py | 工作流到达与下一次生成 |
| src/mengxu/simulation/event/TaskVisitEvent.java | simulation/events.py | 上传后到达和排队 |
| src/mengxu/simulation/event/ProcessStartEvent.java | simulation/events.py | 占用资源与安排完成 |
| src/mengxu/simulation/event/ProcessFinishEvent.java | simulation/events.py | 完成、选队列项、释放后继和登记 |
| src/mengxu/simulation/RoutingDecisionSituation.java | rules/contexts.py | 路由候选与状态 |
| src/mengxu/simulation/SequencingDecisionSituation.java | rules/contexts.py | 队列、资源与状态 |
| src/mengxu/rule/AbstractRule.java | rules/base.py、selection.py | 评分、遍历和选择 |
| src/mengxu/algorithm/FCFS.java | rules/baselines/fcfs.py | FCFS 两类评分 |
| src/mengxu/taskscheduling/WorkflowParser.java | instances/dax_parser.py | 从 DAX 读取任务及父子依赖 |
| src/mengxu/taskscheduling/dag/DAGTypePath.java | instances/dax_parser.py、generator.py | 生效模板路径 |
| src/mengxu/util/random/ExponentialSampler.java 等 | instances/samplers.py | 分布参数与端点 |
| src/mengxu/gp/terminal/JobShopAttribute.java | features | 特征的实际计算 |
| src/mengxu/rule/evolved/GPRule.java、util/lisp | rules/gp_rule.py、gp/expression.py | 表达式规则和解析 |
| src/mengxu/taskscheduling/SchedulingSet.java | evaluation/scheduling_set.py | 实例重复和 seed 轮换 |
| src/mengxu/ruleevaluation、ruleoptimisation | evaluation | 规则对、个体和适应度连接 |
| src/mengxu/algorithm/singletreegp、multipletreegp | gp、evaluation、experiments | 单/双树演化与配置 |
| src/mengxu/ruleanalysis | analysis、experiments | 测试、结果读取和规则分析 |

## 3. 已核对的核心行为

### 3.1 规则评分与平分

FCFS 路由返回资源 readyTime 的原值，Python 名称为 available_time。FCFS 排序返回所属工作流 releaseTime，而不是任务进入等待队列的时刻。

AbstractRule 从第一个候选开始依次比较；TaskOption.priorTo 按以下顺序决定：

1. priority 越小越优先。
2. 工作流 releaseTime 越小越优先。
3. 所属移动设备的数值 ID 越小越优先。
4. 工作流数值 ID 越小越优先。
5. 仍相同时不替换当前候选，保留遍历顺序的影响。

不要额外添加任务 ID、服务器 ID 作为平分键，也不要用展示字符串的字典序替代数值 ID。

### 3.2 上传、计算、下载

Process 构造时计算 finishTime=startTime+procTime+downloadDelay。ProcessStartEvent 把资源 readyTime 设为该 finishTime，并创建完成事件。因此下载期间资源仍被占用。

前驱在完成事件中被标记 complete，后继才能路由；后继到达时间为当前时间＋它的 uploadDelay。注释中存在其他通信想法，但当前生效路径即使后继仍在同一远程服务器，也没有自动省掉下载和上传。

### 3.3 TaskOption 的时间与派发标记

JobArrivalEvent 给入口任务的全部候选设置 releaseTime；TaskVisitEvent.trigger 给选中选项设置到达时间。Task 中当前后继路由入口没有统一刷新所有选项的 readyTime。

TaskVisitEvent 的构造函数已经把任务 dispatch 设为 true，而不是等上传完成才设。这一时机有助于防止已安排上传的任务被重复派发。Python 接口可把派发动作放在明确方法中，但必须保持相应时序并记录调整。

### 3.4 队列与完成记录

资源队列保存 TaskOption。入队均累加 PT 及 (PT+UT+DT)。Server 出队后为空时直接将两个缓存归零，仍非空则相减；MobileDevice 出队始终相减，没有空队归零分支。Server 空队读取返回零，MobileDevice 直接返回缓存。GP WIQ/TTIQ 按实际定义与资源差异核对；Python 基线保留这项差异，浮点残差及评分影响待运行验证。此处修正了 1.0.0 的统一归零概括。

Job 保存完成事件列表，NTR 使用任务总数减完成记录数。追加方法没有去重，超量时输出错误；ProcessFinishEvent 的 DAG 分支检查 isDone 与登记标记，远程 LINKED 分支没有同样保护。Python 使用完成 Execution 列表，只在真正完成时追加；任务标记、资源计数与完成记录同步，并显式保护任务重复完成和工作流重复登记。

### 3.5 同时刻事件

每种事件有自己的 compareTo。部分比较返回 0，Java PriorityQueue 不保证稳定平分顺序，具体实现还有需要专项检查的细节。不能直接以“时间＋递增编号”替代并宣称轨迹严格一致。

事件处理序号可以作为日志字段，但是否参加排序是另一个问题。完整比较表和堆平分处理仍未确定；不应在新对话中假定已经解决。


### 3.6 待开始检查与临时 Process

源码事实：MobileDevice.canAddToQueue(Process) 使用 if 从 simulation.getEventQueue() 迭代器取第一个元素检查，不是遍历所有全局事件，也没有检查全部设备暂存事件。TaskVisitEvent/ProcessStartEvent 的 compareTo 中有同刻开始事件优先于到达事件的分支。

TaskVisitEvent 在忙闲判断前构造临时 Process；因此存在 Process 对象不意味着已经接受开始安排。Python 选择在接受确定安排时建立正式 Execution 并登记，等待队列继续保存 TaskOption。

Python 新增 Resource.pending_start 表达已安排但开始事件未触发的预约；所有开始安排路径统一检查，触发时核对并清除。available_time 仍在开始事件触发时更新。此显式保护是设计调整，与 Java 组合机制的等价性待具体实例运行验证，不能把 canAddToQueue 当作已证明充分的预约检查。

### 3.7 全局集合与构造副作用

SystemState.addJobToSystem 在接纳未来工作流时就加入 jobsInSystem 并增加 allNumJobsReleased；该集合并不等同于“已到达”。Python 选用 pending_arrivals、active_workflows、completed_workflows 三个生命周期集合；规则只获得已到达范围。

DynamicSimulation 构造会建立 RNG、采样设备/服务器参数并调用 setup。MobileDevice 构造调用 setInterReleaseTimeSamplerMean，将传入 sampler 的 mean 设为 100，还建立 DigraphGeneratorMX。Python 把模型构造、运行初始化和随机生成分开，固定输入构造不隐式采样或修改共享 sampler。

### 3.8 重跑与重设的准确边界

DynamicSimulation.rerun 调用 resetStateforRerun 后 run；resetStateforRerun 清事件、调用 SystemState.resetforRerun，再 setup，没有 reseed。reset(seed) 先 reseed 再 resetState；rotateSeed 增加 10000 后重设并清运行状态。

SystemState 的两个重置方法均清时钟和工作流集合，重置资源/设备；清 firstArriveJobRecordedTime 的语句被注释。reset 不重新构造资源参数，而首次构造调用了资源采样。因此“同 seed 得到同实例”的注释尚需完整调用链和运行检查，不能直接作为证据。

Python 当前固定重跑从同一 InstanceSpec 重建全部运行对象；后续同 seed 重新生成、继续随机流和 seed 轮换分别设计。具体归属见 07 第 8 节。

### 3.9 后继查询中的重复评分

ProcessFinishEvent 的非空 DAG 后继路径先在条件中调用 getNextDag，随后再调用以取得列表；TaskOption.getNextDag 又会进行就绪查询并调用 chooseTaskOption。该调用链包含路由评分和 priority 覆盖，不能一概视为只读查询。完整事件表需要记录实际决策调用，是否调整重复调用必须记录其对逐调用日志和行为的影响。

## 4. 实例生成已核对事项

- setup 为每个移动设备安排首次工作流。DAG 工作流到达事件中调用该设备的 generateWorkflowJob 安排后续工作流，不等前一工作流全部完成。
- generateWorkflowJob 通过 workflowSampler 选模板，再调用 getDAGTypePathForSubmit，读取根目录 `./dax/...`。
- WorkflowParser 读取 job 节点及 child/parent 依赖；主要模拟参数随后随机赋值。不能把 XML 原 runtime 当作实际 PT。
- 另有 generateJob 调用随机 DAG 生成器；当前主要 DAG 工作流路径使用 generateWorkflowJob。
- 到达时刻为当前时钟加 interReleaseTimeSampler 的采样值；ExponentialSampler 调用 nextExponential(mean)。当前 MobileDevice.setInterReleaseTimeSamplerMean 中 mean=100，这属于本包设置，正式论文场景仍需核对。
- 工作流 ID 使用 SystemState 全局计数器，设备归属为调用生成方法的 this。生成顺序与实际到达顺序可以不同。
- 本地 PT=workload/device_rate，UT=DT=0；遍历全部服务器生成其选项。
- 远程 PT=workload/server_rate；UT=(data+total_input_data)/upload_bandwidth；DT=(data+total_output_data)/download_bandwidth。
- 设备/服务器构建时使用共享随机数生成器等对象，严格复现需核对共享关系和调用顺序。相同 seed 不是相同输入的证明。

## 5. Python 设计调整登记

| 调整 | 原因与约束 |
| --- | --- |
| Job 改名 Workflow、Process 改名 Execution | 表意清楚；保留对象行为映射 |
| 公共 Resource 和统一 option.resource | 统一本地、边缘、云引用；通过类型判断本地，不能只依据 Java server 是否为 null |
| 展示 ID 使用字符串，另保留数值 ID | 支持 M0/E0/C0；规则比较仍保留 Java 数值语义 |
| 未完成时间/未提供原始参数使用 None | 避免把未知当成 0；使用前验证 |
| 完成事件列表改成完成执行记录 | 减少模型与事件耦合；追加时机和计数必须一致 |
| 增加 compute_finish_time | 调试区分计算结束与含下载的完成；不要求新增计算结束事件 |
| 生成、规则、事件和评估职责从 MobileDevice 拆出 | 按 07 明确归属；随机流共享、事件归并和评估边界仍须核对 |
| 新增 Resource.pending_start | 显式预约，不提前改变 MRT/FCFS 读取的 available_time；运行等价性待验证 |
| 显式工作流生命周期集合和受限规则情境 | 区分尚未到达、活动和完成，隔离固定输入中的未来信息 |
| 新增 SystemState.executions_by_task | 登记已接受的确定执行安排；与完成历史引用同一 Execution，不复制字段 |
| 派发副作用改为明确操作，事件构造仅存参数 | 保留提交上传时已派发的时序，避免构造事件意外改模型 |
| 完成操作增加一致性和重复保护 | 不依赖 Java 各路径不一致的检查；任务重复完成不得再追加/计数 |
| 固定实例按 InstanceSpec 重建 | 不照搬 Java 随机 rerun，不复用旧轮事件和对象引用 |

以上是已讨论的设计基线，不是运行对照通过的证明。没有对原源码的疑似问题进行无记录修正。

## 6. 固定小实例与 Java 动态入口的差异

固定 0.1 已采用允许 release_time=0 和无 warm-up、全部有限输入完成后结束的约定。当前 Java SystemState.addJobToSystem 却要求新生成工作流 releaseTime>clockTime，并含特定记录窗口逻辑。

因此 Java 对照入口需要明确支持固定实例注入、计数和统计范围；不能直接把 t=0 的实例送入随机生成路径，遇到拒绝后再悄悄把时间改成正数。固定输入适配器尚未实现，属于 0.2 对照准备工作。

warm-up、firstArriveJobRecordedTime、numJobsReleased、throughput 和停止条件应联合核对，不能解释成简单删去前若干个完成工作流。0.1 暂不复制这套训练统计入口。

## 7. 后续 GP/实验提醒

- 当前双树顺序：trees[0] 排序，trees[1] 路由；单树为路由，固定 FCFS 排序。
- 当前多树配置种群为 100，原阅读计划指出论文表 VI 为 1000；正式复现再查论文和全部生效参数。
- 原计划阶段 D 的相对特征集合为 NIQ、WIQ、MRT、TTIQ、UT、DT、PT、TWT、TIS、NTR。特征值依赖上述字段的实际语义。
- 当前配置函数集合为加、减、乘、受保护除法、max、min；存在 If.java 不代表已启用。
- GP 子代复制、节点选择、深度定义、整树交换、实例轮换和异常适应度处理尚未实现或完整验证。

## 8. 证据限制

本组文档进行了附件读取、Java 文本核对、示例 JSON 及链接检查、手算时间检查；没有运行 Java 调度程序，没有实现或运行 Python 模拟器，也没有开始 GP 实验。未来每项运行结果应保存对应输入、规则、版本与轨迹，再更新状态。

## 9. 1.1.0 变更范围

本次更新完成状态归属第一版设计的文档衔接，补充 3.6—3.9 的静态事实，修正队列清理概括，并登记 Python 预约、全局索引、构造及重跑调整。07 是唯一完整归属表，04 维护字段，05 维护进度。

所有运行验收仍未开始。完整事件读写表、最终接口、同时刻完整比较和平分策略属于后续设计；预约等价性、缓存数值影响、Java 固定输入入口及随机重置行为需要相应对照证据。
