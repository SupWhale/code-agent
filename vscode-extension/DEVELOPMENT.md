# VS Code Extension 개발 가이드

## 🎯 현재 상태: Phase 2 - 기본 구현 완료

### ✅ 구현 완료 항목

#### 1. 핵심 모듈
- **connection.ts**: WebSocket 연결 관리
- **fileSync.ts**: 파일 동기화
- **extension.ts**: Extension 엔트리 포인트

#### 2. 기능
- ✅ 서버 연결/해제
- ✅ 파일 업로드 (workspace, 개별 파일, 선택 영역)
- ✅ Agent 요청 (전체 파일, 선택 영역)
- ✅ 실시간 이벤트 스트리밍
- ✅ Diff 뷰어
- ✅ 자동 재연결
- ✅ 보안 필터링

#### 3. UI/UX
- ✅ Status bar indicator
- ✅ Output channel (로그)
- ✅ Command palette commands
- ✅ Context menu integration
- ✅ Progress notifications

---

## 🚀 빌드 및 실행

### 1. 의존성 설치

```bash
cd vscode-extension
npm install
```

### 2. 컴파일

```bash
npm run compile
```

### 3. 디버그 실행

1. VS Code에서 `vscode-extension` 폴더 열기
2. F5 키 누르기 (Extension Development Host 실행)
3. 새 VS Code 창에서 테스트

### 4. 패키징

```bash
npm run package
```

이 명령은 `ai-coding-agent-0.1.0.vsix` 파일을 생성합니다.

### 5. 설치

```bash
code --install-extension ai-coding-agent-0.1.0.vsix
```

---

## 📝 사용 시나리오

### 시나리오 1: 전체 프로젝트 수정

```
1. VS Code에서 프로젝트 열기
2. Cmd+Shift+P → "AI Agent: 서버 연결"
3. 자동으로 모든 파일 업로드
4. Cmd+Shift+P → "AI Agent: 코드 수정 요청"
5. 입력: "모든 Python 파일에 타입 힌트 추가"
6. Agent가 파일들을 순차적으로 처리
7. 각 파일마다 diff 확인 후 적용
```

### 시나리오 2: 특정 함수 리팩토링

```
1. 함수 전체 선택
2. 우클릭 → "AI Agent: 선택 영역 수정"
3. 입력: "이 함수를 더 효율적으로 리팩토링해줘"
4. Diff 확인 후 적용
```

### 시나리오 3: 버그 수정

```
1. 문제가 있는 파일 열기
2. Cmd+Shift+P → "AI Agent: 코드 수정 요청"
3. 입력: "이 파일의 버그를 찾아서 고쳐줘"
4. Agent 분석 결과 확인
5. 수정사항 적용
```

---

## 🔧 개발 팁

### 디버깅

1. **Output Channel 확인**
   - View → Output → "AI Coding Agent"
   - 모든 WebSocket 메시지 확인 가능

2. **개발자 도구**
   - Help → Toggle Developer Tools
   - Console에서 에러 확인

3. **서버 로그 확인**
   - 서버 측 `docker compose logs -f coding-agent`

### 테스트

```typescript
// 수동 테스트 시나리오
1. 연결 테스트
   - 서버 실행 전 연결 시도 → 에러 메시지 확인
   - 서버 실행 후 연결 → 성공 메시지 확인

2. 파일 업로드 테스트
   - 빈 프로젝트 → 0개 파일
   - Python 프로젝트 → .py 파일만 업로드
   - .env 파일 → 차단 확인

3. Agent 요청 테스트
   - 간단한 요청 → 빠른 응답
   - 복잡한 요청 → 진행 상황 표시

4. Diff 테스트
   - 변경사항 미리보기
   - 적용/취소 동작
```

---

## 📦 파일 구조

```
vscode-extension/
├── package.json           # Extension 메타데이터
├── tsconfig.json          # TypeScript 설정
├── README.md              # 사용자 문서
├── DEVELOPMENT.md         # 이 파일
├── .vscodeignore          # 패키징 제외 파일
├── src/
│   ├── extension.ts       # 메인 엔트리 포인트
│   ├── connection.ts      # WebSocket 연결
│   ├── fileSync.ts        # 파일 동기화
│   ├── ui/                # UI 컴포넌트 (TODO)
│   └── commands/          # Commands (TODO)
├── out/                   # 컴파일된 JS 파일
└── resources/
    └── icons/             # 아이콘 (TODO)
```

---

## 🎨 다음 단계 (Phase 3)

### 추가할 기능

1. **Side Panel**
   ```typescript
   - 작업 히스토리
   - 진행 상황 표시
   - 파일 변경 목록
   ```

2. **Chat UI**
   ```typescript
   - 대화형 인터페이스
   - 이전 대화 기록
   - 컨텍스트 유지
   ```

3. **고급 기능**
   ```typescript
   - Undo/Redo for AI changes
   - Snippet 저장
   - 자주 쓰는 요청 템플릿
   ```

4. **설정 UI**
   ```typescript
   - 비주얼 설정 페이지
   - 서버 연결 테스트
   - 파일 필터 설정
   ```

---

## 🐛 알려진 이슈

1. **Windows 경로 문제**
   - 해결: `fileSync.ts`에서 자동 변환

2. **대용량 프로젝트**
   - 제한: 100개 파일까지만 자동 업로드
   - 해결: 수동으로 특정 파일만 업로드

3. **WebSocket 타임아웃**
   - 30초마다 자동 ping 전송

---

## 📚 참고 자료

- [VS Code Extension API](https://code.visualstudio.com/api)
- [WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/)

---

## ✅ 테스트 체크리스트

- [ ] 서버 연결/해제
- [ ] 파일 업로드 (전체)
- [ ] 파일 업로드 (개별)
- [ ] 선택 영역 업로드
- [ ] Agent 요청
- [ ] 실시간 이벤트 수신
- [ ] Diff 뷰어
- [ ] 변경사항 적용
- [ ] 자동 재연결
- [ ] 보안 필터링

---

**개발 완료일**: 2026-02-11
**다음 Phase**: UI/UX 개선
