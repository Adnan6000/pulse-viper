import re
from dashboard.html_template import HTML_TEMPLATE

ids_accessed = re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", HTML_TEMPLATE)
missing = [i for i in ids_accessed if f'id="{i}"' not in HTML_TEMPLATE and f"id='{i}'" not in HTML_TEMPLATE]
print("Missing IDs:", set(missing))
