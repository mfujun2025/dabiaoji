# -*- coding: utf-8 -*-
"""部署后验证：GitHub Pages 配置 + 自定义域名线上可访问性 + CF 回源行为"""
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

OWNER, REPO = "mfujun2025", "dabiaoji"
CNAME = "xn--54q482buudoxam6z.cn"
API = "https://api.github.com"

with open(os.path.expanduser("~/.git-credentials"), encoding="utf-8") as f:
    TOKEN = f.readline().strip().split(":", 2)[2].split("@")[0]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


NO_REDIR = urllib.request.build_opener(NoRedirect)


def api(path):
    req = urllib.request.Request(API + path)
    req.add_header("Authorization", "token " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "wb-verify")
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def fetch(url, follow=True, timeout=40, retries=3):
    """本机代理偶发 502，必须带重试，否则会把抖动误判成站点故障。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    opener = urllib.request.build_opener() if follow else NO_REDIR
    last = (0, {}, b"")
    for attempt in range(retries):
        try:
            with opener.open(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()   # 4xx/5xx 是有效响应，不重试
        except Exception as e:
            last = (0, {"error": type(e).__name__ + ": " + str(e)}, b"")
            time.sleep(2)
    return last


print("=" * 66)
print("GitHub Pages 服务端配置")
print("=" * 66)
s, pg = api("/repos/%s/%s/pages" % (OWNER, REPO))
if s == 200:
    print("  URL          :", pg.get("html_url"))
    print("  status       :", pg.get("status"))
    print("  source       :", pg.get("source", {}).get("branch"), pg.get("source", {}).get("path"))
    print("  cname        :", pg.get("cname"))
    print("  build_type   :", pg.get("build_type"))
    print("  https_enforced:", pg.get("https_enforced"))
    cert = pg.get("https_certificate") or {}
    print("  https_cert   : state=%s domains=%s expires=%s" % (
        cert.get("state"), cert.get("domains"), cert.get("expires_at")))
else:
    print("  查询失败 HTTP", s)

s, b = api("/repos/%s/%s/pages/builds/latest" % (OWNER, REPO))
if s == 200:
    print("  最近构建     : status=%s commit=%s 耗时=%ss" % (
        b.get("status"), (b.get("commit") or "")[:10], b.get("duration")))

# --------------------------------------------------------------- 线上访问
cb = int(time.time())
BASE = "https://" + CNAME
PAGES = [
    ("/", "30W"),
    ("/products/", "产品中心"),
    ("/home/", "激光打标机"),
    ("/guide/", "激光打标机"),
    ("/types/", "紫外"),
    ("/applications/", "应用"),
    ("/faq/", "GB/T 7247.1-2024"),
    ("/domain/", "出售"),
    ("/contact/", "mfujun@agent.qq.com"),
    ("/about/", "关于"),
    ("/sitemap/", "网站地图"),
    ("/sitemap.xml", "xn--54q482buudoxam6z"),
    ("/robots.txt", "Sitemap"),
    ("/static/style.css", "--brand"),
    ("/static/images/product-fiber-30w.svg", "svg"),
    ("/nope-does-not-exist/", ""),
]

print()
print("=" * 66)
print("线上访问  %s" % BASE)
print("=" * 66)
fail = []
for path, needle in PAGES:
    url = BASE + path + ("&" if "?" in path else "?") + "cb=%d" % cb
    st, hd, body = fetch(url)
    txt = body.decode("utf-8", "replace")
    hit = (needle in txt) if needle else True
    cache = hd.get("X-Cache") or hd.get("x-cache") or hd.get("cf-cache-status") or "-"
    expect = 404 if "nope" in path else 200
    ok = (st == expect) and hit
    if not ok:
        fail.append((path, st, expect, needle, hit))
    print("  %-36s %s  %-12s %s" % (
        path, ("%3d %s" % (st, "OK " if ok else "BAD")), cache,
        "" if hit else "内容特征缺失:" + needle))

print()
print("=" * 66)
print("HTTP -> HTTPS 重定向行为（判断 Cloudflare SSL 模式）")
print("=" * 66)
for host in ["http://" + CNAME + "/", "http://www." + CNAME + "/", "https://www." + CNAME + "/"]:
    st, hd, _ = fetch(host + "?cb=%d" % cb, follow=False)
    loc = hd.get("Location", "")
    print("  %-44s -> %s  %s" % (host, st, ("Location: " + loc) if loc else "(无跳转)"))
    if loc:
        st2, hd2, _ = fetch(loc, follow=False)
        print("  %-44s -> %s  %s" % ("  跟随", st2, hd2.get("Location", "(终点)")))

print()
print("=" * 66)
print("旁路验证：GitHub 原生地址")
print("=" * 66)
st, hd, _ = fetch("https://%s.github.io/%s/?cb=%d" % (OWNER, REPO, cb), follow=False)
print("  https://%s.github.io/%s/  -> %s  %s" % (OWNER, REPO, st, hd.get("Location", "(无跳转)")))

print()
print("=" * 66)
print("首页关键内容断言（产品详情页）")
print("=" * 66)
import re as _re
st, hd, body = fetch(BASE + "/?cb=%d" % cb)
txt = body.decode("utf-8", "replace")
ASSERTS = [
    ("产品型号 LM-F30", "LM-F30"),
    ("产品中心入口", "/products/"),
    ("域名出售标注", "出售"),
    ("联系邮箱", "mfujun@agent.qq.com"),
    ("punycode 域名", CNAME),
    ("中文域名", "激光打标机.cn"),
    ("canonical 自指到自定义域名", 'rel="canonical" href="https://' + CNAME),
    ("结构化数据 JSON-LD", "application/ld+json"),
    ("安全标准编号", "GB/T 7247.1-2024"),
    ("产品配图", "product-fiber-30w.svg"),
]
for name, needle in ASSERTS:
    print("  %-30s %s" % (name, "✓" if needle in txt else "✗ 缺失"))
_t = _re.search(r"<title>(.*?)</title>", txt, _re.S)
_d = _re.search(r'<meta name="description" content="(.*?)"', txt, _re.S)
_c = _re.search(r'<link rel="canonical" href="([^"]+)"', txt, _re.S)
print()
print("  <title>      %d 字符｜%s" % (len(_t.group(1).strip()), _t.group(1).strip()) if _t else "  <title> 缺失")
print("  description   %d 字符" % len(_d.group(1).strip()) if _d else "  description 缺失")
print("  canonical     %s" % (_c.group(1) if _c else "缺失"))

print()
print("=" * 66)
print("结论")
print("=" * 66)
if fail:
    print("  有 %d 项异常：" % len(fail))
    for p, st, ex, nd, hit in fail:
        print("    %-30s 实际=%s 期望=%s %s" % (p, st, ex, "内容特征缺失" if not hit else ""))
else:
    print("  全部 %d 个路径返回正常，内容特征全部命中 ✓" % len(PAGES))
