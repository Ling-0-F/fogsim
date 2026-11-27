# Java 参考环境与局部对照

本次实际参考环境为 **Eclipse Temurin OpenJDK 17.0.16+8**，Linux x86_64 HotSpot（原 0.2.0a1 的 Windows 验证记录保留于历史文档）。它是本次验收记录的参考环境（允许使用其他 JDK 17 更新版本），不是作者实验环境的证明。

```text
openjdk version "17.0.16" 2025-07-15
OpenJDK Runtime Environment Temurin-17.0.16+8 (build 17.0.16+8)
OpenJDK 64-Bit Server VM Temurin-17.0.16+8 (build 17.0.16+8, mixed mode, sharing)
```

原始完整 properties/version 输出：[java-version.txt](../outputs/java_oracle/java-version.txt)。本次可执行文件为临时参考目录的 `jdk-17.0.16+8/bin/java`（实际绝对路径见版本/构建清单）；未更改系统 PATH。原项目 `.idea/misc.xml` 仅记录 languageLevel=JDK_1_8、project-jdk-name=openjdk-17。

## 本次参考环境的二进制和源码指纹

- [Temurin 官方 release](https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.16%2B8) 的文件 `OpenJDK17U-jdk_x64_linux_hotspot_17.0.16_8.tar.gz`。
- 下载包 SHA-256：`166774efcf0f722f2ee18eba0039de2d685b350ee14d7b69e6f83437dafd2af1`；实际下载字节与 release 的 `.sha256.txt` 相符。
- JDK `lib/src.zip` 中 `java.base/java/util/PriorityQueue.java` 的 SHA-256：`92f97c6625f4cd1994765acbd718e8a6f7c7697e5e65974a1d78d5e37e284ca8`。
- 上述文件与 [OpenJDK 固定 tag jdk-17.0.16+8 的源码](https://github.com/openjdk/jdk17u/blob/jdk-17.0.16%2B8/src/java.base/share/classes/java/util/PriorityQueue.java) 下载字节的 SHA-256 一致。没有以浮动 master 作为对照依据。

## 堆操作审查

已实际读取该 build 的 offer/poll、siftUpComparable/siftDownComparable：

| 核对点 | 本实现 |
| --- | --- |
| 新项与父项比较，>=0 停止上浮 | 相同 |
| poll 使用尾项补根 | 相同 |
| 仅当左孩子对右孩子 >0 时选右 | 相同，平分选左 |
| 补根项对孩子 <=0 时停止下沉 | 相同 |
| 两层堆 | 同一算法，设备按固定顺序排空，逐项 offer 到全局 |
| 稳定平分序号 | 没有加入；日志 sequence 不参与堆 |

## Oracle 的实际执行

`tools/run_java_oracle.py` 从提供的原 Java 文件抽取四种 compareTo、TaskOption.priorTo、Server/MobileDevice 入出队及 getter 方法。抽取方法保持原文；最小类只提供这些方法读取的字段/访问器。生成的 [ComponentOracle.java](../outputs/java_oracle/ComponentOracle.java) 和方法 SHA 位于证据目录。

在真实 JDK PriorityQueue 上执行：

- 原事件比较器全部有序事件对，包括异常自比较/相同编号分支。
- 多组含平分与非正常比较器的 offer/poll 混合操作。
- 三台合成设备暂存堆→全局堆的逐项归并和每次弹出。
- Double.compare 的有符号零、NaN、无穷及普通值。
- priorTo 的分数、release、owner、workflow 平分组合。
- 原本地/服务器缓存序列及 getter，按 binary64 位模式比较。

实际 **4,764 条输入操作，3,797 条输出，Java/Python 全部逐行一致**。证据：[report.json](../outputs/java_oracle/report.json)、[operations.txt](../outputs/java_oracle/operations.txt)、[Java 输出](../outputs/java_oracle/java-output.txt)、[Python 输出](../outputs/java_oracle/python-output.txt)。测试 fixture 生成使用固定本地 RNG，仅用于构造组件操作样例；模拟器本身不采样。

这支持指定 build 和所列组件样例的对照。完整固定实例另由 Java 适配器验证：14 个正式配置及 96 组固定扫查通过，详见 `VALIDATION.md`。浮点精度归零的实际反例表明不能声称任意有限输入等价；详见 `ISSUES-AND-FIXES.md`。

0.2.1 的两个 Java 工具共用 `tools/java_support.py::reference_jdk`，只要求 `java.specification.version=17`。实际 vendor/build/二进制哈希保存于构建清单，PriorityQueue 源码可取得时记录 SHA，不因不同 build/vendor/源码而拒绝。0.2.0 强制锁定具体 build 的做法属于额外收紧，已撤回。真实堆 oracle 和完整轨迹对照仍必须通过。
