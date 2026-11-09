# Max 会话根与便携配置约定

后台优先采用进程 LOCALAPPDATA；必须是有效绝对路径，空值、相对路径、E:relative及根相对路径均拒绝。环境变量缺省时才调用系统 LocalApplicationData。配置查找依次为该根下 LXMaxTools/max-path.txt、LXTool/repository-tools-v2.json、运行实例和安装注册表。显式平台配置优先于猜测其他实例的版本。

## 三种入口

- 工具启动 Max：后台在自己的 LXMaxTools/connections 下生成 wrapper，传给 -U MAXScript。
- 连接已有 Max：面板在同一根下生成 wrapper，用户在明确选择的 Max 中运行；不再复制裸 bridge 文件路径。
- 自动连接：一次安装的 loader 同样包含显式根。APPDATA 必须是绝对路径；便携启动器应同时为 APPDATA/LOCALAPPDATA 提供自己的目录。

wrapper 设置一次性 LXMaxBridgeRequestedUserRoot，然后 fileIn 当前包的 bridge/LXMaxBridge.ms。桥消费并清空变量，不修改 Max 的进程环境。旧心跳计时器停止，新心跳/请求/回执统一在指定根/sessions/PID-startTicks 下。新消息响应的 sessionRoot 字段可用于诊断。

旧裸 bridge 脚本仍可运行，按 Max 出生 LOCALAPPDATA 定位；当 Max 和工具架配置根不同，必须从新面板生成连接脚本重新连接，不能沿用旧目录入口或仅看旧心跳。旧文件不自动搬迁/删除，旧实例不自动切换目标。业务脚本独立入口不依赖会话桥。

## 验证证据

acceptance/maxsuite-portable-2026-11-10/provider-report.json：真实 LXMaxSession.exe 配置读取、启动wrapper、managed记录在E，非法目录拒绝。3dsmax.exe fixture仅记录参数与环境，不冒充真实Max业务。

bridge-report.json：隐藏真实Max worker99464出生LOCALAPPDATA为另一套E目录；launch/attach/auto三种wrapper都定向到工具架E根，真实provider识别ready并发送ribbon，Max执行后得到已打开回执。Max原环境变量未变化。未操作用户当前窗口。

这些记录证明工具自身配置与会话读写路径，不宣称监控了Windows/许可组件的全部系统写入。生产客户端安装与当前用户实例连接由上游单独验收。
