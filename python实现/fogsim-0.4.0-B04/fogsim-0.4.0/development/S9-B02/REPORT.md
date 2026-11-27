# S9-B02 批次报告

**本批单树闭环验收通过。到此停止，不进入 B03。** 目标版本0.4.0；设计S9-frozen-1。权威机器结论：outputs/step9/B02/acceptance.json。

唯一累计代码基线：fogsim-0.4.0-B01-source-dedup.zip（42405568字节，SHA-256 6c2e6d4f65c3be158f9090bda3413f778f0e4f745eae02f89b1b8f6c9843f8f2）。原B01附件未修改，没有采用历史聊天中的B02开发副本。

## 实际实现

- DEAP 1.4.4精确依赖与传递依赖锁定、轮子和离线重装；PrimitiveTree/Fitness实际使用；定制Java grow/full、锦标赛、节点抽样、单树交叉/变异/复制。适配保留有序结构、重复叶、常量位模式和B08身份，独立克隆树及节点。
- 只演化routing，sequencing始终显式FCFS。每trial一个串行spawn进程；全部条目沿用B01真实B08 fresh、D03、等权均值、RNG隔离、计划/划分和监督合同。精英/复制重评、普通子代在前精英在末、末代停止繁殖及轮换。
- 同代候选按rule_pair_id去重并保留首次和全部出处；先冻结候选，再统一验证。先冻结selected_rule.json并经独立读回，再执行固定测试。测试失败不会换候选。
- train API/CLI、谱系/方向合法性/来源/实际算子计数/逐评估原结果与输入、可独立加载的最终规则。旧API、CLI、固定、动态、重放、身份与特殊数值保持。

## 最终检查与数量

| 范围 | 实际结果 | 证据 |
| --- | --- | --- |
| 最终训练专项 | 99 passed，0失败/错误/跳过；其中B02为38项、B01为61项 | unit-final.xml、commands/unit-final.*、cases-final/ |
| 独立恢复副本全量新旧回归 | 5908 passed，0失败/错误/跳过；155.278s | regression-final.xml、commands/regression-final.*、legacy-final/ |
| JDK17/ECJ局部受控对照 | 45/45；原HalfBuilder、TerminalERCUniform、TournamentSelection、KozaNodeSelector、CrossoverPipeline、MutationPipeline、MultiBreedingPipeline、SimpleBreeder及末代evolve实际执行 | java-final/ |
| 单树首跑＋同配置复跑 | 4个trial，416条模拟；两对应trial的全部952份语义文件一致 | single-first/、single-repeat/、reproducibility.json |
| 独立冻结规则评估 | 新增2条模拟；结果及输入逐字一致，fitness=594.0162104214817 | independent-selected/、independent-selected-check.json |
| Schema | 38份正常/领域失败/程序异常/监督中断样本通过 | schema-final.json |
| 未装DEAP及输出保护 | 旧固定运行/选中规则加载可用；缺训练依赖退出2；现有目录拒绝覆盖退出2 | no-deap.json、output-protection-check.json |
| 来源/历史保留 | 分发11662文件校验；三组3373成员恢复；B08审计3732成员；B01历史证据原字节 | preparation/、b01-retention.json、b08-source-retention.json |

## 闭环预算与结果

正式配置为12个体×4代×每代2条运行；两seed50001/50002；每trial最多4候选×2验证、最终2测试。两个trial预先共享同一套冻结计划。资源1本地+1edge，recorded=2/warmup=1，max_events=2000，墙钟默认关闭；trace全部保存。

| Trial/seed | 候选数 | 训练 | 验证 | 测试 | 每次实际 | 验证均值 | 测试均值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| trial-0001/50001 | 2 | 96 | 4 | 2 | 102 | 516.423053552757 | 594.016210421482 |
| trial-0002/50002 | 4 | 96 | 8 | 2 | 106 | 495.097177427418 | 594.016210421482 |

首跑208，复跑208，正式合计416≤424。不同seed不是复跑的替代；对应seed单独比较。两个trial首跑分别观察1421与1548次真实多候选routing决策，复跑相同。受控PT与(- 0 PT)案例另实际改变多候选选择与makespan，不能由配置字符串代替。

修复前另有208条早期开发闭环及416条CLI边界修复前的完整首跑/复跑，分别保存在initial-single-first/与pre-cli-single-*，额外624条不计入正式416/424；本轮上述12×4×2配置的完整运行实际共1040条（正式416；修复前额外624）。另有独立加载2条，最终组件训练层有记录completed_runs=81（其中11条领域失败）；Java末代对照的Python真实小循环12条。其余早期组件、故障与三次旧回归各自另列在recorded-simulation-counts.json。该清单只统计持久化评估文档中的completed_runs；旧API未统一插桩，故不声称全部旧回归的模拟总数，不把测试项数当作模拟运行数。没有执行双树/848次总门禁或论文规模训练。

## 分项范围与后续

| 门禁 | 本批覆盖 | 后续 |
| --- | --- | --- |
| S02/S08/S09 | 单树适配/生成/选择/独立回退/尾部输出/多次尝试/精英/计数/真实决策/闭环通过 | 双树对应项B03 |
| S11 | J01/J02/J03及单树交叉变异、J06算子接纳数/精英/末代实际ECJ对照；B01 J05证据只读保留 | J04特殊双树及其余双树项B03 |
| S12/S13 | 通用归档、统一验证、测试前冻结、全验证不可行/测试失败不换候选；单树两seed及完整配置复跑通过 | 双树复跑B03 |
| S14/S15 | 高度7/8、节点限制、变异实际0—3、有限重试、事件失败、墙钟、退出码、回调/程序异常链、独立规则、CLI和证据通过 | 后续扩展影响时重验 |
| S16 | 本批必要全量兼容及未装DEAP检查通过 | B04最终联合审计 |
| S10/S17 | 未执行 | 双树B03；最终自运行模板及交付B04 |

## 失败、修复和已知边界

1. unit-dev初轮23通过/6失败：受控夹具把深度6函数误作深度7叶、grow抽样缺一入口、决策名大小写。修正夹具后29通过。后续补四项至33，再增加五项CLI非对象输入边界，B02最终38项。原始失败日志保留。
2. Java适配器前两轮存在原类访问/抽象方法编译问题，第三轮重复叶用equals查找误报位置，改为对象身份。原源码未修改；失败编译及真实差异均保存。java-dev4与正式java-final均45/45。
3. components-pre-final一次收集错误来自新增严格校验时的语法编辑，修复；随后一次断言把浮点累计0.8+0.15误当精确0.95，改用真正阈值外受控值。未改变已冻结算子权重。
4. initial-unit-final的93通过/1失败发现EOF可先于退出码可读的真实监督竞态：训练已经中止，exitcode暂为null。修复为join后补录实际退出码；重新冻结生产源码并重跑正式专项、Java、首跑/复跑及全量回归。修复前全回归恰未触发该竞态（5903通过），不用于替代修复后的验收。
5. schema-initial发现三个早期监督中断快照没有尚未提交的完整trial字段。仅补schema条件分支与说明，不伪造未收到的RNG/计数；38样本重验通过，生产Python字节未改变，差异明确登记。
6. Java与Python不要求原生RNG序列、同seed种群或曲线相同。Java配置规模/深度计数差异按冻结设计声明。本批不改变B08双零保护等既有数值边界。
7. 不支持任意断点续训；被杀时只保留已提交/已接收范围。合法特殊规则分数不作为领域失败。没有使用测试集更换候选或调参。

## 交付与回滚

累计主包fogsim-0.4.0-B02.zip，顶层fogsim-0.4.0/。随包：全部当前源码/测试/配置/schema、设计、锁定轮子、文档、B01证据及B02新增必需证据；完整文件清单S9-B02-FILES.json，新/修改清单S9-B02-NEW-FILES.json，文本补丁CHANGES-S9-B02.patch，实施文件索引development/S9-B02/changes.json。

继续采用来源去重和临时清理：原Java/history/rollback按原SOURCE-INDEX.json从已提供两来源恢复，原src不会覆盖当前src。编译class、安装目录、缓存和pytest current链接不重复打包；新源码/补丁/共同输入/原结果/失败和中断证据保留。完整历史审计需原两来源；JDK17使用已记录版本或另行通过实际对照的完整JDK17。旧B01工具/清单只描述B01，本批校验使用build_s9_b02.py verify。

独立解压复核、ZIP摘要和全部交付文件摘要在外部verification.json与SHA256SUMS。报告本身不包含ZIP自摘要。当前无未解决的B02关键来源或必需门禁阻塞。回滚使用本轮原B01-source-dedup附件另解压，或历史来源恢复工具；不覆盖已验收包和历史证据。到此结束，不自动进入B03。

补充：本批当前wheel为development/S9-B02/dist/fogsim_reproduction-0.4.0-py3-none-any.whl（160449字节，SHA-256 ed9b99a22b01818544ea50ecbf3df08480da996a0e1464995d9f1f4e385e9659），独立安装后在未装DEAP的隔离路径成功加载已选规则并提供train入口。构建生成的build/与egg-info已按临时清理规则删除，最终源码冻结再次核验无差异。

最后CLI复核确认：新selected-rule分派在非对象规则文件上会先触发AttributeError、退出1。已用类型保护恢复输入错误退出2，新增null/list/integer/bool/string五个受控入口案例；随后重新冻结生产源码并完整重跑正式99专项、5908联合、45Java及416闭环。此修复只改变异常输入分派，不改变演化/调度算法。前一套416条因源码绑定变化归入额外执行，原结果保留。

独立规则再评估数量：当前包内正式独立加载2条、最终独立解压再评估2条；前一版独立加载/解压另4条保留为历史开发复核（pre-cli-independent-selected及pre-cli-delivery-verification.json），不混入正式416闭环。
