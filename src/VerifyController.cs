using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Web.Script.Serialization;
using LXMaxTools;
class VerifyController {
    static void MustReject(Action action,string label) { try{action();}catch{Console.WriteLine("PASS "+label);return;}throw new Exception("DID NOT REJECT "+label); }
    static int Main(string[] args) {
        try {
            Engine.Root=Path.GetFullPath(args[0]);
            if(args.Length>1&&args[1]=="scan") { foreach(var i in Engine.Scan())Console.WriteLine(i.Pid+" | "+i.Birth+" | "+i.State+" | "+i.Title+" | "+i.Session);return 0; }
            if(args.Length>2&&args[1]=="send") {
                var target=Engine.Scan().Single(i=>i.Pid==Int32.Parse(args[2]));
                Console.WriteLine(Engine.Enqueue(target,args[3]));return 0;
            }
            if(args.Length>2&&args[1]=="launch") { using(var p=Engine.Launch(args[2]))Console.WriteLine(p.Id);return 0; }
            Engine.VerifyPackage();Console.WriteLine("PASS complete package hashes");
            MustReject(()=>Engine.Enqueue(new Instance(),"../../arbitrary.ms"),"unknown plugin/path injection");
            MustReject(()=>Engine.RequireLive(new Instance {Pid=Int32.MaxValue,Birth=1}),"exited process");
            foreach(var i in Engine.Scan()) {
                var stale=new Instance{Pid=i.Pid,Birth=i.Birth+1};MustReject(()=>Engine.RequireLive(stale),"PID reuse "+i.Pid);
            }
            var previous=Engine.Root;var fixture=Path.Combine(Path.GetTempPath(),"lx-max-test-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(Path.Combine(fixture,".lxtool"));
            try {
                File.WriteAllText(Path.Combine(fixture,"payload"),"original");string hash;
                using(var sha=SHA256.Create())hash=BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(Path.Combine(fixture,"payload")))).Replace("-","").ToLowerInvariant();
                var files=new Dictionary<string,object>{{"payload",hash}};
                File.WriteAllText(Path.Combine(fixture,".lxtool","manifest.json"),new JavaScriptSerializer().Serialize(new Dictionary<string,object>{{"files",files}}));
                Engine.Root=fixture;Engine.VerifyPackage();File.WriteAllText(Path.Combine(fixture,"payload"),"tampered");MustReject(Engine.VerifyPackage,"changed payload");
                files.Clear();files["../escape"]=hash;
                File.WriteAllText(Path.Combine(fixture,".lxtool","manifest.json"),new JavaScriptSerializer().Serialize(new Dictionary<string,object>{{"files",files}}));MustReject(Engine.VerifyPackage,"manifest traversal");
            } finally {Engine.Root=previous;Directory.Delete(fixture,true);}
            Console.WriteLine("PASS controller validation");return 0;
        }catch(Exception e){Console.Error.WriteLine(e);return 1;}
    }
}
