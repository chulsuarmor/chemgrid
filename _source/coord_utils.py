# [Utility] coord_utils.py - Coordinate Precision Management
"""
Centralized coordinate handling for ChemDraw Pro
Ensures all coordinates are consistently rounded to 0.01 precision
throughout all phases (A-D)
"""

from typing import Tuple, Dict, Any
from PyQt6.QtCore import QPointF

def round_coord(value: float, precision: int = 2) -> float:
    """
    Round a single coordinate value to specified precision
    Default: 2 decimal places (0.01 unit)
    
    Args:
        value: Coordinate value to round
        precision: Decimal places (default: 2)
        
    Returns:
        Rounded value
    """
    return round(value, precision)

def round_point(point: Tuple[float, float], precision: int = 2) -> Tuple[float, float]:
    """
    Round a 2D point (x, y) to specified precision
    
    Args:
        point: Tuple of (x, y) coordinates
        precision: Decimal places
        
    Returns:
        Tuple of rounded coordinates
    """
    return (round(point[0], precision), round(point[1], precision))

def round_point_3d(point: Tuple[float, float, float], precision: int = 2) -> Tuple[float, float, float]:
    """
    Round a 3D point (x, y, z) to specified precision
    
    Args:
        point: Tuple of (x, y, z) coordinates
        precision: Decimal places
        
    Returns:
        Tuple of rounded 3D coordinates
    """
    return (round(point[0], precision), round(point[1], precision), round(point[2], precision))

def qpointf_to_tuple(qpoint: QPointF, precision: int = 2) -> Tuple[float, float]:
    """
    Convert QPointF to rounded tuple
    
    Args:
        qpoint: PyQt6 QPointF object
        precision: Decimal places
        
    Returns:
        Tuple of rounded coordinates
    """
    return (round(qpoint.x(), precision), round(qpoint.y(), precision))

def tuple_to_qpointf(point: Tuple[float, float]) -> QPointF:
    """
    Convert tuple to QPointF (coordinates already rounded)
    
    Args:
        point: Tuple of coordinates
        
    Returns:
        QPointF object
    """
    return QPointF(point[0], point[1])

def round_atoms_dict(atoms: Dict, precision: int = 2) -> Dict:
    """
    Round all atom position keys to specified precision
    
    Args:
        atoms: Atoms dictionary {position: {data}}
        precision: Decimal places
        
    Returns:
        Atoms dictionary with rounded position keys
    """
    return {
        round_point(pos, precision): data 
        for pos, data in atoms.items()
    }

def round_bonds_dict(bonds: Dict, precision: int = 2) -> Dict:
    """
    Round all bond endpoint keys to specified precision
    
    Args:
        bonds: Bonds dictionary {(k1, k2): order/data}
        precision: Decimal places
        
    Returns:
        Bonds dictionary with rounded position keys
    """
    result = {}
    for (k1, k2), value in bonds.items():
        rk1 = round_point(k1, precision)
        rk2 = round_point(k2, precision)
        
        # Handle different bond value types
        if isinstance(value, tuple):
            # Wedge/Dash: (QPointF, QPointF, type)
            p1 = value[0] if hasattr(value[0], 'x') else QPointF(value[0][0], value[0][1])
            p2 = value[1] if hasattr(value[1], 'x') else QPointF(value[1][0], value[1][1])
            value = (p1, p2, value[2])
        
        result[(rk1, rk2)] = value
    
    return result

def validate_coordinate_precision(atoms: Dict, bonds: Dict, precision: int = 2) -> bool:
    """
    Validate that all coordinates in atoms and bonds are properly rounded
    
    Args:
        atoms: Atoms dictionary
        bonds: Bonds dictionary
        precision: Expected decimal places
        
    Returns:
        True if all coordinates are properly rounded, False otherwise
    """
    # Check atom positions
    for pos in atoms.keys():
        if len(pos) != 2:
            return False
        
        x_rounded = round(pos[0], precision) == pos[0]
        y_rounded = round(pos[1], precision) == pos[1]
        
        if not (x_rounded and y_rounded):
            print(f"[coord_utils] Atom position not properly rounded: {pos}")
            return False
    
    # Check bond positions
    for (k1, k2) in bonds.keys():
        for pos in [k1, k2]:
            x_rounded = round(pos[0], precision) == pos[0]
            y_rounded = round(pos[1], precision) == pos[1]
            
            if not (x_rounded and y_rounded):
                print(f"[coord_utils] Bond position not properly rounded: {pos}")
                return False
    
    return True


# ============================================================================
# CONSTANTS FOR CONSISTENT COORDINATE HANDLING
# ============================================================================

DEFAULT_PRECISION = 2  # 0.01 unit precision
DEFAULT_GRID_SIZE = 40  # 40 units per grid cell
DEFAULT_SNAP_DISTANCE = 25  # Snapping tolerance
DEFAULT_ATOM_RADIUS = 12  # Atom visual radius


class CoordValidator:
    """Context manager for validating coordinate precision"""
    
    def __init__(self, atoms: Dict, bonds: Dict, precision: int = 2):
        self.atoms = atoms
        self.bonds = bonds
        self.precision = precision
        self.valid = False
    
    def __enter__(self):
        self.valid = validate_coordinate_precision(self.atoms, self.bonds, self.precision)
        if not self.valid:
            print(f"[CoordValidator] Coordinate validation failed")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.valid:
            print(f"[CoordValidator] Warning: exiting with invalid coordinates")
    
    def is_valid(self) -> bool:
        """Check if coordinates are valid"""
        return self.valid
