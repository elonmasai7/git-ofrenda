import dataclasses
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "examples"))

from fakes import FakeServer, GOOD_REPLY, TOKENS  # noqa: E402
from make_demo_repo import build  # noqa: E402

from git_ofrenda import facts, gitscan, llm, poet, prompts  # noqa: E402
from git_ofrenda.cache import SeanceStore, VerseCache  # noqa: E402


class RepoCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.repo = build(os.path.join(cls.tmp, "demo"))
        cls.ghosts = gitscan.scan(cls.repo)

    def ghost(self, path):
        return next(g for g in self.ghosts if g.path == path)


class ScanTests(RepoCase):
    def test_finds_exactly_the_dead_text_files(self):
        self.assertEqual({g.path for g in self.ghosts}, {
            "legacy/ftp_uploader.py", "src/jquery_shim.js", "src/captcha_v1.py",
            "scripts/deploy_to_heroku.sh", "docs/roadmap_2020.md", "lib/logger.js"})

    def test_renamed_survivor_is_not_a_ghost(self):
        self.assertNotIn("src/util.py", {g.path for g in self.ghosts})
        self.assertNotIn("src/helpers.py", {g.path for g in self.ghosts})

    def test_binary_is_skipped(self):
        self.assertNotIn("assets/logo.bin", {g.path for g in self.ghosts})

    def test_lifespan_follows_renames(self):
        g = self.ghost("lib/logger.js")
        self.assertEqual(g.born, "2018-05-02")  # born as old_logger.js
        self.assertEqual(g.died, "2024-09-30")
        self.assertGreater(g.days, 2300)

    def test_profile_details(self):
        g = self.ghost("legacy/ftp_uploader.py")
        self.assertEqual((g.born, g.killer, g.commits), ("2019-03-04", "Marta", 7))
        self.assertEqual(g.authors, ["Ana", "Marta"])
        self.assertIn("upload_report", g.source)

    def test_sorted_by_love(self):
        scores = [g.score for g in self.ghosts]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_filters(self):
        self.assertEqual([g.path for g in gitscan.scan(self.repo, include=["*.py"], exclude=["src/*"])], ["legacy/ftp_uploader.py"])
        self.assertEqual(len(gitscan.scan(self.repo, limit=2)), 2)
        self.assertEqual(gitscan.scan(self.repo, since="2024-01-01").__len__(), 2)

    def test_not_a_repo(self):
        with self.assertRaises(gitscan.GitError):
            gitscan.scan(tempfile.mkdtemp())

    def test_read_blob_is_byte_exact(self):
        g = self.ghost("legacy/ftp_uploader.py")
        self.assertEqual(gitscan.read_blob(self.repo, g.commit, g.path), g.source.encode())

    def test_prerank_path_for_large_histories(self):
        d = os.path.join(self.tmp, "big")
        os.makedirs(d)
        run = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.name=a", "-c", "user.email=a@b", *a], check=True, capture_output=True)
        run("init", "-q")
        for i in range(70):
            with open(os.path.join(d, f"f{i}.txt"), "w") as f:
                f.write(f"v{i}\n")
        run("add", "."); run("commit", "-qm", "add")
        for i in range(70):
            run("rm", "-q", f"f{i}.txt")
        run("commit", "-qm", "rm all")
        self.assertEqual(len(gitscan.scan(d, limit=3)), 3)


class FactsTests(unittest.TestCase):
    def test_extraction(self):
        src = 'import ftplib\nimport os\n\ndef upload(x):\n    """Push things to the server."""\n'
        self.assertEqual(facts.functions(src), ["upload"])
        self.assertEqual(facts.dependencies(src), ["ftplib"])
        self.assertEqual(facts.intent(src), "Push things to the server.")
        self.assertEqual(facts.dependencies("const w = require('winston');"), ["winston"])
        self.assertEqual(facts.intent("#!/bin/sh\n# deploy it to production\n"), "deploy it to production")
        self.assertIsNone(facts.intent("x = 1\n# tweak 1\n"))  # too short to be a purpose
        self.assertIsNone(facts.intent("\n".join(["x = 1"] * 8) + "\n# a long comment far down the file\n"))


class PoetTests(RepoCase):
    def test_template_uses_real_facts_both_languages(self):
        g = self.ghost("legacy/ftp_uploader.py")
        for lang in ("en", "es"):
            last, cal = poet.template_verse(g, lang)
            self.assertEqual(len(cal.splitlines()), 4)
            self.assertTrue(last)

    def test_template_never_invents_a_function(self):
        g = dataclasses.replace(self.ghost("docs/roadmap_2020.md"))
        for lang in ("en", "es"):
            last, cal = poet.template_verse(g, lang)
            self.assertNotIn("()", last + cal)  # a markdown file has no functions to claim
        code = self.ghost("legacy/ftp_uploader.py")
        seen = " ".join(" ".join(poet.template_verse(dataclasses.replace(code, commit=str(i)), "en")) for i in range(40))
        self.assertIn("upload_report()", seen)

    def test_templates_are_deterministic(self):
        g = self.ghost("src/captcha_v1.py")
        self.assertEqual(poet.template_verse(g), poet.template_verse(g))

    def test_span(self):
        self.assertEqual(poet.span(800), "2 years")
        self.assertEqual(poet.span(400), "1 year")
        self.assertEqual(poet.span(90), "3 months")
        self.assertEqual(poet.span(5, "es"), "5 días")

    def test_seance_fallback_answers(self):
        g = self.ghost("legacy/ftp_uploader.py")
        self.assertIn("remove ftp", poet.seance_fallback(g, "why did you die?"))
        self.assertIn("Ana", poet.seance_fallback(g, "who wrote you?"))
        self.assertIn("upload_report()", poet.seance_fallback(g, "what did you do? your code?"))
        self.assertIn("2019-03-04", poet.seance_fallback(g, "when were you born"))
        self.assertIn("Los muertos", poet.seance_fallback(g, "hmm", "es"))

    def test_compose_with_model_and_cache(self):
        g = self.ghost("legacy/ftp_uploader.py")
        cache = VerseCache(os.path.join(self.tmp, "verses.json"))
        with FakeServer() as srv:
            b = llm.OllamaBackend(srv.url, "gemma3")
            poet.compose(dataclasses.replace(g), b, "en", cache)
            first = dataclasses.replace(g)
            poet.compose(first, b, "en", cache)  # served from cache
            self.assertEqual(sum(1 for p, _ in srv.requests if p == "/api/generate"), 1)
            self.assertEqual(first.voice, "model:gemma3")
            self.assertIn("never missed a night", first.last_words)
            # prompt really contains the file's code and facts
            prompt = srv.requests[0][1]["prompt"]
            self.assertIn("upload_report", prompt)
            self.assertIn("remove ftp, partner moved to S3", prompt)
            poet.compose(dataclasses.replace(g), b, "en", cache, refresh=True)
            self.assertEqual(sum(1 for p, _ in srv.requests if p == "/api/generate"), 2)
        # cache survives a restart
        self.assertIsNotNone(VerseCache(os.path.join(self.tmp, "verses.json")).get(
            VerseCache.key(str(prompts.PROMPT_VERSION), "ollama:gemma3", "en", g.commit, g.path)))

    def test_bad_format_retries_then_falls_back(self):
        g = dataclasses.replace(self.ghost("src/captcha_v1.py"))
        with FakeServer(reply="Sure! Here is a poem about a file.") as srv:
            poet.compose(g, llm.OllamaBackend(srv.url, "gemma3"), "en")
            self.assertEqual(sum(1 for p, _ in srv.requests if p == "/api/generate"), poet.ATTEMPTS)
        self.assertEqual(g.voice, "template")
        self.assertTrue(g.calavera)

    def test_unreachable_model_falls_back(self):
        g = dataclasses.replace(self.ghost("src/captcha_v1.py"))
        poet.compose(g, llm.OllamaBackend("http://127.0.0.1:1", "gemma3"))
        self.assertEqual(g.voice, "template")

    def test_summary_is_honest(self):
        a, b = dataclasses.replace(self.ghost("src/captcha_v1.py")), dataclasses.replace(self.ghost("legacy/ftp_uploader.py"))
        self.assertIn("no model was used", poet.summary([a, b]))
        a.voice = "model:gemma3"
        self.assertIn("1 of 2", poet.summary([a, b]))
        b.voice = "model:gemma3"
        self.assertIn("written by gemma3", poet.summary([a, b]))


class ParseTests(unittest.TestCase):
    def test_parse_good_and_messy(self):
        self.assertEqual(prompts.parse_epitaph(GOOD_REPLY)[0], "I was upload_report() and I never missed a night.")
        messy = "```\n**LAST WORDS:** \"Bye.\"\n**CALAVERA:**\nline one\nline two\nline three\n```"
        self.assertEqual(prompts.parse_epitaph(messy), ("Bye.", "line one\nline two\nline three"))

    def test_parse_rejects_garbage(self):
        self.assertIsNone(prompts.parse_epitaph("no format here"))
        self.assertIsNone(prompts.parse_epitaph("LAST WORDS: hi\nCALAVERA:\nonly one line"))


class LLMTests(unittest.TestCase):
    def test_ollama_stream_and_check(self):
        with FakeServer() as srv:
            b = llm.OllamaBackend(srv.url, "gemma3")
            self.assertTrue(b.check()[0])
            self.assertEqual(list(b.chat_stream([{"role": "user", "content": "hi"}])), TOKENS)
            self.assertFalse(llm.OllamaBackend(srv.url, "llama9").check()[0])
            self.assertIn("ollama pull llama9", llm.OllamaBackend(srv.url, "llama9").check()[1])

    def test_openai_generate_stream_and_check(self):
        with FakeServer("openai") as srv:
            b = llm.OpenAICompatBackend(srv.url, "m")
            self.assertTrue(b.check()[0])
            self.assertEqual(b.generate("x"), GOOD_REPLY)
            self.assertEqual(list(b.chat_stream([{"role": "user", "content": "hi"}])), TOKENS)

    def test_unreachable_raises_llmerror(self):
        with self.assertRaises(llm.LLMError):
            llm.OllamaBackend("http://127.0.0.1:1", "x").generate("hi")
        self.assertFalse(llm.OllamaBackend("http://127.0.0.1:1", "x").check()[0])

    def test_make_backend(self):
        self.assertEqual(llm.make_backend("none").name, "none")
        self.assertEqual(llm.make_backend("openai", "http://h:1", "m").host, "http://h:1")
        with self.assertRaises(ValueError):
            llm.make_backend("skynet")


class StoreTests(unittest.TestCase):
    def test_seance_store_persists_and_caps(self):
        path = os.path.join(tempfile.mkdtemp(), "s", "x.json")
        s = SeanceStore(path)
        for i in range(30):
            s.append("a.py", f"q{i}", f"a{i}")
        self.assertEqual(len(s.get("a.py")), 40)
        self.assertEqual(SeanceStore(path).get("a.py")[-1]["content"], "a29")
        s.reset("a.py")
        self.assertEqual(SeanceStore(path).get("a.py"), [])

    def test_corrupt_store_is_ignored(self):
        path = os.path.join(tempfile.mkdtemp(), "bad.json")
        with open(path, "w") as f:
            f.write("{not json")
        self.assertEqual(SeanceStore(path).all(), {})


if __name__ == "__main__":
    unittest.main()
