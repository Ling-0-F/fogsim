# 冻结设计实施记录：第 4 步（V16）

日期：2026-11-05（America/Los_Angeles）。开发基线为当前附件 `fogsim-0.2.1-step3.zip`，SHA-256 `6fbb34ffd6c11489a69892583441d068aa26d14c6c84dd65085b21b87fe86c4e`；解压到独立工作副本。上传 ZIP 未修改。冻结设计 §§5、10–12、15、19 的语义保持不变。

## 已实现与范围

| 模块 | 实际作用 |
| --- | --- |
| `tools/java/step4/fogsim/adapter/DynamicExportMain.java` | 独立 fresh 入口，执行原 DynamicSimulation 构造、setup、run 与原生指标；预先用真实 Java WorkflowParser 和 XML 校验映射 |
| `tools/java/step4/fogsim/adapter/DynamicCapture.java` | 清图前复制完整候选、接纳返回后补全 attempt；保存拒绝者、未到达者及未完成者；记录实际事件、评分选择、交错 DECISION/EMIT、触发后状态和原生结果 |
| `tools/java_dynamic_support.py` | 核对 659 份原源码/依赖；独立编译无 overlay 基线与仅增加五处观察调用的版本；保存源字节哈希、源码差异、JDK/编译器指纹及完整命令 |
| `tools/export_java_dynamic.py` | 导出一个指定 fresh 运行，执行无干扰比较；分开写 input/reference/manifest；拒绝覆盖非空案例目录 |
| `tools/dynamic_export_contract.py` | 利用 step1–3 不可变契约审计导出；检查版本、未知字段、精确整数、有限 binary64、引用顺序及公式；核对清单。它不是第 6 步生产重放加载器 |
| `tools/check_step4.py`、测试与示例 | 9 个真实 Java 案例、故意中断检查、73 项 Python 契约测试、独立 CLI 请求示例及自包含最小输入 |

Python `src/` 生产文件与 step3 逐字节相同；没有提前实现第 5 步集中登记、动态事件或统计生命周期，也没有实现第 6 步重放引擎/固定投影和第 7 步清理/完整 CLI。旧固定配置、规则、事件堆与公开接口保持原样。

## 源码事实、实现选择与验证界限

原 Java `MobileDevice.generateWorkflowJob` 在两遍任务/候选构造完成后，先创建 Job、清空每个 Task 的两张边映射，再调用 `SystemState.addJobToSystem`。接纳只在 release>clock 时成功；失败仍已消耗完整本次输入，且不占正式 ID。setup 按设备顺序继续尝试；DAG Arrival 派发全部入口后继续生成。原 DynamicSimulation.run 在下一次循环条件中先归并设备暂存事件，再判断 R。

观察 overlay 的全部变化保存在 `outputs/step4/build/observed/MobileDevice.patch` 和 `DynamicSimulation.patch`：

1. 第二遍结束、任何 mapClear 前，复制完整候选。
2. addJobToSystem 返回后，记录真实接纳结果。
3. 成功候选的 Arrival 已入设备堆后，记录 EMIT。
4. 原 addEvent 入堆后，记录其他 EMIT。
5. 原 trigger 返回后，记录状态，位置在原 run 的保护判定之前。

没有删除或改写原语句，没有新增构造捷径、修改比较器、替换优先级计算或停止条件。记录决策的 FCFS 子类只调用一次 super 的原 nextTaskOption/priorTask，再读取已有 priority；不再次评分。AuditQueue.poll 只调用一次原 PriorityQueue.poll，再读出结果；容量初值、比较器、offer/poll 顺序不变。记录 sampler 装饰器只调用一次原 next。所有原始 Java 源文件和依赖仍保存在 references 中。

无干扰验证分层执行：

- `plain`：完全原 sampler、FCFS、PriorityQueue，且无源码 overlay。原生随机案例比较环境、RNG 序列化末态 SHA、G/B/R、原生指标等，核对审计包装本身不改变运行。
- `baseline`：无源码 overlay；只使用单次委托的 sampler/规则/堆审计包装，获得实际抽样、事件顺序、决策及最终状态。
- `minimal`：相同原动态路径加五处观察；候选/attempt/状态仅留摘要，不写完整输入。
- `full`：相同观察调用，另保留独立副本并写文件。与 baseline 比较逐项样本、事件、决策、最终状态和 RNG 末态；与 minimal 比较全部候选、attempt、交错动作和触发后状态摘要。

边界 fixture 显式带 `origin.fixture_kind=scripted_boundary`：装饰器先消费一次真实 sampler 再用预先给定的间隔覆盖业务返回值。它用于构造精确 0 间隔和极远的未来到达，不称为原指数分布自然抽到这些值，也不与无替换的 plain 模式混比。其余 5 个案例直接消费原 Java 随机采样，无业务覆盖。

原始 Java 22 份 DAX 的既有来源记录仍保留；本轮再次将 647 份 Java 源码和 12 个非 javadoc 依赖，与当前上传 Java ZIP 逐文件核对，共 659 份一致。没有联网查找或读取项目之外的私人文件。单独的实施顺序 PNG 当前未提供，实施顺序采用用户本轮给出的表格；不影响 V16。

## 文件契约与最小案例

每个正常捕获案例有以下独立文件：

| 文件 | 内容及边界 |
| --- | --- |
| `input.json` | format=`fogsim.dynamic-replay`，schema_version=1；origin、fresh 初始 B/seed/run_index、有效配置、单位、有序环境/模板/候选/attempt、capture；不含停止时间、完成 ID 或参考决策 |
| `reference.json` | 独立版本参考：事件顺序、已有评分/选择、实际 DECISION/EMIT 交错、每次 trigger 后状态、最终状态和 Java 原生结果；不参与输入来源决策 |
| `manifest.json` | 输入、参考、请求、原始输出、DAX、副本及构建来源的 SHA；仅排除自身，避免循环哈希 |
| `sources/` | 实际使用的 XML 副本和构建来源清单，便于完整复核；执行输入建图本身不需要它们 |
| `plain/`、`baseline/`、`minimal/`、`full/` | 当次命令、stdout/stderr、审计/观察原始结果；plain 仅在未覆盖业务输入的案例存在 |

`tests/fixtures/dynamic_v1/input.json` 是来自最小链案例的独立输入；测试将它单独放到空目录，仅凭本文件建立完整 InputArchive 并审计，不读取 Java、XML 或 reference。输入含所有任务、边值、累计量、选项时长和原 XML ID。单独输入的实际调度执行属于第 6 步，当前不冒称已执行。

全量案例和原始证据在 `outputs/step4/cases/`。最小链有 2 次尝试、7 条事件、3 次决策；停止时第二个工作流仍未到达。`pending_at_stop` 刻意保留两个未到达者；拒绝案例也保存了完整候选及边值。参考检查核对所有 EMIT 数量等于已处理事件加最终待处理事件，每个 after_arrival 指向真实 Arrival，最终 Java 的边映射为空而完整输入归档仍有原值。

JSON 不截断小数，不输出 NaN/Infinity 字面量。公开 Java seed 使用精确 signed64 JSON 整数；不经浮点中转。Double.toString 到 Python JSON 的 binary64 值保持不变。导出后的 environment.fingerprint 仅将哈希序列化规范化为现有 EnvironmentSnapshot 算法；原始 Java 文件保留于 full/input.json，不改任何资源参数、边值、累计或 PT/UT/DT。公式审计不会回写时长。

未达到统计目标时，reference 原生返回将正无穷编码为 `POSITIVE_INFINITY`、Double.MAX_VALUE 编码为 `DOUBLE_MAX_VALUE`，保留 java_text 和适用的有限 value；不把它们写入输入或伪造 Python 成功指标。capture.complete 只指捕获完整，不代表目标达成或无限输入流。

full 每次完成接纳观察后原子更新 `capture.complete=false` 的检查点。进程或构造中断时可留部分输入；完整验收明确拒绝。reference/audit 写成功且原 run 返回后才写 complete=true；完整清单最后生成。没有完整清单、写出失败或部分文件不构成完整验收通过。

本工具当前开放原 standardFull 的有效 sampler 参数、类型范围、设备/服务器数、local、N/W、signed64 seed 和 fresh 操作。任意 sampler 配置、其他规则、reset/rerun/rotate 的导出录制不是本轮已验证范围；后续扩展需显式增加契约。该约束不改变既有设计语义。

## 实际运行与结果

本次为 CPython 3.12.14、pytest 9.2.0、Ubuntu OpenJDK 17.0.20+8。运行环境的 java 需要显式库路径；常规 JDK 17 可直接使用 --java 或 FOGSIM_JAVA。无独立 javac 时使用现有 jdk.compiler 模块，实际命令及模块字节哈希均在构建清单。

在项目根执行的最终命令：

```bash
PYTHONPATH=../../test-deps:src python -m pytest -q tests/unit/test_dynamic_export.py --junitxml=outputs/step4/contracts.xml
PYTHONPATH=../../test-deps:src python -m pytest -q tests/unit tests/integration --junitxml=outputs/step4/python-regression.xml
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server python tools/check_step4.py --output outputs/step4
```

临时 test-deps 位于交付工程外，不作为运行依赖打包。常规环境安装 `.[test]` 后可省略 PYTHONPATH。

| 检查 | 结果 |
| --- | --- |
| 新增 Python 契约 | 73 passed，0 failed/errors/skipped |
| Python 单元及集成 | 590 passed，0 failed/errors/skipped；含旧 CLI/repeat、14 个固定配置完整结果和轨迹 |
| V16 Java | 9 案例无干扰及完整性检查通过：7 个达标运行、2 个原生未达标边界；后两者标 EXPECTED_DIFFERENCE_CONFIRMED，不计正常轨迹通过 |
| 每种观察模式实际总量 | 96 次尝试，92 次接纳，4 次拒绝；1,128 条已处理事件，1,008 次决策，6,660 次 sampler 返回 |
| plain 原入口对照 | 5 个原生随机案例通过；包含真实标准 DAX、多类型、signed64 两端点 |
| 故意中断 | 第二台设备初始化时脚本耗尽，留 1 次完整尝试；complete=false，完整门禁拒绝，无伪造 reference；EXPECTED_DIFFERENCE_CONFIRMED |
| 来源完整性 | 当前上传 Java ZIP 的 659 个源码/依赖字节一致；Python src 与 step3 字节一致 |

开发时修正了观察 anchor 匹配到历史注释的问题，现要求完整行/明确分支唯一匹配，保存并核对仅追加观察的 diff。首次新增负例发现设备未知字段在字段校验前落到 dataclass TypeError，已将字段检查前移，保持 InputError 预期。未改测试预期或原调度语义。

单例导出（选择新的输出目录）：

```bash
python tools/export_java_dynamic.py --java /path/to/jdk17/bin/java \
  --request configs/examples/step4_java_export.json --dax-root dax --output outputs/my-java-input
python tools/check_step4.py --java /path/to/jdk17/bin/java --output outputs/step4-rerun
```

案例目录要求为空，避免把旧 input/reference 与新一次失败输出混合。复跑应给新目录；最终正式 Python CLI 仍待第 7 步。

## 继续开发

没有发现必须调整冻结设计的问题。本轮格式字段的具体拼写和工具入口是既有契约的实现具体化。当前证据只证明这组 Java 原动态路径的完整导出与观察无干扰，**不是 Java/Python 动态调度一致性**，不是任意规则/边界的普遍证明，也没有测量观察器性能收益。

第 5 步继续复用 step3 的 prepare_random_input、sample_environment、generate_workflow_input、materialize_workflow，接入集中接纳、Arrival、G/B/R 统计与 Context 生命周期，落实 V09–V15。随后第 6 步消费本轮自包含 input，逐调用核对来源位置、事件内动作与原生统计，并实现覆盖不足诊断及固定投影（V17–V19）。显式边清理、完整 CLI/批次及完整 V01 留到第 7 步，未标为已实现或已验证。

当前开发快照文件指纹为 `STEP4-FILES.json` 和 `outputs/step4/current-files.json`；本轮验证汇总为 `outputs/step4/current-validation.json`，相对 step3 的文本补丁为 `CHANGES-STEP4.patch`。旧 RELEASE/STEP1–3 清单保留为各阶段历史证据。当前包未走正式 release 门禁，不能称为最终完整验收版。
