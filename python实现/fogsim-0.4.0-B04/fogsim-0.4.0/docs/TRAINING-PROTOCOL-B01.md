# S9-B01 协议与工程细化

本文件与 `references/design/fogsim-0.4.0-design.md` 的 S9-frozen-1 配合使用。没有修改 D03、fresh、角色、统计或随机流合同。B01 仅实现固定规则评估；不实现 DEAP 个体、演化、候选归档、验证选优和测试后换规则。

## 配置与冻结

`fogsim.training-config` v1 严格解析器为 `training/config.py`；JSON Schema 在 `schemas/training/`。未知字段在各层拒绝。计数拒绝 bool；所有概率有限非负，权重和绝对容差为 `1e-12`，接受后除以实际和，归一化值进入 resolved config。树最大高度不超过 7，每棵节点不超过 255；初始化 full 最大目标也必须容纳。初始化有限重试默认 100。数值 ERC 为 false。语义版本逐项绑定 D-frozen-1。

默认值全部写入 `resolved_config.json`，额外的 `resolution_root` 仅记录解析位置，不作为可重新输入的配置字段。配置中的三条路径相对训练配置；source-plan 中 config 路径相对各自 source-plan；B08 配置内路径相对该配置。B01 支持两种未来演化模式的配置预检，但不会启动任何演化。

source-plan 为 `fogsim.training-source-plan` v1，严格字段 `format/schema_version/entries`；每条严格字段 `run_id/config`。每个 split 非空，run_id 在计划内唯一。train 必须为 dynamic；validation/test 可作固定输入或 complete reuse_inputs 的受控评估。有限重放的运行覆盖仍须在运行时核验。禁止 verify_reference 和 reference_path 进入本评估器，旧重放 API 保持原合同。

冻结计划每代恰好一份，代号 `0..G-1`。训练 seed 用整数 `b+10000*(g//rotation_period)`，溢出拒绝；旧 `rotate_seed()` 的 Java long 回绕保留。相同周期的计划身份相同，但不提供成绩缓存。验证和测试计划固定，不自动用于选优。跨三类清单检查 `(input_family_id, seed)` 及完整输入内容身份；Python 原生捕获通过重放入口使用时保留同一生成家族和原 seed，不能绕过原生训练清单的隔离。允许同 split 内重复，也允许多个 trial 共享清单。

所有计划保存为不可变 canonical JSON 字符串，`to_dict()` 每次返回独立对象。动态 DAX 原始字节以 Base64 嵌入，摘要按原始字节计算，保留 UTF-16、CRLF 等编码。运行时在临时目录还原，再实际调用 B08 `create_dynamic_context(config, prepared_rules=...)`。固定输入和重放输入也嵌入计划，不依赖原路径。`@frozen-templates`、`@frozen-input` 是持久记录中的位置标记，不作为真实运行路径。

场景中的规则字段冻结为 FCFS 占位；活动规则每次按角色显式安装，并保存 `runs/NNNN/active_config.json` 与原样 B08 manifest。单独的 `rules.json` 严格字段为 routing/sequencing，值就是旧 RuleSpec 描述。B01 不宣称此文件为 B02 的 selected-rule 协议。

## 身份规范

新编码均为：`sha256:` 加 SHA-256 小写 hex；字节是 `fogsim.training.<domain>.v1` 加一个 LF，再接 canonical JSON 的 UTF-8。对象键按 Python Unicode 码点升序；数组保序；`ensure_ascii=False`；无空白和末尾 LF；不做 Unicode 规范化，拒绝未配对代理；浮点有限，采用当前 Python JSON 的十进制表示；signed seed 保留有符号整数。缺失键与 null 不同。Python 精确版本进入 provenance。B08 的规则身份字节编码完全独立，不改动。

| domain | 权威 payload |
| --- | --- |
| `input-family`，dynamic 与 Python native replay | generator=`python-b08-native-v1`、B08 原参数内容摘要 parameter_source（环境配置及全部有效 sampler 分布）、workflow_types、按类型顺序的模板原字节摘要 |
| `scene`，dynamic | input_family 的完整 payload、run（排除两份规则和 trace_enabled） |
| `input-content`，fixed | 完整已验证物理 instance JSON，排除路径 |
| `input-content`，replay | environment/templates/candidates/generation_attempts/initial_state；attempt 排除 observed_acceptance/rejection_reason |
| `input-family`，fixed | mode、input_content_id |
| `input-family`，其他 replay | generator=`recorded-input-v1`、environment、samplers、templates，排除统计/预算/规则；seed 来自原 initial_state.public_seed |
| `scene`，fixed/replay | input_family 完整 payload、有效 run/overrides；排除规则和 trace |
| `plan` | 完整计划文档，排除 plan_id；每条只排除 source_config_sha256，保留有效配置、输入内容、seed、身份、顺序、生命周期、资源和统计合同 |
| `evaluation` | rule_pair_id、plan_id、implementation_source_id、implementation、failure_policy、trial_id、evaluation_sequence、有效 trees 配置 |
| `implementation-source` | 按 fogsim 包相对路径排序的所有 Python 源文件 SHA-256 映射 |

输入家族不含统计目标、事件预算、输出位置、规则和 split；场景不含 seed、规则、split 和输出位置。统计和预算变化不能逃过输入家族重复检查。frozen-plan 导入会校验字段、策略、内容、B08 输入格式并重算身份。测试向量在 `development/S9-B01/identity-vectors.json` 和最终 preflight 计划中。

## 评估、监督与证据

每次评估在一个串行 spawn 子进程中运行全部计划条目；这也是未来单 trial 工作进程的评估组件，B01 没有 trial 代循环。子进程模块级 random 用独立 evolution_seed；模拟继续使用每条 seed 的 B08 Random。父进程不 seed/抽取模块 random。额外进化抽样与模拟输入隔离已由实际子进程故障夹具验证。尚未安装或调用 DEAP。

父进程收到 run_started，执行进度回调，再开始 monotonic 计时并回复 START；预算覆盖该条创建、运行、导出与结果传输，进度回调时间不计入单条预算。每条完成后清除时钟。墙钟保护默认关闭；超时终止整个评估进程，2 秒 join 后必要时 kill。退出/超时/取消/回调异常保存已接收的完整证据，不支持续训。墙钟故障夹具既覆盖极小预算，也覆盖真实 B08 priority 调用期间暂停后被终止。

逐条原 `RunResult/DynamicRunResult.to_dict()` 原样保存，不加训练字段，不将 null makespan 改为罚值。固定结果继续为 B08 原输出 profile；动态实验显式 v2。成功指标必须有限非负。全 K 条成功才用 `statistics.mean` 得到正式 fitness；任一领域失败继续剩余条目并最终不可行；未知异常及覆盖/结果合同错误立即中止，保留 traceback 因果链。

| classification | 评估影响 |
| --- | --- |
| SUCCESS | 计入成功；全部成功才有正式均值 |
| EVENT_BUDGET_EXHAUSTED | 领域失败的独立子类；不可行，继续 |
| DOMAIN_FAILURE | 其他 B08 明确 FAILED；不可行，继续 |
| INPUT_OR_PLAN_ERROR | 配置/来源或 REPLAY_INPUT_EXHAUSTED/DIVERGENCE；INCOMPLETE，异常传播 |
| RESULT_CONTRACT_ERROR | 成功却缺有效 makespan 等；INCOMPLETE，异常传播 |
| PROGRAM_EXCEPTION | 未知程序异常；INCOMPLETE，RemoteEvaluationError 保留远端链 |
| WALLCLOCK_INTERRUPTED / WORKER_EXIT | INCOMPLETE，不能参与选择 |
| CANCELLED / CONTROLLER_EXCEPTION | 保存 INCOMPLETE 后重新抛出调用侧异常 |

`fogsim.individual-evaluation` v1 根字段：format、schema_version、evaluation_id，以及上述 evaluation payload 全部字段；rule_manifest；status/fitness；planned_runs/completed_runs/succeeded_runs/failed_runs/not_run；diagnostic_mean_over_successes、diagnostic_sample_stddev_over_successes、diagnostic_stddev_denominator；failure_rate、failure_rate_denominator、not_run_fraction；runs；interruption；evolution_rng_unchanged。

每个 runs 元素字段：index/run_id/classification/status/makespan/reason_code/reason/result_ref/input_ref/raw_result/input_archive。写盘时引用均相对本评估目录，内联字段为 null；无 output_dir 时返回独立内联快照。原结果和输入可以直接由旧读取器读取。失败/未知异常中的 partial 是诊断，capture.complete 如实标 false；墙钟被杀的当前条目未收到完整结果，不虚构原结果或完整输入。completed 只数收到并分类的成功或领域失败，not_run 包括未完成的当前条目。

FEASIBLE 要求三个成功/完成/计划数相等，fitness 为有限值；INFEASIBLE/INCOMPLETE 的 fitness 为 null。失败率分母 completed；未运行比例分母 planned。成功子集均值、样本标准差仅作诊断；标准差分母为成功数减一。比较器拒绝跨计划与 INCOMPLETE，可行优先，不可行之间相等；具体锦标赛或稳定出生排序留给 B02。

输出：plan.json、provenance.json、evaluation.json；runs/NNNN 下 active_config/result/input；progress.jsonl；failures/ 下 exception/controller-exception/interruption。JSON 原子替换。JSONL 只将 LF 完整行视为提交，尾行截断由 read_jsonl 明确报告。代日志、谱系、候选、选中规则和演化结果协议留给 B02/B03。关闭 trace 不关闭规则、计划、原结果或失败证据。

CLI：成功退出 0，领域不可行 1，配置输入错 2，返回式监督中断 130；未知/远端异常不吞 traceback，未捕获 Python 异常退出 1。Ctrl-C 原样传播，通常退出 130。非空输出目录拒绝覆盖。
