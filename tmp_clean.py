from pathlib import Path
text=Path('app/templates/dashboard.html').read_text(encoding='utf-8')
text=text.replace('�','-')
text=text.replace('keyword-','keyword...')
text=text.replace('<div class="price muted">-</div>','<div class="price muted">--</div>')
text=text.replace(" or '-' }}", " or '--' }}")
text=text.replace('muted">-</span>','muted">--</span>')
Path('app/templates/dashboard.html').write_text(text, encoding='utf-8')
