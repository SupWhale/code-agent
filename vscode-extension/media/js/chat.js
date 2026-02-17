// @ts-check
(function () {
    // @ts-ignore
    const vscode = acquireVsCodeApi();

    const messagesDiv = document.getElementById('messages');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const clearBtn = document.getElementById('clear-btn');
    const contextBtn = document.getElementById('context-btn');
    const thinkingIndicator = document.getElementById('thinking-indicator');
    const messagesContainer = document.getElementById('messages-container');
    const workingDirInput = document.getElementById('working-dir-input');
    const browseDirBtn = document.getElementById('browse-dir-btn');

    // 이전 상태 복원
    const previousState = vscode.getState() || { messages: [] };
    if (previousState.messages && previousState.messages.length > 0) {
        previousState.messages.forEach(msg => {
            addMessageToDOM(msg);
        });
    } else {
        showEmptyState();
    }

    // 메시지 전송
    function sendMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        // 빈 상태 제거
        removeEmptyState();

        // 입력 필드 초기화
        userInput.value = '';
        userInput.style.height = 'auto';

        // Extension에 메시지 전송
        const workingDir = workingDirInput ? workingDirInput.value.trim() || '.' : '.';
        vscode.postMessage({
            type: 'userMessage',
            text: text,
            workingDir: workingDir
        });
    }

    // 메시지를 DOM에 추가
    function addMessageToDOM(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${message.role}`;
        messageDiv.dataset.id = message.id;

        // 헤더
        const header = document.createElement('div');
        header.className = 'message-header';
        const icon = message.role === 'user' ? '👤' : '🤖';
        const name = message.role === 'user' ? 'You' : 'AI Agent';
        header.innerHTML = `<span class="icon">${icon}</span><span>${name}</span>`;

        // 콘텐츠
        const content = document.createElement('div');
        content.className = 'message-content';
        content.innerHTML = formatMessageContent(message.content, message.codeBlocks);

        messageDiv.appendChild(header);
        messageDiv.appendChild(content);
        messagesDiv.appendChild(messageDiv);

        // Syntax highlighting 적용
        highlightCode();

        // 스크롤을 아래로
        scrollToBottom();

        // 상태 저장
        saveState();
    }

    // 메시지 내용 포맷팅
    function formatMessageContent(text, codeBlocks) {
        // 코드 블록 치환
        let formatted = text;

        if (codeBlocks && codeBlocks.length > 0) {
            codeBlocks.forEach((block) => {
                const globalIndex = codeBlockCounter++;
                const codeBlockHtml = createCodeBlock(block.language, block.code, globalIndex, block.path);
                // 코드 블록을 HTML로 치환
                const pattern = new RegExp('```' + block.language + '?\\n[\\s\\S]*?\\n```', 'g');
                formatted = formatted.replace(pattern, codeBlockHtml);
            });
        }

        // 인라인 코드
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

        // 줄바꿈
        formatted = formatted.replace(/\n/g, '<br>');

        // 볼드
        formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // 이탤릭
        formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        return formatted;
    }

    // 코드 블록 생성 (CSP 준수: onclick 대신 data-* + 이벤트 위임)
    // 주의: \n → <br> 전역 치환에 의해 HTML 구조가 깨지지 않도록 한 줄로 생성
    //       코드 내 개행은 &#10; 으로 이스케이프 (textContent로 읽을 때 \n 복원됨)
    function createCodeBlock(language, code, index, filePath) {
        const escapedCode = escapeHtml(code).replace(/\n/g, '&#10;');
        const prismLang = getPrismLanguage(language);
        const label = filePath ? filePath : language;
        const escapedLabel = escapeHtml(label);
        const escapedLang = escapeHtml(language);
        const escapedFilePath = filePath ? escapeHtml(filePath) : '';
        // 모든 HTML을 한 줄로 (중간에 \n이 없어야 전역 치환에 안전)
        return '<div class="code-block" data-index="' + index + '">'
            + '<div class="code-header">'
            + '<span class="code-language">' + escapedLabel + '</span>'
            + '<div class="code-actions">'
            + '<button class="code-btn copy-btn" data-action="copy" data-index="' + index + '">복사</button>'
            + '<button class="code-btn apply-btn" data-action="apply" data-index="' + index + '" data-language="' + escapedLang + '" data-filepath="' + escapedFilePath + '">적용</button>'
            + '</div></div>'
            + '<div class="code-content"><pre><code class="language-' + prismLang + '">' + escapedCode + '</code></pre></div>'
            + '</div>';
    }

    // Prism 언어 매핑
    function getPrismLanguage(lang) {
        const langMap = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'sh': 'bash',
            'yml': 'yaml',
            'dockerfile': 'docker'
        };
        return langMap[lang] || lang;
    }

    // Prism 하이라이팅 적용
    function highlightCode() {
        if (typeof Prism !== 'undefined') {
            Prism.highlightAll();
        }
    }

    // HTML 이스케이프
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // 이벤트 위임: 코드블록 버튼 클릭 처리 (CSP 준수 - onclick 속성 미사용)
    messagesDiv.addEventListener('click', function (e) {
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;

        const action = btn.getAttribute('data-action');
        const index = btn.getAttribute('data-index');
        const codeBlock = document.querySelector(`.code-block[data-index="${index}"]`);
        if (!codeBlock) {
            console.error('[codeBlock btn] element not found for index:', index);
            return;
        }
        const code = codeBlock.querySelector('code').textContent;

        if (action === 'copy') {
            console.log('[copyCode] index:', index, 'code length:', code ? code.length : 0);
            vscode.postMessage({ type: 'copyCode', code: code });

        } else if (action === 'apply') {
            const language = btn.getAttribute('data-language') || 'text';
            const rawFilePath = btn.getAttribute('data-filepath');
            const filePath = rawFilePath && rawFilePath.trim() !== '' ? rawFilePath : null;
            console.log('[applyCode] index:', index, '| language:', language, '| filePath:', filePath, '| code length:', code ? code.length : 0);
            vscode.postMessage({
                type: 'applyCode',
                code: code,
                language: language,
                filePath: filePath
            });
            console.log('[applyCode] postMessage sent');
        }
    });

    // 빈 상태 표시
    function showEmptyState() {
        if (messagesDiv.children.length === 0) {
            messagesDiv.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">💬</div>
                    <div class="empty-state-text">AI Coding Agent에게 질문해보세요</div>
                    <div class="empty-state-hint">
                        코드 작성, 리팩토링, 디버깅 등<br>
                        무엇이든 물어보세요!
                    </div>
                </div>
            `;
        }
    }

    // 빈 상태 제거
    function removeEmptyState() {
        const emptyState = messagesDiv.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }
    }

    // Thinking 표시
    function showThinking(show) {
        thinkingIndicator.style.display = show ? 'flex' : 'none';
        if (show) {
            scrollToBottom();
        }
    }

    // 에러 표시
    function showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = `❌ ${message}`;
        messagesDiv.appendChild(errorDiv);
        scrollToBottom();

        // 5초 후 제거
        setTimeout(() => {
            errorDiv.remove();
        }, 5000);
    }

    // 스크롤을 아래로
    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // 상태 저장
    function saveState() {
        const messages = Array.from(messagesDiv.querySelectorAll('.message')).map(el => ({
            id: el.dataset.id,
            role: el.classList.contains('user') ? 'user' : 'assistant',
            content: el.querySelector('.message-content').textContent
        }));

        vscode.setState({ messages });
    }

    // 전역 코드블록 카운터 (메시지마다 0으로 리셋되지 않도록)
    let codeBlockCounter = 0;

    let currentStreamingMessage = null;

    // Extension으로부터 메시지 수신
    window.addEventListener('message', event => {
        const message = event.data;

        switch (message.type) {
            case 'userMessage':
                addMessageToDOM(message.message);
                currentStreamingMessage = null;
                break;

            case 'aiMessage':
                currentStreamingMessage = null;
                addMessageToDOM(message.message);
                break;

            case 'aiThinking':
                // 스트리밍 응답 표시
                if (!currentStreamingMessage) {
                    currentStreamingMessage = createStreamingMessage();
                }
                appendToStreamingMessage(currentStreamingMessage, message.content);
                break;

            case 'thinking':
                showThinking(message.show);
                break;

            case 'error':
                showError(message.message);
                showThinking(false);
                currentStreamingMessage = null;
                break;

            case 'contextInfo':
                // 컨텍스트 정보 표시 (나중에 구현)
                console.log('Context:', message.context);
                break;

            case 'workspaceInfo':
                updateWorkspacePath(message.path);
                break;

            case 'workspaceBrowseResult':
                if (workingDirInput && message.path) {
                    workingDirInput.value = message.path;
                }
                break;
        }
    });

    // 스트리밍 메시지 생성
    function createStreamingMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant streaming';
        messageDiv.dataset.id = 'streaming-' + Date.now();

        const header = document.createElement('div');
        header.className = 'message-header';
        header.innerHTML = '<span class="icon">🤖</span><span>AI Agent</span>';

        const content = document.createElement('div');
        content.className = 'message-content';
        content.innerHTML = '';

        messageDiv.appendChild(header);
        messageDiv.appendChild(content);
        messagesDiv.appendChild(messageDiv);
        scrollToBottom();

        return messageDiv;
    }

    // 스트리밍 메시지에 내용 추가
    function appendToStreamingMessage(messageDiv, text) {
        const content = messageDiv.querySelector('.message-content');
        content.textContent += text;
        scrollToBottom();
    }

    // Workspace 경로 표시 업데이트
    function updateWorkspacePath(path) {
        const workspacePathEl = document.getElementById('workspace-path');
        if (workspacePathEl && path) {
            // 서버 절대 경로에서 마지막 의미있는 부분만 표시
            const parts = path.replace(/\\/g, '/').split('/');
            const displayPath = parts.slice(-3).join('/');
            workspacePathEl.textContent = displayPath;
            workspacePathEl.title = path;
        }
    }

    // 이벤트 리스너
    sendBtn.addEventListener('click', sendMessage);

    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // 입력 필드 자동 높이 조절
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = Math.min(userInput.scrollHeight, 200) + 'px';
    });

    // 폴더 브라우즈 버튼
    if (browseDirBtn) {
        browseDirBtn.addEventListener('click', () => {
            vscode.postMessage({ type: 'browseWorkspace' });
        });
    }

    // working-dir-input: Enter 키로 포커스 해제
    if (workingDirInput) {
        workingDirInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                workingDirInput.blur();
                userInput.focus();
            }
        });
    }

    clearBtn.addEventListener('click', () => {
        if (confirm('채팅 내역을 모두 삭제하시겠습니까?')) {
            messagesDiv.innerHTML = '';
            vscode.postMessage({ type: 'clearChat' });
            vscode.setState({ messages: [] });
            showEmptyState();
        }
    });

    contextBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'requestContext' });
    });

    // 포커스
    userInput.focus();
})();
