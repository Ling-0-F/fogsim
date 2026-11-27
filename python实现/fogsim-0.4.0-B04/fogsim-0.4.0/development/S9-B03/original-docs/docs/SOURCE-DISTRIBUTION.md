# S9-B02 当前来源去重分发

当前累计包为 fogsim-0.4.0-B02.zip，顶层 fogsim-0.4.0/。B02 新增源码、测试、配置、精确依赖轮子、算子/闭环/复跑/故障/Java证据随包。当前文件清单为 S9-B02-FILES.json，校验使用 `python tools/build_s9_b02.py verify`。

SOURCE-INDEX.json 与 restore_sources.py 保持原字节。Java/history/rollback三组继续从下列已提供来源按摘要恢复，只恢复索引成员，不覆盖当前 src。

| 来源 | 字节数 | SHA-256 |
| --- | ---: | --- |
| fogsim-0.3.0-b08.zip | 38390156 | 61c4b14bf2305a9bbc2821ebbe85949e27ba45c8472005d8e5bfe7cbba967ecc |
| Fog-Computing-multiDeviceDebug.zip | 55532796 | 17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a |

```bash
python tools/restore_sources.py restore --source-dir /your/current-source-zips --dry-run
python tools/restore_sources.py restore --source-dir /your/current-source-zips
python tools/restore_sources.py verify
```

旧 SOURCE-DISTRIBUTION-FILES.json 与 build_source_distribution.py 仅描述原 B01；它们不校验本批修改后源码。旧说明原文在 development/S9-B02/original-docs/。历史证据原字节保留，完整旧回归在独立恢复副本运行，新增结果另存。编译class、缓存、虚拟依赖安装目录可重建，不入包；B02-EXCLUDED-GENERATED.json逐项记录。B02所有新源码、补丁、配置、原始输出、失败和中断记录仍随包。

JDK17不内嵌；实际下载版本及摘要在development/S9-B02/dependency-lock.json，正式环境与编译命令在outputs/step9/B02/java-final/。可使用完整JDK17并重新运行局部对照。当前无双树或论文规模结果；B04再整理最终本地完整交付。
