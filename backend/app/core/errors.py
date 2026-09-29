"""Uniform error envelope: {"error": {"code", "message", "details"}}."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFound(AppError):
    def __init__(self, what: str, ident: object) -> None:
        super().__init__("NOT_FOUND", f"{what} {ident} not found", 404, {"id": str(ident)})


class Forbidden(AppError):
    def __init__(self, message: str = "You do not have access to this resource") -> None:
        super().__init__("FORBIDDEN", message, 403)


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic's raw errors can carry exception objects (not JSON): keep the useful parts.
        fields = [{"loc": [str(p) for p in e.get("loc", [])], "msg": str(e.get("msg", "")), "type": e.get("type")}
                  for e in exc.errors()]
        message = fields[0]["msg"].removeprefix("Value error, ") if len(fields) == 1 else "Some fields are invalid"
        return JSONResponse(_body("VALIDATION_ERROR", message, {"fields": fields}), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)
