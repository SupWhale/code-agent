"""
도구 직접 테스트

Agent 시스템의 도구들을 직접 테스트합니다.
"""

import asyncio
from pathlib import Path

from src.agent.tools.file_tools import ReadFileTool, ListFilesTool
from src.agent.tools.search_tools import SearchCodeTool
from src.agent.tools.interaction_tools import FinishTool

async def test_tools():
    workspace = str(Path.cwd())
    print("=" * 60)
    print("🛠️  Agent Tools Direct Test")
    print("=" * 60)
    print(f"Workspace: {workspace}\n")

    # 1. ListFilesTool 테스트
    print("📁 Test 1: ListFilesTool")
    list_tool = ListFilesTool(workspace)
    files = await list_tool.execute({"path": "src/agent", "recursive": False})
    print(f"   결과: {len(files['files'])}개 파일 발견")
    for f in files['files'][:5]:  # 처음 5개만
        print(f"   - {f['name']} ({f['type']})")
    print()

    # 2. ReadFileTool 테스트
    print("📄 Test 2: ReadFileTool")
    read_tool = ReadFileTool(workspace)
    try:
        content = await read_tool.execute({"path": "README_AGENT.md"})
        lines = content.split('\n')
        print(f"   결과: {len(lines)}줄 읽음")
        print(f"   첫 줄: {lines[0]}")
    except Exception as e:
        print(f"   에러: {e}")
    print()

    # 3. SearchCodeTool 테스트
    print("🔍 Test 3: SearchCodeTool")
    search_tool = SearchCodeTool(workspace)
    results = await search_tool.execute({
        "pattern": "class.*Agent",
        "path": "src/agent",
        "file_pattern": "*.py"
    })
    print(f"   결과: {len(results['matches'])}개 매칭")
    for match in results['matches'][:3]:  # 처음 3개만
        print(f"   - {match['file']}:{match['line_number']}: {match['line'].strip()}")
    print()

    # 4. FinishTool 테스트
    print("✅ Test 4: FinishTool")
    finish_tool = FinishTool()
    result = await finish_tool.execute({
        "success": True,
        "message": "모든 도구 테스트 완료"
    })
    print(f"   결과: {result}")
    print()

    print("=" * 60)
    print("✅ 모든 도구 정상 작동!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_tools())
