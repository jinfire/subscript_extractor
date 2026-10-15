"""A small WSGI application. Run locally with `python app.py`."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import WSGIServer, make_server

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger(__name__)
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def parse_video_id(value: str) -> str:
    value = value.strip()
    if ID_PATTERN.fullmatch(value):
        return value
    try:
        parsed = urlparse(value if "://" in value else "https://" + value)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError
        host = (parsed.hostname or "").lower()
        parts = parsed.path.strip("/").split("/")
        result = ""
        if host in {"youtu.be", "www.youtu.be"} and len(parts) == 1:
            result = parts[0]
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                result = parse_qs(parsed.query).get("v", [""])[0]
            elif len(parts) == 2 and parts[0] in {"shorts", "embed", "live"}:
                result = parts[1]
        if ID_PATTERN.fullmatch(result):
            return result
    except ValueError:
        pass
    raise AppError(400, "invalid_url", "올바른 유튜브 영상 링크를 입력해 주세요.")


def choose_track(tracks, language=None):
    if not tracks:
        raise AppError(404, "no_captions", "사용 가능한 자막이 없습니다.")
    for code in ([language] if language else ["ko", "en"]):
        candidates = [track for track in tracks if track.language_code == code]
        if candidates:
            return min(candidates, key=lambda track: track.is_generated)
    if language:
        raise AppError(404, "language_unavailable", "선택한 언어의 자막이 없습니다.")
    return min(tracks, key=lambda track: track.is_generated)


def fetch_youtube(identifier, language):
    # Lazy import lets the UI and health endpoint run before dependencies are installed.
    try:
        from requests import Session
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as error:
        raise AppError(503, "dependency_missing", "서버의 자막 추출 모듈이 설치되지 않았습니다. 관리자에게 문의해 주세요.") from error

    class TimeoutSession(Session):
        def request(self, *args, **kwargs):
            kwargs.setdefault("timeout", (5, 20))
            return super().request(*args, **kwargs)

    try:
        # A requests.Session / YouTubeTranscriptApi instance must not be shared by threads.
        with TimeoutSession() as session:
            tracks = list(YouTubeTranscriptApi(http_client=session).list(identifier))
            selected = choose_track(tracks, language)
            segments = []
            for snippet in selected.fetch():
                text = re.sub(r"\s+", " ", snippet.text).strip()
                start = float(snippet.start)
                if text and math.isfinite(start):
                    segments.append({"text": text, "start": max(0, start)})
            if not segments:
                raise AppError(404, "empty_captions", "자막에 텍스트가 없습니다.")
            languages = {}
            for track in tracks:
                languages.setdefault(track.language_code, {"code": track.language_code, "name": track.language})
            return {
                "video_id": identifier,
                "url": f"https://www.youtube.com/watch?v={identifier}",
                "language": selected.language_code,
                "is_generated": selected.is_generated,
                "languages": list(languages.values()),
                "segments": segments,
            }
    except AppError:
        raise
    except Exception as error:
        # Use class ancestry so subclasses (e.g. IpBlocked) are classified correctly.
        names = {cls.__name__ for cls in type(error).__mro__}
        if names & {"RequestBlocked", "IpBlocked", "PoTokenRequired"}:
            raise AppError(503, "youtube_blocked", "유튜브가 서버의 자막 요청을 차단했습니다. 잠시 후 다시 시도해 주세요.") from error
        if names & {"TranscriptsDisabled", "NoTranscriptFound"}:
            raise AppError(404, "no_captions", "사용 가능한 자막이 없습니다. 자동생성 자막도 없는 영상은 지원하지 않습니다.") from error
        if names & {"VideoUnavailable", "VideoUnplayable", "AgeRestricted"}:
            raise AppError(422, "video_unavailable", "비공개·삭제·연령 제한 등의 이유로 영상에 접근할 수 없습니다.") from error
        if names & {"Timeout", "ConnectTimeout", "ReadTimeout"}:
            raise AppError(504, "upstream_timeout", "유튜브 응답이 늦어지고 있습니다. 잠시 후 다시 시도해 주세요.") from error
        LOG.warning("YouTube extraction failed (%s)", type(error).__name__)
        raise AppError(502, "upstream_error", "자막을 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.") from error


class TranscriptService:
    def __init__(self, provider=fetch_youtube, clock=time.monotonic):
        self.provider, self.clock = provider, clock
        self.cache = OrderedDict()
        self.requests = OrderedDict()
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(4)

    def get(self, value, language, client):
        identifier = parse_video_id(value)
        key = (identifier, language)
        with self.lock:
            now = self.clock()
            recent = self.requests.setdefault(client, deque())
            while recent and now - recent[0] >= 60:
                recent.popleft()
            if len(recent) >= 12:
                raise AppError(429, "rate_limited", "요청이 많습니다. 1분 후 다시 시도해 주세요.")
            recent.append(now)
            self.requests.move_to_end(client)
            while len(self.requests) > 2048:
                self.requests.popitem(last=False)
            entry = self.cache.get(key)
            if entry and now - entry[0] < 600:
                self.cache.move_to_end(key)
                return entry[1]
        if not self.slots.acquire(blocking=False):
            raise AppError(429, "server_busy", "서버가 처리 중입니다. 잠시 후 다시 시도해 주세요.")
        try:
            result = self.provider(identifier, language)
            encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
            if len(encoded) > 5_000_000:
                raise AppError(413, "transcript_too_large", "대본이 너무 커서 처리할 수 없습니다.")
            with self.lock:
                self.cache[key] = (self.clock(), encoded)
                self.cache.move_to_end(key)
                while len(self.cache) > 16:
                    self.cache.popitem(last=False)
            return encoded
        finally:
            self.slots.release()


STATUS = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed", 413: "Content Too Large", 415: "Unsupported Media Type", 422: "Unprocessable Content", 429: "Too Many Requests", 500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout"}
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/static/style.css": ("style.css", "text/css; charset=utf-8"), "/static/app.js": ("app.js", "text/javascript; charset=utf-8"), "/static/text.mjs": ("text.mjs", "text/javascript; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}


def create_application(service=None):
    service = service or TranscriptService()

    def application(environ, start_response):
        path, method = environ.get("PATH_INFO", "/"), environ.get("REQUEST_METHOD", "GET")
        headers = [("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"), ("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"), ("Cache-Control", "no-store")]
        status, content_type = 200, "application/json; charset=utf-8"
        try:
            if path in STATIC:
                if method not in {"GET", "HEAD"}:
                    raise AppError(405, "method_not_allowed", "지원하지 않는 요청 방식입니다.")
                filename, content_type = STATIC[path]
                body = (ROOT / "static" / filename).read_bytes()
            elif path == "/health":
                if method not in {"GET", "HEAD"}:
                    raise AppError(405, "method_not_allowed", "지원하지 않는 요청 방식입니다.")
                body = b'{"status":"ok"}'
            elif path == "/api/transcript":
                if method != "POST":
                    raise AppError(405, "method_not_allowed", "POST 요청이 필요합니다.")
                if environ.get("CONTENT_TYPE", "").split(";")[0].strip().lower() != "application/json":
                    raise AppError(415, "invalid_content_type", "JSON 요청이 필요합니다.")
                try:
                    length = int(environ.get("CONTENT_LENGTH") or "0")
                except ValueError:
                    raise AppError(400, "invalid_body", "요청 크기가 올바르지 않습니다.")
                if not 0 < length <= 8192:
                    raise AppError(413, "body_too_large", "입력한 링크를 확인해 주세요.")
                try:
                    request = json.loads(environ["wsgi.input"].read(length))
                except (ValueError, UnicodeError):
                    raise AppError(400, "invalid_body", "JSON 형식이 올바르지 않습니다.")
                if not isinstance(request, dict) or not isinstance(request.get("url"), str) or not 1 <= len(request["url"]) <= 2048:
                    raise AppError(400, "invalid_body", "유튜브 링크를 입력해 주세요.")
                language = request.get("language")
                if language is not None and (not isinstance(language, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", language)):
                    raise AppError(400, "invalid_language", "자막 언어를 확인해 주세요.")
                # Do not trust arbitrary client-supplied X-Forwarded-For headers.
                body = service.get(request["url"], language, environ.get("REMOTE_ADDR", "unknown"))
            else:
                raise AppError(404, "not_found", "페이지를 찾지 못했습니다.")
        except AppError as error:
            status = error.status
            if status == 429:
                headers.append(("Retry-After", "60"))
            body = json.dumps({"error": error.code, "message": error.message}, ensure_ascii=False).encode("utf-8")
        except Exception:
            LOG.exception("Application error")
            status, body = 500, b'{"error":"internal_error","message":"Server error"}'
        headers += [("Content-Type", content_type), ("Content-Length", str(len(body)))]
        start_response(f"{status} {STATUS[status]}", headers)
        return [b"" if method == "HEAD" else body]

    return application


application = create_application()


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"Open http://{host}:{port}", flush=True)
    # Development only. Public deployments use waitress behind the host's HTTPS proxy.
    with make_server(host, port, application, server_class=ThreadedWSGIServer) as server:
        server.serve_forever()
