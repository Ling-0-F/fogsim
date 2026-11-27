# 0.3.0 冻结设计逐条契约审计

基线：本对话第7步交付包。冻结原文保存在 `references/design/FROZEN-0.3.0-BASELINE.md`；历史“初稿/待审阅”标签不改变用户冻结状态。

本表逐条记录源码审查义务、实现位置和运行验收入口。最终每项状态、实际执行测试数量、缺失/失败证据在 `outputs/final/contracts-audit.json`；V01～V22跨语言及边界门禁状态在 `outputs/final/acceptance.json`。测试关联是可查证据，不作为任意输入的形式化证明。

## 本轮补齐

- 正式 `AdmissionService.admit` 返回 `AdmissionResult(accepted, workflow, reason_code)`，动态调用链已使用；原 `attempt` 保留Workflow/None兼容返回。普通拒绝与生成异常分离。
- 新Java参考额外观察真实owner/staging、事件前态和错误边界；仅追加观察、不修改原方法/堆/采样/规则。历史参考不改，旧producer字段继续按owner映射。
- 对照按每个实际事件的头→前态→动作→后态→错误定位首差；不得让后续事件差异遮蔽更早的前态差异。
- 进度观察回调获取独立结果快照，不能污染后续结果；存在的rng_seed_decimal必须为精确字符串。
- Python包/CLI/pyproject及新输入provenance统一为0.3.0；已有schema_version=1保持独立版本契约。

## 审查表

| 编号 | 冻结条款 | 逐项义务 | 主要实现 | 验收 |
|---|---|---|---|---|
| C001 | 1.3 | 旧固定JSON、公开API、结果字段与repeat保持兼容 | `src/fogsim/instances/fixed.py`, `src/fogsim/simulation/engine.py`, `src/fogsim/simulation/events.py`, `src/fogsim/simulation/event_queue.py` | V01 |
| C002 | 1.3 | 四事件、两层堆、异常比较器和平分遍历顺序保留 | `src/fogsim/instances/fixed.py`, `src/fogsim/simulation/engine.py`, `src/fogsim/simulation/events.py`, `src/fogsim/simulation/event_queue.py` | V01 |
| C003 | 1.3 | Finish后两整轮路由、预约、计算/下载占用及缓存加减顺序保留 | `src/fogsim/instances/fixed.py`, `src/fogsim/simulation/engine.py`, `src/fogsim/simulation/events.py`, `src/fogsim/simulation/event_queue.py` | V01 |
| C004 | 1.3 | 固定全集完成才成功，领域失败空指标，未知程序异常传播 | `src/fogsim/instances/fixed.py`, `src/fogsim/simulation/engine.py`, `src/fogsim/simulation/events.py`, `src/fogsim/simulation/event_queue.py` | V01 |
| C005 | 4 | 输入/环境/来源→集中接纳→规范状态→原四事件；不复制调度器 | `src/fogsim/instances/source.py`, `src/fogsim/simulation/admission.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/rules/contexts.py` | V09 |
| C006 | 4 | 日志和比较只观察；规则视图不含Context、RNG、完整归档或未来输入 | `src/fogsim/instances/source.py`, `src/fogsim/simulation/admission.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/rules/contexts.py` | V09 |
| C007 | 4 | 资源对象不承担生成、seed轮换或批次汇总 | `src/fogsim/instances/source.py`, `src/fogsim/simulation/admission.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/rules/contexts.py` | V09 |
| C008 | 5.1 | 模板和任务映射独立不可变；不含随机值或运行图 | `src/fogsim/instances/generated.py`, `src/fogsim/instances/templates.py`, `src/fogsim/environment/spec.py`, `src/fogsim/model/task.py`, `src/fogsim/model/workflow.py` | V09 |
| C009 | 5.1 | 环境保存有序实际资源数值；不含队列状态 | `src/fogsim/instances/generated.py`, `src/fogsim/instances/templates.py`, `src/fogsim/environment/spec.py`, `src/fogsim/model/task.py`, `src/fogsim/model/workflow.py` | V09 |
| C010 | 5.1 | 候选完整保存任务物理值、累计、边值和全部实际PT/UT/DT | `src/fogsim/instances/generated.py`, `src/fogsim/instances/templates.py`, `src/fogsim/environment/spec.py`, `src/fogsim/model/task.py`, `src/fogsim/model/workflow.py` | V09 |
| C011 | 5.1 | attempt与正式工作流ID分离；归档不共享可变边字典 | `src/fogsim/instances/generated.py`, `src/fogsim/instances/templates.py`, `src/fogsim/environment/spec.py`, `src/fogsim/model/task.py`, `src/fogsim/model/workflow.py` | V09 |
| C012 | 5.2 | 旧构造字段位置保留，新增可选字段后置 | `src/fogsim/instances/generated.py`, `src/fogsim/instances/templates.py`, `src/fogsim/environment/spec.py`, `src/fogsim/model/task.py`, `src/fogsim/model/workflow.py` | V09 |
| C013 | 5.2 | 动态Workflow元数据、Task物理数据、资源物理参数完整 | `src/fogsim/instances/generated.py`, `src/fogsim/instances/templates.py`, `src/fogsim/environment/spec.py`, `src/fogsim/model/task.py`, `src/fogsim/model/workflow.py` | V09 |
| C014 | 5.2 | UNAVAILABLE/RETAINED/RELEASED及访问错误明确 | `src/fogsim/instances/generated.py`, `src/fogsim/instances/templates.py`, `src/fogsim/environment/spec.py`, `src/fogsim/model/task.py`, `src/fogsim/model/workflow.py` | V09 |
| C015 | 5.2 | Task/Workflow无Context、归档或目录的反向引用 | `src/fogsim/instances/generated.py`, `src/fogsim/instances/templates.py`, `src/fogsim/environment/spec.py`, `src/fogsim/model/task.py`, `src/fogsim/model/workflow.py` | V09 |
| C016 | 5.3 | 动态ID为接纳前G；拒绝不占ID，固定ID不重编号 | `src/fogsim/instances/identity.py`, `src/fogsim/instances/materialize.py`, `src/fogsim/simulation/state.py` | V09 |
| C017 | 5.3 | Task.id保留XML字符串，Java编号仅按任务位置映射 | `src/fogsim/instances/identity.py`, `src/fogsim/instances/materialize.py`, `src/fogsim/simulation/state.py` | V09 |
| C018 | 5.3 | 设备/服务器编号按资源顺序；不靠名称后缀解析 | `src/fogsim/instances/identity.py`, `src/fogsim/instances/materialize.py`, `src/fogsim/simulation/state.py` | V09 |
| C019 | 5.3 | 同轮规范对象唯一，跨工作流/跨轮对象图隔离 | `src/fogsim/instances/identity.py`, `src/fogsim/instances/materialize.py`, `src/fogsim/simulation/state.py` | V09 |
| C020 | 5.3 | 模板依赖顺序与边采样顺序分别保存，不混用 | `src/fogsim/instances/identity.py`, `src/fogsim/instances/materialize.py`, `src/fogsim/simulation/state.py` | V09 |
| C021 | 6 | G/B/R各有单一权威；recorded引用物理completed中的同一对象 | `src/fogsim/simulation/state.py`, `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/event_queue.py` | V09 |
| C022 | 6 | pending/active/completed互斥且覆盖全部接纳工作流 | `src/fogsim/simulation/state.py`, `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/event_queue.py` | V09 |
| C023 | 6 | 各设备计数、统计子集、实际到达与物理完成关系一致 | `src/fogsim/simulation/state.py`, `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/event_queue.py` | V09 |
| C024 | 6 | 任务只派发/执行/完成一次，资源预约与Start一一对应 | `src/fogsim/simulation/state.py`, `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/event_queue.py` | V09 |
| C025 | 6 | 占用区间为正且不重叠，队列/缓存/引用/执行索引受检查 | `src/fogsim/simulation/state.py`, `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/event_queue.py` | V09 |
| C026 | 7.1 | 20标准编号/文件/实际规模对应；额外图不自动编号 | `src/fogsim/instances/dax.py`, `src/fogsim/instances/catalog.py` | V02 |
| C027 | 7.1 | dag_root相对配置路径；文件名及声明计数不决定实际图 | `src/fogsim/instances/dax.py`, `src/fogsim/instances/catalog.py` | V02 |
| C028 | 7.2 | 根adag、允许命名空间及结构大小写按约定识别 | `src/fogsim/instances/dax.py`, `src/fogsim/instances/catalog.py` | V03 |
| C029 | 7.2 | job/child按根直属顺序，ID/ref原样保留，uses不参与参数 | `src/fogsim/instances/dax.py`, `src/fogsim/instances/catalog.py` | V03 |
| C030 | 7.2 | 前向/未知引用、重复ID/边、自环/环、空图和未知结构拒绝 | `src/fogsim/instances/dax.py`, `src/fogsim/instances/catalog.py` | V03 |
| C031 | 7.2 | 不排序拓扑或加虚拟节点；允许无边/多入口出口/不连通DAG | `src/fogsim/instances/dax.py`, `src/fogsim/instances/catalog.py` | V03 |
| C032 | 7.2 | 声明数量不符仅诊断；失败含位置及相关ID/ref，无部分模板 | `src/fogsim/instances/dax.py`, `src/fogsim/instances/catalog.py` | V03 |
| C033 | 7.3 | 抽样范围所有模板在RNG创建前加载、验证和冻结 | `src/fogsim/instances/catalog.py`, `src/fogsim/randomness/state.py`, `src/fogsim/simulation/context.py` | V05 |
| C034 | 7.3 | reset/rerun/rotate复用模板及哈希；文件变更需新上下文 | `src/fogsim/instances/catalog.py`, `src/fogsim/randomness/state.py`, `src/fogsim/simulation/context.py` | V05 |
| C035 | 8.1 | 公开seed是真signed64，拒绝bool/浮点/字符串/越界 | `src/fogsim/seed.py`, `src/fogsim/randomness/state.py`, `src/fogsim/randomness/samplers.py`, `src/fogsim/simulation/context.py` | V15 |
| C036 | 8.1 | 内部按unsigned64位模式编码，保留版本及精确十进制 | `src/fogsim/seed.py`, `src/fogsim/randomness/state.py`, `src/fogsim/randomness/samplers.py`, `src/fogsim/simulation/context.py` | V15 |
| C037 | 8.1 | rotate回绕加10000；reset(None)使用当前seed，不调用随机None种子 | `src/fogsim/seed.py`, `src/fogsim/randomness/state.py`, `src/fogsim/randomness/samplers.py`, `src/fogsim/simulation/context.py` | V15 |
| C038 | 8.2 | 每Context一条共享输入流，环境与所有设备共同推进 | `src/fogsim/seed.py`, `src/fogsim/randomness/state.py`, `src/fogsim/randomness/samplers.py`, `src/fogsim/simulation/context.py` | V05 |
| C039 | 8.2 | sampler只持参数，构造/校验/clone/日志不抽数 | `src/fogsim/seed.py`, `src/fogsim/randomness/state.py`, `src/fogsim/randomness/samplers.py`, `src/fogsim/simulation/context.py` | V05 |
| C040 | 8.2 | 角色共享正确，上下行独立角色，各Context sampler独立 | `src/fogsim/seed.py`, `src/fogsim/randomness/state.py`, `src/fogsim/randomness/samplers.py`, `src/fogsim/simulation/context.py` | V05 |
| C041 | 8.2 | 先校验冻结有效参数；mean100冲突及不支持profile明确拒绝 | `src/fogsim/seed.py`, `src/fogsim/randomness/state.py`, `src/fogsim/randomness/samplers.py`, `src/fogsim/simulation/context.py` | V05 |
| C042 | 8.3 | 实数均匀拒零并按u*b+(1-u)*a；端点舍入不钳制/重抽 | `src/fogsim/randomness/samplers.py`, `src/fogsim/experiment_config.py` | V04 |
| C043 | 8.3 | 整数用包含两端randint，单点仍调用；指数按Python算法且可返回0 | `src/fogsim/randomness/samplers.py`, `src/fogsim/experiment_config.py` | V04 |
| C044 | 8.3 | 权重及云带宽0.2/0.8边界和拒零正确 | `src/fogsim/randomness/samplers.py`, `src/fogsim/experiment_config.py` | V04 |
| C045 | 8.3 | 边缘带宽1024常量不推进RNG；不移植Java指数内部算法 | `src/fogsim/randomness/samplers.py`, `src/fogsim/experiment_config.py` | V04 |
| C046 | 8.4 | 标准参数范围、概率和有效参数指纹保存 | `src/fogsim/randomness/samplers.py`, `src/fogsim/experiment_config.py` | V04 |
| C047 | 8.4 | 只使用s和模型单位，不擅加单位换算 | `src/fogsim/randomness/samplers.py`, `src/fogsim/experiment_config.py` | V04 |
| C048 | 8.4 | 复现要求代码/运行时/数据/操作一致；跨环境以实际输入为依据 | `src/fogsim/randomness/samplers.py`, `src/fogsim/experiment_config.py` | V04 |
| C049 | 9.1 | 先所有设备算力，再边缘/云各上行、下行、算力 | `src/fogsim/environment/build.py`, `src/fogsim/environment/spec.py` | V06 |
| C050 | 9.1 | 禁用本地仍采设备算力，边缘带宽仍调用但不抽数 | `src/fogsim/environment/build.py`, `src/fogsim/environment/spec.py` | V06 |
| C051 | 9.1 | 资源数值齐备后逐设备尝试；运行队列/缓存/预约/时钟归零 | `src/fogsim/environment/build.py`, `src/fogsim/environment/spec.py` | V06 |
| C052 | 9.1 | 服务器全局规范共享，不按设备复制 | `src/fogsim/environment/build.py`, `src/fogsim/environment/spec.py` | V06 |
| C053 | 9.2 | 类型→间隔→release→权重→两遍生成顺序保持 | `src/fogsim/instances/generation.py`, `src/fogsim/instances/materialize.py` | V07 |
| C054 | 9.2 | 第一遍每任务workload/data/children交错，边只采一次 | `src/fogsim/instances/generation.py`, `src/fogsim/instances/materialize.py` | V07 |
| C055 | 9.2 | 第二遍按parents顺序累计并创建完整候选 | `src/fogsim/instances/generation.py`, `src/fogsim/instances/materialize.py` | V07 |
| C056 | 9.2 | 已知release不推进也完整消耗候选采样；不提前跳过 | `src/fogsim/instances/generation.py`, `src/fogsim/instances/materialize.py` | V07 |
| C057 | 9.3 | 累计从0逐项加，不排序/fsum；总量不含基础data | `src/fogsim/instances/generation.py`, `src/fogsim/instances/materialize.py` | V08 |
| C058 | 9.3 | 本地PT与零UT/DT、远程PT/UT/DT公式和括号保持 | `src/fogsim/instances/generation.py`, `src/fogsim/instances/materialize.py` | V08 |
| C059 | 9.3 | 候选为合法本地→边缘→云，其他移动设备不候选 | `src/fogsim/instances/generation.py`, `src/fogsim/instances/materialize.py` | V08 |
| C060 | 9.3 | 无边仍传基础data，同服务器父子不免通信 | `src/fogsim/instances/generation.py`, `src/fogsim/instances/materialize.py` | V08 |
| C061 | 9.4 | 完整生成后按finite release>clock接纳 | `src/fogsim/simulation/admission.py`, `src/fogsim/simulation/dynamic.py` | V11 |
| C062 | 9.4 | 成功集中登记规范图/任务事实/pending/G/设备数/B/Arrival | `src/fogsim/simulation/admission.py`, `src/fogsim/simulation/dynamic.py` | V11 |
| C063 | 9.4 | 拒绝保留完整候选/attempt，不登记、不占ID、不改G/B、不发事件 | `src/fogsim/simulation/admission.py`, `src/fogsim/simulation/dynamic.py` | V11 |
| C064 | 9.4 | 拒绝不重抽或回滚，不中断其他设备，Finish不续生 | `src/fogsim/simulation/admission.py`, `src/fogsim/simulation/dynamic.py` | V11 |
| C065 | 9.4 | 非法派生值是领域失败，原始delta与release均保存 | `src/fogsim/simulation/admission.py`, `src/fogsim/simulation/dynamic.py` | V11 |
| C066 | 9.5 | workload/算力/带宽/PT正有限，data/UT/DT非负有限 | `src/fogsim/numerics.py`, `src/fogsim/input_validation.py`, `src/fogsim/instances/generation.py`, `src/fogsim/model/execution.py`, `src/fogsim/simulation/statistics.py` | V22 |
| C067 | 9.5 | 派生加除、PT下溢及执行总区间舍零明确失败 | `src/fogsim/numerics.py`, `src/fogsim/input_validation.py`, `src/fogsim/instances/generation.py`, `src/fogsim/model/execution.py`, `src/fogsim/simulation/statistics.py` | V22 |
| C068 | 9.5 | N/W及N+W乘500、资源编号/G在int32边界内，不模仿计数回绕 | `src/fogsim/numerics.py`, `src/fogsim/input_validation.py`, `src/fogsim/instances/generation.py`, `src/fogsim/model/execution.py`, `src/fogsim/simulation/statistics.py` | V22 |
| C069 | 9.5 | W0合法；N1/W0不可达统计目标不自动修正 | `src/fogsim/numerics.py`, `src/fogsim/input_validation.py`, `src/fogsim/instances/generation.py`, `src/fogsim/model/execution.py`, `src/fogsim/simulation/statistics.py` | V22 |
| C070 | 10 | 固定/随机/重放共用原事件处理和真实initialize/after_arrival位置 | `src/fogsim/simulation/events.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/engine.py`, `src/fogsim/simulation/trace.py` | V10 |
| C071 | 10 | Arrival先激活并派发全部入口，再生成一次；Finish不生成 | `src/fogsim/simulation/events.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/engine.py`, `src/fogsim/simulation/trace.py` | V10 |
| C072 | 10 | 不随机换设备；达到N+W仍继续生成 | `src/fogsim/simulation/events.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/engine.py`, `src/fogsim/simulation/trace.py` | V10 |
| C073 | 10 | 所有新事件stage；owner和当前生产设备分离 | `src/fogsim/simulation/events.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/engine.py`, `src/fogsim/simulation/trace.py` | V10 |
| C074 | 10 | no-trace仍登记任务事实/输入；actions保留实际DECISION/EMIT交错 | `src/fogsim/simulation/events.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/engine.py`, `src/fogsim/simulation/trace.py` | V10 |
| C075 | 10 | 动态每轮单次归并→目标→耗尽→预算→poll；固定pop_next保持 | `src/fogsim/simulation/events.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/engine.py`, `src/fogsim/simulation/trace.py` | V10 |
| C076 | 11.1–11.2 | Java字段映射G、设备生成/物理/统计数、R、B准确 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V12 |
| C077 | 11.1–11.2 | 接纳后G<N+W时B直接赋值，可下降；等号后冻结 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V12 |
| C078 | 11.1–11.2 | 完成时按当时G>W、ID非负、release<=B筛选一次 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V12 |
| C079 | 11.1–11.2 | 不增加ID窗口筛选；不补录；物理完成标志与统计资格分离 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V12 |
| C080 | 11.3 | R达标事件完整执行，再归并停止，保留同刻剩余/pending/active | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V13 |
| C081 | 11.3 | 动态指标只用统计集合，flow按登记顺序逐项累计，不加权 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V13 |
| C082 | 11.3 | 固定指标用全集；失败指标为空，不使用成功子集填充 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V13 |
| C083 | 12 | 仅在原事件后位置按原顺序检查严格>保护和全部命中 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V14 |
| C084 | 12 | 首次保护明确FAILED，保留实际时钟和队列，不执行Java异常尾部 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V14 |
| C085 | 12 | 同事件目标与保护冲突时失败优先 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V14 |
| C086 | 12 | 事件耗尽、预算、重放覆盖、数值/状态错误稳定区分 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V14 |
| C087 | 12 | 结果保留计划/实际时刻区别、物理/统计/源消费事实 | `src/fogsim/simulation/statistics.py`, `src/fogsim/simulation/dynamic.py`, `src/fogsim/simulation/dynamic_result.py` | V14 |
| C088 | 13 | fresh先环境后工作流，B0；reset重设输入流且保留环境/B | `src/fogsim/simulation/context.py`, `src/fogsim/randomness/state.py` | V15 |
| C089 | 13 | rerun延续流与B；rotate只准备不运行 | `src/fogsim/simulation/context.py`, `src/fogsim/randomness/state.py` | V15 |
| C090 | 13 | 每轮重建对象，结果快照隔离，READY旧引擎不能再推进流 | `src/fogsim/simulation/context.py`, `src/fogsim/randomness/state.py` | V15 |
| C091 | 13 | 生命周期仅在轮次边界；准备失败保留诊断并可显式恢复 | `src/fogsim/simulation/context.py`, `src/fogsim/randomness/state.py` | V15 |
| C092 | 13 | 原生RNG边界快照含Python/state版本，不以哈希代替真实状态 | `src/fogsim/simulation/context.py`, `src/fogsim/randomness/state.py` | V15 |
| C093 | 14 | 默认retain；提供实际工作流级释放能力 | `src/fogsim/simulation/cleanup.py`, `src/fogsim/simulation/admission.py` | V20 |
| C094 | 14 | 完整候选已独立归档，整张工作流预检后才修改任何映射 | `src/fogsim/simulation/cleanup.py`, `src/fogsim/simulation/admission.py` | V20 |
| C095 | 14 | 仅两张运行映射置None/RELEASED；身份、拓扑、物理值、选项和完成记录保留 | `src/fogsim/simulation/cleanup.py`, `src/fogsim/simulation/admission.py` | V20 |
| C096 | 14 | 固定UNAVAILABLE跳过，重复释放幂等，映射条目不误作独立边数 | `src/fogsim/simulation/cleanup.py`, `src/fogsim/simulation/admission.py` | V20 |
| C097 | 14 | 归档/RNG/时钟/事件/候选/轨迹/统计不因开关变化 | `src/fogsim/simulation/cleanup.py`, `src/fogsim/simulation/admission.py` | V20 |
| C098 | 14 | 测量准备和完整小型运行的current/peak/耗时，不宣称普遍加速 | `src/fogsim/simulation/cleanup.py`, `src/fogsim/simulation/admission.py` | V20 |
| C099 | 15.1–15.2 | 独立schema-v1 input/reference/manifest分层；input单独运行 | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V17 |
| C100 | 15.1–15.2 | 版本、未知字段、数组、真整数、有限值、顺序/引用/候选/capture严格校验 | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V17 |
| C101 | 15.1–15.2 | 拒绝、未到达、未完成候选均保留；输入无参考决策/完成集/停止指标 | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V17 |
| C102 | 15.1–15.2 | 主调度使用记录时长，累计/公式审计独立且不回写 | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V17 |
| C103 | 15.1–15.2 | capture完整不表示无限输入；不完整捕获不能完整验收 | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V17 |
| C104 | 15.3 | 真实原Java构造/setup/run，第二遍后mapClear前复制完整候选 | `tools/java_dynamic_support.py`, `tools/java/step4/fogsim/adapter/DynamicCapture.java`, `tools/export_java_dynamic.py` | V16 |
| C105 | 15.3 | 接纳后补观察，保留初始化/Arrival拒绝及未到达候选 | `tools/java_dynamic_support.py`, `tools/java/step4/fogsim/adapter/DynamicCapture.java`, `tools/export_java_dynamic.py` | V16 |
| C106 | 15.3 | 原源码不改，观察追加且不增加采样/评分/比较操作 | `tools/java_dynamic_support.py`, `tools/java/step4/fogsim/adapter/DynamicCapture.java`, `tools/export_java_dynamic.py` | V16 |
| C107 | 15.3 | plain/baseline/minimal/full验证观察无干扰，来源/依赖指纹保留 | `tools/java_dynamic_support.py`, `tools/java/step4/fogsim/adapter/DynamicCapture.java`, `tools/export_java_dynamic.py` | V16 |
| C108 | 15.4 | 每次仅下一全局attempt，核对phase/owner/clock/触发workflow/拟用ID | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V18 |
| C109 | 15.4 | 不搜索、不按设备重组、不用event_sequence安排调度 | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V18 |
| C110 | 15.4 | Python独立release gate后核对observed acceptance | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V18 |
| C111 | 15.4 | 需要更多记录时明确用尽/错位，保留位置和部分诊断，不补输入 | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V18 |
| C112 | 15.4 | 正常停止可有未消费尾部；换规则覆盖不足不直接判算法错误 | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V18 |
| C113 | 15.4 | verify禁止行为变更；reuse仅支持的规则且关闭原轨迹结论 | `src/fogsim/replay/loader.py`, `src/fogsim/replay/spec.py`, `src/fogsim/replay/source.py`, `src/fogsim/replay/engine.py`, `src/fogsim/replay/audit.py` | V18 |
| C114 | 15.5 | 只投影成功接纳，保留资源/接纳/任务/依赖/选项顺序及ID/实际时长 | `src/fogsim/replay/export.py`, `src/fogsim/instances/fixed.py` | V19 |
| C115 | 15.5 | 独立标明fixed_projection、拒绝/动态位置/统计窗/物理字段损失 | `src/fogsim/replay/export.py`, `src/fogsim/instances/fixed.py` | V19 |
| C116 | 15.5 | Java和Python固定入口消费同一投影到全集完成 | `src/fogsim/replay/export.py`, `src/fogsim/instances/fixed.py` | V19 |
| C117 | 15.5 | 固定结果不与原动态统计指标混比，保留Java规则/物理占位限制 | `src/fogsim/replay/export.py`, `src/fogsim/instances/fixed.py` | V19 |
| C118 | 16 | 新实验格式/版本/mode独立，旧配置不猜模式 | `src/fogsim/experiment_config.py`, `src/fogsim/instances/fixed.py` | V21 |
| C119 | 16 | 路径相对配置或直接CLI cwd，程序化相对路径要求base_dir | `src/fogsim/experiment_config.py`, `src/fogsim/instances/fixed.py` | V21 |
| C120 | 16 | 未知/重复键、bool数值、非有限/非法范围/无候选在采样前拒绝 | `src/fogsim/experiment_config.py`, `src/fogsim/instances/fixed.py` | V21 |
| C121 | 16 | 固定路由对所有可能owner合法；seed列表完整且不矛盾 | `src/fogsim/experiment_config.py`, `src/fogsim/instances/fixed.py` | V21 |
| C122 | 16 | 冻结配置及profile冲突拒绝；诊断选项不偷偷改变输入 | `src/fogsim/experiment_config.py`, `src/fogsim/instances/fixed.py` | V21 |
| C123 | 17.1–17.2 | 保留旧固定公开接口和单次Engine.run；新API独立调用，simulate_replay支持可选运行后比较报告 | `src/fogsim/__init__.py`, `src/fogsim/simulation/context.py`, `src/fogsim/replay/engine.py`, `src/fogsim/experiments/runner.py` | V21 |
| C124 | 17.1–17.2 | 创建/reset领域失败抛带Engine/结果的PreparationError，便利入口归一化 | `src/fogsim/__init__.py`, `src/fogsim/simulation/context.py`, `src/fogsim/replay/engine.py`, `src/fogsim/experiments/runner.py` | V21 |
| C125 | 17.1–17.2 | 未知程序异常保持原类型并传播 | `src/fogsim/__init__.py`, `src/fogsim/simulation/context.py`, `src/fogsim/replay/engine.py`, `src/fogsim/experiments/runner.py` | V21 |
| C126 | 17.3 | dynamic/replay/export-fixed显式入口；仅dynamic可覆盖seed | `src/fogsim/cli.py`, `src/fogsim/io.py`, `src/fogsim/simulation/admission.py` | V21 |
| C127 | 17.3 | CLI覆盖在创建上下文前完成并进入有效配置 | `src/fogsim/cli.py`, `src/fogsim/io.py`, `src/fogsim/simulation/admission.py` | V21 |
| C128 | 17.3 | 退出0/1/2、no-trace事实/输入、旧repeat/identical语义保持 | `src/fogsim/cli.py`, `src/fogsim/io.py`, `src/fogsim/simulation/admission.py` | V21 |
| C129 | 17.3 | 未知异常不保留旧成功文件，保存中断时batch/capture明确不完整 | `src/fogsim/cli.py`, `src/fogsim/io.py`, `src/fogsim/simulation/admission.py` | V21 |
| C130 | 17.3 | 集中admit返回accepted/workflow/reason_code的AdmissionResult；普通拒绝非异常 | `src/fogsim/cli.py`, `src/fogsim/io.py`, `src/fogsim/simulation/admission.py` | V21 |
| C131 | 18 | 多轮必须显式模式，fresh_same_seed每轮新建，seed_list仅指定seed | `src/fogsim/experiments/runner.py`, `src/fogsim/replay/export_input.py` | V21 |
| C132 | 18 | java_rerun同Context延续RNG/B和环境数值，最终无额外reset/prepare/rotate | `src/fogsim/experiments/runner.py`, `src/fogsim/replay/export_input.py` | V21 |
| C133 | 18 | 重放每轮新对象/游标，不消费前轮尾部 | `src/fogsim/experiments/runner.py`, `src/fogsim/replay/export_input.py` | V21 |
| C134 | 18 | 每轮完整快照记录seed/环境/初始B/来源；观察回调也不能污染后续结果 | `src/fogsim/experiments/runner.py`, `src/fogsim/replay/export_input.py` | V21 |
| C135 | 18 | 领域失败继续；未知异常中止并标未完成，不作GP惩罚 | `src/fogsim/experiments/runner.py`, `src/fogsim/replay/export_input.py` | V21 |
| C136 | 18 | 完整成功才all_runs_mean，成功子集显示分母/失败率，少于2无样本std | `src/fogsim/experiments/runner.py`, `src/fogsim/replay/export_input.py` | V21 |
| C137 | 18 | 仅同场景/统计/规则/策略汇总；允许显式seed差异，DAX变更禁混合 | `src/fogsim/experiments/runner.py`, `src/fogsim/replay/export_input.py` | V21 |
| C138 | 19.1 | 3固定seed、每角色每seed100000样本、阈值预先固定且原始结果保留 | `src/fogsim/randomness/samplers.py`, `src/fogsim/experiment_config.py` | V04 |
| C139 | 19.1 | 两语言分别对理论分布，不要求同seed样本相等 | `src/fogsim/randomness/samplers.py`, `src/fogsim/experiment_config.py` | V04 |
| C140 | 19.2 | 先输入/配置/来源位置，再按事件序号比较头、前态、动作、后态、错误 | `src/fogsim/validation/dynamic_compare.py`, `src/fogsim/validation/trace_compare.py` | V17 |
| C141 | 19.2 | ID/计数/顺序精确，浮点abs1e-9/rel1e-12，priority区分有符号零 | `src/fogsim/validation/dynamic_compare.py`, `src/fogsim/validation/trace_compare.py` | V17 |
| C142 | 19.2 | 不排序/补调用/按时间匹配/覆盖时长掩盖差异 | `src/fogsim/validation/dynamic_compare.py`, `src/fogsim/validation/trace_compare.py` | V17 |
| C143 | 19.2 | 正常通过需完整捕获/覆盖/受支持条件/双边正常/清单绑定/首差空 | `src/fogsim/validation/dynamic_compare.py`, `src/fogsim/validation/trace_compare.py` | V17 |
| C144 | 19.2 | 正常、预期差异、覆盖不足、失败、未执行、基础设施错误分开，无参考NOT_COMPARED | `src/fogsim/validation/dynamic_compare.py`, `src/fogsim/validation/trace_compare.py` | V17 |
| C145 | 20–21 | Java/Python已确认差异逐项列出scope/known_differences | `src/fogsim/replay/engine.py`, `src/fogsim/simulation/context.py`, `src/fogsim/model/execution.py`, `src/fogsim/experiments/runner.py` | V22 |
| C146 | 20–21 | 结构/错误/统计/精度/RNG差异不泛称随机差异，失败后流尾差异明确 | `src/fogsim/replay/engine.py`, `src/fogsim/simulation/context.py`, `src/fogsim/model/execution.py`, `src/fogsim/experiments/runner.py` | V22 |
| C147 | 20–21 | 旧物理未知值兼容，不经旧序列化静默丢物理输入 | `src/fogsim/replay/engine.py`, `src/fogsim/simulation/context.py`, `src/fogsim/model/execution.py`, `src/fogsim/experiments/runner.py` | V22 |
| C148 | 20–21 | 只减少运行边映射，不清空工作流/执行历史或删保护以求规模 | `src/fogsim/replay/engine.py`, `src/fogsim/simulation/context.py`, `src/fogsim/model/execution.py`, `src/fogsim/experiments/runner.py` | V22 |
| C149 | 20–21 | dataset_role保存为来源元数据，规则无未来数据/演化RNG | `src/fogsim/replay/engine.py`, `src/fogsim/simulation/context.py`, `src/fogsim/model/execution.py`, `src/fogsim/experiments/runner.py` | V22 |

## V01～V22与范围解释

V01执行当前完整pytest（门禁不允许skip）、14固定配置、96扫查、原Java组件oracle及明确精度反例。V02/V04重跑20标准拓扑和两语言各3 seed×100000/角色的分布检查；V06～V08重跑原Java生成探针。V09～V18使用当前断言、50项原Java生命周期/保护探针、7份新导出输入和完整前后态重放；5个正常例与2个预期失败差异分列。V19两侧固定入口对6个非空投影、10条规则路径执行到完成；空投影为原固定格式表示限制。V20包括严格Java参考下的清理等价及完整小型运行的内存/峰值/耗时测量。V21/V22覆盖批次/CLI/回调隔离和所有冻结数值边界。

两个native_*大型固定投影是此前扩大规模的附加案例，不是原设计规定的最低门禁；本轮保留NOT_EXECUTED，不把它们算通过，也不将其自动升级为功能完成条件。性能测量有明确场景与样本量，不宣称普遍加速或论文规模收益。

## 声明性条款与非目标

§2是历史证据快照；各阶段报告保留时间及范围，最新报告不改写旧记录。§3的D01～D19按用户冻结执行；D20论文勘误解释/正式实验参数原设计明确留后续。§22对应来源与指纹，实际仅使用本项目/对话提供的文件和本对话交付包。§23冻结已由用户确认，无需重新审批。

不实现GP、十个特征、演化/训练、论文实验，不增加网络排队/抢占/失败重试/动态成员，不宣称完整DAX XSD、任意输入Java等价。已确认的Python严格校验、RNG算法、统计/保护尾部、精度与物理占位等差异全部进入最终acceptance的known_differences。
