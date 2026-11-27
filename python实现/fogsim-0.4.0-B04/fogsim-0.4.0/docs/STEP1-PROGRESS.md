# 冻结设计实施记录：第 1 步

日期：2026-11-04（America/Los_Angeles）。这是基于 0.2.1 的开发快照，尚非完整动态版本或新的正式验收版。用户本次指令冻结上传设计；文档中的历史审阅状态不再阻止编码。原始 ZIP 保留不变。

## 本轮交付

| 模块 | 已实现的职责 |
| --- | --- |
| `experiment_config.py`，`input_validation.py` | `fogsim.experiment` v1；dynamic/replay 分层；严格字段、类型、范围、有限值和跨字段校验；纯参数冻结及有效参数指纹 |
| `seed.py` | signed64-bits-v1 编码和 Java long 加 10000 的纯回绕函数；尚未创建随机流或实现 context 生命周期 |
| `instances/templates.py`，`identity.py` | 不可变拓扑及类型+内容哈希引用；XML ID→Java 位置；资源独立编号空间；不解析 ID 后缀来建立运行身份 |
| `environment/spec.py` | 有序设备/服务器实际数值快照、候选合法性、来源及内容指纹；不采样，不建运行资源 |
| `instances/generated.py` | 完整物理任务/边/候选、生成原因/尝试、接纳映射、不可变归档；引用、顺序和数值校验 |
| `model/task.py`，`workflow.py` | 在原字段后追加来源元数据、可空 Java 序号及边状态；明确区分 UNAVAILABLE/RETAINED/RELEASED 的访问器 |
| `simulation/state.py` | 固定建图复用显式资源身份映射，资源对象创建与遍历顺序不变 |
| `config.py`，包公共导出 | 新配置入口可导入；`RunConfig/load_config/create_engine/simulate` 的固定语义不变 |

未增加 GP、采样器空壳、动态模拟入口空壳或另一套事件循环。`release_edge_data` 的实际释放服务按用户实施顺序留在第 7 步，当前只建立状态/访问契约，不宣称 V20 已通过；不能在后续最终交付时省略该服务。

## 精确配置用法与本轮实现选择

```python
from fogsim import load_experiment_config, parse_experiment_config

config = load_experiment_config("configs/examples/step1_dynamic.json")
assert config.run.max_events is None
single = config.single_run(0)  # 纯配置展开；不会创建环境、准备工作流或运行事件
```

示例文件仅可解析；尚不能用旧 CLI 执行。它们放在 `configs/examples/`，避免被原固定配置发现逻辑误读。输入路径在配置阶段不要求存在，DAX 文件与目录检查在第 2 步执行。`parse_experiment_config` 遇到相对路径必须显式给 `base_dir`；直接构造 SourceConfig 须给绝对 `Path`。有效路径在加载后固定。

`source.samplers` 的可调实数均匀范围字段为 `workload`、`data_size`、`edge_data`、`processing_rate_device`、`processing_rate_edge`、`processing_rate_cloud`，值均为 `{lower, upper}`。工作量/算力下界严格正，数据下界允许 0，所有实数范围严格 lower<upper。类型范围允许整数单点。冻结设计未规定 sampler 子字段的 JSON 拼写，本轮据此具体化，未改变任何分布语义。

固定 profile 字段为 `inter_release_mean=100`、`weight_profile="two_six_two"`、`cloud_bandwidth_profile="bandwidth_cloud"`、`edge_bandwidth=1024`；可省略，显式冲突时报错。不开放其他分布家族。`effective_parameters()` 另外完整列出固定值、阈值、取值顺序和算法标识；`to_dict()` 保持可被严格配置解析器重新读取。返回字典都是独立副本。

动态 repeat.count>1 须显式选择 fresh_same_seed / fresh_seed_list / java_rerun。seed 列表模式可不写 source.seed；同时给时须等于首项。`single_run(index)` 仅展开一轮配置，java_rerun 的上下文延续将由第 7 步实验执行器负责。replay 的 repeat 归一化为 same_input，每轮来源位置重置；不接受 seed 或 N/W 覆盖。verify_reference 必须给参考路径且不准覆盖规则；input-only 执行使用 reuse_inputs，比较状态由后续模块标为 NOT_COMPARED。配置解析不读取输入，因此 replay 目标资源实际合法性留到输入装载后校验。

没有调整冻结语义。N=1,W=0 配置仍合法；本轮不提前把其运行失败结论记为已验证。计数上限与 seed 回绕分开处理。

## 输入与身份约束

- 拓扑、环境和归档使用冻结 dataclass 和逐层复制的 tuple；不包含运行对象、队列、RNG、Context 或参考输出。`OptionSpec` 复用旧不可变描述，新增 TaskInput 对其数值做严格校验。
- Task.id 为原字符串，Java 序号为模板列表位置；固定模式旧 ID 和任务顺序保持。运行 Task.java_index 对旧输入默认为 None；动态建图在第 3 步按模板映射填写。
- 资源数字身份由明确顺序产生：设备独立从 0 开始；服务器边缘后云。固定自定义 ID 和原始资源字典顺序保持。标准动态名字的合法性校验不承担运行 numeric_id 分配。
- 模板 dependencies 保留 XML 边序；候选 edges 使用任务→children 采样序，两者通过父子 ID 关联。归档检查完整匹配，绝不将边值数组顺序当成 parents 累计顺序。
- 每条候选记录与一次尝试一对一，record_id 为从 1 连续尝试序号的十进制字符串；正式 ID 取接纳前 G，拒绝不占号。初始化设备顺序及一次 Arrival 仅触发一次尝试通过引用校验保护。
- 归档可保存已完成候选的有效前缀，用于准备期诊断；它不是带 capture.complete 的 ReplayInput。完整重放文件及覆盖判定属于第 6 步。边总量/UT/PT/DT 的公式审计属于第 3/6 步，不静默重算替换记录值。
- 运行边映射是另外建立的可变副本。清空或修改它们不影响归档；旧固定数据未知时保持 None，不伪造 0。

## 证据与本轮验证

| 类别 | 事实及适用范围 |
| --- | --- |
| Java 源码事实 | `WorkflowParser.java:114–121` 按 job 出现位置编号；`DynamicSimulation.java:127–163` 设备独立、边缘后云；`MobileDevice.java:348–433` 两遍生成、取全局 ID 后接纳；`SystemState.java:69–83` 严格 release>clock 才登记。仅静态读取，本轮未运行 Java 动态路径 |
| Python 0.2.1 既有事实 | 固定严格加载；每轮规范对象图；旧 RunConfig max_events=100000；已有可空物理字段；四事件、比较器、队列、日志和固定 repeat 不变 |
| 冻结设计要求 | §§5、8.1、9.5、16–18 的数据、配置、身份和 seed 边界已经落实到本轮代码；V09/V11/V15/V21/V22 只完成相应纯契约部分 |
| 实际运行结果 | 见下列命令与 `outputs/step1/`，不同于原 0.2.1 历史证据 |

执行目录为项目根目录；当前环境将 pytest 9.2.0 安装在工作区独立测试依赖目录，无需重建完整 Java 环境。可在常规开发环境直接执行 `python -m pytest`，本次实际命令为：

```text
PYTHONPATH=../../.test-deps:src python -m pytest -q tests/unit/test_experiment_config.py tests/unit/test_input_contracts.py --junitxml=outputs/step1/contracts.xml
PYTHONPATH=../../.test-deps:src python -m pytest -q tests/unit tests/integration --junitxml=outputs/step1/python-regression.xml
```

当前结果：新增契约测试 **193 passed**；单元+集成共 **355 passed，0 failed，0 errors，0 skipped**。其中 14 个正式固定配置的完整 result/events/decisions 与保存的 0.2.1 Python 轨迹精确相等；旧输入、旧配置、CLI、repeat、规范引用和已知执行精度负例通过对应回归测试。首次三组旧接口检查为 76 passed，首次新增契约为 189 passed，补齐顺序/隔离测试后为上述最终计数。

开发中曾有一轮 355 passed、1 failed：动态示例重复保留在顶层 configs，被原固定配置自动发现，旧严格加载器正确拒绝了新格式。删除该重复文件，仅保留 configs/examples 下的示例后重跑；未修改已有预期或放宽旧加载器。开发期 XML 另存于 `outputs/step1/development-example-placement.xml`。

校验不抽数的测试禁止创建 random.Random 及调用常用抽样方法，并检查全局 random 状态未变；这只证明本轮纯校验路径。共享输入流、sampler 构造/复制、reset/rerun/rotateSeed 资源及 B 延续均未实现，不能据此宣称生命周期验收通过。

未执行：完整 V01（96 扫查、组件 oracle 与 Java 重新对照）、V02–V22 的动态运行部分。当前 `/usr/bin/java -version` 因缺少 libjli.so 失败，未找到 javac；未为第 1 步搭建 Java 环境。没有使用跳过测试伪造正式跨语言门禁通过，也未调用正式 release 工具。原 `outputs/validation-manifest.json`、`RELEASE-FILES.json` 及旧 outputs 是 **0.2.1 历史证据**，不描述当前工作副本；本轮包标为 step1 开发快照，当前文件指纹见 `outputs/step1/current-files.json`。

## 后续衔接

第 1 步已实现并完成上述 Python 验证。第 2 步接入现有 DagTemplate / WorkflowTypeRange / SamplerParameters / seed 编码，完成 20 类型 DAX 目录与严格保序解析、共享 Random 的构造及 sampler；落实 V02–V05 与 seed 测试。参数校验后再加载模板，所有模板合法后才允许采环境；校验和模板加载均不推进随机流。环境采样及两遍建图仍归第 3 步。Java 导出器在第 6 步前完成，不阻塞第 2 步。
