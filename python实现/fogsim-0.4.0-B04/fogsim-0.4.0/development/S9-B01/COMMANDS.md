# S9-B01 实际命令与环境

日期 2026-11-14（America/Los_Angeles）。工作根目录在本轮 scratch 的 `fogsim-0.4.0/`；包内命令均从工程根目录执行。当前宿主路径只作为 provenance，不是交付依赖。正式 Python、平台、测试轮子 SHA-256、JDK 获取包 SHA-256 在 dependency-lock.json；Java 二进制、编译器、全部原源码、JAR、DAX、补丁及实际命令在 lifecycle-final/manifest.json。

实际使用 Python 3.12.14；测试 pytest 9.2.0，关闭外部 pytest 插件；Temurin JDK17.0.21+9。系统默认 Java21 没有作为正式参考使用。DEAP 未安装。本批无 Python 运行时第三方依赖。

## 阅读与基线

完整读取附件 S9-frozen-1 与 D-frozen-1，检查 B08 `development/b08/*`、`docs/FINAL-ACCEPTANCE.md`、`outputs/final/acceptance.json` 和相关生产源码。原 B08 及原 Java ZIP 先检查目录和摘要；从 B08 独立解压工作副本，未以其他 Python ZIP 替换实现。B08 最终证据优先于旧顶层 README。

## 环境准备

```bash
python -m pip install --target ../.test-deps 'pytest>=8,<10'
curl -L --fail --max-time 180 -o ../.runtime/jdk17.tar.gz https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse
tar -xzf ../.runtime/jdk17.tar.gz -C ../.runtime
python -m pip download --only-binary=:all: --dest development/S9-B01/test-wheels pytest==9.2.0 packaging==26.3 pluggy==1.7.0 iniconfig==2.3.1 pygments==2.21.0
```

实际 JDK 路径 `../.runtime/jdk-17.0.21+9/bin/java`。以下 `JAVA17` 表示其绝对路径，`PYTHONPATH=../.test-deps:src:tools`。网络取得 JDK 的最终版本与 tar 摘要固定在 lock，复核时不以 latest 重定向代替精确来源。

## 原始尝试（全部保留）

首次完整 pytest：`initial-regression.xml/txt`，实际 5797 项；因输入 B08 缺失 development/b07 的 fixture/evidence，以及新发行版本号的旧断言，19 failed、48 errors、5730 passed。不是本批通过证据。

用原 `stage_d_b07.plans.write_plans('development/b07/fixtures')` 与 `native.build_native_plan()` 重建不存在的夹具；只将一个旧版本测试中的发行版本与 capture provenance 断言由 0.3.0 改为 0.4.0，未放宽调度断言。首次 native 检查缺 native-plan，保留在 regression-native-command.txt，补齐原生成器输出后另建 regression-native-retry。未覆盖原 B08 历史证据。

`regression-r1.xml/txt` 的 13 项失败来自该次长回归进行中新增 worker 消息、父进程仍加载旧协议的混合源码执行；此轮标为无效开发尝试，不能作为兼容结论。之后冻结生产源码运行 `regression-final` 全部通过；再补充错误分类时保存刚返回的原结果，并增加对应测试，最终运行 accepted-regression 和 unit-release。所有初轮及重跑日志均保存。

## Java 生命周期与必要旧场景新跑

```bash
PYTHONPATH=src:tools python tools/check_s9_lifecycle.py --java "$JAVA17" --output outputs/step9/B01/lifecycle-final
PYTHONPATH=src:tools python tools/validate_stage_d_b07.py --java "$JAVA17" --output outputs/step9/B01/regression-fixed --phase fixed
PYTHONPATH=src:tools python tools/validate_stage_d_b07.py --java "$JAVA17" --output outputs/step9/B01/regression-dynamic --phase dynamic --existing-build outputs/step9/B01/regression-fixed/build
PYTHONPATH=src:tools python tools/validate_stage_d_b07.py --java "$JAVA17" --output outputs/step9/B01/regression-native-retry --phase native
```

生命周期有自然 B 更新、小 N/W 的 sentinel B 保留，以及 Long.MAX_VALUE 轮换三种案例。Java 单独编译和执行，Python 单独运行 B08，未注入预期结果。编译/运行 stdout/stderr、overlay 与补丁、输入 DAX、实际状态与检查全部保留。算子 J01-J04、J06 未执行。

## 最终 B01 与完整回归

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=../.test-deps:src:tools python -m pytest tests/training -q -p no:cacheprovider --basetemp=outputs/step9/B01/cases-delivery --junitxml=outputs/step9/B01/unit-delivery.xml
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=../.test-deps:src:tools FOGSIM_JAVA="$JAVA17" python -m pytest tests -q -p no:cacheprovider --junitxml=outputs/step9/B01/accepted-regression.xml
PYTHONPATH=src python -m fogsim.training.cli validate --config configs/training/B01.json --output outputs/step9/B01/accepted-preflight
PYTHONPATH=src python -m fogsim.training.cli evaluate --rules configs/training/rules.json --plan outputs/step9/B01/accepted-preflight/plans/train-0000.json --output outputs/step9/B01/accepted-smoke
PYTHONPATH=src python -m fogsim.training.cli evaluate --rules configs/training/rules.json --plan outputs/step9/B01/accepted-preflight/plans/train-0000.json --output outputs/step9/B01/accepted-smoke-repeat
PYTHONPATH=src:tools python tools/accept_s9_b01.py
```

每条结果见对应 `*-command.txt`、JUnit 或工具 manifest。完整回归中旧工具默认写 outputs/parity/v2/java_oracle；已先将本轮结果另存 B01/legacy-rerun* 再恢复原 B08 历史文件，恢复清单与最终 source-retention.json 保存逐项核对。最后在独立解压目录重新检查 ZIP CRC/成员摘要、CLI、冻结计划评估和本批测试，见外部 fogsim-0.4.0-B01-verification.json。

最终身份补强后另执行同一完整 pytest，输出 identity-final-regression.xml/txt；专项输出 unit-identity-final.xml/txt 与 cases-identity-final。正式 CLI 输出 identity-preflight / identity-smoke / identity-smoke-repeat。最终 acceptance 绑定这些文件，先前通过的快照仍保留，但不替代最终源码。
