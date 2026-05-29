# scratch/view_html_line.py
import urllib.request

def view_line():
    url = "http://127.0.0.1:18080/"
    try:
        with urllib.request.urlopen(url) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching HTML: {e}")
        return
        
    lines = html.split('\n')
    print(f"Total HTML lines: {len(lines)}")
    
    # Safely print lines 1795 to 1805 (1-based index)
    for i in range(1790, 1810):
        if i < len(lines):
            line = lines[i]
            escaped_line = line.encode('ascii', 'backslashreplace').decode('ascii')
            prefix = ">>> " if i == 1799 else "    "
            print(f"{prefix}{i+1}: {escaped_line}")
            if i == 1799:
                print("Char codes in line 1800:")
                for col, char in enumerate(line, 1):
                    print(f"  Col {col}: {repr(char)} (code: {ord(char)})")

if __name__ == "__main__":
    view_line()
