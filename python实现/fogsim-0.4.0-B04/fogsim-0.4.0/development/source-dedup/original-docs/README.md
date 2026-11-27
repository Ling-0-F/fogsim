# fogsim 0.4.0 — S9-B01 评估层

以 `fogsim-0.3.0-b08.zip` 为唯一实现基线，累计保留固定、动态、重放、GP 固定规则、身份和数值合同。本批新增严格训练配置、计划冻结、防泄漏检查、真实 B08 固定规则评估、D03 适应度和失败分类、fresh/RNG 隔离、spawn 墙钟监督及独立证据协议。

先读 [运行说明](docs/RUNNING-S9-B01.md)、[批次报告](development/S9-B01/REPORT.md) 和 [协议细化](docs/TRAINING-PROTOCOL-B01.md)。正式设计在 [S9-frozen-1](references/design/fogsim-0.4.0-design.md)；阶段 D 冻结合同在同目录。实际门禁状态以 `outputs/step9/B01/acceptance.json` 为准。

```bash
PYTHONPATH=src python -m fogsim.training.cli validate --config configs/training/B01.json --output outputs/my-preflight
PYTHONPATH=src python -m fogsim.training.cli evaluate --rules configs/training/rules.json --plan outputs/my-preflight/plans/train-0000.json --output outputs/my-evaluation
```

运行依赖仅 Python 3.11+ 标准库；本批无须 DEAP。安装后也可用 `fogsim-train`，旧命令 `fogsim` 保留。API、完整回归和 JDK17 实跑说明见运行手册。

本包只实现 S9-B01，没有单树/双树演化闭环，没有执行 848 次闭环预算，也不启动论文规模训练。后续批次仍须分别验收。

原 B08 ZIP 原样保存在 `rollback/fogsim-0.3.0-b08.zip`；旧 README 原文保存在 `references/design/B08-README.md`，旧验收与参考保持原字节。缺失旧 B07 夹具的重建及本轮新证据均另行标注。回滚可将原 ZIP 解压到独立目录。
