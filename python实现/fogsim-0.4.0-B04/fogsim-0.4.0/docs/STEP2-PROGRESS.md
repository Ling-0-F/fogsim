# 冻结设计实施记录：第 2 步

日期：2026-11-04（America/Los_Angeles）。基于已交付的 step1 快照，在独立 step2 工作副本继续实现。上传的 0.2.1 ZIP 与 step1 ZIP 均未修改。冻结设计 §§7、8、13 及第 19 节 V02–V05 是本轮依据；没有重新讨论已确认语义。

| 模块 | 本轮完成 |
| --- | --- |
| `instances/dax.py` | 标准库 XML 解析；空/标准命名空间、结构名称大小写、原 ID、任务/边/邻接保序；非法结构/引用/重复/环明确失败；原字节 SHA256；数量诊断 |
| `instances/catalog.py` | 0–19 目录映射；只加载配置类型范围，全部成功才发布不可变目录；配置路径不依赖启动 cwd |
| `instances/templates.py` | 追加不可变诊断；提供返回独立数据的有序 adjacency；原构造参数保持兼容 |
| `randomness/samplers.py` | 冻结、只保存参数的实数/整数/指数/权重/带宽 sampler；显式传入共享 RNG；按参数 clone，不操作 RNG；上下行独立角色 |
| `randomness/state.py` | 模板合法后创建唯一 `random.Random(encode_seed(seed))`；单轮输入准备、Python 原生 RNG 快照及仅 RNG 的恢复保护 |
| `dax/` | 附件顶层 dax 的 22 份原始 XML 与逐文件来源清单；示例配置的 dag_root 已有对应输入 |
| 测试及 `tools/check_step2.py` | Python 边界/保序/生命周期基础测试；实际编译并运行原 Java 解析器和 sampler 的独立核对工具 |

## 调用与范围

```python
from fogsim import load_experiment_config, parse_dax, load_dax_catalog, prepare_random_input

config = load_experiment_config("configs/examples/step1_dynamic.json")
catalog = load_dax_catalog(config)  # 不创建 RNG，不采样
template = parse_dax("dax/HEFT_paper.xml")  # dag_type_id=None，保留数量诊断
prepared = prepare_random_input(config.single_run(0))
assert prepared.catalog.template(0).dag_type_id == 0
value = prepared.samplers.workload.sample(prepared.rng)
```

`prepare_random_input` 只接受已展开、含有效 seed 的单轮 dynamic ExperimentConfig；不建立资源、任务、统计或 Engine。返回时输入流仍位于编码 seed 起点，没有资源采样前缀。第 3 步应将其作为上下文准备的一部分调用，并让所有设备及环境使用同一个 rng 和同角色 sampler。当前同角色消费者共享及不同准备实例独立已测试；真正设备对象接入后的共享关系随第 3 步验证。

`snapshot()` 保存实际 getstate 数据、状态版本、Python 版本/实现及编码版本，读取/计算指纹不抽数。`restore_rng` 校验版本并在非法状态时回滚；它只恢复 RNG，不恢复事件、资源、统计或 B。Context 的 reset/rerun/rotateSeed 和轮次边界约束留在第 5 步，不能把此方法当作完整模拟检查点或 reset 实现。

纯模板和目录不持有 RNG 或运行 Task。XML 按解析后的属性值保留 ID；元数据 uses/runtime 不参与任务参数。模板 dependencies 保持 XML 边序，adjacency 保持每个节点的父子追加顺序。标准图没有重排或添加虚拟节点。目录与模板一旦返回，不再读取变动的 XML；重新加载才观察新文件。

## 源码事实和采用行为

Java 原 `WorkflowParser` 按直属 job/child 遍历，以出现位置建立 Task 序号，依赖按 parent 出现顺序追加；原类型目录映射已从 `DAGType`、`DAGTypePath.getDAGTypePathForSubmit` 核对。Python 对重复 ID/边、空图、循环、未知及前向引用采取冻结设计要求的显式拒绝；这比原 Java 的宽松或静默跳过更严格，不作为非法输入的跨语言正常通过。

Java `UniformSampler.next` 调用 Commons Math nextUniform；Python 保留拒零及 `u*b+(1-u)*a`，不用 `a+u*(b-a)`，不钳制或重抽缩放端点。整数直接调用 randint（单点仍调用）；指数直接调用 expovariate(1/mean)，允许返回 0。权重/云带宽读取拒零单位 u：u<0.2 对应 4/256，u<0.8 对应 2/512，否则 1/128；边缘固定 1024，不推进 RNG。原 BandwidthCloud/Edge 的 getMean 返回值不作为分布依据，核对使用实际 next。

Java 与 Python 使用各自 RNG/底层算法，同 seed 不要求逐个随机值相同。分布检查每个角色独立设置 seed 是统计测试方法，实际输入消费仍使用单一共享流；没有在业务采样中按角色重新设种。

## 实际验证

在项目根目录执行的命令：

```text
PYTHONPATH=../../.test-deps:src python -m pytest -q tests/unit/test_dax.py tests/unit/test_samplers.py tests/unit/test_random_input_state.py --junitxml=outputs/step2/contracts.xml
PYTHONPATH=../../.test-deps:src python -m pytest -q tests/unit tests/integration --junitxml=outputs/step2/python-regression.xml
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server PYTHONPATH=../../.test-deps:src python tools/check_step2.py
```

常规开发环境安装 `.[test]` 后可直接 `python -m pytest ...`。正常 JDK 17 环境运行 `python tools/check_step2.py --java /path/to/jdk17/bin/java`；工具优先使用 javac，缺少启动文件但存在 jdk.compiler 时使用编译器模块。`--python-only` 明确不执行 Java，报告不标跨语言通过。

| 验收项 | 本轮真实结果与边界 |
| --- | --- |
| 新增 Python 测试 | **88 passed，0 failed/errors/skipped**；首次为 87 passed/1 failed，问题见下文 |
| Python 单元+集成回归 | **443 passed，0 failed/errors/skipped**；包括 step1、旧 CLI/repeat、14 固定配置精确轨迹及精度负例 |
| V02 | **20 标准 DAX 实际 Java/Python 正常拓扑对照通过**；逐项比较任务顺序、XML ID→Java 位置、父和子列表；原 Java 类无覆盖构造或方法修改 |
| V03 | Python 解析负例、命名空间/顺序/诊断、辅助图已通过；非法输入明确差异，不宣称与原 Java 的宽松行为相同 |
| V04 | 确定性边界通过；两种语言分别对理论分布通过，每侧 14 角色×3 seed×100000=**420 万次**；不比较随机数逐个相等 |
| V05 | 构造、clone、参数冻结、上下行角色区分、单流调用顺序、新准备实例独立通过；实际环境/设备消费集成随第 3 步验证 |
| seed/RNG 基础 | signed64 两端、正负值编码起点、只创建一条输入流、快照不抽数/恢复后续值/失败回滚通过；完整 Context 生命周期未实现 |

分布样本量、seed 集合 0/1/20261104 和阈值在运行前按冻结设计写入工具：离散频率绝对误差≤0.01；实数均值误差≤宽度×0.01；指数均值相对误差≤0.02、方差≤0.05、CDF(mean)误差≤0.01。常量与整数单点精确检查。没有依据结果放宽阈值。

运行环境为 CPython 3.12.14、pytest 9.2.0，以及 Ubuntu OpenJDK **17.0.20+8-1-24.04-Ubuntu**。本轮发现系统 libjli.so 实际存在，通过当前进程 LD_LIBRARY_PATH 启动了 Java；未改系统配置。没有 javac 启动文件，但 jdk.compiler 可编译，因此使用 `java -m jdk.compiler/com.sun.tools.javac.Main`。这更新的是本轮环境证据，不回写 step1 当时未执行的历史结果。只要求 JDK 主版本 17，未重新锁定厂商/更新号。

证据保存在 `outputs/step2/`：`contracts.xml`、`python-regression.xml`、`checks.json`、两侧完整 topology/raw、两侧逐 seed 分布统计、`java-build.json` 和编译/运行输出。构建清单校验原 659 份源码/依赖指纹，记录来源、命令、版本和无 overlay；编译产物只用于本轮，交付保留可重建源码。

开发期首次新增测试的失败来自一个手写预期：a=1，b=1+2^-52，u=1-2^-53，`u*b` 舍入为 1，再加 2^-53 是中点舍入，仍为 1。原测试误以为必定得到上端点。保持 sampler 公式不变，补入此位模式案例，另以 u=0.75 验证能舍入到上端点；原失败 XML 保留在 `development-float-expectation.xml`。未修改任何旧预期来掩盖行为变化。

## 状态与下一步

没有发现需要改变冻结语义的问题；诊断数据结构、API 名称和输入准备对象是本轮实现具体化。第 2 步代码及上述验证完成，可进入第 3 步：复用 prepared 的 catalog/samplers/rng，按设备→边缘→云顺序采环境，再按 Java 两遍顺序生成完整候选与 TaskOption，验证 V06–V08/V11。

尚未实现/验证：环境采样、实际两遍生成、动态接纳/Arrival/统计/B/Context 生命周期、Java 动态输入导出、动态重放、固定投影、释放服务、实验批次与新 CLI。完整 V01 的 Java 调度对照、96 扫查与旧组件 oracle本轮未重跑。V02 的解析对照与分布验收不等于动态调度对照，不宣称论文实验或 GP 完成。
