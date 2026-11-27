# B08 回归、打包与验收

本批在用户确认 B07 交付后开始，以 `B07-r1-20261107` 四分包联合恢复副本为唯一基线。B07 的代码、场景、参考、失败尝试和 69 项场景合同先恢复并重新执行；随后执行旧固定/v1 回归、V01～V04/V06～V08 核对、重放/清理/CLI 合同、逐条合同审计和发行包门禁。

B08 的工作范围是最终工程验收与交付整理。没有改变调度、GP 数值、重放或统计语义。为让累计测试能在同一次 pytest 进程内加载历史 `conftest`，仅在 `tests/gp/b06/conftest.py` 与 `tests/stage_d/b07/conftest.py` 补齐历史测试所需的 `ROOT`、`step` 和 `two_workflows` 兼容导出；这两处被列为允许的测试兼容改动，生产 `src/fogsim` 逐文件保持 B07 字节一致。

## 验收结果

| 门禁 | 结果 |
| --- | --- |
| B07 场景恢复 | 69/69，0 失败，0 跳过 |
| 累计 Python 回归 | 5797/5797，0 失败，0 错误，0 跳过 |
| V02/V04 拓扑与分布 | 20 个拓扑；两语言各 3 个 seed × 100000 样本；通过 |
| V06/V07/V08 生成核对 | 7 个脚本案例；通过 |
| 动态/重放/固定投影 | 7 个 fresh Java 案例；正常与预期差异分列；通过 |
| V20 性能与清理 | retain/release 同结果，释放计数实际非零；通过 |
| 合同审计 | 149/149，未解析 0 |

机器结果见 `outputs/final/acceptance.json`、`outputs/final/source-audit.json` 和 `outputs/final/contracts-audit.json`。最终源码包由 `tools/build_release.py` 生成，并在包内重新核对 CRC、逐文件 SHA-256 和已验收源码快照。

## 复跑

```bash
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server \
PYTHONPATH=src:tools:.deps FOGSIM_JAVA=/usr/lib/jvm/java-17-openjdk-amd64/bin/java \
python tools/validate.py
python tools/audit_b08.py
python tools/assemble_acceptance.py
python tools/build_release.py --output fogsim-0.3.0-b08.zip
```

验收要求 JDK 17；本次环境使用系统 OpenJDK 17 的 `jdk.compiler` 模块，测试依赖由工作副本的 `.deps` 提供。没有把旧历史 JSON 当作新运行通过；历史结果只作为来源保留与字节绑定依据。
