#!/usr/bin/env python3
import sys
sys.path.insert(0, '_source')

try:
    compile(open('_source/draw.py').read(), 'draw.py', 'exec')
    print("OK")
except SyntaxError as e:
    print(f"Line {e.lineno}: {e.msg}")
    if e.text:
        print(f"  {e.text.strip()}")
        print(f"  {' ' * (e.offset - 1)}^")
