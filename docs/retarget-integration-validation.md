# 重定向父包接入验证

2026-11-10，Max 工具集 0.0.6。

- 父包统一九项工具入口，retarget 运行文件及图标共12项，附来源和接口文档；不包含独立商店标识。
- tests/host/retarget_entry.py 在独立隐藏 Max 2026 worker108780 验证源码与精确 ZIP 两个根目录：LX_Retarget.ms、桥接 retarget 调用、重复打开同窗口和 Session、Max 父窗口均通过。污染共享 __file__ 后仍按执行代码路径定位。启动器退出0。
- 父37项自动测试、局部14项启动路由测试、阻断xml导入的九项面板构造和精确ZIP资源校验通过。业务负责人另提供137项算法/会话/UI回放，原算法来源见 retarget/SOURCE.json。
- 便携环境真实provider与独立Max三入口验证见 portable-sessions.md。
- 以上为源码/后台宿主/离屏面板证据，不代表用户当前客户端安装或屏幕验收。
