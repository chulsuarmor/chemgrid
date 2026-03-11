# [Phase Integration] phase_integration.py (v1.1)
"""
ChemDraw Pro Phase B-D Integration Module
Connects ESP visualization, 3D popup, and IUPAC labeling

Changes (v1.1):
  - S5 fix: print() → logging module
"""

import logging
from typing import Dict, Optional, List
from PyQt6.QtCore import QThread, pyqtSignal, QPointF
from PyQt6.QtWidgets import QMainWindow
import math

logger = logging.getLogger(__name__)

# Import Phase modules
try:
    from renderer import ElectronicDensity, ESPCalculatorThread, CloudRenderer
    PHASE_B_AVAILABLE = True
except ImportError:
    PHASE_B_AVAILABLE = False
    logger.warning("[Integration] Phase B not available")

try:
    from popup_3d import Molecule3DData, Molecule3DPopup
    PHASE_C_AVAILABLE = True
except ImportError:
    PHASE_C_AVAILABLE = False
    logger.warning("[Integration] Phase C not available")

try:
    from iupac_analyzer import IUPACAnalyzer, IUPACAnalyzerThread, IUPACLabelRenderer
    PHASE_D_AVAILABLE = True
except ImportError:
    PHASE_D_AVAILABLE = False
    logger.warning("[Integration] Phase D not available")

from orca_interface import OrcaCalculationResult


class Phase3DPopupManager:
    """
    Manages 3D popup window creation and display
    Triggered exclusively from Theory layer interactions
    """
    
    def __init__(self, canvas):
        self.canvas = canvas
        self.popup_window = None
    
    def trigger_3d_popup_from_theory_layer(self, atoms: Dict, bonds: Dict, theory_data: Dict):
        """
        [Phase C] Trigger 3D popup when user clicks on Theory layer
        
        Args:
            atoms: Molecule atom data
            bonds: Molecule bond data
            theory_data: Theory layer optimization data (coords, map)
        """
        if not PHASE_C_AVAILABLE:
            logger.warning("[Integration] Phase C (3D Popup) not available")
            return
        
        try:
            # Close existing popup if open
            if self.popup_window and self.popup_window.isVisible():
                self.popup_window.close()
            
            # Create 3D molecular data
            mol_data = Molecule3DData(atoms, bonds, theory_data)
            
            # Create and show popup
            self.popup_window = Molecule3DPopup(mol_data)
            self.popup_window.show()
            
            logger.info("[Integration] 3D popup opened: %d atoms", len(mol_data.atom_positions))
            
        except Exception as e:
            logger.error("[Integration Phase C Error] %s", e)
    
    def close_popup(self):
        """Close 3D popup if open"""
        if self.popup_window:
            self.popup_window.close()
            self.popup_window = None


class Phase2ESPCalculationManager:
    """
    Manages background ESP calculation and visualization
    Processes ORCA electronic density data
    """
    
    def __init__(self, canvas):
        self.canvas = canvas
        self.esp_thread = None
        self.cached_densities = None
    
    def start_esp_calculation(self, densities: List[ElectronicDensity], atom_positions: Dict):
        """
        [Phase B] Start background ESP calculation
        
        Args:
            densities: List of ElectronicDensity objects from ORCA
            atom_positions: Dictionary of atom coordinates
        """
        if not PHASE_B_AVAILABLE:
            logger.warning("[Integration] Phase B (ESP) not available")
            return
        
        try:
            # Cancel previous calculation if running
            if self.esp_thread and self.esp_thread.isRunning():
                self.esp_thread.quit()
                self.esp_thread.wait()
            
            # Create new ESP calculator thread
            self.esp_thread = ESPCalculatorThread(densities, atom_positions)
            self.esp_thread.progress.connect(self._on_esp_progress)
            self.esp_thread.result.connect(self._on_esp_result)
            self.esp_thread.error.connect(self._on_esp_error)
            
            # Cache densities for rendering
            self.cached_densities = densities
            CloudRenderer.set_density_data(densities)
            
            # Start calculation
            self.esp_thread.start()
            
            logger.info("[Integration] ESP calculation started: %d density points", len(densities))
            
        except Exception as e:
            logger.error("[Integration Phase B Error] %s", e)
    
    def _on_esp_progress(self, message: str):
        """Handle ESP progress message"""
        logger.debug("[Phase B Progress] %s", message)
    
    def _on_esp_result(self, esp_map: Dict):
        """Handle ESP calculation result"""
        logger.info("[Phase B Result] ESP map calculated: %d points", len(esp_map))
        
        # Trigger canvas redraw
        if hasattr(self.canvas, 'update'):
            self.canvas.update()
    
    def _on_esp_error(self, error: str):
        """Handle ESP calculation error"""
        logger.error("[Phase B Error] %s", error)
    
    def import_orca_densities(self, orca_result: OrcaCalculationResult) -> List[ElectronicDensity]:
        """
        Convert ORCA calculation result to ElectronicDensity objects
        
        Args:
            orca_result: OrcaCalculationResult from ORCA interface
            
        Returns:
            List of ElectronicDensity objects with coordinates rounded to 0.01
        """
        densities = []
        
        try:
            if not orca_result.densities:
                # Generate densities from ORCA charges and geometry
                for atom_idx, (x, y, z) in orca_result.geometry.items():
                    density = ElectronicDensity(
                        atom_index=atom_idx,
                        atom_symbol="C",  # Placeholder
                        position=(round(x, 2), round(y, 2), round(z, 2)),
                        density=0.5,  # Default density
                        mulliken_charge=orca_result.charges_mulliken.get(atom_idx, 0.0),
                        lowdin_charge=orca_result.charges_lowdin.get(atom_idx, 0.0)
                    )
                    densities.append(density)
            else:
                # Use pre-calculated densities
                for d in orca_result.densities:
                    # Round position to 0.01 precision
                    d.position = (round(d.position[0], 2), round(d.position[1], 2), round(d.position[2], 2))
                    densities.append(d)
            
            logger.info("[Integration] Imported %d electronic densities from ORCA", len(densities))
            return densities
            
        except Exception as e:
            logger.error("[Integration ORCA Import Error] %s", e)
            return []


class Phase4IUPACAnalysisManager:
    """
    Manages IUPAC nomenclature analysis
    Runs asynchronously to avoid blocking UI
    """
    
    def __init__(self, canvas):
        self.canvas = canvas
        self.iupac_thread = None
        self.iupac_data = None
    
    def start_iupac_analysis(self, atoms: Dict, bonds: Dict):
        """
        [Phase D] Start background IUPAC analysis
        
        Args:
            atoms: Molecule atom data
            bonds: Molecule bond data
        """
        if not PHASE_D_AVAILABLE:
            logger.warning("[Integration] Phase D (IUPAC) not available")
            return
        
        try:
            # Cancel previous analysis if running
            if self.iupac_thread and self.iupac_thread.isRunning():
                self.iupac_thread.quit()
                self.iupac_thread.wait()
            
            # Create new IUPAC analyzer thread
            self.iupac_thread = IUPACAnalyzerThread(atoms, bonds)
            self.iupac_thread.progress.connect(self._on_iupac_progress)
            self.iupac_thread.result.connect(self._on_iupac_result)
            self.iupac_thread.error.connect(self._on_iupac_error)
            
            # Start analysis
            self.iupac_thread.start()
            
            logger.info("[Integration] IUPAC analysis started")
            
        except Exception as e:
            logger.error("[Integration Phase D Error] %s", e)
    
    def _on_iupac_progress(self, message: str):
        """Handle IUPAC progress message"""
        logger.debug("[Phase D Progress] %s", message)
    
    def _on_iupac_result(self, iupac_data):
        """Handle IUPAC analysis result"""
        self.iupac_data = iupac_data
        logger.info("[Phase D Result] IUPAC: %s", iupac_data.iupac_name)
        logger.info("[Phase D Result] Stereochemistry: %s", iupac_data.stereo_descriptors)
        logger.info("[Phase D Result] Functional Groups: %s", iupac_data.functional_groups)
        
        # Update canvas if in Theory view
        if hasattr(self.canvas, 'view_state') and self.canvas.view_state == "Theory":
            if hasattr(self.canvas, 'update'):
                self.canvas.update()
    
    def _on_iupac_error(self, error: str):
        """Handle IUPAC analysis error"""
        logger.error("[Phase D Error] %s", error)
    
    def get_iupac_label_text(self) -> str:
        """
        Get formatted IUPAC label for display in Theory layer
        
        Returns:
            Formatted label text
        """
        if not self.iupac_data:
            return "IUPAC: Analyzing..."
        
        return IUPACLabelRenderer.format_label_for_display(self.iupac_data)


class PhaseIntegrationManager:
    """
    Master integration manager
    Coordinates all Phase B, C, D operations
    """
    
    def __init__(self, canvas):
        self.canvas = canvas
        self.esp_manager = Phase2ESPCalculationManager(canvas) if PHASE_B_AVAILABLE else None
        self.popup_manager = Phase3DPopupManager(canvas) if PHASE_C_AVAILABLE else None
        self.iupac_manager = Phase4IUPACAnalysisManager(canvas) if PHASE_D_AVAILABLE else None
    
    def on_molecule_updated(self, atoms: Dict, bonds: Dict, analysis_results: Dict = None):
        """
        Called when molecule is updated (atom/bond added, deleted, moved)
        Triggers Phase B, C, D updates
        
        Args:
            atoms: Molecule atom data
            bonds: Molecule bond data
            analysis_results: Chemical analysis results
        """
        logger.info("[Integration] Molecule updated: %d atoms, %d bonds", len(atoms), len(bonds))
        
        # Phase D: Update IUPAC analysis
        if self.iupac_manager:
            self.iupac_manager.start_iupac_analysis(atoms, bonds)
    
    def on_theory_layer_interaction(self, atoms: Dict, bonds: Dict, theory_data: Dict):
        """
        Called when user interacts with Theory layer
        Triggers Phase C 3D popup
        
        Args:
            atoms: Molecule atom data
            bonds: Molecule bond data
            theory_data: Theory optimization data
        """
        logger.info("[Integration] Theory layer interaction detected")
        
        # Phase C: Open 3D popup
        if self.popup_manager:
            self.popup_manager.trigger_3d_popup_from_theory_layer(atoms, bonds, theory_data)
    
    def on_orca_calculation_complete(self, orca_result: OrcaCalculationResult):
        """
        Called when ORCA quantum calculation completes
        Triggers Phase B ESP visualization
        
        Args:
            orca_result: OrcaCalculationResult with electronic density data
        """
        logger.info("[Integration] ORCA calculation complete")
        
        # Phase B: Import densities and start ESP calculation
        if self.esp_manager:
            densities = self.esp_manager.import_orca_densities(orca_result)
            
            # Create atom position dict
            atom_positions = {}
            for k in self.canvas.atoms.keys():
                atom_positions[k] = (k[0], k[1], 0.0)
            
            # Start ESP calculation
            self.esp_manager.start_esp_calculation(densities, atom_positions)
    
    def display_3d_popup(self):
        """Manually trigger 3D popup display"""
        if self.popup_manager and hasattr(self.canvas, 'analysis_results'):
            theory_data = self.canvas.analysis_results.get("theory_data", {})
            self.on_theory_layer_interaction(self.canvas.atoms, self.canvas.bonds, theory_data)
    
    def cleanup(self):
        """Clean up threads and resources with graceful shutdown"""
        logger.info("[Integration] Starting cleanup process...")
        
        # Stop ESP calculation thread gracefully
        if self.esp_manager and self.esp_manager.esp_thread:
            if self.esp_manager.esp_thread.isRunning():
                logger.info("[Integration] Stopping ESP calculation thread...")
                self.esp_manager.esp_thread.stop()  # Graceful stop signal
                self.esp_manager.esp_thread.quit()
                if not self.esp_manager.esp_thread.wait(5000):  # Wait max 5 seconds
                    logger.warning("[Integration] Warning: ESP thread did not finish cleanly")
        
        # Stop IUPAC analysis thread gracefully
        if self.iupac_manager and self.iupac_manager.iupac_thread:
            if self.iupac_manager.iupac_thread.isRunning():
                logger.info("[Integration] Stopping IUPAC analysis thread...")
                self.iupac_manager.iupac_thread.stop()  # Graceful stop signal
                self.iupac_manager.iupac_thread.quit()
                if not self.iupac_manager.iupac_thread.wait(5000):  # Wait max 5 seconds
                    logger.warning("[Integration] Warning: IUPAC thread did not finish cleanly")
        
        # Close 3D popup
        if self.popup_manager:
            logger.info("[Integration] Closing 3D popup...")
            self.popup_manager.close_popup()
        
        logger.info("[Integration] Cleanup completed successfully")


# ============================================================================
# INTEGRATION HOOKS FOR draw.py
# ============================================================================

def attach_phase_integration(canvas: QMainWindow) -> PhaseIntegrationManager:
    """
    Attach Phase B-D integration to main canvas
    Call this in draw.py __init__ after canvas is created
    
    Args:
        canvas: MoleculeCanvas instance
        
    Returns:
        PhaseIntegrationManager instance (store as self.phase_manager)
    """
    manager = PhaseIntegrationManager(canvas)
    logger.info("[Integration] Phase B-D integration attached to canvas")
    return manager
