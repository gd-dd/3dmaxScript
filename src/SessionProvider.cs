using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using System.Threading;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace LXMaxTools {
public sealed class Instance {
    public int Pid, Version, ConnectionProtocol; public long Birth; public string Title, Exe, Session, Scene, State;
    public string Key { get { return Pid + "-" + Birth; } }
    public bool Connected { get { return State == "已连接"; } }
}
public static class Engine {
    public static string Root = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, ".."));
    public static string AbsoluteDirectory(string value) {
        if(String.IsNullOrWhiteSpace(value) || !Path.IsPathRooted(value) || Path.GetPathRoot(value).Length<3)
            throw new Exception("LOCALAPPDATA 必须是有效的绝对目录。");
        return Path.GetFullPath(value);
    }
    public static string LocalDataRoot() {
        var value=Environment.GetEnvironmentVariable("LOCALAPPDATA",EnvironmentVariableTarget.Process);
        return AbsoluteDirectory(value==null?Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData):value);
    }
    public static string UserRoot = Path.Combine(LocalDataRoot(), "LXMaxTools");
    public static readonly Dictionary<string,string> Plugins = new Dictionary<string,string> {
        {"animation-bake", "动画烘焙工具.ms"}, {"keyframe-formula", "自定义公式关键帧.ms"},
        {"material-split", "按材质ID拆分模型.ms"}, {"parent-keep-world", "保持位移建立父子.ms"},
        {"pmx-import", "PMX导入.ms"}, {"root-cleanup", "清理根骨骼.ms"},
        {"rig-workbench", "LX_RigSkin.ms"}, {"ribbon", "LX_Ribbon.ms"}, {"retarget", "LX_Retarget.ms"}, {"uv-overlap", "LX_UVOverlap.ms"}
    };
    public static string Decode(string s) { return Encoding.UTF8.GetString(Convert.FromBase64String(s)); }
    public static string Label(string id) { return Plugins.ContainsKey(id)?Path.GetFileNameWithoutExtension(Plugins[id]):id; }
    public static bool SamePath(string a,string b) { return String.Equals(Path.GetFullPath(a).TrimEnd('\\'),Path.GetFullPath(b).TrimEnd('\\'),StringComparison.OrdinalIgnoreCase); }
    public static int DetectVersion(int major,string product,string path) {
        // Binary metadata wins over a stale year in an installation directory.
        if(major>=20&&major<=99)return major+1998;
        foreach(var text in new [] {product ?? "",path ?? ""}) {
            var match=Regex.Match(text,@"(?<!\d)(20[0-9]{2})(?!\d)");
            if(match.Success)return Int32.Parse(match.Value);
        }
        return 0;
    }
    public static bool SupportedVersion(int year) {return year>=2023&&year<=2027;}
    public static void ApplyHeartbeat(Instance instance,string[] data,bool stale) {
        if(!((data.Length==3&&data[0]=="1")||(data.Length==4&&data[0]=="2")))throw new Exception("连接格式不匹配");
        instance.ConnectionProtocol=Int32.Parse(data[0]);
        if(instance.ConnectionProtocol==2) {
            var declared=Int32.Parse(data[3]);
            if(!SupportedVersion(declared)||(instance.Version!=0&&instance.Version!=declared))throw new Exception("连接信息与 Max 进程版本不匹配");
            instance.Version=declared;
        }
        instance.Scene=Decode(data[2]);
        instance.State=!SamePath(Decode(data[1]),Root)?"连接的是其他工具版本":stale?"忙碌 / 暂未响应":"已连接";
    }
    public static void VerifyPackage() {
        var doc = new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(Root,".lxtool","manifest.json")));
        var files = (Dictionary<string,object>)doc["files"];
        foreach(var pair in files) {
            var path = Path.GetFullPath(Path.Combine(Root,pair.Key));
            if(!path.StartsWith(Root.TrimEnd('\\')+"\\",StringComparison.OrdinalIgnoreCase)) throw new Exception("工具文件路径无效。");
            using(var sha=SHA256.Create()) using(var stream=File.OpenRead(path)) {
                var digest=BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();
                if(digest!=(string)pair.Value) throw new Exception("工具文件校验失败："+pair.Key+"，请重新安装。");
            }
        }
    }
    public static List<Instance> Scan() {
        var result=new List<Instance>();
        foreach(var p in Process.GetProcessesByName("3dsmax")) {
            using(p) {
            var i=new Instance { Pid=p.Id,Title="正在启动 / 无可见窗口",Exe="",State="未连接" };
            try { i.Birth=p.StartTime.ToUniversalTime().Ticks;i.Title=String.IsNullOrWhiteSpace(p.MainWindowTitle)?i.Title:p.MainWindowTitle; }
            catch { i.State="无法读取进程";result.Add(i);continue; }
            try {
                i.Exe=p.MainModule.FileName;
                var version=FileVersionInfo.GetVersionInfo(i.Exe);
                i.Version=DetectVersion(version.FileMajorPart,version.ProductName+" "+version.ProductVersion,i.Exe);
            } catch {}
            i.Session=Path.Combine(UserRoot,"sessions",i.Key);
            var info=Path.Combine(i.Session,"info");
            try {
                if(File.Exists(info)) {
                    string[] data;
                    using(var stream=new FileStream(info,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete))
                    using(var reader=new StreamReader(stream,Encoding.UTF8))data=reader.ReadToEnd().Replace("\r","").Split('\n');
                    ApplyHeartbeat(i,data,DateTime.UtcNow-File.GetLastWriteTimeUtc(info)>TimeSpan.FromSeconds(8));
                }
            } catch { i.State="连接信息暂不可读"; }
            if(i.Version!=0&&!SupportedVersion(i.Version))i.State="不支持的 Max 版本（需要 2023–2027）";
            result.Add(i);
        }}
        return result.OrderBy(i=>i.Pid).ToList();
    }
    public static Instance RequireLive(Instance selected) {
        var live=Scan().FirstOrDefault(i=>i.Key==selected.Key);
        if(live==null) throw new Exception("PID "+selected.Pid+" 已退出，请重新选择。");
        if(!live.Connected) throw new Exception("PID "+selected.Pid+"："+live.State+"。请等待自动连接或 Max 空闲。");
        return live;
    }
    public static string Enqueue(Instance selected,string plugin) {
        if(!Plugins.ContainsKey(plugin)) throw new Exception("未知操作。");
        var live=RequireLive(selected);
        VerifyPackage();
        var path=Path.Combine(live.Session,DateTime.UtcNow.Ticks+"-"+Guid.NewGuid().ToString("N")+".request");
        File.WriteAllText(path+".tmp",plugin+"\n"+DateTime.UtcNow.AddSeconds(30).Ticks,new UTF8Encoding(false));
        File.Move(path+".tmp",path); return path;
    }
    public static string EnqueueRig(Instance selected, string payload) {
        var live=RequireLive(selected);VerifyPackage();
        var path=Path.Combine(live.Session,DateTime.UtcNow.Ticks+"-"+Guid.NewGuid().ToString("N")+".request");
        File.WriteAllText(path+".tmp","rig\n"+DateTime.UtcNow.AddMinutes(5).Ticks+"\n"+Convert.ToBase64String(Encoding.UTF8.GetBytes(payload)),new UTF8Encoding(false));
        File.Move(path+".tmp",path);return path;
    }
    static string MxsString(string value) {
        return "((dotNetClass \"System.Text.Encoding\").UTF8.GetString ((dotNetClass \"System.Convert\").FromBase64String \""+Convert.ToBase64String(Encoding.UTF8.GetBytes(value))+"\"))";
    }
    public static string ConnectionScript() {
        var folder=Path.Combine(UserRoot,"connections");Directory.CreateDirectory(folder);
        var script=Path.Combine(folder,RootKey+".ms");
        File.WriteAllText(script,"global LXMaxBridgeRequestedUserRoot = "+MxsString(UserRoot)+"\nfileIn "+MxsString(Path.Combine(Root,"bridge","LXMaxBridge.ms"))+" quiet:true\n",new UTF8Encoding(true));
        return script;
    }
    public static string ConnectionPayload(Instance target) {
        var bridge=Path.Combine(Root,"bridge","LXMaxBridge.ms");
        string digest;using(var sha=SHA256.Create())using(var stream=File.OpenRead(bridge))
            digest=BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();
        return "LXCONNECT1\n"+target.Pid+"\n"+target.Birth+"\n"+DateTime.UtcNow.AddSeconds(12).Ticks+"\n"+
            Convert.ToBase64String(Encoding.UTF8.GetBytes(Root))+"\n"+digest;
    }
    public static string Connect(Instance target) {
        var live=Scan().FirstOrDefault(i=>i.Key==target.Key);
        if(live==null)throw new Exception("此 Max 已退出，未连接其他窗口。");
        if(!SupportedVersion(live.Version))throw new Exception("无法识别或不支持此 Max 版本（需要 2023–2027）。");
        if(live.ConnectionProtocol<2)throw new Exception("此窗口尚未加载连接组件，保存场景并重开 Max 后会自动接入。");
        VerifyPackage();
        var path=Path.Combine(live.Session,Guid.NewGuid().ToString("N")+".connect");
        File.WriteAllText(path+".tmp",ConnectionPayload(live),new UTF8Encoding(false));File.Move(path+".tmp",path);
        return path;
    }
    public static Process Launch(string exe) {
        if(!File.Exists(exe)||!String.Equals(Path.GetFileName(exe),"3dsmax.exe",StringComparison.OrdinalIgnoreCase)) throw new Exception("请选择有效的 3dsmax.exe。");
        VerifyPackage();
        var version=FileVersionInfo.GetVersionInfo(exe);
        var year=DetectVersion(version.FileMajorPart,version.ProductName+" "+version.ProductVersion,exe);
        if(year!=0&&!SupportedVersion(year))throw new Exception("请选择 3ds Max 2023–2027 的程序。");
        var start=new ProcessStartInfo(exe,"-U MAXScript \""+ConnectionScript()+"\"") { UseShellExecute=false,WorkingDirectory=Path.GetDirectoryName(exe) };
        foreach(var key in new [] {"QT_QPA_PLATFORM","QT_PLUGIN_PATH","QT_QPA_PLATFORM_PLUGIN_PATH","PYTHONHOME","PYTHONPATH"}) start.EnvironmentVariables.Remove(key);
        var started=Process.Start(start);
        Remember(started);return started;
    }

    static string RootKey { get {using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(Root.ToLowerInvariant()))).Replace("-","").Substring(0,24);} }
    static string ManagedPath { get {return Path.Combine(UserRoot,"managed",RootKey+".json");} }
    public static List<Instance> ReadManaged() {
        if(!File.Exists(ManagedPath))return new List<Instance>();
        return new JavaScriptSerializer().Deserialize<List<Instance>>(File.ReadAllText(ManagedPath));
    }
    static void Remember(Process p) {
        using(var gate=new Mutex(false,"Local\\LXMaxTools-"+RootKey)) {
            bool locked=false;
            try {
                try {locked=gate.WaitOne(5000);}catch(AbandonedMutexException){locked=true;}
                if(!locked)throw new Exception("写入实例记录超时，请稍后连接。");
                var list=ReadManaged().Where(i=>{try{using(var q=Process.GetProcessById(i.Pid))return q.StartTime.ToUniversalTime().Ticks==i.Birth;}catch{return false;}}).ToList();
                var record=new Instance{Pid=p.Id,Birth=p.StartTime.ToUniversalTime().Ticks};
                if(!list.Any(i=>i.Key==record.Key))list.Add(record);
                Directory.CreateDirectory(Path.GetDirectoryName(ManagedPath));
                var temp=ManagedPath+"."+Guid.NewGuid().ToString("N")+".tmp";
                File.WriteAllText(temp,new JavaScriptSerializer().Serialize(list),new UTF8Encoding(false));
                if(File.Exists(ManagedPath))File.Replace(temp,ManagedPath,null);else File.Move(temp,ManagedPath);
            }finally{if(locked)gate.ReleaseMutex();}
        }
    }
    public static string DefaultExe() {
        var config=Path.Combine(UserRoot,"max-path.txt");
        if(File.Exists(config)&&File.Exists(File.ReadAllText(config))) return File.ReadAllText(config);
        try {
            var shelf=Path.Combine(LocalDataRoot(),"LXTool","repository-tools-v2.json");
            var json=new JavaScriptSerializer().DeserializeObject(File.ReadAllText(shelf)) as Dictionary<string,object>;
            var apps=(Dictionary<string,object>)json["applications"];
            var app=(Dictionary<string,object>)((Dictionary<string,object>)apps["repo-1342543761"])["max"];
            var path=(string)app["path"];if(File.Exists(path))return path;
        } catch {}
        var running=Scan().FirstOrDefault(i=>File.Exists(i.Exe)); if(running!=null) return running.Exe;
        using(var key=Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Autodesk\3dsMax")) if(key!=null) {
            foreach(var name in key.GetSubKeyNames().OrderByDescending(s=>s)) using(var version=key.OpenSubKey(name)) {
                var dir=version.GetValue("Installdir") as string;
                if(dir!=null&&File.Exists(Path.Combine(dir,"3dsmax.exe")))return Path.Combine(dir,"3dsmax.exe");
            }
        }
        return "";
    }
}

sealed class Request { public string Session,Tool,Path,Id; public DateTime Deadline; }
sealed class ConnectionAttempt {public string Session,Path;public DateTime Deadline;}
static class Provider {
    static JavaScriptSerializer json=new JavaScriptSerializer {MaxJsonLength=32*1024*1024};
    static List<Request> pending=new List<Request>();
    static List<ConnectionAttempt> connecting=new List<ConnectionAttempt>();
    static string Field(Dictionary<string,object> d,string name){return d.ContainsKey(name)?d[name] as string:null;}
    static object Respond(Dictionary<string,object> request) {
        var op=Field(request,"op");var events=new List<string>();var results=new List<object>();
        if(op=="launch") {
            using(var p=Engine.Launch(Field(request,"applicationPath")))events.Add("已启动 Max · PID "+p.Id+"，正在等待连接。如 Max 出现启动提示，请先完成提示。");
        } else if(op=="run") {
            var session=Field(request,"sessionId");var tool=Field(request,"toolId");
            var target=Engine.Scan().FirstOrDefault(i=>i.Key==session);
            if(target==null)throw new Exception("此窗口已退出，请重新选择。");
            if(pending.Any(p=>p.Session==session&&p.Tool==tool))throw new Exception("此窗口的该工具正在打开，请稍候。");
            pending.Add(new Request{Session=session,Tool=tool,Path=Engine.Enqueue(target,tool),Deadline=DateTime.UtcNow.AddSeconds(30)});
            events.Add("正在 PID "+target.Pid+" 中打开 "+Engine.Label(tool)+"…");
        } else if(op=="rig") {
            var session=Field(request,"sessionId");
            var target=Engine.Scan().FirstOrDefault(i=>i.Key==session);
            if(target==null)throw new Exception("目标 Max 已退出，请重新选择。");
            if(pending.Any(p=>p.Session==session))throw new Exception("此 Max 还有操作正在执行，请等待完成。");
            if(!request.ContainsKey("request"))throw new Exception("缺少操作数据");
            var payload=json.Serialize(request["request"]);
            pending.Add(new Request{Session=session,Tool="rig",Id=Field(request,"id"),Path=Engine.EnqueueRig(target,payload),Deadline=DateTime.UtcNow.AddMinutes(5)});
        } else if(op=="cancel-rig") {
            var p=pending.FirstOrDefault(i=>i.Tool=="rig"&&i.Id==Field(request,"requestId")&&i.Session==Field(request,"sessionId"));
            if(p==null)throw new Exception("操作已完成或不属于当前连接。");
            try {File.Move(p.Path,p.Path+".cancelled");}
            catch(IOException) {throw new Exception("Max 已接收此操作，无法中途取消；请等待回执。");}
            File.Delete(p.Path+".cancelled");pending.Remove(p);
            results.Add(new {requestId=p.Id,sessionId=p.Session,result=new {ok=false,error="尚未开始的操作已取消。"}});
        } else if(op!="status"&&op!="hello")throw new Exception("未知操作。");
        var sessions=Engine.Scan();
        if(op=="hello"||op=="status") {
            foreach(var instance in sessions) {
                if(instance.Connected||connecting.Any(c=>c.Session==instance.Key)||pending.Any(p=>p.Session==instance.Key))continue;
                if(!Engine.SupportedVersion(instance.Version)||instance.ConnectionProtocol<2||instance.State=="忙碌 / 暂未响应")continue;
                try {
                    connecting.Add(new ConnectionAttempt{Session=instance.Key,Path=Engine.Connect(instance),Deadline=DateTime.UtcNow.AddSeconds(12)});
                    events.Add("正在连接 Max "+instance.Version+" · PID "+instance.Pid+" 到当前工具版本…");
                }catch(Exception error){events.Add("PID "+instance.Pid+"："+error.Message);}
            }
        }
        foreach(var connection in connecting.ToArray()) {
            var live=sessions.FirstOrDefault(i=>i.Key==connection.Session);
            if(live!=null&&live.Connected) {
                events.Add("Max "+live.Version+" · PID "+live.Pid+" 已连接当前工具版本。");connecting.Remove(connection);
            }else if(File.Exists(connection.Path+".result")||live==null||DateTime.UtcNow>connection.Deadline) {
                var message="Max 暂未响应，空闲后会继续尝试连接。";
                if(live==null)message="窗口已退出";
                else if(File.Exists(connection.Path+".result"))message=File.ReadAllText(connection.Path+".result");
                events.Add("PID "+connection.Session.Split('-')[0]+"："+message);connecting.Remove(connection);
            }
            if(!connecting.Contains(connection)) {
                foreach(var path in new [] {connection.Path,connection.Path+".result"})try{File.Delete(path);}catch{}
            }
        }
        foreach(var p in pending.ToArray()) {
            if(File.Exists(p.Path+".result")) {
                try {
                    var lines=File.ReadAllLines(p.Path+".result");
                    if(p.Tool=="rig") {
                        object body=lines.Length>1&&lines[0]=="DATA"?json.DeserializeObject(Engine.Decode(lines[1])):new {ok=false,error=lines.Length>1?Engine.Decode(lines[1]):"无效回执"};
                        results.Add(new {requestId=p.Id,sessionId=p.Session,result=body});
                    } else events.Add("PID "+p.Session.Split('-')[0]+" · "+Engine.Label(p.Tool)+"："+(lines.Length>0&&lines[0]=="OK"?"已打开":lines.Length>1?Engine.Decode(lines[1]):"无效执行回执"));
                }catch(Exception e){events.Add("执行回执读取失败："+e.Message);if(p.Tool=="rig")results.Add(new {requestId=p.Id,sessionId=p.Session,result=new {ok=false,error="执行回执读取失败："+e.Message}});}
                pending.Remove(p);try{File.Delete(p.Path+".result");}catch{}
            } else if(!sessions.Any(i=>i.Key==p.Session)||DateTime.UtcNow>p.Deadline) {
                events.Add("PID "+p.Session.Split('-')[0]+" 请求超时或窗口已退出；尚未开始的操作已取消。");
                if(p.Tool=="rig")results.Add(new {requestId=p.Id,sessionId=p.Session,result=new {ok=false,error="命令超时或 Max 已退出。已经开始的操作可能仍在执行，请刷新检查结果。"}});
                try{File.Delete(p.Path);}catch{}pending.Remove(p);
            }
        }
        return new {protocol=1,id=Field(request,"id"),ok=true,sessionRoot=Engine.UserRoot,applicationPath=Engine.DefaultExe(),events=events,results=results,
            sessions=sessions.Select(i=>new {id=i.Key,pid=i.Pid,version=i.Version==0?"未知":i.Version.ToString(),scene=i.Scene??"",title=String.IsNullOrEmpty(i.Scene)?i.Title:Path.GetFileName(i.Scene),
                detail="Max "+(i.Version==0?"未知版本":i.Version.ToString())+" · PID "+i.Pid+" · "+i.Title,
                state=i.Connected?"ready":connecting.Any(c=>c.Session==i.Key)?"connecting":i.State=="未连接"||i.ConnectionProtocol<2?"unconnected":"busy",status=i.State}),
            pending=pending.Select(p=>new {sessionId=p.Session,toolId=p.Tool})};
    }
    static int Main() {
        Console.SetIn(new StreamReader(Console.OpenStandardInput(),new UTF8Encoding(false)));
        Console.SetOut(new StreamWriter(Console.OpenStandardOutput(),new UTF8Encoding(false)){AutoFlush=true});
        Console.SetError(new StreamWriter(Console.OpenStandardError(),new UTF8Encoding(false)){AutoFlush=true});
        try {
            Engine.VerifyPackage();string line;
            while((line=Console.ReadLine())!=null) {
                Dictionary<string,object> request=null;object result;
                try {
                    if(line.Length>1024*1024)throw new Exception("请求过长。");
                    request=json.Deserialize<Dictionary<string,object>>(line);result=Respond(request);
                }catch(Exception e){result=new {protocol=1,id=request==null?null:Field(request,"id"),ok=false,error=e.Message};}
                Console.WriteLine(json.Serialize(result));Console.Out.Flush();
            }
            return 0;
        }catch(Exception e){Console.Error.WriteLine(e.GetBaseException().Message);return 1;}
        finally{foreach(var p in pending)try{File.Delete(p.Path);}catch{}foreach(var c in connecting)try{File.Delete(c.Path);}catch{}}
    }
}
}
