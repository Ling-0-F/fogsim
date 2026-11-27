# 0.2 第一阶段实际验收记录

日期：2026-10-22。实现版本：**0.2.0a1**。本次完成Java固定实例入口及已有单任务/链式配置的逐事件、逐决策对照；未声明完整0.2验收完成。

## 最终实际结果

**145项测试通过，0失败、0错误、0跳过**，实际耗时见pytest原始报告。运行环境为Windows x64、CPython3.12.12、pytest9.1.1、Eclipse Temurin OpenJDK17.0.16+8。

实际执行：

```powershell
.\.venv\Scripts\python.exe tools/validate.py
```

证据：[测试控制台](../outputs/pytest-console.txt)、[JUnit XML](../outputs/pytest-results.xml)、[源码/输入/配置清单](../outputs/validation-manifest.json)、[固定对照总报告](../outputs/parity/summary.json)。清单中的snapshot_sha256标识本次真实测试的源码快照。

| 配置 | Java/Python事件 | Java/Python决策 | Java/Python makespan | 首个调度差异 |
| --- | --- | --- | --- | --- |
| single_local | 4/4 | 1/1 | 3/3 | null，未发现 |
| single_local_release5 | 4/4 | 1/1 | 3/3；最终时钟8/8 | null，未发现 |
| chain_remote | 7/7 | 3/3 | 13/13 | null，未发现 |
| chain_fcfs | 7/7 | 3/3 | 17/17 | null，未发现 |

总计22条实际事件、8次决策。两组链式的路由轮次均为[1,1,2]，第二轮后才发出后继Visit。固定E0任务时刻为A=[0,2,2,5,6]、B=[6,7,7,11,13]；FCFS为A=[0,0,0,10,10]、B=[10,11,11,15,17]，列顺序为派发、到达、开始、派生计算结束、实际完成。

## 对照了哪些内容

- 输入文件SHA、实际配置、从两侧已构建模型读取的依赖/ID/候选顺序及UT/PT/DT。
- 每条事件的顺序、时间、类型、任务/资源、owner、生产设备。
- 事件前后任务标记、ready_time、priority、资源available_time、队列与两个缓存、完成记录、集合与完成登记。
- 事件内部DECISION/EMIT的真实交错顺序；每次决策的全部候选、即时评分、选择、轮次及候选/资源状态。
- 实际任务时间、工作流时间、计数、最终状态和makespan。
- Java观察到的待开始Process与Python预约按明确映射比较，Java未加入Python保护逻辑。

原始文件不改写；另存规范化副本。已知表示差异及映射见每个comparison.json和[适配文档](JAVA-FIXED-ADAPTER.md)。Java未完成时间0.0与PythonNone、原Java缺少pending_start属于表示差异，不能说raw逐字相同。未登记非零时间、多个Java待开始项目不会被转换规则隐藏。

## 每个案例的原始证据

| 案例 | Python原始轨迹 | Java原始轨迹 | 对照报告 |
| --- | --- | --- | --- |
| 本地单任务 | [Python](../outputs/parity/single_local/python-raw.json) | [Java](../outputs/parity/single_local/java-raw.json) | [报告](../outputs/parity/single_local/comparison.json) |
| release=5 | [Python](../outputs/parity/single_local_release5/python-raw.json) | [Java](../outputs/parity/single_local_release5/java-raw.json) | [报告](../outputs/parity/single_local_release5/comparison.json) |
| 固定E0链式 | [Python](../outputs/parity/chain_remote/python-raw.json) | [Java](../outputs/parity/chain_remote/java-raw.json) | [报告](../outputs/parity/chain_remote/comparison.json) |
| FCFS链式 | [Python](../outputs/parity/chain_fcfs/python-raw.json) | [Java](../outputs/parity/chain_fcfs/java-raw.json) | [报告](../outputs/parity/chain_fcfs/comparison.json) |

各目录还含run-manifest、Java实际请求、进程命令和stdout/stderr。构建证据位于outputs/parity/build：两份构造补丁、overlay、Java版本、编译命令/输出、647份源码与12个依赖jar的哈希。

[来源完整性核对](../outputs/parity/build/source-integrity.json)实际比较659个文件，与提供Java ZIP字节一致；没有改references原始源码。原依赖在JDK17下产生44条旧API/strictfp等警告，0编译错误。

## 测试覆盖与证据边界

| 测试组 | 实际验证 |
| --- | --- |
| 原0.1测试 | 输入、模型身份、状态、规则、事件/堆、缓存/预约、失败、日志、重跑、手算案例，113项继续通过 |
| tests/integration/test_v01_regression.py | 新结果去掉新增日志字段后与保存0.1轨迹完全一致，4案例 |
| tests/parity/test_fixed_java.py | 真正编译并运行原Java类的4案例、构造补丁范围、原件未改、日志无干扰、新JVM重复、Unicode任务ID、旧trace保护、真实轨迹故障注入 |
| tests/unit/test_trace_compare.py | 合成日志的错序、错误时间/评分/选择、漏第二轮、ready/预约差异、非法完成时间、字段顺序、容差、失败不能假通过、CLI报告 |
| 原Java组件oracle | 4,764条操作、3,797条输出仍逐行一致；属于局部方法/堆证据，独立于新增完整生命周期适配 |

合成日志负例只证明对照器检测能力，不当作Java调度证据。完整生命周期的Java证据来自parity实际JVM输出。

## 首差检测负例与开发修正

复制真实chain_fcfs Java轨迹，将首次路由的首项分数从0.0改为99.0。对照器正确定位第1事件的actions[0].decision.candidates[0].priority，并报告两侧0.0/99.0。原始Java轨迹SHA保持不变。证据：[人工故障报告](../outputs/parity/fault_injection/comparison.json)、[修改副本](../outputs/parity/fault_injection/java-score-altered.json)。这是人工故障，不是4个正常配置的调度差异。

首次完整测试144通过、1失败：漏第二轮路由负例已经找到正确事件/action，但诊断路径只到对象层。改进共同字段比较后，进一步定位到kind字段，最终145项全通过。初次XML保留在[开发记录](../outputs/development/pytest-0.2-first.xml)，没有改变调度来使测试通过。

## 未执行与尚待验证

- 同一单设备规模下的复杂分叉汇合、完整资源竞争、复杂同刻交错及Java/Python对照：后续0.2主验收。
- pending_start与原Java canAddToQueue在所有可达竞争情形的差异：尚未确认。
- 多设备完整集成、任意输入等价性、作者实际运行build：未证明。
- 原始随机/训练入口、warm-up统计、DAX/RNG/seed、GP及论文规模结果：不在本次范围，未执行。
- 其他Python版本及操作系统：未实际运行。

0.1原始输出保留于outputs/v0.1，旧fogsim-0.1.0.zip不覆盖。当前结论仅为：指定参考JDK和明确固定模式适配下，这4个现有配置通过逐事件、逐决策和状态/结果对照。

## 交付包独立验证

已在基础Python的 `-I` 隔离进程中加载解压包内源码，使用包内647份Java源文件及随附依赖重新编译，四个固定配置再次全部对照通过。已断言导入模块、编译源目录和全部Java运行classpath条目位于解压目录；仅参考JDK可执行文件来自外部。证据：[package-smoke.json](../outputs/package-smoke.json)。

新版安装和 `python -m fogsim --version` 已实际验证为0.2.0a1；compileall语法检查通过。交付ZIP构建时核对已验证源码哈希、压缩包CRC及每个打包文件的SHA，包内附RELEASE-FILES.json。
