# S9-B03 当前来源去重分发

当前累计主包fogsim-0.4.0-B03.zip，顶层fogsim-0.4.0/。B03全部新源码/测试/配置、Java适配器/原输出、正式闭环与复跑、故障/中断及诊断证据随包。当前清单S9-B03-FILES.json，校验：

```bash
python tools/build_s9_b03.py verify
```

SOURCE-INDEX.json与restore_sources.py沿用B01原字节；Java/history/rollback三组仍按已提供来源摘要恢复，恢复不会覆盖当前src。

| 来源 | 字节数 | SHA-256 |
| --- | ---: | --- |
| fogsim-0.3.0-b08.zip | 38390156 | 61c4b14bf2305a9bbc2821ebbe85949e27ba45c8472005d8e5bfe7cbba967ecc |
| Fog-Computing-multiDeviceDebug.zip | 55532796 | 17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a |

```bash
python tools/restore_sources.py restore --source-dir /your/current-source-zips
python tools/restore_sources.py verify
```

不重复嵌入旧ZIP/Java/历史块。B01/B02旧清单和工具保持原字节，只描述对应原批次。原B02分发说明另存development/S9-B03/original-docs。缓存、安装目录、pytest current链接和可重建class不入包；B03-EXCLUDED-GENERATED.json逐项列出移出的class等生成文件。必要新源码、补丁、配置及真实原输出不清除。

正式JDK17环境记录在outputs/step9/B03/java-final/build/environment.json，JDK下载信息沿用B02依赖锁。B03当前完整代码以本包为准；B01/B02结果沿用已有验收，新兼容回归均在独立恢复副本执行、另存B03目录。B04再整理最终本地完整交付。
