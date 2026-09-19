from fastapi import Request, Response


async def health(request: Request, response: Response):
    return {"status": "ok"}


async def ping(request: Request, response: Response):
    return Response("pong", media_type="text/plain")
