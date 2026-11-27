# fogsim 0.4.0 — S9-B01 评估层

以 `fogsim-0.3.0-b08.zip` 为唯一实现基线，累计保留固定、动态、重放、GP 固定规则、身份和数值合同。本批新增严格训练配置、计划冻结、防泄漏检查、真实 B08 固定规则评估、D03 适应度和失败分类、fresh/RNG 隔离、spawn 墙钟监督及独立证据协议。

**当前为 B01 来源去重开发分发版。** 当前源码、测试、配置和 B01 自身证据完整随包；来源已有的 Java 参考、历史输出和原 B08 回滚 ZIP 按 `SOURCE-INDEX.json` 恢复。开始 B02 前请先读 [分发与恢复说明](docs/SOURCE-DISTRIBUTION.md)，并完成所需来源恢复。它仍然只有 B01 能力。

先读 [运行说明](docs/RUNNING-S9-B01.md)、[批次报告](development/S9-B01/REPORT.md) 和 [协议细化](docs/TRAINING-PROTOCOL-B01.md)。正式设计在 [S9-frozen-1](references/design/fogsim-0.4.0-design.md)；阶段 D 冻结合同在同目录。实际门禁状态以 `outputs/step9/B01/acceptance.json` 为准。

```bash
PYTHONPATH=src python -m fogsim.training.cli validate --config configs/training/B01.json --output outputs/my-preflight
PYTHONPATH=src python -m fogsim.training.cli evaluate --rules configs/training/rules.json --plan outputs/my-preflight/plans/train-0000.json --output outputs/my-evaluation
```

运行依赖仅 Python 3.11+ 标准库；本批无须 DEAP。安装后也可用 `fogsim-train`，旧命令 `fogsim` 保留。API、完整回归和 JDK17 实跑说明见运行手册。

本包只实现 S9-B01，没有单树/双树演化闭环，没有执行 848 次闭环预算，也不启动论文规模训练。后续批次仍须分别验收。

原 B08 ZIP 由来源 `fogsim-0.3.0-b08.zip` 提供，摘要绑定在 `SOURCE-INDEX.json`；需要包内回滚路径时用恢复工具还原至 `rollback/`。旧 README 原文保存在 `references/design/B08-README.md`。已索引的旧验收与参考恢复后保持原字节；B01 新增验收与缺失 B07 夹具重建证据继续随本包保留。原完整 B01 包未改写，其旧清单仍作为历史记录，新分发清单为 `SOURCE-DISTRIBUTION-FILES.json`。
