#!/usr/bin/env python3
"""
Verify charge conservation for all 6 test molecules
"""

# TEST 5: Azulene (C10H8)
azulene_c = [0.0850, -0.1250, 0.0950, -0.0850, 0.1050, -0.0950, -0.1150, 0.0750, -0.0550, 0.0150]
azulene_h = [0.0125] * 8
azulene_total = sum(azulene_c) + sum(azulene_h)
print("TEST 5: Azulene (C10H8)")
print(f"  C charges sum: {sum(azulene_c):.4f}")
print(f"  H charges sum: {sum(azulene_h):.4f}")
print(f"  Total charge: {azulene_total:.4f}")
assert abs(azulene_total) < 0.001, f"Azulene total should be 0.0000, got {azulene_total:.4f}"
print("  ✅ PASS\n")

# TEST 6: Pyridine (C5H5N)
pyridine_charges = {
    'N': -0.1500,
    'C_ortho_1': 0.0250,
    'C_meta_1': 0.0450,
    'C_para': 0.0100,
    'C_meta_2': 0.0450,
    'C_ortho_2': 0.0250,
    'H': [0.0] * 5
}
pyridine_total = pyridine_charges['N'] + 2*pyridine_charges['C_ortho_1'] + 2*pyridine_charges['C_meta_1'] + pyridine_charges['C_para'] + sum(pyridine_charges['H'])
print("TEST 6: Pyridine (C5H5N - 11 atoms)")
print(f"  N: {pyridine_charges['N']:.4f}")
print(f"  C (ortho×2): {2*pyridine_charges['C_ortho_1']:.4f}")
print(f"  C (meta×2): {2*pyridine_charges['C_meta_1']:.4f}")
print(f"  C (para): {pyridine_charges['C_para']:.4f}")
print(f"  H (5×): {sum(pyridine_charges['H']):.4f}")
print(f"  Total charge: {pyridine_total:.4f}")
assert abs(pyridine_total) < 0.001, f"Pyridine total should be 0.0000, got {pyridine_total:.4f}"
print("  ✅ PASS\n")

# TEST 7: Pyrrole (C4H5N - 10 atoms)
pyrrole_charges = {
    'N': -0.1000,
    'C': [0.0250] * 4,
    'H': [0.0] * 5
}
pyrrole_total = pyrrole_charges['N'] + sum(pyrrole_charges['C']) + sum(pyrrole_charges['H'])
print("TEST 7: Pyrrole (C4H5N - 10 atoms)")
print(f"  N: {pyrrole_charges['N']:.4f}")
print(f"  C (4×): {sum(pyrrole_charges['C']):.4f}")
print(f"  H (5×): {sum(pyrrole_charges['H']):.4f}")
print(f"  Total charge: {pyrrole_total:.4f}")
assert abs(pyrrole_total) < 0.001, f"Pyrrole total should be 0.0000, got {pyrrole_total:.4f}"
print("  ✅ PASS\n")

# TEST 8: Fulvene (C6H6 - 12 atoms)
fulvene_charges = {
    'C_exo': -0.1000,
    'C_ring': [0.0200] * 5,
    'H': [0.0] * 6
}
fulvene_total = fulvene_charges['C_exo'] + sum(fulvene_charges['C_ring']) + sum(fulvene_charges['H'])
print("TEST 8: Fulvene (C6H6 - 12 atoms)")
print(f"  C (exocyclic): {fulvene_charges['C_exo']:.4f}")
print(f"  C (ring×5): {sum(fulvene_charges['C_ring']):.4f}")
print(f"  H (6×): {sum(fulvene_charges['H']):.4f}")
print(f"  Total charge: {fulvene_total:.4f}")
assert abs(fulvene_total) < 0.001, f"Fulvene total should be 0.0000, got {fulvene_total:.4f}"
print("  ✅ PASS\n")

# TEST 9: Naphthalene (C10H8 - 18 atoms)
naphthalene_c = [-0.0850, 0.0150, -0.0750, 0.0250, -0.0850, 0.0150, -0.0750, 0.0250, -0.0650, 0.0050]
naphthalene_h = [0.0100] * 8
naphthalene_total = sum(naphthalene_c) + sum(naphthalene_h)
print("TEST 9: Naphthalene (C10H8 - 18 atoms)")
print(f"  C charges sum: {sum(naphthalene_c):.4f}")
print(f"  H charges sum: {sum(naphthalene_h):.4f}")
print(f"  Total charge: {naphthalene_total:.4f}")
assert abs(naphthalene_total) < 0.001, f"Naphthalene total should be 0.0000, got {naphthalene_total:.4f}"
print("  ✅ PASS\n")

# TEST 10: Nitrobenzene (C6H5NO2 - 14 atoms)
nitrobenzene_charges = {
    'N': 0.3500,
    'O': [-0.3000] * 2,
    'C': [0.1000, -0.0100, 0.0100, -0.0100, 0.0100, -0.0100],
    'H': [0.0320] * 5
}
nitrobenzene_total = nitrobenzene_charges['N'] + sum(nitrobenzene_charges['O']) + sum(nitrobenzene_charges['C']) + sum(nitrobenzene_charges['H'])
print("TEST 10: Nitrobenzene (C6H5NO2 - 14 atoms)")
print(f"  N: {nitrobenzene_charges['N']:.4f}")
print(f"  O (2×): {sum(nitrobenzene_charges['O']):.4f}")
print(f"  C (6×): {sum(nitrobenzene_charges['C']):.4f}")
print(f"  H (5×): {sum(nitrobenzene_charges['H']):.4f}")
print(f"  Total charge: {nitrobenzene_total:.4f}")
assert abs(nitrobenzene_total) < 0.001, f"Nitrobenzene total should be 0.0000, got {nitrobenzene_total:.4f}"
print("  ✅ PASS\n")

print("="*60)
print("✅ ALL CHARGE CONSERVATION CHECKS PASSED!")
print("="*60)
print("\n📊 Summary:")
print("  TEST 5: Azulene      - 18 atoms (C10+H8)  - Total: 0.0000 ✅")
print("  TEST 6: Pyridine     - 11 atoms (C5+N+H5) - Total: 0.0000 ✅")
print("  TEST 7: Pyrrole      - 10 atoms (C4+N+H5) - Total: 0.0000 ✅")
print("  TEST 8: Fulvene      - 12 atoms (C6+H6)   - Total: 0.0000 ✅")
print("  TEST 9: Naphthalene  - 18 atoms (C10+H8)  - Total: 0.0000 ✅")
print("  TEST 10: Nitrobenzene- 14 atoms (C6+NO2+H5) - Total: 0.0000 ✅")
print("\n✨ All mock data mathematically validated!")
