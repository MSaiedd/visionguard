"""Enforce a bounded request body before multipart parsing, including chunked uploads."""

from starlette.responses import JSONResponse


class BodyBudget:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        limit = self.settings.max_upload_bytes + 65536
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        try:
            too_large = declared is not None and int(declared) > limit
        except ValueError:
            await JSONResponse({"detail": "Invalid content length"}, 400)(scope, receive, send)
            return
        if too_large:
            await JSONResponse({"detail": "Request body exceeds upload budget"}, 413)(
                scope, receive, send
            )
            return
        blocks = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            block = message.get("body", b"")
            total += len(block)
            if total > limit:
                await JSONResponse({"detail": "Request body exceeds upload budget"}, 413)(
                    scope, receive, send
                )
                return
            blocks.append(block)
            if not message.get("more_body"):
                break
        body = b"".join(blocks)
        del blocks
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
