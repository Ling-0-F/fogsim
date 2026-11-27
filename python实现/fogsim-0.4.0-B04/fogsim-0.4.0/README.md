# fogsim 0.4.0 — S9-B04 最终交付

在已验收B03累计基线上完成最终兼容与交付。支持固定规则评估、单树routing＋FCFS sequencing及双树GP训练、候选归档、固定验证选优、冻结规则独立加载与最终测试。默认大规模入口只预检，不启动论文规模训练。

阅读 [运行手册](docs/RUNNING-0.4.0.md)、[最终验收矩阵](docs/ACCEPTANCE-S9-B04.md)、[报告](development/S9-B04/REPORT.md) 和 [分发说明](docs/SOURCE-DISTRIBUTION.md)。权威机器结论为outputs/step9/B04/acceptance.json。B01—B03和B08的历史结论及原始证据保留，最终新旧联合检查另存B04目录。

```bash
PYTHONPATH=src python tools/run_s9_training.py --config configs/training/large-dual-template.json --output outputs/my-preflight
```

精确训练锁/轮子在development/S9-B02；当前安装wheel在development/S9-B04/dist。所有分包解压到同一新目录，不覆盖旧工程。主包为fogsim-0.4.0-B04.zip，统一顶层fogsim-0.4.0/；evidence、references、rollback分包与索引一并交付。JDK17不随包，获取信息保留。
