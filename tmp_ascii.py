from pathlib import Path
text=Path('app/templates/dashboard.html').read_text(encoding='utf-8')
text=text.replace('\u2026','...')
text=text.replace('\u2013','-')
text=text.replace('\u2014','-')
Path('app/templates/dashboard.html').write_text(text, encoding='utf-8')
