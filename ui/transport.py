"""Hidden Windows child process with anonymous pipes and Qt signal delivery."""
import subprocess
import threading
from PySide6.QtCore import QObject, Signal, QProcess

class HiddenProcess(QObject):
    readyReadStandardOutput=Signal()
    readyReadStandardError=Signal()
    started=Signal()
    finished=Signal(int)
    errorOccurred=Signal(str)
    output=Signal(bytes)
    errors=Signal(bytes)
    ended=Signal(int,int)

    def __init__(self,parent):
        super().__init__(parent)
        self.child=None;self.program='';self.args=[];self.cwd=None
        self.out=bytearray();self.err=bytearray();self.generation=0;self.worker=None
        self.output.connect(self._output);self.errors.connect(self._errors);self.ended.connect(self._ended)

    def _output(self,data):self.out.extend(data);self.readyReadStandardOutput.emit()
    def _errors(self,data):self.err.extend(data);self.readyReadStandardError.emit()
    def _ended(self,code,generation):
        if generation==self.generation:self.finished.emit(code)
    def state(self):return QProcess.ProcessState.Running if self.child and self.child.poll() is None else QProcess.ProcessState.NotRunning
    def setProgram(self,value):self.program=value
    def setArguments(self,value):self.args=value
    def setWorkingDirectory(self,value):self.cwd=value

    def start(self):
        try:
            self.child=subprocess.Popen([self.program,*self.args],cwd=self.cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
            child=self.child;self.generation+=1;generation=self.generation
            def read(stream,signal):
                try:
                    while True:
                        data=stream.readline(1048577)
                        if not data:break
                        signal.emit(data)
                finally:stream.close()
            readers=[threading.Thread(target=read,args=(child.stdout,self.output),daemon=True),threading.Thread(target=read,args=(child.stderr,self.errors),daemon=True)]
            for thread in readers:thread.start()
            def wait():
                code=child.wait()
                for thread in readers:thread.join()
                self.ended.emit(code,generation)
            self.worker=threading.Thread(target=wait,daemon=True);self.worker.start()
            self.started.emit()
        except OSError as error:self.errorOccurred.emit(str(error))

    def write(self,data):
        try:self.child.stdin.write(data);self.child.stdin.flush()
        except (OSError,ValueError) as error:self.errorOccurred.emit(str(error))
    def readAllStandardOutput(self):data=bytes(self.out);self.out.clear();return data
    def readAllStandardError(self):data=bytes(self.err);self.err.clear();return data
    def closeWriteChannel(self):
        if self.child and self.child.stdin and not self.child.stdin.closed:
            try:self.child.stdin.close()
            except OSError:pass
    def waitForFinished(self,milliseconds):
        if not self.child:return True
        try:
            self.child.wait(milliseconds/1000)
            if self.worker:self.worker.join(milliseconds/1000)
            return True
        except subprocess.TimeoutExpired:return False
    def kill(self):
        if self.child and self.child.poll() is None:self.child.kill()
