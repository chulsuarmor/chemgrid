#!/usr/bin/env python3
import sys

try:
    with open('_source/draw.py', 'r', encoding='utf-8') as f:
        code = f.read()
    compile(code, '_source/draw.py', 'exec')
    with open('diagnosis.txt', 'w') as f:
        f.write("✅ Syntax OK\n")
except SyntaxError as e:
    with open('diagnosis.txt', 'w') as f:
        f.write(f"SyntaxError at line {e.lineno}: {e.msg}\n")
        if e.text:
            f.write(f"Text: {e.text}\n")
            f.write(f"Offset: {e.offset}\n")
except Exception as e:
    with open('diagnosis.txt', 'w') as f:
        f.write(f"Error: {type(e).__name__}: {e}\n")
