import os,sys,subprocess
from pathlib import Path
os.environ['PYTHONIOENCODING']='utf-8'
root=Path(__file__).resolve().parent
view=sys.argv[1]
prompt=(root/(view+'-prompt.txt')).read_text(encoding='utf-8')
raise SystemExit(subprocess.call([sys.executable,'C:/Users/Lifeye/.codex/skills/gemini-image/scripts/gemini_image.py','generate',prompt,'--model','gemini-2.5-pro-image','--out',str(root/(view+'.png'))],env=os.environ))
