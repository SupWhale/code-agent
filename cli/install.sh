#!/bin/bash
# code-agent CLI 설치 스크립트 (macOS)
# 사용법: bash cli/install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
BIN_LINK="/usr/local/bin/agent"

echo "==> 가상환경 생성"
python3 -m venv "$VENV_DIR"

echo "==> 의존성 설치"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q

echo "==> 실행 래퍼 생성"
cat > "$SCRIPT_DIR/agent" << EOF
#!/bin/bash
exec "$VENV_DIR/bin/python" -m cli.main "\$@"
EOF
chmod +x "$SCRIPT_DIR/agent"

echo "==> /usr/local/bin/agent 심링크 생성 (sudo 필요)"
sudo ln -sf "$SCRIPT_DIR/agent" "$BIN_LINK"

echo ""
echo "✓ 설치 완료! 다음 명령으로 시작하세요:"
echo ""
echo "  agent status"
echo "  agent session new"
echo "  agent chat"
echo ""
