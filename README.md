# 激光打标机.cn

面向激光打标机品类的中文静态站点，同时是 **中文域名 `激光打标机.cn` 的出售落地页**。

- **线上地址**：<https://激光打标机.cn>（punycode：`xn--54q482buudoxam6z.cn`）
- **咨询邮箱**：mfujun@agent.qq.com

## 站点结构

| 路径 | 内容 |
| --- | --- |
| `/` | **产品详情页（首页）**：30W 光纤激光打标机参考机型，含参数速览、光路原理、打标效果、材料适配 |
| `/products/` | 产品中心列表页 |
| `/home/` | 站点总览首页（早期版本，完整保留） |
| `/guide/` | 主 SEO 长文：原理、类型、参数、选型、安全合规、验收维护 |
| `/types/` | 四种机型对比：光纤 / 紫外 / CO₂ / 绿光 |
| `/applications/` | 应用场景与行业工序 |
| `/faq/` | 采购常见问题（含 FAQPage 结构化数据） |
| `/domain/` | 域名出售说明：价值论证、买家画像、交易流程 |
| `/contact/` | 分级咨询入口与邮件模板 |
| `/about/` | 站点定位与免责声明 |
| `/sitemap/` | 网站地图（HTML 版） |

## 技术栈

无框架、无外部依赖的静态站点，自写 Python 构建器：

- `site.json` — 站点元信息与导航配置
- `build.py` — 构建脚本，内容（Markdown）→ `public/` 产物
- `check.py` — 产物自检：内链可达性、sitemap 双向一致性、表格包裹、HTML 标签闭合
- `templates/` — 页面模板（Python `str.format` 占位符，非 Jinja）
- `content/` — Markdown 正文
- `static/` — 样式与原创 SVG 插画

所有配图为**手写 SVG**，无第三方素材，无版权风险。

## 本地构建

```bash
python build.py     # 生成 public/
python check.py     # 产物自检，退出码非 0 表示有问题
python -m http.server 8899 --directory public   # 本地预览
```

## 部署

- `main` 分支 — 源码
- `gh-pages` 分支 — 构建产物（`public/`），由 GitHub Pages 托管
- 自定义域名 `激光打标机.cn`，DNS 托管于 Cloudflare

> 上游 `main` 只在本地构建校验通过后才推送，构建产物不提交到源码分支。

## 内容原则

- 技术数值标注来源与口径，不虚构参数
- 安全标准核实为现行版本（GB/T 7247.1-2024）
- 中文域名的价值论述只保留可验证的部分，不编造搜索引擎加权
- 页面上的产品型号为**参考机型**，非任一厂商在售型号
- 配图不得出现第三方品牌标识，也不得暗示产品获得他人或品牌认可

## 图片来源与许可

首页产品主图 `static/images/product-fiber-30w-photo.jpg|webp` 来源：

| 项目 | 内容 |
|---|---|
| 来源 | Pexels（照片 ID `38867222`） |
| 许可 | Pexels License — 免费商用、无需署名、可修改 |
| 处理 | 裁切为 3:2、轻微对比与锐度调整，输出 WebP（主）/ JPEG（兼容） |
| 限制 | 机身无可见第三方品牌标识；页面已标注"非本站机型实拍" |

> Pexels License 禁止将图片用于商标、商号、服务标记，以及暗示产品获得他人或品牌认可。
> 该图仅作"此类落地式工业激光设备的整机形态"示意，页面图注已如实说明。

技术示意图（`product-fiber-30w.svg` / `optical-path.svg` / `marking-effects.svg` / `material-matrix.svg`）均为本站手绘 SVG，无第三方版权依赖。
