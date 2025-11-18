from pathlib import Path
text=Path('app/templates/dashboard.html').read_text(encoding='utf-8')
positions=[4479,8470,8837,9294,9617,11940,12334,16493,16943,25345,28135,28860]
for pos in positions:
    start=max(pos-40,0); end=min(pos+40,len(text));
    snippet=text[start:end]
    print('\nPOS',pos)
    print(snippet)
