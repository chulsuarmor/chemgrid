# domain_synthesis Mistakes Log

## [2026-03-19] EAS Bromination: No Gold Standard Mechanism
- **Status**: Known limitation (not a code bug)
- **Issue**: `reaction_mechanisms.py` has no hardcoded EAS bromination mechanism. Auto-generated mechanism collapses 3-step EAS (sigma complex intermediate) to 1-step concerted representation.
- **Impact**: Mechanism is functionally correct (correct bond changes) but educationally oversimplified.
- **Action**: Future cascade should add gold standard EAS mechanism with: (1) pi-complex formation, (2) sigma complex (arenium ion), (3) proton loss/rearomatization.

## [2026-03-19] Ester Hydrolysis: Simplified to Single Step
- **Status**: Known limitation
- **Issue**: Auto-generated ester hydrolysis mechanism shows direct C-O bond swap instead of proper tetrahedral intermediate pathway.
- **Impact**: Same as EAS -- functional but educationally incomplete.
- **Action**: Add gold standard acid/base-catalyzed ester hydrolysis mechanism.

## [2026-03-19] Building Block Molecules: PDF Export Returns False
- **Status**: Expected behavior (not a bug)
- **Issue**: Phenol and Aniline are registered building blocks, so retrosynthesis returns 0-step routes. PDF exporter correctly rejects empty routes.
- **Lesson**: When testing PDF export, choose target molecules that are NOT building blocks, or handle the "already a building block" case explicitly.
