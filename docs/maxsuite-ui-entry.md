# 父包九个 Max 内入口的 UI 集成门禁

`tests/host/run_maxsuite_ui_entry.py` 只用于负责人排期后的独立隐藏 Max 验收。源码和精确 ZIP 解包目录必须各运行一次、顺序执行；每次使用新进程与唯一输出目录，避免绑定蒙皮的跨目录混载。

```powershell
python -B tests/host/run_maxsuite_ui_entry.py source-ui-1 E:/project/LXTools/3dmaxScript
python -B tests/host/run_maxsuite_ui_entry.py package-ui-1 <完整父包解压目录>
```

运行前先由父负责人确认其他 Max 批处理已经结束、三个子模块源码冻结，并完成父清单摘要更新。脚本会校验全部已声明资源；不会为通过测试临时修改清单。源码验收不等于公开发行验收。

每次只启动并等待自己的 `3dsmaxbatch.exe`，不枚举或终止现有 Max。配置、TEMP、Max 用户设置、日志与输出位于 `E:/project/LXTools/acceptance/maxsuite-ui-2026-11-12/host-runs/<唯一运行名>`。运行名已存在时拒绝启动，不复用历史通过报告。

`launch.json` 用新建 `Popen` 自身句柄的 `GetProcessTimes` 记录启动器 PID 与 UTC 出生时间/FILETIME；不枚举其他进程。宿主 `report.json` 在入口检查前写出实际 Max 工作进程 PID、EXE、`StartTime.ToUniversalTime().ToString('o')` 及 FILETIME，供排期方精确核对进程身份。

覆盖范围：

- 先在同一 Max 中通过 `legacy_ui_acceptance.py` 的 `LEGACY_UI_ONLY` 模式顺序打开、渲染及关闭六个原 MAXScript 窗口；不重置场景、不再启动宿主或重跑其业务阶段。原生初始化、主按钮、用户图片、控件边界及公式参考展开/收起保留输入均须通过，输出七张 PrintWindow 图。仅适配源根路径和窗口离屏坐标，不改业务代码。
- 完整父包的 `LX_RigSkin.ms`、`LX_Ribbon.ms`、`LX_Retarget.ms` 和对应桥接路由；污染共享 `__file__` 后仍定位到正确包根。
- 绑定蒙皮的 Max 所属浮动 dock、真实异步场景读取、重复呼出复用和关闭重开。
- 飘带在合成普通 Bone 链上读取、重复呼出保留同窗/骨链；不执行烘焙。
- 重定向在合成 Point 节点上读取源/目标、重复呼出保留 Session、关闭恢复实际显隐。
- 三类真实 Max 所属窗口的 Qt 隐藏渲染截图；工具原生显示被抑制，截图不是桌面截图，不声称用户当前窗口目测或手感验收。
- 临时节点删除、入口前后场景状态与声明资源保持。

主报告应有九个入口检查：六项原生窗口和三项 L3 入口；同时记录原生检查报告 PID 必须等于当前测试进程 PID。每次正常运行共输出七张原生窗口图和六张 Qt 隐藏窗口图。

这组门禁不代替三个子工具各自的布局尺寸/交互测试、算法/撤销测试、冻结工具架、公开安装或用户生产角色验收。测试报告和截图属于验收产物，不放进父工具运行包。
