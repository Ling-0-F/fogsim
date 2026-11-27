# B04 命令与证据定位

outputs/step9/B04/commands记录完整argv/cwd、有限环境、耗时、退出、原stdout/stderr。训练专项在当前工程执行；全量联合回归在独立恢复副本执行，当前源码/测试/配置一致，审计工具的后续两项细化见regression-code-binding.json。旧回归生成的262份结果另存legacy-current，不覆盖历史。

执行顺序：恢复3373来源成员；按B02锁安装训练依赖；本批测试工具精确wheel锁；组件受控失败与修复；冻结；unit-final；独立副本regression；两大模板仅preflight；源码与wheel独立评估、无DEAP路径；协议/引用审计、149项旧合同关联、源码保留与最终验收；分包与独立解压/全清单/离线安装/冻结规则评估。

全部原始失败记录保留。delivery-dev为相对路径报告错误前已完成的8条评估；delivery-audit-before-origin-policy为第二轮审计false及原日志；delivery-audit-final用--audit-existing仅重审当前已有输出。两次pytest缺依赖是收集前基础设施错误。大模板始终未执行。

来源B03与前批结论已验收，不重新运行原包确认旧成绩。JDK获取URL、摘要和环境信息在preparation/runtime.json、commands/java-environment.*及development/S9-B02/dependency-lock.json。完整独立解压命令与新增4条评估记录在外部verification.json；其原执行文件随交付复核附件提供。
