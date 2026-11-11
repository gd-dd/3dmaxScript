# 六原脚本窗口布局整理

2026-11-12，ALL-UI-20261112。

六窗口保留原业务事件、输入校验及撤销边界，按目标对象、必要参数、主动作排序。保留用户图片，统一浅底绿色标题/主按钮；简单工具不额外拆分步骤。动画通道和根骨骼轴向并排，帧数值使用独立文字标签，避免原生 spinner 的长 caption 越界。源对象提示允许两行显示，PMX 文件路径占满一行、信息区加高。

公式关键帧主窗保留输入、变量简要说明和执行；低频运算/函数/示例通过“公式参考与示例”在同一窗口展开。默认高度290、展开434逻辑像素，展开/收起保留输入和主动作位置。其余窗口固定宽420，高346–430逻辑像素，原生Max控件仍使用宿主控件样式。

## 证据与边界

`tests/host/run_legacy_ui_batch.py 3` 的独立隐藏 Max worker79096、launcher74732（2026-11-12 03:31:15启动）正常exit0。六窗口初始化文字/图片、布局边界、公式展开/收起输入保留通过；原始六款业务harness仅重定向产物目录后运行，6/6功能/撤销/主要异常路径通过。证据位于 `E:/project/LXTools/acceptance/legacy-ui-2026-11-12/3-ui-report.json`、`3-report.json` 和 `3-processes.json`。native PrintWindow图为隐藏窗口自身绘制，不是屏幕截图，不涉及用户Max。

第1、2轮失败记录保留：新增.NET事件注册与Max的dotNetControl不兼容，导致open初始化提前中止；已移除该非必要hook，使用Label原生AutoEllipsis。第3轮修复后业务通过，但目视发现部分帧数值的旧caption仍残留；现已统一改为.NET文字+无caption数值框。该最后排版调整待父包最终九入口同进程gate再次截图，不把第3轮图当作最终排版通过。

## 父包最终UI复验调用

在专用隐藏Max主线程中执行（不会启动新Max，不执行场景业务）：

```python
import runpy
result = runpy.run_path(
    'E:/project/LXTools/3dmaxScript/tests/host/legacy_ui_acceptance.py',
    init_globals={
        'LEGACY_UI_ROOT': actual_installed_or_unpacked_parent_root,
        'LEGACY_UI_OUT': isolated_e_drive_output_directory,
        'LEGACY_UI_ONLY': True,
    },
)
assert result['report']['ok'], result['report']
```

夹具只在内存替换根路径解析与窗口位置到离屏坐标，逐个打开/渲染/关闭六窗口。产品代码不写入测试适配。输出ui-report.json及七张PNG（六默认态+公式展开态），保留实际125%环境的像素尺寸；不据此宣称完整100/125/150%矩阵或用户生产场景/当前窗口验收。

最终父包gate前进一步压缩：根骨骼窗口430、公式默认290/展开434逻辑像素，创建高度与open后的高度一致。150%下分别645/651物理像素，比此前减少87/54物理像素，标题栏/任务栏仍以最终宿主环境验收；没有宣称MAXScript自动限高或自动滚动。该最后尺寸调整同样等待父包gate渲染，geometry门槛为两者<=440。
