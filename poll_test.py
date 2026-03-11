import time, os
report = r'c:\chemgrid\docs\reports\live_visual_report.html'
out = r'c:\chemgrid\live_test_out.txt'
err = r'c:\chemgrid\live_test_err.txt'
for i in range(90):
    if os.path.exists(report):
        sz = os.path.getsize(report)
        print(f'Report ready! size={sz}')
        # print last few lines of out
        if os.path.exists(out):
            lines = open(out, encoding='utf-8', errors='ignore').readlines()
            print(''.join(lines[-10:]))
        break
    time.sleep(1)
    if i % 10 == 0:
        print(f'Waiting... {i}s')
        if os.path.exists(out):
            lines = open(out, encoding='utf-8', errors='ignore').readlines()
            if lines:
                print('  Progress:', lines[-1].strip())
else:
    print('Timeout 90s')
    for f in [out, err]:
        if os.path.exists(f):
            print(f'=== {f} ===')
            c = open(f, encoding='utf-8', errors='ignore').read()
            print(c[-800:])
