# -*- coding: utf-8 -*-
"""把 laser-marking-cn 部署到 GitHub。

- 源码 -> main 分支
- 构建产物 public/ -> gh-pages 分支（孤儿 commit，完整镜像本地）
- GitHub Pages 发布源指向 gh-pages，并绑定自定义域名

本机 git push 受 Watt Toolkit 拦截，全程走 REST API。
幂等：可重复执行。
"""
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

OWNER = "mfujun2025"
REPO = "dabiaoji"
BRANCH_SRC = "main"
BRANCH_DIST = "gh-pages"
CNAME = "xn--54q482buudoxam6z.cn"

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(ROOT, "public")
API = "https://api.github.com"

with open(os.path.expanduser("~/.git-credentials"), encoding="utf-8") as _f:
    TOKEN = _f.readline().strip().split(":", 2)[2].split("@")[0]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

REPO_PATH = "/repos/%s/%s" % (OWNER, REPO)


def api(path, method="GET", body=None, retries=3, ok=(200, 201)):
    """调用 GitHub API。返回 (status, data)。"""
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    last = (0, {})
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "token " + TOKEN)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "wb-deploy")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            # urllib 默认 application/x-www-form-urlencoded，会让 POST /git/trees 报 404
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, (json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code in (422, 429, 500, 502, 503) and attempt < retries - 1:
                last = (e.code, {"raw": raw[:300]})
                time.sleep(1.5 * (attempt + 1))
                continue
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"raw": raw[:400]}
        except Exception as e:  # 网络层
            last = (0, {"error": str(e)})
            time.sleep(1.5 * (attempt + 1))
    return last


# --------------------------------------------------------------------- 文件收集

def collect_source():
    files = []
    for name in [".gitignore", "build.py", "check.py", "site.json"]:
        p = os.path.join(ROOT, name)
        if os.path.exists(p):
            files.append((name, p))
    for d in ["content", "templates", "static"]:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, d)):
            dirnames[:] = [x for x in dirnames if x != "__pycache__"]
            for fn in sorted(filenames):
                if fn.endswith(".pyc") or fn.endswith(".pyo"):
                    continue
                p = os.path.join(dirpath, fn)
                files.append((os.path.relpath(p, ROOT).replace(os.sep, "/"), p))
    return files


def collect_dist():
    files = []
    for dirpath, dirnames, filenames in os.walk(PUBLIC):
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            # 注意：不能过滤点开头文件，.nojekyll 必须上传
            files.append((os.path.relpath(p, PUBLIC).replace(os.sep, "/"), p))
    return files


def blob_sha_of(path):
    """本地计算 git blob sha（不联网）"""
    import hashlib
    with open(path, "rb") as fh:
        data = fh.read()
    h = hashlib.sha1(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


# --------------------------------------------------------------------- 推送

def push(branch, files, message, mirror=False):
    """把 files 提交到 branch。

    mirror=True  -> 用完整独立树（远端完全等于 files，多余文件被清掉）
    mirror=False -> 用 base_tree 增量
    """
    s, ref = api("%s/git/ref/heads/%s" % (REPO_PATH, branch))
    exists = s == 200
    base_commit = ref["object"]["sha"] if exists else None
    base_tree = None
    if exists and not mirror:
        s2, cm = api("%s/git/commits/%s" % (REPO_PATH, base_commit))
        if s2 == 200:
            base_tree = cm["tree"]["sha"]

    # 1) 逐个建 blob
    entries = []
    for i, (rel, path) in enumerate(files, 1):
        with open(path, "rb") as fh:
            raw = fh.read()
        s, blob = api("%s/git/blobs" % REPO_PATH, "POST", {
            "content": base64.b64encode(raw).decode("ascii"),
            "encoding": "base64",
        })
        if s != 201:
            raise RuntimeError("blob 失败 %s -> %s %s" % (rel, s, json.dumps(blob, ensure_ascii=False)[:200]))
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        if i % 10 == 0:
            print("      ... %d/%d" % (i, len(files)))

    # 2) 建 tree
    body = {"tree": entries}
    if base_tree:
        body["base_tree"] = base_tree
    s, tree = api("%s/git/trees" % REPO_PATH, "POST", body)
    if s != 201:
        raise RuntimeError("tree 失败: %s %s" % (s, json.dumps(tree, ensure_ascii=False)[:300]))

    # 3) 建 commit
    parents = [base_commit] if (exists and not mirror) else []
    s, commit = api("%s/git/commits" % REPO_PATH, "POST", {
        "message": message,
        "tree": tree["sha"],
        "parents": parents,
    })
    if s != 201:
        raise RuntimeError("commit 失败: %s %s" % (s, json.dumps(commit, ensure_ascii=False)[:300]))

    # 4) 更新 ref
    if exists:
        s, r = api("%s/git/refs/heads/%s" % (REPO_PATH, branch), "PATCH",
                   {"sha": commit["sha"], "force": bool(mirror)})
        if s != 200:
            raise RuntimeError("ref 更新失败: %s %s" % (s, json.dumps(r, ensure_ascii=False)[:200]))
    else:
        s, r = api("%s/git/refs" % REPO_PATH, "POST",
                   {"ref": "refs/heads/" + branch, "sha": commit["sha"]})
        if s not in (201, 422):  # 422 = 已存在，等价成功
            raise RuntimeError("ref 创建失败: %s %s" % (s, json.dumps(r, ensure_ascii=False)[:200]))

    return commit["sha"], len(entries)


def verify_tree(branch, expect):
    """核对远端分支的文件清单"""
    s, t = api("%s/git/trees/%s?recursive=1" % (REPO_PATH, branch))
    if s != 200:
        return None, [], "tree 读取失败 %s" % s
    remote = sorted(x["path"] for x in t.get("tree", []) if x["type"] == "blob")
    local = sorted(expect)
    missing = [x for x in local if x not in remote]
    extra = [x for x in remote if x not in local]
    return remote, (missing, extra), None


# --------------------------------------------------------------------- 主流程

def main():
    print("=" * 64)
    print("部署 %s/%s  ->  https://%s" % (OWNER, REPO, CNAME))
    print("=" * 64)

    # ---------- 1 激活空仓库
    print("\n[1/5] 激活仓库（空仓库必须先用 Contents API 落第一个 commit）")
    readme = os.path.join(ROOT, "README.md")
    b64 = base64.b64encode(open(readme, "rb").read()).decode("ascii")
    s, c = api("%s/contents/README.md" % REPO_PATH)
    if s == 200:
        s, r = api("%s/contents/README.md" % REPO_PATH, "PUT",
                   {"message": "docs: 更新 README", "content": b64, "sha": c["sha"]})
        print("  README.md 已存在，更新 -> HTTP %s" % s)
    elif s == 404:
        s, r = api("%s/contents/README.md" % REPO_PATH, "PUT",
                   {"message": "chore: 初始化仓库", "content": b64})
        print("  空仓库，首个 commit -> HTTP %s（201 正常）" % s)
    else:
        print("  仓库状态查询异常 HTTP %s %s" % (s, c))
    if s not in (200, 201):
        print("  激活失败，终止"); return 1

    # ---------- 2 推源码
    print("\n[2/5] 推送源码 -> %s" % BRANCH_SRC)
    src = collect_source()
    print("  源码文件 %d 个（README 已在第 1 步提交）" % len(src))
    sha, n = push(BRANCH_SRC, src, "feat: 激光打标机.cn 站点源码（产品中心 + SEO 长文 + 域名出售）",
                  mirror=False)
    print("  commit %s  文件 %d" % (sha[:10], n))
    _, diff, err = verify_tree(BRANCH_SRC, [x[0] for x in src] + ["README.md"])
    if err:
        print("  核对: " + err)
    elif diff[0] or diff[1]:
        print("  核对: 缺失 %s / 多余 %s" % (diff[0] or "无", diff[1] or "无"))
    else:
        print("  核对: 远端与本地完全一致 ✓")

    # ---------- 3 推产物
    print("\n[3/5] 推送构建产物 -> %s" % BRANCH_DIST)
    dist = collect_dist()
    print("  产物文件 %d 个" % len(dist))
    for must in ["index.html", "CNAME", ".nojekyll"]:
        mark = "✓" if any(x[0] == must for x in dist) else "✗ 缺失"
        print("    %-14s %s" % (must, mark))
    sha2, n2 = push(BRANCH_DIST, dist, "build: 发布站点产物", mirror=True)
    print("  commit %s  文件 %d" % (sha2[:10], n2))
    _, diff, err = verify_tree(BRANCH_DIST, [x[0] for x in dist])
    if err:
        print("  核对: " + err)
    elif diff[0] or diff[1]:
        print("  核对: 缺失 %s / 多余 %s" % (diff[0] or "无", diff[1] or "无"))
    else:
        print("  核对: 远端与本地完全一致 ✓")

    # ---------- 4 Pages + 自定义域名
    print("\n[4/5] 配置 GitHub Pages 与自定义域名")
    payload = {"source": {"branch": BRANCH_DIST, "path": "/"}, "cname": CNAME}
    s, pg = api("%s/pages" % REPO_PATH)
    if s == 404:
        s2, r = api("%s/pages" % REPO_PATH, "POST", payload)
        if s2 == 201:
            print("  Pages 已启用 -> HTTP 201")
        elif s2 == 409:
            print("  Pages 已启用（409 = already enabled，非错误）")
        else:
            print("  启用返回 HTTP %s %s" % (s2, json.dumps(r, ensure_ascii=False)[:200]))
    elif s == 200:
        s2, r = api("%s/pages" % REPO_PATH, "PUT", payload)
        print("  Pages 已存在，改配置 -> HTTP %s（204 = 无 body 正常）" % s2)
    else:
        print("  Pages 查询异常 HTTP %s" % s)

    s, pg = api("%s/pages" % REPO_PATH)
    if s == 200:
        src_cfg = pg.get("source", {})
        print("  当前配置: branch=%s path=%s cname=%s build_type=%s status=%s" % (
            src_cfg.get("branch"), src_cfg.get("path"), pg.get("cname"),
            pg.get("build_type"), pg.get("status")))
        if pg.get("cname") != CNAME:
            print("  ⚠ cname 未写入，重试 PUT")
            api("%s/pages" % REPO_PATH, "PUT", payload)
    else:
        print("  读取 Pages 配置失败 HTTP %s" % s)

    # ---------- 5 触发构建
    print("\n[5/5] 触发 Pages 构建")
    s, r = api("%s/pages/builds" % REPO_PATH, "POST", {})
    print("  触发 -> HTTP %s %s" % (s, r.get("status", "")))
    for i in range(20):
        time.sleep(12)
        s, b = api("%s/pages/builds/latest" % REPO_PATH)
        if s != 200:
            print("  第 %d 次: HTTP %s" % (i + 1, s)); continue
        print("  第 %d 次: status=%s commit=%s" % (i + 1, b.get("status"), (b.get("commit") or "")[:10]))
        if b.get("status") == "built":
            return 0
        if b.get("status") == "errored":
            print("  构建失败: %s" % b.get("error", {}).get("message"))
            return 1
    print("  构建仍在进行，稍后可用 GET /pages/builds/latest 复查")
    return 0


if __name__ == "__main__":
    sys.exit(main())
