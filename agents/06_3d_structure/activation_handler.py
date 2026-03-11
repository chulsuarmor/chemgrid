import threading
from engine_core import QuantumChemistryValidator

class StructureActivator:
    def __init__(self):
        self.validator = QuantumChemistryValidator()
        self.lock = threading.Lock()

    def enable_3d_button(self, molecule):
        """3D 활성화 조건 검증 로직"""
        with self.lock:
            return (
                molecule.has_3d_coordinates()
                and self.validator.check_stereochemistry(molecule)
                and self.validator.validate_quantum_data(molecule)
            )

    def async_quantum_calculation(self, molecule):
        """양자화학 계산 비동기 실행"""
        def calculation_task():
            try:
                result = self.validator.run_orca_calculation(molecule)
                molecule.store_quantum_data(result)
            except Exception as e:
                molecule.log_error(f"Calculation failed: {str(e)}")

        threading.Thread(target=calculation_task, daemon=True).start()