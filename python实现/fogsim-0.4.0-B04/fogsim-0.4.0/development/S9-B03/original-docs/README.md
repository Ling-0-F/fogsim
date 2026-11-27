# fogsim 0.4.0 — S9-B02 单树闭环

累计基线为已验收的 B01-source-dedup；本批新增 DEAP 单树 routing 演化、显式 FCFS sequencing、固定验证选优、规则冻结与独立加载测试。双树仍未实现，不自动进入 B03。

先读 [B02运行说明](docs/RUNNING-S9-B02.md)、[协议](docs/TRAINING-PROTOCOL-B02.md)、[本批报告](development/S9-B02/REPORT.md)。正式状态为 outputs/step9/B02/acceptance.json；独立交付复核另附报告。B01和B08证据保持原字节，不以旧顶层状态文字覆盖正式验收。

```bash
PYTHONPATH=src python -m fogsim.training.cli train --config configs/training/smoke-single.json --output outputs/my-single
```

旧固定/动态/重放及B01固定规则评估保持可用且不需要DEAP；训练依赖使用development/S9-B02的精确锁定及轮子。Java/历史/回滚按SOURCE-INDEX.json从已提供来源恢复，详见[来源说明](docs/SOURCE-DISTRIBUTION.md)。本批当前完整文件校验使用 tools/build_s9_b02.py verify；旧分发工具与清单保留用于原B01，不代表本批源码。原README副本在development/S9-B02/original-docs/README.md。
