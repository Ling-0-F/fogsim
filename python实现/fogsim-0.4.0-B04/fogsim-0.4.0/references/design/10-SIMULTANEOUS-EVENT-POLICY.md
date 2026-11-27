# 同时刻比较策略第一版：Java 兼容主线与可选稳定变体

- 项目：Xu 等（2023）雾计算调度 Java→Python 复现。
- 文档版本：1.0.0；日期：2026-10-22。
- 状态：**用户已采用推荐：首次复现使用 Java 兼容主线；稳定序号排序暂不采用。**
- 关联：[08 事件读写表](08-EVENT-READ-WRITE.md)、[09 接口](09-INTERFACES.md)、[11 实现后验证](11-VALIDATION-AFTER-0.1.md)。
- 证据边界：上传 Java ZIP 的比较器和归并路径已静态核对；目标 JDK 的具体 build、兼容堆实现及运行等价性尚未验证。本文没有测试通过记录。

## 1. 为什么不只规定“同刻按类型排序”

同时刻策略回答：事件时间相同，先处理谁；比较完全相等时怎么办；处理一个事件后，新产生的同刻事件何时重新参与竞争。

这三件事都会改变后续规则看到的资源时间、队列和任务完成状态。只写“时间小者优先”不够；只写四类事件的类型顺序也不能完整复现 Java PriorityQueue。

| 层次 | 本轮采用的主线 | 依据 |
| --- | --- | --- |
| 时间比较 | 有限事件时间按源码普通 `<`、`>` 比较，不设时间容差 | Java 源码事实 |
| 类型及同类分支 | 保留四个 compareTo 的全部返回分支，包括不正常的平分返回 | Java 源码事实；不静默修正 |
| 事件堆 | 按锁定参考 JDK 的 PriorityQueue offer/poll 操作复现暂存堆及全局堆 | 为取得源码行为兼容而采用的 Python 实现建议 |
| 设备归并 | 每次处理一个事件前，按固定设备列表排空各暂存堆，逐项加入全局堆 | Java DynamicSimulation 源码事实 |
| 稳定序号 | 主线不加入 enqueue_seq；处理序号只记日志 | 避免把新政策误称为 Java 原行为 |
| 预约防重 | 用 pending_start 保护已接受但尚未开始的安排 | 既有 Python 设计；不是靠比较器代替状态保护 |

## 2. 时间比较与数值范围

### 2.1 事件时间

先比较 a.time 与 b.time：a 小返回 -1，大返回 +1；两项判断都不成立才进入同刻分支。0.1 输入和全部派生事件时间必须有限，拒绝 NaN、无穷大和加法溢出后的无穷大。

不使用四舍五入、时间桶或 isclose 决定同刻。比如由浮点加法得到的两个不同二进制时间，即使打印成同一个小数，也按实际数值排序。验证时的容差不进入调度算法。

普通比较将 +0.0 和 -0.0 视为同刻；这与下文 priority 的 Double.compare 不是同一种比较规则。

### 2.2 规则分数另行比较

规则分数走 TaskOption.priorTo，对 priority 使用 Java Double.compare 语义：分数较小优先；-0.0 小于 +0.0；NaN 排在所有普通数值及正无穷之后，NaN 与 NaN 比较相等。0.1 的正常 FCFS 分数来自有限资源时间和发布时间；特殊值语义可作为局部比较测试，不能因此允许非法事件时间。

后续 GP 若产生特殊分数，不得为方便直接钳零或换成 Python 对 NaN 的默认比较行为。其错误/记录约定应在 GP 阶段补充。

## 3. Java 四事件的完整同刻比较

下表是 `compare_event_java(a,b)` 在时间相同时的返回值；行是 a，列是 b。-1 表示 a 优先，+1 表示 b 优先，0 表示比较器不区分二者。**比较返回值不等于唯一的实际弹出顺序**，实际顺序还经过堆操作和归并。

缩写：JA=JobArrivalEvent，PS=ProcessStartEvent，TV=TaskVisitEvent，PF=ProcessFinishEvent。

| a \ b | JA | PS | TV | PF |
| --- | --- | --- | --- | --- |
| JA | 按工作流数值 ID；相同仍返回 -1 | -1 | -1 | -1 |
| PS | +1 | 0 | -1 | -1 |
| TV | +1 | +1 | 0 | -1 |
| PF | +1 | +1 | +1 | 按第 3.2 节；关键编号相同仍返回 +1 |

因此，不同类型同刻的关系为：**到达工作流 → 执行开始 → 到达资源 → 执行完成**。

这里的箭头只表示不同类型比较优先级，不是要求每个时刻都具备四类事件，也不是一次性按类型分批执行。新产生的同刻事件还要再次入堆。

### 3.1 JobArrivalEvent 对 JobArrivalEvent

| 条件 | 返回值 |
| --- | ---: |
| a.workflow.id < b.workflow.id | -1 |
| a.workflow.id > b.workflow.id | +1 |
| ID 相同 | -1 |

最后一行来自方法末尾的返回分支，不是合理全序的“相等”。正常输入要求工作流 ID 全局唯一、一个工作流一条初始到达事件，因此该分支在合法路径的可达性与异常输入测试应分开说明，不能为凑测试放宽输入唯一性。

### 3.2 ProcessFinishEvent 对 ProcessFinishEvent

| 条件 | Java 返回规则 |
| --- | --- |
| 两者都是本地执行 | 比较任务所属移动设备的数值 ID，小者优先 |
| a 本地，b 服务器 | -1 |
| a 服务器，b 本地 | +1 |
| 两者都是服务器执行 | 比较服务器数值 ID，小者优先 |
| 上述同类关键编号相同 | 最终返回 +1 |

服务器分支不额外比较 EDGE/CLOUD 类型，也不比较工作流、任务或资源展示字符串。本地与服务器使用不同编号空间。

关键编号相同且同刻时，可能出现 compare(a,b)=+1、compare(b,a)=+1，连自比较也不是 0。源码不满足普通比较器应有的部分性质。本轮主线保留返回分支；不能声称已经证明这些异常分支在所有合法模拟路径均可达或均不可达。

### 3.3 ProcessStartEvent、TaskVisitEvent 的同类平分

同刻两个开始事件返回 0；同刻两个到达资源事件也返回 0。没有源码依据再按任务 ID、资源 ID 或事件创建序号排序。

Java PriorityQueue 的公共契约不保证此时 FIFO。Python 使用稳定排序或 `(time,type,sequence)` 会给出一种明确顺序，但那属于修改策略，不能标成原 Java 的保证。

## 4. 规则选择平分：与事件比较分开

这是候选 TaskOption 的比较，不能混用事件类型顺序。

| 先后层次 | 规则 |
| --- | --- |
| 1 | priority：按 Double.compare，较小优先 |
| 2 | 所属工作流 release_time：按普通 `<`、`>`，较早优先 |
| 3 | 所属移动设备数值 ID：较小优先 |
| 4 | 全局工作流数值 ID：较小优先 |
| 全部平分 | 不替换当前已选项，保留遍历中先出现者 |

不加 task_id、resource_id 或队列到达时间作为第五个键。对于同一任务的多个路由选项，后面三项通常相同，因此完全平分时依候选顺序保留：合法本地、边缘、云。

路由/排序都按 09 的逐项评分选择，不能改为直接调用 TaskOption.compareTo（源码恒为 -1）。等待队列排序选中后才出队，评分时队列长度和缓存包含选中项。

## 5. 设备暂存堆与全局堆

### 5.1 主线的单次取事件流程

每次 `EventQueue.pop_next()` 完成以下步骤：

1. 按 SystemState 中固定的移动设备列表顺序访问设备。
2. 对每台设备，反复 poll 该设备暂存堆，直到为空。
3. 每取一项立即 offer 到全局堆；不直接迭代堆数组，不先放到另一个列表重新排序。
4. 全部暂存堆处理完后，从全局堆 poll 一项作为下一事件。
5. 两层都为空才返回 None。

Engine 更新 clock_time 后处理这一项，处理过程中生成的事件 stage 到相应设备暂存堆。该项处理结束后，再从第 1 步开始。has_pending 同时查看两层，但自身不归并。

初始事件按输入工作流列表顺序 stage 到各自 owner 设备。初始插入次序、设备列表次序和每个暂存堆的 poll 次序都是对照条件。不能因为事件时间一样就经 set 去重或改按字典键排序。

### 5.2 生产设备不一定是事件 owner

| 概念 | 含义 | 影响 |
| --- | --- | --- |
| 当前处理设备 | 当前事件载荷携带的 mobileDevice | 当前 trigger 和规则来源 |
| staging_device | 将新事件加入哪个设备暂存堆；正常 trigger 路径为当前处理设备 | 暂存堆竞争及下一轮归并位置 |
| 新事件 owner | 新事件涉及任务所属工作流的移动设备 | 下次弹出后的 trigger 设备 |
| 实际执行资源 | TaskOption.resource，本地或某服务器 | 处理器队列、available_time 和执行占用 |

共享服务器完成后，队列选中的下一任务可能属于另一台设备。Java 把其开始事件加到当前完成事件设备的暂存堆，但新事件携带下一任务的 owner。Python 事件构造从任务派生 owner，ctx.emit 使用当前处理设备暂存，保留该区别。

当前 0.1 为单设备，数值上不容易暴露差异；接口仍应表达清楚，0.2/后续扩展时再验证跨设备集成。

### 5.3 为什么不能预取一批同刻事件

假设全局堆里有同刻的 TV-A、TV-B。处理 TV-A 时产生 PS-A。下一次归并后，PS-A 按类型比较可先于 TV-B，开始事件因此可能先更新 available_time。

若预先取出 TV-A、TV-B 一起处理，PS-A 就没有机会在第二个到达事件之前参与竞争，资源状态和入队分支可能改变。所以禁止一次性拉出全部相同时间事件后再统一提交新事件。

也不能在 TV-A 内直接调用 PS-A.trigger：这样会跳过其他同刻工作流到达事件、事件堆和日志边界。

## 6. 为什么还要复现堆操作

公共 API 只约束最小项和任意平分处理。此源码还含不正常的比较返回，单纯把 Java compareTo 包成 Python `__lt__` 后交给 heapq，不能据此宣称得到相同轨迹：堆在何时调用哪个方向的比较、选左还是右，可能不同。

采用方案是：**EventQueue 内部提供 Java 兼容堆，暂存堆与全局堆共用同一套实现，并以锁定的参考 JDK 源码及运行 oracle 为准。** 0.1 所需操作主要是空堆建立、offer、poll、判空；不要求移植 Java 集合库全部接口。

实现审查应核对以下操作细节，而不是只验证普通不平分样例：

| 操作 | 需按参考实现核对的细节 |
| --- | --- |
| offer 上浮 | 比较方向是新项对父项；比较结果 >=0 时停止，否则移动父项后继续上浮 |
| poll 补根下沉 | 使用最后一项补根；左右孩子都在时，只有左项对右项 >0 才选右孩子，平分保留左孩子 |
| 下沉停止 | 补根项对选中孩子 <=0 时停止，否则孩子上移、继续下沉 |
| 最终落位 | 保存比较对象与数组移动次序，不能在“看起来相同”的平分处自行换边 |
| 全路径 | 两层堆及每次 offer/poll 的操作顺序一致；不用稳定排序替换其中一层 |

这些是兼容实现的审查目标；最终采用的算法须逐项与指定 build 的对应源码核对。当前没有完成该 build 的源码锁定或 oracle 运行，因此不能把本表视为已经证明 Java 17 某一具体发行包完全兼容。

### 6.1 参考 Java 版本

ZIP 内 `.idea/misc.xml` 写有 `languageLevel="JDK_1_8"`、`project-jdk-name="openjdk-17"`。这是 IDE 配置事实，**不是作者实验实际 JDK/build 的运行证明**。

本轮采用 OpenJDK 17 作为对照参考系列。开始堆对照前记录实际使用的发行方、完整版本/build、可执行程序及对应 PriorityQueue 源码版本。若无法取得作者当年的运行版本，报告应写“与指定参考 JDK 的当前源码运行对照”，不扩张为已复现作者所有环境。

官方参考：

- [Java 17 PriorityQueue API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)：平分任意处理，迭代次序不保证有序。
- [Java 17 Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html)：compare/compareTo 的有符号零和 NaN 语义。
- 参考 build 的 PriorityQueue 实现须另行锁定；不能以不断变化的 OpenJDK master 代替已锁定版本。

## 7. pending_start 与同刻资源保护

比较顺序和资源预约解决不同问题。开始事件尚未触发时，available_time 尚未更新，单靠它可能把资源误认成可再次安排。

| 操作阶段 | 必须保持的规则 |
| --- | --- |
| 上传中 | dispatched=True；未到达资源，不建立 pending_start，不占用处理器 |
| 接受确定开始安排 | 每资源最多一个 pending_start；保存正式 Execution 同一引用、登记执行索引、提交开始事件 |
| 后续到达检查 | available_time>t **或** pending_start 非空就排队；不能再预约第二项 |
| 对应开始事件 | 核对预约身份；只清自己的预约；available_time=自己的 finish_time，再提交完成事件 |
| 旧完成事件 | 不把 available_time 重写成 t，不清其他 Execution 的 pending_start；队列续接仍检查预约 |

特别是同刻 PS 比 PF 优先，下一执行可能已更新资源时间，而旧执行的完成事件还未处理。从队列续接的时间保持 `max(available_time,t)`；不能改成“完成了就一律在 t 开始”。

实际占用区间采用 `[start_time, finish_time)`，包含下载，首尾相接允许。因为 PF 可晚于同刻 PS 记录，“已开始但尚未写 completed 标记的任务数<=1”并非可靠的全程检查；应检查占用区间与预约对应关系，不能误把事件记账次序当成物理重叠。

Java 的 canAddToQueue 只看全局堆迭代器的一项且未全面检查设备暂存事件，不能称为充分预约保护。pending_start 是明确的 Python 改进，其边界结果是否与原始 Java 不同仍须测试记录；若原代码暴露错误，不应为取得相同错误而关闭该保护。

## 8. 可选稳定变体：记录但不用于本轮主线

若以后目标转为更清楚的确定性模拟，可另设 `stable` 策略。它属于新增行为，不能拿其结果声称通过 Java 原始事件序列验收。

| 部分 | 变体建议 |
| --- | --- |
| 总键 | `(time, type_rank, same_type_key, enqueue_seq)` |
| type_rank | JA=0，PS=1，TV=2，PF=3 |
| JA 同类键 | workflow_id |
| PS/TV 同类键 | 空元组，后续按 enqueue_seq |
| PF 同类键 | 本地 `(0, owner_device_numeric_id)`；服务器 `(1, server_numeric_id)` |
| enqueue_seq | 每轮 EventQueue 首次接收事件时分配，归并时保留；每轮从初始值重建；不能复用 processed_event_count |
| 归并节奏 | 仍保留相同设备暂存及每事件重新归并，便于只改变一个因素 |

这个变体会正规化异常比较分支，并把原来的未定平分变成明确先入先出。优点是规则容易解释和复查；代价是可能改变同刻顺序、特征、选择与结果。只有作为显式的另一个实验配置并单独验证后才能使用。

**当前采用项只有 Java 兼容主线。** 不默认同时实现两个模式，也不在兼容模式背后悄悄追加稳定序号。

## 9. 需要验证什么

| 层次 | 验证内容 | 阶段 |
| --- | --- | --- |
| 比较器局部 | 时间先后、完整矩阵、同类关键编号、异常返回、有符号零和 NaN 的 priority 比较 | 0.1 必要组件检查；特殊事件对可用合成对象 |
| 堆局部 | 与指定 JDK 相同的 offer/poll 输入操作及输出序列，涵盖平分和异常分支 | 0.1 后即可准备和执行的小型 Java oracle；不要求完整模拟器对照已通过 |
| 归并局部 | 设备顺序、暂存 poll、全局 offer、每事件再归并、新同刻事件重新参与 | 0.1 组件检查；跨设备完整集成按后续范围 |
| 预约局部 | 已安排未触发开始时不重复预约；两条接受开始路径和身份校验 | 0.1 基础保护检查 |
| 复杂竞争集成 | 多工作流、多种同刻事件、完整 DAG、共享资源与轨迹差异 | 0.2 主验收 |
| 完整行为等价 | 固定相同输入、ID、规则、候选、归并、目标 JDK 下逐事件逐决策比较 | 0.2；Java 固定输入适配尚未实现 |

针对原始比较器的测试应验证“返回与源码相同”，不能要求异常分支满足反对称性后才算通过。可另设性质报告揭示异常，但不要为使性质测试变绿而修正兼容比较器。

堆 oracle 是堆操作级证据，不能替代完整调度对照；Python 自己多跑几次相同只证明本实现可重复，也不能单独证明与 Java 相同。验证细目、样例与证据格式见 11。

## 10. 源码与当前进度

Java ZIP：`Fog-Computing-multiDeviceDebug.zip`。

SHA-256：`17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a`。

| ZIP 内相对 Fog-Computing-multiDeviceDebug/ 的路径 | 事实 |
| --- | --- |
| src/mengxu/simulation/event/JobArrivalEvent.java | 时间、工作流 ID、末尾 -1 |
| src/mengxu/simulation/event/ProcessStartEvent.java | 同类 0，先于 TV/PF |
| src/mengxu/simulation/event/TaskVisitEvent.java | 同类 0，晚于 JA/PS、先于 PF |
| src/mengxu/simulation/event/ProcessFinishEvent.java | 本地/服务器及编号比较、末尾 +1 |
| src/mengxu/taskscheduling/TaskOption.java | priority 的 Double.compare 与后续平分 |
| src/mengxu/simulation/DynamicSimulation.java | mobiledeviceHaveEvent 和 run 的两层归并节奏 |
| src/mengxu/taskscheduling/MobileDevice.java | 暂存事件、canAddToQueue 的实际限制 |
| .idea/misc.xml | IDE JDK 配置线索；未证明作者实际运行 build |

**同时刻策略第一版设计已完成。** 目标 build 的锁定、兼容实现、可达边界和运行等价性是后续验证事项，不是已经通过的结论。

整套同步时应更新 00/05 的进度，02 的 EventQueue 职责，03 的顺序及事件序号说明，06 的比较矩阵/JDK 限制，07 的事件队列管理链接，08 的“策略尚待设计”旧表述。无需向固定输入添加 enqueue_seq 或其他运行状态。
