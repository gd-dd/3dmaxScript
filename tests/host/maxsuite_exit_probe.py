"""Minimal owned-batch exit baselines; no window, business or quit override."""
import json
import os
from pathlib import Path
import sys


def main():
    mode = os.environ.get('LX_MAXSUITE_EXIT_PROBE_MODE')
    if os.environ.get('LX_MAXSUITE_UI_ENTRY') != '1' or mode not in ('noqt', 'qt-import-only', 'qt-pump', 'qt-global-deferred'):
        raise RuntimeError('Use the scheduled parent-entry launcher with --probe')
    source = Path(main.__code__.co_filename).resolve().parents[2]
    out = Path(os.environ['LX_MAXSUITE_UI_RUN']).resolve()
    expected = source.parent / 'acceptance/maxsuite-ui-2026-11-12/host-runs'
    if not out.is_relative_to(expected):
        raise RuntimeError('Probe output must remain inside its unique E run')
    for key in ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP',
                'ADSK_3DSMAX_APPDATA_DIR', 'ADSK_3DSMAX_USERSETTINGS_DIR'):
        value = os.environ.get(key, '')
        if not value or not Path(value).resolve().is_relative_to(out):
            raise RuntimeError('Probe needs isolated E environment: ' + key)
    sys.dont_write_bytecode = True
    from pymxs import runtime as rt
    process = rt.dotNetClass('System.Diagnostics.Process').GetCurrentProcess()
    report = dict(ok=True, mode=mode, pid=os.getpid(),
                  executable=str(process.MainModule.FileName),
                  workerBirthUTC=str(process.StartTime.ToUniversalTime().ToString('o')),
                  workerBirthFileTime=str(rt.dotNetClass('System.Convert').ToString(
                      process.StartTime.ToUniversalTime().ToFileTimeUtc())),
                  command=str(rt.dotNetClass('System.Environment').CommandLine),
                  scope='Exit-only baseline; no business, widgets or quit override',
                  scriptImportsQt=False, checks=[], screenshots=[], stages=[],
                  eventPumpCalls=0, globalDeferredDeleteCalls=0)
    if mode != 'noqt':
        import PySide6
        from PySide6 import QtWidgets
        application = QtWidgets.QApplication.instance()
        report.update(scriptImportsQt=True, pysideVersion=PySide6.__version__,
                      pysidePath=str(PySide6.__file__),
                      qtWidgetsPath=str(QtWidgets.__file__),
                      applicationClass=type(application).__name__,
                      applicationExists=application is not None,
                      quitOnLastWindowClosed=application.quitOnLastWindowClosed() if application is not None else None)
    def stage(name):
        report['stages'].append(name)
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    report['ok'] = False
    stage('metadata.complete')
    if mode in ('qt-pump', 'qt-global-deferred'):
        from PySide6 import QtCore
        assert application is not None, 'Max QApplication is required'
        if mode == 'qt-global-deferred':
            report['globalDeferredDeleteCalls'] += 1
            stage('global-deferred.begin')
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            stage('global-deferred.end')
        report['eventPumpCalls'] += 1
        stage('event-pump.begin')
        application.processEvents(QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents, 20)
        stage('event-pump.end')
    report['ok'] = True
    stage('probe.complete')
    print('MAXSUITE_EXIT_PROBE', mode, 'PID', report['pid'], report['workerBirthUTC'], flush=True)


if __name__ == '__main__':
    main()
