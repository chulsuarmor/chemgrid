#!/usr/bin/env python3
"""Mass PNG generator for Cycle 13-18 reaction mechanisms.

Generates comprehensive PNG evidence for all named reactions in Cycles 13-18
that don't yet have visual evidence PNGs.

Output: departments/domain_mechanism/evidence/cycle18_mass/
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_mass_png_generation():
    from drylab_report_exporter import _generate_mechanism_step_png

    # ═══ Cycle 13: Schmidt, Dakin, Tiffeneau-Demjanov, Paal-Knorr, Chichibabin ═══
    # ═══ Cycle 14: Neber, Lossen, Hofmann-Loffler-Freytag, Sommelet-Hauser, Stevens ═══
    # ═══ Cycle 15: Barton Reaction, Eschenmoser-Claisen, Ireland-Claisen, Overman, Rupe ═══
    # ═══ Cycle 16: Aza-Cope/Mannich, Carroll, Meyer-Schuster, Meinwald, VCP ═══
    # ═══ Cycle 17: Retro-Diels-Alder, Oxy-Cope, Mislow-Evans, Negishi, Stille ═══
    # ═══ Cycle 18: Kumada, Tebbe, Petasis, Buchwald-Hartwig, Chan-Lam ═══

    test_cases = [
        # ── Cycle 13 ──
        (
            "C13_Schmidt_cyclohexanone",
            "O=C1CCCCC1",                    # cyclohexanone
            "O=C1CCCCCN1",                   # caprolactam (ring expansion)
            "HN3, H2SO4, Schmidt",
        ),
        (
            "C13_Schmidt_acetophenone",
            "CC(=O)c1ccccc1",                # acetophenone
            "CNC(=O)c1ccccc1",               # N-methylbenzamide
            "HN3, TFA, Schmidt",
        ),
        (
            "C13_Dakin_4hydroxybenzaldehyde",
            "O=Cc1ccc(O)cc1",                # 4-hydroxybenzaldehyde
            "Oc1ccc(O)cc1",                  # hydroquinone
            "H2O2, NaOH, Dakin",
        ),
        (
            "C13_Dakin_vanillin",
            "O=Cc1ccc(O)c(OC)c1",            # vanillin
            "Oc1ccc(O)c(OC)c1",              # methoxycatechol
            "H2O2, NaOH, Dakin",
        ),
        (
            "C13_TiffeneauDemjanov_cyclopentanone",
            "O=C1CCCC1",                     # cyclopentanone
            "O=C1CCCCC1",                    # cyclohexanone
            "CH2N2, HNO2, Tiffeneau-Demjanov",
        ),
        (
            "C13_TiffeneauDemjanov_cyclobutanone",
            "O=C1CCC1",                      # cyclobutanone
            "O=C1CCCC1",                     # cyclopentanone
            "CH2N2, NaNO2/HCl, Tiffeneau-Demjanov, ring expansion",
        ),
        (
            "C13_PaalKnorr_acetonylacetone_MeNH2",
            "CC(=O)CCC(=O)C",                # 2,5-hexanedione
            "Cc1ccc(C)n1C",                  # 1,2,5-trimethylpyrrole
            "MeNH2, AcOH, Paal-Knorr",
        ),
        (
            "C13_PaalKnorr_diketone_aniline",
            "CC(=O)CCC(=O)C",                # 2,5-hexanedione
            "Cc1ccc(C)n1-c1ccccc1",          # N-phenyl-2,5-dimethylpyrrole
            "PhNH2, p-TsOH, Paal-Knorr",
        ),
        (
            "C13_Chichibabin_pyridine",
            "c1ccncc1",                      # pyridine
            "Nc1ccccn1",                     # 2-aminopyridine
            "NaNH2, 120C, Chichibabin",
        ),
        (
            "C13_Chichibabin_3methylpyridine",
            "Cc1ccncc1",                     # 3-methylpyridine (3-picoline)
            "Nc1cc(C)ccn1",                  # 2-amino-5-methylpyridine
            "NaNH2, PhNMe2, Chichibabin",
        ),

        # ── Cycle 14 ──
        (
            "C14_Neber_oxime_tosylate",
            "CC(=NOC)C(=O)C",                # oxime tosylate (approx)
            "CC(=O)C(C)N",                   # alpha-amino ketone
            "KOEt, Neber",
        ),
        (
            "C14_Neber_acetophenone_oxime",
            "CC(=NOS(=O)(=O)c1ccc(C)cc1)c1ccccc1",  # acetophenone oxime tosylate
            "NC(C(=O)c1ccccc1)C",            # alpha-amino ketone
            "NaOEt, EtOH, Neber",
        ),
        (
            "C14_Lossen_acetohydroxamic",
            "CC(=O)NO",                      # acetohydroxamic acid
            "CN",                            # methylamine
            "Ac2O, Et3N, Lossen",
        ),
        (
            "C14_Lossen_benzohydroxamic",
            "O=C(NO)c1ccccc1",               # benzohydroxamic acid
            "Nc1ccccc1",                     # aniline
            "TsCl, NaOH, Lossen",
        ),
        (
            "C14_HofmannLofflerFreytag_Nchloroamine",
            "ClN(C)CCCC",                    # N-chloro-N-methylpentylamine
            "CN1CCCC1",                      # N-methylpyrrolidine
            "hv, H2SO4, NaOH, Hofmann-Loffler-Freytag",
        ),
        (
            "C14_HofmannLofflerFreytag_Nchloropiperidine",
            "ClN(C)CCCCC",                   # N-chloro-N-methylhexylamine
            "CN1CCCCC1",                     # N-methylpiperidine
            "hv, Fe2+, NaOH, Loffler-Freytag",
        ),
        (
            "C14_SommeletHauser_benzyltrimethylammonium",
            "C[N+](C)(C)Cc1ccccc1",          # benzyltrimethylammonium
            "CN(C)Cc1ccccc1C",               # ortho-methylated product
            "NaNH2, Sommelet-Hauser, benzyl",
        ),
        (
            "C14_SommeletHauser_2",
            "C[N+](C)(C)Cc1ccc(C)cc1",       # 4-Me-benzyltrimethylammonium
            "CN(C)Cc1cc(C)ccc1C",            # ortho-methyl product
            "NaNH2, Sommelet-Hauser, benzyl",
        ),
        (
            "C14_Stevens_ammonium_ylide",
            "C[N+](C)(Cc1ccccc1)CC=C",       # benzylic quaternary ammonium
            "C=CCN(C)Cc1ccccc1",             # rearranged tertiary amine
            "NaH, THF, Stevens rearrangement",
        ),
        (
            "C14_Stevens_2",
            "C[N+]1(CC=C)CCc2ccccc21",       # quaternary indolinium
            "C(=C)CN1CCc2ccccc21",           # rearranged product
            "KOtBu, Stevens rearrangement, [1,2]-shift, ammonium ylide",
        ),

        # ── Cycle 15 ──
        (
            "C15_Barton_reaction_nitrite",
            "CCCCCON=O",                     # hexyl nitrite
            "OC(=NO)CCCC",                   # delta-oximo alcohol
            "hv, Barton reaction, barton nitrite",
        ),
        (
            "C15_Barton_steroid_nitrite",
            "CC1(ON=O)CCC2CCCCC2C1",         # steroid-like nitrite (simplified)
            "CC1(O)CCC2CCC(=NO)CC2C1",       # delta-oximo product
            "hv, 254nm, Barton photolysis",
        ),
        (
            "C15_EschenmoserClaisen_allyl_alcohol",
            "OCC=C",                         # allyl alcohol
            "C=CCC(=O)N(C)C",               # gamma,delta-unsaturated amide
            "MeC(OMe)2NMe2, xylene, 140C, Eschenmoser-Claisen",
        ),
        (
            "C15_EschenmoserClaisen_crotyl",
            "O/C=C/C",                       # crotyl alcohol (approx: 2-butenol)
            "C=C(C)CC(=O)N(C)C",             # unsaturated amide product
            "DMA dimethyl acetal, Eschenmoser-Claisen",
        ),
        (
            "C15_IrelandClaisen_allyl_propanoate",
            "C=CCOC(=O)CC",                  # allyl propanoate
            "C=CCC(C)C(=O)O",               # pentenoic acid derivative
            "LDA, TMSCl, -78C, Ireland-Claisen",
        ),
        (
            "C15_IrelandClaisen_crotyl_acetate",
            "CC=CCOC(=O)C",                  # crotyl acetate
            "C=C(C)CC(=O)O",                # acid product
            "LDA, TMSCl, THF, Ireland-Claisen",
        ),
        (
            "C15_Overman_allylic_trichloroacetimidate",
            "OCC=C",                         # allyl alcohol (substrate for imidate)
            "NCC=C",                         # allylic amine (simplified)
            "Cl3CC#N, heat, Overman rearrangement",
        ),
        (
            "C15_Rupe_propargyl_alcohol",
            "CC(O)(C)C#CC",                  # 2-methyl-3-pentyn-2-ol
            "CC(=O)/C=C\\C",                 # alpha,beta-unsaturated ketone
            "H2SO4, Rupe rearrangement",
        ),

        # ── Cycle 16 ──
        (
            "C16_AzaCopeMannich",
            "C=CCC(N)CC=O",                  # amino-aldehyde-alkene
            "OC1CCNCC1",                     # piperidinol
            "H+, Aza-Cope/Mannich, Aza-Cope",
        ),
        (
            "C16_AzaCopeMannich_2",
            "C=CCC(NCC)CC=O",                # N-ethyl variant
            "OC1CCN(CC)CC1",                 # N-ethylpiperidinol
            "AcOH, 2-Aza-Cope, Mannich, Cope",
        ),
        (
            "C16_Carroll_betaketoester",
            "CC(=O)CC(=O)OCC=C",             # allyl acetoacetate
            "CC(=O)CC(C)C=C",               # gamma,delta-unsaturated ketone
            "heat, 200C, Carroll",
        ),
        (
            "C16_Carroll_2",
            "CC(=O)CC(=O)OC/C=C/C",          # crotyl acetoacetate
            "CC(=O)CC(/C=C/C)C",             # Carroll product
            "Pd(PPh3)4, Carroll rearrangement",
        ),
        (
            "C16_MeyerSchuster_propargyl_alcohol",
            "OC(C)(C)C#CC",                  # 2-methyl-3-pentyn-2-ol
            "CC(/C=O)=C\\C",                 # alpha,beta-unsaturated aldehyde
            "H2SO4, Meyer-Schuster",
        ),
        (
            "C16_MeyerSchuster_secondary",
            "OC(C)C#C",                      # 3-butyn-2-ol
            "CC=CC=O",                       # crotonaldehyde
            "Au(PPh3)Cl, AgOTf, Meyer-Schuster rearrangement",
        ),
        (
            "C16_Meinwald_styrene_oxide",
            "C(O1)C1c1ccccc1",               # styrene oxide
            "O=CCc1ccccc1",                  # phenylacetaldehyde
            "BF3.OEt2, Meinwald",
        ),
        (
            "C16_Meinwald_cyclohexene_oxide",
            "C1CCC2OC2C1",                   # cyclohexene oxide
            "O=CC1CCCCC1",                   # cyclohexanecarboxaldehyde (approx)
            "H2SO4, Meinwald rearrangement",
        ),
        (
            "C16_VCP_vinylcyclopropane",
            "C=CC1CC1",                      # vinylcyclopropane
            "C1CC=CC1",                      # cyclopentene
            "heat, 300C, VCP rearrangement, vinylcyclopropane",
        ),
        (
            "C16_VCP_donor_acceptor",
            "C=CC1(C(=O)OC)CC1C(=O)OC",     # donor-acceptor VCP
            "C1(C(=O)OC)C(C(=O)OC)C=CC1",   # cyclopentene product
            "Rh2(OAc)4, VCP, vinyl cyclopropane rearrangement",
        ),

        # ── Cycle 17 ──
        (
            "C17_RetroDielsAlder_norbornene",
            "C1CC2CC1C=C2",                  # norbornene
            "C=CC=CC=C",                     # 1,3-butadiene + ethylene (simplified)
            "FVP, 500C, retro-Diels-Alder",
        ),
        (
            "C17_RetroDielsAlder_cyclohexene",
            "C1CC=CCC1",                     # cyclohexene
            "C=CC=C.C=C",                    # butadiene + ethylene
            "heat, 600C, retro Diels-Alder",
        ),
        (
            "C17_OxyCope_15dien3ol",
            "C=CC(O)CC=C",                   # 1,5-dien-3-ol
            "O=CCCCC=C",                     # unsaturated aldehyde
            "KH, 18-crown-6, THF, Oxy-Cope rearrangement",
        ),
        (
            "C17_OxyCope_anionic",
            "C=CC(O)(C)CC=C",                # 3-methyl-1,5-dien-3-ol
            "O=C(C)CCCC=C",                 # unsaturated ketone
            "KH, anionic Oxy-Cope",
        ),
        (
            "C17_MislowEvans_phenylselenide",
            "CC([Se]c1ccccc1)C",             # alkyl phenyl selenide
            "CC=C",                          # propene
            "H2O2, Mislow-Evans, selenoxide elimination",
        ),
        (
            "C17_MislowEvans_sulfoxide",
            "CC(S(=O)c1ccccc1)CC",           # phenyl sulfoxide
            "CC=CC",                         # 2-butene
            "heat, 80C, Mislow-Evans, sulfoxide elimination, syn-elimination",
        ),
        (
            "C17_Negishi_PhBr_MeZnCl",
            "Brc1ccccc1",                    # bromobenzene
            "Cc1ccccc1",                     # toluene
            "MeZnCl, Pd(PPh3)4, THF, Negishi",
        ),
        (
            "C17_Negishi_aryl_vinyl",
            "Brc1ccc(C)cc1",                 # 4-bromotoluene
            "C=Cc1ccc(C)cc1",               # 4-methylstyrene
            "CH2=CHZnBr, Pd(PPh3)4, Negishi coupling",
        ),
        (
            "C17_Stille_PhI_vinylSnBu3",
            "Ic1ccccc1",                     # iodobenzene
            "C=Cc1ccccc1",                  # styrene
            "CH2=CHSnBu3, Pd(PPh3)4, LiCl, DMF, Stille",
        ),
        (
            "C17_Stille_acylchloride",
            "O=C(Cl)c1ccccc1",               # benzoyl chloride
            "O=C(/C=C)c1ccccc1",             # phenyl vinyl ketone
            "CH2=CHSnBu3, Pd2(dba)3, Stille coupling",
        ),

        # ── Cycle 18 ──
        (
            "C18_Kumada_PhBr_MeMgBr",
            "Brc1ccccc1",                    # bromobenzene
            "Cc1ccccc1",                     # toluene
            "MeMgBr, NiCl2(dppf), THF, Kumada",
        ),
        (
            "C18_Kumada_vinyl",
            "Clc1ccc(C)cc1",                 # 4-chlorotoluene
            "C=Cc1ccc(C)cc1",               # 4-methylstyrene
            "CH2=CHMgBr, Pd(dppf)Cl2, Kumada coupling",
        ),
        (
            "C18_Tebbe_cyclohexanone",
            "O=C1CCCCC1",                    # cyclohexanone
            "C=C1CCCCC1",                   # methylenecyclohexane
            "Cp2TiCH2, pyridine, Tebbe olefination",
        ),
        (
            "C18_Tebbe_ester",
            "CC(=O)OCC",                     # ethyl acetate
            "C=C(C)OCC",                    # ethyl vinyl ether (enol ether)
            "Cp2Ti=CH2, Tebbe, Petasis reagent",
        ),
        (
            "C18_Petasis_glycine",
            "OCC=O",                         # glycolaldehyde
            "OCC(N)c1ccccc1",               # alpha-amino alcohol
            "PhB(OH)2, MeNH2, Petasis reaction, borono-Mannich",
        ),
        (
            "C18_Petasis_salicylaldehyde",
            "O=Cc1ccccc1O",                  # salicylaldehyde
            "OC(c1ccccc1)c1ccccc1O",         # alpha-aryl aminol (simplified)
            "PhB(OH)2, piperidine, Petasis borono-Mannich",
        ),
        (
            "C18_BuchwaldHartwig_PhBr_morpholine",
            "Brc1ccccc1",                    # bromobenzene
            "c1ccc(N2CCOCC2)cc1",            # N-phenylmorpholine
            "morpholine, Pd2(dba)3, XPhos, NaOtBu, Buchwald-Hartwig",
        ),
        (
            "C18_BuchwaldHartwig_arylchloride",
            "Clc1ccc(C(F)(F)F)cc1",          # 4-chlorobenzotrifluoride
            "c1cc(C(F)(F)F)ccc1NC1CCCCC1",   # N-cyclohexyl product
            "cyclohexylamine, Pd(OAc)2, BINAP, Cs2CO3, Buchwald-Hartwig amination",
        ),
        (
            "C18_ChanLam_PhBOH2_morpholine",
            "OB(O)c1ccccc1",                 # phenylboronic acid
            "c1ccc(N2CCOCC2)cc1",            # N-phenylmorpholine
            "morpholine, Cu(OAc)2, Et3N, air, Chan-Lam",
        ),
        (
            "C18_ChanLam_imidazole",
            "OB(O)c1ccc(OC)cc1",             # 4-methoxyphenylboronic acid
            "c1cc(OC)ccc1n1ccnc1",           # N-aryl imidazole
            "imidazole, Cu(OAc)2, pyridine, Chan-Lam coupling",
        ),
    ]

    output_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                              'departments', 'domain_mechanism', 'evidence', 'cycle18_mass')
    os.makedirs(output_dir, exist_ok=True)

    results = []
    total_bytes = 0
    t0 = time.time()

    for name, rsmi, psmi, cond in test_cases:
        print(f"\n{'='*60}")
        print(f"  [{len(results)+1}/{len(test_cases)}] {name}")
        print(f"  R: {rsmi}")
        print(f"  P: {psmi}")
        print(f"  Cond: {cond}")
        print(f"{'='*60}")

        try:
            png_bytes = _generate_mechanism_step_png(rsmi, psmi, cond)
            if png_bytes:
                out_path = os.path.join(output_dir, f'{name}.png')
                with open(out_path, 'wb') as f:
                    f.write(png_bytes)
                fsize = len(png_bytes)
                total_bytes += fsize
                fsize_kb = fsize / 1024
                print(f"  PASS: {fsize_kb:.0f} KB -> {out_path}")
                results.append((name, 'PASS', f'{fsize_kb:.0f}KB'))
            else:
                print(f"  FAIL: render returned None")
                results.append((name, 'FAIL', 'render=None'))
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, 'ERROR', str(e)[:80]))

    elapsed = time.time() - t0

    # ── Summary ──
    print(f"\n{'='*60}")
    print("  MASS PNG GENERATION SUMMARY")
    print(f"{'='*60}")
    total_pass = sum(1 for r in results if r[1] == 'PASS')
    total_fail = sum(1 for r in results if r[1] == 'FAIL')
    total_err = sum(1 for r in results if r[1] == 'ERROR')

    for name, status, info in results:
        icon = 'PASS' if status == 'PASS' else 'FAIL'
        print(f"  [{icon}] {name}: {status} ({info})")

    print(f"\n  Total: {total_pass} PASS / {total_fail} FAIL / {total_err} ERROR  "
          f"({len(test_cases)} total)")
    print(f"  Total size: {total_bytes/1024/1024:.1f} MB")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"  Output dir: {output_dir}")

    return total_pass, total_fail, total_err, len(test_cases)


if __name__ == '__main__':
    p, f, e, t = test_mass_png_generation()
    print(f"\nFinal: {p}/{t} PASS")
    sys.exit(0 if f == 0 and e == 0 else 1)
