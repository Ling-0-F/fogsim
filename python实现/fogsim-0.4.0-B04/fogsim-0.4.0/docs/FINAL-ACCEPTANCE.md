# fogsim 0.3.0 最终验收

日期：2026-11-05（America/Los_Angeles）。直接基线为本对话第7步ZIP，SHA-256 `ab8cafeadc2872c48b39457c9a3e08d472a04279c166101267f5dee9f3ce670d`。冻结原文复制到`references/design/FROZEN-0.3.0-BASELINE.md`，不更改其内容或已确认语义。原ZIP保留，在独立副本实现。

## 本轮审计与修正

1. 完成149项源码审查义务，逐条关联实现、测试及V01～V22，见CONTRACT-AUDIT.md和CONTRACT-INVENTORY.json。最终机器核对状态在outputs/final/contracts-audit.json，不用单一“测试总数”替代条款证据。
2. 补正式AdmissionResult及AdmissionService.admit，动态真实调用链已使用；旧attempt返回方式保留兼容。成功的workflow是本轮规范对象，拒绝不占ID/登记/发事件，生成异常不伪装拒绝。
3. 仅给新的Java观察overlay追加beforeEvent观察，以及基于真实事件身份的owner/staging记录和错误边界；原Java方法字节、采样、比较、队列及路由不改。plain/baseline/minimal/full验证观察无干扰；额外元数据单列，不从旧producer名字猜staging。历史参考完全保留。
4. 动态比较器按每个实际事件的头→前态→交错动作→后态→错误定位首差，再比较最终事实/统计/指标；补故障注入验证早期前态不会被后续事件头差异遮蔽。非法参考结构统一InputError。
5. 进度回调取得独立结果快照，防止观察者修改前一checkpoint污染最终结果。存在的rng_seed_decimal必须为精确十进制字符串，不能用null冒充。
6. 直接simulate_replay支持显式可选参考的运行后比较，并统一配置适配器；错误路径类型明确InputError，重放来源仍不读取参考。
7. 包名/pyproject/公开版本/CLI/新Python输入provenance统一0.3.0；schema-v1和旧固定公共接口保留。

## 真实执行与证据

最终是否通过、测试数量/零skip、每个V01～V22状态、原始结果路径、分类计数及源文件快照在`outputs/final/acceptance.json`。当前pytest完整结果为`outputs/pytest-results.xml`和`outputs/pytest-console.txt`；V01构建/扫查/组件oracle和精度边界在`outputs/parity/`、`outputs/v2/`、`outputs/java_oracle/`。

```bash
PYTHONPATH=../../test-deps:src python -m pytest -q tests/unit/test_final_contracts.py tests/unit/test_replay.py --junitxml=outputs/final/contracts-final.xml
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server PYTHONPATH=src python tools/check_step2.py --output outputs/final/step2
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server PYTHONPATH=src python tools/check_step3.py --output outputs/final/step3
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server PYTHONPATH=src python tools/run_final_acceptance.py --phase dynamic --output outputs/final/current
PYTHONPATH=src python tools/run_final_acceptance.py --phase performance
LD_LIBRARY_PATH=/usr/lib/jvm/java-17-openjdk-amd64/lib:/usr/lib/jvm/java-17-openjdk-amd64/lib/server PYTHONPATH=../../test-deps:src python tools/validate.py
PYTHONPATH=src python tools/assemble_acceptance.py
python tools/build_release.py --output /path/to/fogsim-0.3.0.zip
```

本机CPython3.12.14、pytest9.2.0、Ubuntu OpenJDK17.0.20+8，compiler为已有jdk.compiler模块。当前环境需显式LD_LIBRARY_PATH；常规JDK17环境可直接运行，测试依赖安装在工程外。构建清单保留实际命令、返回码、JDK/模块/原源码/JAR/适配器指纹、stdout/stderr。

- V02/V04：20标准拓扑任务/父子顺序对照，两语言各14角色×3 seed×100000分布验收；固定阈值不调宽。
- V06～V08：原Java构造/生成探针及20标准模板生成建图断言；脚本业务值不冒充相同RNG算法。
- V09～V18：当前单元/集成断言、原Java50项生命周期/保护探针、新导出7例完整输入及严格逐事件参考。5例正常一致、2例预期失败差异；两种分类不混合。捕获中断、错误位置、记录用尽/换规则覆盖不足分别保存。
- V19：六个非空投影、十条FCFS/fixed_resource路径，两侧固定入口同一投影到完成；空接纳集为旧非空格式表示边界。比较固定模型/轨迹/结果，不混比原动态指标。
- V20：原子/幂等/归档和RNG不变，实际启用清理的严格Java diamond重放；准备阶段历史测量和完整小型运行新测量分别报告。
- V21/V22：新旧CLI、显式重复模式、流/B延续、失败分母、未知异常、回调快照、精确seed和冻结数值边界。

性能工具开发初次遗漏了policy覆盖，使两条lane都retain；该轮结果明确标无效，保存于outputs/final/performance-initial-invalid.json，不用于收益结论。最终测量强制检查实际启用的策略和非零释放计数。测试/验收未修改旧调度预期或历史Java参考。

## 接受范围与保留事项

范围内每项契约及V01～V22门禁均须有当前证据才能由assemble_acceptance标通过；build_release还核对验证时的源码快照，缺项/skip/源码改动不发布成功。正常通过、预期差异、覆盖不足、失败、未执行、基础设施错误及无参考分别保留。

两个可选native_*大型固定投影并非冻结最低样例门禁，继续标NOT_EXECUTED，不算通过。小型性能测量不外推论文规模，也不要求必须获得加速。GP/十特征/训练/论文实验、D20正式实验参数解释和新增网络模型在原设计非目标/后续范围。未改变冻结语义，不承诺任意有限输入与Java等价。完整已确认差异列表进入最终acceptance的known_differences。

本轮独立补丁、全包校验和最终ZIP解压后的Java重新编译/固定对照、新CLI链路、版本与导入隔离检查另随交付验证报告保存。报告绑定最终ZIP的SHA-256，避免自引用哈希。
