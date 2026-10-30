# Max 工具集开发约定

正式开发仓库：E:/project/LXTools/3dmaxScript，远端 gd-dd/3dmaxScript。
工具架独立仓库：E:/project/LXTools/LXTools。
协议文档在工具架 docs/lx-tool-v2.md、docs/custom-panel-api.md。

- 后续 Max 工具源码修改、测试、构建都在本仓库执行。
- 工具架 runtime/tool-authoring/3dmaxScript 以及 E:/Ruanjian/LXTool 为备份，不再作为 Max 开发入口，不自动删除。
- 用户已授权后续修改验证通过后自动 commit、push 到 GitHub 默认分支，并更新开发客户端的 0.0.0 分支快照；不创建 Release，除非用户另行明确要求。
- 首次正式 GitHub Release 是 0.0.1；旧 1.x 为已停用索引机制下的开发版本。后续版本递增，已发布附件不可覆盖；先编译和刷新摘要再提交打标签。
- 只使用 GitHub Releases，附件名 LXTool-package.zip；不维护 releases.json 或仓库内历史完整包。
- 本仓库 core.autocrlf=false；不要自动转换已发布资源换行，文件 SHA256 必须与 manifest 一致。
- 图标使用用户提供图片；LXTool 只提供实例管理与启动入口；绑定蒙皮业务 UI 位于 Max 内可停靠面板，其他脚本 UI 也位于 Max。工具面板列出所有已打开的 Max，用户明确选择目标；一次安装用户级自动连接组件后，新启动的 Max 自动加载连接。目标退出后不得自动切换到另一个进程，独立脚本可在任意 Max 直接运行。
