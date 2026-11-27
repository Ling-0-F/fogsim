> 当前累计快照：B05 重新生成版，待用户确认。最新使用与验证说明见 [development/b05/README.md](development/b05/README.md)。B01—B04 文档是历史检查点；阶段 D 未完成，GP 跨语言验收未执行。

> 当前累计开发快照：阶段 D / B04。请先阅读 [B04 说明](development/b04/README.md)、[验证报告](development/b04/REPORT.md) 与 [续接记录](development/b04/HANDOFF.md)。阶段 D 尚未完成。

# fogsim 0.3.0

Xu等（2023）雾计算工作流调度Java模拟器的Python复现。保留原固定内核，提供DAX拓扑、共享输入RNG、动态多设备、Java兼容统计/生命周期、完整输入归档、生产重放、固定投影、边数据清理和显式重复实验。

本版本以本对话第7步交付包为基线完成冻结设计逐条审计。149项义务和V01～V22的源码、测试及跨语言证据对应关系见 [CONTRACT-AUDIT](docs/CONTRACT-AUDIT.md)；本轮最终结果见 `outputs/final/acceptance.json` 和 [FINAL-ACCEPTANCE](docs/FINAL-ACCEPTANCE.md)。包名、Python版本、CLI和新生成输入的实现标识均为0.3.0；输入/参考各自schema_version保持1。

## 安装

Python>=3.11，模拟器本身不需要Java或第三方库；测试需要pytest，跨语言验收需要JDK17。允许不同JDK17厂商/更新版本，并记录实际指纹。完整安装示例：

```bash
python -m venv .venv
python -m pip install -e '.[test]'
python -m fogsim --version
```

请使用所建虚拟环境的Python（Windows为`.venv\Scripts\python.exe`，Linux/macOS为`.venv/bin/python`）。本次实际CPython3.12.14、pytest9.2.0、Ubuntu OpenJDK17.0.20+8，编译器为已有jdk.compiler模块。普通JDK可直接使用javac；当前受限运行环境额外需要LD_LIBRARY_PATH，详见最终验收记录。

## 运行

```bash
# 旧固定接口和repeat输出结构保留
python -m fogsim --config configs/chain_fcfs.json --repeat 2 --output outputs/fixed.json

# 显式动态重复模式：fresh_same_seed / fresh_seed_list / java_rerun
python -m fogsim dynamic --config configs/examples/dynamic_rerun.json --output outputs/batch.json --archive-dir outputs/inputs

# 单独input即可重放；输入复用不产生原参考轨迹通过结论
python -m fogsim replay --input outputs/inputs/run-000000.input.json --repeat 2 --output outputs/replay.json

# 使用本轮独立Java参考进行验证（含完整前后态及实际owner/staging）
python -m fogsim replay --config configs/examples/replay_verify.json --output outputs/verified.json

# 固定投影附独立.projection.json损失/哈希清单
python -m fogsim export-fixed --input outputs/inputs/run-000000.input.json --output outputs/projected.json
python -m fogsim --instance outputs/projected.json --output outputs/projected-result.json
```

配置内路径相对配置文件；直接CLI路径相对cwd。`dynamic --help`、`replay --help`、`export-fixed --help`列出全部选项。仅dynamic可覆盖seed；多轮须显式模式，不自动seed+序号或rotate。退出码0成功、1运行/批次/要求的参考验证失败、2输入错误；未知程序异常传播，输出不能遗留旧成功。

`--no-trace`关闭详细事件/决策，仍保留任务事实和完整输入。`verify_reference`需要详细轨迹才能报告完整正常一致；`reuse_inputs`只可改变已支持规则，保持原N/W、来源和环境。记录不足/调用错位有独立诊断，不补输入。

## Python API

```python
from fogsim import (load_experiment_config, create_dynamic_context, run_experiment,
                    load_replay_input, create_replay_engine, simulate_replay,
                    export_fixed_instance, release_edge_data, AdmissionResult)

config = load_experiment_config('configs/examples/dynamic_rerun.json')
batch = run_experiment(config)
# 单轮Context需要已经展开的配置
context = create_dynamic_context(config.single_run(0))
first = context.run()
second = context.rerun()             # 延续RNG/B，复用环境数值，新对象图
context.reset(-1)                    # 重设输入流，不重采环境，保留B；只准备
third = context.run()
```

直接`simulate_replay(input, options, reference_path=...)`可在运行完成后返回嵌套比较报告；input为对象时可显式给input_path用于清单绑定。reuse_inputs不打开参考文件。

正式内部接纳入口`AdmissionService.admit`返回`AdmissionResult(accepted, workflow, reason_code)`；普通release拒绝是返回值，生成异常仍传播。历史`attempt`是保留Workflow/None返回的兼容便利适配。默认保留运行边映射，`release_after_materialization`显式启用；只释放运行副本两张映射，独立归档、拓扑、总量、候选时长及完成记录保留。

## 验收复跑

```bash
python tools/check_step2.py --output outputs/my-final/step2
python tools/check_step3.py --output outputs/my-final/step3
python tools/run_final_acceptance.py --phase dynamic --output outputs/my-final
python tools/run_final_acceptance.py --phase performance --output outputs/my-final
python tools/validate.py
```

动态Java导出目录必须为新目录，以免混合新旧捕获。本轮固定的汇总路径为`outputs/final/step2`、`outputs/final/step3`、`outputs/final/current/dynamic`、`outputs/final/performance`。默认汇总/发包用`python tools/assemble_acceptance.py`、`python tools/build_release.py`；后者同时检查完整V01、逐条契约及当前源码快照，缺证据不会发布成功包。自定义验收输出应使用相应新记录审阅，不覆盖历史来源。

## 一致性范围

跨语言对照以相同实际输入为基础，Python与Java随机数算法/逐值不同是设计允许的差异。动态指标只用Java兼容统计集合；固定投影两侧执行全集，其指标独立于原动态统计。正常、预期差异、覆盖不足、未执行和基础设施错误分别报告。

旧`producer_device_id`实际是owner，历史文件不改；新Java参考分别观察真实owner/staging，并有前后态/错误边界。旧参考仍可按已有字段比较，报告`full_contract_verified=false`；最终严格门禁仅使用本轮新完整参考。

已知binary64边界：正PT仍可能使总执行区间归零。Python在接受计划前明确FAILED；原Java会出现重叠。这是保留的预期差异，不算正常通过。固定Java适配器仅支持FCFS/fixed_resource，并使用未被这些规则读取的物理占位；不能扩展为GP/真实物理特征一致。

两个可选native_*大型固定投影未在本轮执行；V19六个非空投影、十条规则路径构成本轮明确验证范围。性能测量只覆盖具体初始化/小型完整运行，不宣称普遍加速。GP、十个特征、演化训练、论文规模实验、D20正式实验参数勘误解释、网络排队/抢占/重试均在本阶段之外。

历史第1～7步报告及原始证据保留；它们描述各自版本和验证范围，不能代替本轮当前验收。原始Java源码/JAR和第4步输入/参考不改，相对第7步补丁为`CHANGES-FROM-STEP7.patch`，全包文件哈希为`RELEASE-FILES.json`。
