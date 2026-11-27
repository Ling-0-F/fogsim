# S9-B02 运行

Python >=3.11；当前锁定离线轮子适用于 CPython3.12/Linux x86_64。实际验收运行时见 development/S9-B02/dependency-lock.json。其他平台需取得同精确版本兼容包并重新记录摘要/受影响门禁。旧固定/动态/重放不需要 DEAP。

```bash
python -m pip install --no-index --find-links development/S9-B02/wheels --require-hashes -r development/S9-B02/requirements-train.lock
PYTHONPATH=src python -m fogsim.training.cli validate --config configs/training/smoke-single.json --output outputs/my-preflight
PYTHONPATH=src python -m fogsim.training.cli train --config configs/training/smoke-single.json --output outputs/my-single
PYTHONPATH=src python -m fogsim.training.cli evaluate --rules outputs/my-single/trial-0001/selected_rule.json --plan outputs/my-single/plans/test.json --output outputs/my-independent-test
```

默认两 evolution seed，每 trial训练96、验证最多8、测试2，总上界212；同配置首跑+复跑上界424。实际候选去重减少验证次数。每运行2 recorded/1 warmup、max_events=2000，资源为1本地设备+1edge。验证和测试各两条不同seed，三组在训练前冻结。两个trial共享计划是预先声明的安排。

S9-B02只交付小规模单树；不自动进行双树或论文规模。变更规模时先validate检查预算和seed溢出，使用新输出目录。源码及依赖改变须重验；历史证据不能被新命令覆盖。完整旧回归在独立恢复副本执行。

```bash
python tools/restore_sources.py restore --source-dir /your/current-source-zips
python tools/restore_sources.py verify
PYTHONPATH=src:tools python tools/check_s9_b02_java.py --java /your/jdk17/bin/java --output outputs/my-java-b02
PYTHONPATH=src:tools PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 FOGSIM_JAVA=/your/jdk17/bin/java python -m pytest tests -q
```

Java来源不被修改。对照独立保存原始源码快照/overlay、适配器、共同输入、实际Java与Python输出、编译运行命令及环境。J01/J02/J03、单树交叉和变异、J06算子接纳数/精英/末代检查在B02；J04双树专项留B03。Java原生RNG序列不作同seed一致承诺。
