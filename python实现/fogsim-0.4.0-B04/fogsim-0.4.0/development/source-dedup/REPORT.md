# B01 来源去重分发复核报告

本次仅调整已验收 B01 的包装；没有实施或交付 B02。原完整 B01 ZIP SHA-256 为 `9bdad190123d44642eb4847bbf4d3ee32d555bdb51ac427b0c7429e25ef21bd1`，保留原件不改。本分发文件名加 `source-dedup`，供用户上传到来源后在新对话继续 B02。

## 已执行与结果

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| 未恢复来源时完整性、旧固定 API/CLI、validate/evaluate | 通过；DEAP 确认未安装 | verification/commands.json 与对应 stdout |
| 两次同计划真实固定规则评估 | 两次各 2 条成功；评估快照、原结果及输入逐字节相同 | verification/verification.json |
| 未恢复来源时训练层和恢复专项 | 73 项通过，0 失败/错误/跳过；其中原 B01 61 项、新恢复工具 12 项 | verification/components.xml |
| 来源只读预检、完整恢复、verify 和重复执行 | 3,373 文件全部校验；重复执行新增 0 | verification/restore*.txt、restored-status.stdout.txt |
| B08 原审计 | 3,732 文件通过；只保留原登记的 README/版本等允许差异 | verification/b08-byte-audit.stdout.txt |
| JDK17 独立 Java/Python 生命周期 | 68 项通过 | verification/lifecycle/ |
| 恢复后的新旧完整回归 | 5,870 项通过，0 失败/错误/跳过；105.59 s | verification/regression.xml、full-regression.stdout.txt |
| 保留文件审计 | 原 11,615 文件中 11,613 原字节保留；2 个文档更新分发说明 | verification/verification.json |
| 原源码/测试/工具和 B01 原始证据 | 原 232 个 src/tests/tools 文件全部相同；outputs/step9/B01 的 9,091 文件全部相同 | verification/verification.json |

73 是独立专项轮次，不与 5,870 相加。历史 5,858 只作为原 B01 记录，新完整回归增加本次 12 项恢复测试。完整回归和所有写旧路径的工具在独立解压副本执行，未改写干净分发工程与来源。

本次来源索引共 3,373 文件：history 2,419、java 952、rollback 2（B08 ZIP 和审计绑定成员）。清除 3,767 个混入临时/编译产物：测试临时文件 2,801，Java class 966。没有移出 B01 早期过程记录，没有改写历史验收。完整逐项索引/清理记录与原保留文件摘要均在本目录或根 SOURCE-INDEX.json。

## 初始发现与处理

初次独立恢复审计发现，B08 将一个 Java 编辑器临时文件也纳入 3,732 文件审计。为保持旧审计原样执行，将它列入 rollback 来源组，从 B08 原成员恢复，不在主包重复携带。初始失败报告在 initial-check/，最终审计通过，未放宽门禁。

运行环境为 Python 3.12.14、pytest 9.2.0（全部测试轮子与原包相同）、Temurin JDK17.0.21+9。实际命令、耗时和环境摘要在 verification/。JDK 下载包 SHA-256 与原锁文件的 `8b9b611d917e3dfd8419d3566b5949226f69b052fed7e109c1368add1dfe8711` 一致。JDK 本体、这次新生成的 class、测试临时目录没有加入分发。

verification-driver-observed.py 保存实际运行驱动源码，仅作取证；其中 BASE、candidate-3 及观测绝对路径属于本轮执行布局。用户复核请使用 docs/SOURCE-DISTRIBUTION.md 的相对工程路径命令。verification/verification.json 绑定受检候选 ZIP；最终交付 ZIP 在加入这些复核记录及打包工具路径/时间戳细化后另经独立解压，外部交付 verification.json 绑定最终 ZIP，二者分开记录。

## 范围与下一步

本次没有缺失必需来源，没有未解决的分发阻塞。主包可直接进行基本 Python 评估；B02 开发和完整 Java/历史复核前按说明恢复两个已有来源。原 B01 的演化 trial 数仍为 0，单树/双树闭环与 848 次预算未在本次执行。

原始 B01 验收、定稿和阶段 D 合同保留；本次没有把新包装清单替代算法验收。S9-B02 新对话 prompt 同时在根目录和独立 txt 文件提供。B04 最终本地自运行交付仍待后续批次。
