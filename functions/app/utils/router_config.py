from fastapi import APIRouter


def create_router(*, prefix: str, tags: list[str]) -> APIRouter:
    return APIRouter(prefix=prefix, tags=tags)