"""Offscreen candidate test; writes only to E-drive acceptance isolation."""
import os, sys, json, builtins
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/'acceptance/maxsuite-xml-2026-11-10'
OUT.mkdir(parents=True,exist_ok=True)
for key in ('TEMP','TMP','APPDATA','LOCALAPPDATA'):
    folder=OUT/key;folder.mkdir(exist_ok=True);os.environ[key]=str(folder)
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent/'LXTools/src'))
real_import=builtins.__import__
def restricted(name,*args,**kwargs):
    if name=='xml' or name.startswith('xml.'):
        raise ModuleNotFoundError("No module named 'xml'")
    return real_import(name,*args,**kwargs)
builtins.__import__=restricted
from ui import max_connection
from PySide6.QtWidgets import QApplication,QWidget
from native_panels import NativePanelHandle
app=QApplication([])
bootstrap=OUT/'中文 & 路径'/'桥接.ms';bootstrap.parent.mkdir(exist_ok=True)
bootstrap.write_text('-- isolated test; never executed',encoding='utf-8')
folder=max_connection.install('max-tools',bootstrap)
assert str(bootstrap) in (folder/'loader.ms').read_text('utf-8-sig')
special='中文 &<>"\'\t\n\r'
document=max_connection.package_xml(special,'{stable-id}')
for invalid in ('\0','\ud800','\ufffe'):
    try:max_connection.xml_attribute(invalid)
    except ValueError:pass
    else:raise AssertionError('invalid XML character accepted')
manifest=json.loads((ROOT/'.lxtool/manifest.json').read_text('utf-8-sig'))
tool=dict(manifest,id='repo-1342543761',root=ROOT,panelData=json.loads((ROOT/'.lxtool/panel.json').read_text('utf-8')))
parent=QWidget();handle=NativePanelHandle(tool,OUT/'config',parent)
assert 'ribbon' in handle.widget.buttons
assert handle.widget.process.state().value==0
handle.shutdown();handle.shutdown()
builtins.__import__=real_import
# The parser is used only for test assertions, after removing the import ban.
import xml.etree.ElementTree as ET
root=ET.fromstring(document)
assert root.attrib['Name']=='LX '+special+' connection'
assert root.attrib['UpgradeCode']==root.attrib['ProductCode']=='{stable-id}'
installed=ET.parse(folder/'PackageContents.xml').getroot()
assert installed.find('Components/ComponentEntry').attrib['ModuleName']=='./loader.ms'
assert installed.find('Components/RuntimeRequirements').attrib==dict(OS='Win64',Platform='3ds Max',SeriesMin='2024',SeriesMax='2027')
assert str(ROOT/'bridge/LXMaxBridge.ms') in (folder/'loader.ms').read_text('utf-8-sig')
(OUT/'result.json').write_text(json.dumps(dict(ok=True,scope='source loader; xml imports blocked; not frozen EXE',ribbon=True,attributes=True,chinesePath=True),indent=2),encoding='utf-8')
print('PASS blocked xml native loader, ribbon button, Chinese path, XML attribute roundtrip, invalid character rejection')
