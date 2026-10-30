# 绑定蒙皮工作台验证记录

日期：2026-10-30。宿主：本机 3ds Max 2026.3，工具架 native API 1。

## 已执行

- `build.ps1`：C# WinExe 编译及全部资源 SHA256 刷新通过。
- `python -m unittest discover -s tests -v`：12 项通过，覆盖权重不变量、镜像/距离拒绝、锁定、面板不自动启动进程、切换实例时丢弃旧回执。
- `tests/host/run_in_max.py`：在独立测试 Max、生成的几何和 Bones 上执行，报告 ok=true。测试前重置专用测试场景，不应在用户工作场景运行。
- `tests/native_live.py`：工具架真实 NativePanelHandle 加载；由提供器启动 Max，面板发 scene.inspect / bone.create，再读回并渲染。
- `tests/provider_live.py`：非管理实例拒绝、过期场景令牌拒绝、尚未开始的命令成功取消。
- LX 工具 v2 校验器：20 项声明资源通过。
- `scripts/package_release.py` 与 `tests/package_smoke.py`：ZIP 精确文件集合、SHA256、解压包实际工具架 RepositoryWorkspace 加载、5 个嵌入页签、无自动进程、重复 shutdown 均通过。

## 真实宿主通过的检查

- bone.create
- undo create
- rollback after mutation
- scene.inspect
- bind.create
- skin.inspect
- weights.edit
- profile.save
- weights.mirror
- pose.capture
- pose.restore
- snapshot.create
- snapshot.restore
- weights.export
- weights.import
- skin.check
- vertices.select
- weights.transfer
- bind.unbind
- snapshot.list
- deformed mesh snapshot restore positions
- morph.add
- morph.inspect
- morph.value
- morph.reset
- Morpher inserted below Skin
- bone.rename
- bone.parent
- bind.add
- bind.remove
- influence removal preserves remaining node identities
- stale scene rejected

权重结果不只检查接口返回值：写入后 Invalidate + completeRedraw 再读回验证；解除绑定后重建快照，比较已变形顶点位置；异常创建对象测试验证失败后没有残留。Morpher 堆栈测试验证 Skin 在上、Morpher 在下。

## 未完成或不声称已验证

- 正式已安装客户端的升级仍需人工验收。打包版源码通过真实加载器和工作区测试，不等同于发布安装验收；本次发布不覆盖本地安装收据。
- 用户生产角色、超大网格性能、所有 Max 版本、Biped/CAT 专用控制器、各种第三方修改器组合。
- 自动 IK/FK、自动面部绑定、分层权重和运行中取消不属于本次实现。

## 人工验收

通过正常开发商店流程安装本次源码后，从工具面板打开 Max，加载一个角色副本：读取场景与 Skin，选择少量顶点测试增减/平滑并撤销，再检查左右配对、表情通道和权重快照。请重点反馈布局、命名习惯、角色映射需要的预设以及生产模型的兼容问题。

## v0.0.2 发布检查

用户于 2026-10-30 明确授权发布新版 Release。发布前重新编译、执行 12 项单元测试、协议和解压包工作区加载检查。宿主实测沿用上述同一功能实现的记录，不将发布校验声称为重新运行生产角色。通过标签触发 GitHub Actions 打包提交文件，不在 Actions 重编译；发布后核对附件摘要。

## 发布后开发修改：Max 内工作台和六款工具美化

用户纠正承载位置后，绑定蒙皮界面迁入 Max 的 PySide6 可停靠面板。LXTool 仅保留实例管理和打开入口，独立运行根目录 LX_RigSkin.ms 也可以打开工作台。此修改尚未发布，以上 v0.0.2 发布记录属于旧版。

在独立测试 Max 2026.3 场景中，tests/host/max_ui_test.py 验证窗口归属、重复打开单实例、读取场景、通过 UI 创建骨骼、Skin 绑定、赋权并读回、关闭重开，以及新建场景后旧目标失效，全部通过。

tests/host/legacy_ui_test.py 在真实 Max 中逐个打开动画烘焙、保持位移建立父子、材质 ID 拆分、清理根骨骼、自定义公式关键帧、PMX 导入，验证用户图片、主操作样式、重复打开和关闭，全部通过；三个动画区间按钮通过 PerformClick 验证事件仍有效。六款窗口已截图检查布局。修正了 PMX 原有编码器初始化括号错误，否则该脚本无法打开。

此次六款工具只验证界面和上述按钮事件，没有据此声称已全面回归各款工具对生产模型的处理结果。12 项自动测试及开发 ZIP 的全部资源摘要、真实工具架 RepositoryWorkspace 加载、无自动启动副作用和重复关闭检查通过。安装版仍未覆盖，生产角色仍待用户验收。

完整启动链路补验：tests/native_live.py 启动专用 Max（PID 7712），连接后通过真实工具架加载器发送 rig-workbench；刷新开发资源摘要后复用该测试实例，收到 LX_RigSkin 已打开回执。最终重新构建并打包，精确 ZIP 校验及工作区加载通过。

## 2026-10-31 七阶段工作流

22 项 unittest 通过（包含人体命名层级、线段距离、隔离体积距离传播、逐点 N 影响、多骨骼比例/锁定、滚轮禁止改值、白底下拉调色板）。真实 Max 2026.3 的 workflow_regression.py 通过：生成 94 根 Bone，长度冻结标志全部关闭；子骨骼、端点对齐、IK 定型、控制器、分类显隐、平均点、环选、线段/体素 Skin 赋权、选择层转 Skin、隐藏恢复、多骨骼权重、笔刷撤销/重做/取消并逐点读回。

原生交互补验：在前视图实际拖出高度，成功生成 20 根不含手指脚趾的人体骨架；通过真实鼠标拖动 Painter 视口，4 个顶点权重改变，笔划正常结束。作用范围弹出列表截图确认白底黑字、选中项深绿底白字。开发包包含 37 项清单资源，真实 RepositoryWorkspace 解压加载和全部摘要检查通过。

测试使用独立临时场景，不代表已验证用户生产模型、超大网格性能或所有版本 Max；笔刷手感、人体比例和生产角色仍需用户反馈。体素实现为 CPU 近似内部距离传播，具体输入限制见 rig-workflow.md。

旧版完整宿主回归 run_in_max.py 再次通过，包含权重镜像/传递/交换、快照重建、Morpher、骨骼层级和过期场景拒绝。

2026-10-31 骨架修正：独立 Max 中创建 Biped 取样比例及肩、肘位置，普通 Bone 的实际起终点与模板逐根核对通过。symmetry_test.py 验证双向位置/朝向/长度对称、选中子树隔离、撤销重做、自动同步不覆盖撤销、定型后拒绝修改、首次悬浮及重复呼出保持手动停靠，全部通过。23 项 unittest 通过；前视图肩部及新面板截图已检查。

追加验收：BodyCenter 为 Point，Pelvis 为宽骨盆 Bone；旋转骨盆时双腿随动而 Spine 保持，世界 Root 同时携带上下身。workspace_test.py 验证所有预期连续关节无断点、类别包围框不影响外部对象、Nitrous 三类显示状态读回、各步骤保持模型 / Skin 目标、中文层级、1450 宽屏双列与 820 窄窗重排 / 调高、真实按钮队列执行，以及完整 .max 副本写盘，全部通过。27 项 unittest 通过；原完整 workflow_regression.py 再次通过。
