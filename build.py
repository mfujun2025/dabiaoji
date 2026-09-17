# -*- coding: utf-8 -*-
"""
激光打标机.cn — 静态站构建脚本

Python + markdown（{{TOKEN}} 替换式模板）→ public/
不清空 public/，覆盖式写入（Windows 下 shutil.rmtree 会被路由到回收站）。
"""
import json
import os
import re
import shutil
import sys
from urllib.parse import quote

import markdown

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
TEMPL = os.path.join(ROOT, "templates")
STATIC = os.path.join(ROOT, "static")
PUBLIC = os.path.join(ROOT, "public")

TODAY = "2026-09-17"
YEAR = "2026"

with open(os.path.join(ROOT, "site.json"), encoding="utf-8") as f:
    SITE = json.load(f)

BASE = SITE["base_url"].rstrip("/")
EMAIL = SITE["email"]
PUNY = SITE["domain_punycode"]
SITE_NAME = SITE["name"]

# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------


def tpl(name):
    with open(os.path.join(TEMPL, name), encoding="utf-8") as f:
        return f.read()


def write(rel, text):
    dst = os.path.join(PUBLIC, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text)
    return dst


def mailto(subject):
    return "mailto:%s?subject=%s" % (EMAIL, quote(subject))


def parse_doc(path):
    """极简 front matter 解析：--- 之间的 key: value"""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    meta, body = {}, raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            head = raw[3:end].strip()
            body = raw[end + 4:].lstrip("\n")
            for line in head.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
    return meta, body


def render_md(text):
    md = markdown.Markdown(
        extensions=["extra", "toc"],
        extension_configs={"toc": {"toc_depth": "2-3", "anchorlink": False}},
    )
    html = md.convert(text)
    # 表格统一由这里包裹，移动端才不会被撑破布局。
    # 先归一化：内容里若已手写 table-scroll 包裹，先剥掉，避免双层（幂等）。
    html = re.sub(r'<div class="table-scroll">\s*<table>', "<table>", html)
    html = re.sub(r"</table>\s*</div>", "</table>", html)
    html = html.replace("<table>", '<div class="table-scroll"><table>')
    html = html.replace("</table>", "</table></div>")
    return html, md.toc_tokens


def plain_text(md_text):
    """把 md 片段转成纯文本（用于 JSON-LD 的 answer 文本）"""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md_text)
    t = re.sub(r"[*`>#]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def jsonld_script(data):
    if not data:
        return ""
    return (
        '<script type="application/ld+json">\n'
        + json.dumps(data, ensure_ascii=False, indent=1)
        + "\n</script>"
    )


def crumbs(items):
    out = []
    for i, (label, url) in enumerate(items):
        if i:
            out.append("<span>›</span>")
        if url:
            out.append('<a href="%s">%s</a>' % (url, label))
        else:
            out.append(label)
    return "".join(out)


def nav_html(current, extra_active=None):
    active = {current}
    if extra_active:
        active.update(extra_active)
    out = []
    for it in SITE["nav"]:
        cls = []
        if it["url"] in active:
            cls.append("is-active")
        if it["url"] == "/contact/":
            cls.append("nav-cta")
        out.append(
            '<a class="%s" href="%s">%s</a>' % (" ".join(cls), it["url"], it["label"])
        )
    return "\n      ".join(out)


SALE_SIDE_BOX = (
    '<div class="side-box side-sale">\n'
    "      <h4>域名出售中</h4>\n"
    "      <p><strong>激光打标机.cn</strong> 精确匹配行业品类词，现接受报价，支持第三方担保交易。</p>\n"
    '      <a class="btn btn-accent" href="%s">发送询价邮件</a>\n'
    "    </div>" % mailto("域名报价咨询：激光打标机.cn")
)


def toc_list(tokens, limit=None):
    items = tokens[:limit] if limit else tokens
    return "".join(
        '<li><a href="#%s">%s</a></li>' % (t["id"], t["name"]) for t in items
    )


def side_html(toc_items=None, related=None):
    parts = [SALE_SIDE_BOX]
    if toc_items:
        parts.append(
            '<div class="side-box"><h4>本篇目录</h4><ul>%s</ul></div>' % toc_items
        )
    if related:
        lis = "".join('<li><a href="%s">%s</a></li>' % (u, l) for l, u in related)
        parts.append('<div class="side-box"><h4>相关阅读</h4><ul>%s</ul></div>' % lis)
    return "\n    ".join(parts)


def render_page(url, title, desc, keywords, content_html, jsonld_data=None, og_image="",
                extra_active=None):
    canonical = BASE + url
    og = ""
    if og_image:
        og = '<meta property="og:image" content="%s">' % og_image
    reps = {
        "{{TITLE}}": title,
        "{{DESC}}": desc,
        "{{KEYWORDS}}": keywords,
        "{{CANONICAL}}": canonical,
        "{{NAV}}": nav_html(url, extra_active),
        "{{CONTENT}}": content_html,
        "{{EMAIL}}": EMAIL,
        "{{PUNYCODE}}": PUNY,
        "{{YEAR}}": YEAR,
        "{{JSONLD}}": jsonld_script(jsonld_data),
        "{{OG_IMAGE_TAG}}": og,
        "{{EXTRA_HEAD}}": "",
    }
    html = tpl("layout.html")
    for k, v in reps.items():
        html = html.replace(k, v)
    return html, canonical


# --------------------------------------------------------------------------
# 内容页定义
# --------------------------------------------------------------------------

DOC_PAGES = [
    dict(
        url="/guide/",
        file="guide.md",
        crumb="激光打标机完全指南",
        related=[
            ("四种机型对比", "/types/"),
            ("应用场景与行业", "/applications/"),
            ("采购常见问题", "/faq/"),
            ("域名出售说明", "/domain/"),
        ],
    ),
    dict(
        url="/types/",
        file="types.md",
        crumb="四种机型对比",
        related=[
            ("激光打标机完全指南", "/guide/"),
            ("应用场景与行业", "/applications/"),
            ("采购常见问题", "/faq/"),
        ],
    ),
    dict(
        url="/applications/",
        file="applications.md",
        crumb="应用场景与行业",
        related=[
            ("四种机型对比", "/types/"),
            ("激光打标机完全指南", "/guide/"),
            ("采购常见问题", "/faq/"),
        ],
    ),
    dict(
        url="/faq/",
        file="faq.md",
        crumb="常见问题",
        faq=True,
        related=[
            ("激光打标机完全指南", "/guide/"),
            ("四种机型对比", "/types/"),
            ("采购咨询与域名报价", "/contact/"),
        ],
    ),
    dict(
        url="/about/",
        file="about.md",
        crumb="关于本站",
        related=[
            ("域名出售说明", "/domain/"),
            ("采购咨询与域名报价", "/contact/"),
            ("网站地图", "/sitemap/"),
        ],
    ),
]


def build_doc_page(p):
    meta, body = parse_doc(os.path.join(CONTENT, p["file"]))
    html_body, tokens = render_md(body)

    tail = (
        '<div class="callout sale">\n'
        '      <b class="title">本站域名正在出售</b>\n'
        "      <p><strong>激光打标机.cn</strong> 现公开出售，接受报价。"
        '详细信息见 <a href="/domain/">域名出售说明</a>，询价请发邮件至 '
        '<a href="%s">%s</a>。</p>\n'
        "    </div>" % (mailto("域名报价咨询：激光打标机.cn"), EMAIL)
    )

    content = tpl("content_page.html")
    content = content.replace(
        "{{CRUMBS}}", crumbs([("首页", "/"), (p["crumb"], None)])
    )
    content = content.replace("{{H1}}", meta.get("h1", meta.get("title", "")))
    content = content.replace("{{LEDE}}", meta.get("lede", ""))
    meta_line = '<span>更新日期：%s</span>' % meta.get("date", TODAY)
    if meta.get("readtime"):
        meta_line += "<span>约 %s 分钟读完</span>" % meta["readtime"]
    content = content.replace("{{META}}", meta_line)
    content = content.replace("{{BODY}}", html_body)
    content = content.replace("{{TAIL}}", tail)
    content = content.replace(
        "{{SIDE}}", side_html(toc_list(tokens), p.get("related"))
    )

    kg = [k.strip() for k in meta.get("keywords", "").split(",") if k.strip()]
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": meta.get("h1", meta.get("title", "")),
                "description": meta.get("desc", ""),
                "inLanguage": "zh-CN",
                "datePublished": meta.get("date", TODAY),
                "dateModified": meta.get("date", TODAY),
                "keywords": kg,
                "mainEntityOfPage": {"@type": "WebPage", "@id": BASE + p["url"]},
                "author": {"@type": "Organization", "name": SITE_NAME},
                "publisher": {
                    "@type": "Organization",
                    "name": SITE_NAME,
                    "url": BASE + "/",
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "首页", "item": BASE + "/"},
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": p["crumb"],
                        "item": BASE + p["url"],
                    },
                ],
            },
        ],
    }

    if p.get("faq"):
        _, fbody = parse_doc(os.path.join(CONTENT, "faq.md"))
        ld["@graph"].append(
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": it["q"],
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": plain_text(it["md"]),
                        },
                    }
                    for it in extract_faqs(fbody)
                ],
            }
        )

    return render_page(
        p["url"],
        meta.get("title", ""),
        meta.get("desc", ""),
        meta.get("keywords", ""),
        content,
        ld,
    )


# --------------------------------------------------------------------------
# 首页
# --------------------------------------------------------------------------

SCENES = [
    (
        "五金与汽车零部件",
        "光纤 1064nm",
        "序列号、批次号、二维码追溯打标。替代气动打标与电腐蚀，不接触工件、不产生应力，适合轴承、齿轮、紧固件、法兰、刹车盘等批量零件。",
    ),
    (
        "3C 电子与精密结构件",
        "紫外 355nm / 光纤",
        "外壳 Logo、连接器、充电头、按键等表面标记。薄壁与热敏塑料件优先紫外，避免熔边、起泡与变形。",
    ),
    (
        "医疗器械与耗材",
        "紫外 / 光纤",
        "器械唯一标识与批次追溯码。紫外冷加工对不锈钢、钛合金、高分子耗材的热影响小，边缘清晰不发黄。",
    ),
    (
        "食品饮料与医药包装",
        "CO₂ / 紫外",
        "瓶盖、包装膜、标签上的生产日期、批号与防伪码。无油墨接触，不易被擦除，符合追溯要求。",
    ),
    (
        "新能源电池与光伏",
        "光纤（含 MOPA）",
        "电池极片、模组壳体、光伏组件边框与接线盒的追溯码标记，要求高节拍与稳定读码率。",
    ),
    (
        "工具量具与五金饰件",
        "光纤 / 绿光",
        "深度雕刻、品牌 Logo、刻度与型号。金银铜等高反材料用绿光 532nm 提升吸收率，不锈钢彩色效果需 MOPA 光源。",
    ),
]

DOMAIN_VALUES = [
    (
        "域名即品类词",
        "「激光打标机」是行业检索量最集中的主干词。域名与它完全一致，在中文搜索结果中天然获得关键词高亮，用户在点击前就能确认站点主题。",
    ),
    (
        "口播与线下零成本",
        "电话、展会、报价单、名片上写「激光打标机点cn」，对方一次就记住。英文域名需要逐字拼读，还容易听错。",
    ),
    (
        "品类词的唯一性",
        "一个品类只能被一个主体持有。要么拿这个，要么退到加词变体，失去「域名即品类」的干净度。",
    ),
    (
        ".cn 强化本土身份",
        ".cn 是中国国家顶级域，由 CNNIC 管理，国内采购方对其信任度高于部分海外后缀，与「中文词 + 中国厂商」的身份表达一致。",
    ),
]


def build_home_scenes():
    out = []
    for title, tech, desc in SCENES:
        out.append(
            '<div class="card">\n'
            '        <span class="pill">%s</span>\n'
            "        <h3 style=\"margin-top:12px\">%s</h3>\n"
            "        <p>%s</p>\n"
            "      </div>" % (tech, title, desc)
        )
    return "\n      ".join(out)


def build_home_domain_block():
    items = "".join(
        '<div class="value-item">\n'
        '        <div class="v-ico">%02d</div>\n'
        "        <h3>%s</h3>\n"
        "        <p>%s</p>\n"
        "      </div>" % (i + 1, t, d)
        for i, (t, d) in enumerate(DOMAIN_VALUES)
    )
    return (
        '<section class="section">\n'
        '  <div class="wrap">\n'
        '    <div class="section-head">\n'
        '      <span class="eyebrow">关于本站域名</span>\n'
        "      <h2>激光打标机.cn —— 这个域名正在出售</h2>\n"
        "      <p>这不是一个凑出来的组合词。它完整覆盖了行业的核心品类词，而品类词级的中文域名在同一后缀下只能存在一个。"
        "如果您是激光设备厂商、代理商或行业平台方，可以直接把它变成客户的入口。</p>\n"
        "    </div>\n"
        '    <div class="value-grid">\n'
        "      %s\n"
        "    </div>\n"
        '    <div style="margin-top:26px;display:flex;gap:12px;flex-wrap:wrap">\n'
        '      <a class="btn btn-accent" href="/domain/">域名价值与交易流程</a>\n'
        '      <a class="btn btn-ghost" href="%s">直接邮件询价</a>\n'
        "    </div>\n"
        "  </div>\n"
        "</section>" % (items, mailto("域名报价咨询：激光打标机.cn"))
    )


def extract_faqs(text, limit=None):
    """从 faq.md 抽取 ### 问题 + 答案，返回 [{q, md, html}]"""
    chunks = re.split(r"\n###\s+", "\n" + text)
    items = []
    for c in chunks[1:]:
        lines = c.strip().split("\n")
        if not lines or not lines[0].strip():
            continue
        q = lines[0].strip()
        a_md = "\n".join(lines[1:]).strip()
        a_html, _ = render_md(a_md)
        items.append({"q": q, "md": a_md, "html": a_html})
    return items[:limit] if limit else items


def build_home_faq():
    _, body = parse_doc(os.path.join(CONTENT, "faq.md"))
    faqs = extract_faqs(body, 6)
    out = []
    for it in faqs:
        out.append(
            '<details class="faq-item">\n'
            "        <summary>%s</summary>\n"
            '        <div class="faq-answer">%s</div>\n'
            "      </details>" % (it["q"], it["html"])
        )
    return "\n      ".join(out)


def build_home():
    meta, body = parse_doc(os.path.join(CONTENT, "guide.md"))
    _, tokens = render_md(body)
    # 首页导览只取 h2 前 8 条
    guide_toc = tokens[:8]
    toc_items = []
    for i, t in enumerate(guide_toc):
        toc_items.append(
            '<li>\n'
            '      <span class="num">%02d</span>\n'
            '      <span class="body"><b>%s</b><span>点击进入指南对应章节</span></span>\n'
            "    </li>" % (i + 1, t["name"])
        )

    home_toc = "\n    ".join(toc_items)

    content = tpl("home.html")
    content = content.replace("{{HOME_TOC}}", home_toc)
    content = content.replace("{{HOME_SCENES}}", build_home_scenes())
    content = content.replace("{{HOME_DOMAIN_BLOCK}}", build_home_domain_block())
    content = content.replace("{{HOME_FAQ}}", build_home_faq())
    content = content.replace(
        "{{MAILTO_DOMAIN}}", mailto("域名报价咨询：激光打标机.cn")
    )
    content = content.replace("{{MAILTO_TECH}}", mailto("激光打标机选型咨询"))
    content = content.replace("{{PUNYCODE}}", PUNY)
    content = content.replace("{{EMAIL}}", EMAIL)

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": SITE_NAME,
                "alternateName": PUNY,
                "url": BASE + "/",
                "description": SITE["description"],
                "inLanguage": "zh-CN",
                "publisher": {"@type": "Organization", "name": SITE_NAME, "email": EMAIL},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "首页", "item": BASE + "/"}
                ],
            },
        ],
    }
    return render_page(
        "/",
        "激光打标机_选购指南与机型参数对比｜激光打标机.cn",
        "激光打标机选型指南：光纤/紫外/CO₂/绿光四类机型的波长、功率、幅面、适用材料与行业场景对比，含采购常见问题与安全合规要点。站点域名 激光打标机.cn 正在出售。",
        "激光打标机,激光打标机价格,光纤激光打标机,紫外激光打标机,CO2激光打标机,激光打标机参数,激光打标机厂家,激光打标机选型,激光打标机.cn",
        content,
        ld,
    )


# --------------------------------------------------------------------------
# 产品中心
# --------------------------------------------------------------------------

PRODUCT = dict(
    slug="fiber-laser-30w",
    name="30W 光纤激光打标机",
    model="参考机型 LM-F30",
    tech="光纤 · 1064nm",
    lede=(
        "金属打标的主力机型。1064nm 波长配合 30W 功率，覆盖五金汽配、3C 电子、医疗器械、"
        "新能源等绝大多数金属件与深色工程塑料的 Logo、序列号、批次码与二维码标记需求。"
    ),
    points=[
        "非接触加工：不打伤工件本体、无机械应力，薄壁件与精加工面同样适用",
        "免耗材：不用油墨与网版，标记永久，耐溶剂、耐高温、耐蒸汽消毒",
        "换幅面只换镜：110×110mm 标配，可换至 300×300mm，不用换整机",
    ],
    specs=[
        ("1064", "nm", "激光波长", "近红外，金属吸收率高"),
        ("30", "W", "额定输出功率", "常规金属标记主力功率段"),
        ("110×110", "mm", "标配标刻幅面", "可换 70 至 300mm 见方"),
        ("7000", "mm/s", "标刻线速上限", "实际受图形复杂度影响"),
        ("±0.003", "mm", "重复定位精度", "同点多次打标的一致性"),
        ("4", "类", "激光安全等级", "开放光路；加防护罩可评估 1 类"),
    ],
    highlights=[
        (
            "金属通用",
            "不锈钢、碳钢、合金钢、铝及阳极氧化铝、镀层件都能打。1064nm 对这些材料的吸收率高，"
            "打白、打黑、深雕都稳定。例外是高反贵金属（金、银）与纯铜，吸收率低，"
            "需要提高功率密度或改走绿光 532nm。",
        ),
        (
            "标记不可擦除",
            "激光改变的是材料表层本身，不是在上面附着一层东西。油污、溶剂、高温、蒸汽消毒都不会让字迹脱落——"
            "这正是医疗器械 UDI 与汽车零部件追溯码选择激光的原因。",
        ),
        (
            "配置决定能力边界",
            "功率决定「能不能打得动」，场镜决定「一次能打多大」，光源结构决定「能不能打彩色」。"
            "三者互相独立，采购时要分别确认，不要被一句「标配 30W」带过去。",
        ),
    ],
    std_config=[
        ("30W 光纤激光器主机", "含一体化机柜、光学系统与电气控制"),
        ("高速振镜扫描头", "决定标刻线速与定位能力"),
        ("110×110mm F-θ 场镜", "标准幅面，覆盖多数中小工件"),
        ("工业 PC + 打标软件", "支持条码生成、序列号递增与变量数据"),
        ("电动升降工作台", "换型时调整焦距，无需重做夹具"),
        ("红光预览定位", "用于对位与幅面校准"),
        ("启动按钮与脚踏开关", "支持手动单件与脚踏触发两种模式"),
        ("操作手册与随机工具", "含安全说明与日常维护指引"),
    ],
    opt_config=[
        ("旋转轴", "轴类、管件、瓶体等圆柱面的周向打标"),
        ("场镜更换", "70×70 / 150×150 / 200×200 / 300×300mm"),
        ("MOPA 光源", "彩色打标与脉宽可调工艺，适合高端外壳与装饰件"),
        ("封闭式防护罩", "带联锁，可整机按 1 类激光产品评估，适合开放产线"),
        ("飞行打标组件", "与流水线同步的在线打标，不停线"),
        ("视觉定位与读码校验", "自动对位，打标后即时复核读码结果"),
        ("定制夹具与上下料", "按工件形状与节拍要求设计"),
    ],
    flow=[
        ("说清需求", "材料牌号、打标内容、工件尺寸、需要的幅面、单件节拍、是否需要读码校验。信息越具体，方案越准。"),
        ("寄样打样", "用真实工件打样，不要只看厂商提供的效果图。要求留存样品与对应参数记录，作为后续验收的比对基准。"),
        ("效果与读码确认", "肉眼效果与读码率必须分开确认。二维码要按条码质量等级测试并明确合格线，例如连续 100 件读码率 100%。"),
        ("配置与报价确认", "锁定光源结构（调 Q 还是 MOPA）、场镜规格、选配件清单、交期与质保条款，一并写进技术协议。"),
        ("交付与验收", "设备就位、光路校准、软件安装与操作培训；连续运行 2–4 小时测试稳定性，并用标准量具复核定位精度。"),
    ],
    related=[
        ("产品中心", "/products/"),
        ("四类机型对比", "/types/"),
        ("激光打标机完全指南", "/guide/"),
        ("应用场景与行业", "/applications/"),
        ("采购咨询与域名报价", "/contact/"),
    ],
)

PRODUCT_TYPES = [
    ("光纤 1064nm", "光纤激光打标机", "金属打标主力：不锈钢、碳钢、铝、镀层件与部分工程塑料。", "/", "已上线", "live"),
    ("紫外 355nm", "紫外激光打标机", "冷加工、热影响极小：塑料、玻璃、PCB、医药包装、硅片。", None, "资料补充中", "pending"),
    ("CO₂ 10.6μm", "CO₂ 激光打标机", "有机物吸收强：木材、皮革、纸张纸板、亚克力、玻璃表面。", None, "资料补充中", "pending"),
    ("绿光 532nm", "绿光激光打标机", "高反金属与内部雕刻：金、银、铜，以及玻璃晶体内雕。", None, "资料补充中", "pending"),
]

PRODUCT_HOWTO = [
    ("先定波长", "看材料对哪个波长吸收率高。金属走 1064nm，塑料玻璃优先 355nm，木材皮革走 10.6μm，金银铜考虑 532nm。这一步定错，后面全白搭。"),
    ("再定功率", "看深度要求和节拍要求，不是越大越好。常规标记 20–30W 够用；要深雕或压缩节拍，才往 50W 以上走，功率上去价格和散热要求都会跟着上去。"),
    ("最后定幅面与配置", "单件最大尺寸决定场镜规格；产线形态决定要不要旋转轴、飞行打标、视觉定位或自动上下料。配置按工艺需要加，不为用不上的功能付钱。"),
]


def build_spec_strip():
    out = []
    for value, unit, label, note in PRODUCT["specs"]:
        out.append(
            '<div class="spec-card">\n'
            '        <span class="sc-label">%s</span>\n'
            '        <b class="sc-value">%s<i>%s</i></b>\n'
            '        <span class="sc-note">%s</span>\n'
            "      </div>" % (label, value, unit, note)
        )
    return "\n      ".join(out)


def build_ph_points():
    return "\n          ".join("<li>%s</li>" % p for p in PRODUCT["points"])


def build_highlights():
    out = []
    for i, (t, d) in enumerate(PRODUCT["highlights"]):
        out.append(
            '<div class="card">\n'
            '        <div class="card-ico" aria-hidden="true">%02d</div>\n'
            "        <h3>%s</h3>\n"
            "        <p>%s</p>\n"
            "      </div>" % (i + 1, t, d)
        )
    return "\n      ".join(out)


def build_config_list(items):
    return "\n        ".join(
        "<li><b>%s</b><span>%s</span></li>" % (t, d) for t, d in items
    )


def build_flow(items):
    return "\n      ".join("<li><b>%s</b>%s</li>" % (t, d) for t, d in items)


def build_product_body():
    """产品 md 拆两段：正文（渲染成 HTML）+ FAQ（渲染成折叠组件）"""
    meta, body = parse_doc(os.path.join(CONTENT, "product-fiber-30w.md"))
    marker = "\n## 常见问题"
    idx = body.find(marker)
    if idx == -1:
        main_md, faq_md = body, ""
    else:
        main_md, faq_md = body[:idx], body[idx + 1:]
    html_body, tokens = render_md(main_md)
    return meta, html_body, tokens, faq_md


def build_product_faq(faq_md):
    if not faq_md.strip():
        return ""
    rest = faq_md.split("\n", 1)[1] if "\n" in faq_md else ""
    out = []
    for it in extract_faqs(rest):
        out.append(
            '<details class="faq-item">\n'
            "        <summary>%s</summary>\n"
            '        <div class="faq-answer">%s</div>\n'
            "      </details>" % (it["q"], it["html"])
        )
    return "\n      ".join(out)


def build_product_page(url="/", extra_active=None):
    meta, body_html, tokens, faq_md = build_product_body()

    content = tpl("product_page.html")
    content = content.replace(
        "{{CRUMBS}}", crumbs([("产品中心", "/products/"), (PRODUCT["name"], None)])
    )
    content = content.replace("{{H1}}", PRODUCT["name"])
    content = content.replace("{{MODEL}}", PRODUCT["model"])
    content = content.replace("{{LEDE}}", PRODUCT["lede"])
    content = content.replace("{{POINTS}}", build_ph_points())
    content = content.replace("{{SPEC_CARDS}}", build_spec_strip())
    content = content.replace("{{HIGHLIGHTS}}", build_highlights())
    content = content.replace("{{BODY}}", body_html)
    content = content.replace(
        "{{SIDE}}", side_html(toc_list(tokens), PRODUCT["related"])
    )
    content = content.replace("{{STD_CONFIG}}", build_config_list(PRODUCT["std_config"]))
    content = content.replace("{{OPT_CONFIG}}", build_config_list(PRODUCT["opt_config"]))
    content = content.replace("{{FLOW}}", build_flow(PRODUCT["flow"]))
    content = content.replace("{{FAQ}}", build_product_faq(faq_md))
    content = content.replace(
        "{{MAILTO_QUOTE}}", mailto("激光打标机选型与打样咨询（30W 光纤机型）")
    )
    content = content.replace(
        "{{MAILTO_DOMAIN}}", mailto("域名报价咨询：激光打标机.cn")
    )
    content = content.replace("{{EMAIL}}", EMAIL)
    content = content.replace("{{PUNYCODE}}", PUNY)

    title = "30W 光纤激光打标机参数与选型（参考机型 LM-F30）｜激光打标机.cn"
    desc = (
        "30W 光纤激光打标机的光路原理、完整技术参数、六种打标效果、材料适配清单、"
        "标准配置与选配、打样验收要点与常见问题。1064nm 波长，金属打标主力机型。"
    )
    keywords = (
        "30W光纤激光打标机,光纤激光打标机,1064nm激光打标机,激光打标机参数,"
        "激光打标机配置,激光打标机选型,光纤打标机"
    )

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "name": PRODUCT["name"],
                "alternateName": PRODUCT["model"],
                "description": desc,
                "inLanguage": "zh-CN",
                "category": "工业设备 / 激光打标机",
                "url": BASE + url,
                "additionalProperty": [
                    {
                        "@type": "PropertyValue",
                        "name": label,
                        "value": "%s%s" % (value, unit),
                    }
                    for value, unit, label, _ in PRODUCT["specs"]
                ],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "产品中心", "item": BASE + "/products/"},
                    {"@type": "ListItem", "position": 2, "name": PRODUCT["name"], "item": BASE + url},
                ],
            },
        ],
    }
    return render_page(url, title, desc, keywords, content, ld, extra_active=extra_active)


def build_products():
    content = tpl("products.html")
    content = content.replace(
        "{{CRUMBS}}", crumbs([("首页", "/"), ("产品中心", None)])
    )
    content = content.replace("{{PRODUCTS}}", build_product_card())
    content = content.replace("{{TYPE_CARDS}}", build_type_cards())
    content = content.replace("{{HOWTO}}", build_flow(PRODUCT_HOWTO))
    content = content.replace("{{MAILTO_TECH}}", mailto("激光打标机选型咨询"))
    content = content.replace(
        "{{MAILTO_DOMAIN}}", mailto("域名报价咨询：激光打标机.cn")
    )
    content = content.replace("{{EMAIL}}", EMAIL)
    content = content.replace("{{PUNYCODE}}", PUNY)

    title = "产品中心：激光打标机机型与配置资料｜激光打标机.cn"
    desc = (
        "激光打标机产品中心：按机型整理设备资料，含完整技术参数、可实现效果、"
        "标准配置与选配清单、打样与验收要点，用于采购前的技术对照。"
    )
    keywords = (
        "激光打标机产品中心,激光打标机机型,光纤激光打标机,紫外激光打标机,"
        "CO2激光打标机,绿光激光打标机,激光打标机配置"
    )

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "name": "产品中心",
                "url": BASE + "/products/",
                "description": desc,
                "inLanguage": "zh-CN",
            },
            {
                "@type": "ItemList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": PRODUCT["name"],
                        "url": BASE + "/",
                    }
                ],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "首页", "item": BASE + "/"},
                    {"@type": "ListItem", "position": 2, "name": "产品中心", "item": BASE + "/products/"},
                ],
            },
        ],
    }
    return render_page("/products/", title, desc, keywords, content, ld)


def build_product_card():
    specs = "".join(
        "<li><span>%s</span><b>%s%s</b></li>" % (label, value, unit)
        for value, unit, label, _ in PRODUCT["specs"][:4]
    )
    return (
        '<a class="product-card" href="/">\n'
        '        <div class="pc-media">\n'
        '          <img src="/static/images/product-fiber-30w.svg" width="860" height="660" alt="30W 光纤激光打标机整机结构示意图：柜体、立柱、振镜扫描头、F-θ 场镜与工作台面">\n'
        "        </div>\n"
        '        <div class="pc-body">\n'
        '          <div class="pc-tags">\n'
        '            <span class="pill">%s</span>\n'
        '            <span class="type-status live">%s</span>\n'
        "          </div>\n"
        '          <h3>%s<span class="pc-model">%s</span></h3>\n'
        "          <p>%s</p>\n"
        '          <ul class="pc-specs">%s</ul>\n'
        '          <span class="pc-foot">查看产品详情 →</span>\n'
        "        </div>\n"
        "      </a>"
        % (
            PRODUCT["tech"],
            "当前产品",
            PRODUCT["name"],
            PRODUCT["model"],
            PRODUCT["lede"],
            specs,
        )
    )


def build_type_cards():
    out = []
    for tech, name, desc, link, status, cls in PRODUCT_TYPES:
        if link:
            head, foot = '<a class="card type-card" href="%s">' % link, "</a>"
        else:
            head, foot = '<div class="card type-card is-pending">', "</div>"
        out.append(
            head
            + "\n"
            + '        <span class="pill">%s</span>\n' % tech
            + '        <span class="type-status %s">%s</span>\n' % (cls, status)
            + "        <h3>%s</h3>\n" % name
            + "        <p>%s</p>\n" % desc
            + "      "
            + foot
        )
    return "\n      ".join(out)


# --------------------------------------------------------------------------
# 特殊页面
# --------------------------------------------------------------------------


def build_special(tpl_name, url, title, desc, keywords, crumb_label, ld_type="WebPage",
                  mailtos=None, extra_head=""):
    content = tpl(tpl_name)
    if tpl_name == "domain.html":
        content = content.replace(
            "{{CRUMBS}}", crumbs([("首页", "/"), (crumb_label, None)])
        )
        content = content.replace(
            "{{MAILTO_DOMAIN}}", mailto("域名报价咨询：激光打标机.cn")
        )
        content = content.replace("{{MAILTO_TECH}}", mailto("激光打标机选型咨询"))
    elif tpl_name == "contact.html":
        content = content.replace(
            "{{CRUMBS}}", crumbs([("首页", "/"), (crumb_label, None)])
        )
        content = content.replace(
            "{{MAILTO_DOMAIN}}", mailto("域名报价咨询：激光打标机.cn")
        )
        content = content.replace("{{MAILTO_TECH}}", mailto("激光打标机选型咨询"))
    content = content.replace("{{EMAIL}}", EMAIL)
    content = content.replace("{{PUNYCODE}}", PUNY)

    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": ld_type,
                "name": title,
                "url": BASE + url,
                "description": desc,
                "inLanguage": "zh-CN",
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "首页", "item": BASE + "/"},
                    {"@type": "ListItem", "position": 2, "name": crumb_label, "item": BASE + url},
                ],
            },
        ],
    }
    html, canonical = render_page(url, title, desc, keywords, content, ld)
    if extra_head:
        html = html.replace("</head>", extra_head + "\n</head>")
    return html


def build_sitemap(all_pages):
    groups = [
        ("主要页面", [p for p in all_pages if p.get("group") == "main"]),
        ("知识内容", [p for p in all_pages if p.get("group") == "knowledge"]),
        ("域名与联系", [p for p in all_pages if p.get("group") == "domain"]),
    ]
    parts = []
    for title, pages in groups:
        if not pages:
            continue
        lis = "".join(
            '<li><a href="%s">%s</a><span class="map-meta">%s</span></li>'
            % (p["url"], p["label"], p.get("date", ""))
            for p in pages
        )
        parts.append('<h2>%s</h2>\n<ul class="map-list">%s</ul>' % (title, lis))

    content = tpl("sitemap.html")
    content = content.replace("{{CRUMBS}}", crumbs([("首页", "/"), ("网站地图", None)]))
    content = content.replace("{{SITEMAP_CONTENT}}", "\n".join(parts))

    html, _ = render_page(
        "/sitemap/",
        "网站地图｜激光打标机.cn",
        "激光打标机.cn 全站页面索引：激光打标机完全指南、机型对比、应用场景、常见问题、域名出售说明与采购咨询入口。",
        "网站地图,激光打标机.cn",
        content,
        {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "网站地图",
            "url": BASE + "/sitemap/",
            "inLanguage": "zh-CN",
        },
    )
    return html


# --------------------------------------------------------------------------
# 静态资源 / 站点级文件
# --------------------------------------------------------------------------


def copy_static():
    """static/ → public/static/（保留 /static/ 前缀）

    static/_root/ 下的文件平铺到站点根 —— 搜索引擎归属验证文件
    （BingSiteAuth.xml / baidu_verify_xxx.html）放这里，会落到站点根目录，
    这是它们的硬性要求（必须能从 https://域名/文件名 直接访问）。
    """
    n = 0
    root_pass = os.path.join(STATIC, "_root")
    for dirpath, dirnames, filenames in os.walk(STATIC):
        for fn in filenames:
            if fn.startswith(".") and fn != ".nojekyll":
                continue
            src = os.path.join(dirpath, fn)
            if src.startswith(root_pass + os.sep):
                dst = os.path.join(PUBLIC, os.path.relpath(src, root_pass))
            else:
                dst = os.path.join(PUBLIC, "static", os.path.relpath(src, STATIC))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    return n


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#16406f"/>
<path d="M32 10 L32 30" stroke="#7fc4ff" stroke-width="4" stroke-linecap="round"/>
<path d="M18 34 L46 34" stroke="#d93b26" stroke-width="4" stroke-linecap="round"/>
<circle cx="32" cy="42" r="9" fill="none" stroke="#ffffff" stroke-width="3"/>
<circle cx="32" cy="42" r="2.6" fill="#d93b26"/>
</svg>
"""


def build_site_files():
    # CNAME（必须由构建脚本产出，否则 deploy 覆盖 tree 时会抹掉）
    write("CNAME", PUNY + "\n")
    write(".nojekyll", "")

    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "Sitemap: %s/sitemap.xml\n" % BASE
    )
    write("robots.txt", robots)


def build_xml_sitemap(all_pages):
    rows = []
    for p in all_pages:
        rows.append(
            "  <url>\n"
            "    <loc>%s%s</loc>\n"
            "    <lastmod>%s</lastmod>\n"
            "    <changefreq>%s</changefreq>\n"
            "    <priority>%s</priority>\n"
            "  </url>"
            % (BASE, p["url"], p.get("date", TODAY), p.get("changefreq", "monthly"), p.get("priority", "0.6"))
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(rows)
        + "\n</urlset>\n"
    )
    write("sitemap.xml", xml)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def main():
    n_pages = 0

    # 1) 首页 = 30W 光纤激光打标机产品详情页
    html, _ = build_product_page("/", extra_active=["/products/"])
    write("index.html", html)
    n_pages += 1

    # 2) 产品中心
    html, _ = build_products()
    write("products/index.html", html)
    n_pages += 1

    # 3) 原首页：完整迁到 /home/，内容一字不删
    html, _ = build_home()
    write("home/index.html", html)
    n_pages += 1

    # 4) 内容页
    for p in DOC_PAGES:
        html, _ = build_doc_page(p)
        write(p["url"].strip("/") + "/index.html", html)
        n_pages += 1

    # 5) 特殊页
    domain_html = build_special(
        "domain.html",
        "/domain/",
        "激光打标机.cn 域名出售说明｜中文域名的价值与交易流程",
        "激光打标机.cn 中文域名正在出售。本文说明该域名的价值来源、适合哪几类买家、交易流程与报价方式，并如实说明中文域名在搜索引擎中的实际作用边界。",
        "激光打标机.cn,中文域名出售,域名购买,激光打标机域名,行业域名,cn域名出售",
        "域名出售说明",
    )
    write("domain/index.html", domain_html)
    n_pages += 1

    contact_html = build_special(
        "contact.html",
        "/contact/",
        "采购咨询与域名报价｜激光打标机.cn",
        "激光打标机选型咨询与域名报价入口。提供可直接套用的邮件模板，把材料、打标内容、幅面、产能等关键信息一次说清。联系邮箱 mfujun@agent.qq.com。",
        "激光打标机采购咨询,激光打标机选型,域名报价,激光打标机.cn 联系方式",
        "采购咨询与域名报价",
    )
    write("contact/index.html", contact_html)
    n_pages += 1

    # 6) 站点地图页需要先有全量页面清单
    all_pages = [
        dict(url="/", label="30W 光纤激光打标机：参数、配置与选型（首页）", group="main", date=TODAY, priority="1.0", changefreq="weekly"),
        dict(url="/products/", label="产品中心：机型与配置资料", group="main", date=TODAY, priority="0.9", changefreq="monthly"),
        dict(url="/guide/", label="激光打标机完全指南：原理、类型、参数与选型", group="knowledge", date=TODAY, priority="0.9", changefreq="monthly"),
        dict(url="/types/", label="四种机型对比：光纤 / 紫外 / CO₂ / 绿光", group="knowledge", date=TODAY, priority="0.8", changefreq="monthly"),
        dict(url="/applications/", label="应用场景与行业：激光打标用在哪道工序", group="knowledge", date=TODAY, priority="0.8", changefreq="monthly"),
        dict(url="/faq/", label="采购常见问题：打样、验收、安全等级与维护成本", group="knowledge", date=TODAY, priority="0.7", changefreq="monthly"),
        dict(url="/domain/", label="域名出售说明：激光打标机.cn 的价值与交易流程", group="domain", date=TODAY, priority="0.9", changefreq="weekly"),
        dict(url="/contact/", label="采购咨询与域名报价", group="domain", date=TODAY, priority="0.8", changefreq="monthly"),
        dict(url="/home/", label="站点总览：知识内容与域名信息索引", group="domain", date=TODAY, priority="0.4", changefreq="monthly"),
        dict(url="/about/", label="关于本站", group="domain", date=TODAY, priority="0.4", changefreq="yearly"),
        dict(url="/sitemap/", label="网站地图", group="main", date=TODAY, priority="0.3", changefreq="monthly"),
    ]

    sm_html = build_sitemap(all_pages)
    write("sitemap/index.html", sm_html)
    n_pages += 1

    # 7) 404
    err = tpl("404.html")
    err_html, _ = render_page(
        "/404.html",
        "页面不存在｜激光打标机.cn",
        "您访问的页面不存在，可返回首页查看激光打标机选型指南与域名出售信息。",
        "404",
        err,
    )
    write("404.html", err_html)
    n_pages += 1

    # 8) 站点级文件与静态资源
    build_site_files()
    write("static/favicon.svg", FAVICON)
    n_static = copy_static()

    # 9) XML sitemap
    build_xml_sitemap(all_pages)

    print("构建完成 →", PUBLIC)
    print("  页面数：%d" % n_pages)
    print("  静态资源：%d 个文件" % n_static)
    print("  域名：%s (%s)" % (SITE["domain_cn"], PUNY))


if __name__ == "__main__":
    main()
