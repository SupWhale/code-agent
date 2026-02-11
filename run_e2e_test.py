"""
E2E 테스트 실행 스크립트

서버를 시작하고 테스트를 실행한 후 서버를 종료합니다.
"""

import subprocess
import time
import sys
import requests
import os

def main():
    print("🚀 AI Coding Agent E2E Test Runner")
    print("=" * 60)

    # 서버 프로세스 시작
    print("\n📡 서버 시작 중...")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

    # 서버가 시작될 때까지 대기
    max_wait = 10
    for i in range(max_wait):
        try:
            response = requests.get("http://localhost:8000/docs", timeout=1)
            if response.status_code == 200:
                print(f"✅ 서버 시작 완료! ({i+1}초)")
                break
        except:
            pass

        print(f"   대기 중... ({i+1}/{max_wait})")
        time.sleep(1)
    else:
        print("❌ 서버 시작 실패!")
        server_process.terminate()
        return False

    # E2E 테스트 실행
    print("\n" + "=" * 60)
    print("🧪 E2E 테스트 실행")
    print("=" * 60)

    try:
        test_process = subprocess.run(
            [sys.executable, "test_e2e.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            timeout=30
        )

        success = test_process.returncode == 0

    except subprocess.TimeoutExpired:
        print("\n⚠️  테스트 타임아웃")
        success = False
    except Exception as e:
        print(f"\n❌ 테스트 실행 에러: {e}")
        success = False

    # 서버 종료
    print("\n" + "=" * 60)
    print("🛑 서버 종료 중...")
    server_process.terminate()

    try:
        server_process.wait(timeout=5)
        print("✅ 서버 종료 완료")
    except subprocess.TimeoutExpired:
        print("⚠️  강제 종료")
        server_process.kill()

    print("=" * 60)

    if success:
        print("✅ 전체 테스트 성공!")
    else:
        print("⚠️  일부 테스트 실패 (Ollama 필요)")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
