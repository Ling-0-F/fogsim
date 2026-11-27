# B01 来源去重开发分发说明

当前分发标识：`B01-source-dedup`。仍然只有 S9-B01 评估层能力，未纳入任何 S9-B02 实现。

本分发依据用户已确认的“约 39 MiB：来源去重＋临时清理”方案制作。它是累计源码工程，不是增量补丁；基本 Python 使用独立可用，完整历史/Java 复核需要下列指定来源。为与原完整验收包区分，文件名使用 `fogsim-0.4.0-B01-source-dedup.zip`，ZIP 顶层仍为 `fogsim-0.4.0/`。此为中间批次的包装调整，不修改 S9-frozen-1 算法合同、门禁或 B01 验收结果。到 B04 再核对本地完整交付所需材料。

## 保留、索引与清理

| 内容 | 当前处理 | 恢复/使用条件 |
| --- | --- | --- |
| 全部当前源码、原有测试/工具、配置、schema、DAX、必要数据、依赖轮子 | 完整保留 | 可直接开始代码阅读及基本评估 |
| 0.4.0 定稿、阶段 D 合同、B08 development/b08 记录 | 保留原字节 | 文档编制时的“未实施”不覆盖已保存验收 |
| B01 全部 outputs/step9/B01 过程与最终证据、development/b07 夹具和新实跑证据 | 完整保留 | 没有采用进一步移出早期过程记录的约 21 MiB 方案 |
| B08 历史 outputs（2,419 文件） | 从原 B08 ZIP 按成员索引恢复 | 旧测试、完整回归及历史审计前恢复 history |
| 原 Java 参考（952 文件，含源码/JAR） | 从原 Java ZIP 按成员索引恢复 | Java/ECJ 阅读、编译及对照前恢复 java |
| 内嵌 B08 ZIP＋1 个旧审计绑定成员（共 2 文件） | 原包不重复携带 | 字节保留审计/旧打包工具/回滚时恢复 rollback |
| pytest-of-agent/、根级 fogsim-run-*（2,801 文件） | 清除混入的测试临时产物 | 无须恢复 |
| 非 step9 输出下 966 个 .class | 清除可重建或废弃产物 | Java 工具重新编译 |

旧审计绑定的成员虽然是历史编辑器临时文件，但 B08 审计要求逐字节保留；因此将其从 B08 ZIP 列入 rollback 组按需恢复，不随主包复制。其精确成员路径见 SOURCE-INDEX.json。

机器可读信息：`SOURCE-INDEX.json` 为来源精确摘要与逐文件成员/目标映射；`development/source-dedup/removed-generated-files.json` 为清理记录。原完整 B01 ZIP 及所有来源附件没有修改。原 `S9-B01-FILES.json` 与旧验收报告保留原字节，描述原完整包；不能用它们代替本分发的新清单 `SOURCE-DISTRIBUTION-FILES.json`。

## 必需来源与路径

来源原件放到任意本地目录，例如 `../sources/`。不依赖本轮临时工作区路径、聊天链接或固定上传前缀。下列两个来源是完整恢复的必需材料，当前项目来源中均已提供。

| 来源文件 | 字节数 | SHA-256 | 适用组 |
| --- | ---: | --- | --- |
| fogsim-0.3.0-b08.zip | 38390156 | 61c4b14bf2305a9bbc2821ebbe85949e27ba45c8472005d8e5bfe7cbba967ecc | history、rollback |
| Fog-Computing-multiDeviceDebug.zip | 55532796 | 17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a | java |

恢复工具只读取指定目录顶层的 ZIP，按字节数和 SHA-256 匹配，允许文件带上传前缀或改名。ZIP 成员和工程目标路径逐项绑定；只恢复索引中的文件，不解压来源中其余无关文件。目标均相对 `fogsim-0.4.0/` 根目录。已有相同文件跳过；摘要不符、路径越界、符号链接或已有目标冲突明确失败，不覆盖修改文件。写入前先验证全部选中来源与成员；中途磁盘/操作系统故障不提供事务回滚，修复后可重复执行。

从工程根目录执行（仅 Python 标准库）：

```bash
# 校验精简包随附文件，不要求恢复来源
python tools/build_source_distribution.py verify

# 未恢复时 verify 返回 1 并列出缺失数量，这是预期状态
python tools/restore_sources.py verify

# 先完整只读预检，再恢复；目录必须换成你持有两个来源 ZIP 的位置
python tools/restore_sources.py restore --source-dir ../sources --dry-run
python tools/restore_sources.py restore --source-dir ../sources
python tools/restore_sources.py verify
```

多目录可重复传 `--source-dir`。只需 Java 可加 `--group java`；历史输出用 `--group history`，回滚用 `--group rollback`。默认三组全部处理。恢复后相同命令可重复执行，新增恢复数应为 0。退出码：完成/成功预检 0，verify 缺文件 1，来源/冲突/格式等错误 2。工具无网络访问。

## 使用与复核顺序

1. 在新目录独立解压本分发，不覆盖原完整 B01 或其他批次目录。
2. 校验新分发清单。阅读定稿、阶段 D 合同、B01 批次报告与协议细化。
3. 基本评估、旧固定 API、B01 训练层专项和恢复工具测试可以直接运行，无须 DEAP。
4. 开始 B02 前恢复三组，复核 Java 源码、旧默认测试路径及 B08 字节审计；不要改写历史参考来消除差异。
5. Java 对照需要完整 JDK17，包含 java 和 javac。JDK 不随包。精确已实跑版本与下载摘要在 development/S9-B01/dependency-lock.json；系统 Java21 不替代正式 JDK17 对照。
6. 完整 pytest 会写旧 outputs，必须在另一个已恢复的解压副本中执行，将新日志写入新目录。原分发/历史记录保持只读。重新打包去重版应从未恢复、未被回归修改的干净工程构建。

```bash
# 无需恢复的基本检查
PYTHONPATH=src python -m fogsim --version
PYTHONPATH=src python -m fogsim.training.cli validate --config configs/training/B01.json --output outputs/my-preflight
PYTHONPATH=src python -m fogsim.training.cli evaluate --rules configs/training/rules.json --plan outputs/my-preflight/plans/train-0000.json --output outputs/my-evaluation

# 精确测试依赖可离线安装，普通运行无第三方依赖
python -m pip install --no-index --find-links development/S9-B01/test-wheels pytest==9.2.0
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src:tools python -m pytest tests/packaging tests/training -q

# 完整回归：先恢复全部来源，在独立副本中指定真正的 JDK17
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src:tools FOGSIM_JAVA=/path/to/jdk17/bin/java python -m pytest tests -q --junitxml=/path/to/new-evidence/regression.xml
PYTHONPATH=src:tools python tools/check_s9_lifecycle.py --java /path/to/jdk17/bin/java --output /path/to/new-evidence/lifecycle
```

B01 的 wheel 完整保留，生产源码未改，因此无需重建 wheel。新增恢复和分发工具从工程文件使用，不包含于原 B01 wheel。原 build_s9_b01.py 针对原完整分发，仍需还原其依赖且不能用来生成此去重版；此分发的构建入口为 tools/build_source_distribution.py。原验收脚本不应在只读历史目录重新运行并覆盖原结论；只调用其 audit() 可进行 B08 字节检查。

新对话复制 `S9-B02-new-conversation-prompt.txt`。新会话以这个已交付 B01 为累计代码基线；历史聊天中提到的 B02 开发副本不在本包，不作为已完成实现或验收证据。
