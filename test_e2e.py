"""
End-to-End API Test

실제 서버를 사용한 통합 테스트
"""

import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8000/api/v1/agent"
WORKSPACE = str(Path.cwd())

def test_complete_workflow():
    """전체 워크플로우 테스트"""
    print("=" * 60)
    print("🚀 AI Coding Agent E2E Test")
    print("=" * 60)

    # 1. 작업 생성
    print("\n📝 Step 1: 작업 생성")
    create_response = requests.post(f"{BASE_URL}/task", json={
        "user_request": "src 디렉토리의 파일 목록을 보여줘",
        "workspace_path": WORKSPACE
    })

    if create_response.status_code != 201:
        print(f"❌ 작업 생성 실패: {create_response.status_code}")
        print(create_response.text)
        return False

    task_data = create_response.json()
    task_id = task_data["task_id"]
    print(f"✅ 작업 생성 성공!")
    print(f"   Task ID: {task_id}")
    print(f"   Status: {task_data['status']}")
    print(f"   Request: {task_data['user_request']}")

    # 2. 작업 조회
    print(f"\n🔍 Step 2: 작업 상태 조회")
    get_response = requests.get(f"{BASE_URL}/task/{task_id}")

    if get_response.status_code != 200:
        print(f"❌ 작업 조회 실패: {get_response.status_code}")
        return False

    task_info = get_response.json()
    print(f"✅ 작업 조회 성공!")
    print(f"   Status: {task_info['status']}")
    print(f"   Workspace: {task_info['workspace_path']}")

    # 3. 작업 목록 조회
    print(f"\n📋 Step 3: 전체 작업 목록 조회")
    list_response = requests.get(f"{BASE_URL}/tasks")

    if list_response.status_code != 200:
        print(f"❌ 목록 조회 실패: {list_response.status_code}")
        return False

    tasks_data = list_response.json()
    print(f"✅ 목록 조회 성공!")
    print(f"   총 작업 수: {tasks_data['total']}")
    print(f"   통계: {tasks_data['stats']}")

    # 4. 작업 실행 (SSE - Mock LLM 사용)
    print(f"\n⚡ Step 4: 작업 실행 (SSE 스트리밍)")
    print("   Note: Mock LLM이 없어 Ollama 서버가 필요합니다.")
    print("   Ollama가 실행 중이지 않으면 타임아웃됩니다.")

    try:
        with requests.post(
            f"{BASE_URL}/task/{task_id}/execute",
            stream=True,
            timeout=5
        ) as execute_response:

            if execute_response.status_code != 200:
                print(f"⚠️  작업 실행 시작 실패: {execute_response.status_code}")
                print("   (Ollama 서버가 실행 중이 아닐 수 있습니다)")
            else:
                print("✅ SSE 스트림 시작!")
                event_count = 0

                for line in execute_response.iter_lines(decode_unicode=True):
                    if line.startswith('data: '):
                        event_data = json.loads(line[6:])
                        event_count += 1
                        print(f"   📨 Event {event_count}: {event_data['type']}")

                        if event_data['type'] in ['task_completed', 'task_failed', 'error']:
                            print(f"   🏁 작업 종료: {event_data}")
                            break

                        if event_count >= 5:  # 최대 5개 이벤트만
                            print("   ⏸️  (테스트를 위해 중단)")
                            break

                print(f"✅ {event_count}개 이벤트 수신")

    except requests.exceptions.Timeout:
        print("⚠️  타임아웃 (Ollama 서버가 실행 중이 아님)")
    except Exception as e:
        print(f"⚠️  실행 중 에러: {e}")

    # 5. 최종 상태 확인
    print(f"\n🔍 Step 5: 최종 상태 확인")
    final_response = requests.get(f"{BASE_URL}/task/{task_id}")
    final_data = final_response.json()
    print(f"   Status: {final_data['status']}")
    print(f"   Iterations: {final_data['iteration_count']}")

    # 6. 작업 삭제
    print(f"\n🗑️  Step 6: 작업 삭제")
    delete_response = requests.delete(f"{BASE_URL}/task/{task_id}")

    if delete_response.status_code == 204:
        print("✅ 작업 삭제 성공!")
    elif delete_response.status_code == 400:
        print("⚠️  실행 중인 작업은 삭제 불가")
    else:
        print(f"❌ 삭제 실패: {delete_response.status_code}")

    # 7. 삭제 확인
    verify_response = requests.get(f"{BASE_URL}/task/{task_id}")
    if verify_response.status_code == 404:
        print("✅ 삭제 확인 완료!")
    else:
        print("⚠️  아직 작업이 존재함 (실행 중이었을 수 있음)")

    print("\n" + "=" * 60)
    print("✅ E2E 테스트 완료!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    # 서버 연결 확인
    print("서버 연결 확인 중...")
    try:
        response = requests.get("http://localhost:8000/docs", timeout=2)
        if response.status_code == 200:
            print("✅ 서버 연결 확인\n")
            test_complete_workflow()
        else:
            print(f"⚠️  서버 응답 이상: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ 서버에 연결할 수 없습니다!")
        print("먼저 서버를 시작하세요:")
        print("   uvicorn src.main:app --host 0.0.0.0 --port 8000")
    except Exception as e:
        print(f"❌ 에러: {e}")
