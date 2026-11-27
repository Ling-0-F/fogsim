# S9-B03 运行

依赖、Python版本及离线训练锁沿用B02；不升级DEAP或传递依赖。锁与轮子在development/S9-B02。B03环境/当前wheel/实际检查另见development/S9-B03与outputs/step9/B03。旧功能与冻结规则独立加载不需要DEAP。

```bash
python -m pip install --no-index --find-links development/S9-B02/wheels --require-hashes -r development/S9-B02/requirements-train.lock
PYTHONPATH=src python -m fogsim.training.cli validate --config configs/training/smoke-dual.json --output outputs/my-dual-preflight
PYTHONPATH=src python -m fogsim.training.cli train --config configs/training/smoke-dual.json --output outputs/my-dual
PYTHONPATH=src python -m fogsim.training.cli evaluate --rules outputs/my-dual/trial-0001/selected_rule.json --plan outputs/my-dual/plans/test.json --output outputs/my-dual-test
```

单树仍使用configs/training/smoke-single.json；同一train API支持两种模式。默认两个trial共享预先冻结的模拟计划，单次完整双树配置上界212，首跑+复跑上界424。确切场景及早期诊断差异见development/S9-B03/PLAN.md；常规不设置墙钟预算，故障用显式受控限制。

```bash
PYTHONPATH=src:tools python tools/check_s9_b03_java.py --java /your/jdk17/bin/java --output outputs/my-dual-java
PYTHONPATH=src:tools python tools/compare_s9_b02.py outputs/my-dual outputs/my-dual-repeat --output outputs/my-reproducibility.json
```

Java/历史/回滚继续按SOURCE-INDEX.json从当前已提供两来源恢复。完整旧回归务必用独立恢复副本并另存新结果。B03当前文件清单由build_s9_b03.py校验；旧B01/B02工具与清单保持原字节，只描述原批次。

本批止于双树小规模闭环；不自动开始B04最终联合交付或论文规模训练，无任意断点续训。
