# Skill: PDF Export Testing

## Key Points
1. **Building block molecules** (Phenol, Aniline, Benzene, etc.) return 0-step routes. Don't test PDF export on these -- use complex molecules instead.
2. **Minimum file size**: Valid PDFs with molecule images should be >10KB. 1-step routes produce ~38KB, 3-step routes ~62KB.
3. **PYTHONIOENCODING=utf-8** is required when running tests from bash on Windows (cp949 codec fails on Unicode characters like em-dash).
4. **Korean font**: malgun.ttf at `C:/Windows/Fonts/malgun.ttf` works. Registered as "KoreanGothic" in reportlab.
5. **Snake layout** works correctly for multi-step routes -- verified with Caffeine (3 steps).

## Good Test Molecules (NOT building blocks)
- Aspirin: CC(=O)Oc1ccccc1C(=O)O (1-step route)
- Caffeine: Cn1cnc2c1c(=O)n(C)c(=O)n2C (3-step route)
- Ibuprofen: CC(C)Cc1ccc(C(C)C(=O)O)cc1 (2-step route)
- Lidocaine: CCN(CC)CC(=O)Nc1c(C)cccc1C
- Paracetamol: CC(=O)Nc1ccc(O)cc1
