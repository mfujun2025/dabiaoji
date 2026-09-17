# -*- coding: utf-8 -*-
"""
激光打标机.cn — 产物自检

1. 内链自检：解析 HTML 的 href/src，断言目标文件存在
2. 占位符残留检查：不得存在 {{TOKEN}}
3. 必备文件检查：CNAME / .nojekyll / robots.txt / sitemap.xml / style.css
4. sitemap.xml 与本地页面一致性
5. 关键内容断言：域名在售标注、联系邮箱、标准编号
"""
import os
import re
import sys
from html.parser import HTMLParser

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(ROOT, "public")

PUNY = "xn--54q482buudoxam6z.cn"
EMAIL = "mfujun@agent.qq.com"

errors = []
warnings = []
checked_links = 0


def rel_to_file(path):
    """把站内路径映射到产物文件"""
    p = path.split("#")[0].split("?")[0]
    if not p:
        return None
    if p.endswith("/"):
        p += "index.html"
    target = os.path.join(PUBLIC, p.lstrip("/").replace("/", os.sep))
    return target


def walk_html():
    for dirpath, dirnames, filenames in os.walk(PUBLIC):
        for fn in filenames:
            if fn.endswith(".html"):
                yield os.path.join(dirpath, fn)


# ---------------------------------------------------------------- 1 & 2
html_files = list(walk_html())
if not html_files:
    errors.append("public/ 下没有任何 HTML 产物")

HREF_RE = re.compile(r'(?:href|src)="([^"]+)"')
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")

for f in html_files:
    rel = os.path.relpath(f, PUBLIC)
    with open(f, encoding="utf-8") as fh:
        html = fh.read()

    # 占位符残留
    leftovers = set(PLACEHOLDER_RE.findall(html))
    if leftovers:
        errors.append("%s 存在未替换的占位符：%s" % (rel, ", ".join(sorted(leftovers))))

    # 内链
    for link in HREF_RE.findall(html):
        if link.startswith(("http://", "https://", "mailto:", "#", "data:", "tel:")):
            continue
        if link.startswith("//"):
            continue
        target = rel_to_file(link)
        checked_links += 1
        if target and not os.path.isfile(target):
            errors.append("%s 中的链接 %s 指向不存在的文件" % (rel, link))

# ---------------------------------------------------------------- 3
MUST_HAVE = [
    "index.html",
    "404.html",
    "CNAME",
    ".nojekyll",
    "robots.txt",
    "sitemap.xml",
    "static/style.css",
    "static/favicon.svg",
    "static/images/product-fiber-30w-photo.webp",
    "static/images/product-fiber-30w-photo.jpg",
    # 搜索引擎归属验证文件：必须落在产物根，才能从 https://域名/文件名 访问
    "BingSiteAuth.xml",
    "guide/index.html",
    "types/index.html",
    "applications/index.html",
    "faq/index.html",
    "domain/index.html",
    "contact/index.html",
    "about/index.html",
    "sitemap/index.html",
]
for m in MUST_HAVE:
    if not os.path.isfile(os.path.join(PUBLIC, m.replace("/", os.sep))):
        errors.append("缺少必备文件：%s" % m)

# CNAME 内容
cname_path = os.path.join(PUBLIC, "CNAME")
if os.path.isfile(cname_path):
    with open(cname_path, encoding="utf-8") as fh:
        content = fh.read().strip()
    if content != PUNY:
        errors.append("CNAME 内容应为 %s，实际为 %r" % (PUNY, content))

# ---------------------------------------------------------------- 4
sitemap_path = os.path.join(PUBLIC, "sitemap.xml")
if os.path.isfile(sitemap_path):
    with open(sitemap_path, encoding="utf-8") as fh:
        sm = fh.read()
    locs = re.findall(r"<loc>(.*?)</loc>", sm)
    if not locs:
        errors.append("sitemap.xml 中没有任何 <loc>")
    for loc in locs:
        if not loc.startswith("https://" + PUNY):
            errors.append("sitemap.xml 中的 URL 域名不正确：%s" % loc)
            continue
        path = loc[len("https://" + PUNY):] or "/"
        target = rel_to_file(path)
        if target and not os.path.isfile(target):
            errors.append("sitemap.xml 收录了不存在的页面：%s" % loc)
    # 反向：产物里的页面都应被收录
    for f in html_files:
        rel = os.path.relpath(f, PUBLIC).replace(os.sep, "/")
        if rel == "404.html":
            continue
        url_path = "/" + rel
        if url_path.endswith("/index.html"):
            url_path = url_path[: -len("index.html")]
        if ("https://" + PUNY + url_path) not in locs:
            warnings.append("页面未被 sitemap.xml 收录：%s" % url_path)

    # robots.txt 里应声明 sitemap
    with open(os.path.join(PUBLIC, "robots.txt"), encoding="utf-8") as fh:
        robots = fh.read()
    if "Sitemap:" not in robots:
        errors.append("robots.txt 未声明 Sitemap")
    if "Allow: /" not in robots:
        errors.append("robots.txt 未放行普通爬虫")

# ---------------------------------------------------------------- 5
def read(rel):
    with open(os.path.join(PUBLIC, rel.replace("/", os.sep)), encoding="utf-8") as fh:
        return fh.read()


idx = read("index.html")
if PUNY not in idx:
    errors.append("首页未出现 punycode 域名")
if EMAIL not in idx:
    errors.append("首页未出现联系邮箱")
if "出售" not in idx:
    errors.append("首页未标注域名出售")
if "mailto:" not in idx:
    errors.append("首页缺少 mailto 咨询入口")

# 首页 = 30W 光纤激光打标机产品详情页
for kw in ["30W 光纤激光打标机", "1064nm", "光学参数", "打标参数", "标准配置"]:
    if kw not in idx:
        errors.append("首页（产品详情页）缺少关键内容：%s" % kw)
if "spec-card" not in idx:
    errors.append("首页缺少参数速览卡片")
if '"@type": "Product"' not in idx:
    errors.append("首页缺少 Product 结构化数据")
if 'href="/products/"' not in idx:
    errors.append("首页缺少返回产品中心的入口")
for img in ["product-fiber-30w.svg", "optical-path.svg", "marking-effects.svg", "material-matrix.svg"]:
    if img not in idx:
        errors.append("首页缺少配图引用：%s" % img)

prod = read("products/index.html")
for kw in ["产品中心", "30W 光纤激光打标机", EMAIL, PUNY]:
    if kw not in prod:
        errors.append("产品中心页缺少关键内容：%s" % kw)
if "product-card" not in prod:
    errors.append("产品中心页缺少产品卡片")

hm = read("home/index.html")
for kw in ["激光打标机怎么选", "出售", EMAIL]:
    if kw not in hm:
        errors.append("站点总览页（/home/）缺少原首页内容：%s" % kw)

dom = read("domain/index.html")
for kw in ["出售", EMAIL, PUNY, "担保交易"]:
    if kw not in dom:
        errors.append("域名页缺少关键内容：%s" % kw)

guide = read("guide/index.html")
if "GB/T 7247.1-2024" not in guide:
    errors.append("长文缺少现行标准编号 GB/T 7247.1-2024")
for kw in ["1064", "355", "10.6", "532"]:
    if kw not in guide:
        errors.append("长文缺少波长数据：%s" % kw)

# 全站都应能看到出售标注
for f in html_files:
    rel = os.path.relpath(f, PUBLIC).replace(os.sep, "/")
    if rel == "404.html":
        continue
    with open(f, encoding="utf-8") as fh:
        html = fh.read()
    if "出售" not in html:
        warnings.append("%s 页面上没有域名出售提示" % rel)
    if EMAIL not in html:
        warnings.append("%s 页面没有出现联系邮箱" % rel)

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class Balance(HTMLParser):
    """标签闭合平衡检查：模板拼接出错时最容易留下未闭合的 div"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errs = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_TAGS:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.errs.append("第 %d 行：多余的结束标签 </%s>" % (self.getpos()[0], tag))
            return
        if self.stack[-1][0] == tag:
            self.stack.pop()
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                unclosed = [t for t, _ in self.stack[i + 1:]]
                self.errs.append(
                    "第 %d 行：</%s> 之前有未闭合标签 %s" % (self.getpos()[0], tag, unclosed)
                )
                del self.stack[i:]
                return
        self.errs.append("第 %d 行：孤立的结束标签 </%s>" % (self.getpos()[0], tag))


# 表格包裹必须与表格数量一致（多一个 = 双层包裹，少一个 = 移动端会撑破布局）
for f in html_files:
    rel = os.path.relpath(f, PUBLIC).replace(os.sep, "/")
    with open(f, encoding="utf-8") as fh:
        html = fh.read()
    n_table = html.count("<table>")
    n_wrap = html.count('<div class="table-scroll">')
    if n_table != n_wrap:
        errors.append(
            "%s 表格包裹数不匹配：<table>=%d，table-scroll=%d" % (rel, n_table, n_wrap)
        )

    # 标签闭合平衡
    bal = Balance()
    bal.feed(html)
    bal.close()
    problems = list(bal.errs)
    if bal.stack:
        problems.append("文件结束时未闭合：%s" % [t for t, _ in bal.stack])
    for x in problems[:5]:
        errors.append("%s 标签结构异常 —— %s" % (rel, x))

# ---------------------------------------------------------------- 输出
total_bytes = 0
file_count = 0
for dirpath, dirnames, filenames in os.walk(PUBLIC):
    for fn in filenames:
        file_count += 1
        total_bytes += os.path.getsize(os.path.join(dirpath, fn))

print("=" * 58)
print("自检结果")
print("=" * 58)
print("HTML 页面：%d 个" % len(html_files))
print("产物文件：%d 个，共 %.1f KB" % (file_count, total_bytes / 1024.0))
print("检查内链：%d 条" % checked_links)
print()

if warnings:
    print("提示（%d 条）：" % len(warnings))
    for w in warnings:
        print("  · " + w)
    print()

if errors:
    print("错误（%d 条）：" % len(errors))
    for e in errors:
        print("  ✗ " + e)
    print()
    sys.exit(1)

print("全部检查通过 ✓")
