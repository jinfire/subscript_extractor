import io
import json
import threading
import unittest
from types import SimpleNamespace
from wsgiref.simple_server import make_server
from urllib.request import Request, urlopen

from app import AppError, ThreadedWSGIServer, TranscriptService, choose_track, create_application, parse_video_id


VIDEO = "dQw4w9WgXcQ"


def payload(identifier=VIDEO, language=None):
    return {"video_id": identifier, "url": f"https://www.youtube.com/watch?v={identifier}", "language": language or "ko", "is_generated": True, "languages": [{"code": "ko", "name": "한국어"}], "segments": [{"text": "안녕하세요 <script>alert(1)</script>", "start": 0.0}]}


class UrlTests(unittest.TestCase):
    def test_supported_links(self):
        for url in [VIDEO, f"https://www.youtube.com/watch?v={VIDEO}&t=10", f"https://youtu.be/{VIDEO}?si=abc", f"https://youtube.com/shorts/{VIDEO}", f"https://m.youtube.com/watch?v={VIDEO}", f"youtube.com/live/{VIDEO}", f"https://www.youtube.com/embed/{VIDEO}"]:
            with self.subTest(url=url):
                self.assertEqual(parse_video_id(url), VIDEO)

    def test_untrusted_and_invalid_links(self):
        for url in ["", "https://youtube.com.evil.test/watch?v=" + VIDEO, "https://evil.test/" + VIDEO, "file://youtube.com/watch?v=" + VIDEO, "https://youtube.com@evil.test/watch?v=" + VIDEO, "https://user@youtube.com/watch?v=" + VIDEO, "https://youtu.be/short", "https://youtube.com/playlist?list=abc", "https://[broken", "https://youtu.be/" + VIDEO + "/extra"]:
            with self.subTest(url=url), self.assertRaises(AppError) as caught:
                parse_video_id(url)
            self.assertEqual(caught.exception.status, 400)


class TrackTests(unittest.TestCase):
    def track(self, code, generated):
        return SimpleNamespace(language_code=code, is_generated=generated)

    def test_korean_auto_before_english_manual(self):
        korean = self.track("ko", True)
        self.assertIs(choose_track([self.track("en", False), korean]), korean)

    def test_manual_before_auto_in_same_language(self):
        manual = self.track("ko", False)
        self.assertIs(choose_track([self.track("ko", True), manual]), manual)

    def test_english_fallback_and_explicit_language(self):
        english, japanese = self.track("en", True), self.track("ja", False)
        self.assertIs(choose_track([japanese, english]), english)
        self.assertIs(choose_track([japanese, english], "ja"), japanese)

    def test_other_language_fallback(self):
        japanese = self.track("ja", False)
        self.assertIs(choose_track([japanese]), japanese)

    def test_missing_language_and_no_tracks(self):
        for tracks, language in [([], None), ([self.track("ko", True)], "en")]:
            with self.subTest(language=language), self.assertRaises(AppError):
                choose_track(tracks, language)


class ServiceTests(unittest.TestCase):
    def test_cache_key_and_expiry(self):
        calls, clock = [], [0]
        def provider(identifier, language):
            calls.append((identifier, language))
            return payload(identifier, language)
        service = TranscriptService(provider, lambda: clock[0])
        self.assertEqual(service.get(VIDEO, None, "local"), service.get("https://youtu.be/" + VIDEO, None, "local"))
        self.assertEqual(len(calls), 1)
        service.get(VIDEO, "ko", "local")
        self.assertEqual(len(calls), 2)
        clock[0] = 601
        service.get(VIDEO, None, "local")
        self.assertEqual(len(calls), 3)

    def test_rate_limit_and_expiry(self):
        clock = [0]
        service = TranscriptService(payload, lambda: clock[0])
        for _ in range(12):
            service.get(VIDEO, None, "client")
        with self.assertRaises(AppError) as caught:
            service.get(VIDEO, None, "client")
        self.assertEqual(caught.exception.status, 429)
        service.get(VIDEO, None, "other-client")
        clock[0] = 61
        service.get(VIDEO, None, "client")

    def test_failure_not_cached_and_slot_released(self):
        calls = []
        def provider(*args):
            calls.append(args)
            raise AppError(503, "youtube_blocked", "차단")
        service = TranscriptService(provider)
        for _ in range(5):
            with self.assertRaises(AppError) as caught:
                service.get(VIDEO, None, "client")
            self.assertEqual(caught.exception.code, "youtube_blocked")
        self.assertEqual(len(calls), 5)

    def test_concurrent_limit(self):
        entered = threading.Barrier(5)
        release = threading.Event()
        def provider(*args):
            entered.wait(timeout=5)
            release.wait(timeout=5)
            return payload()
        service = TranscriptService(provider)
        threads = [threading.Thread(target=service.get, args=(VIDEO, None, str(i))) for i in range(4)]
        try:
            for thread in threads:
                thread.start()
            entered.wait(timeout=5)
            with self.assertRaises(AppError) as caught:
                service.get(VIDEO, "ko", "fifth")
            self.assertEqual(caught.exception.code, "server_busy")
        finally:
            release.set()
            for thread in threads:
                thread.join(timeout=5)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.application = create_application(TranscriptService(payload))

    def request(self, path="/api/transcript", method="POST", raw=None, content_type="application/json", length=None):
        raw = raw if raw is not None else json.dumps({"url": VIDEO}).encode()
        captured = {}
        def start(status, headers):
            captured.update(status=int(status.split()[0]), headers=dict(headers))
        environ = {"PATH_INFO": path, "REQUEST_METHOD": method, "CONTENT_TYPE": content_type, "CONTENT_LENGTH": str(len(raw)) if length is None else length, "wsgi.input": io.BytesIO(raw), "REMOTE_ADDR": "127.0.0.1"}
        captured["body"] = b"".join(self.application(environ, start))
        return captured

    def test_success(self):
        response = self.request()
        self.assertEqual(response["status"], 200)
        self.assertEqual(json.loads(response["body"])["segments"][0]["start"], 0)
        self.assertEqual(response["headers"]["Cache-Control"], "no-store")

    def test_body_validation(self):
        for raw in [b"{", b"[]", b"null", b'{"url":1}', b'{"url":""}', json.dumps({"url": VIDEO, "language": {}}).encode()]:
            with self.subTest(raw=raw):
                self.assertEqual(self.request(raw=raw)["status"], 400)

    def test_large_request_rejected_before_read(self):
        self.assertEqual(self.request(length="8193")["status"], 413)

    def test_invalid_length(self):
        self.assertEqual(self.request(length="invalid")["status"], 400)

    def test_content_type_and_method(self):
        self.assertEqual(self.request(content_type="text/plain")["status"], 415)
        self.assertEqual(self.request(method="GET")["status"], 405)

    def test_static_allowlist(self):
        for path, content_type in [("/", "text/html"), ("/static/app.js", "text/javascript"), ("/static/style.css", "text/css"), ("/static/text.mjs", "text/javascript"), ("/favicon.svg", "image/svg+xml")]:
            with self.subTest(path=path):
                response = self.request(path, "GET")
                self.assertEqual(response["status"], 200)
                self.assertIn(content_type, response["headers"]["Content-Type"])
        self.assertEqual(self.request("/static/../app.py", "GET")["status"], 404)
        self.assertEqual(self.request("/.env", "GET")["status"], 404)

    def test_head_has_headers_but_no_body(self):
        response = self.request("/", "HEAD")
        self.assertEqual(response["body"], b"")
        self.assertGreater(int(response["headers"]["Content-Length"]), 0)

    def test_provider_error_and_retry_header(self):
        def blocked(*args):
            raise AppError(503, "youtube_blocked", "유튜브가 요청을 차단했습니다.")
        self.application = create_application(TranscriptService(blocked))
        response = self.request()
        self.assertEqual(response["status"], 503)
        self.assertEqual(json.loads(response["body"])["error"], "youtube_blocked")
        self.application = create_application(TranscriptService(payload))
        for _ in range(12):
            self.request()
        response = self.request()
        self.assertEqual(response["status"], 429)
        self.assertEqual(response["headers"]["Retry-After"], "60")

    def test_live_http_server(self):
        server = make_server("127.0.0.1", 0, self.application, server_class=ThreadedWSGIServer)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/health", timeout=5) as response:
                self.assertEqual(json.load(response), {"status": "ok"})
            req = Request(base + "/api/transcript", data=json.dumps({"url": VIDEO}).encode(), headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=5) as response:
                self.assertEqual(json.load(response)["video_id"], VIDEO)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
