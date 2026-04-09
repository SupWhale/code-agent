"""
code-agent CLI
맥 터미널에서 AI 코딩 에이전트를 사용하기 위한 CLI

사용법:
  agent status              — 서버 상태 확인
  agent session new         — 새 세션 생성
  agent session info        — 현재 세션 정보
  agent session delete      — 현재 세션 삭제
  agent files ls [path]     — 파일 목록 (트리)
  agent files show <path>   — 파일 내용 출력
  agent files upload <path> — 로컬 파일 업로드
  agent ask "<요청>"         — 에이전트에게 작업 요청 (스트리밍)
  agent chat                — 대화형 인터랙티브 모드
  agent config set <key> <value>
  agent config show
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from . import config
from .client import AgentClient

app = typer.Typer(
    name="agent",
    help="AI 코딩 에이전트 CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
session_app = typer.Typer(help="세션 관리", no_args_is_help=True)
files_app = typer.Typer(help="파일 관리", no_args_is_help=True)
config_app = typer.Typer(help="설정 관리", no_args_is_help=True)

app.add_typer(session_app, name="session")
app.add_typer(files_app, name="files")
app.add_typer(config_app, name="config")

console = Console()
err_console = Console(stderr=True, style="bold red")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _client() -> AgentClient:
    return AgentClient()


def _require_session() -> str:
    sid = config.get("session_id")
    if not sid:
        err_console.print("[!] 세션이 없습니다. 먼저 'agent session new' 를 실행하세요.")
        raise typer.Exit(1)
    return sid


def _build_file_tree(files: List[str], label: str = "workspace") -> Tree:
    tree = Tree(f":open_file_folder: [bold]{label}[/]")
    dirs: dict = {}
    for f in sorted(files):
        parts = Path(f).parts
        node = tree
        for i, part in enumerate(parts[:-1]):
            key = "/".join(parts[: i + 1])
            if key not in dirs:
                dirs[key] = node.add(f":file_folder: [dim]{part}[/]")
            node = dirs[key]
        node.add(f":page_facing_up: {parts[-1]}")
    return tree


# ── Status ───────────────────────────────────────────────────────────────────

@app.command()
def status():
    """서버 및 현재 세션 상태 확인"""
    client = _client()
    cfg = config.load()

    try:
        h = client.health()
        server_ok = True
        model = h.get("model", "-")
        ollama = h.get("ollama", "-")
    except Exception as e:
        server_ok = False
        model = "-"
        ollama = str(e)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("key", style="dim")
    table.add_column("value")
    table.add_row("서버", cfg.get("server_url", "-"))
    table.add_row("서버 상태", "[green]OK[/]" if server_ok else "[red]연결 실패[/]")
    if server_ok:
        table.add_row("모델", model)
        table.add_row("Ollama", str(ollama))

    sid = cfg.get("session_id")
    if sid:
        table.add_row("세션", sid)
        try:
            sess = client.get_session(sid)
            if sess:
                table.add_row("workspace", sess.get("workspace_path", "-"))
                table.add_row("파일 수", str(sess.get("file_count", 0)))
            else:
                table.add_row("세션 상태", "[yellow]세션 없음 (만료?)[/]")
        except Exception:
            table.add_row("세션 상태", "[red]조회 실패[/]")
    else:
        table.add_row("세션", "[dim]없음[/]")

    console.print(Panel(table, title="[bold]code-agent 상태[/]", border_style="blue"))


# ── Session ───────────────────────────────────────────────────────────────────

@session_app.command("new")
def session_new(session_id: Optional[str] = typer.Argument(None, help="세션 ID (생략 시 자동)")):
    """새 세션 생성"""
    client = _client()
    try:
        sess = client.create_session(session_id)
    except Exception as e:
        err_console.print(f"[!] 세션 생성 실패: {e}")
        raise typer.Exit(1)

    config.set_value("session_id", sess["session_id"])
    config.set_value("workspace_path", sess["workspace_path"])

    console.print(Panel(
        f"[bold green]세션 생성 완료[/]\n\n"
        f"ID        : [cyan]{sess['session_id']}[/]\n"
        f"workspace : {sess['workspace_path']}",
        border_style="green",
    ))


@session_app.command("info")
def session_info():
    """현재 세션 정보"""
    sid = _require_session()
    client = _client()
    try:
        sess = client.get_session(sid)
    except Exception as e:
        err_console.print(f"[!] 조회 실패: {e}")
        raise typer.Exit(1)

    if not sess:
        err_console.print(f"[!] 세션 '{sid}' 를 찾을 수 없습니다.")
        config.set_value("session_id", None)
        raise typer.Exit(1)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("key", style="dim")
    table.add_column("value")
    table.add_row("ID", sess["session_id"])
    table.add_row("workspace", sess["workspace_path"])
    table.add_row("파일 수", str(sess["file_count"]))
    table.add_row("생성일", sess["created_at"])
    table.add_row("마지막 활동", sess["last_activity"])
    console.print(Panel(table, title="[bold]세션 정보[/]", border_style="blue"))


@session_app.command("delete")
def session_delete():
    """현재 세션 삭제"""
    sid = _require_session()
    client = _client()
    confirm = Prompt.ask(f"세션 '{sid}' 를 삭제하시겠습니까?", choices=["y", "n"], default="n")
    if confirm != "y":
        console.print("[dim]취소됨[/]")
        return
    try:
        client.delete_session(sid)
    except Exception as e:
        err_console.print(f"[!] 삭제 실패: {e}")
        raise typer.Exit(1)
    config.set_value("session_id", None)
    config.set_value("workspace_path", None)
    console.print("[green]세션 삭제 완료[/]")


# ── Files ──────────────────────────────────────────────────────────────────

@files_app.command("ls")
def files_ls(path: Optional[str] = typer.Argument(None, help="경로 필터 (prefix)")):
    """워크스페이스 파일 목록 (트리 형식)"""
    sid = _require_session()
    client = _client()
    try:
        files = client.list_files(sid)
    except Exception as e:
        err_console.print(f"[!] 파일 목록 조회 실패: {e}")
        raise typer.Exit(1)

    if path:
        files = [f for f in files if f.startswith(path)]

    if not files:
        console.print("[dim]파일 없음[/]")
        return

    console.print(_build_file_tree(files))
    console.print(f"\n[dim]총 {len(files)}개 파일[/]")


@files_app.command("show")
def files_show(
    path: str = typer.Argument(..., help="파일 경로"),
    no_line_numbers: bool = typer.Option(False, "--no-lines", is_flag=True, help="줄 번호 숨기기"),
):
    """파일 내용 출력 (신택스 하이라이팅)"""
    sid = _require_session()
    client = _client()
    try:
        content = client.get_file(sid, path)
    except Exception as e:
        err_console.print(f"[!] 파일 조회 실패: {e}")
        raise typer.Exit(1)

    if content is None:
        err_console.print(f"[!] 파일을 찾을 수 없습니다: {path}")
        raise typer.Exit(1)

    ext = Path(path).suffix.lstrip(".")
    lang_map = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "json": "json", "yml": "yaml", "yaml": "yaml",
        "sh": "bash", "md": "markdown", "html": "html", "css": "css",
        "go": "go", "rs": "rust", "java": "java", "cpp": "cpp",
    }
    lang = lang_map.get(ext, "text")
    syntax = Syntax(content, lang, line_numbers=not no_line_numbers, theme="monokai")
    console.print(Panel(syntax, title=f"[bold]{path}[/]", border_style="dim"))


@files_app.command("upload")
def files_upload(
    paths: List[Path] = typer.Argument(..., help="업로드할 로컬 파일 경로(들)"),
    base: Optional[str] = typer.Option(None, "--base", help="경로 기준 디렉토리 (생략 시 파일명만 사용)"),
):
    """로컬 파일을 워크스페이스에 업로드"""
    sid = _require_session()
    client = _client()
    base_path = Path(base) if base else None

    files = []
    for p in paths:
        if not p.exists():
            err_console.print(f"[!] 파일 없음: {p}")
            continue
        rel = str(p.relative_to(base_path)) if base_path else p.name
        files.append({"path": rel, "content": p.read_text(encoding="utf-8", errors="replace")})

    if not files:
        err_console.print("[!] 업로드할 파일이 없습니다.")
        raise typer.Exit(1)

    try:
        result = client.upload_files(sid, files)
    except Exception as e:
        err_console.print(f"[!] 업로드 실패: {e}")
        raise typer.Exit(1)

    console.print(f"[green]업로드 완료[/] — {result['uploaded_count']}개 파일 (총 {result['total_files']}개)")


# ── Ask (one-shot) ────────────────────────────────────────────────────────────

@app.command()
def ask(request: str = typer.Argument(..., help="에이전트에게 요청할 작업")):
    """에이전트에게 작업을 요청하고 결과를 스트리밍으로 출력"""
    sid = _require_session()
    asyncio.run(_run_ask(sid, request))


async def _run_ask(session_id: str, user_request: str):
    client = _client()
    console.print(Panel(f"[bold]{user_request}[/]", title="[cyan]요청[/]", border_style="cyan"))
    try:
        async for msg in client.run_agent(session_id, user_request):
            _render_event(msg)
    except Exception as e:
        err_console.print(f"\n[!] 오류: {e}")
        raise typer.Exit(1)


def _render_event(msg: dict):
    mtype = msg.get("type")

    if mtype == "task_created":
        console.print(f"[dim]▶ 작업 시작 — ID: {msg.get('task_id')}[/]")

    elif mtype == "agent_event":
        event = msg.get("event", {})
        etype = event.get("type")

        if etype == "llm_response":
            reasoning = event.get("reasoning", "")
            if reasoning:
                console.print(f"\n[yellow]◎ 추론:[/] {reasoning}")

        elif etype == "action_start":
            tool = event.get("tool", "")
            params = event.get("params", {})
            param_str = ", ".join(f"{k}={repr(v)[:40]}" for k, v in params.items())
            console.print(f"[blue]  → {tool}[/]({param_str})")

        elif etype == "action_success":
            tool = event.get("tool", "")
            result = event.get("result", "")
            if tool in ("edit_file", "create_file", "delete_file"):
                console.print(f"[green]  ✓ {tool}[/] 완료")
            elif tool == "read_file":
                console.print(f"[dim]  ✓ read_file 완료[/]")
            elif tool == "finish":
                summary = event.get("params", {}).get("summary", str(result))
                console.print(Panel(Markdown(summary), title="[green bold]완료[/]", border_style="green"))
            else:
                console.print(f"[green]  ✓ {tool}[/]: {str(result)[:200]}")

        elif etype == "action_error":
            console.print(f"[red]  ✗ {event.get('tool')}[/]: {event.get('error')}")

        elif etype == "ask_user":
            console.print(f"\n[magenta]? {event.get('question')}[/]")

        elif etype == "task_completed":
            console.print("\n[green bold]✓ 작업 완료[/]")

        elif etype == "task_failed":
            console.print(f"\n[red bold]✗ 작업 실패[/]: {event.get('error')}")

    elif mtype == "file_changed":
        console.print(f"[dim]  ↺ 파일 변경: {msg.get('path')}[/]")

    elif mtype == "error":
        console.print(f"[red][!] {msg.get('error')}[/]")


# ── Interactive Chat ───────────────────────────────────────────────────────────

@app.command()
def chat():
    """대화형 인터랙티브 모드 (exit 또는 Ctrl+C 로 종료)"""
    sid = _require_session()
    console.print(Panel(
        "[bold]AI 코딩 에이전트 대화 모드[/]\n"
        "[dim]종료: exit / quit / Ctrl+C  |  커맨드: /files  /show <path>  /help[/]",
        border_style="blue",
    ))
    try:
        sess = _client().get_session(sid)
        if sess:
            console.print(f"[dim]세션: {sid} | workspace: {sess.get('workspace_path')}[/]\n")
    except Exception:
        pass

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]>[/]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]종료[/]")
            break

        stripped = user_input.strip()
        if not stripped:
            continue
        if stripped.lower() in ("exit", "quit", "q"):
            console.print("[dim]종료[/]")
            break

        if stripped.startswith("/"):
            _handle_slash_command(stripped, sid)
            continue

        asyncio.run(_run_ask(sid, stripped))
        console.print()


def _handle_slash_command(stripped: str, sid: str):
    parts = stripped[1:].split()
    cmd = parts[0] if parts else ""
    client = _client()

    if cmd == "files":
        try:
            files = client.list_files(sid)
            console.print(_build_file_tree(files))
        except Exception as e:
            err_console.print(f"[!] {e}")

    elif cmd == "show" and len(parts) > 1:
        try:
            content = client.get_file(sid, parts[1])
            if content:
                ext = Path(parts[1]).suffix.lstrip(".")
                console.print(Syntax(content, ext or "text", line_numbers=True, theme="monokai"))
            else:
                console.print("[red]파일 없음[/]")
        except Exception as e:
            err_console.print(f"[!] {e}")

    elif cmd == "status":
        try:
            console.print(client.health())
        except Exception as e:
            err_console.print(f"[!] {e}")

    elif cmd == "help":
        console.print(
            "[dim]/files[/]        — 파일 목록\n"
            "[dim]/show <path>[/]  — 파일 내용\n"
            "[dim]/status[/]       — 서버 상태\n"
            "[dim]exit[/]          — 종료"
        )
    else:
        console.print(f"[yellow]알 수 없는 커맨드: /{cmd}[/]  (도움말: /help)")


# ── Config ─────────────────────────────────────────────────────────────────────

@config_app.command("show")
def config_show():
    """현재 설정 출력"""
    cfg = config.load()
    table = Table(show_header=True, header_style="bold")
    table.add_column("키")
    table.add_column("값")
    for k, v in cfg.items():
        table.add_row(k, str(v) if v is not None else "[dim]없음[/]")
    console.print(table)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(...),
    value: str = typer.Argument(...),
):
    """설정 값 변경 (예: agent config set server_url http://localhost:8000)"""
    config.set_value(key, value)
    console.print(f"[green]{key}[/] = {value}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
