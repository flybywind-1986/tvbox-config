#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 sources.txt 里列的上游配置抓一遍，只保留"活着"的，合并成一个多仓 config.json。

用法:
    python scripts/build_config.py            # 正常跑
    python scripts/build_config.py --selftest # 用内置假数据自测，不联网

输出:
    config.json   给 TVBox / FongMi 用的多仓配置（TV 里只需要填这一个固定地址）
    report.md     上游存活报告
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOURCES = os.path.join(ROOT, "sources.txt")
TRUSTED = os.path.join(ROOT, "trusted.txt")
CONFIG = os.path.join(ROOT, "config.json")
REPORT = os.path.join(ROOT, "report.md")
TIMEOUT = 15
UA = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
# 电视在国内，raw.githubusercontent.com 基本拉不动，统一改写成 jsDelivr（同源镜像）。
# 想保留原始地址就跑：NO_REWRITE=1 python scripts/build_config.py
REWRITE = os.environ.get("NO_REWRITE", "") != "1"


def rewrite(url):
    """把 GitHub 的 raw 地址换成国内可直连的 jsDelivr 地址。"""
    if not REWRITE:
        return url
    u = url
    for prefix in ("https://raw.githubusercontent.com/", "http://raw.githubusercontent.com/"):
        if u.startswith(prefix):
            rest = u[len(prefix):]
            bits = rest.split("/", 3)
            if len(bits) == 4:
                owner, repo, branch, path = bits
                branch = branch.replace("refs/heads/", "")
                return "https://cdn.jsdelivr.net/gh/%s/%s@%s/%s" % (owner, repo, branch, path)
    if u.startswith("https://github.com/") and "/raw/" in u:
        rest = u[len("https://github.com/"):]
        owner, repo, raw, branch, path = (rest.split("/", 4) + ["", "", "", "", ""])[:5]
        if raw == "raw" and branch and path:
            return "https://cdn.jsdelivr.net/gh/%s/%s@%s/%s" % (owner, repo, branch, path)
    return u


def default_name(url):
    """没写备注名时，给个短名字：owner/repo/文件名 或 域名/文件名。"""
    try:
        rest = url.split("//", 1)[1]
        host, _, path = rest.partition("/")
        segs = [s for s in path.split("/") if s]
        stem = ""
        if segs:
            stem = segs[-1].split("@")[0].rsplit(".", 1)[0]
        owner = repo = ""
        if host == "cdn.jsdelivr.net" and path.startswith("gh/") and len(segs) >= 3:
            owner, repo = segs[1], segs[2].split("@")[0]
        elif host in ("raw.githubusercontent.com", "github.com") and len(segs) >= 2:
            owner, repo = segs[0], segs[1]
        if owner:
            return "%s/%s/%s" % (owner, repo, stem) if stem else "%s/%s" % (owner, repo)
        return "%s/%s" % (host, stem) if stem else host
    except Exception:
        return url[:40]


def read_sources():
    if not os.path.exists(SOURCES):
        return []
    out = []
    with open(SOURCES, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            url = parts[0].lstrip("\ufeff").strip()
            name = parts[1].strip() if len(parts) > 1 else default_name(url)
            out.append({"url": url, "name": name})
    return out


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("//"))


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        if resp.status != 200:
            raise ValueError("HTTP %s" % resp.status)
        raw = resp.read()
    if len(raw) < 20:
        raise ValueError("响应太短 (%d 字节)" % len(raw))
    text = raw.decode("utf-8-sig", "replace").lstrip("\ufeff").strip()
    if not text:
        raise ValueError("空响应")
    try:
        return json.loads(text)
    except ValueError:
        # 很多 TVBox 配置带 // 注释，App 侧能容忍，这里也宽松一次
        return json.loads(_strip_comments(text))


def looks_like_config(obj):
    if not isinstance(obj, dict):
        return False
    return ("sites" in obj) or ("urls" in obj)


def expand(entry, seen, alive, dead, depth=0):
    """把一个上游展开：单仓直接收；多仓把里面的仓再验一遍。"""
    try:
        obj = fetch_json(entry["url"])
    except Exception as e:
        dead.append((entry["name"], entry["url"], str(e)[:80]))
        return
    if not looks_like_config(obj):
        dead.append((entry["name"], entry["url"], "不是 TVBox 配置（没有 sites/urls）"))
        return

    if "urls" in obj and isinstance(obj["urls"], list):
        inner = [u for u in obj["urls"] if isinstance(u, dict) and u.get("url")]
        if not inner:
            dead.append((entry["name"], entry["url"], "多仓里没有有效条目"))
            return
        if depth >= 1:
            return
        for u in inner[:20]:
            sub = {"url": rewrite(u.get("url") or ""), "name": u.get("name") or entry["name"]}
            if sub["url"] in seen:
                continue
            seen.add(sub["url"])
            expand(sub, seen, alive, dead, depth + 1)
        return

    sites = obj.get("sites") or []
    entry["sites"] = len(sites)
    entry["url"] = rewrite(entry["url"])
    alive.append(entry)


def build():
    srcs = read_sources()
    alive, dead, seen = [], [], set()
    for s in srcs:
        s["url"] = rewrite(s["url"])   # 先改写再验证，保证验过的就是发出去的
        if s["url"] in seen:
            continue
        seen.add(s["url"])
        expand(s, seen, alive, dead)

    # trusted.txt：只在中国能解析的源（GitHub runner 验证不到），照样保留
    if os.path.exists(TRUSTED):
        have = {a["url"] for a in alive}
        with open(TRUSTED, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                bits = line.split("|")
                u = bits[0].strip()
                if u and u not in have:
                    alive.append({"url": u, "name": (bits[1].strip() if len(bits) > 1 else default_name(u)), "sites": "?"})
                    have.add(u)

    config = {
        "name": "我的电视源",
        "urls": [{"url": a["url"], "name": a["name"]} for a in alive],
    }
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    lines = ["# 源存活报告", "", "更新时间：%s" % now, "",
             "可用：**%d** 条，失效：**%d** 条。" % (len(alive), len(dead)), "",
             "## 可用", "", "| 名称 | 站点数 | 地址 |", "|---|---|---|"]
    for a in alive:
        lines.append("| %s | %s | %s |" % (a["name"], a.get("sites", "?"), a["url"]))
    lines += ["", "## 失效", "", "| 名称 | 原因 | 地址 |", "|---|---|---|"]
    for n, u, why in dead:
        lines.append("| %s | %s | %s |" % (n, why, u))
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("alive=%d dead=%d" % (len(alive), len(dead)))
    for a in alive:
        print("  OK   %-20s sites=%s" % (a["name"], a.get("sites")))
    for n, u, why in dead:
        print("  DEAD %-20s %s" % (n, why))
    return 0 if alive else 1


def selftest():
    os.makedirs(ROOT, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump({"name": "selftest", "urls": [{"url": "http://x", "name": "x"}]}, f)
    assert looks_like_config({"sites": []})
    assert not looks_like_config({"foo": 1})
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else build())