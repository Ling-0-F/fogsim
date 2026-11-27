# 0.1 实际验收记录

日期：2026-10-22。基线：00—07 v1.1.0，08—11 v1.0.0；实现 0.1.0。原设计 11 是验收清单，本文件记录真实执行与证据，不修改原始设计快照。

## 执行环境与命令

Windows x64，CPython 3.12.12，pytest 9.1.1；局部 Java oracle 为 Eclipse Temurin OpenJDK 17.0.16+8。Python 模拟器无运行时第三方依赖。实际命令（项目根目录）：

```powershell
.\.venv\Scripts\python.exe tools/validate.py
```

该命令内部执行 `python -m pytest -q --junitxml=outputs/pytest-results.xml`，再运行4组实例，保存完整结果与材料/源码哈希。原始 [控制台](../outputs/pytest-console.txt)、[JUnit XML](../outputs/pytest-results.xml)、[验证清单](../outputs/validation-manifest.json) 是实际结果来源；源码快照的精确 SHA-256 以清单中 `snapshot_sha256` 为准。

## 四组端到端实际结果

| 场景 | 预期来源 | 实际完成/事件数 | makespan | 结果/证据 |
| --- | --- | --- | --- | --- |
| CASE-L，单任务固定 M0 | 11 §7.1：PT3，UT/DT0 | A=3；4事件 | 3 | [通过](../outputs/single_local.json) |
| CASE-L，release=5 | 11 §7.1：5+3=8 | A=8；4事件 | 8-5=3 | [通过](../outputs/single_local_release5.json) |
| CASE-R，A→B固定E0 | 03 与11 §7.2 | A=6，B/W=13；7事件 | 13 | [通过](../outputs/chain_remote.json) |
| CASE-F，相同输入改FCFS | 11 §7.3、实际FCFS源码 | A在M0=10，B在E0=17；7事件 | 17 | [通过](../outputs/chain_fcfs.json) |

固定 E0 的任务实际时间为 A `[dispatch=0,arrival=2,start=2,compute=5,finish=6]`、B `[6,7,7,11,13]`。FCFS 的 A 为 `[0,0,0,10,10]`、B 为 `[10,11,11,15,17]`。compute 是由实际开始派生的时刻，无第五种事件。单链没有真实等待队列，缓存测试另外执行。

## A层检查与测试定位

以下测试文件均位于 `tests/`。ID 采用设计11中的编号；一项测试可能同时验证多个关联不变量。

| 设计验收项 | 实际检查 | 测试证据 |
| --- | --- | --- |
| IN-01～06 | 时间/数值、唯一ID、合法边/环、完整候选、本地资格、未知运行字段、输入顺序 | `unit/test_input.py` |
| INIT-01～03、OBJ-01～03 | 初始标记/集合/预约、t=0未自动激活、规范引用、身份相等、事件纯构造 | `unit/test_model_rules.py::test_initialization_and_identity`、`test_constructors_pure_and_identity_equality` |
| VIEW-01/02 | 递归遍历规则可达图，无未来工作流或完整state；同刻未处理到达仍不可见 | `test_view_cannot_reach_future_even_at_same_release` |
| RD-01～03 | 就绪列表/空列表、活动集合资格、读前后字段图一致、空列表不等于完成 | `test_query_is_pure_and_empty_not_done` |
| SEL-01～04 | FCFS原值、release排序、平分层次、有符号零/NaN/无穷 | `test_fcfs_scores_overwrite_and_queue_selection_keeps_members`、`test_selection_tie_hierarchy`、`test_double_compare` |
| SEL-05～07、09 | 每项评分覆盖、单项也评分、队列尚在、空候选错误、违规改状态可检测、快照不变 | `test_fcfs_scores_overwrite_and_queue_selection_keeps_members`、`test_empty_selection_and_mutating_rule` |
| SEL-08 | A,B,A,B两整轮；完成两轮前后继均未派发 | `test_two_complete_routing_rounds_and_no_early_dispatch`（局部完成流程） |
| EV-01～07 | 时钟/ready/available/标记、四事件与新事件分离、下载占用、不省略后继UT | `integration/test_runs.py::test_chain_stable_boundaries`、`test_hand_calculated_full_runs`；事件队列组件 |
| Q-01～06 | 到达排队无幽灵执行；整数/浮点缓存；身份移除；空队类型差异 | `unit/test_queue_lifecycle.py::test_pending_reservation_before_start_and_queue_continuation`、`test_integer_cache_includes_upload`、`test_cache_order_identity_and_resource_difference` |
| Q-07、EV-06 | 即使单项队列也排序，先出队/缓存再后继路由 | `test_finish_dequeues_before_successor_routing` |
| EX-01～03 | 正式执行建立时机、不可变计划、时间公式、索引/预约/事件/历史同引用 | `test_pending_reservation_before_start_and_queue_continuation`、`test_constructors_pure_and_identity_equality`、链式稳定边界 |
| RES-01～04 | 预约但未开始时第二项排队；两路径防重；Start才写avail；匹配清除 | `test_pending_reservation_before_start_and_queue_continuation`、`test_mismatch_reservation_and_foreign_objects` |
| RES-05/06 | 同刻旧Finish不清新预约/不回写avail；接受的执行区间不重叠 | `test_old_finish_does_not_clear_new_reservation_or_availability`（参数化已开始/未开始），所有完整事件后不变量 |
| WF-01～07 | 同步完成记录与计数、分区、完整登记、幂等/错误登记、保留拓扑、无warm-up | 生命周期组件、`test_registration_inconsistent_flag`、`test_registration_inconsistent_records`、四完整实例 |
| EQ-01～04 | 精确时间、完整4×4矩阵、同类关键编号/异常分支、非FIFO平分 | `unit/test_events.py::test_complete_same_time_matrix`、`test_numeric_ties_and_exact_time`、`test_equal_heap_is_not_fifo` |
| EQ-05～09 | 两层判空/归并、每事件重新竞争、owner与暂存区分、源堆审查 | `test_staging_drain_and_each_event_recompetition`、`test_owner_and_staging_are_distinct`、Java oracle |
| RUN-01～04 | 成功条件、事件耗尽、重复/外来对象失败、单次引擎、程序缺陷抛出 | `integration/test_runs.py`、预约/完成局部负例；额外检查时间/缓存溢出和过去事件 |
| LOG-01～03 | 计划/实际分离、历史分数不变、开关日志后实际pop序列和结果一致 | `test_failure_preserves_plan_vs_actual`、快照测试、`test_logging_switch_preserves_actual_pop_sequence` |
| RE-01～04 | 结果与详细轨迹重复一致、全新初态及对象、旧结果不变、固定模式无采样 | `test_log_off_and_fresh_rerun`、输入spec不可变测试、CLI repeat测试 |

每条完整事件后检查集合分区、对象身份、completed蕴含dispatched、记录/计数、队列/缓存、预约与待处理Start一一对应、接受执行的占用区间。验证容差仅用于缓存数值检查（abs=1e-9、rel=1e-12），不进入调度比较。整数时间案例精确断言。

## B层：Java局部参考验证

J-01：实际build、二进制SHA及对应PriorityQueue源文件已锁定并核对，见 [JAVA-REFERENCE](JAVA-REFERENCE.md)。J-02～06：原方法受控抽取支架真实运行，比较器、priorTo/Double.compare、offer/poll、两层归并和缓存均对照通过。

实际4,764条操作产生3,797条输出，逐行一致。缓存K行比较原始double位模式，不是宽容差对比。测试及报告：[test_java_components.py](../tests/parity/test_java_components.py)、[report.json](../outputs/java_oracle/report.json)。

受控抽取保留原方法内容，支架替代原构造/采样环境。因此它不是原始完整类构造链的运行证明，也不是Java调度器整体对照。

## 首次失败与后续修正

首次Python测试为81通过、1失败：本地缓存手填预期未匹配实际出队顺序。原Java方法oracle证实结果为`5.551115123125783e-17`，据此修正测试预期；没有改实现归零或放宽容差。详见IMPLEMENTATION-NOTES N05。之后补充了登记损坏状态、队列先于路由、非法派生时间与日志无干扰检查。

最终数量及失败/跳过状态由下方自动记录区和原始报告给出；不把手算、源码阅读或文档完成算成运行通过。

## 未执行与尚存边界

- 完整原Java调度器固定输入适配及逐事件/逐决策轨迹对照：未实现、未执行，属于0.2。
- 复杂DAG分叉汇合、完整竞争场景、多设备完整集成：未作0.2正式验收；已有局部测试只验证对应组件/阶段。
- pending_start与Java canAddToQueue在所有可达同刻场景的行为差异：待上述对照确认。
- 作者实际JDK/build：无法由现有材料确认；本次仅锁定参考Temurin17。
- DAX、随机生成/RNG/seed、GP、训练窗口、论文规模结果：后续范围，未执行。
- 其他Python版本/操作系统：未运行；声明支持Python>=3.11是接口与语法范围，实际证据仅上述环境。

## 最终执行结果

最终执行：**113 passed，0 failed，0 errors，0 skipped**，pytest 报告耗时1.21秒。四组实例均 SUCCEEDED；makespan 为3、3、13、17，实际时钟分别为3、8、13、17。Java局部oracle包含在通过测试中，3,797条输出全部一致。

`compileall` 已成功检查源码、工具和测试语法。ZIP 构建器逐文件校验已验证源码哈希，校验压缩包CRC和文件SHA；包内保留 `RELEASE-FILES.json`。完整Java调度等价性仍按上节列为未执行。

交付包另做隔离运行检查：解压后以基础Python的 `-I` 模式显式加载包内 `src`，断言实际导入路径属于解压目录；四案例均SUCCEEDED且makespan仍为3、3、13、17。见 [package-smoke.json](../outputs/package-smoke.json)。没有依赖原项目的editable安装来完成此项检查。
