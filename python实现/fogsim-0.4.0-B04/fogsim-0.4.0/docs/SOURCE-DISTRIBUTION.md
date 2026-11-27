# S9-B04 最终完整本地交付

B04以来源中已验收B03累计包为唯一当前代码基线。B01—B03结果沿用，B04源码修改、专项、新旧联合回归和协议/合同审计均另存；旧原始证据不重写。

本次不再依赖沙箱绝对路径或用户另找旧来源。四个分包以fogsim-0.4.0/为顶层，解压到同一新目录，成员路径互不重叠：

| 分包 | 内容 | 使用要求 |
| --- | --- | --- |
| fogsim-0.4.0-B04.zip | 累计源码/测试/工具、必要场景/DAX、配置、schema、设计、手册与验收摘要 | 基本使用必需 |
| fogsim-0.4.0-B04-evidence.zip | 原B01/B02/B03及B04原结果、输入、故障、Java原输出和历史证据 | 完整复核必需 |
| fogsim-0.4.0-B04-references.zip | 已恢复Java/history/rollback来源、离线训练与测试依赖、当前及历史wheel | 离线安装/Java复核必需 |
| fogsim-0.4.0-B04-rollback.zip | 原B01去重包、B02/B03累计包与其已提供交付附件 | 原批次回滚必需 |

外部分包索引列出文件名、用途、体积、SHA-256、合并顺序、目标目录和必需性。SOURCE-INDEX.json及restore_sources.py保持原字节；索引3373成员已恢复并随分包提供，基本使用不需要再恢复。references中rollback/fogsim-0.3.0-b08.zip亦为原字节。JDK17按既有约定不随包，仅为独立Java复核的外部环境要求；版本、URL、摘要在依赖锁。

主包保存所有分包成员的S9-B04-FILES.json：python tools/build_s9_b04.py verify。也可用--part main检查基本包，--part references/evidence/rollback检查指定分包。全量verify要求四包全部解压。旧B01/B02/B03清单只描述对应旧批次，不用其旧清单校验B04变化。

可重建缓存、class、虚拟环境、安装临时目录和egg-info不交付；删除项清单B04-EXCLUDED-GENERATED.json记录本批排除内容。历史压缩包内部不重打包、不改字节，必要原始失败记录不删。新文件/变更清单S9-B04-NEW-FILES.json与CHANGES-S9-B04.patch保留。
