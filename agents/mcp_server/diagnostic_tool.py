import subprocess
from engine_core import validate_quantum

def check_stereo_activation():
    try:
        result = subprocess.run(['python', 'agents/06_3d_structure/activate.py'], 
                              capture_output=True, text=True)
        return "활성화 성공" if "3D ready" in result.stdout else "활성화 실패"
    except Exception as e:
        return f"진단 오류: {str(e)}"

if __name__ == "__main__":
    print(":: 양자 검증 결과 ::", validate_quantum())
    print(":: 3D 활성화 상태 ::", check_stereo_activation())