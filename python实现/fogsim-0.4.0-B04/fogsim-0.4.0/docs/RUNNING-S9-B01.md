# 0.4.0 S9-B01 运行说明

当前来源去重分发的前置说明见 [SOURCE-DISTRIBUTION.md](SOURCE-DISTRIBUTION.md)。基本 Python 使用不需恢复；Java 对照、完整兼容回归、历史审计前须恢复相应来源。

这是累计工程。新增评估层在 `src/fogsim/training/`，B08 模拟器生产源码除公开版本号外保持原字节。设计定稿在 `references/design/fogsim-0.4.0-design.md`，阶段 D 合同同目录；原 B08 ZIP 在原完整包的 `rollback/`；本分发通过来源索引按需恢复，其历史 evidence 未重新解释。

## 安装与基本使用

Python 3.11+。可直接安装本包附带的 `development/S9-B01/dist/fogsim_reproduction-0.4.0-py3-none-any.whl`，无须联网获取构建依赖。本批实际 Python 3.12.14，DEAP 没有安装；评估层和旧 API/CLI 均不依赖它。普通运行没有第三方 Python 运行依赖。`train` extra 的 DEAP 1.4.4 声明预留给 B02，B01 未完成其安装、传递依赖锁定和算子验证，不需安装该 extra。

```bash
python -m pip install -e .
fogsim --version
fogsim-train validate --config configs/training/B01.json --output outputs/my-B01-preflight
fogsim-train evaluate --rules configs/training/rules.json --plan outputs/my-B01-preflight/plans/train-0000.json --output outputs/my-B01-evaluation
```

不安装包时可用 `PYTHONPATH=src python -m fogsim.training.cli ...`。所有输出目录必须不存在或为空。validate 只预检、冻结、估算，模拟执行数为 0；B01 不提供 train 子命令，未知子命令明确退出 2。evaluate 读取一份冻结计划，按指定固定规则对完整执行。selected-rule 导入与演化训练入口在 B02 实现。

配置 `configs/training/B01.json` 含未来的 12 个体、4 代、2 trial 参数，仅用于预检；不会自动训练。实际 B01 smoke 每次只评估 2 条 fresh 运行，seed 101/102，1 台移动设备和 1 台边缘服务器，2 个 recorded、1 个 warmup、每条事件预算 2000。DAX 是包内 `examples/step5/dax` 的两任务小链。固定验证/test 列表各 1 条，seed 11001/21001，在训练前冻结。训练计划 4 代的清单全部展开，但不等于实际执行这些代。

`trace=selected_cases` 在 B01 表示保留各场景原有 trace_enabled；all/none 统一覆盖。代表、异常和小规模验收保存完整 trace。原始结果与可导出输入始终保存。

Python API 的脚本使用 spawn，务必放在 `if __name__ == '__main__':` 内；交互式 stdin/notebook 直接启动 spawn 的限制沿用 Python 自身机制，推荐 CLI 或脚本文件。

```python
from fogsim.training import load_training_config, build_training_plans, evaluate_rule_pair
from fogsim.rules.factory import prepare_rules
from fogsim.rules.specs import RuleSpec

if __name__ == '__main__':
    cfg = load_training_config('configs/training/B01.json')
    plans = build_training_plans(cfg)
    pair = prepare_rules(RuleSpec('routing', 'gp', expression='PT'),
                         RuleSpec('sequencing', 'fcfs'))
    result = evaluate_rule_pair(pair, plans.training[0], 'outputs/my-api-evaluation',
                                trees=cfg.to_dict()['trees'])
    print(result.to_dict()['status'])
```

## 复核本批

实际环境、完整命令和失败尝试说明在 `development/S9-B01/COMMANDS.md`、`outputs/step9/B01/`。运行正式 Java 对照需完整 JDK17（java 和 javac），不支持用 Java21 结果替代。原 Java 647 份源码及所需 JAR 在恢复 java 来源组后位于 references/java 中；JDK 本体不随包分发。实际使用 Temurin 17.0.21+9，二进制、JAR、源码和观察补丁摘要在 lifecycle-final/manifest.json。

离线安装本次精确测试依赖：

```bash
python -m pip install --no-index --find-links development/S9-B01/test-wheels pytest==9.2.0
```

可设置 `FOGSIM_JAVA=/absolute/path/to/jdk17/bin/java`，并将 `JAVA17` 换成该路径：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src:tools python -m pytest tests/training -q --basetemp=outputs/my-B01-cases --junitxml=outputs/my-B01-unit.xml
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src:tools FOGSIM_JAVA="$JAVA17" python -m pytest tests -q --junitxml=outputs/my-B01-regression.xml
PYTHONPATH=src:tools python tools/check_s9_lifecycle.py --java "$JAVA17" --output outputs/my-B01-lifecycle
```

旧完整回归工具会重写 `outputs/parity`、`outputs/v2` 和 `outputs/java_oracle` 的运行记录。因此重跑完整测试应在新的解压副本中进行；若需保留历史目录，先另存新结果，再按 rollback ZIP 恢复原字节。本交付已经这样保存和恢复，详见 history-restoration*.json；旧 outputs/final、development/b08、references 与旧验收原件均经过字节核对。

输入 B08 中缺少旧测试所需的 development/b07；本轮用原 `stage_d_b07.plans.write_plans()` 和 `native.build_native_plan()` 重建缺失夹具，另执行 fixed 20 案例、dynamic 3 案例、native 3 案例。development/b07/evidence 中明确标注为本轮实跑副本，不冒充历史恢复件。它们让旧测试默认路径在独立解压后也可使用。复核 Java 完整场景可用原 `tools/validate_stage_d_b07.py`，指定新 output 目录。

## 读取结果与范围

`evaluation.json` 是训练层快照，`runs/NNNN/result.json` 是原 B08 结果；input.json 是旧读取器可加载的捕获输入或固定物理输入。正式 fitness 只对 FEASIBLE 有值。INFEASIBLE 不能拿 diagnostic_mean_over_successes 选优；INCOMPLETE 必须从头重跑，不用于继续选择。

配置中增大规模只改变预检估算。本包没有单树或双树演化闭环，没有候选、冠军或论文规模结果。S9-B02 的入口是 DEAP 锁定/适配、初始化、单树代循环和通用验证选择；本轮到 B01 为止。
