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
        vscode.postMessage({
            type: 'userMessage',
            text: text
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
            codeBlocks.forEach((block, index) => {
                const codeBlockHtml = createCodeBlock(block.language, block.code, index);
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

    // 코드 블록 생성
    function createCodeBlock(language, code, index) {
        const escapedCode = escapeHtml(code);
        return `
            <div class="code-block" data-index="${index}">
                <div class="code-header">
                    <span class="code-language">${language}</span>
                    <div class="code-actions">
                        <button class="code-btn copy-btn" onclick="copyCode(${index})">
                            복사
                        </button>
                        <button class="code-btn apply-btn" onclick="applyCode('${language}', ${index})">
                            적용
                        </button>
                    </div>
                </div>
                <div class="code-content">
                    <pre><code>${escapedCode}</code></pre>
                </div>
            </div>
        `;
    }

    // HTML 이스케이프
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // 코드 복사
    window.copyCode = function (index) {
        const codeBlock = document.querySelector(`.code-block[data-index="${index}"]`);
        if (!codeBlock) return;

        const code = codeBlock.querySelector('code').textContent;
        vscode.postMessage({
            type: 'copyCode',
            code: code
        });
    };

    // 코드 적용
    window.applyCode = function (language, index) {
        const codeBlock = document.querySelector(`.code-block[data-index="${index}"]`);
        if (!codeBlock) return;

        const code = codeBlock.querySelector('code').textContent;
        vscode.postMessage({
            type: 'applyCode',
            code: code,
            language: language
        });
    };

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

    // Extension으로부터 메시지 수신
    window.addEventListener('message', event => {
        const message = event.data;

        switch (message.type) {
            case 'userMessage':
                addMessageToDOM(message.message);
                break;

            case 'aiMessage':
                addMessageToDOM(message.message);
                break;

            case 'thinking':
                showThinking(message.show);
                break;

            case 'error':
                showError(message.message);
                showThinking(false);
                break;

            case 'contextInfo':
                // 컨텍스트 정보 표시 (나중에 구현)
                console.log('Context:', message.context);
                break;
        }
    });

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
