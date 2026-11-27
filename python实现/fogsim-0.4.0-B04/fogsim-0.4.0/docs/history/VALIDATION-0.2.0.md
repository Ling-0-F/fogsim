# 0.2 固定实例完整验收记录

日期：2026-10-29（America/Los_Angeles）。版本：0.2.0。范围为设计 11 的 V2-01～V2-05，以及原有 0.1/0.2.0a1 回归。原第一阶段记录另存于 `docs/history/VALIDATION-0.2.0a1.md`，原始交付证据保留在 `outputs/history-0.2.0a1/`。

## 结论与适用范围

指定参考环境下，14 个正式固定配置和 96 组确定性生成的固定输入通过逐事件、逐决策、状态和结果对照，共 **3,469 条事件、2,021 次决策／每种语言**。原有 4,764 条局部操作、3,797 条输出的组件 oracle 继续逐行一致。最终测试 **278 项通过，0 失败、0 错误、0 跳过**；实际执行和计数以 `outputs/pytest-results.xml`、`outputs/validation-manifest.json` 为准。

**存在明确的数值边界，不能宣称任意有限输入都与 Java 等价。** 正的 PT 可能在 binary64 加法中被舍掉，使 `(start+PT)+DT == start`。实测这种输入能使原 Java 同一资源上的两个正长度执行重叠；旧 Python 则保留预约保护并串行执行，结果不同。0.2.0 对该输入明确返回 FAILED、makespan=null，保留 Java 原件和失败对照报告。详见 `docs/ISSUES-AND-FIXES.md`。此负例不计入上面的 110 个正常对照通过案例。

V2 验收完成的口径为：有可重复证据的固定输入验收、已发现错误的修正及回归、已知不等价边界显式化；不将边界反例改写成“与 Java 一致”。

## 实际环境

- Linux x86_64，CPython 3.12.14，pytest 9.2.0。
- Eclipse Temurin OpenJDK **17.0.16+8**，HotSpot；与先前 Windows 验证使用相同 vendor/build，本轮使用 Linux 二进制。
- 下载包 `OpenJDK17U-jdk_x64_linux_hotspot_17.0.16_8.tar.gz`，实际 SHA-256 与官方随附校验文件一致：`166774efcf0f722f2ee18eba0039de2d685b350ee14d7b69e6f83437dafd2af1`。
- `PriorityQueue.java` SHA-256：`92f97c6625f4cd1994765acbd718e8a6f7c7697e5e65974a1d78d5e37e284ca8`，与原锁定值相同。
- `tools/java_support.py` 现在同时检查 vendor、完整 build 和源码哈希；只检查“主版本为 17”不足以满足锁定要求。Java 适配器与组件 oracle 共用这项检查。

构建清单记录实际 Java/javac 路径、二进制哈希、版本输出、编译命令和全部输入指纹。原 647 份 Java 源码及 12 个依赖 jar 与用户上传 ZIP 逐文件字节一致，见 `outputs/source-integrity-v2.json`。原 Java 编译 44 条旧 API 等警告、0 错误；没有为消除警告修改原方法。

## 正式验收映射

| 编号 | 实例与检查 | 实际证据与结果 |
| --- | --- | --- |
| V2-01 | A→B/C→D 分叉汇合；两整轮路由；空 ready 不代表完成；D 只派发一次 | `v2_diamond`；A=[0,2]、B=[2,6]、C=[6,7]、D=[8,11]；makespan=11；通过 |
| V2-02 | 工作流竞争 E0；排队顺序与发布时间顺序相反；缓存含已发生 UT | `v2_contention`；W2 先入队，但 W1 按 release 先执行；[0,12]、[12,15]、[15,17]；通过 |
| V2-03 | 三种资源不同 avail 和队列；候选平分保留输入顺序；读取原始 available_time | `v2_candidates`；路由依次 M0、M0、E0、C0、M0、M0、M0；makespan=14；通过 |
| V2-04 | JA/TV/新 PS/旧 PF 同刻交错；队列安排未来 PS；到达前归并；多项完全平分 | `v2_collision_m0/e0`、`v2_equal_heap`、`v2_candidates`；保留真实两层堆顺序；通过 |
| V2-05 | 同输入/加载模型/候选顺序；每条事件前后；内部 DECISION/EMIT；每次评分、选择、轮次；队列/缓存/预约；任务/工作流时间和指标 | 14 个正式配置、96 组固定扫查输入；全部通过；精度反例另列为明确失败边界 |

V2-03 的特征检查涵盖当前固定规则直接读取的 MRT、release 以及队列数/两个缓存状态；没有宣称已完成后续十个 GP 特征和表达式模块。

## 正式配置实测表

计数为每种语言的实际事件数和决策数，Java 与 Python 均相同。

| 配置 | 事件 | 决策 | makespan |
| --- | ---: | ---: | ---: |
| single_local | 4 | 1 | 3 |
| single_local_release5 | 4 | 1 | 3；最终时钟 8 |
| chain_remote | 7 | 3 | 13 |
| chain_fcfs | 7 | 3 | 17 |
| v2_diamond | 13 | 8 | 11 |
| v2_contention | 12 | 5 | 17 |
| v2_candidates | 27 | 10 | 14 |
| v2_collision_m0 | 20 | 8 | 11 |
| v2_collision_e0 | 20 | 8 | 11 |
| v2_equal_heap | 39 | 29 | 12 |
| v2_float_local | 16 | 7 | 1.6 |
| v2_float_remote | 16 | 7 | 2.2 |
| v2_shared_server | 15 | 8 | 8 |
| v2_order | 12 | 4 | 4 |
| 合计 | 212 | 102 | — |

96 组固定扫查另有 3,257 条事件、1,919 次决策。生成器使用 Python `random.Random(20261029 + index)`，覆盖 1/2 设备、禁用本地执行、不同资源输入顺序、负及乱序工作流 ID、2～5 个工作流、1～5 个任务、DAG/无边、同刻到达、整数/小数时长、FCFS/固定 E0。生成后的 JSON 同时提供给两种运行时，不是 Java 随机实例分布或相同 seed 复现。全部输入、原始轨迹、规范化副本、比较报告、进程命令和 SHA 都保存在 `outputs/v2/sweep/`。

## pending_start 与 canAddToQueue

1. **方法边界确有差异。** 实际原方法只查看全局堆首项。`outputs/v2/reservation-probe/result.json` 的四项隔离实验显示：空状态、一条匹配 PS 在堆首时一致；PS 仅在设备暂存堆、匹配 PS 藏在其他资源堆首后面时不同。它们是手工注入状态，不能据此认定正常运行必然错误。
2. **正常完整运行未观察到判断差异。** 110 个正常案例记录到 395 次真正执行的 `canAddToQueue` 调用，原返回值与观察到的待开始状态一致。资源忙的 Visit 由 Java `||` 短路，不进入该方法。每个事件边界仍完整对照预约与原 Java 待触发 Start 列表，多个 Start 不会被归一化隐藏。
3. **正常路径的解释。** 每次事件前排空暂存堆；同刻 PS 优先于 TV。若已有未来 PS，它来自 Finish 的 `max(available,time)`，此时资源 available>time，Visit 已走 busy 分支。在实际占用区间严格为正时，一条旧 Finish 可以与一条新 Start 交错，但不会积累多条同资源同刻 Finish。此为源码路径推理与实测支持，不是任意输入的形式化证明。
4. **可达反例已找到。** 数值精度使执行区间归零后，上述“严格为正”条件失效；多条旧 Finish 在同刻触发。原 Finish 无预约检查、也不调用 canAddToQueue，因而反复从等待队列安排未来 Start。Python 的 Finish 预约保护与 Java 分叉。详细复现见问题报告。

## 回归、失败与交付检查

- 原 145 项回归重新执行通过，基线 XML：`outputs/development/pytest-original-145.xml`。
- 10 个新增正式配置逐一检查 Python 完整轨迹重跑一致、关闭日志不影响事实；Java 新 JVM 重跑完整 raw 相同，关闭观察日志不影响结果。
- 每任务恰好一个 Visit/Start/Finish；每资源正长度占用区间无重叠；所有工作流完成并只登记一次。
- 额外验证共享 E0 时事件 owner 与 staging_device 不同的三次跨设备安排；这不等于完成后续所有多设备模型扩展。
- 数值反例在接受 Execution 前失败，无幽灵计划、实际 start 或 finish；PT 极小但总占用含 DT 仍可表示为正时，保留原加法顺序和结果。
- `tools/validate.py`、`tools/build_release.py` 要求 Java 对照及 V2 gate 通过且无 skip，防止缺 JDK 时凭 Python 测试结束码误发“已验收”包。
- 包内源码通过语法检查；从最终 ZIP 独立解压后重新编译原 Java 类、重跑正式配置并核对源码导入位置。交付清单见 `RELEASE-FILES.json`，独立运行证据见 `outputs/package-smoke-v2.json`。

本轮首轮新增完整测试为 276 通过、1 失败。失败来自诊断辅助函数将空区间 [t,t) 误计为重叠，真实重叠仍被正确发现；已修正并增加独立回归测试。初次 XML 保留于 `outputs/development/pytest-v2-first.xml`。最终实际运行结果见顶部文件，不把开发中失败记录删除。

## 复跑方式

在项目根目录建立 Python 虚拟环境并安装 `.[test]`，将 `FOGSIM_JAVA` 设为 **Temurin 17.0.16+8** 的 java 可执行文件，然后执行：

```text
python tools/validate.py
```

只复跑 V2 原始对照、96 组固定扫查和边界实验：

```text
python tools/run_v2_acceptance.py --java /path/to/jdk-17.0.16+8/bin/java
```

原始数值反例单独对照会返回退出码 1，这是保留的已知不等价结果，不是正常对照通过：

```text
python tools/run_fixed_parity.py --config configs/v2_precision_collapse.json --output outputs/manual-precision
```

DAX 解析、原 Java RNG/动态输入分布、warm-up/训练窗口、GP 表达式与演化、论文规模统计尚未执行，属于后续计划。
