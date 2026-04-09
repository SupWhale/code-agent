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

@session_app.command("list")
def session_list():
    """서버의 전체 세션 목록 조회"""
    client = _client()
    try:
        sessions = client.list_sessions()
    except Exception as e:
        err_console.print(f"[!] 세션 목록 조회 실패: {e}")
        raise typer.Exit(1)

    if not sessions:
        console.print("[dim]세션 없음[/]")
        return

    current_sid = config.get("session_id")
    table = Table(header_style="bold", show_lines=True)
    table.add_column("", width=2)
    table.add_column("세션 ID")
    table.add_column("파일 수", justify="right")
    table.add_column("마지막 활동")
    table.add_column("상태")

    for s in sessions:
        is_current = s["session_id"] == current_sid
        marker = "[green]▶[/]" if is_current else ""
        expired = s.get("is_expired", False)
        status = "[red]만료[/]" if expired else "[green]활성[/]"
        sid_display = f"[bold]{s['session_id']}[/]" if is_current else s["session_id"]
        table.add_row(marker, sid_display, str(s["file_count"]), s["last_activity"][:19], status)

    console.print(table)
    console.print(f"[dim]총 {len(sessions)}개 세션 | 현재: {current_sid or '없음'}[/]")


@session_app.command("select")
def session_select(session_id: Optional[str] = typer.Argument(None, help="선택할 세션 ID (생략 시 대화형 선택)")):
    """기존 세션으로 전환"""
    client = _client()
    try:
        sessions = client.list_sessions()
    except Exception as e:
        err_console.print(f"[!] 세션 목록 조회 실패: {e}")
        raise typer.Exit(1)

    if not sessions:
        err_console.print("[!] 서버에 세션이 없습니다. 'agent session new' 로 생성하세요.")
        raise typer.Exit(1)

    # 세션 ID를 직접 넘긴 경우
    if session_id:
        match = next((s for s in sessions if s["session_id"] == session_id), None)
        if not match:
            err_console.print(f"[!] 세션 '{session_id}' 를 찾을 수 없습니다.")
            raise typer.Exit(1)
        _switch_session(match)
        return

    # 대화형 선택
    current_sid = config.get("session_id")
    console.print("\n[bold]세션을 선택하세요[/]\n")
    for i, s in enumerate(sessions):
        is_current = s["session_id"] == current_sid
        expired = s.get("is_expired", False)
        status = "[red]만료[/]" if expired else "[green]활성[/]"
        marker = " [green](현재)[/]" if is_current else ""
        console.print(f"  [cyan]{i + 1}[/].  {s['session_id']}  파일:{s['file_count']}  {status}{marker}")

    console.print()
    raw = Prompt.ask("번호 입력", default="1")
    try:
        idx = int(raw) - 1
        if not (0 <= idx < len(sessions)):
            raise ValueError
    except ValueError:
        err_console.print("[!] 올바른 번호를 입력하세요.")
        raise typer.Exit(1)

    _switch_session(sessions[idx])


def _switch_session(sess: dict):
    config.set_value("session_id", sess["session_id"])
    config.set_value("workspace_path", sess["workspace_path"])
    console.print(Panel(
        f"[bold green]세션 전환 완료[/]\n\n"
        f"ID        : [cyan]{sess['session_id']}[/]\n"
        f"workspace : {sess['workspace_path']}\n"
        f"파일 수   : {sess['file_count']}",
        border_style="green",
    ))


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
def session_delete(
    session_id: Optional[str] = typer.Argument(None, help="삭제할 세션 ID (생략 시 현재 세션)"),
):
    """세션 삭제 (생략 시 현재 세션, ID 지정 시 해당 세션)"""
    client = _client()
    sid = session_id or config.get("session_id")

    if not sid:
        err_console.print("[!] 세션이 없습니다.")
        raise typer.Exit(1)

    confirm = Prompt.ask(f"세션 '{sid}' 를 삭제하시겠습니까?", choices=["y", "n"], default="n")
    if confirm != "y":
        console.print("[dim]취소됨[/]")
        return
    try:
        client.delete_session(sid)
    except Exception as e:
        err_console.print(f"[!] 삭제 실패: {e}")
        raise typer.Exit(1)

    if sid == config.get("session_id"):
        config.set_value("session_id", None)
        config.set_value("workspace_path", None)
    console.print(f"[green]세션 삭제 완료[/]: {sid}")


@session_app.command("delete-all")
def session_delete_all():
    """서버의 전체 세션 삭제"""
    client = _client()

    try:
        sessions = client.list_sessions()
    except Exception as e:
        err_console.print(f"[!] 세션 목록 조회 실패: {e}")
        raise typer.Exit(1)

    if not sessions:
        console.print("[dim]삭제할 세션이 없습니다.[/]")
        return

    console.print(f"[yellow]서버에 {len(sessions)}개 세션이 있습니다.[/]")
    confirm = Prompt.ask("전체 세션을 삭제하시겠습니까?", choices=["y", "n"], default="n")
    if confirm != "y":
        console.print("[dim]취소됨[/]")
        return

    try:
        deleted = client.delete_all_sessions()
    except Exception as e:
        err_console.print(f"[!] 삭제 실패: {e}")
        raise typer.Exit(1)

    config.set_value("session_id", None)
    config.set_value("workspace_path", None)
    console.print(f"[green]전체 세션 삭제 완료[/] — {deleted}개 삭제됨")


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


@files_app.command("local-ls")
def files_local_ls(
    directory: Optional[str] = typer.Argument(None, help="탐색할 로컬 디렉토리 (기본: 현재 디렉토리)"),
    max_depth: int = typer.Option(4, "--depth", help="최대 탐색 깊이"),
):
    """로컬 파일 구조를 트리로 출력 (서버 업로드 없이)"""
    root = Path(directory).resolve() if directory else Path.cwd()
    if not root.exists():
        err_console.print(f"[!] 경로 없음: {root}")
        raise typer.Exit(1)

    ignore = _load_gitignore(root)
    tree = Tree(f":open_file_folder: [bold]{root}[/]")
    count = _fill_local_tree(tree, root, root, ignore, 0, max_depth)
    console.print(tree)
    console.print(f"\n[dim]총 {count}개 파일[/]")


@files_app.command("sync")
def files_sync(
    directory: Optional[str] = typer.Argument(None, help="동기화할 로컬 디렉토리 (기본: 현재 디렉토리)"),
    max_size_kb: int = typer.Option(500, "--max-size", help="파일 최대 크기 (KB)"),
    dry_run: bool = typer.Option(False, "--dry-run", is_flag=True, help="실제 전송 없이 대상 파일만 출력"),
):
    """로컬 디렉토리 전체를 서버 워크스페이스에 동기화

    .gitignore, 바이너리 파일, 대용량 파일은 자동으로 제외됩니다.
    """
    sid = _require_session()
    root = Path(directory).resolve() if directory else Path.cwd()
    if not root.exists():
        err_console.print(f"[!] 경로 없음: {root}")
        raise typer.Exit(1)

    ignore = _load_gitignore(root)
    candidates = _collect_files(root, root, ignore, max_size_kb * 1024)

    if not candidates:
        console.print("[dim]전송할 파일이 없습니다.[/]")
        return

    # 미리보기
    tree = Tree(f":open_file_folder: [bold]{root}[/]")
    for rel, _ in candidates:
        parts = Path(rel).parts
        node = tree
        dirs: dict = {}
        for i, part in enumerate(parts[:-1]):
            key = "/".join(parts[: i + 1])
            if key not in dirs:
                dirs[key] = node.add(f":file_folder: [dim]{part}[/]")
            node = dirs[key]
        node.add(f":page_facing_up: {parts[-1]}")
    console.print(tree)
    console.print(f"\n[dim]{len(candidates)}개 파일 — 최대 {max_size_kb}KB 이하[/]")

    if dry_run:
        console.print("[yellow]--dry-run: 실제 전송 없음[/]")
        return

    confirm = Prompt.ask(f"\n서버에 {len(candidates)}개 파일을 동기화하시겠습니까?", choices=["y", "n"], default="y")
    if confirm != "y":
        console.print("[dim]취소됨[/]")
        return

    files_payload = [{"path": rel, "content": content} for rel, content in candidates]
    client = _client()
    try:
        result = client.upload_files(sid, files_payload)
    except Exception as e:
        err_console.print(f"[!] 동기화 실패: {e}")
        raise typer.Exit(1)

    config.set_value("local_workspace", str(root))
    console.print(f"[green]동기화 완료[/] — {result['uploaded_count']}개 파일 전송 (워크스페이스 총 {result['total_files']}개)")


@files_app.command("pull")
def files_pull(
    remote_path: Optional[str] = typer.Argument(None, help="가져올 서버 파일 경로 (생략 시 전체)"),
    output: Optional[str] = typer.Option(None, "--out", "-o", help="저장할 로컬 경로 (기본: 현재 디렉토리)"),
    overwrite: bool = typer.Option(False, "--overwrite", is_flag=True, help="기존 파일 덮어쓰기"),
):
    """서버 워크스페이스의 파일을 로컬로 가져옵니다.

    특정 파일 하나 또는 워크스페이스 전체를 다운로드합니다.
    """
    sid = _require_session()
    client = _client()
    out_dir = Path(output).resolve() if output else Path.cwd()

    # 단일 파일
    if remote_path:
        try:
            content = client.get_file(sid, remote_path)
        except Exception as e:
            err_console.print(f"[!] 파일 조회 실패: {e}")
            raise typer.Exit(1)

        if content is None:
            err_console.print(f"[!] 파일을 찾을 수 없습니다: {remote_path}")
            raise typer.Exit(1)

        local_path = out_dir / remote_path
        if local_path.exists() and not overwrite:
            confirm = Prompt.ask(f"'{local_path}' 이(가) 이미 있습니다. 덮어쓰시겠습니까?", choices=["y", "n"], default="n")
            if confirm != "y":
                console.print("[dim]취소됨[/]")
                return

        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")
        console.print(f"[green]저장 완료[/] → {local_path}")
        return

    # 전체 파일
    try:
        file_list = client.list_files(sid)
    except Exception as e:
        err_console.print(f"[!] 파일 목록 조회 실패: {e}")
        raise typer.Exit(1)

    if not file_list:
        console.print("[dim]서버에 파일이 없습니다.[/]")
        return

    console.print(_build_file_tree(file_list, label=f"workspace → {out_dir}"))
    console.print(f"\n[dim]{len(file_list)}개 파일[/]")

    confirm = Prompt.ask(f"\n로컬 '{out_dir}' 에 {len(file_list)}개 파일을 저장하시겠습니까?", choices=["y", "n"], default="y")
    if confirm != "y":
        console.print("[dim]취소됨[/]")
        return

    saved, skipped = 0, 0
    for path in file_list:
        try:
            content = client.get_file(sid, path)
        except Exception:
            skipped += 1
            continue

        if content is None:
            skipped += 1
            continue

        local_path = out_dir / path
        if local_path.exists() and not overwrite:
            skipped += 1
            console.print(f"[dim]  건너뜀 (이미 있음): {path}[/]")
            continue

        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(content, encoding="utf-8")
        saved += 1

    console.print(f"\n[green]완료[/] — {saved}개 저장" + (f", {skipped}개 건너뜀" if skipped else ""))


# ── File scan helpers ──────────────────────────────────────────────────────────

_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".exe", ".bin", ".so", ".dylib", ".dll", ".o", ".a",
    ".mp3", ".mp4", ".mov", ".avi", ".mkv",
    ".pyc", ".pyo", ".class",
    ".woff", ".woff2", ".ttf", ".eot",
}

_DEFAULT_IGNORE = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".pytest_cache", ".mypy_cache", "dist", "build", ".next",
    ".DS_Store", "*.egg-info",
}


def _load_gitignore(root: Path) -> List[str]:
    """루트의 .gitignore 패턴을 읽어 반환"""
    patterns: List[str] = []
    gi = root / ".gitignore"
    if gi.exists():
        for line in gi.read_text(errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def _is_ignored(rel: str, name: str, patterns: List[str]) -> bool:
    """이름 기반 단순 gitignore 매칭"""
    import fnmatch
    if name in _DEFAULT_IGNORE:
        return True
    for pat in patterns:
        pat_clean = pat.rstrip("/")
        if fnmatch.fnmatch(name, pat_clean):
            return True
        if fnmatch.fnmatch(rel, pat_clean):
            return True
    return False


def _collect_files(
    root: Path,
    current: Path,
    patterns: List[str],
    max_bytes: int,
) -> List[tuple]:
    """재귀적으로 텍스트 파일 수집 → [(rel_path, content), ...]"""
    results = []
    try:
        entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return results

    for entry in entries:
        rel = str(entry.relative_to(root))
        if _is_ignored(rel, entry.name, patterns):
            continue
        if entry.is_dir():
            results.extend(_collect_files(root, entry, patterns, max_bytes))
        elif entry.is_file():
            if entry.suffix.lower() in _BINARY_EXTENSIONS:
                continue
            if entry.stat().st_size > max_bytes:
                continue
            try:
                content = entry.read_text(encoding="utf-8", errors="strict")
                results.append((rel, content))
            except (UnicodeDecodeError, PermissionError):
                pass  # 바이너리 또는 권한 없음 — 스킵
    return results


def _fill_local_tree(tree: Tree, root: Path, current: Path, patterns: List[str], depth: int, max_depth: int) -> int:
    """Rich Tree에 로컬 파일 구조 채우기, 파일 수 반환"""
    if depth >= max_depth:
        return 0
    count = 0
    try:
        entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return 0
    for entry in entries:
        rel = str(entry.relative_to(root))
        if _is_ignored(rel, entry.name, patterns):
            continue
        if entry.is_dir():
            branch = tree.add(f":file_folder: [dim]{entry.name}/[/]")
            count += _fill_local_tree(branch, root, entry, patterns, depth + 1, max_depth)
        else:
            tree.add(f":page_facing_up: {entry.name}")
            count += 1
    return count


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
        path = msg.get("path", "")
        content = msg.get("content")
        local_ws = config.get("local_workspace")

        if content is not None and local_ws:
            local_path = Path(local_ws) / path
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_text(content, encoding="utf-8")
                console.print(f"[green]  ↺ 로컬 저장[/]: {local_path}")
            except Exception as e:
                console.print(f"[yellow]  ↺ 파일 변경 (로컬 저장 실패: {e})[/]: {path}")
        else:
            console.print(f"[dim]  ↺ 파일 변경: {path}[/]")

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

    elif cmd == "local" and len(parts) > 1 and parts[1] == "ls":
        directory = parts[2] if len(parts) > 2 else "."
        root = Path(directory).resolve()
        ignore = _load_gitignore(root)
        tree = Tree(f":open_file_folder: [bold]{root}[/]")
        count = _fill_local_tree(tree, root, root, ignore, 0, 4)
        console.print(tree)
        console.print(f"[dim]총 {count}개 파일[/]")

    elif cmd == "pull":
        remote = parts[1] if len(parts) > 1 else None
        out_dir = Path.cwd()
        if remote:
            try:
                content = client.get_file(sid, remote)
                if content:
                    local_path = out_dir / remote
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_text(content, encoding="utf-8")
                    console.print(f"[green]저장 완료[/] → {local_path}")
                else:
                    console.print("[red]파일 없음[/]")
            except Exception as e:
                err_console.print(f"[!] {e}")
        else:
            try:
                file_list = client.list_files(sid)
                console.print(f"[dim]{len(file_list)}개 파일 다운로드 중...[/]")
                saved = 0
                for path in file_list:
                    content = client.get_file(sid, path)
                    if content:
                        local_path = out_dir / path
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        local_path.write_text(content, encoding="utf-8")
                        saved += 1
                console.print(f"[green]완료[/] — {saved}개 저장 → {out_dir}")
            except Exception as e:
                err_console.print(f"[!] {e}")

    elif cmd == "sync":
        directory = parts[1] if len(parts) > 1 else "."
        root = Path(directory).resolve()
        ignore = _load_gitignore(root)
        candidates = _collect_files(root, root, ignore, 500 * 1024)
        if not candidates:
            console.print("[dim]전송할 파일 없음[/]")
        else:
            console.print(f"[dim]{len(candidates)}개 파일 동기화 중...[/]")
            payload = [{"path": r, "content": c} for r, c in candidates]
            try:
                result = client.upload_files(sid, payload)
                console.print(f"[green]동기화 완료[/] — {result['uploaded_count']}개 파일")
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
            "[dim]/files[/]             — 서버 워크스페이스 파일 목록\n"
            "[dim]/show <path>[/]       — 서버 파일 내용\n"
            "[dim]/local ls [dir][/]    — 로컬 파일 구조 트리\n"
            "[dim]/sync [dir][/]        — 로컬 → 서버 동기화\n"
            "[dim]/pull [path][/]       — 서버 → 로컬 저장 (생략 시 전체)\n"
            "[dim]/status[/]            — 서버 상태\n"
            "[dim]exit[/]               — 종료"
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
