# Java 到 Python 的实际实现位置

Java 路径相对原项目 `src/mengxu/`；Python 路径相对 `src/fogsim/`。

| Java | Python | 已落实内容 |
| --- | --- | --- |
| taskscheduling/Job.java | model/workflow.py | Workflow、派生完成信息；历史改存 Execution |
| taskscheduling/Task.java | model/task.py、simulation/readiness.py | 规范任务/拓扑、只读全工作流就绪扫描 |
| taskscheduling/TaskOption.java | model/task.py、rules/selection.py | 选项、ready/priority、priorTo；未使用恒 -1 的 compareTo |
| taskscheduling/Process.java | model/execution.py | 不变执行计划及 start+PT+DT |
| taskscheduling/Server.java、MobileDevice.java | model/resource.py | 统一资源、原缓存运算、显式 pending_start |
| simulation/state/SystemState.java | simulation/state.py | 索引、pending/active/completed、任务执行登记与不变量 |
| simulation/event/*.java | simulation/events.py、engine.py | 四事件、纯构造、显式状态提交及两整轮评分 |
| simulation/DynamicSimulation.java | simulation/engine.py、event_queue.py | 逐事件归并、时钟、明确失败、全新对象重跑 |
| rule/AbstractRule.java | rules/selection.py | 逐项评分覆盖、保留首项平分 |
| algorithm/FCFS.java | rules/baselines/fcfs.py | available_time 路由与 release_time 排序 |
| simulation/*DecisionSituation.java | rules/contexts.py | 受限视图、候选 tuple、违规修改检查 |
| 无对应固定文件加载入口 | instances/spec.py、fixed.py、config.py | 本次固定实例和配置支架 |
| 无一一对应日志类 | simulation/trace.py、metrics.py | 不参与调度的快照及计划/实际区分 |
| 原Java模型、四事件与规则类 | tools/java/src/fogsim/adapter/FixedInstanceMain.java | 0.2固定入口与观察支架，调用原trigger/选择/比较/缓存 |
| DynamicSimulation/MobileDevice原构造 | tools/java/constructors/*.java.inc、tools/java_support.py | 仅生成无采样构造增量，references原件不改 |
| 双侧固定轨迹 | validation/trace_compare.py、tools/run_fixed_parity.py | 原始轨迹保存、明确结构映射、逐事件/逐决策首差定位 |

职责拆分、t=0/全输入统计、去重、预约和固定重建均是已采用的 Python 调整，不声称 Java 原类具有相同结构。完整差异与待确认事项见 IMPLEMENTATION-NOTES。
