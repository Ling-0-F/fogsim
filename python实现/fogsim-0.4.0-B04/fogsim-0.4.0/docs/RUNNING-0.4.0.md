# fogsim 0.4.0 运行手册

本版本完成 S9 的固定评估、单树 routing＋FCFS sequencing、双树 sequencing/routing 学习闭环。设计为 S9-frozen-1，固定执行语义为 D-frozen-1。最终状态见 outputs/step9/B04/acceptance.json 和 development/S9-B04/REPORT.md；S01—S17 的证据定位在 docs/ACCEPTANCE-S9-B04.md。

## 解压与安装

四个分包均以 fogsim-0.4.0/ 为顶层，解压到同一个新目录：主包 B04、evidence、references、rollback，路径互不覆盖。分包索引记录字节数与SHA-256。主包提供源码、测试、所有必要小场景/DAX、配置、schema、设计和运行手册；references提供离线依赖及原Java/历史来源；evidence提供历批及本批原始证据；rollback保留前批原交付。基本源码使用需要主包；离线训练安装还需references，完整复核及回滚需要全部分包。不要覆盖旧实验目录。

已验证运行环境是 Linux x86_64、CPython 3.12.14；包内训练轮子适用于CPython3.12/Linux x86_64（moocore为abi3）。项目允许Python≥3.11，但未声称其他环境随机序列可复现。换平台须取得对应精确版本轮子、另存锁/环境并重新验收。JDK17用于Java对照，普通Python模拟与训练不需要Java；JDK不随包，其下载URL/SHA-256在development/S9-B02/dependency-lock.json。

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --find-links development/S9-B02/wheels --require-hashes -r development/S9-B02/requirements-train.lock
python -m pip install --no-deps development/S9-B04/dist/fogsim_reproduction-0.4.0-py3-none-any.whl
```

B01—B04的安装版号均为0.4.0；已有旧批次时加 --force-reinstall 安装当前wheel。也可在工程根目录使用 PYTHONPATH=src，避免安装项目wheel。旧固定/动态/重放与独立加载冻结规则无需DEAP。未装训练依赖时train按输入错误退出2，旧功能仍可运行。

## 小规模训练与独立评估

```bash
PYTHONPATH=src python -m fogsim.training.cli validate --config configs/training/smoke-single.json --output outputs/my-single-preflight
PYTHONPATH=src python -m fogsim.training.cli train --config configs/training/smoke-single.json --output outputs/my-single
PYTHONPATH=src python -m fogsim.training.cli train --config configs/training/smoke-dual.json --output outputs/my-dual
PYTHONPATH=src python -m fogsim.training.cli evaluate --rules outputs/my-dual/trial-0001/selected_rule.json --plan outputs/my-dual/plans/test.json --output outputs/my-dual-independent
```

validate不模拟、不创建进化RNG；结果为PREFLIGHT_ONLY。train在开始模拟前显示预算/保存策略/实际版本，并保存preflight.json。两种正式smoke各为12个体×4代×2seed，每次上界212条；若检验复现，使用相同配置另开输出目录，逐trial比较。历史B02/B03的首跑＋复跑840条证据已保留，本批不自动重启它们。

API由fogsim.training导出parse_training_config、build_training_plans、evaluate_rule_pair、train、evaluate_selected_rule。API返回不可变JSON快照，不暴露Engine或RNG。evaluate_selected_rule读取完整selected-rule身份与B08 rule_manifest，既可单独调用也可由CLI读取。进度回调只观察已发生事实；异常中止控制流程并留证。使用spawn的程序入口须有 if __name__ == '__main__' 保护。

## 大规模自运行

两个可编辑文件：configs/training/large-single-template.json、large-dual-template.json。默认入口只预检：

```bash
PYTHONPATH=src python tools/run_s9_training.py --config configs/training/large-dual-template.json --output outputs/my-large-preflight
```

两模板当前均为100个体×50代×5个不同evolution seed；训练每代2条、固定验证2条、测试2条。每trial上界100×50×2＋50×2＋2=10102，五trial上界50510。事件预算2000/条，粗略累计上界101020000。候选按rule_pair_id去重可能减少验证次数。预检不会将50510条标记为已执行。

只有用户后续明确选择执行时，另用新的输出目录：

```bash
PYTHONPATH=src python tools/run_s9_training.py --config configs/training/large-dual-template.json --output outputs/my-large --execute
```

修改规模用evolution.population_size/generations/elite_count和trials.evolution_seeds；修改场景先复制六份B03-*-0/1.json及三份source清单、修改引用，再编辑资源/采样范围/num_jobs_recorded/warmup_jobs/max_events。source seed与evolution seed分离，跨split输入不能重用，每代训练seed步长10000且溢出会预检拒绝。路径相对所属配置文件解析。固定验证/测试在训练前展开，不依据测试成绩换候选。

模板沿用B03工程小场景，不代表论文数据和实验设置。output.trace=none可关闭常规完整事件trace；all或selected_cases按现有协议启用（selected_cases当前保守保存完整trace）。规则、计划、配置、谱系、原结果、可导出输入和故障摘要仍保留；save_run_results/save_input_archives必须true，不提供关闭。当前没有磁盘配额或自动清理，大实验应先缩小规模测量实际时间/空间，手动预留容量。事件数不能换算为时间/内存/磁盘保证；B08只读图检查在积压下可能很慢。可设置limits.wallclock_seconds_per_run，默认null，触发时单独标记INCOMPLETE，不能当领域失败。

## 读取输出与退出

resolved_config.json记录全部默认值，provenance.json记录当前源码与依赖；plans/冻结公共计划。每trial的generations.jsonl/individuals.jsonl/operations.jsonl记录代、出生、谱系与算子；candidates/archive.json包含首次及全部出处；validation/统一评分；selected_rule.json在test/之前冻结。training-result.json/evolution-result.json记录终态。正式fitness为完整计划全部成功后的运行等权平均，成功子集均值仅为诊断。不同代训练成绩不构成全局排名；跨trial不按test挑冠军。

退出0成功；2配置/输入错误（包括非空输出目录）；1领域不可行/无验证赢家/最终测试失败；控制流程返回的INCOMPLETE退出130。KeyboardInterrupt由Python进程终止语义处理并留中断证据；未知程序异常保留异常链并非惩罚适应度。失败/中断看failures/，只承认完整提交JSONL行；received-only/capture_complete=false档案不能假装完整重放输入。保存记录不等于支持任意断点续训。重新运行使用新目录。

## 新旧联合复核

测试工具离线安装：python -m pip install --no-index --find-links development/S9-B04/test-wheels --require-hashes -r development/S9-B04/requirements-test.lock。Java对照还需要JDK17，设置FOGSIM_JAVA为其bin/java路径。完整复核在新的工程解压副本中执行，避免旧脚本在历史相对路径生成文件：

```bash
PYTHONPATH=src:tools PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests -q --junitxml=outputs/my-regression.xml --basetemp=outputs/my-regression-cases
PYTHONPATH=src:tools python tools/audit_contracts.py --junit outputs/my-regression.xml --output outputs/my-contract-audit.json
```

测试会在独立副本的若干旧路径生成当前结果；不能据此覆盖保留的原交付证据。源码/历史保留和协议审计另见B04命令记录。原Java/Python本地RNG序列允许不同；局部受控对照不等于任意输入Java等价。无数值ERC搜索、并行加速、任意中断点恢复、论文规模训练或论文表格复现。两个旧大型native固定投影仍为非必需、未执行项，不伪称完成。
