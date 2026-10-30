# 绑定蒙皮工作台开发接口

当前实现是 Max 内显示 UI 并执行场景命令的基础工作流；LXTool 只提供打开入口。不是独立 DCC，也不依赖外部开源 rig 运行时。

## 分层

| 模块 | 职责 |
| --- | --- |
| `rig/workbench.py` | 工作台 QWidget 内容、目标和作用范围、操作结果，不导入 pymxs |
| `rig/max_ui.py` | Max 主窗口持有的 QDockWidget、本地 QTimer 命令队列、场景变更监测、关闭清理 |
| `LX_RigSkin.ms` / `bridge/open_rig.py` | 独立 Max 启动入口，不需要工具架或提供器 |
| `ui/panel.py` / `ui/transport.py` | 生命周期、Max 实例选择、请求关联、隐藏 stdio 后台 |
| `src/SessionProvider.cs` | 只管理工具启动的 PID+启动时间，摘要校验、原子请求与结果队列、超时及开始前取消 |
| `bridge/LXMaxBridge.ms` | Max 主线程定时收取固定命令、场景变更令牌、心跳 |
| `bridge/rig_entry.py` | 旧版本远程命令兼容入口；当前 UI 不走此通道 |
| `rig/max_host.py` | 注册命令、宿主对象解析、撤销事务、Skin/Morpher 读写、配置与快照 |
| `rig/weights.py` | 无宿主依赖的稀疏权重、邻接平滑、KD-tree 最近点、镜像与诊断 |

## 请求

Max 面板通过 `RigDock.rig_command` 在当前进程中排队 request，再由 Qt 主循环调用 dispatch。数据结构沿用如下格式：

```json
{"action":"weights.edit","scene":"scene-token","params":{"mesh":"1234","skin":0,"scope":"selected","mode":"normalize","locked":[]}}
```

模型与骨骼使用 `getHandleByAnim` / `getAnimByHandle`，不按显示名称选择目标。Skin 是从 0 开始的修改器堆栈索引；影响骨骼 ID 是 Skin 自己的索引，不能当场景节点 ID。配置同时保存影响节点句柄，影响列表变化后重映射左右配对与锁定。跨场景导入仅接受唯一名称的一一对应映射。

每个 Max 进程持有独立面板。重复打开聚焦现有窗口；关闭时清空尚未执行队列并停止监测。场景改变时作废旧目标和回调。旧 stdio `op=rig` / `results` 协议保留兼容，但当前工作台不会从 LXTool 远程编辑场景。

## 新增功能

1. 纯算法放入 `rig/`，输入输出普通 Python 数据，先写边界和不变量测试。
2. 在宿主模块用 `@command('domain.operation', True)` 注册写命令，读取用 `False`。参数检查应在第一次写入之前完成；函数返回可序列化字典。
3. 所有场景写入都走 dispatch。它校验场景令牌并使用 `pymxs.undo(True)`；该上下文会吞掉异常，所以实现显式保留异常并在回滚后重新抛出。不可直接调用 `theHold.Accept` 嵌套覆盖外部事务。
4. 权重操作复用 `skin_data`、`selected_vertices`、`backup` 和 `write_rows`。写后必须使 Skin 求值并读回，否则 Max 会返回缓存中的零权重。
5. UI 使用 `call` / `mutate` 发结构化数据。不得拼接用户输入成 MAXScript/Python 源码；不得在 panel 构造时启动 Max。
6. 新模块加入 manifest.files，再运行 build.ps1 刷新摘要；宿主重启后加载新包。开发中改源码不会热更新已导入的宿主模块。

## 数据和性能边界

JSON 权重格式 schema=1，含场景令牌、节点、影响节点表、稀疏权重、三角拓扑签名、当前局部坐标、三角面；单 Skin 还含绑定矩阵。坐标数值沿用当前 Max 场景单位，不自动换算。JSON 导入上限 128 MiB。

当前 UI、纯计算和宿主写入都在 Max 主线程；大模型执行期间 Max 与工具面板会忙碌，没有运行中强制中断和百分比进度。后续加后台算法时必须先提取不可变快照，回主线程再次校验令牌、拓扑和影响表，不能在线程中直接访问 pymxs。分层权重、BBW/体素求解和 GPU 后端尚未实现；不为未来功能显示空按钮。

快照不是场景备份。它不保留整个 Skin 的参数/动画/包络/DQ，不跨场景令牌自动恢复，不重建多个已删除 Skin。姿态记录仅保存当前世界矩阵，不重新定义 Skin 绑定姿态。

## 验证

`python -m unittest discover -s tests -v` 执行纯算法和面板状态测试。`tests/host/run_in_max.py` 只能在新建的专用测试 Max 中执行，会重置测试场景；它通过 QTimer 返回宿主主循环再运行。

`tests/native_live.py` 使用真实工具架 NativePanelHandle 和后台启动专用 Max，验证连接与打开 Max 内面板的回执；`--reuse` 仅重用工具已经管理的测试实例。它不会写安装收据。`tests/package_smoke.py` 检查构建 ZIP 并用工具架工作区加载解压后的精确资源。

`tests/host/max_ui_test.py` 检查真实 Max 内停靠、单实例、创建骨骼、Skin 绑定、权重读回、关闭重开和场景切换。`tests/host/legacy_ui_test.py` 检查六款既有工具的图片、按钮、重复打开和关闭。两个脚本均只在独立测试 Max 内运行。
