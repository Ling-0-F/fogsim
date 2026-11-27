# 项目文件结构与职责规划

文档版本：1.1.0；更新日期：2026-10-22（America/Los_Angeles）。这是拟实现结构，不表示这些 Python 文件已存在。

返回 [总览](00-START-HERE.md)。字段以 [模型字段表](04-MODEL-FIELDS.md) 为当前设计基线。

## 1. 规划目录

子包均需适当的 `__init__.py`，下列展示除根包外省略。标记“后续”的文件或目录到对应阶段再创建。

```text
fog-computing-python/
    README.md
    pyproject.toml
    src/
        fogsim/
            __init__.py
            __main__.py
            cli.py
            config.py
            model/
                workflow.py
                task.py
                resource.py
                execution.py
            simulation/
                state.py
                events.py
                event_queue.py
                engine.py
                readiness.py
                metrics.py
                trace.py
            rules/
                base.py
                contexts.py
                selection.py
                baselines/
                    fcfs.py
                gp_rule.py                 # 后续
            instances/
                spec.py
                fixed.py
                dax_parser.py              # 后续
                samplers.py                # 后续
                generator.py               # 后续
                communication.py           # 后续
            features/                      # 后续
            gp/                            # 后续
            evaluation/                    # 后续
            experiments/                   # 后续
            analysis/                      # 后续
            validation/
                trace_compare.py           # 0.2
    configs/
        tiny.json
        training/                          # 后续
        testing/                           # 后续
    data/
        cases/
            single_local.json
            chain_remote.json
            diamond.json
            contention.json
            event_ties.json
        dax/                               # 后续
        reference/
            java/
    tests/
        unit/
        integration/
        parity/
    tools/
        java/
    docs/
        java_mapping.md
        semantics.md
        roadmap.md
    outputs/
```

`diamond.json`、`contention.json`、`event_ties.json` 的主要验收阶段为 0.2。当前八份 Markdown 是设计交接包；未来可放入项目 `docs/` 并更新 README 导航。04 维护字段，07 维护唯一完整状态归属表，不复制成两套独立基线。

## 2. 0.1/0.2 代码文件职责

以下代码路径从 `src/fogsim/` 开始。

| 文件 | 职责与内容 | 阶段 |
| --- | --- | --- |
| `__init__.py` | 包入口、必要的公共导出；避免启动模拟等导入副作用 | 0.1 |
| `__main__.py` | 将包运行入口转交给命令行入口 | 0.1 |
| `cli.py` | 读取命令，组装实例、规则与模拟器，指定输出 | 0.1，后续扩展命令 |
| `config.py` | 运行配置的加载与合法性检查；区分配置和实例数据 | 0.1 |
| `model/workflow.py` | Workflow，工作流完成记录及派生属性 | 0.1 |
| `model/task.py` | Task、TaskOption，共享引用和依赖关系 | 0.1 |
| `model/resource.py` | Resource、MobileDevice、Server；资源参数、等待队列、按类型维护的缓存及 pending_start；队列修改统一入口 | 0.1 |
| `model/execution.py` | Execution；接受确定开始安排时建立，保存不变时间字段；排队临时试算不登记为正式执行 | 0.1 |
| `simulation/state.py` | SystemState；时钟、pending/active/completed 工作流、资源/任务索引及 executions_by_task；生命周期登记及一致性；统计尽量派生 | 0.1 |
| `simulation/events.py` | 四种事件数据与触发逻辑；按 07 调用指定职责操作；Python 构造只保存参数，完整读写/先后待事件表展开 | 0.1 |
| `simulation/event_queue.py` | Engine 持有的事件管理器；插入/取出、比较、同时刻处理；核对 Java 暂存归并影响，日志序号不自动排序 | 0.1，0.2 专项验证 |
| `simulation/engine.py` | 持有 SystemState、EventQueue、TraceRecorder；推进时钟、事件循环、处理序号、正常/异常运行控制；固定重跑重建运行对象图 | 0.1，后续扩展随机重设 |
| `simulation/readiness.py` | 入口识别、前驱完成与防重复派发；只检查已到达工作流 | 0.1 基础，0.2 完善 DAG |
| `simulation/metrics.py` | makespan；后续扩展 mean flowtime 等源码指标 | 0.1 |
| `simulation/trace.py` | TraceRecorder；保存事件、评分/选择和队列快照、任务实际时间；区分执行计划与实际触发，日志不参与调度 | 0.1 |
| `rules/base.py` | 路由/排序规则的接口与类型，不包含模拟循环 | 0.1 |
| `rules/contexts.py` | 路由/排序候选、资源和受限只读状态；未来工作流及完整内部索引不暴露给规则；具体接口待设计 | 0.1 |
| `rules/selection.py` | 评分后的候选选择和平分比较；保留遍历行为 | 0.1 |
| `rules/baselines/fcfs.py` | Java FCFS 的两种评分，不能替换成按任务入队时间的另一种 FCFS | 0.1 |
| `instances/spec.py` | 可重复使用的输入描述；不携带上一轮的派发、队列、时钟等可变状态 | 0.1 |
| `instances/fixed.py` | 读取固定实例，验证 ID/依赖/时间/资源资格，建立输入描述 | 0.1 |
| `validation/trace_compare.py` | 读取同格式轨迹，比较事件与决策，报告首个差异 | 0.2 |

`events.py` 初期集中四种事件，便于阅读生命周期；文件规模增长后才考虑拆包。模型使用对象引用时，类型导入与构建顺序需要避免循环导入，具体方案待接口设计。

## 3. 其他目录

| 位置 | 保存什么 |
| --- | --- |
| `README.md` | 目标、当前可用功能、安装和运行方法、设计文档导航；未实现命令不可写成可用 |
| `pyproject.toml` | 项目、依赖和工具配置；Python 最低版本及测试框架待编码前确定 |
| `configs/` | 使用什么规则、哪个实例、输出开关；后续训练与测试配置 |
| `data/cases/` | 可手算的固定实例；具体实例数据与运行规则分开 |
| `data/dax/` | 后续工作流 XML 模板；从原项目实际生效的根目录 dax 取得 |
| `data/reference/java/` | 有明确实例与配置对应关系的 Java 参考结果；不被普通 Python 运行覆盖 |
| `tests/unit/` | 关键局部语义：平分、时间计算、依赖和队列缓存等 |
| `tests/integration/` | 完整固定实例的生命周期与指标验收 |
| `tests/parity/` | Java/Python 行为对照 |
| `tools/java/` | Java 固定实例构建、导出输入/事件/决策轨迹的辅助入口；尚未实现 |
| `docs/java_mapping.md` | Java→Python 路径、类/方法对应与迁移进度 |
| `docs/semantics.md` | 时间、事件、评分、重置、统计边界及差异 |
| `docs/roadmap.md` | 阶段、验收和当前进度 |
| `outputs/` | 本次运行产生的轨迹、指标、实验输出；不作为已验证参考结果的唯一保存位置 |

## 4. 后续功能的文件位置

| 包 | 建议文件 | 计划内容 |
| --- | --- | --- |
| `instances` | `dax_parser.py` | 从 DAX 读取任务与边，转换为统一输入结构 |
| `instances` | `samplers.py` | 均匀、整数均匀、指数、离散带宽和权重采样；核对参数与端点 |
| `instances` | `generator.py` | 模板选择、工作流参数和动态到达；设备归属、全局 ID、随机调用顺序 |
| `instances` | `communication.py` | 根据原始工作量、数据量、资源速率和带宽生成执行选项 |
| `rules/baselines` | 每种基准算法一个文件 | 移植 HEFT、MinMin 等实际实现；标记占位、注释或未启用算法 |
| `rules` | `gp_rule.py` | 用同一规则接口包装 GP 表达式，连接候选状态、特征和求值器 |
| `features` | `attributes.py`、`relative.py` | 属性定义和当前相对终端集合；值的计算按源码，不凭名称推断 |
| `gp` | `tree.py`、`functions.py`、`expression.py` | 树、函数、受保护除法、表达式解析/输出及所需简化 |
| `gp` | `individual.py`、`initialization.py`、`selection.py` | 单/双树个体、初始化、锦标赛等 |
| `gp` | `operators.py`、`evolution.py`、`statistics.py` | 交叉/变异、深度、精英、演化循环及最优规则/树大小记录 |
| `evaluation` | `scheduling_set.py`、`evaluator.py`、`fitness.py`、`policy.py` | 多实例、重复、seed 轮换、异常值、适应度；个体转换为路由/排序规则 |
| `experiments` | `scenarios.py`、`train.py`、`test.py`、`benchmark.py` | 场景、训练、独立测试和基准对比 |
| `analysis` | `readers.py`、`statistics.py`、`plots.py`、`rule_analysis.py` | 读取结果、统计、绘图、规则大小与终端频率分析 |

## 5. 依赖与职责约定

1. 模型表达数据、局部状态和必要操作；任务对象不直接调用 FCFS 或 GP。
2. 模拟器通过规则接口作决策，固定规则与 GP 规则使用相同接口。
3. 实例描述可复用；每轮运行建立独立可变对象。对象构建、重置及 RNG 重设需分别设计。
4. 一个 Task 在 Workflow、TaskOption、依赖和事件中应是同一个对象。不得无意复制成几份不一致的状态。
5. GP 树和演化通过评估接口取得适应度；具体模拟、批次平均与异常处理由 evaluation 负责。
6. 实验入口负责组装，模型不反向依赖实验脚本。
7. 状态归属第一版设计已完成，以 [07](07-STATE-OWNERSHIP.md) 为权威；本文件维护职责，不重复完整状态表。下一步展开事件读写表及接口。

## 6. 1.1.0 的状态管理补充

- 固定实例由 instances/fixed.py 验证为 InstanceSpec，运行构建过程再建立本轮模型；构造模型不隐式采样、产生工作流或修改共享 sampler。
- 事件处理协调派发、开始安排、任务完成和工作流登记；模型负责局部不变量，SystemState 负责全局成员关系。具体函数签名尚未确定。
- 已选定 Resource.pending_start 和 SystemState.executions_by_task。前者保存待开始预约引用，后者登记确定执行；Workflow.completed_executions 只含真正完成的同一 Execution。
- 固定重跑重建所有运行对象与引用；RNG 内部状态和生成进度后续归 instances，seed 轮换归 evaluation 配置与驱动，不重新混入资源职责。
- 事件集中管理是 Python 结构选择；是否需要兼容 Java 的暂存/归并机制，由后续事件策略与运行对照确定。
