# S9-B01 批次报告

日期：2026-11-14（America/Los_Angeles）。目标版本 0.4.0；批次 S9-B01；设计 S9-frozen-1。唯一实现基线为 B08，原 ZIP SHA-256 `61c4b14bf2305a9bbc2821ebbe85949e27ba45c8472005d8e5bfe7cbba967ecc`。

**本批评估层门禁通过。** 此结论只覆盖第 14 节 B01，不表示第 13 节 S01—S17 全部完成。正式机器结论、逐项范围、未执行项和源码绑定在 `outputs/step9/B01/acceptance.json`。发行包另经独立解压复核，外部交付校验报告绑定最终 ZIP 摘要。

## 实际完成

- 新建独立 training 层：严格配置与默认值展开、三类计划提前冻结、signed64 seed 与 10000 步长展开、输入家族与完整内容防泄漏、规范化身份与测试向量。
- 固定规则对通过真实 B08 执行。动态每条新建 context；固定和重放使用 B08 原引擎。计划嵌入 DAX 原始字节或完整物理输入，活动配置与 PreparedRules 严格一致。
- 全计划成功后 `statistics.mean` 等权汇总。领域失败继续收集其余条目并使评估不可行；事件预算单列。覆盖/输入缺陷、结果合同错误与未知异常中止并保留异常链；不将成功子集均值用于比较，不修改原 makespan。
- spawn 工作进程、调用侧 RNG 不污染、模拟与进化流隔离；父进程监督墙钟、工作进程退出及回调异常，完整结果原子保存，JSONL 提交/截断可识别。
- validate/evaluate API 与独立 CLI、树资源准入、原结果/输入/活动配置、failure/interruption/provenance 证据。旧功能在未安装 DEAP 时继续可用。
- Java 独立生命周期实跑：新建、run、rerun、reset、rotate 的操作和运行边界；自然 B 更新、sentinel B 保留和 Java long 回绕。单独保存源码、观察补丁、输入 DAX、配置、命令、编译环境、原输出及检查。

模块拆分、规范字段与 schema 详见 `docs/TRAINING-PROTOCOL-B01.md`；变更清单和独立补丁为 changes.json、根目录 CHANGES-S9-B01.patch。

## 实际检查结果

| 项目 | 实际结果 | 当前证据 |
| --- | --- | --- |
| 最终新旧联合 pytest | **5858 passed，0 failed/error/skip**，132.58 s | identity-final-regression.xml/txt |
| 最终 B01 专项 | **61 passed，0 failed/error/skip**；另跑并保存每条组件原结果/输入 | unit-identity-final.xml/txt、cases-identity-final/ |
| JDK17 生命周期 | **68 项通过**，三种独立案例 | lifecycle-final/ |
| 固定 GP 完整兼容场景 | **20/20**，双方实际执行与比较 | regression-fixed/summary.json |
| Java 动态完整场景 | **3/3** | regression-dynamic/summary.json |
| Python 原生捕获与独立重放 | **3/3** | regression-native-retry/summary.json |
| 固定规则正式 CLI 评估及同计划复跑 | 两次各 2 条成功，均值 **438.51263927373697**，语义输出/原结果/输入相同 | identity-smoke、identity-smoke-repeat |
| 手算多场景汇总 | 1、1、10，逐运行等权均值 **4**，样本标准差 sqrt(27) | cases-delivery/test_real_fixed_multiscene… |
| Schema 样本验证 | config/source-plan/plan/evaluation 四类验证通过 | schema-validation.json |
| B08 字节保留 | **3732 文件检查，无意外差异**；版本/README/版本断言改动显式登记 | source-retention.json |

表中全部路径除注明外相对 `outputs/step9/B01/`。61 项是专项独立复跑，不和 5858 相加冒充一轮测试数量。组件测试、故障注入、Java 对照与旧回归另计，不将测试项目数当作模拟运行次数。

## 分项范围与后续

| 门禁 | 本批状态与证据边界 | 后续部分 |
| --- | --- | --- |
| S01 | B01 范围通过：严格配置、计划、泄漏、溢出、未知字段 | 演化执行时绑定继续在 B02/B03 核验 |
| S03—S06 | 本批评估公式、失败、特殊数值、fresh 隔离通过 | 种群代循环相关行为在 B02 |
| S07 | 实际 spawn、额外进化抽样/模拟与调用侧 RNG 隔离通过 | DEAP 内置组件调用在 B02 |
| S11 | **部分覆盖：J05 生命周期实跑通过** | J01—J04、J06 算子/演化对照在 B02/B03 |
| S14 | **部分覆盖：高度 7/8、节点预算、事件预算、B08 评分中的墙钟终止、进程退出通过** | 变异新子树实际高度 0—3 在 B02 |
| S15 | **部分覆盖：validate/evaluate、活动配置、原运行、失败、进度及输出保护通过** | train、谱系、候选、selected-rule 在 B02/B03 |
| S16 | 本批必要新旧回归与未装 DEAP 检查通过 | B04 仍须最终联合审计 |
| S02/S08/S09/S10/S12/S13/S17 | **未执行本项完整门禁** | 按 B02/B03/B04 分批完成 |

本批没有安装/锁定实际 DEAP 及传递依赖，没有单树或双树演化、真实精英重评、候选归档、验证胜者、最终冠军规则或论文规模训练。固定规则复跑不能代替 S13 两模式闭环复现。**848 次闭环预算未执行，演化 trial 数为 0。**

## 工程问题、修复与限制

1. 输入 B08 包缺失旧 B07 测试依赖的 development/b07 夹具与证据。先保存原失败，再由包内原生成器重建夹具并实际新跑；新证据明确标本轮，不虚构历史恢复。独立累计包附其默认路径副本，可直接运行旧测试。
2. 初轮完整回归的 19 failed / 48 errors，以及一次混合源码协议造成的 13 failed，全部原日志保留，不能作为通过依据。最终是在冻结生产源码后实际重跑通过。命令与差异原因见 COMMANDS.md。
3. 旧回归工具默认写历史 output 路径。本轮已将新运行另存 legacy-rerun*，再恢复原 B08 每个历史成员并逐字节审计。原 references、outputs/final、development/b08、历史验收和原 B08 ZIP 不改。
4. Python 与 Java 的 RNG 样本不要求同值；比较生命周期状态合同。主评估每条 fresh，不复制 Java reset 状态复用。旧旋转 long 回绕和新计划溢出拒绝分别验证。
5. 墙钟中断仅保存父进程已收到证据；未完成条目明确 capture_complete=false，不虚构完整轨迹。无任意断点恢复。API spawn 建议通过脚本或 CLI 使用。
6. 本批精确小案例预算为动态每条 max_events=2000，recorded=2/warmup=1；故障用 1 事件预算、0.2 s 受控墙钟以及极小墙钟保护测试。验证/test 各一条为 B01 固定评估范围的工程细化，不宣称完整训练 smoke。

当前没有未解决的 B01 关键文件或必需门禁阻塞。剩余事项属于明确的后续批次，不自动进入 S9-B02。回滚时将 rollback 原 B08 ZIP 解压到独立目录；不要覆盖本包来伪造历史记录。

交付前身份审计另增加一项跨入口泄漏检查：Python native 捕获改用 replay 入口后，仍与同生成参数、模板和 seed 的 train 计划冲突。最终已按此合同重新生成计划、评估/复跑并重跑 5858 项联合回归，61 项专项通过。早期 preflight/accepted-smoke 只保留作开发证据；正式身份向量与交付证据使用 identity-*。
