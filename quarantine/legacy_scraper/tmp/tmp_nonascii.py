from pathlib import Path
text=Path('app/templates/dashboard.html').read_text(encoding='utf-8')
non=[(i,ch) for i,ch in enumerate(text) if ord(ch)>127]
print('count', len(non))
