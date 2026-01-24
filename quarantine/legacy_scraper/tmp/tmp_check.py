from pathlib import Path
import re
text=Path('app/templates/dashboard.html').read_text(encoding='utf-8')
m=re.search(r"muted\">(.*?)</span>", text)
if m:
    start=text.rfind('\n',0,m.start())
    end=text.find('\n', m.end())
    print(text[start+1:end])
