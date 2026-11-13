# -*- coding: utf-8 -*-
"""把本地文件推到 Gitee 仓库（GitHub Action 里也用这段逻辑）。"""
import base64, json, os, sys, urllib.request, urllib.error

TOKEN = os.environ.get("GITEE_TOKEN", "")
OWNER, REPO = "flybywind2021", "tvbox-config"
BRANCH = "main"

def api(path, method="GET", payload=None):
    url = "https://gitee.com/api/v5/repos/%s/%s/contents/%s" % (OWNER, REPO, path)
    if method == "GET":
        url += "?access_token=%s&ref=%s" % (TOKEN, BRANCH)
        req = urllib.request.Request(url, headers={"User-Agent": "dsh"})
        return json.load(urllib.request.urlopen(req, timeout=30))
    body = dict(payload)
    body["access_token"] = TOKEN
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="PUT",
                                 headers={"Content-Type": "application/json", "User-Agent": "dsh"})
    return json.load(urllib.request.urlopen(req, timeout=30))

def push(path, local):
    with open(local, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    try:
        old = api(path)
        sha = old.get("sha")
    except urllib.error.HTTPError:
        sha = None
    payload = {"content": content, "message": "sync %s from GitHub" % path, "branch": BRANCH}
    if sha:
        payload["sha"] = sha
    try:
        r = api(path, "PUT", payload)
        print("OK   %-12s -> %s" % (path, (r.get("commit") or {}).get("sha", "")[:8]))
    except urllib.error.HTTPError as e:
        print("FAIL %-12s %s %s" % (path, e.code, e.read().decode()[:200]))

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for name in ("config.json", "report.md"):
    p = os.path.join(root, name)
    if os.path.exists(p):
        push(name, p)
