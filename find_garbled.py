
import os
import re

def check(path):
    print(f'\nChecking {path}...')
    if not os.path.exists(path):
        print(f"File {path} not found.")
        return
    with open(path, 'rb') as f:
        content = f.read()
    
    # Try multiple decodings
    text = content.decode('utf-8', errors='replace')
    
    # Check for 4+ question marks
    for m in re.finditer(r'\?{4,}', text):
        line_no = text[:m.start()].count('\n') + 1
        print(f'Line {line_no}: Found "????": {text[text.rfind("\n", 0, m.start())+1 : text.find("\n", m.start())].strip()}')
        
    # Check for non-standard chars and \ufffd
    lines_reported = set()
    for i, char in enumerate(text):
        cp = ord(char)
        line_no = text[:i].count('\n') + 1
        if line_no in lines_reported: continue
        
        if cp == 0xfffd:
            print(f'Line {line_no}: Found replacement char \\ufffd')
            lines_reported.add(line_no)
        elif cp > 127:
            # Common CJK and symbols
            is_cjk = (0x4e00 <= cp <= 0x9fff) or (0x3000 <= cp <= 0x303f) or (0xff00 <= cp <= 0xffef) or (0x2000 <= cp <= 0x206f)
            if not is_cjk:
                line_start = text.rfind('\n', 0, i) + 1
                line_end = text.find('\n', i)
                if line_end == -1: line_end = len(text)
                line_text = text[line_start:line_end]
                print(f'Line {line_no}: Potential garbled char "{char}" (U+{cp:04X}): {line_text.strip()}')
                lines_reported.add(line_no)

check('ChatDBServer/server.py')
check('ChatDBServer/static/js/chat.js')
