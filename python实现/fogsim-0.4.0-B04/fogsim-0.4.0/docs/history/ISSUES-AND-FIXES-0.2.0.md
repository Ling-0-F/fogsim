# 本轮发现的问题、复现与代码修改

版本 0.2.0；验收日期 2026-10-29（America/Los_Angeles）。本报告仅讨论固定实例模拟器，不把 Java 原算法的问题改写为移植器应当照抄的正确行为。

## 1. 可达的预约差异：正 PT 被浮点精度吞掉

### 输入与执行方式

完整输入：`data/cases/v2_precision_collapse.json`；配置：`configs/v2_precision_collapse.json`。三种资源候选齐全，所有任务固定选择 M0，本地 UT=DT=0，各工作流只有一个任务 A，无依赖。定义 T=2^53=9007199254740992 秒：

| 工作流 ID | 发布时间 | PT | 目的 |
| --- | ---: | ---: | --- |
| 0 | T−4 | 4 | 在 T 产生一条旧完成事件 |
| 1 | T−2 | 4 | 提前进入等待队列 |
| 2 | T−2 | 4 | 提前进入等待队列 |
| 5 | T−2 | 4 | 提前进入等待队列 |
| 3 | T | 1 | PT 为正，但 binary64 下 T+1==T |
| 4 | T | 1 | 同样形成零长度执行 |

原始包 0.2.0a1 上运行本输入的固定对照，实际产物原样保留于 `outputs/issues/precision-before/v2_collapsed_time/`。其中 `java-request.json` 是实际交给 Java 的全部输入和配置，`comparison.json` 是未修正前的首差报告；目录名保留发现当时的名称。复现旧行为时，将该输入和配置放入用户原始 0.2.0a1 包，再运行其 `tools/run_fixed_parity.py --config ...` 即可；必须使用指定 JDK。

### 第一个不同点与后果

T 时刻，W3/W4 的 Start 都产生同刻 Finish，旧 W0 的 Finish 也尚未处理。堆按原比较器依次处理若干 Finish，W1 被安排在 [T,T+4)，W2 先被安排在 [T+4,T+8)，此时 M0 已有 W2 的未来预约。

**第 19 条实际事件**是 W0 的 `ProcessFinishEvent`，time=T。旧 Python 看到 `pending_start=W2`，保留 W5 在队列；Java 的 `ProcessFinishEvent.trigger` 继续无条件出队 W5，再安排一条 [T+4,T+8) 的 Start。两条未来 Start 同资源、同区间，Java 日志保留 `observed_pending_starts=[[2,"A"],[5,"A"]]`。

首差路径：`$.result.events[18].actions[0]`；Python 动作数 0，Java 动作数 2（SEQUENCING 与 EMIT）。未排序、未合并事件、未压缩 Java 的多条待开始列表。

| 原始实现实测 | W2 区间 | W5 区间 | makespan |
| --- | --- | --- | ---: |
| Java | [T+4,T+8) | [T+4,T+8) | 12 |
| 旧 Python 0.2.0a1 | [T+4,T+8) | [T+8,T+12) | 16 |

真正的重叠是 W2 与 W5 两个正长度区间。W3/W4 的 [T,T) 是空区间，不单独算物理重叠。

这里**不是某次 canAddToQueue 返回错误造成的差异**：Java 的 Finish 续接路径根本没有调用它。`pending_start` 与 Java 原保护的结构差别，在这个可达的数值退化输入上才转化为不同运行行为。

### 本轮实际修改

实际修改 `src/fogsim/model/execution.py` 的 `Execution.__post_init__`。在原有有限数值/非负检查后、写入计划字段前增加：

```python
require(finish > self.start_time,
        "execution duration lost to floating-point precision ...")
```

保留 `(start+PT)+DT` 的原运算顺序。`reserve_start` 仍先成功构造 Execution 才登记执行索引、资源预约和 Start 事件，所以拒绝时没有幽灵计划或实际 start/finish。没有删除 `pending_start`、放松区间不重叠不变量、修改 Java 原件或改动对照器来隐藏差异。

修正后该输入在**第 12 条 TaskVisitEvent**接受 W3 的安排时明确失败：`status=FAILED`、`makespan=null`，原因含 start/PT/DT。对应证据：`outputs/v2/precision-collapse/`。原 Java 仍成功结束但存在上述重叠；比较报告继续为 `passed=false`。总验收中的负例 gate 仅表示“已识别并拒绝这个已知边界”，不表示该输入跨语言等价。

这收紧了此前“有限时间、PT>0 就可正常运行”的实现边界：实际总占用区间还必须在 binary64 中严格为正。仅计算结束时刻舍入为 start、但 DT 使总占用仍为正的情况保留原数值结果。若要支持极大绝对时间和极短作业，应先减去统一时间原点，或另立高精度时间模型并重新对照；不能只把输入改成更长的小数字符串。

相关回归：`tests/unit/test_execution_precision.py`；完整原 Java 反例回归：`tests/parity/test_v2_acceptance.py::test_precision_counterexample_is_an_explicit_failure_not_false_parity`。

### 若后续要修正原 Java

本轮交付保持 `references/java/` 的原始字节，以它作为原实现 oracle。若另建“修正版 Java”分支，应至少修改：

- `taskscheduling/Process.java`：计算 finish 后检查有限性及 `finishTime > startTime`，报告输入精度问题。
- `taskscheduling/MobileDevice.java::canAddToQueue`：用统一、按资源标识的待开始预约；若暂用事件扫描，则必须覆盖全局堆与所有设备暂存堆，不能只看 iterator 第一项。
- `simulation/event/ProcessFinishEvent.java::trigger`：本地、服务器两个续接分支均检查已有待开始预约；已有预约时不再从队列创建另一条 Start。
- `simulation/event/ProcessStartEvent.java::trigger`：只消耗匹配的预约，再更新 readyTime。

这是后续 Java 修正版建议，不属于本轮已修改的原件。不能只补 canAddToQueue，因为实际反例来自绕过该方法的 Finish 路径；也不能再把修正版当作原 Java 运行基线。

## 2. canAddToQueue 的局部边界差异与正常路径

`tools/java/src/fogsim/adapter/ReservationBoundaryMain.java` 调用原方法，分别注入四种状态。结果在 `outputs/v2/reservation-probe/result.json`：

| 手工状态 | Java 允许新开始 | Python 预约允许新开始 | 是否相同 |
| --- | --- | --- | --- |
| 无待开始事件 | 是 | 是 | 是 |
| 匹配 PS 仅在设备暂存堆 | 是 | 否 | 否 |
| 匹配 PS 位于全局堆首 | 否 | 否 | 是 |
| 其他资源 PS 为堆首、匹配 PS 在后面 | 是 | 否 | 否 |

这些是组件边界实验，不是声称可由正常事件循环达到的四个完整案例。Python 一侧的预约规则也由已有直接 Visit/Start/Finish 组件测试实际执行；表中的 Python 列表示按预约存在与否作出的允许条件。

正常 110 个实例的 395 次实际方法调用未观察到差异。观察器 `FixedDevice.canAddToQueue` **只调用一次 `super.canAddToQueue`，原样返回结果**，随后输出堆首和待开始列表；输出不参与调度。每个完整事件前后也比较资源预约，确保没有通过日志转换丢掉多个 Java 待开始项目。

在总占用区间严格为正、每事件前都归并暂存堆的条件下，同刻 PS 会先于 TV；未来 PS 对应 available>time，会先走 busy 分支。因此本轮普通固定实例不需要删除或替换 Python 预约保护。该源码路径解释与实测不能外推为对任意输入、任意改动后入口的形式化等价证明。

## 3. 参考 JDK 与验收门禁不够严格

旧 `tools/java_support.py::prepare_and_compile` 和 `tools/run_java_oracle.py::run_oracle` 只检查 `java.specification.version = 17`。因此另一个厂商或另一个 17.x build 也会被允许，和“锁定 JDK 17.0.16+8”的验收要求不一致。环境中默认 Java 实际是另一个 17.x build，不能直接用于本轮声明。

已增加共用 `reference_jdk` 检查：vendor=Eclipse Adoptium、runtime=17.0.16+8、`PriorityQueue.java` 的固定 SHA-256 三项均须满足。Linux 与 Windows 使用各自二进制、相同 vendor/build 和源码锁。构建清单另记 Java/javac 二进制指纹。`tests/unit/test_jdk_lock.py` 验证错误 build/vendor 被拒绝，不会只因“都是 17”而通过。

旧验证入口直接沿用 pytest 退出码；缺 JDK 的测试可能 skip，导致命令退出 0。正式发布要求现在由 `tools/validate.py` 与 `tools/build_release.py` 同时检查：测试无 skip、正常 Java 固定对照通过、V2 正式验收 gate 通过。运行前清除本次总报告，防止复用旧的成功结论。

## 4. 本轮开发中修正的诊断问题

第一次新增完整测试结果为 276 通过、1 失败。`positive_intervals` 辅助函数原先将 [t,t) 放入正区间重叠扫描，多报了一个“W1 与零长度 W3 重叠”；W2/W5 的真实重叠始终可见。已过滤 `finish>start`，增加 `test_empty_half_open_intervals_are_not_reported_as_overlap`，保存初次 XML 后重新完整执行。

新增 JDK 属性解析最初对空 `java.class.path = ` 先 strip 后 split，造成长度为 1 的字典项。已改为先分隔、再分别 strip，相关错误 build/vendor 测试也含空 class.path。此问题只在新增验证工具开发阶段出现，没有改变模拟规则。

## 5. 修改文件导航

| 文件 | 实际修改目的 |
| --- | --- |
| `src/fogsim/model/execution.py` | 拒绝整体执行时长被浮点精度吞掉的安排 |
| `tools/java_support.py`、`tools/run_java_oracle.py` | 同一锁定 JDK 校验；平台路径支持；二进制与源码指纹 |
| `tools/java/src/fogsim/adapter/FixedInstanceMain.java` | 原 canAddToQueue 返回值与堆首的只读观察，不改原调度 |
| `tools/java/src/fogsim/adapter/ReservationBoundaryMain.java` | 四种隔离状态的原方法边界实验 |
| `tools/v2_cases.py`、`tools/run_fixed_parity.py` | 14 个正式配置及固定对照入口 |
| `tools/run_v2_acceptance.py` | 96 组同输入扫查、局部边界、精度反例及合并 gate |
| `tests/parity/test_v2_acceptance.py` | V2-01～05、独立生命周期断言、重跑/日志无干扰、完整 Java 负例 |
| `tests/unit/test_execution_precision.py`、`test_jdk_lock.py` | 数值精度与运行环境锁定回归 |
| `tools/validate.py`、`tools/build_release.py` | 无 skip 发布门禁、当前 V2 证据及原 Java 完整性检查 |
| `tools/package_smoke.py` | 最终 ZIP 独立解压后重新编译并核对来源、运行正式对照 |
| `configs/v2_*.json`、`data/cases/v2_*.json` | 10 个正式输入与 1 个明确数值边界反例 |

完整相对原 0.2.0a1 的文本变更另附 `CHANGES-FROM-0.2.0a1.patch`。所有新证据与原始 Java 参考文件均在修订包中。
