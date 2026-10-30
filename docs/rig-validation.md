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
