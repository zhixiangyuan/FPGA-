"""Create a local work mapping before starting ModelSim, without live vmap edits."""
from pathlib import Path
import re


def prepare_ini(run,modelsim_bin):
    text=(Path(modelsim_bin).parent/'modelsim.ini').read_text()
    text=re.sub(r'(?im)^work\s*=.*(?:\n|$)','',text)
    assert '[Library]\n' in text
    text=text.replace('[Library]\n','[Library]\nwork = work\n',1)
    (Path(run)/'modelsim.ini').write_text(text,encoding='utf-8')
