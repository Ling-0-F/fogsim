# Java 固定实例适配器：0.2.0

本次适配器实际执行原Java项目的模型、规则和四类事件。它与0.1的“方法抽取组件oracle”是两套不同工具：固定适配器运行完整固定 DAG、竞争和同刻交错生命周期，组件oracle继续负责局部比较器/堆/缓存测试。

## 原始代码与适配代码的边界

`references/java/Fog-Computing-multiDeviceDebug/` 保持原始内容。构建工具在 `outputs/parity/build/overlay/` 生成两个同名类的副本，仅增加protected构造函数；原方法正文不改。Java编译器使用overlay优先的sourcepath，并编译原始依赖类。没有使用原项目 `out/` 中的旧class文件。

| 项目 | 原始Java行为 | 本次固定模式适配 | 是否改变原调度选择/排序 |
| --- | --- | --- | --- |
| DynamicSimulation构造 | 建立RNG、采样资源、调用setup | 新构造仅注入SystemState并建全局PriorityQueue | 跳过随机环境构建，原run不作为固定入口 |
| MobileDevice构造 | 配置共享sampler并建立随机图生成器 | 新构造建立资源局部初态；sampler/RNG/生成器保持null | 原队列、readyTime、canAddToQueue未改 |
| 资源参数 | 由工作量/带宽等生成UT/PT/DT | 直接读取完整固定时长；速率/带宽使用未被当前规则读取的1.0占位 | 只允许FCFS或固定资源规则；不能据此运行依赖真实速率的其他规则 |
| 输入ID | Java任务ID为int | 工作流整数ID保留；任务字符串ID按各工作流列表顺序映射0..n-1，日志反向映射 | 不增加Task/Resource平分键；超出Java int32的工作流ID明确拒绝 |
| 工作流接纳 | addJobToSystem要求release>clock，含生成计数/训练窗口 | 到达事件处理时加入活动集合，支持t=0；初始事件按输入顺序暂存 | 固定模式的生命周期适配；未来工作流不加入规则可见活动集合 |
| 后续工作流生成 | Arrival调用generateWorkflowJob | FixedDevice覆写为空操作，并记录被抑制调用次数 | 停止随机输入扩张；原Arrival.trigger仍实际调用此方法 |
| 工作流完成统计 | completeJob按warm-up等条件筛选 | 全部完成输入记录进jobsCompleted并移出活动集合 | 原Finish触发登记的位置、completionTime和标记写入保留 |
| 主循环 | 以训练数量/保护阈值停止，异常可写极大时钟 | 固定有限事件循环，调用原mobiledeviceHaveEvent；每轮poll一条、更新时间、调用原trigger；明确失败/事件上限 | 保留两层归并和逐事件节奏；替换训练停止/指标口径 |
| 日志 | 原项目没有本次统一轨迹格式 | 在事件边界、addEvent、规则调用周围观察并复制数值 | 观察结果不回写调度状态 |

**原样执行的关键部分**：四事件构造/trigger/compareTo、Task.getNextDag与TaskOption.getNextDag、AbstractRule.nextTaskOption/priorTask、TaskOption.priorTo、FCFS.priority、Process时间公式、两类资源入出队与缓存、MobileDevice.canAddToQueue、DynamicSimulation.mobiledeviceHaveEvent、真实JDK PriorityQueue。

FCFS评分使用原类委托；观察规则通过 `super.nextTaskOption/priorTask` 调用原选择循环。固定资源的0/1调试评分由适配器新增，与Python相同，不冒充论文基准算法。两轮后继路由来自原Java真实调用链，观察器只标注轮次。

## Python 改动

第一阶段只扩充日志，本轮另在 `Execution.__post_init__` 拒绝总执行区间因 binary64 精度归零的计划。普通正区间输入保留原调度路径。精度反例是明确不等价边界，见 `ISSUES-AND-FIXES.md`，不作为正常对照通过。

本轮 `FixedDevice.canAddToQueue` 增加只读观察：恰好调用一次原 `super` 方法、原样返回结果，随后记录全局堆首和观察到的待开始列表。观测集合不参与调度。独立 `ReservationBoundaryMain` 只运行手工状态实验，不把它们冒充完整可达调度案例。

## 日志口径与原始差异

每个案例目录包含以下文件：

| 文件 | 含义 |
| --- | --- |
| `java-request.json` | 交给Java的固定输入与实际配置，不含随机seed |
| `java-raw.json`、`python-raw.json` | 两侧真实运行输出，不被对照器改写 |
| `java-normalized.json`、`python-normalized.json` | 仅用于比较的独立副本 |
| `comparison.json` | 通过/失败、计数、首差、容差及明确的表示映射 |
| `run-manifest.json` | 原始输入/配置SHA、候选和ID映射、初始stage顺序、构建指纹、raw哈希 |
| `java-process.json`、stdout/stderr | JVM命令、退出码及原始进程输出 |

输入回显之外，两边都导出从已构建模型读取的 `loaded_model`，核对实际依赖、任务数值ID、候选顺序和UT/PT/DT，避免仅凭“用了同一个文件”判定加载一致。

Java原生未完成 `completionTime` 为0.0，Python为None。只有“未登记且恰为0.0”的Java默认值转换为None；意外非零值仍参与比较。完成后的时间不作这一转换。

Java没有 `pending_start`。Java日志使用 `observed_pending_starts`，由已发出但未触发的Start事件引用观察得到；不会用于拒绝新安排。Python的零/一个预约与该列表按任务键对照，多个Java待开始项完整保留，不能压成一个。Java的原 `canAddToQueue` 检查保持原样。本轮 110 个正常固定输入案例未发现预约差异；精度归零反例确有可达差异，已保留原始失败报告并明确拒绝该数值范围。

原Java没有SystemState执行索引。日志从正式发出的Start事件观察已接受Process计划，忙分支创建但未安排的临时Process不进入此观察列表；完成历史从原Job的ProcessFinishEvent列表读取。观察集合均不参与规则、队列或事件比较。

观察映射、生产设备和事件标识采用Java `IdentityHashMap`，避免原Process.equals恒false及某些事件仅按类/时间相等导致日志误关联。堆仍使用原compareTo，没有替换原相等语义来参与调度。

## 首个差异如何确定

先比较输入、配置和实际加载模型；再按真实事件顺序比较：

1. 类型、时间、workflow/task/resource、owner、生产设备。
2. 事件处理前状态。
3. 事件内部实际顺序的DECISION和EMIT，包括两轮路由和全部候选评分。
4. 发出事件列表、处理后状态、错误。
5. 最终任务/工作流记录、决策索引、数量和指标。

数组顺序严格比较，不排序、不补调用、不按时间重新匹配事件。对象键排列不影响结果。整数ID、类型和计数精确比较；时间/分数等按abs=1e-9、rel=1e-12检查，priority正负零保持区别。容差不影响两侧实际调度。

失败报告保存首差的事件序号、时间、阶段、字段路径、Python值、Java值和原因。两侧都FAILED或缺少详细事件也不能判为通过。Java进程失败前会清除本次目标trace旧文件，防止读取上一轮结果；套件基础设施失败会写ERROR摘要，不保留旧“通过”结论。

## 实测结果与范围

14 个正式配置及 96 组固定扫查均通过：每种语言 3,469 条事件、2,021 次决策。详细逐例结果及 V2-01～05 映射见 `VALIDATION.md`，证据在 `outputs/v2/`。原链式首差故障注入继续执行，原 raw 不修改。

本次实际采用 Temurin 17.0.16+8，记录 vendor/build/源码 SHA；0.2.1 允许任意 JDK 17 更新版本，不强制其与参考指纹相同；构造增量仍只增加构造函数，原 647 份源码及 12 个依赖与原 ZIP 一致。44 条既有编译警告、0 错误。

数值精度归零负例单列于 `outputs/v2/precision-collapse/`：Python FAILED，Java 返回成功但两个正区间重叠，比较 `passed=false`。`outputs/issues/precision-before/` 保留修正前 Python/Java 的真实分叉。不得压缩待开始列表或改变对照器使其通过。

本结论只覆盖固定模式支架和明确列出的输入。原训练入口、warm-up、任意输入、DAX/RNG、GP、论文实验未验证；两个设备共享服务器只是一项额外集成检查。
