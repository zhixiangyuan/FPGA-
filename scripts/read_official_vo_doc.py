from pathlib import Path
import zipfile, xml.etree.ElementTree as E, hashlib, json, shutil
SRC=Path(r'C:\Users\袁志祥\Downloads\.vqm文件和.vo文件生成与使用20230605.docx')
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence'/'official_vo_20230605'
OUT.mkdir(parents=True,exist_ok=True)
shutil.copy2(SRC,OUT/SRC.name)
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
with zipfile.ZipFile(SRC) as z:
    xml=E.fromstring(z.read('word/document.xml'))
    lines=[]
    for i,p in enumerate(xml.findall('.//w:body//w:p',ns),1):
        txt=''.join(p.itertext()) if False else ''.join(t.text or '' for t in p.findall('.//w:t',ns))
        pics=[e.attrib.get('{'+ns['r']+'}embed','') for e in p.findall('.//a:blip',ns)]
        if txt or pics:lines.append(f'P{i}: {txt}'+(' [image:'+','.join(pics)+']' if pics else ''))
    (OUT/'body.txt').write_text('\n'.join(lines),encoding='utf-8')
    for n in z.namelist():
        if n.startswith('word/media/') and not n.endswith('/'):
            (OUT/Path(n).name).write_bytes(z.read(n))
    rels=E.fromstring(z.read('word/_rels/document.xml.rels'))
    (OUT/'image_relationships.json').write_text(json.dumps({x.attrib['Id']:x.attrib['Target'] for x in rels},ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'core.xml').write_bytes(z.read('docProps/core.xml'))
(OUT/'source.json').write_text(json.dumps({'provided_by':'User says official administrator provided this document; provenance is user-attested','source':str(SRC),'sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'file_time':SRC.stat().st_mtime,'extraction':'read-only OOXML text and embedded images; original DOCX unchanged'},ensure_ascii=False,indent=2),encoding='utf-8')
print('\n'.join(lines))
print('EVIDENCE',OUT)
