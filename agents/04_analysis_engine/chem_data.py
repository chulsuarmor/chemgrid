# chem_data.py (v2.25 - Complete Physics & Visual Scaling DB)

# [SECTION 1] 1~54번 원소 물리 데이터 (cloud_scale & density_scale 반영)
ELEMENT_DATA = {
    "H":  {"number": 1,  "negativity": 2.20, "radius": 0.37, "cloud_scale": 0.80, "density_scale": 0.7, "F": 0.00, "R": 0.00},
    "He": {"number": 2,  "negativity": 0.00, "radius": 0.32, "cloud_scale": 0.70, "density_scale": 0.5, "F": 0.00, "R": 0.00},
    "Li": {"number": 3,  "negativity": 0.98, "radius": 1.34, "cloud_scale": 1.10, "density_scale": 0.6, "F": 0.00, "R": 0.00},
    "Be": {"number": 4,  "negativity": 1.57, "radius": 0.90, "cloud_scale": 1.00, "density_scale": 0.7, "F": 0.00, "R": 0.00},
    "B":  {"number": 5,  "negativity": 2.04, "radius": 0.82, "cloud_scale": 0.95, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "C":  {"number": 6,  "negativity": 2.55, "radius": 0.77, "cloud_scale": 1.00, "density_scale": 1.0, "F": 0.00, "R": 0.00},
    "N":  {"number": 7,  "negativity": 3.04, "radius": 0.75, "cloud_scale": 0.82, "density_scale": 1.4, "F": 0.08, "R": -0.74},
    "O":  {"number": 8,  "negativity": 3.44, "radius": 0.73, "cloud_scale": 0.72, "density_scale": 1.6, "F": 0.33, "R": -0.70},
    "F":  {"number": 9,  "negativity": 3.98, "radius": 0.71, "cloud_scale": 0.68, "density_scale": 1.8, "F": 0.45, "R": -0.39},
    "Ne": {"number": 10, "negativity": 0.00, "radius": 0.69, "cloud_scale": 0.70, "density_scale": 0.5, "F": 0.00, "R": 0.00},
    "Na": {"number": 11, "negativity": 0.93, "radius": 1.54, "cloud_scale": 1.20, "density_scale": 0.6, "F": 0.00, "R": 0.00},
    "Mg": {"number": 12, "negativity": 1.31, "radius": 1.30, "cloud_scale": 1.15, "density_scale": 0.7, "F": 0.00, "R": 0.00},
    "Al": {"number": 13, "negativity": 1.61, "radius": 1.18, "cloud_scale": 1.10, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "Si": {"number": 14, "negativity": 1.90, "radius": 1.11, "cloud_scale": 1.05, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "P":  {"number": 15, "negativity": 2.19, "radius": 1.06, "cloud_scale": 1.10, "density_scale": 0.9, "F": 0.15, "R": -0.10},
    "S":  {"number": 16, "negativity": 2.58, "radius": 1.02, "cloud_scale": 1.15, "density_scale": 0.9, "F": 0.20, "R": -0.15},
    # 할로젠 이탈기 및 대형 원소: 부피 크고 밀도 낮게 (Polarizability 반영)
    "Cl": {"number": 17, "negativity": 3.16, "radius": 0.99, "cloud_scale": 1.38, "density_scale": 0.8, "F": 0.42, "R": -0.19},
    "Ar": {"number": 18, "negativity": 0.00, "radius": 0.97, "cloud_scale": 0.90, "density_scale": 0.5, "F": 0.00, "R": 0.00},
    "K":  {"number": 19, "negativity": 0.82, "radius": 1.96, "cloud_scale": 1.40, "density_scale": 0.5, "F": 0.00, "R": 0.00},
    "Ca": {"number": 20, "negativity": 1.00, "radius": 1.74, "cloud_scale": 1.35, "density_scale": 0.6, "F": 0.00, "R": 0.00},
    "Sc": {"number": 21, "negativity": 1.36, "radius": 1.44, "cloud_scale": 1.20, "density_scale": 0.7, "F": 0.00, "R": 0.00},
    "Ti": {"number": 22, "negativity": 1.54, "radius": 1.36, "cloud_scale": 1.15, "density_scale": 0.7, "F": 0.00, "R": 0.00},
    "V":  {"number": 23, "negativity": 1.63, "radius": 1.25, "cloud_scale": 1.15, "density_scale": 0.7, "F": 0.00, "R": 0.00},
    "Cr": {"number": 24, "negativity": 1.66, "radius": 1.27, "cloud_scale": 1.15, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "Mn": {"number": 25, "negativity": 1.55, "radius": 1.39, "cloud_scale": 1.15, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "Fe": {"number": 26, "negativity": 1.83, "radius": 1.25, "cloud_scale": 1.10, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "Co": {"number": 27, "negativity": 1.88, "radius": 1.26, "cloud_scale": 1.10, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "Ni": {"number": 28, "negativity": 1.91, "radius": 1.21, "cloud_scale": 1.10, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "Cu": {"number": 29, "negativity": 1.90, "radius": 1.38, "cloud_scale": 1.15, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "Zn": {"number": 30, "negativity": 1.65, "radius": 1.31, "cloud_scale": 1.15, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "Ga": {"number": 31, "negativity": 1.81, "radius": 1.26, "cloud_scale": 1.15, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "Ge": {"number": 32, "negativity": 2.01, "radius": 1.22, "cloud_scale": 1.10, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "As": {"number": 33, "negativity": 2.18, "radius": 1.19, "cloud_scale": 1.10, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "Se": {"number": 34, "negativity": 2.55, "radius": 1.16, "cloud_scale": 1.05, "density_scale": 1.0, "F": 0.00, "R": 0.00},
    "Br": {"number": 35, "negativity": 2.96, "radius": 1.14, "cloud_scale": 1.55, "density_scale": 0.7, "F": 0.44, "R": -0.17},
    "Kr": {"number": 36, "negativity": 3.00, "radius": 1.10, "cloud_scale": 0.95, "density_scale": 0.5, "F": 0.00, "R": 0.00},
    "Rb": {"number": 37, "negativity": 0.82, "radius": 2.11, "cloud_scale": 1.60, "density_scale": 0.4, "F": 0.00, "R": 0.00},
    "Sr": {"number": 38, "negativity": 0.95, "radius": 1.92, "cloud_scale": 1.55, "density_scale": 0.5, "F": 0.00, "R": 0.00},
    "Y":  {"number": 39, "negativity": 1.22, "radius": 1.62, "cloud_scale": 1.40, "density_scale": 0.6, "F": 0.00, "R": 0.00},
    "Zr": {"number": 40, "negativity": 1.33, "radius": 1.48, "cloud_scale": 1.35, "density_scale": 0.7, "F": 0.00, "R": 0.00},
    "Nb": {"number": 41, "negativity": 1.60, "radius": 1.37, "cloud_scale": 1.30, "density_scale": 0.7, "F": 0.00, "R": 0.00},
    "Mo": {"number": 42, "negativity": 2.16, "radius": 1.45, "cloud_scale": 1.25, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "Tc": {"number": 43, "negativity": 1.90, "radius": 1.56, "cloud_scale": 1.25, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "Ru": {"number": 44, "negativity": 2.20, "radius": 1.26, "cloud_scale": 1.20, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "Rh": {"number": 45, "negativity": 2.28, "radius": 1.35, "cloud_scale": 1.20, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "Pd": {"number": 46, "negativity": 2.20, "radius": 1.31, "cloud_scale": 1.20, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "Ag": {"number": 47, "negativity": 1.93, "radius": 1.53, "cloud_scale": 1.25, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "Cd": {"number": 48, "negativity": 1.69, "radius": 1.48, "cloud_scale": 1.30, "density_scale": 0.7, "F": 0.00, "R": 0.00},
    "In": {"number": 49, "negativity": 1.78, "radius": 1.44, "cloud_scale": 1.25, "density_scale": 0.8, "F": 0.00, "R": 0.00},
    "Sn": {"number": 50, "negativity": 1.96, "radius": 1.41, "cloud_scale": 1.20, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "Sb": {"number": 51, "negativity": 2.05, "radius": 1.38, "cloud_scale": 1.15, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "Te": {"number": 52, "negativity": 2.10, "radius": 1.35, "cloud_scale": 1.15, "density_scale": 0.9, "F": 0.00, "R": 0.00},
    "I":  {"number": 53, "negativity": 2.66, "radius": 1.33, "cloud_scale": 1.75, "density_scale": 0.6, "F": 0.40, "R": -0.19},
    "Xe": {"number": 54, "negativity": 2.60, "radius": 1.30, "cloud_scale": 1.10, "density_scale": 0.5, "F": 0.00, "R": 0.00},
}

# [SECTION 2] 70개 이상의 정밀 작용기 상수 (Identity Pattern 추가)  (Hansch & Leo 1991 기준)
SUBSTITUENT_DATA = {
    # Nitrogen Groups
    "NH2":   {"F": 0.08, "R": -0.74, "sigma_p": -0.66},
    "NHMe":  {"F": 0.06, "R": -0.76, "sigma_p": -0.70},
    "NMe2":  {"F": 0.10, "R": -0.93, "sigma_p": -0.83},
    "NMe3+": {"F": 0.93, "R": -0.11, "sigma_p": 0.82},
    "NHAc":  {"F": 0.28, "R": -0.26, "sigma_p": 0.00},
    "NO2":   {"F": 0.65, "R": 0.13,  "sigma_p": 0.78, "pattern": "Nitro"}, # 대칭 패턴 명시
    "NO":    {"F": 0.49, "R": 0.42,  "sigma_p": 0.91},
    "N3":    {"F": 0.48, "R": -0.40, "sigma_p": 0.08},
    "CN":    {"F": 0.51, "R": 0.15,  "sigma_p": 0.66},
    "NCS":   {"F": 0.42, "R": -0.09, "sigma_p": 0.33},
    
    # Oxygen Groups
    "OH":    {"F": 0.33, "R": -0.70, "sigma_p": -0.37},
    "OMe":   {"F": 0.29, "R": -0.56, "sigma_p": -0.27},
    "OEt":   {"F": 0.22, "R": -0.44, "sigma_p": -0.24},
    "OPh":   {"F": 0.34, "R": -0.35, "sigma_p": -0.01},
    "OAc":   {"F": 0.39, "R": -0.08, "sigma_p": 0.31},
    "OCF3":  {"F": 0.38, "R": -0.03, "sigma_p": 0.35},
    "CHO":   {"F": 0.31, "R": 0.11,  "sigma_p": 0.42},
    "COMe":  {"F": 0.28, "R": 0.20,  "sigma_p": 0.48},
    "COOH":  {"F": 0.34, "R": 0.11,  "sigma_p": 0.45},
    "COOMe": {"F": 0.33, "R": 0.12,  "sigma_p": 0.45},
    "COO-":  {"F": -0.21, "R": 0.10, "sigma_p": -0.11},
    "O3":    {"F": 0.00, "R": 0.00,  "sigma_p": 0.00, "pattern": "Ozone"}, # 오존 패턴 추가
    
    # Carbon/Alkyl/Aryl
    "Me":    {"F": -0.01, "R": -0.13, "sigma_p": -0.17},
    "Et":    {"F": -0.01, "R": -0.12, "sigma_p": -0.15},
    "iPr":   {"F": -0.01, "R": -0.12, "sigma_p": -0.15},
    "tBu":   {"F": -0.07, "R": -0.13, "sigma_p": -0.20},
    "CF3":   {"F": 0.38, "R": 0.16,  "sigma_p": 0.54},
    "CCl3":  {"F": 0.30,  "R": 0.03,  "sigma_p": 0.33},
    "Vinyl": {"F": 0.10, "R": -0.16, "sigma_p": -0.08},
    "Ethynyl":{"F": 0.22, "R": 0.01, "sigma_p": 0.23},
    "Ph":    {"F": 0.12, "R": -0.11, "sigma_p": -0.01},
    
    # Sulfur & Others
    "SH":    {"F": 0.30, "R": -0.15, "sigma_p": 0.15},
    "SMe":   {"F": 0.20, "R": -0.20, "sigma_p": 0.00},
    "SO2Me": {"F": 0.61, "R": 0.17,  "sigma_p": 0.72},
    "SF5":   {"F": 0.56, "R": 0.12,  "sigma_p": 0.68},
    "SiMe3": {"F": -0.12, "R": 0.11, "sigma_p": -0.01},
    "B(OH)2":{"F": -0.03, "R": 0.15, "sigma_p": 0.12},
    "F":     {"F": 0.45, "R": -0.39, "sigma_p": 0.06}, # 할로젠 상보
    "Cl":    {"F": 0.42, "R": -0.19, "sigma_p": 0.23},
    "Br":    {"F": 0.44, "R": -0.17, "sigma_p": 0.27},
    "I":     {"F": 0.40, "R": -0.19, "sigma_p": 0.21},
}

# [SECTION 3] 시각 가중치
VISUAL_SETTINGS = {
    "cloud_opacity": 140,
    "resonance_color": "#4CAF50",
    "negative_color": "#F44336",
    "positive_color": "#2196F3",
    "aromatic_density_boost": 1.85,
    "conjugation_intensity": 1.5,
    "charge_visual_weight": 5.8, # 대비 극대화
    "simple_bond_suppression": 0.12,
}