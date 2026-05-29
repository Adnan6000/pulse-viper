# scratch/check_js_syntax.py
import sys
import re

def check_syntax():
    with open("dashboard/html_template.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    match = re.search(r"<script>(.*?)</script>", content, re.DOTALL)
    if not match:
        print("FAIL - No script tag found")
        sys.exit(1)
        
    js_code = match.group(1)
    
    # Simple lexical scanner to strip strings, regexes, and comments
    chars = []
    i = 0
    n = len(js_code)
    
    # We will reconstruct a cleaned string where strings, regex, and comments are replaced by spaces
    cleaned = []
    
    in_string = False
    string_char = None
    in_regex = False
    in_single_comment = False
    in_multi_comment = False
    
    line_map = [] # maps cleaned index back to (line_num, col_num)
    
    # Track line and col
    line_num = 1
    col_num = 1
    
    while i < n:
        char = js_code[i]
        
        # Keep track of line and column
        curr_line = line_num
        curr_col = col_num
        
        if char == '\n':
            line_num += 1
            col_num = 1
        else:
            col_num += 1
            
        next_char = js_code[i+1] if i + 1 < n else ''
        
        if in_single_comment:
            if char == '\n':
                in_single_comment = False
            cleaned.append(' ')
            line_map.append((curr_line, curr_col))
            i += 1
            continue
            
        if in_multi_comment:
            if char == '*' and next_char == '/':
                in_multi_comment = False
                cleaned.append(' ')
                cleaned.append(' ')
                line_map.append((curr_line, curr_col))
                line_map.append((curr_line, curr_col + 1))
                i += 2
                col_num += 1
                continue
            cleaned.append(' ')
            line_map.append((curr_line, curr_col))
            i += 1
            continue
            
        if in_string:
            # Check escape
            if char == '\\':
                cleaned.append(' ')
                cleaned.append(' ')
                line_map.append((curr_line, curr_col))
                line_map.append((curr_line, curr_col + 1))
                i += 2
                col_num += 1
                continue
            if char == string_char:
                in_string = False
            cleaned.append(' ')
            line_map.append((curr_line, curr_col))
            i += 1
            continue
            
        if in_regex:
            if char == '\\':
                cleaned.append(' ')
                cleaned.append(' ')
                line_map.append((curr_line, curr_col))
                line_map.append((curr_line, curr_col + 1))
                i += 2
                col_num += 1
                continue
            if char == '/':
                in_regex = False
            cleaned.append(' ')
            line_map.append((curr_line, curr_col))
            i += 1
            continue
            
        # Check starting comments
        if char == '/' and next_char == '/':
            in_single_comment = True
            cleaned.append(' ')
            cleaned.append(' ')
            line_map.append((curr_line, curr_col))
            line_map.append((curr_line, curr_col + 1))
            i += 2
            col_num += 1
            continue
            
        if char == '/' and next_char == '*':
            in_multi_comment = True
            cleaned.append(' ')
            cleaned.append(' ')
            line_map.append((curr_line, curr_col))
            line_map.append((curr_line, curr_col + 1))
            i += 2
            col_num += 1
            continue
            
        # Check starting strings
        if char in ["'", '"', '`']:
            in_string = True
            string_char = char
            cleaned.append(' ')
            line_map.append((curr_line, curr_col))
            i += 1
            continue
            
        # Check starting regex (heuristic: slash not preceded by alphanumeric or closing bracket/paren)
        if char == '/':
            # Heuristic check: look back at previous non-whitespace char in cleaned
            prev_idx = len(cleaned) - 1
            while prev_idx >= 0 and cleaned[prev_idx].isspace():
                prev_idx -= 1
            prev_char = cleaned[prev_idx] if prev_idx >= 0 else ''
            
            # If slash follows an operator or keyword, it's a regex start.
            # If it follows alphanumeric or close brackets, it's division.
            if prev_char not in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_)}]':
                in_regex = True
                cleaned.append(' ')
                line_map.append((curr_line, curr_col))
                i += 1
                continue
                
        cleaned.append(char)
        line_map.append((curr_line, curr_col))
        i += 1

    # Now run brace checking on cleaned code
    stack = []
    lines = js_code.split('\n')
    
    for idx, char in enumerate(cleaned):
        line_num, col_num = line_map[idx]
        if char in "{[(":
            stack.append((char, line_num, col_num))
        elif char in "}])":
            if not stack:
                print(f"FAIL - Unmatched closing '{char}' at line {line_num}, col {col_num}")
                # Print context
                start = max(0, line_num - 5)
                end = min(len(lines), line_num + 5)
                for j in range(start, end):
                    prefix = ">>> " if j == line_num - 1 else "    "
                    print(f"{prefix}{j+1}: {lines[j]}")
                sys.exit(1)
            
            top, l_num, c_num = stack.pop()
            if (char == "}" and top != "{") or (char == "]" and top != "[") or (char == ")" and top != "("):
                print(f"FAIL - Mismatched '{char}' at line {line_num}, col {col_num} (matches '{top}' from line {l_num}, col {c_num})")
                # Print context
                start = max(0, line_num - 5)
                end = min(len(lines), line_num + 5)
                for j in range(start, end):
                    prefix = ">>> " if j == line_num - 1 else "    "
                    print(f"{prefix}{j+1}: {lines[j]}")
                sys.exit(1)
                
    if stack:
        char, line_num, col_num = stack.pop()
        print(f"FAIL - Unclosed '{char}' from line {line_num}, col {col_num} remains open at end of file")
        sys.exit(1)
        
    print("SUCCESS - All braces, brackets, and parentheses match perfectly!")

if __name__ == "__main__":
    check_syntax()
