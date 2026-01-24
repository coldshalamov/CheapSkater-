from pathlib import Path
import re
path=Path('app/templates/dashboard.html')
text=path.read_text(encoding='utf-8')
text=re.sub(r"\? \`\$\{formatCurrency\(group\.min_price\)\}\$\{group\.max_price[^`]*`", " ? `${formatCurrency(group.min_price)}${group.max_price !== null && group.max_price !== undefined && group.max_price !== group.min_price ? ` - ${formatCurrency(group.max_price)}` : ''}`", text)
text=re.sub(r"Save \$\{formatCurrency\(group\.min_savings\)\}\$\{group\.max_savings[^`]*`", "Save ${formatCurrency(group.min_savings)}${group.max_savings !== null && group.max_savings !== undefined && group.max_savings !== group.min_savings ? ` - ${formatCurrency(group.max_savings)}` : ''}`", text)
path.write_text(text, encoding='utf-8')
