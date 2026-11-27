# fogsim 0.2.1 下一阶段扩展需求与详细设计初稿

> 这是本轮文档创建内容的快照，未与云端 Page 校验，也不包含后续编辑。

设计日期：2026年11月4日，America/Los_Angeles。设计状态：阶段C初稿，等待整体审阅；未进入编码准备。实现基线：用户提供的 fogsim 0.2.1 verified 包。

目标是在已验证的固定实例内核上增加 DAX、随机工作流、多设备动态输入、可复现实验和 Java 导出重放。原四事件、比较器、两层堆、资源预约及固定输入入口继续保留。跨语言验证以相同实际输入为基础，允许所选 Python RNG 和采样算法产生不同于 Java 的随机序列。

“已确认”只表示用户已经确认设计语义，不表示功能已实现或运行验收通过。本文接口、字段、格式及错误码的具体命名是对已确认语义的集中具体化，状态为“建议待确认”；最终审阅通过后再冻结。所有新增动态能力的运行验证均尚未执行。

# 1 范围与版本边界

## 1.1 本阶段范围

支持标准 Java 类型编号0至19对应的 DAX 拓扑；按照原业务顺序生成任务和工作流参数；初始化多移动设备及共享边缘、云资源；运行事件驱动动态来源；复现 Java 正常统计筛选、reset、rerun 和 seed 轮换；提供完整输入记录、固定投影和记录驱动重放。

本阶段提供数据清理接口，但复现核对阶段默认保留边数据，完成验证后可显式启用释放。

## 1.2 非目标

不实现 GP 表达式、十个特征、演化算子、单树或多树训练、论文规模性能复现；不增加网络排队、动态带宽分配、抢占、失败重试、运行中设备增减或 sampler 改参。解析器支持本项目需要的 DAX 拓扑子集，不宣称完整 DAX 标准实现。

## 1.3 固定基线

以下现有行为保留：严格固定 JSON；字符串任务 ID；每轮独立规范对象图；四事件；Java 兼容比较和两层堆；完全平分保留遍历行为；Finish 后两整轮路由；pending_start 预约；计算与下载共同占用处理器；队列缓存的原加减顺序；固定全部输入完成才成功；领域失败返回 FAILED 和空 makespan；未知程序异常向外传播。

不覆盖原 ZIP。现有 API、配置、固定结果字段、顺序及 repeat 含义保持兼容。新增格式有独立标识，不把物理字段塞入旧加载器后再静默丢弃。

# 2 证据等级与当前验证状态

| 类别 | 当前证据 | 适用范围 |
|---|---|---|
| Python 已有行为 | 源码、测试、README、VALIDATION、IMPLEMENTATION-NOTES、ISSUES-AND-FIXES、roadmap、semantics | 0.2.1 当前实现 |
| 包内历史运行证据 | 286项通过，0失败、0错误、0跳过；14正式配置和96固定扫查；每种语言3469事件、2021决策 | 指定固定输入及适配口径 |
| 本轮实际复核 | 14正常配置完整 Python 结果与保存轨迹一致；精度反例第12事件明确失败 | 不扩大为本轮完整测试或 Java 重跑 |
| 文件一致性 | 117个清单文件哈希匹配；647份 Java 源码和12个依赖 JAR 与另附 Java ZIP 逐字节一致 | 当前输入与参考来源 |
| Java 静态事实 | 实际构造、生成、四事件、统计及重置调用链；相关 Commons Math 3.5 字节码 | 不等于动态运行验证 |
| 新增运行验证 | 尚未执行 | 见验收矩阵 |

当前环境缺少 pytest，现有 Java 因缺少运行库不能启动，且无 javac；因此没有把包内历史通过记录称为本轮重新通过。

IMPLEMENTATION-NOTES 中早期条目保留历史范围说明；当前状态使用其后续更新、README 和最终 VALIDATION。早期设计的“尚未编码”“仅四案例”等进度不能覆盖0.2.1。

已知数值边界保留：正 PT 仍可能在浮点加法中被吞掉，使总占用区间归零。Python 在接受 Execution 前失败，原 Java 反例会发生重叠。该输入是明确差异边界，不是跨语言正常通过案例。

# 3 决策登记

| 决定 | 内容 | 状态 |
|---|---|---|
| D01 | 采用方案C，动态生成、固定输入和记录重放共存 | 已确认 |
| D02 | 动态正常统计采用明确命名的 java_legacy 口径 | 已确认 |
| D03 | completed_workflows 保存全部物理完成；另设统计集合 | 已确认 |
| D04 | 保留 Java 保护判定，首次触发后明确 FAILED，不模仿极大时钟和异常尾部 | 已确认 |
| D05 | random.Random，每上下文一条共享输入随机流 | 已确认 |
| D06 | reset、rerun、rotateSeed 保留 Java 的资源参数及 B 延续语义 | 已确认 |
| D07 | sampler 初始化后冻结，改参新建上下文 | 已确认 |
| D08 | 实数均匀保留拒零和 Java 式缩放；整数及指数使用已指定 Python 方法 | 已确认 |
| D09 | DAX 保序，非法及前向引用拒绝，无宽松丢边模式 | 已确认 |
| D10 | 动态 Task.id 使用 XML ID，Java 序号仅作映射 | 已确认 |
| D11 | 保留边映射，提供显式释放接口，输入记录独立保留 | 已确认 |
| D12 | 严格按 Java 两遍顺序、累计方式和候选公式生成 | 已确认 |
| D13 | 发布时间不推进时拒绝；不重抽、不回滚随机流、不立即终止其他设备 | 已确认 |
| D14 | 独立版本重放输入，支持旧固定 JSON 投影；输入与参考输出分离 | 已确认 |
| D15 | 重放输入不足明确失败，不补采样 | 已确认 |
| D16 | 分层配置；动态多次运行显式选择重复模式 | 已确认 |
| D17 | 公开有符号64位 seed，内部按无符号64位位模式编码 | 已确认 |
| D18 | 本稿提出的精确字段、接口名、错误码、数值上限、验收阈值 | 建议待确认 |
| D19 | 原动态调用链、边界行为及导出观察无干扰 | 待运行验证 |
| D20 | 原论文表格差异的勘误解释及正式实验参数 | 待验证，留后续实验阶段 |

源码已经能确定的行为不再当作选择题。运行验证状态与用户确认状态分别维护，不能因设计获得确认而将测试标记为通过。

# 4 模块职责与依赖

以下路径相对于 src/fogsim；新路径是建议命名。

| 模块 | 职责 | 与基线关系 |
|---|---|---|
| instances/fixed.py 与 spec.py | 旧固定格式和不可变固定描述 | 保留；必要时提取纯拓扑校验 |
| instances/dax.py 与 catalog.py | 纯拓扑解析、类型目录、来源哈希、不可变模板 | 新建 |
| instances/generated.py | 完整生成候选、边值、来源和尝试描述 | 新建，不复用会丢物理字段的旧序列化 |
| randomness/samplers.py 与 state.py | 参数化 sampler、共享 RNG、seed 编码和状态描述 | 新建 |
| environment/spec.py 与 build.py | 资源数值快照、按原顺序生成环境 | 新建 |
| simulation/context.py | 上下文生命周期、资源快照、共享 RNG、本轮 Engine | 新建 |
| simulation/sources.py | 固定、随机、记录驱动三种来源 | 新建 |
| simulation/state.py | 规范索引、生命周期、动态登记和物理完成 | 扩展 |
| simulation/statistics.py | G、B、设备工作流计数、统计资格及统计集合 | 新建 |
| simulation/engine.py 与 events.py | 来源钩子、停止策略及失败报告 | 局部扩展 |
| simulation/event_queue.py | 保留原操作；拆出归并和全局 poll 以对齐动态停止边界 | 局部扩展 |
| simulation/trace.py | 动态任务记录登记，保持观察不参与调度 | 扩展 |
| replay/spec.py、loader.py、source.py、export.py | 新重放格式、校验、固定投影及覆盖边界 | 新建 |
| validation | 固定比较器保留；新增生成与动态比较入口 | 扩展 |
| experiments | 显式重复策略、独立结果与汇总 | 新建 |
| config.py、cli.py、公共 API | 旧入口保留，新配置和子命令独立路由 | 扩展 |

依赖方向为：配置和不可变输入 → 环境与来源 → 集中接纳 → 规范运行状态 → 四事件 → 统计与结果。日志、输入归档和比较器只观察；规则视图没有 Context、RNG、完整来源记录或未来输入的回引用。

资源对象负责运行队列和占用，不承担随机生成、seed 轮换、实验汇总或工作流身份分配。

# 5 数据模型与对象身份

## 5.1 不可变描述

| 类型 | 关键字段和类型 | 默认或契约 |
|---|---|---|
| DagTaskSpec | xml_id 字符串，java_index 整数 | 顺序从0开始，保留解析后的 ID |
| DagTemplate | dag_type_id 可空整数，source_name 字符串，source_sha256 字符串，tasks 元组，dependencies 元组 | 不含随机值和运行对象 |
| EnvironmentSnapshot | devices 元组，servers 元组，参数来源及指纹 | 全部实际算力、带宽和执行开关；不含队列 |
| TaskInput | id，workload，data_size，total_input_data，total_output_data，options 元组 | 动态输入数值完整且有限 |
| EdgeInput | parent_id，child_id，data_size | 每条边一个正式采样值 |
| WorkflowInput | candidate_id，owner_device_id，template_ref，release_time，inter_release_time，weight，tasks，edges | 已完成两遍生成的完整候选 |
| GenerationCause | phase，owner_device_id，clock_time，causing_workflow_id，event_sequence | 初始化的 causing_workflow_id 和 event_sequence 为空 |
| GenerationAttempt | attempt_sequence，cause，workflow_input_ref，observed_acceptance，rejection_reason | 尝试序号独立于正式 Job ID |
| InputArchive | 模板、环境、完整候选与尝试、接纳 ID 对应关系 | 独立保存；不与待释放字典共享可变存储 |

完整候选和尝试可分两次完成观察记录：生成数值先复制，接纳返回后补充观察结果；发布为可重放输入前必须形成完整、不可变记录。边列表按明确顺序保存，不能用无序集合代替。

## 5.2 运行模型

既有字段不重排。新可选字段放在原字段之后，旧构造调用保持兼容。

| 对象 | 字段 | 类型与初始值 |
|---|---|---|
| Workflow | id、owner_device、release_time、tasks | 沿用现有类型和身份 |
| Workflow | weight | 固定未知为 None；动态为正有限数 |
| Workflow | dag_type_id、template_hash、input_record_id | 可空；固定旧输入为空 |
| Workflow | completion_time、completed_executions、completion_registered | 沿用 None、空列表、False |
| Task | id、workflow、parents、children、options | id为字符串；引用本轮规范对象 |
| Task | workload、data_size、total_input_data、total_output_data | 固定未知为 None；动态完整填充 |
| Task | input_data_by_parent、output_data_by_child | 字符串键字典或 None |
| Task | edge_data_state | UNAVAILABLE、RETAINED、RELEASED；旧固定默认 UNAVAILABLE |
| Task | dispatched、completed | 初始 False |
| TaskOption | task、resource、processing_time、upload_time、download_time | 原字段；动态数值由输入建立 |
| TaskOption | ready_time、priority | 初始0.0，保留原更新时间 |
| Resource | processing_rate | 固定未知为 None；动态为正有限数 |
| Server | upload_bandwidth、download_bandwidth | 固定未知为 None；动态为正有限数 |
| Resource | available_time、队列、缓存、完成任务数、pending_start | 原初值和语义保留 |
| Execution | option、start_time、compute_finish_time、finish_time | 原不可变模型与数值校验保留 |

edge_data_state 的不变量：UNAVAILABLE 时两映射为 None；RETAINED 时两映射存在，天然无边用空字典；RELEASED 时两映射为 None，但总量和完整独立输入记录仍存在。输入访问器对 UNAVAILABLE 和 RELEASED 分别给出明确错误，不把它们解释为0数据。

Task 与 Workflow 不持有完整 Context、InputArchive 或类型目录的回引用。来源标识仅为字符串或整数；需要清理或导出时由拥有归档的服务查找。这也防止规则通过可达对象访问未来输入。

## 5.3 身份和编号

DAG 类型编号表示模板类别，不能作为工作流 ID。动态 Job ID 取接纳前 G，成功后才增加 G；拒绝尝试不占正式 ID。固定输入原 ID 不重编号。

动态 Task.id 为 XML ID；Java 编号按模板任务位置保存。禁止解析 ID 数字后缀、按字符串排序或为运行新加任务平分键。Task.key 继续为工作流 ID 与任务 ID；Option.key 再加资源字符串 ID。

默认设备名 M0起、边缘 E0起、云 C0起。设备数值编号独立从0开始；服务器数值编号先边缘再云。字符串后缀不是数值编号的解析依据。固定输入的自定义 ID 及输入顺序保留。

同一轮同一键只有一个规范对象。跨工作流同名任务合法；跨轮同键代表新对象。外层 run_index 区分运行，不进入调度键或平分逻辑。

模板引用由类型编号与内容哈希共同标识；edges按第一遍实际采样顺序保存，模板dependencies按XML边出现顺序保存。它们可以不同；建图和输入累计必须使用模板对应的邻接顺序，不按边值数组顺序替代。

# 6 状态归属与不变量

| 权威位置 | 管理内容 |
|---|---|
| SimulationContext | 有效配置、EnvironmentSnapshot、冻结 sampler、共享 RNG、当前公开 seed、当前运行引用 |
| SystemState | clock_time、资源和工作流索引、任务索引、pending、active、全部物理完成集合、执行索引 |
| RunStatistics | G、各设备接纳和物理完成计数、B、统计完成集合、设备统计完成计数、全局非记录事件计数 |
| Resource | 等待队列、缓存、available_time、pending_start、实际执行完成任务数 |
| Workflow | 任务列表、完成执行记录、完成时间和物理完成登记标记 |
| InputArchive 与来源 | 完整生成输入、尝试序号、记录读取位置 |
| EventQueue | 全局堆、设备暂存堆及事件生产设备关联 |
| TraceRecorder | 任务事实快照、事件、决策和实际动作序列 |

RunStatistics.recorded_workflows 是独立有序字典，成员引用 SystemState.completed_workflows 中的同一 Workflow。正常登记顺序是完成顺序；不按 ID 重排。R 由设备统计计数求和，且等于统计集合大小。

B 在当前 RunStatistics 中只有一份可变权威值。准备下一轮时从上一轮读取 B，传入新统计对象；上下文不另维护同时变化的 B 副本。其他本轮计数和集合清零。

事件边界至少检查：

- pending、active、completed 互斥，覆盖全部成功接纳工作流。
- G 等于成功接纳索引大小，也等于各设备生成数之和。
- 统计完成集合是物理完成集合的子集；每设备统计数和物理完成数与所属工作流一致。
- 0 ≤ R ≤ 物理完成数 ≤ 实际到达数 ≤ G。
- 每任务至多一次派发、一次正式 Execution 和一次完成记录；完成蕴含派发。
- 每资源最多一个 pending_start；预约与待触发 Start 一一对应。
- 资源占用区间严格为正且不重叠；旧 Finish 不破坏其他预约。
- 队列、缓存、父子引用和执行索引满足0.2.1原有不变量。
- 记录、输入归档、任务及资源之间没有跨轮可变对象引用。

Java jobsInSystem 的成员范围对应 pending与active，但其生成插入顺序不能用两个容器简单拼接代替。若需比较该列表，按接纳顺序重建可比视图。规则仍只获得已经到达的 active与completed；G、B 的统计需求不通过放宽未来可见性实现。

# 7 DAX 目录与解析契约

## 7.1 标准类型目录

| 编号 | 文件 | 实际任务数 |
|---:|---|---:|
| 0 | CyberShake_30.xml | 30 |
| 1 | Epigenomics_24.xml | 24 |
| 2 | Inspiral_30.xml | 30 |
| 3 | Montage_25.xml | 25 |
| 4 | Sipht_30.xml | 29 |
| 5 | CyberShake_50.xml | 50 |
| 6 | Epigenomics_46.xml | 47 |
| 7 | Inspiral_50.xml | 50 |
| 8 | Montage_50.xml | 50 |
| 9 | Sipht_60.xml | 58 |
| 10 | CyberShake_100.xml | 100 |
| 11 | Epigenomics_100.xml | 100 |
| 12 | Inspiral_100.xml | 100 |
| 13 | Montage_100.xml | 100 |
| 14 | Sipht_100.xml | 97 |
| 15 | CyberShake_1000.xml | 1000 |
| 16 | Epigenomics_997.xml | 997 |
| 17 | Inspiral_1000.xml | 1000 |
| 18 | Montage_1000.xml | 1000 |
| 19 | Sipht_1000.xml | 968 |

目录保存相对文件名。dag_root 相对配置文件目录解析；不依赖启动时 cwd。HEFT_paper.xml 和 floodplain.xml 可以由纯解析器读取，但不自动分配新的标准类型编号。文件名、jobCount 和 childCount 不决定实际建图。

## 7.2 解析流程

使用标准库 XML 解析能力处理本项目子集。根本地名要求 adag。结构标签按本地名转小写识别，ID与ref不转小写。支持空命名空间和 http://pegasus.isi.edu/schema/DAX；结构元素命名空间应与根一致，前缀可不同。不联网读取 schemaLocation，不进行完整 XSD 校验。

按根直属元素顺序处理 job和child。job要求非空白且唯一的id，编号取出现位置；其他任务属性及内部 uses 信息不参与拓扑或随机参数。child要求有效ref，直接子元素必须为parent并提供ref；parent不允许嵌套结构。引用必须指向此前已经定义的job。根直属其他结构元素在本阶段明确报不支持，XML注释不作为结构节点。

每次出现 parent→child 就按当前顺序追加依赖；保留每个任务的 parents和children顺序。重复ID、重复边、自环、未知或前向引用、空工作流、循环依赖均失败。允许无边、多入口、多出口和不连通但无环的工作流。

拓扑检查只校验，不重排任务或依赖；不添加虚拟节点。ID保留XML解析后的属性值，不额外trim、数字化或按后缀排序。

声明数量不一致仅产生诊断。随附 HEFT_paper.xml 的实际任务数为10，jobCount声明25，实际child块9而声明20；原Java忽略这些声明。标准20文件的实际图规模以本表为准。

## 7.3 初始化冻结

创建上下文前加载抽样范围的所有模板并校验，失败不开始采样。模板、目录和来源哈希在上下文中固定；每工作流依据模板创建独立运行图。reset、rerun、rotateSeed 复用模板；修改文件或配置须新建上下文。

这是相对于Java每次生成重新读XML的结构差异。对内容不变的有效文件，加载本身不推进RNG；顺序和数值一致性仍需运行验证。

错误包含路径、元素序号、相关id/ref和错误类型，不返回部分模板。

# 8 随机流与采样器

## 8.1 seed

公开seed必须是真整数，范围为有符号64位；拒绝bool、浮点、字符串和越界值。内部rng_seed为seed模2的64次方；使用random.Random(rng_seed)。记录编码版本 signed64-bits-v1。0仍为0，负1映射为18446744073709551615。

rotateSeed先按Java long的64位回绕规则加10000，再执行编码。reset的可空参数None只表示使用当前保存的公开seed，不能传给random.seed(None)而引入时间或系统随机性。

本轮当前Python检查显示直接传入1与负1起始状态相同；上述编码避免这种符号归一化情况。它不承诺任意seed序列互不相关。

## 8.2 共享与冻结

每上下文只持有一条输入随机流，环境与全部设备共同推进。各sampler仅保存参数，采样时接收RNG。构造、校验、复制和日志不抽数；复制sampler按参数重建，不复制或重设RNG。各上下文sampler对象独立；同上下文同角色共享。上下行是两个业务角色，不合并一次采样。

先解析请求配置、执行兼容规则、校验并冻结有效参数，再采样环境。当前兼容profile的到达间隔为指数mean100；该值在有效配置中明确保存。本稿建议该profile不开放其他到达mean，显式冲突值报配置错误。其他已支持范围可在新上下文调整。

## 8.3 算法

| 分布 | Python契约 | 底层推进 |
|---|---|---|
| 实数均匀 | a与b有限且a小于b；random()取u，拒绝0；按u×b加(1减u)×a计算 | 通常一次，拒零时增加 |
| 整数均匀 | randint(a,b)，两端包含；允许a等于b，仍调用randint | 位采样内部可变 |
| 指数 | expovariate(1/mean)，mean正且有限 | 当前参考Python每次一次random() |
| 权重 | 开区间单位u；小于0.2为4，小于0.8为2，否则1 | 通常一次，拒零时增加 |
| 云带宽 | 相同阈值，依次256、512、128 | 通常一次，拒零时增加 |
| 边缘带宽 | 固定1024 | 不推进 |

实数均匀名义支持开区间，但浮点缩放可能舍入到端点；不对缩放结果钳制或再抽。整数单点不能优化成不抽数的常量。指数可返回0，不补epsilon，不在sampler自动重抽；工作流接纳按后文执行。

Java的指数采样实际字节码含循环和额外nextDouble调用，Python不移植该内部算法。业务调用顺序保留，底层消耗及随机值不同明确允许。构造和复制不抽数属于可单独验证契约。

## 8.4 标准参数与单位

workload实数均匀5000至15000；基础data为5120至20480；边数据100至200；设备算力125至250；边缘250至500；云500至1000。范围作为前述实数均匀参数。权重1、2、4对应20%、60%、20%；云带宽128、256、512对应20%、20%、60%；边缘上下行各1024。

时间沿用s。工作量及数据采用模型单位，算力为工作量单位每秒，带宽为数据单位每秒；不擅称MI、KB或MB，不添加8或1024换算。单位标识属于本稿具体化建议，数值与Java保持直接对应。

同配置和seed的新建上下文可复现，还要求代码、Python版本、数据内容和操作序列相同。旧上下文的seed不足以标识整个运行，必须保留环境及初始B等状态。跨环境复现以实际输入记录为主要依据。

# 9 环境初始化与工作流生成

## 9.1 新环境顺序

先按设备顺序各采一次设备算力，即使禁用本地执行也不能跳过。再按边缘服务器顺序调用上行、下行、算力sampler；再按云服务器顺序调用同三项。边缘带宽调用保留但不推进RNG。全部资源数值建立后，按设备顺序各尝试生成一个工作流。

运行对象的可用时间和缓存为0、队列为空、预约为空；本轮时钟0。服务器对象全局共享，不能为每个设备复制一套。

## 9.2 一次完整生成尝试

1. 采样工作流类型，取得冻结模板并保持其顺序。
2. 采样间隔delta，按当前clock加delta计算release。
3. 采样权重。
4. 第一遍按任务顺序：workload、基础data，然后按children顺序逐条采边数据，逐项累计输出总量。
5. 第二遍按任务顺序：按parents顺序读取已采边值，逐项累计输入总量，再创建本地和服务器候选。
6. 拟用Job ID取当前G；完整输入与尝试记录建立独立副本。
7. 执行接纳检查；成功后发布规范对象并安排Arrival；拒绝则只保留尝试记录。

不能因release已经不推进，就提前跳过后续任务采样。Java的检查在完整生成后发生。默认保留边映射；可选清理只在整个第二遍完成且完整输入独立保存后执行。

## 9.3 数据与候选公式

输入总量只累计入边，输出总量只累计出边，均不包含基础data。累计从0.0开始按邻接顺序逐项加，不改用排序、fsum或向量归约。每边只采一次，父输出与子输入引用同一个数值事实。

| 候选 | PT | UT | DT |
|---|---|---|---|
| 所属设备 | workload除以设备算力 | 0 | 0 |
| 任一边缘或云服务器 | workload除以服务器算力 | (基础data加总输入)除以上行带宽 | (基础data加总输出)除以下行带宽 |

候选顺序为合法本地、边缘、云；各类型内部保留资源顺序。其他移动设备不是候选。无父或无子时仍可能传输基础data。同服务器父子任务仍按原UT和DT执行，不引入通信复用。

## 9.4 接纳与拒绝

有限release严格大于clock才接纳。成功后：创建并登记完整运行图；加入pending及必要任务事实记录；G和所属设备生成数增加；用增加后的G更新B；Arrival进入当前生成设备暂存堆。

release不大于clock时，记录REJECTED_RELEASE_NOT_FUTURE：不正式登记、不占Job ID、不增加G或设备接纳数、不更新B、不发Arrival、不重抽、不回滚RNG。已进入系统的工作流继续运行，其他设备不立即中断。在当前标准到达链中，该设备不再有后续生成触发点；此控制流后果待Java运行验证。

非有限release或非法派生时长是领域失败，不归类为普通拒绝。原始delta与release都保存，不能用两时间相减倒算采样值。

## 9.5 数值保护

动态workload及算力、带宽必须正且有限；基础及边数据非负有限；PT必须正有限，UT和DT非负有限。除法和加法结果提交前检查。预约时继续要求(start加PT)加DT严格大于start，保留原括号，不取整、不补epsilon。

新动态计数使用Java可比范围：N为正整数，W非负；N加W不超过floor(2147483647除以500)，避免原保护阈值表达式溢出。设备和服务器计数在int32内，边缘加云的编号空间也在范围内。接纳后的G必须仍在int32范围；拒绝尝试不执行G加一。超界明确失败，不复现Java整数回绕。这些是建议待确认的Python边界保护，旧固定输入范围不因此改变。

W为0允许，用于复现已知边界。新环境N为1且W为0时，B保持0而正常接纳release均正，统计目标不可达；不自动修正配置，专门测试其失败结束。

# 10 动态来源与四事件接入

来源接口有initialize和after_arrival两个调用位置；随机来源内部只推进RNG和输入记录，不自行写系统索引或事件堆。集中接纳服务拥有正式登记权。

| 来源 | initialize | after_arrival |
|---|---|---|
| 固定 | 按旧规则建立全部固定工作流并stage到达 | 无操作 |
| 随机 | 每设备一次完整尝试 | 当前工作流所属设备一次完整尝试 |
| 记录重放 | 按录制的初始化尝试提供输入 | 在对应调用位置提供下一条记录 |

Arrival先激活，再按原顺序设置入口候选ready_time、路由并派发全部Visit，然后调用after_arrival。不能在各入口之间生成。下一工作流不等前一工作流完成；Finish不生成工作流；不随机换设备；G达到N加W不截断生成。

Visit、Start、Finish保留已验证的队列、预约和两轮后继路由。物理完成登记返回首次成功时，才调用统计登记，避免重复增加计数。

所有新事件经过stage，不内联trigger。事件owner是任务所属设备，staging device是产生事件的当前设备；服务器队列续接可能使二者不同。共享资源排队和比较器不因来源不同而改写。

TraceRecorder新增register_workflow能力，在正式登记时建立任务事实行；即使trace关闭也必须建立。events.actions继续表示实际DECISION和EMIT，生成记录独立保存并关联事件序号与阶段。动态Arrival会实际多发下一Arrival的EMIT。

固定路径继续使用原pop_next。动态循环可将原归并提取为merge_staging，再使用poll_global：每次循环先按设备顺序排空暂存堆，随后检查统计目标，再判断事件耗尽和额外预算，最后poll一条。不能调用两次归并或更改offer/poll顺序。这样对齐Java循环条件在检查R之前已经归并的边界。

即使只有一个设备，也运行DynamicSimulation对应的全局路径，不回退Java MobileDevice.run的其他阈值分支。当前标准路径不调用被注释的设备选择sampler。

# 11 统计与停止

## 11.1 Java兼容字段

| Java名称 | 本设计名称 | 含义 |
|---|---|---|
| allNumJobsReleased | generated_total即G | 成功生成并接纳数量，含未来工作流 |
| 设备numJobsReleased | generated_by_device | 设备接纳数量 |
| 设备numJobsCompleted | completed_by_device | 所属工作流物理完成数量 |
| 设备throughput | recorded_by_device | 完成时符合筛选的数量 |
| getCurrentCompletedJobsNum | recorded_total即R | 设备统计数之和 |
| firstArriveJobRecordedTime | cutoff_release_time即B | 按生成登记更新的时间边界 |
| jobsCompleted | recorded_workflows | 统计入选工作流集合 |

DynamicSimulation.numJobReleased没有实际承担全局生成计数，不移植成另一份G。

## 11.2 更新规则

新环境B初始0；兼容重置保留旧B。接纳后若G严格小于N加W，则B直接赋为当前新工作流release，不取最大值。多设备下B可能减小。

工作流物理完成后，所属设备物理完成数加一。使用完成当时的G与B判断：G大于W、Job ID非负、release不晚于B；全满足才增加设备统计数并追加统计集合。资格只判一次；未入选的完成工作流不随B变化补录。

completion_registered表示物理完成登记，不表示统计入选。早期ID工作流可以入选；不增加ID至少为W或小于N加W等源码没有的条件。

## 11.3 正常指标和停止

R达到N时正常停止，当前事件必须已完整处理，随后执行下一次循环的归并观察边界；不处理剩余同刻事件、不排空系统。pending和active可以非空。

makespan取统计集合最大completion减最小release；mean_flow_time按统计登记顺序逐项累计各completion减release，再除集合大小。B不作为makespan起点。固定模式仍使用全部输入，全部完成才成功。

Java记录不足时的正无穷及Double.MAX_VALUE只保存在参考输出的原生返回描述中；Python正式失败指标为空。不要以成功子集的局部makespan填充正式失败指标。

工作流weight按输入保存，当前makespan与mean_flow_time不加权，FCFS也不因weight改变评分。

# 12 异常终止与结果

## 12.1 原保护判定

每条事件完整处理后，先计算R变化。R大于W且本事件R不增加时，全局legacy_nonrecording_events加一。它不是连续停滞计数；设备completeJob清零的同名字段不等于全局计数，不能据此重设全局值。

然后按原顺序检查：

1. 全局计数严格大于400000。
2. 允许本地执行的设备，等待队列严格大于400。
3. 任一服务器等待队列严格大于400。
4. G严格大于500乘(N加W)。

只在原事件后位置检查这些保护，不把它们提前当作setup后的配置条件。多项同时触发时按原检查及资源顺序确定主原因，同时保存其他命中条件。

## 12.2 Python明确失败

首次命中保护后停止，不写极大时钟、不清除诊断队列后再继续。当前实际事件时间保留；正式指标为空。即使同一事件已使R达标，后续保护命中也按失败报告，这是已确认的原Java差异。

事件耗尽而R不足为失败；重放输入不足为另一独立失败。额外事件预算只在目标未达、下一条事件poll前检查，标注为Python运行限制。配置错误不进入模拟；领域错误保留诊断；未知程序异常原样传播，禁止吞为成功或普通惩罚。

## 12.3 动态结果字段

| 字段 | 契约 |
|---|---|
| status | SUCCEEDED或FAILED |
| reason与reason_code | 可读原因及稳定机器码；成功为空 |
| final_clock_time | 最后实际处理时刻；setup阶段失败为当前时钟0 |
| generated_workflow_count | 成功接纳数G |
| arrived_workflow_count | 实际Arrival激活数 |
| completed_workflow_count | 全部物理完成数 |
| recorded_workflow_count | 统计入选数R |
| processed_event_count | 实际处理事件数 |
| makespan与mean_flow_time | 正常统计目标达成且无失败时才有正式值 |
| workflow_records | 按接纳顺序列全部工作流，含统计入选标记和实际完成值 |
| task_records | 保留计划与实际时间区分，未发生的实际时间为空 |
| device_statistics | 按设备顺序列工作流生成、物理完成和统计完成数 |
| source_summary | 尝试数、拒绝数、消费位置和覆盖状态 |
| events与decisions | 详细trace关闭时为空，必要事实仍保留 |

compute_finish_time仍仅由实际Start加PT派生，不是第五类事件或已观测计算完成的证明。预先知道的计划finish不能填入实际finish。

建议错误码包括：EVENTS_EXHAUSTED_BEFORE_TARGET、JAVA_NONRECORDING_EVENT_LIMIT、JAVA_DEVICE_QUEUE_LIMIT、JAVA_SERVER_QUEUE_LIMIT、JAVA_GENERATED_JOB_LIMIT、MAX_EVENTS_EXCEEDED、REPLAY_INPUT_EXHAUSTED、REPLAY_INPUT_DIVERGENCE、NUMERIC_DERIVATION_ERROR、STATE_INVARIANT_VIOLATION。输入或调用错误使用InputError与EngineUsageError，不伪造运行成功。

# 13 生命周期

| 操作 | 环境数值 | 输入RNG | B | 首批工作流 | 是否run |
|---|---|---|---|---|---|
| 新建上下文 | 新采样 | 编码seed后先采环境 | 0 | 按设备顺序生成 | 否 |
| reset(seed) | 保留 | 重设到编码seed的起点 | 保留 | 重新生成 | 否 |
| reset() | 保留 | 使用当前公开seed重设 | 保留 | 重新生成 | 否 |
| rerun() | 保留 | 继续当前状态 | 保留 | 重新生成 | 是 |
| rotate_seed() | 保留 | 公开seed回绕加10000后重设 | 保留 | 重新生成 | 否 |
| 同输入重放 | 使用记录 | 不采样 | 使用记录起点 | 按来源记录提供 | 按调用入口 |

每轮重建Resource、Workflow、Task、TaskOption、SystemState、统计对象、Engine、队列、执行索引和日志。保留的资源参数是数值快照，不能共享上一轮资源对象。sampler有效参数保留。

新建环境先消耗资源采样；reset不消耗该前缀。因此构造首轮与reset后首轮不要求相同。从头重复实验要新建上下文；同输入复跑用记录重放。旧上下文同seed并不单独保证整个实验相同，初始B及保留环境也要一致。

上下文保留当前失败轮的RNG和B，允许按所选生命周期开始下一轮。由于已确认的失败策略提前停止，失败后rerun的起点不承诺等于原Java异常尾部之后的起点。

本阶段只支持轮次边界的原生RNG状态保存，记录getstate版本及Python版本；不承诺任意运行中检查点恢复。哈希用于核对，不能代替实际状态或完整输入。

# 14 边数据释放

默认保留RETAINED状态。编码阶段必须提供工作流级release_edge_data(workflow, archive)能力，完成复现验证后可显式启用，不只留下未来TODO。

前置条件：整个工作流两遍生成与全部选项已完成；完整输入有独立归档；当前调度及校验不依赖运行时边映射。必须在清理前一次核验全工作流，不能边处理父任务边提前清空输出映射。

只释放input_data_by_parent与output_data_by_child，设为None并标RELEASED；保留workload、data_size、两个总量、UT/PT/DT、身份、拓扑和完成记录。输入归档不变，不与运行字典共享可变引用。旧固定UNAVAILABLE对象跳过；重复释放幂等，不重复计数。

返回CleanupReport，含首次释放任务数、移除映射条目数和状态；映射条目数不是独立边数，一条边通常在两端各一条。访问已释放映射通过明确错误报告，不能当作无依赖或0。

清理不推进RNG、时钟或事件，不加入第五类事件。清理开关不得改变相同输入下的候选、轨迹、完成或统计结果；独立归档仍能重放。内存和执行时间收益须测量峰值及耗时，不能因调用成功就宣称加速。

本阶段不整体回收已完成Workflow、Task或Execution图；它们仍服务于不变量和完整结果。边映射释放只减少这一层副本，不能据此推断输入归档和轨迹占用也已消失。

这里的完整归档指该工作流候选输入已经完整保存，不要求整轮运行结束或capture.complete已为True。复现验收前默认retain，release模式先用于专门等价测试，验收后才作为显式运行选项启用。

# 15 动态输入记录与重放格式

## 15.1 文件分层

新增自包含input.json，format为fogsim.dynamic-replay，schema_version为1。reference.json独立保存期望轨迹和原生结果；manifest.json保存输入、参考及来源文件哈希，不包含自身循环哈希。旧固定JSON不增加必需字段。

input.json单独足以执行，无需Java、原XML或reference文件。原始数据不由参考输出补齐。完整复核另要求reference及相应清单存在。新格式未知版本和未知结构字段报错；诊断信息使用明确diagnostics对象，不允许任意顶层键。

## 15.2 输入结构

| 字段 | 类型 | 契约 |
|---|---|---|
| format、schema_version | 字符串、整数 | 精确匹配已支持版本 |
| origin | 对象 | 语言、实现版本、代码及依赖指纹、规则身份、运行操作 |
| initial_state | 对象 | 初始B、公开seed、编码版本、运行序号；计数从0开始 |
| effective_config | 对象 | 当前统计、异常、事件和预算等有效条件 |
| units | 对象 | s及模型工作量、数据单位 |
| environment | 对象 | 有序设备和服务器及全部实际数值 |
| templates | 有序记录集合 | 自包含拓扑、原ID与Java序号及来源哈希 |
| candidates | 有序记录集合 | 唯一record_id及完整WorkflowInput，拒绝者也保留 |
| generation_attempts | 数组 | 严格全局尝试顺序 |
| capture | 对象 | complete布尔值、完整尝试数量、是否发生写出或进程中断 |

Python归一化后的seed可保存为rng_seed_decimal十进制字符串，避免经过浮点数；公开seed按有符号64位整数精确读取。Java来源不要求存在Python原生RNG状态。

attempt包括attempt_sequence、phase、owner_device_id、generation_clock_time、causing_workflow_id、诊断event_sequence、candidate_ref、observed_acceptance、rejection_reason。正式Job ID只要求成功接纳者唯一；拒绝者的candidate_id可以重复。

记录原始间隔和加法后的release。所有输入数值有限，禁止NaN或Infinity字面量，不截断小数；加载必须恢复原binary64数值。累计和UT/PT/DT都保存，主调度重放使用已导出的时长；另行审计公式，不静默重算并覆盖。

capture.complete只表示本轮捕获完整，不表示无限输入流。原停止时间、完成ID集合和最终指标放reference；不作为来源强制执行条件。

## 15.3 Java观察位置

类型和任务顺序需能恢复原XML映射。在整个第二遍完成、mapClear之前复制完整边和任务参数；addJobToSystem返回后补接纳观察。记录初始化尝试和所有Arrival内尝试，包括拒绝、未到达及未完成工作流。

导出工具以单独入口和明确观察改动执行原动态路径，保留原源文件字节及构建指纹。已有固定适配器跳过随机和训练统计，不能冒充原动态导出器。观察器不调用额外sampler、不替换比较器或调度方法；完整输出与最小观察模式需验证输入及调度不受影响。

## 15.4 消费规则

来源每次被调用只读取下一条全局attempt，检查phase、设备、触发工作流、生成时钟和拟用ID；不向后搜索匹配，不按设备重组，不依据录制事件序号调度。Python重新执行release大于clock判定，再比较observed_acceptance。

需要下一输入而记录用尽时，REPLAY_INPUT_EXHAUSTED；不补采样、不循环复用、不伪造空工作流。若没有生成调用而事件已耗尽、目标未达，报告EVENTS_EXHAUSTED_BEFORE_TARGET。捕获不完整不能用于完整验收。

复核原规则时比较消费位置及参考结果。换规则后提前正常结束可以有未消费记录；需要更多输入则说明覆盖不足，不直接断言调度错误。verify_reference模式禁止改变行为配置；reuse_inputs可显式改为当前支持的规则，标记新实验并关闭原轨迹通过结论。本阶段reuse_inputs不改变来源、N/W及输入环境。

## 15.5 固定投影

仅选择成功接纳记录，保留接纳顺序、资源顺序、工作流ID、原任务顺序、依赖顺序和实际候选时长，展开成原InstanceSpec。拒绝尝试、生成时点和统计窗口不进入旧格式，清单明确标注fixed_projection。

两侧固定入口必须使用同一投影执行到完成。结果不能直接比较原动态运行的最终指标。现有固定Java入口仍只支持FCFS和固定资源规则，并使用不被这些规则读取的物理参数占位，不能用于声称GP或真实物理字段已对照。

phase取initialize或after_arrival，attempt_sequence从1连续增加，初始化clock为0且causing_workflow_id为空；after_arrival关联当前工作流。record_id使用本轮尝试序号的稳定字符串表示，由外层run_index分隔轮次。任何参考输出字段都不进入来源的行为决策。

新格式中devices、servers、templates、candidates、generation_attempts均为有序数组。templates按类型编号保存，candidates与attempts按尝试顺序保存；每条完整attempt对应一个唯一candidate记录，capture.complete为True时不允许缺失或孤立引用。模板依赖与候选边数据通过父子ID关联，不靠数组位置猜测。

# 16 配置与数值边界

新增配置format为fogsim.experiment，schema_version为1，mode为dynamic或replay。旧配置继续由旧load_config处理；未知模式不猜测、不回退。

| 配置项 | 类型 | 默认与要求 |
|---|---|---|
| source.seed | 真整数 | dynamic非列表模式必填，有符号64位；列表模式见下文 |
| source.dag_root | 路径字符串 | dynamic必填，相对配置文件 |
| source.workflow_types.lower、upper | 整数 | dynamic必填，0至19且lower不大于upper |
| source.environment.num_mobile_devices | 整数 | 必填，至少1 |
| num_edge_servers、num_cloud_servers | 整数 | 必填，非负 |
| can_mobile_devices_process_tasks | 布尔 | 必填，标准来源统一开关 |
| source.samplers | 对象 | 可省略支持的范围；按标准值展开 |
| run.num_jobs_recorded、warmup_jobs | 整数 | dynamic必填，N正、W非负 |
| run.statistics_policy | 字符串 | java_legacy |
| run.failure_policy | 字符串 | explicit_failure |
| run.event_policy | 字符串 | java_compatible |
| run.routing_rule | 对象 | fcfs；或合法fixed_resource目标 |
| run.sequencing_rule | 对象 | fcfs |
| run.max_events | 正整数或空 | 新模式默认空；旧固定仍100000 |
| run.check_invariants | 布尔 | True |
| run.trace_enabled | 布尔 | True |
| run.edge_data_policy | 字符串 | retain；可显式release_after_materialization |
| repeat.count | 正整数 | 1 |
| repeat.mode | 字符串 | dynamic count大于1必须显式给出 |
| repeat.seeds | 有符号64位整数数组 | fresh_seed_list必填，长度等于count，其他模式禁止 |
| output.dataset_role | 字符串 | debug；可显式train或test作为数据标识 |

标准动态来源只支持前文已核定的分布家族与固定阈值；当前可调整的范围为workload、基础data、边data、三类算力及类型上下界。其他分布替换在本阶段报不支持。到达mean100、权重和带宽分布完整记录为有效参数，不隐藏覆盖冲突配置。

replay的source必须给input_path；verify_reference还给reference_path。环境、初始B和行为配置默认来自记录；run只开放trace、额外预算及清理等不更改输入的诊断选项。更换支持的规则需显式purpose为reuse_inputs。重放不接受seed覆盖来重新生成输入。

配置内路径相对配置文件目录；直接CLI路径相对cwd。相对路径解析后保存为有效路径，但重放执行不依赖原路径存在。重复JSON键、未知字段、bool冒充数值、非有限数、非法范围和无合法候选在采样前拒绝。

实数均匀范围要求严格lower小于upper；算力下界必须正，data下界非负。单点整数范围合法。禁用全部本地计算且服务器数为0不合法。固定资源路由目标须对所有可能产生工作流的设备合法，不能依赖某个设备恰好拒绝生成才变得合法。

新数值上限见生成章节；公开seed采用回绕编码，而工作流计数不采用回绕。两者规则不同，必须分别测试和记录。

fresh_seed_list可省略source.seed，单轮有效seed由repeat.seeds明确提供；若同时给source.seed，必须等于列表首项，避免未使用的冲突值。程序化配置使用绝对路径或显式base_dir，加载后有效路径固定。

# 17 API与CLI契约

## 17.1 保留接口

load_fixed_instance、parse_instance、InstanceSpec、RunConfig、create_engine、simulate保持原固定语义；Engine.run仍只执行一次。旧结果结构不增加必需字段，旧固定repeat输出和identical判断保持。

## 17.2 新接口建议

| 接口 | 输入与输出 | 主要副作用 |
|---|---|---|
| load_experiment_config(path) | ExperimentConfig | 只读取、校验和归一化，不抽数 |
| parse_dax(path) | DagTemplate | 只解析，不建立运行Task |
| load_dax_catalog(config) | DagCatalog | 校验全部候选模板并冻结，不抽数 |
| create_dynamic_context(config) | SimulationContext及首个READY Engine | 新建RNG、采环境、准备首批输入 |
| context.run() | RunResult | 运行当前READY Engine一次 |
| context.reset(seed可省略) | 新READY Engine | 重新设种、保留环境和B、准备首批输入 |
| context.rerun() | RunResult | 继续流准备新Engine并运行 |
| context.rotate_seed() | 新READY Engine | 回绕加10000后按reset准备，不自动run |
| simulate_dynamic(config) | RunResult | 新上下文的一次完整运行 |
| load_replay_input(path) | ReplayInput | 完整性、版本、映射和数值校验 |
| create_replay_engine(input, options) | READY Engine | 按录制初始化提供输入，不采样 |
| simulate_replay(input, options) | RunResult及可选比较报告 | 重放一次 |
| export_fixed_instance(input) | InstanceSpec | 生成旧固定投影 |
| release_edge_data(workflow, archive) | CleanupReport | 满足前置条件后释放运行副本 |
| run_experiment(config) | ExperimentResult | 按显式重复模式组织多轮 |

接口命名是本稿建议待确认。生命周期和顺序已经确认，不因API命名调整而改变。

配置及文件错误抛InputError。创建或reset在准备阶段遇到派生数值等领域错误时抛PreparationError，携带FAILED部分结果；context保留可诊断的失败轮。simulate_dynamic、simulate_replay和run_experiment的便利入口将这类准备失败归一化为FAILED结果。rerun同样返回准备失败结果。未知程序异常不包装成PreparationError，原样传播。直接创建接口的调用方不应在准备失败后调用旧Engine.run。

运行来源在内部使用GenerationCause和完整候选；集中admit入口负责索引、任务事实、G/B及Arrival，来源不能分别修改它们。来源输入记录不读取参考路由、完成或停止结果。

## 17.3 命令路径

旧 fogsim --instance 和 fogsim --config继续处理旧格式。新子命令为dynamic、replay、export-fixed；新配置由对应子命令显式选择，避免旧--config悄然改变含义。

新命令允许显式覆盖seed仅用于dynamic；重放不重新设种。no-trace只关闭详细事件和决策；必要事实和输入记录仍保留。所有覆盖在创建上下文前完成，并写入有效配置。

退出码沿用0成功、1运行或批次包含失败、2输入或调用错误。程序异常传播并导致非零退出，不能留下可误读的旧成功文件；若保存中断诊断必须标capture或batch不完整。旧入口的已有行为以回归测试保持。

create_dynamic_context接受已经展开的单轮动态配置，必须包含一个有效seed；run_experiment负责将列表策略展开为单轮配置。重放多轮的来源位置每次独立重置，不消费上一轮剩余记录。

内部admit接口返回AdmissionResult，至少包含accepted、workflow或空、reason_code；拒绝是正常返回值，不抛领域异常。来源生成异常和接纳拒绝必须区分。任务事实登记在正式发布前准备完整，事件边界检查索引和统计一致性；失败诊断不用于继续调度。

# 18 重复实验与汇总

| 模式 | 第一次 | 后续 | 解释 |
|---|---|---|---|
| fresh_same_seed | 新建上下文并run | 相同配置及seed新建上下文 | 可重复性核对，不算独立随机重复 |
| fresh_seed_list | 列表首seed新建并run | 对应seed各自新建 | 环境和工作流均重新采样 |
| java_rerun | 新建上下文并run | 同上下文rerun | 环境不变，流及B延续 |

count大于1缺模式，在任何采样前InputError。seed列表必须完整且长度等于count；不暗中使用seed加序号，不自动执行rotate_seed。count为1表示一次新建运行。

固定及记录重放的repeat继续表示相同输入、新对象；重放每轮读取位置重置到输入起点。上下文在批次结束后不自动reset，避免多消耗下一批首工作流随机数；调用方需要时显式执行。

ExperimentResult包含完整runs、planned_runs、succeeded_runs、failed_runs、not_run、failure_reasons、repeat_mode和配置指纹。每轮记录公开seed、环境指纹、初始B、来源覆盖及状态，结果快照不得随下一轮变化。

全部计划轮次成功时才有all_runs_mean；任何失败或未执行都使其为空。可另给mean_over_successes，必须同时显示成功分母和失败率；成功样本不足2时不提供样本标准差。只有相同场景、指标、统计口径及运行策略的轮次可以汇总，seed变化是模式允许的差异。

领域失败后继续执行既定下一轮；java_rerun从Python实际失败位置继续，不能承诺原Java异常尾部的RNG位置。未知程序异常中止批次并向外传播，不将未运行轮次当成功。当前不定义GP适应度惩罚，后续评估层另行设计。

# 19 验收矩阵

所有新增验收均待执行。正常对照与预期差异测试分别统计，不因双方失败或缺少轨迹而判正常一致。

| 编号 | 场景 | 通过标准 |
|---|---|---|
| V01 | 原0.2.1回归 | 原测试与14配置、96扫查、组件oracle重新通过；正式门禁0跳过；已知精度负例仍明确失败 |
| V02 | 20标准DAX | 两侧任务顺序、Java编号、父子列表顺序及实际规模逐项一致 |
| V03 | DAX负例 | 命名空间变体、重复ID、非法及前向引用、重复边、空图、自环、环、未知结构按契约处理，无部分模板 |
| V04 | sampler边界 | 拒零、0.2与0.8归属、整数两端及单点、指数0、常量不推进 |
| V05 | sampler生命周期 | 构造和复制不抽数，冻结后不能改参，新上下文独立，设备共享正确 |
| V06 | 环境采样顺序 | 设备、边缘、云及各字段调用准确；禁用本地仍抽设备算力 |
| V07 | 两遍生成 | 每任务workload、data、children交错；每边一次；多父输入按parents顺序累计 |
| V08 | 候选公式 | 本地和远程PT、UT、DT及候选顺序正确；同服务器父子不免通信 |
| V09 | 身份与多设备 | 同模板多工作流不共享Task；全局JobID按接纳；共享同一服务器；owner与producer分离 |
| V10 | 动态Arrival | 全部入口派发后一次后续尝试；Finish不生成；G到N加W仍继续；无额外设备选择抽样 |
| V11 | 拒绝尝试 | 零间隔及舍入不推进时完整消耗本次采样，G/B不变，无Arrival，无自动重试 |
| V12 | 统计筛选 | G等于W、超过W、G达到N加W、B下降、早期ID晚完成、不入选完成不补录 |
| V13 | 正常停止 | 达标事件完整执行、下一条件归并后停；同刻剩余事件不执行；指标使用统计集合 |
| V14 | 保护与失败 | 400与401、400000与400001、生成阈值边界、目标与保护同事件、事件耗尽、额外预算 |
| V15 | 重置和seed | fresh、reset、rerun、rotate前后环境、B、RNG起点准确；正负seed及64位回绕 |
| V16 | Java输入导出 | mapClear前数据完整，拒绝和未到达者保留；观察不增加采样或改变结果 |
| V17 | Python重放 | 同输入、同来源位置、同规则、同初始B及统计条件下，正常轨迹和结果一致 |
| V18 | 记录覆盖 | 缺记录、不完整捕获、调用位置不符、换规则覆盖不足明确诊断，不补输入 |
| V19 | 固定投影 | 两侧固定入口对同一投影逐轨迹一致；不误比原动态指标 |
| V20 | 边数据释放 | 原始归档不变、无RNG推进、读取状态明确、幂等；开启和关闭调度事实一致 |
| V21 | 批次与CLI | 旧入口及repeat不变；缺动态模式先报错；结果独立；失败分母正确 |
| V22 | 数值边界 | 非有限派生、PT下溢、执行总区间归零、计数溢出、非法seed明确处理 |

## 19.1 统计分布验收建议

每个随机sampler使用固定seed集合0、1、20261104，每seed100000次，结果和有效参数留存。离散频率与理论值绝对误差不超过0.01；均匀实数均值误差不超过区间宽度的0.01；指数均值相对误差不超过0.02、方差相对误差不超过0.05，并在均值位置检查CDF频率误差不超过0.01。单点整数和常量用精确值检查。参数、样本量和阈值在运行前冻结，不根据观察结果调宽。

这些是工程验收建议，不构成严格的分布等价数学证明。Java与Python分别对理论分布核对，不要求成对随机值相同。若需Java分布采样参考，先运行其真实sampler；不能以文档getMean替代观测和实际next逻辑。

## 19.2 正常逐轨迹对照

先校验配置和实际加载输入，再按事件顺序比较类型、时间、owner、producer、对象键、前态、DECISION与EMIT、后态和错误，最后比较任务事实、统计集合及指标。ID、计数、顺序和选择精确；时间和评分沿用abs1e-9、rel1e-12，priority有符号零保持区分。容差不参与运行排序。

输入值以binary64准确往返为目标；物理累计和公式审计独立报告。不能通过排序日志、补决策、合并近似同时事件或覆盖时长隐藏差异。

严格正常通过要求：输入捕获完整、来源覆盖足够、规则受支持、统计条件一致、两侧正常成功、首差为空。预期异常差异只报告边界测试通过，不报告正常轨迹等价。基础设施错误、未执行、跳过均不能计通过。

报告分类固定为NORMAL_PARITY_PASSED、EXPECTED_DIFFERENCE_CONFIRMED、INPUT_COVERAGE_INSUFFICIENT、FAILED、NOT_EXECUTED、INFRASTRUCTURE_ERROR；只有第一类计正常跨语言通过。未提供参考文件的输入重放可正常执行，但比较状态为NOT_COMPARED，不能记NORMAL_PARITY_PASSED。

# 20 Java与Python差异登记

| 项目 | 原Java | 本设计处理 |
|---|---|---|
| 固定与动态入口 | 原构造采样并setup | 固定旧入口保留；动态上下文另建 |
| DAX非法引用 | 静默跳过 | 初始化明确失败 |
| 重复ID与边、空图和环 | 缺少严格保护 | 主动拒绝 |
| XML数量声明 | 不用于建图 | 实际元素权威，声明不符诊断 |
| DAX读取 | 每次生成读文件 | 上下文预读、校验、冻结 |
| XML路径 | 相对cwd的dax及历史硬编码路径 | 显式dag_root，相对配置文件 |
| Task身份 | 顺序整数 | XML字符串加Java映射，不增加排序键 |
| 边映射 | 生成末尾清空 | 默认保留，提供显式释放 |
| sampler修改 | 对象可变，部分setter空操作 | 有效参数初始化后冻结 |
| RNG | Commons Math共享生成器 | random.Random共享输入流，具体算法和消耗可不同 |
| seed输入 | Java long | 有符号64位公开值，Python按位模式编码 |
| jobsInSystem | 包含未来工作流 | pending与active分区，规则视图不暴露未来 |
| jobsCompleted | 统计入选者 | 另设recorded集合，物理completed保留全部 |
| 原保护后续 | 极大时钟、清全局堆，可能续跑 | 首次判定后明确FAILED |
| 失败指标 | 正无穷或极大值，也可能按已达标集合计算 | 正式指标为空，原生参考值独立编码 |
| 总占用归零 | 已知反例会重叠 | 保留0.2.1精度拒绝 |
| 整数溢出 | 原int可能回绕 | 计数与派生阈值越界保护，旧固定范围不变 |
| 原评估与重复 | 多次rerun后reset；有额外评估层处理 | 当前只实现显式运行与汇总，GP惩罚留后续 |

每项差异都必须出现在验收报告的scope或known_differences，不以“都是随机差异”概括。异常提前退出对后续rerun随机流位置的影响属于已确认异常差异。

论文辅助核对：PDF第8页、印刷第2664页描述预热及考虑工作流全部完成后停止，但原代码按R目标及实际筛选停止；论文数据描述为5220至20680的离散均匀，代码为基础data5120至20480的实数均匀加边数据；论文表IV云带宽概率印为20%、80%、20%，合计120%，代码实际为128占20%、256占20%、512占60%。当前基线按源码，表格勘误解释留后续正式实验核查。

不承诺任意有限输入与Java等价，也不将本阶段成功扩展为GP或论文实验复现完成。

# 21 兼容迁移与后续扩展

旧固定配置、输入及结果继续直接使用；不要求用户补seed、物理参数或DAX字段。旧加载器维持严格未知字段检查。新配置和输入各自带格式及版本，避免旧接口按内容猜模式。物理输入不可经过旧to_dict再丢字段后进入动态模型。

资源和工作流建图共享规范对象约束，来源与停止策略分别注入；新增功能不复制一套调度器。event_queue归并拆分只提取现有操作，旧固定路径顺序保持。性能开关不更改评分次数、采样次序或缓存算法。

依赖实施顺序为：数据与配置契约；模板和sampler；环境与完整输入生成；集中登记、动态事件和统计；输入导出、重放及清理；完整跨语言回归。这里是架构依赖关系；用户确认本设计完成后，阶段D再拆模块级编码任务和验收顺序。

后续GP接口通过规则工厂和PriorityRule接入，输入来源不感知树表达式或演化。输入流与未来演化流分开；当前不创建未使用演化RNG。InputArchive及dataset_role支持debug、train、test来源标识，后续数据集注册独立管理，不向规则暴露测试集信息或未来工作流。

本阶段不为了GP规模先移除对象图保护、不截断统计证据、不清空拓扑和完成历史；如需优化，建立独立开关、等价用例与测量。

# 22 来源定位

以下均来自本对话提供的文件，不使用其他对话文件或未选中的资料。

| 来源 | 主要位置 |
|---|---|
| fogsim-0.2.1-verified.zip | README；docs/VALIDATION、IMPLEMENTATION-NOTES、ISSUES-AND-FIXES、roadmap、semantics、JAVA-FIXED-ADAPTER |
| Python运行源码 | src/fogsim/instances、model、simulation、rules、config.py、cli.py |
| Python验证工具 | tests/parity/test_v2_acceptance.py；tests/unit/test_execution_precision.py；tools/run_fixed_parity.py、run_v2_acceptance.py、validate.py |
| Java解析 | taskscheduling/WorkflowParser.java第94行起 |
| Java目录 | taskscheduling/dag/DAGType.java；DAGTypePath.java第149行起 |
| Java环境与循环 | simulation/DynamicSimulation.java第106、127、257、302、316行起 |
| Java生命周期与指标 | DynamicSimulation.java第436、453、484、503、511、535行起 |
| Java生成与数据 | taskscheduling/MobileDevice.java第348、369、379、415行起；Task.java第185行起 |
| Java接纳与B | simulation/state/SystemState.java第63、147、161行起 |
| Java完成筛选 | MobileDevice.java第808行起；event/ProcessFinishEvent.java第141行起 |
| Java到达续生 | event/JobArrivalEvent.java第46、98行 |
| Java评分平分 | TaskOption.java第107行起 |
| Java采样器 | util/random下Uniform、UniformInteger、Exponential、TwoSixTwo、BandwidthCloud、BandwidthEdge |
| 依赖实际实现 | libraries/commons-math3-3.5.jar的RandomDataGenerator、UniformIntegerDistribution、ExponentialDistribution相关字节码 |
| 原计划与设计 | Fog-Computing-Java-to-Python-Study-Plan-2026-10-08.md；实现方案及详细设计.zip |
| 论文 | Xu等2023中英对照PDF，第2664页及模型相关段落 |

Java位置均相对于Fog-Computing-multiDeviceDebug/src/mengxu；完整源文件路径按上表组合。行号针对当前附件，不是未来观察overlay。早期设计用于语义追溯，不作为0.2.1新增功能已实现的证据。

附件SHA256如下，文件名与上传名称对应。

| 文件 | SHA256 |
|---|---|
| fogsim-0.2.1-verified.zip | b481609243dcd6c73c6428f3a242555f0ffaf5e27a63d5049e2fc50a72877c2e |
| Fog-Computing-multiDeviceDebug.zip | 17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a |
| 实现方案及详细设计.zip | 9ab607d19439cd25fe8dea60124be22651220e15e3ac34d142bd5aaaf482b42e |
| 原阅读计划MD | 221353e11d7f8493d3afd9b2aa02537f0be4f4073193b45cbe161ea839589e0a |
| Xu等2023双语PDF | 0fe716a44ca8d63013406d641e0b7dea652dc17f23614554f86c30b9937a9305 |

Commons Math运行JAR的SHA256为dcf9768726b82e8d7b8a928447b08bca7cfe2773d5120a63a41ec224207c1a29。字节码静态核查不替代实际Java采样与动态运行证据。

# 23 审阅状态与完成条件

已确认的核心语义见决策登记。以下是本稿新增的具体化建议，等待整体审阅，不再把源码事实重复作为选择题：

- 模块和API名称，准备失败PreparationError及便利入口的统一结果处理。
- 精确字段、edge_data_state、输入格式标识和版本、错误码及CLI拼写。
- 新配置必填字段、兼容profile中冲突参数的处理、数值上限与派生表达式校验。
- 分布验收样本量和误差界、完整验收矩阵及报告分类。

尚待运行验证的重点包括：原动态生成及同刻顺序、B下降和延续、拒绝后设备生成链、原保护尾部可达行为、导出观察无干扰、记录驱动重放、清理等价与实际内存收益。每一项都有目标用例；当前均不标记为新增功能通过。

阶段C完成条件：用户明确确认本详细设计完成；关键语义、接口及边界无未决项；新增差异均有理由和对应验收；固定兼容范围清楚。尚未实现的运行验证保留为后续验收任务，不要求在编码前伪造通过。

确认阶段C完成后，才进入阶段D整理模块级编码任务与验收顺序。当前不修改原ZIP、不生成模拟器实现代码、不启动GP或论文训练。
