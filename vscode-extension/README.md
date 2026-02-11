# AI Coding Agent - VS Code Extension

AI-powered coding assistant using Ollama and Qwen2.5-Coder

## Features

- 🤖 **AI-Powered Code Generation**: Generate and modify code using advanced AI models
- 🔄 **Real-time Sync**: Automatic file synchronization with the server
- ✨ **Smart Code Editing**: Context-aware code modifications
- 📝 **Selection Support**: Modify specific code sections
- 🔍 **Diff Viewer**: Preview changes before applying

## Requirements

- VS Code 1.80.0 or higher
- AI Coding Agent server running (see main project)
- Node.js 18+ (for development)

## Installation

### From VSIX

```bash
code --install-extension ai-coding-agent-0.1.0.vsix
```

### From Source

```bash
cd vscode-extension
npm install
npm run compile
```

## Quick Start

1. **Start the AI Agent server**
   ```bash
   # In the main project directory
   uvicorn src.main:app --host 0.0.0.0 --port 8000
   ```

2. **Connect from VS Code**
   - Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
   - Type "AI Agent: 서버 연결"
   - Wait for connection confirmation

3. **Use AI Agent**
   - Right-click in editor → "AI Agent: 코드 수정 요청"
   - Or select code → Right-click → "AI Agent: 선택 영역 수정"

## Commands

| Command | Description | Shortcut |
|---------|-------------|----------|
| `AI Agent: 서버 연결` | Connect to server | - |
| `AI Agent: 연결 해제` | Disconnect from server | - |
| `AI Agent: 코드 수정 요청` | Request code modification | - |
| `AI Agent: 선택 영역 수정` | Modify selected code | Context menu |
| `AI Agent: 현재 파일 업로드` | Upload current file | - |

## Configuration

```json
{
  "aiAgent.serverUrl": "ws://localhost:8000",
  "aiAgent.autoConnect": false,
  "aiAgent.autoUpload": true,
  "aiAgent.showDiff": true,
  "aiAgent.maxFileSize": 1048576
}
```

### Settings

- **serverUrl**: AI Agent server WebSocket URL
- **autoConnect**: Auto-connect on VS Code startup
- **autoUpload**: Auto-upload workspace files on connect
- **showDiff**: Show diff viewer before applying changes
- **maxFileSize**: Maximum file size to upload (bytes)

## Usage Examples

### Example 1: Add Type Hints

1. Open a Python file
2. Press `Cmd+Shift+P` → "AI Agent: 코드 수정 요청"
3. Enter: "모든 함수에 타입 힌트 추가"
4. Review diff and apply

### Example 2: Refactor Function

1. Select a function
2. Right-click → "AI Agent: 선택 영역 수정"
3. Enter: "이 함수를 더 효율적으로 리팩토링해줘"
4. Review and apply

### Example 3: Add Docstrings

1. Open project
2. Press `Cmd+Shift+P` → "AI Agent: 코드 수정 요청"
3. Enter: "모든 함수에 docstring 추가"
4. Agent will process multiple files sequentially

## Status Bar

The status bar shows connection status:

- 🔌 **$(plug) AI Agent**: Not connected (click to connect)
- ✅ **$(check) AI Agent**: Connected (click to disconnect)

## Output Channel

View detailed logs in the "AI Coding Agent" output channel:
- View → Output → Select "AI Coding Agent"

## Security

Files are automatically filtered:
- `.env`, `*.key`, `*.pem` - Blocked
- `node_modules/`, `.git/` - Excluded
- Large files (>1MB) - Skipped by default

## Troubleshooting

### Cannot connect to server

1. Check if server is running:
   ```bash
   curl http://localhost:8000/health
   ```

2. Verify WebSocket URL in settings

3. Check firewall settings

### Files not uploading

1. Check file size limit in settings
2. Verify file is not in blocked patterns
3. Check output channel for errors

### Changes not applying

1. Enable diff viewer in settings
2. Manually save file after applying
3. Check file permissions

## Development

```bash
# Install dependencies
npm install

# Compile
npm run compile

# Watch mode
npm run watch

# Package
npm run package
```

## Contributing

See main project repository for contribution guidelines.

## License

MIT

## Links

- [GitHub Repository](https://github.com/your-repo/ai-coding-agent)
- [Documentation](https://github.com/your-repo/ai-coding-agent/blob/main/README_AGENT.md)
- [Issues](https://github.com/your-repo/ai-coding-agent/issues)
