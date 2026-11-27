# 来源可访问性与阅读记录

实际材料位于交付项目的上一级目录。不存在 `来源/` 子目录；所需文件均可访问。设计 ZIP 实际包含 00—11 共12份 Markdown，与 prompt 列表一致。`prompt.txt` 的任务文本重复两次，内容相同。

| 材料 | SHA-256 |
| --- | --- |
| 实现方案及详细设计.zip | `9ab607d19439cd25fe8dea60124be22651220e15e3ac34d142bd5aaaf482b42e` |
| Fog-Computing-multiDeviceDebug.zip | `17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a` |
| Fog-Computing-Java-to-Python-Study-Plan-2026-10-08.md | `221353e11d7f8493d3afd9b2aa02537f0be4f4073193b45cbe161ea839589e0a` |
| Xu 等（2023）中英双栏论文 PDF | `0fe716a44ca8d63013406d641e0b7dea652dc17f23614554f86c30b9937a9305` |
| prompt.txt | `353bbefa6800e4dbac8cf2caa59c3272d87fda503a6d26ca072897d9e18448f4` |

全部设计 Markdown 及学习计划已经读取；四事件的生效 trigger/compareTo、Task/TaskOption 查询及选择、AbstractRule、FCFS、Process 时间公式、队列缓存、canAddToQueue、主循环归并、Job 完成记录、MobileDevice 构造/完成统计和 SystemState 接纳等辅助路径进行了源码核对。没有把注释中的旧路径或 `out/` 编译文件作为实现依据。

论文 PDF 共15页，已提取文本，重点阅读 IV 的工作流/处理器/约束/指标、V 的模拟器与算法1，并渲染相关页检查算法1和图3。公式(2)对应全部输入工作流最大完成时间减最早发布时间；本地通信为零，未来工作流在发布前未知。论文的高层描述不用于替换源码的异常同刻比较、重复评分及下载占用细节。

本次没有实现论文 VI/后续实验中的 GP、采样、训练和统计机制。阅读材料不视作运行验证；真实验证结果分别记录在 VALIDATION 和 outputs 中。

`references/design/`保持原始文件内容不变。0.1包只保留局部oracle及阅读映射所需Java文件；0.2.0a1包为支持重新编译固定适配器，纳入原Java源码和12个非javadoc依赖jar。原ZIP、PDF和JDK二进制不重复打包。原647份Java源码及12个依赖jar已与提供ZIP逐项核对一致，见 `outputs/parity/build/source-integrity.json`。当前项目快照、顺序映射、构建补丁和轨迹指纹分别见validation-manifest、parity/build及各案例run-manifest。
# 第 1 步资料可访问性补充（2026-11-04）

本轮对话提供的七份材料均可访问：0.2.1 verified ZIP、冻结扩展设计 MD、简易实施顺序 PNG、multiDeviceDebug Java ZIP、2026-10-08 学习计划 MD、早期设计 ZIP、Xu 2023 双语 PDF。仅使用本对话附件，未搜索其他私人文件。

实际优先读取冻结设计全文、顺序图、README、VALIDATION、IMPLEMENTATION-NOTES、ISSUES-AND-FIXES、roadmap、semantics 及本轮配置/模型/建图/测试源码；Java 原始解析、资源构造、工作流生成和接纳方法静态核对。学习计划读取总体路线；早期设计仅核对目录与现有文档引用，论文可访问但本轮没有用它替代 Java 源码或开展新的模型结论核验。

冻结设计原文副本位于 `references/design/NEXT-STAGE-FROZEN.md`，顺序图位于 `references/design/NEXT-STAGE-ORDER.png`；设计正文历史“初稿/未进入编码”状态由本轮用户指令覆盖，未篡改原文。当前实施状态见 `STEP1-PROGRESS.md`。

Python 基线 ZIP 本轮 SHA256 为 b481609243dcd6c73c6428f3a242555f0ffaf5e27a63d5049e2fc50a72877c2e；Java ZIP 为 17a273961e66f409c4cfc8305ee31433bf7022232da3a2cbd0cc8e70e4c32c9a，均与设计来源表一致。

## 第 2 步补充（2026-11-04）

基于本对话 step1 交付包建立独立 step2 副本；直接读取冻结设计 §§7/8/13/19 及现有数据/配置/seed 契约。实际核对并编译 Java 原 WorkflowParser、DAGType/DAGTypePath、Task 的父子列表方法、Uniform/UniformInteger/Exponential/TwoSixTwo/BandwidthCloud/BandwidthEdge sampler，未修改原件或插入 source overlay。

`dax/` 的 22 份 XML 来自已上传 Java ZIP 的顶层 dax；本轮逐字节哈希核验，来源清单为 `dax/SOURCES.json`。20 个标准类型已实际 Java/Python 逐项拓扑核对；各自 sampler 对理论分布检查通过，证据见 `outputs/step2/` 与 `STEP2-PROGRESS.md`。没有以静态文档、论文或 getMean 值代替实际 next 和解析器运行结果。

## 第 3 步补充（2026-11-04）

独立 step3 副本来自本对话已保存的 step2 ZIP。重读冻结设计的资源/两遍生成/公式/拒绝/数值段落，及现有输入、sampler、资源、建图和测试代码。Java 静态核对 DynamicSimulation 的设备/边缘/云构造与 setup，MobileDevice.generateWorkflowJob、Task.addChildOutputData/addParentInputData/mapClear，TaskOption 与 SystemState.addJobToSystem。

运行核对使用 659 份指纹匹配的原源码/依赖，无覆盖补丁。只增加独立观察入口和脚本 sampler 子类，以相同数值检查原构造/生成调用、物理总量及候选时长。没有据此宣称原随机流、完整动态输入导出、统计/事件或调度轨迹已对照。原始 request、两侧结果、构建命令和版本保存在 `outputs/step3/`。

