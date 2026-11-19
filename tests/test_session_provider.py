"""Compile and exercise the actual provider's version and wire contracts."""
import os,subprocess,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/'acceptance/max-connect-2026-11-19/provider-tests'

HARNESS=r'''
using System;
using System.IO;
using System.Text;
using LXMaxTools;
public static class ContractTests {
 static void Check(bool value,string message) {if(!value)throw new Exception(message);}
 static string Enc(string value) {return Convert.ToBase64String(Encoding.UTF8.GetBytes(value));}
 public static int Main(string[] args) {
  Engine.Root=args[1];
  if(args[0]=="versions") {
   for(int year=2023;year<=2027;year++) {
    Check(Engine.DetectVersion(year-1998,"",@"E:\DCC\Max\3dsmax.exe")==year,"major/year");
    Check(Engine.DetectVersion(0,"Autodesk 3ds Max "+year,"")==year,"product/year");
    Check(Engine.SupportedVersion(year),"supported");
   }
   Check(!Engine.SupportedVersion(2022)&&!Engine.SupportedVersion(2028),"range");
   Check(Engine.DetectVersion(28,"3ds Max",@"E:\2023\3dsmax.exe")==2026,"binary wins over stale directory year");
   Check(Engine.DetectVersion(24,"","")==2022&&Engine.DetectVersion(30,"","")==2028,"retain unsupported binary versions");
   Check(Engine.DetectVersion(0,"3ds Max 2028","")==2028,"retain unsupported product year");
   Check(Engine.DetectVersion(0,"unknown","")==0,"no guessing unknown");
  } else if(args[0]=="heartbeat") {
   foreach(int year in new[]{2023,2024,2025,2026,2027}) {
    var instance=new Instance{Version=year};
    Engine.ApplyHeartbeat(instance,new[]{"2",Enc(Engine.Root),Enc("角色 场景.max"),year.ToString()},false);
    Check(instance.Connected&&instance.Version==year&&instance.ConnectionProtocol==2,"five-version heartbeat");
    Check(instance.Scene=="角色 场景.max","unicode scene");
   }
   var legacy=new Instance{Version=2026};
   Engine.ApplyHeartbeat(legacy,new[]{"1",Enc(Engine.Root),Enc("legacy.max")},false);
   Check(legacy.Connected&&legacy.ConnectionProtocol==1,"read legacy without claiming v2 reconnect");
   Engine.ApplyHeartbeat(legacy,new[]{"1",Enc(Engine.Root),Enc("legacy.max")},true);
   Check(!legacy.Connected,"stale not ready");
   Engine.ApplyHeartbeat(legacy,new[]{"2",Enc(Path.Combine(Engine.Root,"different-version")),Enc("same.max"),"2026"},false);
   Check(!legacy.Connected,"different package not ready");
   bool rejected=false;
   try{Engine.ApplyHeartbeat(new Instance{Version=2026},new[]{"2",Enc(Engine.Root),Enc("x"),"2023"},false);}catch{rejected=true;}
   Check(rejected,"process year and heartbeat year must agree");
   rejected=false;try{Engine.ApplyHeartbeat(legacy,new[]{"2","partial"},false);}catch{rejected=true;}
   Check(rejected,"partial heartbeat rejected");
  } else if(args[0]=="payload") {
   var target=new Instance{Pid=4321,Birth=123456789,Version=2026};
   var parts=Engine.ConnectionPayload(target).Split('\n');
   Check(parts.Length==6&&parts[0]=="LXCONNECT1","wire format");
   Check(parts[1]=="4321"&&parts[2]=="123456789","PID and birth identity");
   Check(Int64.Parse(parts[3])>DateTime.UtcNow.Ticks&&Int64.Parse(parts[3])<=DateTime.UtcNow.AddSeconds(13).Ticks,"bounded expiry");
   Check(Engine.Decode(parts[4])==Engine.Root&&parts[5].Length==64,"package and hash");
  } else throw new Exception("Unknown test");
  Console.WriteLine("PASS "+args[0]);return 0;
 }
}
'''


@unittest.skipUnless(os.name=='nt','Windows .NET provider')
class SessionProviderContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUT.mkdir(parents=True,exist_ok=True);cls.env=dict(os.environ)
        for key in ('TEMP','TMP','APPDATA','LOCALAPPDATA','USERPROFILE'):
            p=OUT/'environment'/key;p.mkdir(parents=True,exist_ok=True);cls.env[key]=str(p)
        cls.exe=OUT/'ProviderContracts.exe';source=OUT/'ProviderContracts.cs';source.write_text(HARNESS,'utf-8-sig')
        compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        result=subprocess.run([str(compiler),'/nologo','/target:exe','/main:ContractTests','/r:System.Web.Extensions.dll',
            '/out:'+str(cls.exe),str(ROOT/'src/SessionProvider.cs'),str(source)],env=cls.env,capture_output=True,timeout=30)
        if result.returncode:raise AssertionError(result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace'))
    def run_case(self,name):
        result=subprocess.run([str(self.exe),name,str(ROOT)],env=self.env,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,(result.stdout+result.stderr).decode(errors='replace'))
    def test_five_supported_versions_and_unknown_version(self):self.run_case('versions')
    def test_heartbeat_version_identity_stale_and_legacy(self):self.run_case('heartbeat')
    def test_reconnect_targets_pid_birth_package_and_expiry(self):self.run_case('payload')
