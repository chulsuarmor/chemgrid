# renderer.py 핵심 함수 전체 코드 (v3.2 Final)

@staticmethod
def draw_clouds(painter, results, use_theory_coords=False, densities: List[ElectronicDensity] = None):
    if not results: return
    charges, islands = results.get("charges", {}), results.get("islands", [])
    aromatic, atoms = results.get("aromatic", set()), results.get("atoms", {})
    bonds = results.get("bonds", {})

    print(f"\n{'='*70}")
    print(f"[v3.2 Renderer] draw_clouds called")
    print(f"  Total atoms: {len(charges)}")
    print(f"  use_theory_coords: {use_theory_coords}")
    print(f"{'='*70}")

    atom_is_size = {}
    for isl in islands:
        for a in isl: atom_is_size[a] = len(isl)

    base_alpha = VISUAL_SETTINGS.get("cloud_opacity", 140)
    ch_weight = 6.0

    # ========== 로컬 대비: 고리 탄소만의 min/max 기준 ==========
    if charges:
        global_min = min(charges.values())
        global_max = max(charges.values())

        ring_carbon_charges = []
        for pt_key, charge in charges.items():
            at_main = atoms.get(pt_key, {}).get("main", "C")
            is_ring_atom = (pt_key in aromatic or atom_is_size.get(pt_key, 0) >= 2)
            if at_main == "C" and is_ring_atom:
                ring_carbon_charges.append(charge)

        if ring_carbon_charges:
            ring_min = min(ring_carbon_charges)
            ring_max = max(ring_carbon_charges)
            ring_avg_charge = sum(ring_carbon_charges) / len(ring_carbon_charges)

            min_charge = ring_min
            max_charge = ring_max
            charge_range = max(abs(ring_min), abs(ring_max), 0.01)

            print(f"\n[v3.2 LOCAL CONTRAST]")
            print(f"  전체 분자: min={global_min:+.3f}, max={global_max:+.3f}")
            print(f"  고리 탄소: min={ring_min:+.3f}, max={ring_max:+.3f}, avg={ring_avg_charge:+.3f}")
            print(f"  → 색상 범위: {charge_range:.3f} (고리 기준)")
        else:
            min_charge, max_charge, charge_range = -0.5, 0.5, 0.5
            ring_avg_charge = 0.0
    else:
        min_charge, max_charge, charge_range = -0.5, 0.5, 0.5
        ring_avg_charge = 0.0

    bond_lengths = []
    if bonds:
        for (k1, k2), _ in bonds.items():
            dist = math.sqrt((k1[0] - k2[0])**2 + (k1[1] - k2[1])**2)
            bond_lengths.append(dist)

    avg_bond_length = sum(bond_lengths) / len(bond_lengths) if bond_lengths else 40.0
    max_cloud_radius = avg_bond_length * 0.25

    density_values = []
    if densities:
        for d in densities:
            density_values.append(d.density)

    min_density = min(density_values) if density_values else 0.0
    max_density = max(density_values) if density_values else 1.0

    substituent_atoms = []
    ring_atoms = []

    for pt_key, charge in charges.items():
        at_main = atoms.get(pt_key, {}).get("main", "C")
        is_ring_atom = (pt_key in aromatic or atom_is_size.get(pt_key, 0) >= 2)

        if at_main in ["O", "N", "F", "Cl", "Br", "S", "P"] and not is_ring_atom:
            substituent_atoms.append(pt_key)
        else:
            ring_atoms.append(pt_key)

    render_order = substituent_atoms + ring_atoms
    electron_rich_carbons = []

    for pt_key in render_order:
        charge = charges[pt_key]
        at_main = atoms.get(pt_key, {}).get("main", "C")
        at_lookup = at_main if at_main and at_main != "C" else "C"
        el_data = ELEMENT_DATA.get(at_lookup, ELEMENT_DATA["C"])

        atom_density = None
        if densities:
            for d in densities:
                d_pos = (round(d.position[0], 2), round(d.position[1], 2))
                if d_pos == pt_key:
                    atom_density = d
                    break

        is_substituent_atom = (at_main in ["O", "N", "F", "Cl", "Br", "S", "P"] and
                               pt_key not in aromatic and
                               atom_is_size.get(pt_key, 0) < 2)

        if at_main == "H":
            is_polar_h = False
            for bond_pair in results.get("bonds", {}).keys():
                if pt_key in bond_pair:
                    neighbor = bond_pair[1] if bond_pair[0] == pt_key else bond_pair[0]
                    n_main = atoms.get(neighbor, {}).get("main", "")
                    if n_main in ["N", "O", "F"]:
                        is_polar_h = True; break

            if is_polar_h:
                c_scale, d_scale = 0.38, 1.3
            else:
                c_scale, d_scale = 0.5, 0.5
        elif is_substituent_atom:
            base_c_scale = el_data.get("cloud_scale", 1.0)
            c_scale = base_c_scale * 0.80
            d_scale = el_data.get("density_scale", 1.0) * 1.5
        else:
            c_scale = el_data.get("cloud_scale", 1.0)
            d_scale = el_data.get("density_scale", 1.0)

        if use_theory_coords:
            t_map = results.get("theory_data", {}).get("map", {})
            lookup_key = (round(pt_key[0], 2), round(pt_key[1], 2))
            center = t_map.get(lookup_key, QPointF(*pt_key))
        else:
            center = QPointF(*pt_key)

        isl_size = atom_is_size.get(pt_key, 0)

        raw_strength = (2.2) if pt_key in aromatic else (0.85 if isl_size >= 2 else 0.0)
        strength = math.sqrt(raw_strength) * 1.3

        # ========== 선형 증폭 (로그 제거) ==========
        charge_intensity = abs(charge - ring_avg_charge) * 100.0 * d_scale
        charge_intensity = min(charge_intensity, 5.0)

        if charge_intensity < 0.1 and strength < 0.1: continue

        is_ring_carbon = (at_main == "C" and (pt_key in aromatic or isl_size >= 2))

        if is_ring_carbon:
            charge_deviation = charge - ring_avg_charge
            reactivity_weight = min(math.exp(abs(charge_deviation) * 15.0), 3.0)

            if charge < ring_avg_charge:
                electron_rich_carbons.append((pt_key, charge, center))
        else:
            reactivity_weight = 1.0

        base_radius = (19.5 + (math.log1p(charge_intensity) * 15.0) + (strength * 7.5)) * c_scale
        radius = min(base_radius, max_cloud_radius)

        deactivation_applied = False
        if is_ring_carbon and charge > ring_avg_charge:
            deactivation_factor = 0.60
            radius *= deactivation_factor
            deactivation_applied = True

        if is_ring_carbon and at_main == "C":
            status = "DEACTIVATED" if deactivation_applied else "ACTIVATED"
            print(f"  Carbon at {pt_key}: charge={charge:+.3f}, avg={ring_avg_charge:+.3f}, "
                  f"radius={radius:.1f}px, weight={reactivity_weight:.2f}x [{status}]")

        if densities and atom_density:
            color = CloudRenderer.calculate_esp_color(atom_density.density, min_density, max_density)
            alpha = int(base_alpha * min(charge_intensity, 1.5))
        elif isl_size >= 2:
            # ========== 로컬 정규화 강제 (고리 탄소만) ==========
            if is_ring_carbon and ring_carbon_charges and len(ring_carbon_charges) > 1:
                ring_min = min(ring_carbon_charges)
                ring_max = max(ring_carbon_charges)
                ring_range = ring_max - ring_min
                if ring_range > 0.001:
                    local_normalized = (charge - ring_min) / ring_range
                else:
                    local_normalized = 0.5

                if local_normalized < 0.5:
                    ratio = local_normalized * 2.0
                    r = int(50 + (255 - 50) * (1 - ratio))
                    g = int(50 + (150 - 50) * (1 - ratio))
                    b = 255
                else:
                    ratio = (local_normalized - 0.5) * 2.0
                    r = 255
                    g = int(150 - 150 * ratio)
                    b = int(255 - 205 * ratio)

                color = QColor(r, g, b)
            else:
                base = QColor(VISUAL_SETTINGS["resonance_color"])
                normalized_charge = charge / charge_range
                mix = pow(abs(normalized_charge), 0.6) * 2.0 * reactivity_weight
                mix = min(mix, 0.98)
                target = QColor(VISUAL_SETTINGS["negative_color" if charge < 0 else "positive_color"])
                color = CloudRenderer._blend(base, target, mix)

            base_layer_alpha = base_alpha * min(max(strength, charge_intensity * 1.1), 1.5)

            if is_ring_carbon:
                base_layer_alpha *= 1.5

            alpha = int(base_layer_alpha)
        else:
            color = DFTDensityRenderer.charge_to_color(charge, min_charge, max_charge)
            alpha = int(base_alpha * min(charge_intensity, 1.5))

        color.setAlpha(alpha)
        grad = QRadialGradient(center, radius)
        grad.setColorAt(0, color); grad.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(grad)); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius + 2, radius + 2)

    if electron_rich_carbons:
        electron_rich_carbons.sort(key=lambda x: x[1])
        num_markers = min(3, max(2, len(electron_rich_carbons) // 3))
        top_sites = electron_rich_carbons[:num_markers]

        print(f"\n[v3.2 Crosshairs] Storing {len(top_sites)} markers:")
        for pt_key, charge_val, pos in top_sites:
            print(f"  ⊕ pt_key: {pt_key}, charge: {charge_val:.4f}")
            print(f"     → QPointF: ({pos.x():.1f}, {pos.y():.1f})")

        results["crosshairs_v32"] = [(pt_key, charge_val, pos) for pt_key, charge_val, pos in top_sites]


@staticmethod
def draw_crosshairs_v32(painter, results):
    if not results:
        return

    crosshair_data = results.get("crosshairs_v32", [])
    if not crosshair_data:
        return

    painter.save()
    # ========== 클리핑 완전 제거 (함수 내부) ==========
    painter.setClipping(False)

    pen = QPen(QColor(0, 255, 0, 255))
    pen.setWidth(3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    print(f"\n[v3.2 TOP LAYER] Rendering {len(crosshair_data)} crosshairs:")

    for pt_key, charge_val, pos in crosshair_data:
        print(f"  ⊕ Drawing at QPointF({pos.x():.1f}, {pos.y():.1f}), charge={charge_val:.4f}")

        marker_size = 24

        painter.drawLine(
            pos.x() - marker_size, pos.y(),
            pos.x() + marker_size, pos.y()
        )

        painter.drawLine(
            pos.x(), pos.y() - marker_size,
            pos.x(), pos.y() + marker_size
        )

        painter.drawEllipse(pos, marker_size * 0.7, marker_size * 0.7)
        painter.drawEllipse(pos, marker_size * 0.45, marker_size * 0.45)
        painter.drawEllipse(pos, marker_size * 0.2, marker_size * 0.2)

    painter.restore()
