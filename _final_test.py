"""최종 PubChem API 기능 테스트"""
import sys, time
sys.path.insert(0, 'src/app')
import pubchem_client as pc

print('=== PubChem API 최종 기능 테스트 ===')
print(f'API 키: {pc.PUBCHEM_API_KEY[:8]}...')
print(f'속도 제한: {pc._rate_limiter._min_interval:.1f}초/회')
print()

tests = ['dopamine', 'serotonin', 'aspirin', 'caffeine', 'benzene']
success = 0
for mol in tests:
    t0 = time.time()
    s = pc.get_smiles_by_name(mol)
    elapsed = time.time() - t0
    status = '✓' if s else '✗'
    print(f'{status} {mol:15s}: {s or "None"}  ({elapsed:.2f}s)')
    if s:
        success += 1

print()
print(f'결과: {success}/{len(tests)} 분자 조회 성공')
print()

# autocomplete 테스트
print('[autocomplete] acetaminoph →', pc.get_suggestions('acetaminoph', limit=3))
print('[autocomplete] domin →', pc.get_suggestions('domin', limit=3))
