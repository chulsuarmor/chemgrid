from engine_core import validate_stereo

if __name__ == "__main__":
    result = validate_stereo()
    print(f"3D 활성화 상태: {'성공' if result else '실패'}")
    exit(0 if result else 1)