# S9-B04 协议补充

S9-frozen-1与D-frozen-1不变。B01—B03规则、计划、候选、谱系、领域失败与结果协议原语义不变。新增fogsim.training-preflight schema_version=1，仅为成本/环境事实，不计训练或模拟通过。versions.dependencies可为null，表示当前环境未安装该包；validate仍可独立运行。retention与resolved_config一致。

processed_event_upper_bound=total_upper_bound×所有冻结条目max_events的最大值，仅当每条预算均存在才给出；包含候选上界，非性能或存储估计。closed_loop_budget按trial数×（population×各代条目数之和＋generations×验证条目数＋测试条目数）。候选去重可能减少实际模拟，异常/中断另计。

train API在创建输出目录后、启动工作进程前保存preflight.json；CLI train在调用前打印同内容并flush。validate只保存预检、resolved_config与展开计划。tools/run_s9_training.py默认调用validate，--execute调用train；输出保护沿用旧合同。

独立evaluate_rule_pair的EOF分支在进程join后补记WORKER_EXIT.exitcode，与train监督器一致；不中断分类、不改已提交运行、数值和身份payload。完整源码摘要因此变更。生成新的训练/评估ID记录当前摘要，旧证据保留原摘要；不把旧闭环伪称为当前源码的新执行。
