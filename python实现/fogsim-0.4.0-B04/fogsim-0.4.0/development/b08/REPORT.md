# B08 最终报告

日期：2026-11-07（UTC 工作副本；交付报告沿用客户端 America/Los_Angeles 的批次日期）。

## 变更

- 恢复并校验 B07 四个普通 ZIP：成员总数 40,143，外部清单 SHA-256 与 CRC 全部匹配。
- 添加 `tools/audit_b08.py`，绑定 B07 活跃文件、累计回归、动态/性能门禁和 149 项合同审计。
- 修复累计 pytest 的 `conftest` 模块名冲突；仅改两个测试兼容文件，生产模拟器源码未改。
- 生成当前 `outputs/final` 验收证据、B08 说明和发行包。

## 执行命令

1. `pytest tests/stage_d/b07 -q -ra -p no:cacheprovider`：69 passed。
2. `tools/validate.py`：5797 passed，0 failed/error/skip；14 固定案例与既有 V2 清单通过。
3. `tools/check_step2.py --java ... --output outputs/final/step2`：20 拓扑与两语言分布通过。
4. `tools/check_step3.py --java ... --output outputs/final/step3`：7 个生成案例通过。
5. `tools/run_final_acceptance.py --phase dynamic --output outputs/final/current`：7 个案例通过，正常/预期差异分类保留。
6. `tools/run_final_acceptance.py --phase performance --output outputs/final`：通过。
7. `tools/audit_contracts.py`：149 contracts，unresolved 0。
8. `tools/audit_b08.py`：B07 活跃文件仅两处允许的测试兼容改动，生产源 0 改动，整体通过。

## 分类与限制

正常跨语言通过、预期的 Java 精度/失败尾部差异、合同检查和未执行的大型可选投影保持分列。发行包不宣称任意输入的 Java 等价、论文规模性能、GP 训练或十特征演化；这几项仍在冻结设计范围之外。
