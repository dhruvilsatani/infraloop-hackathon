import os, sys, unittest, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uploads


class UploadRules(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(uploads.classify("src/app.py", 100), "send")
        self.assertEqual(uploads.classify("node_modules/x/index.js", 10), "skip")
        self.assertEqual(uploads.classify("a/b/.git/config", 10), "skip")
        self.assertEqual(uploads.classify(".env", 10), "placeholder")
        self.assertEqual(uploads.classify("config/.env.production", 10), "placeholder")
        self.assertEqual(uploads.classify(".env.example", 10), "send")
        self.assertEqual(uploads.classify("deploy/server.key", 10), "placeholder")
        self.assertEqual(uploads.classify("logo.png", 10), "placeholder")
        self.assertEqual(uploads.classify("data.json", 5 * 1024 * 1024), "placeholder")

    def test_bad_paths_rejected(self):
        for bad in ("/etc/passwd", "../x", "a/../../x", "a//b", "C:/x", "a\\b", "", "a/\x00b"):
            with self.assertRaises(uploads.UploadError, msg=repr(bad)):
                uploads.clean_relative_path(bad)

    def test_secret_content_never_reaches_disk(self):
        uid = uploads.start_upload()
        try:
            uploads.add_files(uid, [{"path": "proj/.env", "text": "SECRET=hunter2"}, {"path": "proj/app.py", "text": "print(1)"},
                                    {"path": "proj/node_modules/a/b.js", "text": "x"}, {"path": "proj/k.pem", "text": "-----BEGIN"}])
            root = uploads.project_path(uid)
            self.assertEqual(open(os.path.join(root, ".env")).read(), "")
            self.assertEqual(open(os.path.join(root, "k.pem")).read(), "")
            self.assertEqual(open(os.path.join(root, "app.py")).read(), "print(1)")
            self.assertFalse(os.path.exists(os.path.join(root, "node_modules")))
        finally:
            uploads.remove_upload(uid)

    def test_traversal_and_limits(self):
        uid = uploads.start_upload()
        try:
            with self.assertRaises(uploads.UploadError):
                uploads.add_files(uid, [{"path": "proj/../../evil.txt", "text": "x"}])
            with self.assertRaises(uploads.UploadError):
                uploads.add_files(uid, [{"path": "top-level-file.txt", "text": "x"}])
            with self.assertRaises(uploads.UploadError):
                uploads.add_files("not-a-uuid", [])
            with self.assertRaises(uploads.UploadError):
                uploads.add_files(uid, [{"path": "p/a.txt", "text": "x"}] * (uploads.MAX_BATCH_FILES + 1))
        finally:
            uploads.remove_upload(uid)

    def test_stale_uploads_are_cleaned(self):
        uid = uploads.start_upload()
        base = uploads._upload_dir(uid)
        import time
        uploads.cleanup_stale(now=time.time() + uploads.STALE_SECONDS + 10)
        self.assertFalse(os.path.exists(base))


try:
    from fastapi.testclient import TestClient
    HAVE_API = True
except Exception:
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "fastapi/httpx not installed")
class UploadThroughApi(unittest.TestCase):
    def test_full_flow_scans_and_deletes(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web"))
        from web import api
        c = TestClient(api.app)
        uid = c.post("/upload/start").json()["upload_id"]
        files = [{"path": "shop/Dockerfile", "text": "FROM python:3.12\nCMD python app.py\n"},
                 {"path": "shop/app.py", "text": "from flask import Flask\napp = Flask(__name__)\n"},
                 {"path": "shop/requirements.txt", "text": "flask==3.0\npsycopg2\n"},
                 {"path": "shop/.env", "text": "DB_PASSWORD=hunter2"},
                 {"path": "shop/node_modules/x/y.js", "text": "junk"}]
        r = c.post(f"/upload/{uid}/files", json={"files": files})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["skipped"], 1)
        r = c.post("/scan", json={"upload_id": uid, "notes": ""})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["questions"])
        self.assertFalse(os.path.exists(uploads._upload_dir(uid)), "uploaded code must be deleted after the scan")
        sess = api._load_session(r.json()["session_id"])
        self.assertNotIn("hunter2", str(sess))

    def test_bad_requests(self):
        from web import api
        c = TestClient(api.app)
        self.assertEqual(c.post("/scan", json={}).status_code, 400)
        self.assertEqual(c.post("/upload/not-a-uuid/files", json={"files": []}).status_code, 400)
        uid = c.post("/upload/start").json()["upload_id"]
        self.assertEqual(c.post(f"/upload/{uid}/files", json={"files": [{"path": "../x/y", "text": ""}]}).status_code, 400)
        uploads.remove_upload(uid)


if __name__ == "__main__":
    unittest.main()
