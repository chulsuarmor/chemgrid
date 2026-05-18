#!/usr/bin/env python3
"""Quick verification: curved arrow rendering for 5 named reactions.

Output: departments/domain_mechanism/evidence/arrow_verify/
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from drylab_report_exporter import _generate_mechanism_step_png

test_cases = [
    ("BuchwaldHartwig", "c1ccc(cc1)Br", "c1ccc(cc1)N1CCCCC1", "Pd(OAc)2, BINAP, NaOtBu, Buchwald-Hartwig"),
    ("Negishi", "c1ccc(cc1)Br", "c1ccc(cc1)C", "MeZnCl, Pd(PPh3)4, Negishi"),
    ("IrelandClaisen", "C=CCOC(=O)CC", "C=CCC(CC)C(=O)O", "LDA, TMSCl, Ireland-Claisen"),
    ("Suzuki", "c1ccc(cc1)Br", "c1ccc(-c2ccccc2)cc1", "PhB(OH)2, Pd(PPh3)4, K2CO3, Suzuki"),
    ("ChanLam", "c1ccc(cc1)B(O)O", "c1ccc(cc1)N1CCCCC1", "morpholine, Cu(OAc)2, Et3N, Chan-Lam"),
]

output_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                          'departments', 'domain_mechanism', 'evidence', 'arrow_verify')
os.makedirs(output_dir, exist_ok=True)

for name, rsmi, psmi, cond in test_cases:
    try:
        png = _generate_mechanism_step_png(rsmi, psmi, cond)
        if png and len(png) > 100:
            path = os.path.join(output_dir, f'{name}.png')
            with open(path, 'wb') as f:
                f.write(png)
            print(f"OK {name}: {len(png)/1024:.1f}KB")
        else:
            print(f"FAIL {name}: empty or too small ({len(png) if png else 0} bytes)")
    except Exception as e:
        print(f"ERROR {name}: {e}")

print("\nDone. Files in:", os.path.abspath(output_dir))
