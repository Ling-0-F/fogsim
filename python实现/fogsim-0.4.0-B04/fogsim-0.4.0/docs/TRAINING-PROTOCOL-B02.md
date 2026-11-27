# S9-B02 单树协议与工程细化

遵守 S9-frozen-1 与 D-frozen-1；不改变 B01 身份、计划、D03、fresh 或旧执行合同。B02 仅执行 single_routing。dual_tree 可预检但明确拒绝启动，特殊交叉留到 B03。

DEAP 1.4.4 的 PrimitiveTree/Primitive/Terminal 与 Fitness 用于训练存储；适配层显式映射 ADD/SUB/MUL/DIV/MAX/MIN 至既有六 token。真实评分不调用 gp.compile/eval。所有树及节点显式深克隆；DEAP 默认 PrimitiveTree 深复制会共享节点，本实现不采用。常量使用 f64:位串保留，导出用可往返严格十进制（无穷为上下溢 token）；演化生成仅十特征，无 ERC。训练资源错误与结构错误分开，只有前者按算子合同回退。

初始化有限重试沿用 B01 默认100。full/grow 各独立抽样，Java grow 为6函数+1终端入口，再抽十特征；目标高度并非实际高度下限。变异新子树固定生成目标上限 mutation_max_height，默认3，实际允许0—3。锦标赛有放回，平分先抽到者保留。节点先抽类别，根包含在该类别；重复叶按位置。各方向独立检查；单侧输出只检查方向1。多次尝试固定父树、最后一次各方向结果整体提交，单树失败克隆各自受体。

每个 trial 在单个 serial spawn 进程内执行，DEAP及定制算子使用该进程模块 random；模拟只消费 B08 Random。每次评估前后校验进化状态未动。父进程不消费模块 random，不在评估间创建新演化进程。run_started → 回调 → START 后计时；完整结果提交后 run_completed 终止计时。未知异常保留链并中止。超时/退出/取消/回调异常结束当前 trial，不继续下一 trial；当前评估 INCOMPLETE，不用于选择。无任意断点恢复。原子 JSON 和 LF 提交 JSONL 沿用 B01。

新协议均 schema_version=1，命名空间独立：

| format/文件 | 权威内容 |
| --- | --- |
| fogsim.evolution-result | trial/seed、训练/验证/测试各状态、代数、真实完成/尝试运行数、候选和选中规则引用、最终进化状态摘要 |
| fogsim.training-result | 全配置多 trial 状态、预算、每 trial 结果、源码摘要 |
| fogsim.candidate-archive | 按每代最优可行者首次出现顺序，按 rule_pair_id 去重；首次及全部出处、原规则与完整 B08 manifest |
| fogsim.selected-rule | 完整 rules/manifest/pair、候选序号/归档身份、验证计划/评估/fitness、trial、树约束、selected_rule_id |
| individuals.jsonl | 每次出生规则/身份/树尺寸/来源；全部待评估，精英与复制不保留成绩 |
| evaluated-individuals.jsonl | 每代每出生身份与完整评估绑定 |
| operations.jsonl | 操作ID/抽样/节点候选位置/尝试/方向合法性/回退及最终父树来源 |
| generations.jsonl | 同代计划、稳定种群顺序、全部fitness、可行数、候选、实际选择/接纳/回退/精英计数、耗时、RNG摘要 |

individual_id 为 trial/g出生代/i连续出生序号；即使结构相同也不同。普通子代在前，实际可行精英在末尾。按当前代同计划分数选择，不跨代比较训练均值。最后一代无繁殖和下一计划切换。无可行代停止并保留已评估种群；不进入验证。

归档先写 candidates/archive.json 并冻结，再统一验证；全验证不可行不运行测试。验证胜者先写 selected_rule.json，再经独立读回、校验身份与 B08 manifest 后测试；测试失败保留该文件且不换候选。单独 evaluate_selected_rule 和 CLI evaluate 不导入 DEAP。

新摘要沿用 B01 canonical 与域前缀：candidate-archive 输入为归档全文（不含archive_id），selected-rule为全文（不含selected_rule_id），evolution-rng 输入为 repr(random.getstate())；semantic-file/trial-semantics 用于复跑比较。所有普通指标有限或null，合法特殊分数仍由B08位串表示。

复现工具逐 trial 比较全部文件，JSON/JSONL按内容规范化；只排除 generations.jsonl 的 duration_seconds。规则、计划、源码、谱系、算子、结果、输入和实际次数不排除。平台/输出位置只出现在顶层观测记录；同配置复跑另检查顶层有效配置与计划一致。

CLI：成功0；领域训练/验证/测试失败1；配置输入错误2；返回式监督中断130；远端未知异常保留 traceback，非捕获退出1。默认拒绝非空目录。train API 返回不可变JSON快照。单独规则评估沿用 B01 原评估API。

监督终止若发生在工作进程提交 trial 快照之前，evolution-result 只含已知 trial/seed、三阶段状态、INCOMPLETE 与 interruption。该分支的 schema 不要求尚未收到的谱系计数、RNG 指纹或实现细节；不捏造完整快照。正常完成与领域失败仍要求完整字段。schema 的此条件细化未改变生产源码或任何模拟/选优输出。
