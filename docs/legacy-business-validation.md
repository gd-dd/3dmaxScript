# 六款旧工具核心宿主验收（2026-11-10）

计划及所有逐轮报告：E:/project/LXTools/acceptance/legacy-six-2026-11-10。最终9-report.json：worker PID106612，6/6通过，batch正常退出。tests/host/run_legacy_batch.py 创建独立E盘profile与TEMP，仅自己的启动进程，无全局进程清理；tests/host/legacy_business.py 是可复用测试入口。

## 测试边界
测试只在独立3dsmaxbatch中构造合成模型/动画。读取实际业务源码，presentation适配仅固定资源根、messageBox改为记录、rollout窗口位置移出屏幕。公式仅将trackviews.current替换为合成选轨适配器，实际float控制器、选中key及原业务事件不替换。它证明计算和数据恢复，不证明鼠标选轨。最终去掉测试额外undo封装，验证工具自身事务；场景构造在undo off中，且执行前清理测试撤销栈。

- 动画烘焙：0～4帧动画的5个采样值、key增加、撤销；无通道拒绝。
- 父子：两个运动Box逐帧保持世界位置、建立层级、一步撤销恢复旧父；反向帧范围拒绝。
- 材质ID拆分：两面/两个材质生成两个一面对象、材质名与源保留、一步撤销；空源拒绝。
- 根约束：真实Biped的Y运动传递Dummy，X/Z保持原值、撤销；无轴拒绝。
- 公式：原事件修改选中实际float关键帧，v+sin(90)增加1、撤销；非法表达式不改变值。
- PMX：Python struct生成合法PMX2.0，无第三方资产。三点一面、UV、材质、两根骨骼层级和BDEF1/BDEF2/BDEF4权重读回；导入撤销、截断输入拒绝、注入部分构建故障不残留对象。

## 缺陷与修复
父子关系原先在undo块外，移入同一事务。公式原先给MAXScript角度三角函数重复弧度转换，移除转换并添加undo事务。PMX原材质toon字段/骨旗位/显示组等解析顺序错误，索引未区分有符号与顶点无符号；原网格使用不可追加的mesh集合，权重逐骨骼写入会受归一化影响。修正这些路径，批量替换顶点权重，检查面索引，导入失败清理新对象、关闭流、恢复按钮。读取骨尾相对偏移并让骨骼X轴沿骨段。

1～8轮失败/中间报告完整保留：其中部分属于测试夹具问题（未隔离undo、通过普通position读取Biped），其余为真实业务缺陷与修复过程的语法问题。第9轮是最终业务结果，不能将早期失败算成通过。

格式核对参考：[PMX format](https://gist.github.com/Binsk/3bfd792e2dd4aa9cd6bb45dd05c0727e)；撤销适配参考 [Autodesk pymxs introduction](https://help.autodesk.com/cloudhelp/2019/ENU/Max-Python-API/developer/using_pymxs/pymxs_api_introduction.html)。未引入外部实现依赖。

## 未覆盖
商业角色、完整PMX2.1扩展/物理/非顶点变形、所有材质贴图与自定义控制器组合、真实蒙皮视觉效果、当前用户窗口、鼠标交互。绑定蒙皮、飘带沿用各自明确范围的宿主证据，本次未重跑。正式客户端安装与8窗口呼出由上游统一验收。
