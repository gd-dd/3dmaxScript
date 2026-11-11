"""Source-native/offscreen Max panel geometry and visual acceptance.

Run directly to render three DPI workers. No user desktop/Max/provider input.
Only the platform shell is real; Max sessions are explicitly synthetic fixtures.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / 'acceptance/maxsuite-ui-2026-11-12'


def run_workers():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for scale in ('1', '1.25', '1.5'):
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR=scale,
                   PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        for key in ('TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA'):
            path = OUT / 'visual-environment' / scale / key
            path.mkdir(parents=True, exist_ok=True)
            env[key] = str(path)
        process = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
                                  '--worker', scale], env=env, cwd=ROOT,
                                 text=True, encoding='utf-8', capture_output=True)
        (OUT / ('dpi-' + scale + '.log')).write_text(process.stdout + process.stderr, 'utf-8')
        if process.returncode:
            raise RuntimeError('DPI worker failed: ' + scale + '\n' + process.stdout + process.stderr)
        results.append(json.loads((OUT / ('dpi-' + scale + '.json')).read_text('utf-8')))
    report = dict(ok=all(r['ok'] for r in results) and len({r['candidatePanelSha256'] for r in results}) == 1, scope='source NativePanelHandle and actual source desktop shell; offscreen synthetic Max sessions',
                  maxOrProviderStarted=False, currentUserWindowVerified=False,
                  frozenClientVerified=False, sizesAreQtLogicalPixels=True,
                  firstPass=dict(visualUsable=False, reason='offscreen font enumeration lacked CJK; tofu screenshots retained',
                                 reportDirectory=str(OUT / 'fontless-first-pass'), screenshots=str(OUT / 'screenshots')),
                  dpiReports=results)
    (OUT / 'panel-layout-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(dict(ok=report['ok'], scales=len(results), report=str(OUT / 'panel-layout-report.json'))))
    if not report['ok']:
        raise AssertionError('Native panel visual/geometry gate failed; see preserved report')


def render_worker(scale):
    from unittest import mock
    import hashlib
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QScrollArea
    from test_max_layout import OUT, ROOT, PANEL_RESOURCES, SESSIONS, select, settle, source_tool, load_readonly_fonts
    from native_panels import NativePanelHandle
    from core import ToolStore
    from desktop import Window
    from theme import STYLE

    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    fonts = load_readonly_fonts(app)
    app.setStyleSheet(STYLE)
    pictures = OUT / 'screenshots-verified'
    pictures.mkdir(parents=True, exist_ok=True)
    candidate_hash = hashlib.sha256((ROOT / 'ui/panel.py').read_bytes()).hexdigest()
    report = dict(scale=scale, ok=True, directPanels=[], desktopPanels=[],
                  sceneFixtures='3 synthetic Max sessions; long scene path; no host connection',
                  providerStarted=False, readOnlyFontSources=fonts, cjkGlyphVerified=True,
                  candidatePanelSha256=candidate_hash)

    def rectangle(widget, ancestor=None):
        p = widget.mapTo(ancestor, QPoint(0, 0)) if ancestor else widget.pos()
        return [p.x(), p.y(), widget.width(), widget.height()]

    def screenshot(widget, name):
        path = pictures / (name + '-dpi-' + scale + '.png')
        assert widget.grab().save(str(path))
        return str(path)

    def geometry(panel):
        scroll = getattr(panel, 'scroll', None)
        if not isinstance(scroll, QScrollArea):
            scroll = panel.findChild(QScrollArea)
        overflow = scroll.widget().width() > scroll.viewport().width() + 1
        buttons = {}
        all_reachable = True
        for key, button in panel.buttons.items():
            scroll.ensureWidgetVisible(button, 0, 4)
            settle()
            rect = button.rect().translated(button.mapTo(scroll.viewport(), QPoint(0, 0)))
            reachable = scroll.viewport().rect().contains(rect)
            all_reachable &= reachable
            buttons[key] = dict(rect=rectangle(button, scroll.widget()), reachable=reachable,
                                enabled=button.isEnabled())
        scroll.verticalScrollBar().setValue(0)
        settle()
        group_labels = []
        no_label_overlap = True
        for group in getattr(panel, 'tool_grids', []):
            if len(group) != 3:
                continue
            _, group_buttons, label = group
            bounds = label.rect().translated(label.mapTo(scroll.widget(), QPoint()))
            collisions = []
            for button in group_buttons:
                button_bounds = button.rect().translated(button.mapTo(scroll.widget(), QPoint()))
                if bounds.intersects(button_bounds):
                    collisions.append(button.text())
            no_label_overlap &= not collisions
            group_labels.append(dict(text=label.text(), rect=rectangle(label, scroll.widget()), collisions=collisions))
        visible_at_top = [key for key, info in buttons.items()
                          if info['rect'][1] >= 0 and info['rect'][1] + info['rect'][3] <= scroll.viewport().height()]
        return dict(panelSize=[panel.width(), panel.height()], scrollViewport=rectangle(scroll.viewport(), panel),
                    contentSize=[scroll.widget().width(), scroll.widget().height()],
                    horizontalOverflow=overflow, horizontalRange=scroll.horizontalScrollBar().maximum(),
                    allNineReachable=all_reachable and len(buttons) == 9,
                    groupLabels=group_labels, noGroupLabelOverlap=no_label_overlap,
                    fullyVisibleAtTop=visible_at_top,
                    selected=panel.active_id, buttons=buttons)

    def prepare(panel):
        panel.apply_response(dict(sessions=SESSIONS))
        select(panel, 'max-one')
        assert panel.process.child is None
        settle()

    # Focused small panel fixtures using the actual native loader.
    for width, height in ((380, 450), (620, 640), (980, 800)):
        parent = QWidget()
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        handle = NativePanelHandle(source_tool(), OUT / 'visual-profile' / scale, parent)
        panel = handle.widget
        layout.addWidget(panel)
        prepare(panel)
        parent.resize(width, height)
        parent.show()
        settle()
        entry = geometry(panel)
        entry.update(requested=[width, height], devicePixelRatio=parent.devicePixelRatioF())
        entry['mainScreenshot'] = screenshot(parent, f'candidate-panel-{width}x{height}')
        panel.scroll.verticalScrollBar().setValue(panel.scroll.verticalScrollBar().maximum())
        settle()
        entry['lastToolsScreenshot'] = screenshot(parent, f'candidate-panel-last-tools-{width}x{height}')
        panel.connection_toggle.click()
        panel.connection_note.setText('路径已复制。请在目标 Max 中运行脚本后刷新。\nE:/长目录/连接脚本.ms')
        settle()
        panel.scroll.ensureWidgetVisible(panel.connection_options, 0, 4)
        settle()
        entry['settingsScreenshot'] = screenshot(parent, f'candidate-settings-{width}x{height}')
        entry['settingsNoHorizontalOverflow'] = panel.scroll.widget().width() <= panel.scroll.viewport().width() + 1
        panel.connection_toggle.click()
        select(panel, 'max-unconnected')
        settle()
        panel.scroll.ensureWidgetVisible(panel.target, 0, 4)
        settle()
        entry['unconnectedScreenshot'] = screenshot(parent, f'candidate-unconnected-{width}x{height}')
        entry['unconnectedAllDisabled'] = not any(b.isEnabled() for b in panel.buttons.values())
        entry['ok'] = (not entry['horizontalOverflow'] and entry['allNineReachable'] and entry['noGroupLabelOverlap']
                       and entry['settingsNoHorizontalOverflow'] and entry['unconnectedAllDisabled'])
        report['directPanels'].append(entry)
        handle.shutdown()
        parent.close()
        parent.deleteLater()
        settle()

    # Baseline is an immutable panel-only fixture, not an install or business copy.
    baseline = OUT / 'baseline-007-panel-resources'
    baseline.mkdir(parents=True, exist_ok=True)
    for name in PANEL_RESOURCES:
        path = baseline / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = subprocess.check_output(['git', 'show', 'v0.0.7:' + name], cwd=ROOT)
        if path.exists():
            assert path.read_bytes() == data, 'Do not overwrite a different baseline'
        else:
            path.write_bytes(data)
    report['baselineSource'] = dict(tag='v0.0.7', fixture=str(baseline),
                                   hashes={n: hashlib.sha256((baseline / n).read_bytes()).hexdigest() for n in PANEL_RESOURCES})

    for width, height in ((1280, 720), (1440, 900), (1600, 900)):
        for label, root in (('baseline007', baseline), ('candidate', ROOT)):
            with mock.patch('desktop.github_auth.load', return_value={}):
                window = Window(ToolStore(OUT / 'desktop-profile' / scale / label),
                                OUT / 'empty-tools', autoload=False)
            window.navigate('library')
            window.panel_title.setText('Max 工具集 · ' + ('0.0.7' if label == 'baseline007' else '候选'))
            window.move_combo.addItem('未分类', None)
            window.workspace.display(source_tool(root))
            window.pages.setCurrentWidget(window.tool_panel)
            panel = window.workspace.native_panel.widget
            prepare(panel)
            window.resize(width, height)
            window.show()
            settle()
            entry = geometry(panel)
            entry.update(label=label, requestedHost=[width, height], actualHost=[window.width(), window.height()],
                         panelInHost=rectangle(panel, window), devicePixelRatio=window.devicePixelRatioF(),
                         screenshot=screenshot(window, f'{label}-shell-{width}x{height}'))
            # The baseline is comparative evidence; only the candidate is a gate.
            entry['ok'] = label == 'baseline007' or (not entry['horizontalOverflow'] and entry['allNineReachable'] and entry['noGroupLabelOverlap']
                                                     and len(entry['fullyVisibleAtTop']) == 9)
            report['desktopPanels'].append(entry)
            window.close()
            window.deleteLater()
            settle()
    assert hashlib.sha256((ROOT / 'ui/panel.py').read_bytes()).hexdigest() == candidate_hash, 'Candidate changed during visual run'
    report['ok'] = all(e['ok'] for e in report['directPanels'] + report['desktopPanels'])
    (OUT / ('dpi-' + scale + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(dict(ok=report['ok'], scale=scale, direct=len(report['directPanels']), desktop=len(report['desktopPanels']))))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        render_worker(sys.argv[2])
    else:
        run_workers()
