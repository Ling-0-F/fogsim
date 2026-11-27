# 当前语义基线：0.3.0

本轮未改变冻结调度语义。正式admit返回AdmissionResult，旧attempt保留便利返回；新参考补实际owner/staging和前态/错误，对照按事件边界定位首差。149项契约与最终验收范围见CONTRACT-AUDIT.md和FINAL-ACCEPTANCE.md。以下阶段说明保持历史范围。

第7步开放显式release_after_materialization：完整归档后、Arrival前释放两张运行映射，调度事实和RNG不变。批次fresh_same_seed/fresh_seed_list/java_rerun及重放独立游标已编排；新命令与旧固定入口显式区分。完整合同见 [STEP7-PROGRESS](STEP7-PROGRESS.md)。

第6步重放复用动态集中接纳和原事件循环；逐次读取全局attempt、重算release gate，再核对观察值；不采样、不依赖参考输出。正常停止可留尾记录；参考比较在执行结束后进行。固定投影只保留成功接纳记录，固定全集指标独立于动态统计窗口。范围与错误合同见 [STEP6-PROGRESS](STEP6-PROGRESS.md)。

第 5 步动态语义已接入：集中接纳、每 Arrival 一次后续尝试、物理 completed 与 Java recorded 集合分离、B 赋值可下降、事件后保护与最后一次归并、保留环境/B 的 reset/rerun/rotate_seed。固定路径仍保留旧语义。API、失败合同、实际验证边界及旧参考 producer 字段勘误见 [STEP5-PROGRESS](STEP5-PROGRESS.md)。

第 4 步只增加 Java 导出开发工具；Python 生产语义未变。输入捕获与原生参考分离，拒绝/未到达/未完成候选均保存。capture.complete 不等于统计达标或输入无限覆盖；第 6 步才能验证 Python 动态重放。具体格式和观察边界见 [STEP4-PROGRESS](STEP4-PROGRESS.md)。

第 3 步环境、输入生成和运行建图契约见 [STEP3-PROGRESS](STEP3-PROGRESS.md)。生成只推进共享输入流；建图不发布索引，不更新 G/B 或安排 Arrival；release gate 的通过不等于正式接纳。运行边映射默认保留且与不可变输入独立。以下固定内核语义继续保持。

第 2 步新增纯 DAX 与采样基础见 [STEP2-PROGRESS](STEP2-PROGRESS.md)。sampler 必须接收同一上下文的输入 RNG，构造/clone 不持有或创建随机流；prepare_random_input 不创建 Engine。固定调度语义继续保持。

第 1 步扩展增加的纯配置和输入契约见 [STEP1-PROGRESS](STEP1-PROGRESS.md)。本文件以下仍描述已验证的固定运行路径；新数据类型不会使 create_engine/simulate 自动进入动态模式。新运行元数据为可空附加字段，不改变键或平分顺序。

权威设计依次为原设计 04（字段）、07（状态归属）、08（事件）、09（接口）、10（比较与归并）；输入使用03的完整示例，验证使用11。README 写明正式命令/格式，IMPLEMENTATION-NOTES 记录具体落地选择。

运行内每个工作流、任务、选项和资源只有一个规范对象；模型采用身份相等。输入 spec 不存运行状态，每轮重新建图。Task 的 dispatched/completed、Option 的 ready_time/priority、Resource 的队列/缓存/available_time/pending_start、Workflow 的完成记录与登记、SystemState 的全局集合/执行索引分别是其权威状态。

事件顺序：Arrival 激活并路由入口；Visit 更新选中 ready_time 后排队或预约；Start 消耗预约并写 available_time；Finish 完成任务、处理队列、查询当前工作流、两整轮路由后派发，空查询时另外检查全部完成。新事件进入当前生产设备暂存堆，不内联触发。事件 owner 与生产设备分别记录。

完成时间按 `(start + PT) + DT`；下载包含在处理器占用内。ready_time 不统一表示依赖满足时刻，后继评分前不刷新全部选项。MRT/FCFS 所读 available_time 不钳制到当前时钟。Server 空队清缓存，本地继续相减；检查容差不改变算法值。

同刻比较 JA<PS<TV<PF；JA 相同工作流 ID 返回 -1，PF 相同关键编号返回 +1，PS/TV 同类返回0。使用参考 JDK 操作顺序实现堆，不正规化异常比较器，不追加稳定序号。

旧固定入口只处理有限固定输入、无 warm-up、非抢占、无重试、无网络排队。正常 makespan 为所有完成工作流最大完成时间减最早发布时间。领域错误为 FAILED，最终 makespan 缺失。执行计划不等于实际触发；日志不用于判断派发、就绪、开始或完成资格。

0.2.0 已完成 V2-01～05 固定实例验收，详见 VALIDATION。接受执行计划前要求 `(start+PT)+DT > start`；否则显式 FAILED，不写入索引或预约。这是针对实际精度反例新增的边界校验，不声称原 Java 具有该保护，也不将该反例判为等价。支持严格为正的总占用区间；未对单独 PT/DT 重新运算或自动取整。
