from pathlib import Path
text=Path('app/templates/dashboard.html').read_text().splitlines()
for i,line in enumerate(text,1):
    if 'priceCurrent' in line:
        for j in range(i-5, i+12):
            if j>=1 and j<=len(text):
                print(f"{j}:{text[j-1]}")
