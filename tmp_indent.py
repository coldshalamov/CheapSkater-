from pathlib import Path
lines=Path('app/main.py').read_text().splitlines()
for num in [1598,1602,1605,1648]:
    prefix=len(lines[num-1]) - len(lines[num-1].lstrip(' '))
    print(num, prefix, lines[num-1].lstrip())
