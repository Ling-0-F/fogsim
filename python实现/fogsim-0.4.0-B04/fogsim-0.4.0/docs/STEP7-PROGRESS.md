# 冻结设计实施记录：第 7 步

日期：2026-11-05，America/Los_Angeles。直接基线为本对话交付的 `fogsim-0.2.1-step6.zip`，SHA-256 `0c419cc5623a6166be4c2b104322ccc6c573448de96e1990b0fd633fa47909ab`。在独立工作副本实施，保留第6步ZIP及原8份来源；未搜索其他私人文件。冻结设计按确认状态执行。

## 范围与实际改动

| 模块 | 实际作用 |
| --- | --- |
| `simulation/cleanup.py` | 工作流级原子预检；仅释放两张运行时边映射，返回首次任务数、映射条目数和幂等/不可用状态 |
| `simulation/admission.py`、`dynamic.py`、`dynamic_result.py` | 候选/接纳完整归档后、发出Arrival前执行显式清理策略；保存清理计数；原事件/调度/保护次序不变 |
| `simulation/context.py`、`replay/engine.py` | 开放已配置的release_after_materialization；随机、重放均可使用；默认retain保留 |
| `experiments/runner.py` | fresh_same_seed、fresh_seed_list、java_rerun及重放same_input；结果快照、失败分母、均值/标准差和未完成检查点 |
| `replay/export_input.py`、`replay/loader.py` | Python完整观察输入导出为独立schema-v1；明确Python分布标识，支持单独重放；不把Python采样器标作Java采样器 |
| `cli.py`、`io.py` | dynamic/replay/export-fixed、显式覆盖、独立输入文件、原子结果/检查点；旧固定入口和repeat输出格式保留 |
| `tools/java_support.py`、`validate.py` | V01能力检查认可本机已有jdk.compiler；缺失XML/失败运行不能沿用旧成功清单；Java原方法不变 |
| 测试、`tools/check_step7.py`、配置示例 | V20/V21、实际CLI进程、跨语言清理等价、准备阶段内存/时间测量和完整V01证据 |

旧四事件、两层堆、规则比较、共享RNG、signed64 seed、B延续、拒绝不重抽、物理/统计完成集合及预算/保护顺序未改。不实现GP或论文训练。

## 边数据释放（V20）

`release_edge_data(workflow, archive)`在任何写入前核验整张工作流：独立完整候选与成功接纳、身份/顺序、父子规范引用、全部选项及物理字段、两端边数据值和顺序、映射不别名。预检末任务失败时，前面任务的映射也不改变。清理仅将input_data_by_parent/output_data_by_child置None并标RELEASED；保留任务、选项、拓扑、总量、执行和完成记录。固定UNAVAILABLE跳过；重复调用不重复计数。`task.edge_data()`对RELEASED明确报错。

自动策略在本工作流完整记录入档后执行，不要求整轮capture完成。随机及重放同样走集中接纳；不抽数、不推进时钟、不增加事件。retain/release的全部调度事实、完整trace、统计、归档及RNG末态已做等价检查；独立Java diamond参考在两种策略、各两轮下均核对。

内存测量仅覆盖300任务链的新建/生成/建图/初始化，不运行事件。实际current/peak/elapsed数值见`outputs/step7/checks/checks.json`。运行映射条目由598变0；这不意味着整图/归档/trace被回收，也不表示全程加速或峰值下降。本轮观察到释放模式当前占用降低，但预检带来的峰值和耗时增加。完整运行性能未测量。

## 批次与汇总（V21）

```python
from fogsim import load_experiment_config, run_experiment
batch = run_experiment(load_experiment_config("configs/examples/step7_dynamic_rerun.json"))
print(batch.status, batch.succeeded_runs, batch.failed_runs, batch.all_runs_mean)
```

- fresh_same_seed每轮新建上下文，属于可重复性检查，不是独立随机重复。
- fresh_seed_list严格使用完整signed64列表，每轮重新采环境；不使用seed+序号。
- java_rerun首次fresh，随后同上下文继续RNG/B、复用环境数值并重建对象；最后一轮后不额外reset、prepare或rotate。
- 重放每轮独立Engine/游标，从同一不可变记录起点开始；完整原记录保留，实际消费位置逐轮单列。

输入/配置错误在采样前拒绝。准备/运行领域失败归一化为FAILED并继续既定下一轮；java_rerun保留实际失败位置的流/B，不宣称对应Java异常尾部。未知程序异常原样传播并中止。`on_progress`提供INCOMPLETE前缀和最终快照；CLI未知异常留下batch_complete=false、原异常类型及空all_runs_mean，不遗留旧成功。

每轮保存公开seed、实际环境指纹、初始B、RNG边界指纹、来源消费/覆盖、场景指纹及状态。动态输入导出只读完整归档，包含拒绝/未到达/未完成者；关闭trace仍保留任务事实和完整输入。没有完整环境的准备失败不能伪造独立input，inputs相应位置为空并保留失败原因；部分生成的捕获complete=false，完整加载器拒绝。

运行结果的SUCCEEDED/FAILED保留模拟器事实。verify_reference比较在运行结束后进行；参考缺失轨迹/溯源/首差会另外记录verification_failures，批次返回失败，不修改原运行指标冒充调度失败。只有计划全部完成、全部正常、所需参考验证通过且场景兼容时才提供all_runs_mean。mean_over_successes同时给成功分母；failure_rate分母为已取得完整结果的运行数；not_run表示尚无完整结果的计划位置，中断信息另列。成功数不足2不提供样本标准差。若跨fresh轮次的DAX内容改变，禁止混合汇总，明确aggregation_compatible=false。

## 命令入口

```bash
python -m fogsim dynamic --config configs/examples/step7_dynamic_rerun.json --output outputs/my-batch.json --archive-dir outputs/my-inputs
python -m fogsim dynamic --config configs/examples/step7_dynamic_seeds.json --no-trace --output outputs/my-seeds.json
python -m fogsim replay --config configs/examples/step7_replay_repeat.json --output outputs/my-verified.json
python -m fogsim replay --input outputs/my-inputs/run-000000.input.json --repeat 2 --output outputs/my-replay.json
python -m fogsim export-fixed --input outputs/my-inputs/run-000000.input.json --output outputs/my-fixed.json
python -m fogsim --instance outputs/my-fixed.json --repeat 2 --output outputs/my-fixed-results.json
```

旧`--instance`/`--config`仍只接受旧固定格式，输出及identical判断保留。新命令不猜配置mode。dynamic允许显式seed覆盖；replay不接受seed/N/W/环境覆盖。dynamic多轮没有显式repeat.mode时在采样前报错，CLI也不把单轮默认模式暗中扩成多轮。规则覆盖仍受verify_reference/reuse_inputs限制。

配置内路径相对配置文件，直接CLI路径相对cwd。输出不能覆盖输入、配置、参考及DAX源目录。结果和独立输入原子写入；archive-dir的batch-manifest列明本批实际文件，不能将旧的未列文件算作本批。固定导出附独立.projection.json，明确fixed_projection、损失、完整状态和哈希；原固定JSON没有新增字段。退出码0正常、1运行/批次或要求的参考验证失败、2输入/配置错误；未知程序异常传播。

## 实际验证与命令

最终逐项结果为`outputs/step7/current-validation.json`。针对性首轮198项通过，补充场景兼容和源目录保护后200项通过，0失败/错误/跳过；其中第7步新增37项。完整测试计数以正式XML为准。

```bash
PYTHONPATH=../../test-deps:src python -m pytest -q tests/unit/test_step7.py tests/unit/test_dynamic_context.py tests/unit/test_replay.py --junitxml=outputs/step7/targeted-final.xml
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server PYTHONPATH=src python tools/check_step7.py
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server PYTHONPATH=../../test-deps:src python tools/validate.py
```

当前环境为CPython3.12.14、pytest9.2.0、Ubuntu OpenJDK17.0.20+8；无javac launcher，实际使用jdk.compiler。常规JDK17可省略上述库路径，安装`.[test]`后可省略外部test-deps。完整JDK/源码/JAR/编译命令/原始输出指纹见本轮构建清单。

V01正式结果在`outputs/pytest-results.xml`、`outputs/validation-manifest.json`、`outputs/parity/`、`outputs/v2/`及`outputs/java_oracle/`。旧同名证据在重跑前复制至`outputs/history-step6-before-v01/`，第4步参考原件不改。正常跨语言通过、预期精度差异及基础设施/未执行分别报告；原精度反例不得改成正常通过。

仅更新了两处旧测试中“清理尚未实现应拒绝”的阶段性预期：现在检查已开放的能力；所有旧调度数值、轨迹、固定输入和Java参考预期保留。开发端到端试运行发现固定导出元数据合并重复schema_version导致TypeError，已修复为明确字典合并并增加端到端CLI检查。完整V01首轮971通过/1失败：新增清理诊断要求旧统计测试替身不存在的config字段；已仅在Engine提供清理诊断时采集，未改原统计预期。首轮原始报告保存在outputs/step7/v01-first；没有修改调度或参考数据。

## 交付与边界

相对第6步的补丁为`CHANGES-STEP7.patch`，文件清单为`STEP7-FILES.json`。独立应用补丁/ZIP导入和动态→重放→固定入口的可继续开发检查随包保存。

未发现必须调整冻结设计的冲突。现有Java固定适配器仍仅FCFS/fixed_resource和物理占位；本轮完整V01不扩大为任意输入、GP或论文实验等价。第6步两个大型固定投影仍未执行，本轮不为完成V01重复展开它们；完整运行性能也未测量。
