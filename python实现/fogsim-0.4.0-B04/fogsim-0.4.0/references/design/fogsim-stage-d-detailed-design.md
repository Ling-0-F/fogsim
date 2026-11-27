# fogsim 阶段 D：固定 GP 规则执行详细设计

**文档版本：D-frozen-1｜状态：已确认冻结｜冻结日期：2026-11-06**  
**基线：fogsim 0.3.0｜交付性质：设计，不是生产实现或阶段验收报告**

本稿汇总主题 1—6 已获确认的合同，补全主题 7 的模块分工、协议细节、八批实施计划和验收对应关系。用户已明确回复“确认冻结设计”，整份详细设计（含主题 7 工程细化）据此冻结为 D-frozen-1。后续以本稿为生产编码和验收依据；本次冻结仅更新状态和决定记录，没有修改设计语义或开始生产编码。

## 阅读导航

1. 范围、来源、证据与基线
2. 十个特征的精确语义
3. 表达式语法和数值合同
4. 数据结构、求值接口与调度接入
5. 配置、规则身份、输出和兼容
6. 重放、错误和诊断
7. Java/Python 分层验收
8. 八批实施计划
9. 契约—任务—验收对应表
10. 决定记录、待办与冻结条件
11. 源码入口索引及证据说明

## 1. 范围、来源、证据与基线

### 1.1 本阶段完成后应具备的能力

给定固定表达式，在每次真实路由或排序决策中，从当前候选和调度状态读取特征，返回优先级并通过既有选择器选择候选。表达式固定，特征值随状态变化。

| 纳入内容 | 明确交付 |
| --- | --- |
| 十个特征 | NIQ、WIQ、MRT、UT、DT、PT、TTIQ、TIS、TWT、NTR |
| 六个二元函数 | `+`、`-`、`*`、`/`、`Max`、`Min` |
| 表达式执行 | 特征叶、binary64 常量、不可变树、严格 Lisp 解析、后序程序求值 |
| 两类规则 | 明确命名的 routing、sequencing 槽；可分别使用 GP |
| 运行入口 | 旧固定、动态、重放、重复实验共用执行层 |
| 可追溯性 | 原文、结构、语义版本、规则身份、特殊分数、失败位置 |
| 验收 | 特征、分数、选择、完整固定及动态、兼容、隔离、副作用和 RNG |

不实现种群初始化、随机终端、选择、交叉、变异、适应度评估编排、训练实例轮换或论文规模实验。不新增网络排队、抢占或模拟器调度政策。后续训练只能消费本阶段明确角色的规则接口，不能要求当前预建演化 RNG。

总体完成条件：同状态特征一致；同语义表达式分数及选择一致；同输入小型完整运行的事件、状态和结果一致；解析、编译、读取及求值不修改调度状态、不消耗 RNG。不同规则可能改变动态输入调用位置，不要求其整场最终 RNG 状态相同。

### 1.2 实际可访问来源

| 来源 | 本稿采用方式 |
| --- | --- |
| `fogsim-0.3.0.zip` | 当前 Python 基线、包内 Java 参考、既有工具与历史证据 |
| `Fog-Computing-multiDeviceDebug.zip` | 独立原 Java 来源 |
| `Fog-Computing-Java-to-Python-Study-Plan-2026-10-08.md` | 第 8 步及阶段 D 范围 |
| `fogsim 0.2.1 下一阶段扩展需求与详细设计初稿.md` | 前一阶段合同、来源和重放边界；不将其阶段编号混同为本阶段 |
| `fogsim-0.3.0-validation.json` | 绑定当前 ZIP 的历史验收报告 |
| Xu 等（2023）中英双语 PDF | PDF 第 7 页（印刷 2663）十特征及说明；第 8 页（2664）六函数与除零描述 |
| 结果 PNG、实现方案 ZIP、旧 Python ZIP | 当前附件存在；不替代 0.3.0 源码作为本阶段运行行为依据 |

本稿只使用当前附件、从附件生成的独立工作副本，以及本对话中的实际确认。没有搜索其他私人文件。原 ZIP 保留不覆盖。源码引用路径以包内相对路径为准，不依赖以前临时目录或历史下载链接。

| 文件 | SHA-256 |
| --- | --- |
| Python 基线 ZIP | `39766ec0cb019ab84bd1f71498ff1563c82b3a54dc6bbe180c19f54fcce12cb3` |
| 独立 Java ZIP | `17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a` |
| 学习计划 | `221353e11d7f8493d3afd9b2aa02537f0be4f4073193b45cbe161ea839589e0a` |
| 旧扩展设计稿 | `e47a1953e65a8b152f9e6d63b8a8702c862b5fb5518894169922b63543e92758` |
| 外部验收 JSON | `a2f37e73e9345b5bb333247ce5eac56c3a4601176b1b9060ea47706e66ffc770` |

本次重新检查两个源码 ZIP 完整性通过；0.3.0 中 66 个 Python 生产文件已建立摘要索引；内附与独立 Java 的 647 个源文件逐字节一致。外部验收 JSON 的 ZIP 哈希与本附件匹配。

### 1.3 三种证据分开记录

| 证据类型 | 可以得出的结论 | 不可以得出的结论 |
| --- | --- | --- |
| 0.3.0 历史报告 | 记录 995 项、零失败/错误/跳过，适用原阶段范围 | GP 已实现或已验收 |
| 前六主题讨论中的探针报告 | 支持相应设计判断，详见第 11 节的历史报告清单 | 本次已重新运行、原始文件当前可下载、生产集成通过 |
| 本次文档阶段的来源审计 | ZIP、摘要、源码入口和原方法可重新核查 | 已执行 Java/Python GP 完整对照 |

此前临时探针源码、命令和原始结果不在当前可访问附件或工作目录中。本稿保留其“此前对话报告”来源，不伪造或重建成历史原始证据。随附审计包只含本次来源复核材料；生产实施验收须重新生成正式证据，不能依赖这些历史数量作为门禁通过。

## 2. 十个特征的精确语义

### 2.1 统一符号与读取路径

`o` 为当前被评分的规范 `TaskOption`；`r=o.resource`；`w=o.task.workflow`；`t=context.view.clock_time`。Java 调用链为 `GPRule.priority()` → `CalcPriorityProblem` → `AttributeGPNode.eval()` → `JobShopAttribute.value()`；ERC 包装可再委托到实际终端。

Java 根据 `o.getServer()==null` 区分本地设备；服务器分支读取传入 server。合法实际调用保证其对应当前候选。Python 使用规范 `o.resource` 统一映射；禁止同 ID 的外来对象冒充该资源。

### 2.2 逐项合同

下表 Java 行号相对于 `src/mengxu/gp/terminal/JobShopAttribute.java`，Python 路径相对于 `src/fogsim/`。

| 特征 | Java 实际分支/字段 | Python 精确读取与顺序 | 时点及边界 |
| --- | --- | --- | --- |
| NIQ | `value():72`，本地/服务器 `queue.size()` | `float(len(r.waiting_queue))` | 当前完整等待队列；空为 +0；不含执行中项 |
| WIQ | `value():100`，`totalProcTimeInQueue()` | `r.waiting_processing_time` | 历史缓存；禁止重算或夹零 |
| MRT | `value():80`，原始 `readyTime` | `r.available_time` | 绝对时刻；不减 t，不取 max，不推算 pending Start |
| UT | `value():116`，`getUploadDelay()` | `o.upload_time` | 候选已存时长，不重算物理公式 |
| DT | `value():119`，`getDownloadDelay()` | `o.download_time` | 同上 |
| PT | `value():88`，`getProcTime()` | `o.processing_time` | 同上 |
| TTIQ | `value():108`，计算/上传/下载缓存读取方法 | `r.waiting_total_time` | 历史缓存，单项按 `((PT+UT)+DT)` 形成 |
| TIS | `value():97` | `t - w.release_time` | 当前候选自己的工作流；不使用统计 B |
| TWT | `value():125` | `t - o.ready_time` | 候选自己的字段；后继路由前通常仍为默认 +0 |
| NTR | `value():131`，任务数减 `getCompletedTaskNumber()` | 先整数 `w.task_count-w.completed_task_count`，再 `float` | 完成记录计数；不重数任务标志、不夹零 |

十项之外的 `t/W/RT/NTJ/WR` 即使出现在 Java 枚举中也不开放。

**验证状态：**十项原分支和 Python 模型映射已作静态核查；前轮报告 22 个状态、220 个值逐位一致。正式生产特征验收仍为 `NOT_EXECUTED`。

### 2.3 队列范围与缓存更新

等待队列只包含已到达处理器、尚未开始执行的候选。不含上传途中、执行中，或已经移出队列并预约 Start 的项。共享服务器读取全队列，不按设备过滤。

- 路由不把当前候选虚拟加入队列。
- 排序先对仍在完整队列中的每个候选求值，再移除选中项；当前候选包含在 NIQ/WIQ/TTIQ 中。
- 入队：`queued_processing_time = old + PT`；`queued_total_time = old + ((PT+UT)+DT)`。
- 移除：减去同样分组的单项值。不能改变结合顺序，不能改为 `sum/fsum`。
- TTIQ 不扣已过去的上传时间，也不加执行中任务的剩余时长。

| 资源 | 最后一项移除与空队列读取 |
| --- | --- |
| 本地设备 | 继续执行减法；空队列直接读缓存，允许历史舍入残差 |
| EDGE/CLOUD 服务器 | 移除最后一项时两个缓存置 +0；空队列读取返回 +0；非空不夹零 |

例：入队 0.1、0.2，再依次移除，本地可残留 `2.7755575615628914e-17`，服务器为 +0；0.5、0.1 的相同操作本地可残留负余量。不能将负余量一概判作模拟错误。

Java 服务器非空负缓存读取会打印警告并返回原值；Python 已有属性不打印。本阶段保留原数值，特征读取不额外打印或产生诊断副作用。Java stdout 原始警告作为参考原始输出保留；仅凭该警告不判失败，若违反其他模型不变量则按对应错误处理。

### 2.4 生命周期与读取顺序

| 事件/阶段 | 已有行为及特征含义 |
| --- | --- |
| 根任务 Arrival | 路由前将各候选 ready_time 设为工作流 release；一般 TWT=0 |
| 普通后继路由 | 不补设候选 ready_time；默认 0 时 TWT=t；保留两整轮路由 |
| TaskVisit | 只更新被派发候选 ready_time 为实际 Visit 时刻 |
| 排队排序 | TWT=t−该候选 Visit 时刻；其他执行选项不被同步更新 |
| ProcessStart | 此时才将 available_time 更新为 `((start+PT)+DT)`；包括下载 |
| ProcessFinish | 先登记本任务完成，再排序和后继路由；同工作流 NTR 已减一 |
| 已预约尚未 Start | 该项已不在等待队列；MRT 仍读取原字段，不提前推算 |

NTR 包括尚未就绪、上传中、等待、执行和下载中的任务，直到其 Finish 登记后才减少。TIS/TWT 在人为边界夹具中可负；特征层不承担修复模型的职责。

### 2.5 候选时长来源与固定输入适用性

生成阶段本地 PT=workload/device_rate，UT/DT=0；服务器 PT=workload/server_rate，UT=(base_data+total_input_data)/upload_bandwidth，DT=(base_data+total_output_data)/download_bandwidth。这些是生成合同，特征只读存量值。

十特征不直接读取算力、带宽、sampler 或边映射。旧固定输入和固定投影保存显式时长及运行结构，可用于本阶段 GP；这不等于当前 Java 固定适配器已支持 GP。投影须作为独立固定运行，不能拿其结果代替原动态最终结果。

### 2.6 可核对的状态样例

时钟 20，服务器 MRT=40，工作流 release=5、四项任务一条完成记录；候选 PT=4、UT=1.5、DT=0.5、ready=12；队列两项分别 `(2,.5,.25)`、`(3,.75,.5)`，按此顺序入队。

| NIQ | WIQ | MRT | UT | DT | PT | TTIQ | TIS | TWT | NTR |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 5 | 40 | 1.5 | .5 | 4 | 7 | 15 | 8 | 3 |

夹具必须真正构造完成记录和缓存操作历史，不能直接把这行预期值注入特征或参考。

## 3. 表达式语法和数值合同

### 3.1 语法

```text
expr    := FEATURE | NUMBER | '(' FUNC expr expr ')'
FUNC    := '+' | '-' | '*' | '/' | 'Max' | 'Min'
FEATURE := 'NIQ' | 'WIQ' | 'MRT' | 'UT' | 'DT' | 'PT'
         | 'TTIQ' | 'TIS' | 'TWT' | 'NTR'
```

所有名称区分大小写。允许裸特征和裸常量；每个函数严格二元，没有一元负号节点。负常量由数字 token 表示。

接受的空白精确为 ASCII SP、HT、LF、VT、FF、CR，即 U+0020、0009—000D。括号是独立分隔符，允许换行、连续空白、括号内侧空白和相邻子表达式。只接受一个完整表达式，消费到末尾。禁止注释、逗号、字符串、宏、方括号、绑定及范围外终端；其他非 ASCII 字符拒绝，不能把 NBSP 当普通空格。

解析器采用显式 token 栈或帧栈，不能依赖 Python 递归深度。不向用户暴露任意 Python eval 或动态执行入口。不得在解析时化简。

### 3.2 常量词法

这是兼容 Java `NumberUtils.isNumber`（所附 Commons Lang 3.4）与 `Double.valueOf` 的**共同有效范围**，不是扩大到任意 Python float 写法。按以下 ASCII 正则 fullmatch：

```regex
-?(?:0[0-7]+|(?:(?:0|[1-9][0-9]*)(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[dDfF]?)
```

可选尾缀仅 d/D/f/F，转换前去掉一个尾缀；一律直接转换为 binary64，不经 float32。前导零分支仍按十进制转换。保留原 token 位置以及转换结果位模式。

| 接受 | 拒绝 |
| --- | --- |
| `-1`、`.5`、`1.`、`1e+3`、`1d`、`1F`、`010` | `+1`、`+0.0`、`08`、`01.2`、`01e2`、`0x10`、`1L` |
| `1e309`→+∞、`-1e309`→−∞ | `NaN`、`Infinity`、`inf` 等单词 |
| `1e-9999`→+0、`-1e-9999`→−0 | 下划线数字、Unicode 数字和其他未定义形式 |

转换上下溢是合法数值，不报有限数错误。数字文本十进制转换必须对照 Java 边界样本；不采用区域小数点，也不重写 token 后再保存为“原文”。

### 3.3 六函数与目标数值语义

令 a 为完整左子树结果、b 为完整右子树结果。总是先左、后右，最后父节点；除法保护也不短路子树。

| 函数 | 目标精确操作 |
| --- | --- |
| `+` | binary64 `a+b` |
| `-` | binary64 `a-b` |
| `*` | binary64 `a*b` |
| `/` | 若 `b==0.0`，返回 **+1.0**，同时保护正负零；否则 binary64 `a/b` |
| `Max` | 若 `b<a` 返回 a，否则返回 b |
| `Min` | 若 `b>a` 返回 a，否则返回 b |

**明确修订：**原 Java Div 使用 `Double.compare(b,+0)==0`，只保护正零。目标语义依据用户确认 C09 增加负零保护；不能无条件宣称等于未修改原 Java。其余数值行为保留。

- 不设 epsilon；不清洗其他位置的负零。
- Max/Min 相等保留右参数的值及零符号；左 NaN 右普通数返回右数，右 NaN 则返回 NaN。
- 不替换成 Python max/min、Java Math.max/min 或 Double.compare 分支。
- 保留次正规数、正负零、溢出、无穷和 NaN；不对 GP 分数使用模型时间的有限数校验。
- 不折叠常量，不交换操作数、不重结合、不做 CSE 或 FMA 合并；同叶出现几次就读几次。

| 表达式 | 目标结果/目的 |
| --- | --- |
| `(/ 1 -0.0)`、`(/ 0 -0.0)` | 均 +1；原 Java 分别 −∞、NaN |
| `(/ (* 1e309 0) 0)` | 左侧先产生 NaN，保护后仍为 +1 |
| `(Max 0.0 -0.0)` | −0 |
| `(Min -0.0 0.0)` | +0 |
| `(+ (+ 1e16 -1e16) 1)` | 1 |
| `(+ 1e16 (+ -1e16 1))` | +0 |
| `(* 1e308 1e308)` | +∞ |
| `(* (* 1e308 1e308) 0)` | NaN |
| `(/ -1e-300 1e300)` | −0 |

正常非负特征也可经减法生成负数，进而生成负零。例如 `(* (- UT PT) (- WIQ WIQ))`，当 UT<PT 时产生 −0。不能以“模型未出错”为由排除此路径。

### 3.4 与原 Java 解析器的边界

原入口 `LispParser.parseJobShopRule()` / `parseNode()` 未使用 Tokenizer 或自动 LispSimplifier；会忽略多余参数，连续空格和 Tab 等可异常，部分缺括号/尾随表达式存在游标不推进路径。Python 不复制这些故障；采用严格输入诊断和已确认的空白扩展。

正常跨语言通道中，Java 适配器必须独立实现同一严格前端，再从解析结果实际构建原 GPNode 类型；不能用 Python 导出的 AST 替它解析。原 Java 解析器只在合法原格式样本和遗留差异通道使用，危险非法样本放独立进程设超时。深度 2500 的 Python 全文本解析、编译和求值是强制契约项；Java 的深树受原递归 eval 限制时单列其运行条件，不能拿 Python 结果充当 Java 结果。

### 3.5 解析诊断

| 错误码 | 条件 |
| --- | --- |
| GP_EMPTY_EXPRESSION | 输入全为空白或空串 |
| GP_INVALID_CHARACTER | 非许可字符 |
| GP_UNKNOWN_FUNCTION | 函数位置未知名称，包括 if/max/min |
| GP_UNKNOWN_FEATURE | 叶位置未知或超范围标识符 |
| GP_INVALID_CONSTANT | 具有数字意图但不符合常量语法/转换失败 |
| GP_ARITY_ERROR | 函数缺参数或多参数；空调用没有函数时归未知函数 |
| GP_UNBALANCED_PARENTHESES | 游离右括号或结束时仍有未闭合调用 |
| GP_TRAILING_INPUT | 已完成根表达式后仍出现 token |

每条错误含 role（已知时）、field_path、code、token、start/end 字符偏移（左闭右开、0 起）、line/column（1 起）。CRLF 算一个换行，单独 CR/LF 也换行；Tab 算一个字符列，不做显示宽度展开；EOF 跨度为 `[len,len)`。先词法拒绝非法字符，再按扫描顺序报告第一个结构错误；EOF 缺括号优先于该未闭合节点的缺参数。错误在规则准备阶段完成，不能留下空叶进入调度。

## 4. 数据结构、求值接口与调度接入

### 4.1 模块建议与依赖

下列为目标模块，不表示 0.3.0 已存在这些新文件。

| 模块 | 职责 |
| --- | --- |
| `rules/specs.py` | 公共不可变 RuleSpec、规则版本和角色约束；供配置及工厂引用，避免循环依赖 |
| `gp/ast.py` | FeatureNode、ConstantNode、BinaryNode、平面 AST 导出 |
| `gp/parser.py` | 词法、帧栈解析、错误位置、常量转换 |
| `gp/program.py` | 左右有序的后序编译、不可变指令、静态栈需求 |
| `gp/features.py` | 十特征纯读取 |
| `gp/numerics.py` | 六函数精确语义；与物理时间 numerics 分开 |
| `gp/evaluator.py` | 每次独立值栈执行 |
| `gp/identity.py` | 第 5 节规范序列化与身份派生 |
| `rules/gp.py`、`rules/factory.py` | 角色绑定、真实入口校验、PreparedRules 原子准备与安装匹配 |
| `serialization/f64.py`、`serialization/result.py` | v2 优先级编解码与结果协议边界 |
| `validation/gp_compare.py` | 严格数值、身份、首差异和覆盖比较 |

解析/数值层不引用 Engine、SimulationContext、来源或随机模块。日志和比较器读取输出，调度不得读取其预期值。

### 4.2 数据结构合同

| 对象 | 内容 | 共享/隔离 |
| --- | --- | --- |
| FeatureNode | 十项枚举 | 深不可变，可共享 |
| ConstantNode | 权威 64 位位模式；原 token 属来源元数据 | 不合并正负零 |
| BinaryNode | 函数、左节点、右节点 | 无 parent/argposition，无可变 children |
| ParsedExpression | 原文、跨度、根节点 | 不可变来源及结构 |
| CompiledExpression | 根、指令元组、栈上界、语义版本、结构身份 | 可跨运行和角色共享 |
| GPRule | 固定 role、当前来源绑定、CompiledExpression | 同角色绑定可共享；不可捕获运行对象 |
| PreparedRules | 明确 routing/sequencing 绑定及规则对身份 | 两侧全成功后一次发布 |
| 求值栈/当前值 | 本次评分局部容器 | 每次新建，禁止对象池遗留值 |
| 状态、队列、事件、统计、trace | 当前运行规范对象 | 各轮隔离 |

禁止规则字段 `current_option/context/last_score/last_features`。同表达式可绑定两个角色，但必须两个显式绑定。Java ERC 的 parent/argposition 写入不移植。不可变节点可共享对象，但 AST 导出按每次出现的位置编号，不按对象 id 去重；同一叶重复出现必须重复读取，不将有序树导出为 DAG。

### 4.3 公共接口草案

```python
parse_expression(text: str) -> ParsedExpression
compile_expression(parsed: ParsedExpression) -> CompiledExpression
read_feature(feature, option, context) -> float
evaluate(compiled, option, context) -> float
GPRule.priority(option, context) -> float
prepare_rules(routing_spec, sequencing_spec) -> PreparedRules
validate_rules_for_environment(prepared, environment_or_fixed_spec) -> None
```

低层 read_feature/evaluate 可供边界夹具；真实评分经 GPRule.priority 校验。CompiledExpression 的编译只生成程序，不读取当前特征。指令为 PUSH_CONST、READ_FEATURE、APPLY_BINARY；父指令先弹 b 再弹 a，按第 3 节执行。静态编译验证无空节点/未知操作，栈最终恰为 1；不把调用时的特征缓存进程序。

解析、编译、身份导出和结构比较均用迭代遍历，保证深树不在后续记录阶段因递归失败。可复用显式持有的不可变程序；不建立持有模型或无界积累的全局缓存。

### 4.4 准备、适用性和安装

1. 校验两份有效规则描述，解析、编译并绑定角色；任一失败则不发布 PreparedRules。
2. 检查当前输入/环境适用性。固定资源须对每项固定任务或每个动态设备均合法。
3. 引擎安装时核对角色、kind、目标/结构身份、语言/特征/数值版本及当前原文来源。
4. 已准备对象不能覆盖不匹配的有效配置。不同排版的同表达式可共享执行程序，但新绑定必须保留当前原文和 source_sha256。
5. 不把 seed、统计目标、trace、路径绑定进程序；相同程序可用于其他合法运行。

`Engine(..., prepared_rules=None)` 可作为内部可选参数，旧调用不变。省略时走统一工厂；注入时仍执行匹配和场景检查。动态控制层不再只桥接 routing_kind，必须安装两类完整规则。

动态配置的准备在创建输入 RNG、采样环境之前完成。环境构造后执行场景检查，再初始化和消费来源。重放先读并校验输入描述及有效覆盖规则，再准备规则；创建/消费 source 之前失败。无效规则不能推进重放游标。

### 4.5 Context 与对象合法性

每次 `EventContext.choose_route()` / `choose_next()` 现场新建 Context/StateView。StateView 的 clock 是值，但模型引用仍为实时对象；它不是历史快照，不能跨事件缓存。

真实入口检查：角色吻合；option 以 `is` 属于 context.candidates；task/resource/workflow 与本轮可见规范对象一致；路由候选属于同一 task，排序候选资源一致。不能用相同 key/ID 代替对象身份。

| 角色 | 阶段条件 |
| --- | --- |
| 路由 | 任务未完成、未派发；不在 GP 重写 DAG 就绪逻辑 |
| 排序 | 任务已派发、未完成；候选此时仍以身份存在于资源等待队列 |

身份检查不保证旧 Context 时钟新鲜，现场构造是独立必要合同。离线旧状态探针须重建完整模型时点。

Java clone 不作为决策冻结快照：Server.clone 的构造会重置队列缓存；SystemState.clone 会丢失设备/工作流列表；本地排序情境 clone 对空 server 的处理存在异常路径。参考读取真实规范对象；证据快照只复制所需标量、原始位模式和有序标识，不能用 clone 后的值代替现场特征。

### 4.6 实际调用顺序

**路由：**现场 Context → 原 candidates 顺序逐项 priority → 状态保护 → 写入该项 priority → 原比较器 → 返回原对象 → 事件层 dispatch。一个候选也求值。Arrival 根与普通后继 ready_time 生命周期不变。

**Finish：**完成登记 → 完整队列内排序 → 移除选中 → reserve Start → 就绪后继路由两整轮 → 派发第二轮结果。多个后继 A/B 的顺序仍为 A1、B1、A2、B2。预约不提前更新 MRT。

**共享服务器排序：**TIS/NTR 等始终读取每个候选自己的 workflow，不读取事件触发设备或刚完成任务的 workflow。

### 4.7 选择器职责和分数顺序

继续使用现有 `PriorityRule.priority(option,context)` 与 `_choose()`。评分较小者优先；Double.compare 语义下 −∞ < 有限负数 < −0 < +0 < 有限正数 < +∞ < NaN，所有 NaN 比较等值。

分数相等后依次比较 workflow release、设备 numeric_id、workflow id；都相同保留先遍历项。没有 task id 或 server id 平分键。不要将候选排序重排后再求值。FCFS 路由仍返回 resource.available_time，FCFS 排序仍返回 workflow.release_time；FixedResource 仍是目标 0、其他 1。

### 4.8 副作用及失败

| 层 | 允许写入 |
| --- | --- |
| parse/compile/prepare | 新建描述、树及局部容器 |
| feature/evaluate/priority | 本次局部栈和变量 |
| selection | 当前候选 priority、独立观察记录 |
| 四事件 | 原有状态、队列、预约、事件和来源动作 |

保留 graph_fingerprint，不将其当作事务或完整写入证明；它只观察净变化，且现版正常返回后才检查。验收工具用 finally 检查异常路径，并配合纯性审查和 RNG 入口哨兵，不靠恢复状态隐藏写入。

选择失败不回滚此前合法 priority 写入，不产生 selected/完整 DECISION，不返回候选，本次选择不派发。事件此前已做动作不自动撤销。新增独立 DECISION_ERROR 只使用选择器局部已完成分数，不重跑表达式。

领域 StateError 沿现引擎失败结果返回；未知程序异常标记失败后继续抛出。合法 NaN/∞/负分不是错误。不回退 FCFS，不重试，不复用 FAILED Engine。

## 5. 配置、规则身份、输出和兼容

### 5.1 规则描述与组合

| role | 允许 kind | 精确字段 |
| --- | --- | --- |
| routing | fcfs | 仅 kind |
| routing | fixed_resource | kind、非空 resource_id |
| routing | gp | kind、非空 expression |
| sequencing | fcfs | 仅 kind |
| sequencing | gp | kind、非空 expression |

拒绝未知字段、空/空白表达式和冲突字段。固定资源排序非法。六种合法组合为 3 类 routing × 2 类 sequencing，不要求两侧同时 GP。

旧固定配置示例是完整规则入口示例，路径相对配置文件：

```json
{
  "instance": "small.fixed.json",
  "routing_rule": {"kind": "gp", "expression": "(+ PT (+ UT DT))"},
  "sequencing_rule": {"kind": "gp", "expression": "(- 0 TWT)"},
  "trace_enabled": true
}
```

旧 Python RunConfig 的扁平字段调用兼容保留；新增 `routing_expression`、`sequencing_expression` 可选字段（默认 None），通过适配生成公共 RuleSpec。仅相应 kind=gp 时对应 expression 必填，其他 kind 必须 None。旧 `fixed_resource_id` 合同保留，不能与 GP 同时有效。新字段追加在原位置参数之后，不能改变旧位置参数含义；旧模式 `to_dict()` 省略这两个未使用字段，不能直接将新增 dataclass 字段通过 asdict 泄漏到 v1 输出。

版本化实验中的相同对象放 `run.routing_rule` / `run.sequencing_rule`，其他来源和统计字段沿用基线。RuleConfig 增加 expression 字段，to_dict 按 kind 输出有效字段，不向旧 v1 输出新增 null 字段。

`--fixed-resource` 替换整份路由描述并清除 routing_expression，保留 sequencing 描述；`--no-trace` 只改变 trace。GP 文本通过现有 --config 提供，本阶段不另增表达式 CLI 参数。

### 5.2 版本边界

| 文档/入口 | 行为 |
| --- | --- |
| 旧无版本固定配置、无 GP | 原默认、结果形状及未新增 null 字段保持 |
| 旧固定配置启用 GP | 扩展规则对象，结果写 v2 |
| fogsim.experiment schema_version=1 | 原规则范围及序列化合同；拒绝 GP |
| fogsim.experiment schema_version=2 | 六组合、新结果和新捕获输入 v2 |
| fogsim.dynamic-replay v1 | 继续读；在 v2 reuse_inputs 中可用 GP 新规则运行 |
| fogsim.dynamic-replay v2 | 显式完整规则 manifest 及语义身份 |
| 未知版本 | 明确报错，不猜测/降级 |

新结果格式分别定名 `fogsim.fixed-result`、`fogsim.dynamic-result`，均 schema_version=2，保留 status/makespan 等既有根字段；GP 比较参考格式 `fogsim.gp-reference` v2，验收报告 `fogsim.stage-d-validation` v1。这些命名是本稿工程细化，不冒称旧包已有协议。

显式使用 v2 实验，即使两侧为基线规则也按 v2 输出；默认旧固定/旧 v1 不被自动升级。直接 Python API 若配置任一 GP 则结果选 v2；无 GP 且无显式 v2 请求沿用旧输出。该输出 profile 由控制层传递，不写入表达式或规则身份。v2 reuse_inputs 读取 v1 时，将旧 FCFS/FixedResource 行为映射为本稿基线身份并记录迁移来源，不能替换或重写原文件。旧读取器遇新字段/版本应明确失败。

### 5.3 语义版本（不可与 schema_version 混用）

| 标识 | 固定值与覆盖范围 |
| --- | --- |
| language_version | `fogsim-gp-lisp-v1`：十特征、六函数、严格二元、ASCII 空白和本稿常量词法 |
| feature_semantics_version | `fogsim-features-java-v1`：第 2 节字段、时点、缓存分支 |
| numeric_semantics_version | `fogsim-gp-f64-dual-zero-v1`：第 3 节全部数值行为 |
| selection_policy_version | `fogsim-selection-java-v1`：方向、Double.compare、平分顺序 |
| identity_encoding_version | `fogsim-rule-identity-v1`：下述规范编码 |
| score_encoding_version | `ieee754-binary64-hex-v1` |

原 Java 差异参考另标 `java-original-positive-zero-v1`，只用于参考通道；当前用户运行配置不提供切回原除法的选项。软件版本、源码摘要、语言运行时另记 provenance，不能替代语义版本。

### 5.4 原文、AST 和身份

每轮完整保存：原始 expression、source_sha256、语义版本、规范 AST、expression_id、各角色 rule_id 和 rule_pair_id。关闭 trace 仍保存完整规则清单。

AST 按先序、先左后右编号，root=0；节点恰好三种字段形状：

```json
{
  "root": 0,
  "nodes": [
    {"kind": "binary", "op": "+", "left": 1, "right": 2},
    {"kind": "feature", "name": "PT"},
    {"kind": "constant", "bits": "8000000000000000"}
  ]
}
```

索引为非负整数且非 bool；完整表必须单根、无环、无额外节点，每个非根出现一次；不把树变成共享子树 DAG。编译和原文验证是权威来源；不能从不可信表直接安装执行。

身份输入 payload 定义如下，不含派生 ID 本身：

| 身份 | 权威输入 |
| --- | --- |
| source_sha256 | 原始已解码表达式字符串 UTF-8 字节，不含 BOM，不规范换行或空白；不是整个 JSON 文件字节 |
| expression_id | identity_encoding_version、language_version、feature_semantics_version、numeric_semantics_version、ast |
| GP rule_id | identity_encoding_version、role、kind=gp、selection_policy_version、expression_id |
| FCFS rule_id | identity_encoding_version、role、kind=fcfs、selection_policy_version、baseline_semantics_version=`fogsim-fcfs-v1` |
| FixedResource rule_id | identity_encoding_version、role、kind=fixed_resource、selection_policy_version、baseline_semantics_version=`fogsim-fixed-resource-v1`、resource_id |
| rule_pair_id | identity_encoding_version、routing_rule_id、sequencing_rule_id |

payload 字段名称严格采用上表名称。结构 identity 不含原文、跨度、路径、seed、trace、统计配置或运行编号。排版不同和 1/1.0/1d 转成同位时 expression_id 相同；负零/正零、操作顺序、结构或语义版本不同则不同。同表达式跨角色 expression_id 相同而 rule_id 不同。

### 5.5 可跨语言复算的规范字节

以下为主题 7 补齐的编码细节，实施必须用独立 Java/Python 黄金向量重新验收，不能声称沿用此前不可访问探针的准确字节。

规范 JSON（CJ）限制在上述 payload 类型：对象、数组、字符串、非负整数；没有浮点数字，常量用位串。对象 key 均为规定 ASCII 名，按 ASCII 升序；数组保持顺序。无缩进、无空白、无末尾换行；整数为无前导零十进制。

字符串：双引号和反斜线使用 `\"`、`\\`；BS/FF/LF/CR/HT 分别用 `\b/\f/\n/\r/\t`；其他 U+0000—001F 及 U+007F 以上全部以小写四位 `\uXXXX` 转义；非 BMP 用 UTF-16 surrogate pair；其余 U+0020—007E 原样，斜杠不转义。拒绝未配对代理项。不做 Unicode NFC/NFD、大小写或换行规范化。

expression/rule/pair 的摘要字节分别为 ASCII `fogsim.expression-id.v1\n`、`fogsim.rule-id.v1\n`、`fogsim.rule-pair-id.v1\n` 前缀（这里 \n 为一个 LF 字节）加 CJ 的 UTF-8。结果 ID 为 `sha256:` 加 64 位小写十六进制；source_sha256 也用该格式，但直接摘要原文 UTF-8，不加域前缀。

导入清单：先检查版本和字段 → 重新解析原文 → 比较 AST 及常量位模式 → 复算四层摘要 → 核对角色及活动配置。任一不符报错，不修改清单来“修复”。Java 从自己的前端及实际装载 GPNode 树导出结构和身份，不照抄 Python 给出的 ID。

### 5.6 分数和特殊值

v2 所有**指定优先级字段**统一使用标签，有限值也相同：

```json
{"kind":"f64","bits":"8000000000000000"}
```

bits 恰为 16 个小写十六进制字符，表示大端 binary64 位模式。只接受 kind/bits 两字段，不接受数字、大小写混合、额外 display/value 字段或错误长度。解码支持所有位模式；算术跨语言比较 NaN 只按类别，记录仍保存各侧原始位模式。

| 值 | bits |
| --- | --- |
| +0 | 0000000000000000 |
| −0 | 8000000000000000 |
| +∞ | 7ff0000000000000 |
| −∞ | fff0000000000000 |
| 一种 quiet NaN | 7ff8000000000000 |

范围：候选分数、状态 option.priority、selected 观察、actions 决策副本、失败评分前缀和失败后状态；包括混合运行中的基线分数。全局清单中 AST 常量本来已有 bits，不再嵌套 f64 标签。

引擎内部保持 float；只在指定协议字段编码/解码，不递归猜测所有浮点字段。物理工作量、时长、时钟和普通指标仍是有限 JSON 数字，允许时保留负零；不放开 allow_nan=False。新增诊断中的特征值/算术中间值如需要记录，显式声明为 f64 字段。

根层新增字段 `format/schema_version/score_encoding_version/rule_manifest`；rule_manifest 含 identity_encoding_version、expressions 数组、bindings.routing、bindings.sequencing、rule_pair_id。expressions 按 expression_id 排序，binding 保存当前原文摘要并引用 expression_id；每个原文及其 source_sha256 保存在相应 binding 的 source 对象中，避免同结构不同原文被丢失。baseline binding 不含 expression/source。

binding 的 source 对象精确含 `expression/source_sha256`；GP binding 另含 `role/kind/rule_id/expression_id/selection_policy_version`，baseline binding 按 5.4 对应身份字段及 rule_id 保存。expressions 中每项含 5.4 的 expression payload 及 expression_id，完整版本信息不能仅存在于运行配置。

每条成功决策在原有字段外增加 rule_id；角色仍由 kind 明确。不得为了日志再求一次特征或表达式。生产默认不强制导出每叶中间值；验收观察器在同一次读取处捕获标量。

## 6. 重放、错误和诊断

### 6.1 两种重放目的

| 目的 | 行为 |
| --- | --- |
| verify_reference | JSON 配置禁止规则覆盖；直接 API 可给等值规则，但须有效语义身份相同且当前绑定来源如实保存；运行后才读参考并比较 |
| reuse_inputs | 可显式替换任一槽；保存 recorded 与 active 规则/规则对身份；不读取原参考，comparison_status=NOT_COMPARED |

verify_reference 的 recorded 与 active 两角色身份、统计/行为条件及参考绑定必须一致；仅文本排版不同不能伪造记录来源，但可按结构身份判行为等值。不可把不同 numeric_semantics_version 当作等值。

严格动态跨语言参考必须由 Java 使用同表达式和双零保护语义重新真实运行并捕获。旧 FCFS 或原 Java 除法参考不能只改标签/manifest 后充当同语义参考。

### 6.2 来源消费边界

保持原全局 generation-attempt 游标及 phase、owner_device_id、clock_time、causing_workflow_id、candidate_id 调用位置检查，不向后搜索、不跳过、不补样、不重采样。源码 `ReplayWorkflowSource.generate()` 明确将 recorded event_sequence 作为诊断字段，**不把它加入来源消费的匹配条件**；严格参考仍在运行后核对事件序列。保留该分工，不能因新增 GP 而静默加强来源门槛。

| 情况 | 输出及含义 |
| --- | --- |
| 需要记录但已耗尽 | REPLAY_INPUT_EXHAUSTED；INPUT_COVERAGE_INSUFFICIENT |
| reuse_inputs 调用位置不符 | REPLAY_INPUT_DIVERGENCE；INPUT_COVERAGE_INSUFFICIENT |
| verify_reference 调用位置不符 | 保留同原因码；正常一致验收 FAILED，不能隐藏为允许换规则 |
| 新实验正常提前停止 | 允许未消费后缀；如实记录 consumed/available |
| 严格原轨迹对照 | 来源调用数及位置均须一致，参考在运行结束后比较 |

输入候选记录、独立 observed_acceptance 是输入证据和事后观察，不能替代 Python 自己的准入判断。reference 的分数、选择、未来状态不能进入来源生成或调度。

### 6.3 错误分类

| 类别/错误码 | 时点与处理 |
| --- | --- |
| GP 配置字段/版本/表达式错误 | InputError，准备阶段；附 role/field_path/解析位置 |
| GP_RULE_ROLE_MISMATCH、GP_PREPARED_RULE_MISMATCH | 安装阶段输入错配；不初始化来源 |
| GP_RULE_IDENTITY_MISMATCH | 原文、AST 或摘要不符；记录校验失败 |
| GP_F64_ENCODING_INVALID | 位串或标签形状非法；不参与比较 |
| GP_CONTEXT_IDENTITY_MISMATCH、GP_CONTEXT_PHASE_INVALID | 真实评分 StateError；不返回兜底分数 |
| GP_STATE_MUTATION_DETECTED | 规则只读保护失败；保留可观察现场，不自动回滚 |
| 合法 NaN、无穷、负分、负零 | 正常数值，不能错误分类 |
| 未知 TypeError 等程序异常 | 标记失败后传播，不包装成正常领域失败 |
| 重放原因码 | 保留原 REPLAY_* 语义，不统一改为 GP 错误 |

错误码稳定供机器读取；message 可含具体字段。不得吞掉原异常因果链。CLI 输入错退出 2；领域运行或要求的验证失败退出 1；成功退出 0。未知异常沿原传播约定，不为凑退出码吞异常。

### 6.4 未完成决策记录

新增独立 `DECISION_ERROR` 观察，含 event_sequence、time、kind/role、round_number、rule_id、失败候选 key/index、scored_prefix、error.code/type/message。scored_prefix 只含已完成并已写入 priority 的候选与分数；无 selected 字段，不计入成功 decision_count。当前候选求值失败后的瞬间已有写入由失败状态快照保留。

trace 开启时，在 actions 追加独立错误观察，并保留 before/after/错误事件帧；关闭时在 diagnostics 保留最小 rule_id/事件/角色/轮次/候选/错误。已有部分 priority 不回滚。最终序列化必须同时支持失败后状态的特殊值。

一个错误观察只能采集已有局部数据；不能重跑表达式、重新选候选或让 GPRule 保存 last_*。

## 7. Java/Python 分层验收

### 7.1 共同输入和独立参考

| 层次 | 两侧如何取得相同输入 |
| --- | --- |
| 特征、表达式、单次选择 | 保存不含预期输出的状态夹具；各自构造对象并导出实际装载状态，再独立计算 |
| 完整固定 | 独立加载同物理实例、候选及拓扑顺序、同规则；从初态完整运行 |
| 完整动态跨语言 | Java 同 GP 真实生成并捕获有限输入；Python 用输入通过真实 DynamicEngine 独立准入和调度 |
| Python 原生闭环 | 原生动态 GP → 捕获完整输入 → 同规则重放，比较真实轨迹与结果 |

状态夹具需有时钟、对象映射、有序候选、队列成员与形成历史、任务标志、完成记录；WIQ/TTIQ 不能按剩余队列重算，NTR 不能直接填剩余数量。加载状态不一致先报夹具/适配器错误，不接着比较分数。

Java 参考尽可能复用原 AttributeGPNode、六函数和 AbstractRule/TaskOption 比较；仅在独立副本覆盖 Div 双零保护、严格前端及必要构造/观察适配。所有 overlay 单独摘要和 diff，原文件不改。观察器委派实际规则，不另写一套 GP 算法作为“原 Java 结果”。

### 7.2 环境与证据门禁

正式参考使用 JDK17，记录 java 路径、实际 vendor/runtime、二进制摘要、依赖 JAR、编译命令与源码摘要。不同 Java17 更新版不因不等于历史厂商版本而直接失败，但必须通过实际 oracle/parity 检查；JDK21 探针不替代 JDK17 门禁。Java 无法运行仍可做静态核查，结果必须列 INFRASTRUCTURE_ERROR/NOT_EXECUTED。

参考输入文件与输出文件分离；manifest 分别绑定其 SHA-256、规则对身份、baseline/overlay 摘要。Python 来源没有 reference 句柄。运行前不读取 reference；reuse_inputs 全程不得打开 reference。不得从 Python 预期反向构造 Java 结果。

### 7.3 数值比较

| 比较对象 | 标准 |
| --- | --- |
| 十特征、常量、函数、表达式、优先级中的有限数 | binary64 位模式完全一致 |
| +0/−0 | 必须同号 |
| 无穷 | 必须同号 |
| NaN | 同为 NaN 即类别一致；保留双方 payload，不要求算术 payload 跨语言相同 |
| 事件时间、计划时间、clock、release/ready、available_time、候选时长、队列缓存 | 位模式一致 |
| 普通最终派生指标 | `isclose(abs_tol=1e-9, rel_tol=1e-12)`；双方零时仍同号 |
| ID、role、轮次、计数、成员及顺序 | 类型和内容精确一致；不重排、不猜缺省 |

v1 保留原比较合同。v2 严格字段使用明确 schema 字段集合，不采用“所有数字容差”或仅 `.priority` 后缀识别。普通指标允许容差不掩盖影响调度的上游首差异。time/score NaN 不通过有限数类别；只有 schema 声明的算术值和分数允许非有限。

Max/Min 另外做同侧分支断言：同值不同零符号、不同 quiet NaN payload 参数，验证选了右参数。求值访问顺序及重复叶读取次数单独比；不能凭最后同为 NaN 判定顺序正确。

### 7.4 验收矩阵

| ID | 条件/比较字段 | 通过标准 | 必须保存证据 |
| --- | --- | --- | --- |
| D01 状态映射 | 候选、资源、工作流、队列历史、完成记录、时钟 | 两侧实际装载值/顺序/归属一致 | 共同夹具、各自装载导出、字段首差异 |
| D02 十特征 | 两角色、本地/EDGE/CLOUD、共享服务器、空/多队列、部分完成 | 十值按 7.3 一致，整数先减后转 | 原字段、读取路径、双方位模式 |
| D03 特征时点 | 根/后继、Visit 前后、Finish 登记后、待 Start | MRT/TWT/NTR/队列包含范围完全符合第 2 节 | 事件前后状态、同事件决策顺序 |
| D04 六函数 | 六函数 × 16 值 × 16 值，1536 项 | 双零保护、分支及 binary64 类别/位模式正确 | 原节点/overlay、原始值、分支观察 |
| D05 解析与树 | 有效数字、排版、嵌套、错误输入、重复叶、深度2500 | AST/常量/分数一致；错误提前且有位置；Python 全文本至导出无递归失败 | 原文、AST、错误跨度、访问顺序；跨语言深树运行条件单列 |
| D06 路由 | 单/多候选、1 ULP、NaN/∞/零、每级平分 | score、写入顺序、selected 一致 | 原有序候选、逐项分数、原对象归属 |
| D07 排序 | 完整队列、跨设备、不同 workflow、非首项获选 | 队列内求值、候选自己的 TIS/NTR、原平分 | 入/出队前后、候选归属、决策 |
| D08 完整固定 | F01—F06；分叉汇合覆盖六组合 | 事件/动作/决策/计划/最终状态一致；全部工作流完成 | 双方全轨迹、模型、结果、覆盖断言 |
| D09A 动态跨语言 | 同语义 Java 新捕获；链、共享分叉汇合、禁本地 | 来源/准入/事件/轮次/G/B/R/统计成员/结果一致 | input/reference/manifest、完整轨迹、调用游标 |
| D09B 原生动态闭环 | Python GP 原生后同规则重放 | 仅排除明确 provenance/source 操作元数据后轨迹、状态和结果一致 | 捕获、两次结果、排除字段白名单、RNG观察 |
| D10 兼容 | 旧固定、v1、v2、六组合、CLI覆盖、trace开关 | 旧合同保留；新协议可追溯；无GP v1结果不漂移 | 新执行回归、旧/新输入、输出结构 |
| D11 隔离与清理 | 共享程序、交替模型、重复/fresh/rerun/rotate、retain/release | 程序不变；模型/结果不串用；清理不改GP结果 | 对象身份、摘要、操作/RNG生命周期 |
| D12 只读/RNG | parse/prepare/read/evaluate/priority 正常和异常 | 状态无写入、RNG入口零尝试/native state不变 | finally 快照、入口哨兵、外部计数 |
| D13 失败合同 | 角色/身份/阶段/安装错配、部分评分、程序异常 | 时点/错误码/部分合法写入/不派发/传播正确 | 失败状态、错误观察、异常链 |
| D14 重放边界 | identity篡改、非法f64、记录耗尽/调用不符、参考哨兵 | 严格拒绝/覆盖诊断/不修补；reuse不读参考 | 游标、访问记录、原文件绑定、首差异 |
| D15 指定遗留差异 | 原Java负零除法及登记基线精度边界 | 精确定位首因及传播，不能混入正常一致 | 两套身份、补丁、首分歧、原始结果 |

16 值集合固定为：+0、−0、+1、−1、+2、−2、±最小次正规、±最小正规、±最大有限、±∞、两种不同 payload 的 quiet NaN。函数值可以注入探针，不因此放开 Lisp NaN/Infinity 单词。NaN 位模式记录使用 raw bits，不 canonicalize 写出。

### 7.5 完整固定案例及覆盖断言

| 案例 | 强制实际覆盖 |
| --- | --- |
| F01 链 | 非零通信；根及后继 TWT；Finish 后 NTR；后继两轮路由 |
| F02 分叉汇合 | 真正汇合等待；A1/B1/A2/B2；先排序预约再后继路由；六组合分别运行 |
| F03 多设备共享队列 | 至少两个不同设备的等待候选；GP 排序选中原候选第二项或以后 |
| F04 状态相关路由 | 不同真实决策状态下相同候选时长发生选择变化，有 MRT/WIQ 等读取证据 |
| F05 小数缓存 | 真实事件中形成并读取历史舍入残差；本地/服务器分支可区分 |
| F06 特殊分数 | 实际运行覆盖 NaN、±∞、±0；正式输出→读取→比较保真，可分多次运行 |

F03 的可用夹具：三个单任务工作流时刻 0/1/2 到达；共享 E0 的 PT=10/2/4，UT=DT=1；路由 PT，排序 `(- 0 PT)`。其他候选 PT 配得更大，确保进入 E0。时刻12须看到两项等待，分数−2/−4并选中第二项。此前 Python 样机报告证明可达；正式双方运行仍须重新验收。

F06 不要求同一表达式或单次运行产生全部类别；分别用 `(* 1e309 0)`、±溢出、下溢等合法表达式覆盖。特殊分数不能污染物理时间。

动态案例至少为链、双设备共享分叉汇合、禁本地三类；固定与动态各自必须真正发生多候选 GP 排序并选中非首项。配置里出现 GP、只有单项队列或从未调用排序不算覆盖。动态按原统计停止，不要求停止时清空全部工作流。

### 7.6 副作用与 RNG

在 finally 观察模型图、身份/顺序、事件堆、来源游标、捕获计数、统计和 trace。对解析、编译、准备、特征、求值、priority 分别检查。

对实际使用 RNG 检查 native state，并哨兵监测采样、seed、setstate/恢复和新建 RNG。抽样后恢复仍违规；不以最终相同掩盖调用。白名单实现源码不得引入 random、sampler、来源访问或系统随机获取。

检查 selection 时仅豁免它负责的 priority/观察日志；事件层允许原调度动作；动态正常生成窗口允许 RNG。不要比较不同规则的整场最终 RNG；原生与重放来源元数据允许按显式白名单差异。

### 7.7 分类、首差异与总体结论

| classification | 含义 |
| --- | --- |
| NORMAL_PARITY_PASSED | 同语义同输入，比较和覆盖均满足 |
| CONTRACT_CHECK_PASSED | 配置、错误、隔离等合同测试通过，单独统计 |
| EXPECTED_DIFFERENCE_CONFIRMED | 指定遗留差异确认，不能替代正常一致 |
| INPUT_COVERAGE_INSUFFICIENT | 有限输入数量或换规则调用位置不足；保留原因码 |
| INFRASTRUCTURE_ERROR | 必需环境/工具受阻 |
| NOT_EXECUTED / NOT_COMPARED | 未运行；或新实验未比原参考 |
| FAILED | 已执行违反合同；包含必需场景未触发的覆盖失败 |

首差异记录 event_sequence、event kind/time、role、round、candidate key/index、field_path、expected/actual、双方 bits/class，以及 input/rule/reference/source 摘要。不能重排事件、插入缺失决策、过滤不一致候选或继续“修补运行”。

所有强制项须执行且满足对应通过类别；D15 的预期差异不计入 NORMAL。预期差异须在执行前登记具体触发条件、源码位置及预期首分歧；不能用“已有精度边界”泛称豁免任何新差异。基础设施受阻/覆盖不足/未执行不算通过。报告每项 planned/executed/compared/passed 和 coverage，不单凭总测试数宣称完成。

## 8. 八批实施计划

**进入 B01 所需的设计确认条件已满足，后续按冻结设计开展生产实施。** 本文交付设计与实施计划，本次冻结记录不包含生产实现。各批独立记录改动、必要测试、未执行项和产物；不修改历史参考或既有预期来消除差异。

| 批次 | 修改模块/任务 | 依赖 | 验证门槛 | 交付物 |
| --- | --- | --- | --- | --- |
| B01 合同与数值/特征内核 | RuleSpec/版本；gp.features、gp.numerics；诊断类型 | 冻结设计 | D01—04 的 Python契约；不引入RNG；原字段分支 | 内核、公共类型、边界夹具与原始结果 |
| B02 解析/AST/程序 | parser/ast/program/evaluator；迭代遍历；来源跨度 | B01 | D05；深文本2500；常量上下溢；左右顺序和重复叶 | 解析器/求值器、错误黄金案例、不可变程序 |
| B03 规则工厂/调度集成 | GPRule、PreparedRules；Engine/EventContext；动态两槽；旧固定配置/API | B02 | D06/07、D11—13；六组合；Context现场构造；部分失败 | 可实际运行的GP评分接入、安装匹配和隔离证据 |
| B04 v2身份/记录/序列化 | identity、f64、trace/result、experiment v2、CLI覆盖及错误观察 | B02/B03 | D10/13/14；跨语言编码向量准备；所有priority位置含失败 | v2协议、配置样例、manifest、编码/篡改检查 |
| B05 重放/捕获/重复实验 | loader/spec/export_input/engine/source、runner、有效规则与来源记录 | B04 | D09B、D10/11/14；v1复用、reference哨兵、游标和RNG | 原生闭环、v1/v2重放、失败和覆盖诊断 |
| B06 Java独立参考及对比器 | 独立overlay、严格前端、真实树导出、固定/动态观察、gp_compare | B02/B04；JDK17 | 正式D01—07、身份/编码跨语言；原Java差异D15 | Java适配器、补丁、共同输入、双侧原始输出、首差异器 |
| B07 完整场景验收 | F01—F06、动态三类、六组合；严格状态/事件比较 | B03—06 | D08/D09A/B；真实队列和非首项选择；F05/F06覆盖 | 小型完整运行证据、覆盖计数、各项分类 |
| B08 回归/打包/验收报告 | 旧固定/v1回归、重复/清理/CLI/文档；合同审计与交付 | B07 | D10—15及所有必需项；生产源与测试对应；无伪通过 | 新版本源码包、完整验收JSON、证据包、使用说明、限制清单 |

Java 环境准备可以提前只读检查，但正式 Java 数值门禁不能被 Python 单侧代替。B06 发现差异时回到最小失败层修复；不得只调低容差。协议细节若需改变语义、范围或兼容合同，先更新设计记录并取得用户确认；纯模块重命名可自行记录。

建议新测试分为 `tests/gp/` 的解析/数值/接口合同和 `tests/stage_d/` 的完整场景及兼容；Java工具放 `tools/java/stage_d/`，正式验收编排放 `tools/validate_stage_d.py`。这两个 tools 文件是后续目标路径，本轮未创建生产实现。

### 8.1 每批完成定义

批次说明必须含 modified_files、设计契约编号、执行命令及环境、原始结果位置、验收分类、未执行原因及下一批依赖。成功测试必须观察对外行为或数值合同；不以复述实现的测试数量代替有效覆盖。

B08 才能宣称阶段实现完成；设计冻结与实现验收是两个独立状态。新软件发行版本在实施交付时选择，不将本设计版本直接当作软件版本。

## 9. 契约—实现任务—验收项对应关系

本表 K 编号是本稿追溯编号，不替换已确认的 C 决定编号。

| 契约 | 可检查要求 | 实施批次 | 验收 |
| --- | --- | --- | --- |
| K01 | 仅固定执行；十特征六函数，无训练 | B01—08范围审计 | D05/D10、交付审计 |
| K02 | 原字段映射与整数计数顺序 | B01 | D01/D02 |
| K03 | 绝对MRT、根/后继TWT、Finish后NTR | B01/B03 | D03/F01/F02 |
| K04 | 缓存历史、空队列分支、不重算/夹零 | B01 | D02/F05 |
| K05 | 双零保护，其余Java数值、左后右 | B01/B02 | D04/D05/D15 |
| K06 | 严格二元/完整输入/ASCII空白/有效数字 | B02 | D05 |
| K07 | 不可变树/程序、局部值栈、重复叶逐次读取 | B02/B03 | D05/D11/D12 |
| K08 | 两槽原子准备、适用性与安装匹配 | B03 | D10/D13 |
| K09 | Context现场构造、规范身份与阶段校验 | B03 | D03/D06/D07/D13 |
| K10 | 方向、Double.compare、平分和遍历顺序 | B03 | D06/D07/D08 |
| K11 | 队列内排序、预约顺序、后继两轮 | B03 | D03/D08/D09A |
| K12 | priority写入归选择器，失败不回滚/不选中 | B03/B04 | D12/D13 |
| K13 | 旧固定入口/API兼容；动态两槽完整传递 | B03/B04 | D08/D09/D10 |
| K14 | v1保持、v2显式、未知版本拒绝 | B04/B05 | D10/D14 |
| K15 | 原文/有序结构/语义/角色分层身份 | B04/B06 | D05/D10/D14及跨语言黄金向量 |
| K16 | 全priority字段f64标签，物理字段仍有限 | B04 | D14/F06 |
| K17 | trace关仍有manifest和最小失败位置 | B04 | D10/D13 |
| K18 | 两重放目的、全局游标、覆盖不补造 | B05 | D09/D14 |
| K19 | 独立Java计算，输入与参考隔离 | B06 | D01—09、D14哨兵 |
| K20 | GP和相关状态位级，指标容差，NaN分类 | B06/B07 | D01—09/F06 |
| K21 | 完整运行实际多候选且非首项排序 | B07 | F03、D08/D09A/B |
| K22 | GP不改状态/不碰RNG；动态生成可用RNG | B01—07 | D11/D12 |
| K23 | 预期差异/覆盖不足/基础设施/未执行分列 | B06—08 | D14/D15及汇总审计 |
| K24 | 历史证据、设计探针、正式新验收不混记 | B01—08 | 每批及最终证据清单 |
| K25 | 未确认不冻结；未授权不开始生产 | 当前交付及B01入口 | 用户实际明确确认 |

## 10. 决定记录、待办与冻结条件

### 10.1 已确认决定

本次沿用能从实际回复准确追溯的编号；早先 C01—C06 的逐项编号文本当前没有完整原记录，不自行重造。其已明确的范围约束已写入第 1 节。

| 决定 | 实际用户确认 | 本稿落点 |
| --- | --- | --- |
| C07 | “让旧固定配置入口也能显式指定GP路由和排序” | 4.4、5.1、K13 |
| C08 | 主题二建议后的“接受”：保留MRT、后继TWT和缓存差别 | 第2节、K02—04 |
| C09 | 在Java数值行为基础上增加负0保护 | 3.3、5.3、D15 |
| C10 | 严格二元、完整输入、提前报错、ASCII空白、核查的有效常量 | 3.1/3.2/3.5 |
| C11 | “主题四按推荐稿来”：两轮方案整体确认 | 第4节、K07—13 |
| C12 | “主题5按推荐来” | 第5/6节、K14—18 |
| C13 | “主题六按推荐来” | 第7节、K19—24 |
| C14 | “确认冻结设计” | 整份详细设计（含主题7工程细化）冻结为 D-frozen-1 |

### 10.2 明确修订

| 旧记录/事实 | 修订及原因 |
| --- | --- |
| 原Java Div仅保护+0 | C09改为两种零均返回+1；原Java单列差异，不能报普遍等价 |
| Java原解析器容错/故障行为 | C10严格结构及空白扩展；有效原表达式兼容，非法输入提前报错 |
| 主题四第一轮身份检查 | 第二轮补阶段资格、准备匹配、Context生命周期及失败合同；随C11整体确认 |
| 主题七预告“附探针证据包” | 当前无法取得此前临时原始证据；本次只交付新来源审计包，历史数量清楚标来源，不补造 |

### 10.3 已随整体确认冻结的工程细化

以下没有重新打开已确认语义，而是将实现所需的未命名细节具体化：目标模块/API可选字段；版本字符串和结果格式名；身份payload及规范字节；错误位置算法和优先级；manifest字段形状；八批顺序与K追溯表。这些细化在审阅稿生成时仍为待确认；现已随 C14 的整体明确确认纳入冻结设计。

当前没有需要另开一轮选择的关键语义歧义。原始探针不可访问、正式JDK17及完整GP验收未执行属于**证据/实施待办**，不是已通过或已失败的设计语义。

### 10.4 未完成工作与限制

| 待办 | 状态/影响 |
| --- | --- |
| 本稿整体审阅和冻结 | 已完成，C14；后续进入按设计分批编码与验证 |
| 恢复此前探针原始文件 | 当前不可访问；可选恢复，不阻碍从源码重新做正式验收 |
| 深文本解析、工厂、v2正式实现 | NOT_EXECUTED；只有隔离设计报告，非生产能力 |
| JDK17同语义参考、身份编码黄金向量 | NOT_EXECUTED；不能用JDK21历史探针替代 |
| 完整固定/动态GP跨语言及旧功能回归 | NOT_EXECUTED；均为B06—08必需交付 |
| 论文规模性能/训练 | 明确不在阶段D |

冻结记录：用户已明确接受本稿，冻结条件已满足。后续改变语义、范围或兼容合同须先形成修订记录并取得明确确认；普通实现细节按本稿和工程判断推进，不逐项重复索要确认。编码按八批执行；实现验收另出报告，不在冻结设计中预填通过。

### 10.5 冻结版本追溯

- 确认依据：用户实际回复“确认冻结设计”。
- 冻结日期：2026-11-06。
- 前版：D-review-1，SHA-256 `1c8c1e7d3db01c3d5f1e55d919dbd3d481b7267976f238372a6c76a7c83b48aa`。
- 本版：D-frozen-1，仅更新冻结状态、C14 和实施入口说明，未变更语义、范围、配置、身份编码或验收合同。
- 第 11.3 节来源审计包继续保留为 D-review-1 的审计检查点，其 document-qa.json 的文档摘要对应审阅版，不是冻结版摘要；源文件和原始审计结果未改写。

## 11. 源码入口索引及证据说明

### 11.1 引用约定

`P:` 相对于 `fogsim-0.3.0/src/fogsim/`；`T:` 相对于 `fogsim-0.3.0/`；`J:` 相对于 `Fog-Computing-multiDeviceDebug/src/mengxu/`。行号指本附件基线，后续实现移动行号时同时保留源码摘要和类/方法名。

| 入口 | 位置/作用 |
| --- | --- |
| P: rules/base.py | PriorityRule.priority 约10行；RuleKind两角色 |
| P: rules/contexts.py | StateView约11；from_state约19；RoutingContext约25；SequencingContext约34；graph_fingerprint |
| P: rules/selection.py | double_compare:8；is_preferred:22；_choose:34，逐项写priority |
| P: model/resource.py | enqueue:31；remove_waiting:45；waiting_*；begin_execution:67 |
| P: model/workflow.py | task_count/completed_task_count约25/29 |
| P: simulation/engine.py | EventContext.view:23、choose_route:33、choose_next:37；dispatch:47；Engine构造:119；run:135 |
| P: simulation/events.py | JobArrivalEvent.trigger；ProcessFinishEvent.trigger:68，后继两轮和队列内评分 |
| P: simulation/dynamic.py | DynamicEngine.__init__:15起，当前未传sequencing的桥接缺口 |
| P: config.py | RunConfig:9；load_config:37，旧固定规则槽 |
| P: experiment_config.py | RuleConfig:116；DynamicRunConfig/ReplayRunOptions；_rule:348；parse_experiment_config:353 |
| P: simulation/trace.py | state_snapshot:17；TraceRecorder.decision:95；状态和actions重复分数 |
| P: simulation/metrics.py、dynamic_result.py | RunResult/collect_result及动态扩展；结果字段保持 |
| P: replay/loader.py、engine.py、source.py | v1输入读取、运行后参考比较、全局尝试游标 |
| P: replay/export_input.py | export_replay_input，来源捕获不读取参考 |
| P: io.py | write_json_atomic，allow_nan=False |
| P: validation/dynamic_compare.py | first_difference约30—40行有限容差；normalize_python与chronological比较 |
| T: tools/java_support.py | reference_jdk:43，正式Java17检查 |
| T: tools/java/src/fogsim/adapter/FixedInstanceMain.java | 旧固定参考只支持FCFS/FixedResource；ObservedRule.priority约414 |
| T: tools/java/step4/fogsim/adapter/DynamicExportMain.java | 旧动态入口约52行写死两种FCFS |
| J: gp/terminal/JobShopAttribute.java | value:64、relativeAttributes:186；十项定义 |
| J: rule/evolved/GPRule.java | readFromLispExpression:51；priority:83；原文与树可分离 |
| J: gp/function/{Add,Sub,Mul,Div,Max,Min}.java | eval约48/49；Div保护约66；Max/Min分支约63 |
| J: util/lisp/LispParser.java、LispUtil.java | parseJobShopRule:18；parseNode:29；splitArguments:13 |
| J: rule/AbstractRule.java、taskscheduling/TaskOption.java | nextTaskOption:27、priorTask:49；priorTo:107 |
| J: taskscheduling/Server.java、MobileDevice.java | 缓存增减/读取；Server clone不保持缓存 |
| J: gp/terminal/TerminalERC.java | eval约34，运行时写parent/argposition |

精确 Python 类/方法行号见随附 `python-source-index.json`；它由本附件 AST 自动生成，可优先于表中“约”行号。Java 以本节文件和方法定位，摘要见审计包。

### 11.2 此前对话报告的设计探针（原始文件当前不可访问）

| 主题 | 报告结果 | 证据限制 |
| --- | --- | --- |
| 特征 | 22状态/220值逐位；7事件前缀；本地残差/服务器置零 | 不是完整运行验收 |
| 原数值与解析 | 864函数组；139Java表达式案例含2超时；76双方有效；58数字；8格式扩展 | JDK21设计探针；不等于正式1536项门禁 |
| 双零修订 | 144除法输入、12定点表达式及路由选择 | 原Java12组负零差异单列 |
| 接口/共享 | clone缓存变化；跨模型共享；深AST2500编译/求值 | 没有证明深文本解析 |
| 副作用 | 动态Arrival评分RNG不推进；42检查作用域、13次外围状态观察 | 不是系统性生产验收 |
| Context/失败 | 旧Context 27与新Context37；第二候选失败保留[7,202] | 隔离样机和现有引擎故障注入 |
| 协议 | 6身份向量、12位模式往返、7非法标签、5001节点JSON | 本稿精确字节规范仍须重新生成黄金证据 |
| 验收设计 | 旧FCFS7事件/3决策/256浮点，无排序；F03样机12事件/5决策，12时选第二项 | 不算生产GP配置或Java完整对照 |

### 11.3 本次来源审计包

`fogsim-stage-d-source-audit.zip` 包含只读审计脚本、命令说明、source-audit.json、Python入口索引、两侧源码摘要和PDF第7—8页的文本提取及其stderr。文本提取器对双语PDF产生色彩指令告警，日志保留；提取文字用于定位论文说明，不宣称本次重新完成表格渲染核对。

脚本不实现GP、不运行训练、不改生产源码或历史预期；结果 classification 为 SOURCE_AUDIT_ONLY，simulation_or_gp_acceptance_executed=false。审计包不包含不可访问的历史探针或虚构运行输出。

**当前状态：详细设计已确认冻结（D-frozen-1/C14）；生产实现未开始；正式阶段D验收未执行。**
