import contextlib
import http.client
import io
import json
import os
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "examples"))

from fakes import FakeServer, TOKENS  # noqa: E402
from make_demo_repo import build  # noqa: E402

from git_ofrenda import cli, gitscan, llm, poet, render, server  # noqa: E402
from git_ofrenda.cache import SeanceStore  # noqa: E402


class AppCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.repo = build(os.path.join(cls.tmp, "demo"))
        os.environ["OFRENDA_CACHE"] = os.path.join(cls.tmp, "cache")
        cls.ghosts = gitscan.scan(cls.repo, limit=3)
        for g in cls.ghosts:
            poet.compose(g, llm.NoBackend())

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                cli.main(list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()


class RenderTests(AppCase):
    def test_html_escapes_everything(self):
        import dataclasses
        g = dataclasses.replace(self.ghosts[0], path='<script>alert(1)</script>"x.py',
                                source="x = '<img onerror=1>'", cause="</title><b>", killer="<i>k</i>",
                                last_words="<u>hi</u>", calavera="<s>a</s>\nb")
        page = render.html_page("<repo>", [g], interactive=True, history={"p": [{"role": "user", "content": "</script><script>x()"}]})
        for bad in ("<script>alert(1)", "<img onerror", "</title><b>", "<i>k</i>", "<u>hi", "<s>a"):
            self.assertNotIn(bad, page)
        self.assertNotIn("</script><script>x()", page)  # history cannot break out of its JSON block

    def test_static_page_has_no_chat_and_states_template_voice(self):
        page = render.html_page("demo", self.ghosts)
        self.assertNotIn("summon", page.split("</style>")[1])
        self.assertIn("no model was used", page)
        self.assertIn("verse: template", page)

    def test_spanish_page(self):
        page = render.html_page("demo", self.ghosts, "es")
        self.assertIn("Ofrenda para demo", page)
        self.assertIn('lang="es"', page)
        self.assertIn("no se usó ningún modelo", page)
        self.assertNotIn("no model was used", page)

    def test_markdown_and_json(self):
        md = render.markdown("demo", self.ghosts)
        self.assertIn("# Ofrenda for demo", md)
        self.assertIn(f"## `{self.ghosts[0].path}`", md)
        data = json.loads(render.json_dump("demo", self.ghosts))
        self.assertEqual(len(data["ghosts"]), 3)
        self.assertNotIn("final_contents", data["ghosts"][0])
        self.assertIn("final_contents", json.loads(render.json_dump("demo", self.ghosts, True))["ghosts"][0])


class ServerTests(AppCase):
    def start(self, backend):
        store = SeanceStore(os.path.join(self.tmp, f"seance-{self._testMethodName}.json"))
        srv = server.make_server(self.ghosts, "demo", backend, store, "en", port=0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return srv, store

    def req(self, srv, method, path, body=None, headers=None, host=None):
        port = srv.server_address[1]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        h = dict(headers or {})
        h["Host"] = host or f"127.0.0.1:{port}"
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        return r.status, r.read().decode()

    def chat(self, srv, path, message):
        return self.req(srv, "POST", "/api/chat", {"path": path, "message": message}, {"X-Ofrenda": "1"})

    def events(self, text):
        return [json.loads(l) for l in text.splitlines() if l.strip()]

    def test_page_and_health(self):
        srv, _ = self.start(llm.NoBackend())
        status, body = self.req(srv, "GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Hold a séance", body)
        self.assertEqual(json.loads(self.req(srv, "GET", "/healthz")[1])["ghosts"], 3)
        self.assertEqual(self.req(srv, "GET", "/nope")[0], 404)

    def test_rejects_foreign_host_and_missing_header(self):
        srv, _ = self.start(llm.NoBackend())
        self.assertEqual(self.req(srv, "GET", "/", host="evil.example.com")[0], 403)  # DNS rebinding
        self.assertEqual(self.req(srv, "POST", "/api/chat", {"path": self.ghosts[0].path, "message": "hi"})[0], 403)  # CSRF
        self.assertEqual(self.req(srv, "POST", "/api/chat", {"path": self.ghosts[0].path, "message": "hi"},
                                  {"X-Ofrenda": "1"}, host="evil.example.com")[0], 403)

    def test_validation(self):
        srv, _ = self.start(llm.NoBackend())
        p = self.ghosts[0].path
        self.assertEqual(self.chat(srv, "unknown.py", "hi")[0], 400)
        self.assertEqual(self.chat(srv, p, "")[0], 400)
        self.assertEqual(self.chat(srv, p, "x" * 501)[0], 400)

    def test_streams_model_tokens_and_persists_history(self):
        with FakeServer() as fake:
            srv, store = self.start(llm.OllamaBackend(fake.url, "gemma3"))
            p = self.ghosts[0].path
            status, text = self.chat(srv, p, "why did you die?")
            ev = self.events(text)
            self.assertEqual(status, 200)
            self.assertEqual([e["token"] for e in ev if "token" in e], TOKENS)
            self.assertEqual(ev[-1], {"done": True, "voice": "model"})
            self.assertEqual(store.get(p)[-1]["content"], "".join(TOKENS))
            # second turn carries history + the ghost's own facts to the model
            self.chat(srv, p, "and then?")
            msgs = [b for path, b in fake.requests if path == "/api/chat"][-1]["messages"]
            self.assertEqual(msgs[0]["role"], "system")
            self.assertIn(self.ghosts[0].cause, msgs[0]["content"])
            self.assertEqual([m["role"] for m in msgs[1:]], ["user", "assistant", "user"])
            # history is embedded in the next page load
            self.assertIn("why did you die?", self.req(srv, "GET", "/")[1])

    def test_falls_back_when_model_down(self):
        srv, store = self.start(llm.OllamaBackend("http://127.0.0.1:1", "gemma3"))
        p = self.ghosts[0].path
        ev = self.events(self.chat(srv, p, "who wrote you?")[1])
        self.assertEqual(ev[-1]["voice"], "template")
        self.assertIn("written by", ev[0]["token"])
        self.assertEqual(len(store.get(p)), 2)

    def test_reset(self):
        srv, store = self.start(llm.NoBackend())
        p = self.ghosts[0].path
        self.chat(srv, p, "when were you born")
        self.assertEqual(len(store.get(p)), 2)
        self.assertEqual(self.req(srv, "POST", "/api/reset", {"path": p}, {"X-Ofrenda": "1"})[0], 200)
        self.assertEqual(store.get(p), [])


class CLITests(AppCase):
    def test_default_command_is_build_and_writes_html(self):
        out = os.path.join(self.tmp, "o.html")
        code, _, err = self.run_cli(self.repo, "--backend", "none", "-n", "2", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("ofrenda lit", err)
        self.assertIn("Ofrenda for demo", open(out, encoding="utf-8").read())

    def test_formats_and_stdout(self):
        code, out, _ = self.run_cli("build", self.repo, "--backend", "none", "-o", "-", "--format", "json", "-n", "2")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["ghosts"]), 2)
        md = os.path.join(self.tmp, "o.md")
        self.run_cli("build", self.repo, "--backend", "none", "-o", md)
        self.assertTrue(open(md, encoding="utf-8").read().startswith("# Ofrenda"))

    def test_build_with_model_uses_cache(self):
        out = os.path.join(self.tmp, "m.html")
        with FakeServer() as fake:
            args = ("build", self.repo, "--host", fake.url, "-n", "2", "-o", out)
            code, _, err = self.run_cli(*args)
            self.assertEqual(code, 0)
            self.assertIn("using ollama model", err)
            calls = sum(1 for p, _ in fake.requests if p == "/api/generate")
            self.assertEqual(calls, 2)
            self.run_cli(*args)  # all cached now
            self.assertEqual(sum(1 for p, _ in fake.requests if p == "/api/generate"), 2)
        page = open(out, encoding="utf-8").read()
        self.assertIn("written by gemma3", page)

    def test_unreachable_model_warns_and_still_builds(self):
        out = os.path.join(self.tmp, "w.html")
        code, _, err = self.run_cli("build", self.repo, "--host", "http://127.0.0.1:1", "-n", "1", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("warning", err)
        self.assertIn("no model was used", open(out, encoding="utf-8").read())

    def test_scan_and_errors(self):
        code, out, _ = self.run_cli("scan", self.repo)
        self.assertEqual(code, 0)
        self.assertIn("legacy/ftp_uploader.py", out)
        code, out, _ = self.run_cli("scan", self.repo, "--json", "--exclude", "*.py")
        self.assertTrue(all(not g["path"].endswith(".py") for g in json.loads(out)))
        code, _, err = self.run_cli("scan", tempfile.mkdtemp())
        self.assertEqual(code, 1)
        self.assertIn("not a git repository", err)
        code, _, err = self.run_cli("scan", self.repo, "--include", "nothing/*")
        self.assertEqual(code, 2)

    def test_exhume_restores_exact_bytes(self):
        dest = os.path.join(self.tmp, "grave")
        code, out, _ = self.run_cli("exhume", self.repo, dest)
        self.assertEqual(code, 0)
        self.assertIn("6 file(s) restored", out)
        with open(os.path.join(dest, "legacy", "ftp_uploader.py"), encoding="utf-8") as f:
            self.assertIn("def upload_report", f.read())

    def test_doctor(self):
        with FakeServer() as fake:
            code, out, _ = self.run_cli("doctor", "--host", fake.url)
            self.assertEqual(code, 0)
            self.assertIn("has model 'gemma3'", out)
        code, out, _ = self.run_cli("doctor", "--host", "http://127.0.0.1:1")
        self.assertEqual(code, 1)
        self.assertIn("--backend none", out)


if __name__ == "__main__":
    unittest.main()
