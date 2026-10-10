from pathlib import Path
from pypdf import PdfReader
import json,re
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence'/'official_vo_20230605'
pdf=Path(r'D:\FPGA\eLinx3.0\UG102_eLinx_Design_Suite_User_Guide_ehiway_v2024.9.pdf')
reader=PdfReader(pdf)
rows=[]
terms=['.vqm','.vo','SDF','Run Synthesis','Generate SDF','Run Implementation']
for i,page in enumerate(reader.pages):
    txt=page.extract_text() or ''
    found=[t for t in terms if t.lower() in txt.lower()]
    if found:rows.append({'pdf_page':i+1,'terms':found,'text':txt})
(OUT/'ug102_matching_pages.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
for row in rows:
    print('PDF_PAGE',row['pdf_page'],'TERMS',','.join(row['terms']))
    for t in row['terms']:
        m=re.search(re.escape(t),row['text'],re.I)
        print(row['text'][max(0,m.start()-160):m.end()+450].replace('\n',' '))
