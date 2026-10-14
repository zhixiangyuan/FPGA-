"""Read supplied official references without changing their contents."""
from pathlib import Path
import hashlib
import json
import openpyxl
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build' / 'audit' / 'stage2'
OUT.mkdir(parents=True, exist_ok=True)
pdf = Path("D:/FPGA/全国大学生嵌入式芯片与系统设计竞赛'2026FPGA赛道选题指南-中科亿海微.pdf")
xlsx = Path('D:/FPGA/资料/FPGA创新大赛问题汇总 (2).xlsx')
pages = [{'page': i+1, 'text': page.extract_text()} for i, page in enumerate(PdfReader(pdf).pages)]
rows = []
book = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
for sheet in book:
    for number, row in enumerate(sheet, 1):
        cells = [{'cell': cell.coordinate, 'value': str(cell.value)} for cell in row if cell.value is not None]
        if cells:
            rows.append({'sheet': sheet.title, 'row': number, 'cells': cells})
book.close()
result = {'sources': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in (pdf, xlsx)], 'guide_pages': pages, 'faq_rows': rows}
(OUT / 'official_sources.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'guide.txt').write_text('\n\n'.join(f"PAGE {p['page']}\n{p['text']}" for p in pages), encoding='utf-8')
(OUT / 'faq.txt').write_text('\n'.join(f"{r['sheet']} ROW {r['row']}: " + ' | '.join(f"{c['cell']}={c['value']}" for c in r['cells']) for r in rows), encoding='utf-8')
print(json.dumps({'pages': len(pages), 'faq_rows': len(rows), 'output': str(OUT)}, ensure_ascii=False))
