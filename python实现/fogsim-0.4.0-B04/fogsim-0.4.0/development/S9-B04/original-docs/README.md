# fogsim 0.4.0 — S9-B03 双树闭环

累计基线为已验收B02。本批新增双树0=sequencing/1=routing，特殊交叉/整树交换/四分支回退和双树变异；复用既有候选归档、验证、规则冻结与测试。单树routing+FCFS及旧固定/动态/重放保持可用。

先读[运行说明](docs/RUNNING-S9-B03.md)、[协议](docs/TRAINING-PROTOCOL-B03.md)、[本批报告](development/S9-B03/REPORT.md)、[执行范围和预算](development/S9-B03/PLAN.md)。本批正式结果在outputs/step9/B03/acceptance.json；旧B01/B02结论和证据原字节保留，不重新验收原包。

```bash
PYTHONPATH=src python -m fogsim.training.cli train --config configs/training/smoke-dual.json --output outputs/my-dual
```

依赖沿用development/S9-B02的精确锁及轮子。当前安装wheel在development/S9-B03/dist。每种模式完整配置两个trial上界212，B03双树首跑+复跑上界424；组件/故障另计。不启动论文规模训练，不自动进入B04。

本包顶层fogsim-0.4.0/，当前清单S9-B03-FILES.json，校验用python tools/build_s9_b03.py verify。Java/history/rollback继续按SOURCE-INDEX.json恢复。原B02包保留在来源，回滚时独立解压它，不覆盖历史记录。完整分发说明见[来源说明](docs/SOURCE-DISTRIBUTION.md)。
