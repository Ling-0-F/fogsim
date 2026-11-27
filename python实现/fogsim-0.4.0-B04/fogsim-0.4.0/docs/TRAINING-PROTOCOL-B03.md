# S9-B03 双树协议与工程细化

沿用S9-frozen-1/D-frozen-1以及B01/B02身份、计划、失败、监督、候选归档和selected-rule v1。训练配置原有dual_tree模式现可执行。单树算法及显式FCFS sequencing保留；单树与双树不同回退分别实现，不能混用。

DualIndividual.trees严格含两棵独立DEAP PrimitiveTree：0=sequencing、1=routing；genome返回该有序对。prepare_dual通过明确角色构造B08 RuleSpec。单个体仅有一份领域评估和DEAP Fitness，判断可行性仍由D03主导。每棵树分别限制高度≤7、节点≤255，允许完整基因组共510节点。数值ERC搜索仍关闭，固定规则适配保留常量位模式。

初始化分别调用B02生成器，记录tree_initializations.sequencing/routing。双树操作在dual_operators.py，单树operators.py保持B02原字节；根节点、节点类别、Java grow与重试终止复用B02机制。dual交叉先只抽一次slot，固定父代、slot进入所有尝试；各方向合法性独立记录，最后一次整体提交。接纳数按真实输出方向记，回退完整克隆对侧父代。合法方向的未选角色整树交换；失败方向两角色都是同一对侧父代来源。变异只抽一次slot，未选树独立克隆；多次尝试不轮换slot。

操作记录扩充tree_slot、other_role（交叉）、genome_mode、whole_tree_swap_directions，以及sources[].trees中两个角色的精确来源。成功点替换记录recipient/donor、位置及对应出生ID；整树交换记录parent与ID；失败记录complete_pair_fallback、对侧parent与ID。精英和复制也保存两个角色完整来源。birth日志依旧指向operation_id和输出方向，操作/出生/评估可交叉核对。

通用evolution循环按mode选择基因组构造与算子；归档、固定验证、规则冻结/独立读回/最终测试不另建双树分支。双树实现标识fogsim-training-dual-B03-v1；单树既有实现标识保留，完整源码摘要自然随本批代码改变。协议schema版本不变，原字段的身份payload和含义不改。新出生roles映射0=sequencing、1=routing，trees按角色保存，其他字段形状同B02。

B02完整配置的历史成绩不重新验收；改动后的兼容测试产生B03新证据，保存在新目录。B03双树复现比较完整trial语义文件，只排除generations.jsonl的duration_seconds；规则、角色、来源、计划、成绩、次数、原结果与输入不排除。
