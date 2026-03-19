# Reaction Animation Patterns & Skills

## 1. Frame Generation Pattern
- All generators return `ReactionTrajectory` dataclass
- Standard frame count: 40 (configurable)
- Transition zone: t=0.30~0.70 for bond changes
- Energy: parabolic `E = barrier * 4*t*(1-t)` for simple reactions

## 2. Atom Mapping Strategy
- Primary: `rdFMCS.FindMCS` (Maximum Common Substructure)
- Fallback 1: `GetSubstructMatch` (substructure match)
- Fallback 2: index-order mapping (last resort)

## 3. Coordinate Interpolation
- `_ease_in_out(t)` = smoothstep: `3t^2 - 2t^3`
- All coords centered on reactant centroid
- AlignMol used to pre-align product to reactant

## 4. Bond Visualization
- bond_order < 0.95: dashed line (partial bond)
- Forming bonds: green (#2ecc71)
- Breaking bonds: red (#e74c3c)
- Default bonds: gray-blue (#8899aa)

## 5. QPainter 2.5D Projection
- Y-axis rotation then X-axis rotation
- Scale factor adjustable via mouse wheel (10-200)
- Depth-based atom size scaling
- Radial gradient for 3D appearance

## 6. Integration Point
- popup_synthesis.py: `_on_reaction_animation()` -> `ReactionAnimationPopup`
- Gets reactant/product SMILES from `SynthesisStep` dataclass
