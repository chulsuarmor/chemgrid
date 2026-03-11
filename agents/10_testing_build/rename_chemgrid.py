"""
명령 3 STEP 1: ChemDraw → ChemGrid 전체 이름 변경
integrated/ 폴더 내 모든 .py 파일에서 교체
"""
import os

INTEGRATED = r"c:\chemgrid\agents\10_testing_build\integrated"

print("=" * 60)
print("ChemDraw → ChemGrid 이름 변경")
print("=" * 60)

changed_files = []
total_replacements = 0

for f in sorted(os.listdir(INTEGRATED)):
    if not f.endswith('.py'):
        continue
    
    path = os.path.join(INTEGRATED, f)
    with open(path, encoding='utf-8') as fh:
        content = fh.read()
    
    new_content = content
    new_content = new_content.replace('ChemDraw', 'ChemGrid')
    new_content = new_content.replace('chemdraw', 'chemgrid')
    new_content = new_content.replace('CHEMDRAW', 'CHEMGRID')
    
    if content != new_content:
        # 교체 횟수 계산
        count = (
            content.count('ChemDraw') - new_content.count('ChemDraw') +
            content.count('chemdraw') - new_content.count('chemdraw') +
            content.count('CHEMDRAW') - new_content.count('CHEMDRAW')
        )
        # Actually count properly
        count = content.count('ChemDraw') + content.count('chemdraw') + content.count('CHEMDRAW')
        
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(new_content)
        
        changed_files.append((f, count))
        total_replacements += count
        print(f"  ✅ {f}: {count}건 교체")

if not changed_files:
    print("  ℹ️  ChemDraw 문자열 없음 (이미 교체됨)")
else:
    print(f"\n변경: {len(changed_files)}개 파일, 총 {total_replacements}건 교체")

# 검증: 잔존 확인
print()
print("=" * 60)
print("검증: ChemDraw 잔존 확인")
print("=" * 60)

remain = 0
for f in sorted(os.listdir(INTEGRATED)):
    if not f.endswith('.py'):
        continue
    
    path = os.path.join(INTEGRATED, f)
    with open(path, encoding='utf-8') as fh:
        for i, line in enumerate(fh, 1):
            for keyword in ['ChemDraw', 'chemdraw', 'CHEMDRAW']:
                if keyword in line:
                    # 주석 내 허용 (# 기호 뒤)
                    print(f"  ⚠️  {f}:{i}: {line.rstrip()[:80]}")
                    remain += 1

if remain == 0:
    print("  ✅ ChemDraw 잔존 없음 — 모두 ChemGrid로 교체 완료")
else:
    print(f"\n  ⚠️  잔존: {remain}건")
