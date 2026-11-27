# S9-B04 最终验收矩阵

全部必需范围通过。当前检查与继承证据分别列出；继承不是本批重跑。历史闭环合计840条（上界848），B04不重复计数。

| 门禁 | 范围 | 当前B04检查 | 已验收继承 |
| --- | --- | --- | --- |
| S01 PASS | configuration, plans, split, signed64 and seed rotation | tests/training/test_b01.py | B01 acceptance.json |
| S02 PASS | DEAP/B08 ordered identities, Java grow, full, node roles and clone isolation | tests/training/test_b02.py, tests/training/test_b03.py | B02, B03 acceptance.json |
| S03 PASS | D03 full-plan equal-run mean and denominators | tests/training/test_b01.py | B01 acceptance.json |
| S04 PASS | domain continuation versus program/input/interruption failures | tests/training/test_b01.py, tests/training/test_b02.py | B01, B02 acceptance.json |
| S05 PASS | NaN/infinity/signed-zero rule score and identity compatibility | tests/training/test_b01.py, tests/training/test_b02.py, tests/training/test_b03.py | B01, B02, B03 acceptance.json |
| S06 PASS | fresh context/objects/queue/B order isolation | tests/training/test_b01.py | B01 acceptance.json |
| S07 PASS | evolution versus simulator/caller RNG isolation | tests/training/test_b01.py, tests/training/test_b02.py | B01, B02 acceptance.json |
| S08 PASS | plan rotation, elite/copy re-evaluation, actual counts, final-generation stop | tests/training/test_b02.py, tests/training/test_b03.py | B02, B03 acceptance.json |
| S09 PASS | single routing/explicit FCFS real decisions, controlled operators and full closure | tests/training/test_b02.py | B02 acceptance.json |
| S10 PASS | dual roles real decisions, four branches/tail/retries/source and clones | tests/training/test_b03.py | B03 acceptance.json |
| S11 PASS | executed independent J01-J06 local Java cases and lifecycle; original evidence retained | 影响审计；原算法未改 | B01, B02, B03 acceptance.json |
| S12 PASS | dedup/all occurrences, fixed validation, pre-test freeze and no candidate switching | tests/training/test_b02.py, tests/training/test_b03.py | B02, B03 acceptance.json |
| S13 PASS | single and dual two seeds plus complete same-config repeats; semantic comparison | 影响审计；原算法未改 | B02, B03 acceptance.json |
| S14 PASS | height/nodes/mutation/init/event/wallclock/EOF-exit evidence | tests/training/test_b01.py, tests/training/test_b02.py, tests/training/test_b03.py, tests/training/test_b04.py | B01, B02, B03 acceptance.json |
| S15 PASS | CLI/API/protocols/source/lineage/independent freeze loading and output protection | tests/training/test_b04.py | B01, B02, B03 acceptance.json |
| S16 PASS | final combined legacy/training regression, DEAP-free paths and pinned dependencies | tests | B01, B02, B03 acceptance.json |
| S17 PASS | editable large templates preflight, budget/retention/versions, default validate entry and small explicit runs | tests/training/test_b04.py | 无 acceptance.json |

当前JUnit：outputs/step9/B04/unit-final.xml（147）和regression.xml（5956），均零失败/错误/跳过。
149条旧合同关联审计、828份协议及696个文件引用、源码/旧证据保留、DEAP缺席、wheel及规则独立加载详见outputs/step9/B04/acceptance.json。

S11原证据：outputs/step9/B01/lifecycle-final、B02/java-final、B03/java-final；S13原证据：B02/single-first与single-repeat、B03/dual-first与dual-repeat及各自reproducibility.json。

S17新证据：preflight-large-single/dual；cases-final/test_launcher*及regression-cases同类目录。未实际执行大模板。

未执行/不纳入必需范围：论文规模/数值复现、旧两个可选大型native固定投影；并行/任意恢复/数值ERC未实现。完整交付需全部四个分包，JDK17不随包。
