import re
import os

path = 'dashboard/html_template.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Replace document.getElementById('id').innerText = ...
def repl(m):
    id_str = m.group(1)
    # create a safe variable name by replacing hyphens with underscores
    var_name = "el_" + id_str.replace('-', '_')
    val = m.group(2)
    return f"const {var_name} = document.getElementById('{id_str}'); if ({var_name}) {var_name}.innerText = {val};"

code = re.sub(r"document\.getElementById\(['\"]([^'\"]+)['\"]\)\.innerText\s*=\s*([^;]+);", repl, code)

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print("Replaced successfully")
