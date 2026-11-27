"""Clause-level inventory and evidence checker for the frozen design, version 0.3.0."""
from pathlib import Path
import json
import hashlib
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
# Every row is an explicit source review obligation. Test/module associations
# point to executed assertions; they do not claim that test count is a proof.
GROUPS=[
('1.3','fixed','V01',[
 '旧固定JSON、公开API、结果字段与repeat保持兼容',
 '四事件、两层堆、异常比较器和平分遍历顺序保留',
 'Finish后两整轮路由、预约、计算/下载占用及缓存加减顺序保留',
 '固定全集完成才成功，领域失败空指标，未知程序异常传播']),
('4','architecture','V09',[
 '输入/环境/来源→集中接纳→规范状态→原四事件；不复制调度器',
 '日志和比较只观察；规则视图不含Context、RNG、完整归档或未来输入',
 '资源对象不承担生成、seed轮换或批次汇总']),
('5.1','contracts','V09',[
 '模板和任务映射独立不可变；不含随机值或运行图',
 '环境保存有序实际资源数值；不含队列状态',
 '候选完整保存任务物理值、累计、边值和全部实际PT/UT/DT',
 'attempt与正式工作流ID分离；归档不共享可变边字典']),
('5.2','contracts','V09',[
 '旧构造字段位置保留，新增可选字段后置',
 '动态Workflow元数据、Task物理数据、资源物理参数完整',
 'UNAVAILABLE/RETAINED/RELEASED及访问错误明确',
 'Task/Workflow无Context、归档或目录的反向引用']),
('5.3','identity','V09',[
 '动态ID为接纳前G；拒绝不占ID，固定ID不重编号',
 'Task.id保留XML字符串，Java编号仅按任务位置映射',
 '设备/服务器编号按资源顺序；不靠名称后缀解析',
 '同轮规范对象唯一，跨工作流/跨轮对象图隔离',
 '模板依赖顺序与边采样顺序分别保存，不混用']),
('6','invariants','V09',[
 'G/B/R各有单一权威；recorded引用物理completed中的同一对象',
 'pending/active/completed互斥且覆盖全部接纳工作流',
 '各设备计数、统计子集、实际到达与物理完成关系一致',
 '任务只派发/执行/完成一次，资源预约与Start一一对应',
 '占用区间为正且不重叠，队列/缓存/引用/执行索引受检查']),
('7.1','dax','V02',[
 '20标准编号/文件/实际规模对应；额外图不自动编号',
 'dag_root相对配置路径；文件名及声明计数不决定实际图']),
('7.2','dax','V03',[
 '根adag、允许命名空间及结构大小写按约定识别',
 'job/child按根直属顺序，ID/ref原样保留，uses不参与参数',
 '前向/未知引用、重复ID/边、自环/环、空图和未知结构拒绝',
 '不排序拓扑或加虚拟节点；允许无边/多入口出口/不连通DAG',
 '声明数量不符仅诊断；失败含位置及相关ID/ref，无部分模板']),
('7.3','catalog','V05',[
 '抽样范围所有模板在RNG创建前加载、验证和冻结',
 'reset/rerun/rotate复用模板及哈希；文件变更需新上下文']),
('8.1','rng','V15',[
 '公开seed是真signed64，拒绝bool/浮点/字符串/越界',
 '内部按unsigned64位模式编码，保留版本及精确十进制',
 'rotate回绕加10000；reset(None)使用当前seed，不调用随机None种子']),
('8.2','rng','V05',[
 '每Context一条共享输入流，环境与所有设备共同推进',
 'sampler只持参数，构造/校验/clone/日志不抽数',
 '角色共享正确，上下行独立角色，各Context sampler独立',
 '先校验冻结有效参数；mean100冲突及不支持profile明确拒绝']),
('8.3','samplers','V04',[
 '实数均匀拒零并按u*b+(1-u)*a；端点舍入不钳制/重抽',
 '整数用包含两端randint，单点仍调用；指数按Python算法且可返回0',
 '权重及云带宽0.2/0.8边界和拒零正确',
 '边缘带宽1024常量不推进RNG；不移植Java指数内部算法']),
('8.4','samplers','V04',[
 '标准参数范围、概率和有效参数指纹保存',
 '只使用s和模型单位，不擅加单位换算',
 '复现要求代码/运行时/数据/操作一致；跨环境以实际输入为依据']),
('9.1','environment','V06',[
 '先所有设备算力，再边缘/云各上行、下行、算力',
 '禁用本地仍采设备算力，边缘带宽仍调用但不抽数',
 '资源数值齐备后逐设备尝试；运行队列/缓存/预约/时钟归零',
 '服务器全局规范共享，不按设备复制']),
('9.2','generation','V07',[
 '类型→间隔→release→权重→两遍生成顺序保持',
 '第一遍每任务workload/data/children交错，边只采一次',
 '第二遍按parents顺序累计并创建完整候选',
 '已知release不推进也完整消耗候选采样；不提前跳过']),
('9.3','generation','V08',[
 '累计从0逐项加，不排序/fsum；总量不含基础data',
 '本地PT与零UT/DT、远程PT/UT/DT公式和括号保持',
 '候选为合法本地→边缘→云，其他移动设备不候选',
 '无边仍传基础data，同服务器父子不免通信']),
('9.4','admission','V11',[
 '完整生成后按finite release>clock接纳',
 '成功集中登记规范图/任务事实/pending/G/设备数/B/Arrival',
 '拒绝保留完整候选/attempt，不登记、不占ID、不改G/B、不发事件',
 '拒绝不重抽或回滚，不中断其他设备，Finish不续生',
 '非法派生值是领域失败，原始delta与release均保存']),
('9.5','numeric','V22',[
 'workload/算力/带宽/PT正有限，data/UT/DT非负有限',
 '派生加除、PT下溢及执行总区间舍零明确失败',
 'N/W及N+W乘500、资源编号/G在int32边界内，不模仿计数回绕',
 'W0合法；N1/W0不可达统计目标不自动修正']),
('10','events','V10',[
 '固定/随机/重放共用原事件处理和真实initialize/after_arrival位置',
 'Arrival先激活并派发全部入口，再生成一次；Finish不生成',
 '不随机换设备；达到N+W仍继续生成',
 '所有新事件stage；owner和当前生产设备分离',
 'no-trace仍登记任务事实/输入；actions保留实际DECISION/EMIT交错',
 '动态每轮单次归并→目标→耗尽→预算→poll；固定pop_next保持']),
('11.1–11.2','statistics','V12',[
 'Java字段映射G、设备生成/物理/统计数、R、B准确',
 '接纳后G<N+W时B直接赋值，可下降；等号后冻结',
 '完成时按当时G>W、ID非负、release<=B筛选一次',
 '不增加ID窗口筛选；不补录；物理完成标志与统计资格分离']),
('11.3','statistics','V13',[
 'R达标事件完整执行，再归并停止，保留同刻剩余/pending/active',
 '动态指标只用统计集合，flow按登记顺序逐项累计，不加权',
 '固定指标用全集；失败指标为空，不使用成功子集填充']),
('12','guards','V14',[
 '仅在原事件后位置按原顺序检查严格>保护和全部命中',
 '首次保护明确FAILED，保留实际时钟和队列，不执行Java异常尾部',
 '同事件目标与保护冲突时失败优先',
 '事件耗尽、预算、重放覆盖、数值/状态错误稳定区分',
 '结果保留计划/实际时刻区别、物理/统计/源消费事实']),
('13','context','V15',[
 'fresh先环境后工作流，B0；reset重设输入流且保留环境/B',
 'rerun延续流与B；rotate只准备不运行',
 '每轮重建对象，结果快照隔离，READY旧引擎不能再推进流',
 '生命周期仅在轮次边界；准备失败保留诊断并可显式恢复',
 '原生RNG边界快照含Python/state版本，不以哈希代替真实状态']),
('14','cleanup','V20',[
 '默认retain；提供实际工作流级释放能力',
 '完整候选已独立归档，整张工作流预检后才修改任何映射',
 '仅两张运行映射置None/RELEASED；身份、拓扑、物理值、选项和完成记录保留',
 '固定UNAVAILABLE跳过，重复释放幂等，映射条目不误作独立边数',
 '归档/RNG/时钟/事件/候选/轨迹/统计不因开关变化',
 '测量准备和完整小型运行的current/peak/耗时，不宣称普遍加速']),
('15.1–15.2','replay','V17',[
 '独立schema-v1 input/reference/manifest分层；input单独运行',
 '版本、未知字段、数组、真整数、有限值、顺序/引用/候选/capture严格校验',
 '拒绝、未到达、未完成候选均保留；输入无参考决策/完成集/停止指标',
 '主调度使用记录时长，累计/公式审计独立且不回写',
 'capture完整不表示无限输入；不完整捕获不能完整验收']),
('15.3','java_export','V16',[
 '真实原Java构造/setup/run，第二遍后mapClear前复制完整候选',
 '接纳后补观察，保留初始化/Arrival拒绝及未到达候选',
 '原源码不改，观察追加且不增加采样/评分/比较操作',
 'plain/baseline/minimal/full验证观察无干扰，来源/依赖指纹保留']),
('15.4','replay','V18',[
 '每次仅下一全局attempt，核对phase/owner/clock/触发workflow/拟用ID',
 '不搜索、不按设备重组、不用event_sequence安排调度',
 'Python独立release gate后核对observed acceptance',
 '需要更多记录时明确用尽/错位，保留位置和部分诊断，不补输入',
 '正常停止可有未消费尾部；换规则覆盖不足不直接判算法错误',
 'verify禁止行为变更；reuse仅支持的规则且关闭原轨迹结论']),
('15.5','projection','V19',[
 '只投影成功接纳，保留资源/接纳/任务/依赖/选项顺序及ID/实际时长',
 '独立标明fixed_projection、拒绝/动态位置/统计窗/物理字段损失',
 'Java和Python固定入口消费同一投影到全集完成',
 '固定结果不与原动态统计指标混比，保留Java规则/物理占位限制']),
('16','config','V21',[
 '新实验格式/版本/mode独立，旧配置不猜模式',
 '路径相对配置或直接CLI cwd，程序化相对路径要求base_dir',
 '未知/重复键、bool数值、非有限/非法范围/无候选在采样前拒绝',
 '固定路由对所有可能owner合法；seed列表完整且不矛盾',
 '冻结配置及profile冲突拒绝；诊断选项不偷偷改变输入']),
('17.1–17.2','api','V21',[
 '保留旧固定公开接口和单次Engine.run；新API独立调用，simulate_replay支持可选运行后比较报告',
 '创建/reset领域失败抛带Engine/结果的PreparationError，便利入口归一化',
 '未知程序异常保持原类型并传播']),
('17.3','cli','V21',[
 'dynamic/replay/export-fixed显式入口；仅dynamic可覆盖seed',
 'CLI覆盖在创建上下文前完成并进入有效配置',
 '退出0/1/2、no-trace事实/输入、旧repeat/identical语义保持',
 '未知异常不保留旧成功文件，保存中断时batch/capture明确不完整',
 '集中admit返回accepted/workflow/reason_code的AdmissionResult；普通拒绝非异常']),
('18','experiments','V21',[
 '多轮必须显式模式，fresh_same_seed每轮新建，seed_list仅指定seed',
 'java_rerun同Context延续RNG/B和环境数值，最终无额外reset/prepare/rotate',
 '重放每轮新对象/游标，不消费前轮尾部',
 '每轮完整快照记录seed/环境/初始B/来源；观察回调也不能污染后续结果',
 '领域失败继续；未知异常中止并标未完成，不作GP惩罚',
 '完整成功才all_runs_mean，成功子集显示分母/失败率，少于2无样本std',
 '仅同场景/统计/规则/策略汇总；允许显式seed差异，DAX变更禁混合']),
('19.1','samplers','V04',[
 '3固定seed、每角色每seed100000样本、阈值预先固定且原始结果保留',
 '两语言分别对理论分布，不要求同seed样本相等']),
('19.2','comparison','V17',[
 '先输入/配置/来源位置，再按事件序号比较头、前态、动作、后态、错误',
 'ID/计数/顺序精确，浮点abs1e-9/rel1e-12，priority区分有符号零',
 '不排序/补调用/按时间匹配/覆盖时长掩盖差异',
 '正常通过需完整捕获/覆盖/受支持条件/双边正常/清单绑定/首差空',
 '正常、预期差异、覆盖不足、失败、未执行、基础设施错误分开，无参考NOT_COMPARED']),
('20–21','differences','V22',[
 'Java/Python已确认差异逐项列出scope/known_differences',
 '结构/错误/统计/精度/RNG差异不泛称随机差异，失败后流尾差异明确',
 '旧物理未知值兼容，不经旧序列化静默丢物理输入',
 '只减少运行边映射，不清空工作流/执行历史或删保护以求规模',
 'dataset_role保存为来源元数据，规则无未来数据/演化RNG'])]

ALIASES={
 'fixed':(['instances/fixed.py','simulation/engine.py','simulation/events.py','simulation/event_queue.py'],['integration/test_runs.py','integration/test_v01_regression.py','integration/test_step1_fixed_compatibility.py']),
 'architecture':(['instances/source.py','simulation/admission.py','simulation/dynamic.py','rules/contexts.py'],['unit/test_dynamic_admission.py','unit/test_model_rules.py']),
 'contracts':(['instances/generated.py','instances/templates.py','environment/spec.py','model/task.py','model/workflow.py'],['unit/test_input_contracts.py','unit/test_materialize_workflow.py']),
 'identity':(['instances/identity.py','instances/materialize.py','simulation/state.py'],['unit/test_input_contracts.py','unit/test_dynamic_admission.py']),
 'invariants':(['simulation/state.py','simulation/statistics.py','simulation/event_queue.py'],['unit/test_queue_lifecycle.py','unit/test_dynamic_statistics.py','unit/test_dynamic_admission.py']),
 'dax':(['instances/dax.py','instances/catalog.py'],['unit/test_dax.py']),
 'catalog':(['instances/catalog.py','randomness/state.py','simulation/context.py'],['unit/test_random_input_state.py','unit/test_dynamic_context.py']),
 'rng':(['seed.py','randomness/state.py','randomness/samplers.py','simulation/context.py'],['unit/test_samplers.py','unit/test_random_input_state.py','unit/test_dynamic_context.py']),
 'samplers':(['randomness/samplers.py','experiment_config.py'],['unit/test_samplers.py','unit/test_experiment_config.py']),
 'environment':(['environment/build.py','environment/spec.py'],['unit/test_environment_build.py']),
 'generation':(['instances/generation.py','instances/materialize.py'],['unit/test_workflow_generation.py','unit/test_materialize_workflow.py','integration/test_generated_kernel.py']),
 'admission':(['simulation/admission.py','simulation/dynamic.py'],['unit/test_dynamic_admission.py','unit/test_final_contracts.py']),
 'numeric':(['numerics.py','input_validation.py','instances/generation.py','model/execution.py','simulation/statistics.py'],['unit/test_workflow_generation.py','unit/test_execution_precision.py','unit/test_dynamic_admission.py','unit/test_dynamic_statistics.py']),
 'events':(['simulation/events.py','simulation/dynamic.py','simulation/engine.py','simulation/trace.py'],['unit/test_events.py','unit/test_dynamic_admission.py','unit/test_dynamic_statistics.py']),
 'statistics':(['simulation/statistics.py','simulation/dynamic.py','simulation/dynamic_result.py'],['unit/test_dynamic_statistics.py']),
 'guards':(['simulation/statistics.py','simulation/dynamic.py','simulation/dynamic_result.py'],['unit/test_dynamic_statistics.py','unit/test_dynamic_context.py']),
 'context':(['simulation/context.py','randomness/state.py'],['unit/test_dynamic_context.py','unit/test_random_input_state.py']),
 'cleanup':(['simulation/cleanup.py','simulation/admission.py'],['unit/test_step7.py','unit/test_input_contracts.py']),
 'replay':(['replay/loader.py','replay/spec.py','replay/source.py','replay/engine.py','replay/audit.py'],['unit/test_replay.py','unit/test_final_contracts.py']),
 'java_export':([],['unit/test_dynamic_export.py']),
 'projection':(['replay/export.py','instances/fixed.py'],['unit/test_replay.py','unit/test_step7.py']),
 'config':(['experiment_config.py','instances/fixed.py'],['unit/test_experiment_config.py','unit/test_input.py','unit/test_step7.py']),
 'api':(['__init__.py','simulation/context.py','replay/engine.py','experiments/runner.py'],['unit/test_dynamic_context.py','unit/test_replay.py','unit/test_step7.py','unit/test_final_contracts.py']),
 'cli':(['cli.py','io.py','simulation/admission.py'],['unit/test_step7.py','unit/test_final_contracts.py','integration/test_runs.py']),
 'experiments':(['experiments/runner.py','replay/export_input.py'],['unit/test_step7.py','unit/test_final_contracts.py']),
 'comparison':(['validation/dynamic_compare.py','validation/trace_compare.py'],['unit/test_trace_compare.py','unit/test_final_contracts.py','unit/test_replay.py']),
 'differences':(['replay/engine.py','simulation/context.py','model/execution.py','experiments/runner.py'],['unit/test_execution_precision.py','unit/test_dynamic_context.py','unit/test_step7.py'])}


def inventory():
    rows=[]
    for clause,alias,validation,obligations in GROUPS:
        code,tests=ALIASES[alias]
        for obligation in obligations:
            rows.append(dict(id=f'C{len(rows)+1:03d}',clause=clause,requirement=obligation,
                implementation=['src/fogsim/'+p for p in code],tests=['tests/'+p for p in tests],validation=validation))
    for row in rows:
        if row['clause']=='15.3':row['implementation']=['tools/java_dynamic_support.py','tools/java/step4/fogsim/adapter/DynamicCapture.java','tools/export_java_dynamic.py']
    return rows


def audit(junit):
    cases=list(ET.parse(junit).iter('testcase'))
    results=[]
    for row in inventory():
        modules=[Path(t).with_suffix('').as_posix().replace('/','.') for t in row['tests']]
        evidence=[c for c in cases if any(c.get('classname')==m or c.get('classname','').startswith(m+'.') for m in modules)]
        missing_modules=[m for m in modules if not any(c.get('classname')==m or c.get('classname','').startswith(m+'.') for c in cases)]
        invalid=[c for c in evidence if any(c.find(k) is not None for k in ('failure','error','skipped'))]
        missing=[p for p in row['implementation']+row['tests'] if not (ROOT/p).is_file()]
        results.append(row | dict(status='VERIFIED' if evidence and not invalid and not missing and not missing_modules else 'UNRESOLVED',
            executed_test_cases=len(evidence),missing_paths=missing,missing_test_modules=missing_modules,failed_or_skipped_cases=len(invalid)))
    return dict(format='fogsim.contract-audit',schema_version=1,version='0.3.0',
        design='references/design/FROZEN-0.3.0-BASELINE.md',
        design_sha256=hashlib.sha256((ROOT/'references/design/FROZEN-0.3.0-BASELINE.md').read_bytes()).hexdigest(),
        scope='source-reviewed atomic obligations with current executed test associations; cross-language gates are separately required by final acceptance',
        contracts=results,unresolved=[r['id'] for r in results if r['status']!='VERIFIED'],
        declarative_sections={'2':'historical evidence snapshot; current evidence supersedes progress only',
            '3':'frozen decisions D01-D19 applied; D20 paper errata/formal experiment parameters deferred by design',
            '22':'source provenance, checked separately against delivered baseline',
            '23':'user freeze confirmation supersedes historical draft/review labels'},
        outside_scope=['GP/ten features/evolution/training','paper-scale result reproduction and D20 experimental parameters',
            'network queues/preemption/failures/retries/dynamic resource membership','full DAX XSD compliance',
            'arbitrary-input Java equivalence','two optional native large V19 fixed projections (not a frozen minimum-case gate)'])


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--junit',type=Path,default=ROOT/'outputs/pytest-results.xml');p.add_argument('--output',type=Path,default=ROOT/'outputs/final/contracts-audit.json')
    args=p.parse_args();result=audit(args.junit);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(contracts=len(result['contracts']),unresolved=result['unresolved'])))
    raise SystemExit(1 if result['unresolved'] else 0)
