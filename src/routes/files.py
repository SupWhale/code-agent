"""
Files API Routes

공유 워크스페이스에 대한 파일 업로드/목록/읽기/다운로드/삭제 엔드포인트.
"""

import logging
from datetime import datetime
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from prometheus_client import Counter

from ..auth import AuthenticatedKey, require_admin_key, require_api_key
from ..utils.responses import UnicodeJSONResponse

logger = logging.getLogger(__name__)

file_operations_total = Counter('file_operations_total', 'Total file operations', ['operation', 'status'])


def validate_path(path: str, workspace_path: Path) -> Path:
    """경로 검증 및 정규화 (경로 탐색 공격 방지)"""
    try:
        full_path = (workspace_path / path.lstrip("/")).resolve()
        if not full_path.is_relative_to(workspace_path):
            raise ValueError("경로가 워크스페이스 밖을 벗어났습니다")
        return full_path
    except Exception as e:
        logger.error(f"경로 검증 실패: {path}, 에러: {e}")
        raise HTTPException(status_code=400, detail=f"잘못된 경로입니다: {str(e)}")


def init_files_router(workspace_path: Path, max_file_size: int) -> APIRouter:
    """
    Files 라우터 초기화

    Args:
        workspace_path: 파일 작업 루트 디렉토리
        max_file_size: 업로드 허용 최대 파일 크기(바이트)

    Returns:
        설정된 APIRouter
    """
    router = APIRouter(prefix="/api/v1/files", tags=["files"])

    @router.post("/upload")
    async def upload_file(
        file: UploadFile = File(...),
        path: str = Query(default="/"),
        identity: AuthenticatedKey = Depends(require_admin_key),
    ):
        """파일 업로드 (공유 워크스페이스 전체에 쓰기 — admin 키 필요)"""
        try:
            # 경로 검증
            upload_dir = validate_path(path, workspace_path)
            upload_dir.mkdir(parents=True, exist_ok=True)

            file_path = upload_dir / file.filename

            # 파일 크기 확인
            content = await file.read()
            if len(content) > max_file_size:
                file_operations_total.labels(operation="upload", status="failed").inc()
                raise HTTPException(status_code=413, detail=f"파일 크기가 {max_file_size / 1024 / 1024}MB를 초과합니다")

            # 파일 저장
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)

            file_operations_total.labels(operation="upload", status="success").inc()

            return UnicodeJSONResponse({
                "filename": file.filename,
                "path": str(file_path.relative_to(workspace_path)),
                "size": len(content),
                "timestamp": datetime.now().isoformat()
            })

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"파일 업로드 실패: {e}")
            file_operations_total.labels(operation="upload", status="failed").inc()
            raise HTTPException(status_code=500, detail=f"파일 업로드 실패: {str(e)}")

    @router.get("/list")
    async def list_files(path: str = Query(default="/"), identity: AuthenticatedKey = Depends(require_api_key)):
        """파일 목록 조회"""
        try:
            dir_path = validate_path(path, workspace_path)

            if not dir_path.exists():
                raise HTTPException(status_code=404, detail="디렉토리를 찾을 수 없습니다")

            if not dir_path.is_dir():
                raise HTTPException(status_code=400, detail="디렉토리가 아닙니다")

            files = []
            for item in dir_path.iterdir():
                files.append({
                    "name": item.name,
                    "path": str(item.relative_to(workspace_path)),
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                })

            file_operations_total.labels(operation="list", status="success").inc()

            return UnicodeJSONResponse({
                "path": path,
                "files": sorted(files, key=lambda x: (x["type"] != "directory", x["name"]))
            })

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"파일 목록 조회 실패: {e}")
            file_operations_total.labels(operation="list", status="failed").inc()
            raise HTTPException(status_code=500, detail=f"파일 목록 조회 실패: {str(e)}")

    @router.get("/read")
    async def read_file(path: str = Query(..., description="읽을 파일 경로"), identity: AuthenticatedKey = Depends(require_api_key)):
        """파일 읽기"""
        try:
            file_path = validate_path(path, workspace_path)

            if not file_path.exists():
                raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

            if not file_path.is_file():
                raise HTTPException(status_code=400, detail="파일이 아닙니다")

            # 파일 읽기 (텍스트 파일로 가정)
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    content = await f.read()

                file_operations_total.labels(operation="read", status="success").inc()

                return UnicodeJSONResponse({
                    "path": path,
                    "content": content,
                    "size": file_path.stat().st_size,
                    "timestamp": datetime.now().isoformat()
                })
            except UnicodeDecodeError:
                # 바이너리 파일인 경우
                raise HTTPException(status_code=400, detail="바이너리 파일은 읽을 수 없습니다. /download를 사용하세요.")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"파일 읽기 실패: {e}")
            file_operations_total.labels(operation="read", status="failed").inc()
            raise HTTPException(status_code=500, detail=f"파일 읽기 실패: {str(e)}")

    @router.get("/download")
    async def download_file(path: str = Query(..., description="다운로드할 파일 경로"), identity: AuthenticatedKey = Depends(require_api_key)):
        """파일 다운로드"""
        try:
            file_path = validate_path(path, workspace_path)

            if not file_path.exists():
                raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

            if not file_path.is_file():
                raise HTTPException(status_code=400, detail="파일이 아닙니다")

            file_operations_total.labels(operation="download", status="success").inc()

            return FileResponse(
                path=file_path,
                filename=file_path.name,
                media_type="application/octet-stream"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"파일 다운로드 실패: {e}")
            file_operations_total.labels(operation="download", status="failed").inc()
            raise HTTPException(status_code=500, detail=f"파일 다운로드 실패: {str(e)}")

    @router.delete("/delete")
    async def delete_file(
        path: str = Query(..., description="삭제할 파일 경로"),
        identity: AuthenticatedKey = Depends(require_admin_key),
    ):
        """파일 삭제 (공유 워크스페이스 전체에서 삭제 가능 — admin 키 필요)"""
        try:
            file_path = validate_path(path, workspace_path)

            if not file_path.exists():
                raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

            if file_path.is_dir():
                # 디렉토리 삭제 (재귀적)
                import shutil
                shutil.rmtree(file_path)
            else:
                # 파일 삭제
                file_path.unlink()

            file_operations_total.labels(operation="delete", status="success").inc()

            return UnicodeJSONResponse({
                "path": path,
                "deleted": True,
                "timestamp": datetime.now().isoformat()
            })

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"파일 삭제 실패: {e}")
            file_operations_total.labels(operation="delete", status="failed").inc()
            raise HTTPException(status_code=500, detail=f"파일 삭제 실패: {str(e)}")

    return router
