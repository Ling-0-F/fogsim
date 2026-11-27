# S9-B04 最终批次报告

**B04 必需验收范围通过，S9 的 B01—B04 累计实现完成。** 目标版本0.4.0；S9-frozen-1 / D-frozen-1。权威机器结论：outputs/step9/B04/acceptance.json。独立解压/安装的交付复核单列在外部verification.json；完整交付须含分包索引列出的四包。

## 基线与完成内容

唯一当前代码基线为已提供的fogsim-0.4.0-B03.zip。当前沙箱未保留上次B04开发副本，因此从B03接续；不假定历史草稿已落盘。B01—B03既有验收结论沿用，没有重新执行其原ZIP确认旧结果。前置文件齐全，无需补传。

- S17：单/双树可编辑大规模模板、默认只预检的tools/run_s9_training.py，显式--execute才训练。预检列出完整模拟上界、事件预算、档案/trace策略、Python/依赖版本；train在模拟前显示并保存同一报告。普通validate不模拟、不消费进化RNG。
- 运行手册docs/RUNNING-0.4.0.md，含分包解压、离线安装、旧功能/单双树/API/CLI、独立规则加载、结果/失败读取、退出、预算和后续自运行说明。
- 独立evaluate_rule_pair监督器：EOF可能早于exitcode可读，在join后记录最终退出码。新增受控时序与实际os._exit(42)案例；不修改模拟/演化算法、规则身份、原结果协议或领域失败分类。
- B04新旧联合回归、旧149项合同关联审计、当前协议/引用审计、源码/历史保留审计、DEAP缺席及当前wheel独立安装/加载。
- 最终完整本地分发恢复索引三组3373成员，提供累计源码、全部原证据、依赖和前批原交付回滚包；不依赖旧沙箱路径。JDK17按既有约定不随包，精确获取信息保留。

## 实际检查

| 范围 | 结果 | 证据（相对outputs/step9/B04） |
| --- | --- | --- |
| 训练专项（当前生产源码） | 147 passed；0失败/错误/跳过，40.704秒 | unit-final.xml，cases-final，commands/unit-final.* |
| 独立恢复副本新旧联合回归 | 5956 passed；0失败/错误/跳过，194.174秒 | regression.xml，regression-cases，commands/regression.* |
| 旧冻结合同审计 | 149项，0 unresolved；关联当前实际执行测试，不等于重做全部历史Java实验 | contracts-audit.json |
| 当前正常/故障/中断/预检协议 | 828份schema通过，696个原结果/输入引用存在 | schema-audit.json |
| B03累计保留/影响审计 | 39520个旧清单成员，只有登记的5个修改；旧证据无变化 | source-audit.json |
| 大模板 | 两模式均PREFLIGHT_ONLY、0模拟；每模式单次上界50510 | preflight-large-single / preflight-large-dual |
| 新入口实际执行 | 单树与双树各2个体×1代×1seed，每模式8条；专项和联合回归分别执行 | cases-final与regression-cases的launcher案例 |
| 源码独立冻结规则评估 | 两模式共4条成功，无DEAP | independent-selected-check.json、independent-selected-* |
| 当前wheel独立安装评估 | 两模式共4条成功，无DEAP；所有包内.py与当前src相同 | wheel-check.json、wheel-selected-* |
| 未装DEAP | 固定内核及两模式规则加载成功；train退出2且不创建输出 | no-deap.json、commands/no-deap-* |
| 旧回归新增原结果 | 262份另存，旧原件不覆盖 | legacy-current-index.json、legacy-current/ |
| 源码冻结 | 342个源码/测试/工具/配置/schema/合同/锁文件，无未登记变更 | source-freeze.json |

独立加载的**原模拟结果逐字相同**；fitness和规则身份相同。输入档案仅/origin/code_dependency_fingerprint因B04源码变化而不同：核对新值确为当前源码指纹后，严格比较其他全部字段相等。原始新旧档案均保留，不改旧字段以制造逐字相同。该项是跨批兼容，不冒充同源码复现。wheel来源与源码来源指纹一致。

S11沿用已实际运行的B01生命周期68项、B02局部算子45项、B03双树局部38项，合计151项历史Java受控检查；本批没有重新计作新执行。S13沿用B02单树416条、B03双树424条，合计840，低于848上界，均已包含原首跑及完整复跑。相关演化/算子/选择/计划/worker/runtime与旧模拟器保持B03字节；本批改动的监督/预检由新的专项、入口、独立评估和联合回归覆盖。旧source_id保留原值，不声称旧闭环绑定B04源码。

## 次数与资源

本批不重跑正式12×4双seed闭环，不启动大规模模板。每个大模板为100个体×50代×5seed，每trial训练10000、验证最多100、测试2，合计50510；max_events=2000，粗略累计事件上界101020000。两模板沿用B03工程小场景，仅为可编辑规模入口，不是论文实验参数，也无时间/内存/磁盘保证。

recorded-simulation-counts.json按lane记录落盘评估的completed_runs：最终专项150、联合回归150、最终源码独立加载4、wheel加载4；早期组件16+16、首次交付检查8，合计348条记录化已完成运行（其中专项/回归含预期领域失败）。这不是全模拟器插桩总数；组件内存评估、旧API和Java探针另有执行，不能把5956个测试等同模拟数。最终独立解压额外执行数见外部verification.json，不混入上述348条。失败和INCOMPLETE记录均保留。

## 失败、工具修正与冻结关系

1. 初始环境缺pytest，两次命令在收集前退出；日志保留。改用本次独立虚拟环境，训练依赖沿用精确锁，测试依赖新增单列wheel/摘要锁；环境目录不入包。
2. 新增6项检查首轮5通过、1失败：受控EOF在join前的exitcode为null。修复生产监督器后6项通过，随后147项专项和5956项联合回归通过。失败现场在cases-dev-venv。
3. 交付检查工具在8条评估已完成后，因相对wheel路径格式化而ValueError；修正为resolve后取相对路径。第二次8条评估结果均成功，但审计最初要求输入文件逐字等同，因真实源码指纹不同而报告false。改为显式报告唯一来源字段差异、核对当前指纹并严格比较其余输入，使用--audit-existing重审既有本批输出，**没有为修正审计再模拟**。
4. 两次工具细化均仅修改tools/check_s9_b04_delivery.py；生产源码、测试、配置和schema自正式专项/回归起无变动。初版和中间冻结快照、原日志与失败摘要均保留；最终冻结重新记录工具摘要，受影响交付工具已通过。regression-code-binding.json逐项绑定影响面。

## 完成矩阵与交付

S01—S17必需范围均完成，逐项定位见docs/ACCEPTANCE-S9-B04.md。B01—B03的验收与Java/复现原证据作为继承范围明确标记，当前B04新检查另列。没有未解决的关键来源或必需门禁阻塞。

主包fogsim-0.4.0-B04.zip；evidence包含全部原结果/输入/失败/Java证据；references包含已恢复三组来源和离线依赖；rollback包含提供的B01去重、B02/B03原包与其附件。统一顶层fogsim-0.4.0/，解压至同一新目录，各包文件路径不重叠。分包索引、完整清单、SHA-256和独立解压复核记录随交付。当前wheel：development/S9-B04/dist/fogsim_reproduction-0.4.0-py3-none-any.whl。完整回滚不需重造历史包。

未执行/不承诺：论文规模训练和论文表格/数值复现、数值ERC、并行加速、任意中断点恢复、任意输入Java等价；旧两个可选大型native固定投影仍未执行且非必需最小门禁。JDK17为外部环境；离线轮子覆盖CPython3.12/Linux x86_64。到此完成本批，不自动执行任何大规模实验。
