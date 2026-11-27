# JDK 17 版本要求：0.2.1 修正

用户希望限定 JDK 主版本 17，允许 17.x 更新。此前将验收参考环境 Temurin 17.0.16+8 额外变成强制运行要求，属于过度收紧，现已撤回。

| 检查内容 | 0.2.1 行为 |
| --- | --- |
| java.specification.version | 必须为 17；拒绝 8、11、18、21 等 |
| 更新号及 build | 记录实际值；17.0.20.1+1 等允许使用 |
| 厂商 | 记录实际值；不限定 Eclipse Adoptium |
| PriorityQueue 源码 | 可取得时记录 SHA；不同、缺失或不可读不直接阻止运行测试，并记录状态 |
| javac | Java 适配器仍需完整 JDK 中的编译器 |
| 组件 oracle 与固定输入轨迹 | 仍需真实运行并通过 |
| 缺 JDK 导致 skip | 正式 validate/release 仍不允许据此宣称验收通过 |

本次完整回归在 Temurin 17.0.16+8 上执行。针对用户 17.0.20.1+1 的单元测试证明版本门禁接受该元数据；不等于已经在其 Windows 环境运行全部 Java 轨迹。

用户无需为运行本项目降级。建议在 PowerShell 中、解压后的项目根目录执行：

```powershell
java -version
javac -version
.\.venv\Scripts\python.exe tools/validate.py
```

前两个命令应显示 17 系列；若需要显式选择安装路径，可设置当前终端的 `FOGSIM_JAVA` 为对应 JDK 的 `bin\java.exe`。不要求修改系统全局 Java 配置。

运行日志、构建清单和对照报告会记录本次实际环境。若某个 17 更新版本发生实际行为差异，对照器将报告首差；不会仅因更新号不同拒绝，也不会因为主版本相同自动判为行为一致。
