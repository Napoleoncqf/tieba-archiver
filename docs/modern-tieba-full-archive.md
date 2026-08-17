# 贴吧新版完整归档实现记录（主楼层、楼中楼、图片）

本文记录 2026-08-17 对贴吧帖子 `9834811133` 的一次真实归档适配。目标不是只保存楼主文字，而是保存：

- 所有仍可访问的主楼层；
- 每个主楼层下的楼中楼；
- 主楼层和楼中楼中的正文图片；
- 可离线打开、可搜索的静态 HTML；
- 可复核的数量、资源清单和 SHA-256。

真实存档内容没有提交到仓库。本文只保留通用实现、选择器、接口和校验方法。

## 1. 旧实现为什么失效

旧版脚本依赖服务端渲染页面中的两个选择器：

```text
.l_post
.d_post_content
```

当前 PC 帖子页已改为 Vue 动态渲染。主回复使用 `.pb-comment-item`，正文、图片和楼中楼分布在不同的子树中；页面还会虚拟化并无限滚动。因此，直接读取一次 `page.html` 会得到不完整数据，旧选择器则会得到空列表。

图片遗漏的另一个具体原因是：上传图片不在 `.pb-rich-text` 内，而是它的同级 `.image-card-wrapper`。只在正文节点中查找 `<img>` 会得到 0 张上传图片。

## 2. 当前页面的关键结构

主回复根节点：

```css
.pb-comment-item[data-id]
```

字段映射：

| 字段 | 选择器或来源 |
| --- | --- |
| post id | `.pb-comment-item` 的 `data-id` |
| 作者 | `.head-name` |
| 正文 | `.comment-content > .pb-rich-text` |
| 上传图片 | `.image-card-wrapper img` 的 `data-src`，回退到 `src` |
| 楼层、日期、地区 | `.comment-desc-left > span` |
| 已预览楼中楼 | `.lzl-wrapper > .pb-lzl-item` |
| 尚未展开数量 | `.show-more-lzl` 文本中的数字 |

图片必须从主回复根节点向下查找，而不是限定在 `.pb-rich-text`：

```python
images = []
for img in post.select('.image-card-wrapper img'):
    url = img.get('data-src') or img.get('src')
    if url:
        images.append(url)
```

楼中楼总数可在未点击展开按钮时估算：

```text
当前预览节点数 + “展开 N 条回复”中的 N
```

该数字后续必须用独立楼中楼页面的实际条数复核，不能单独作为最终结果。

## 3. 主楼层抓取：分页加重叠滚动

帖子页支持 `?pn=N`，但每页内容由前端动态加载，并可能继续无限加载后续页。可靠做法是：

1. 导航到 `https://tieba.baidu.com/p/{tid}?pn={pn}`；
2. 等待首屏渲染；
3. 反复采集当前 DOM 中的 `.pb-comment-item`；
4. 每次向下滚动约 1800–2400 px，短暂等待；
5. 用 `post_id` 去重；
6. 下一批从前一批覆盖到的页码之前开始，制造重叠区间；
7. 到页面出现“已加载全部评论”为止。

不能用楼层号判断是否连续，因为删帖后楼层号会永久缺号。批次是否完整应通过以下条件判断：

- 相邻批次的楼层范围有重叠，或下一批的首个 post id 紧接上一页；
- post id 去重后不再增长；
- 尾部出现“已加载全部评论”；
- 最后一条记录与当前页面尾楼一致。

建议每批立即写入一个 JSON 文件。长帖抓取可能遇到页面超时或安全验证，分批落盘可避免从头重来。

## 4. 楼中楼：使用独立分页页面

逐个点击“展开更多回复”速度慢，也容易触发虚拟 DOM 更新。贴吧仍保留一个适合读取的独立楼中楼页面：

```text
https://tieba.baidu.com/p/comment?tid={thread_id}&pid={post_id}&pn={page}
```

该页面通常每页最多 10 条。关键选择器：

| 字段 | 选择器或来源 |
| --- | --- |
| 楼中楼节点 | `.lzl_single_post` |
| sub post id、显示名 | 节点的 `data-field` JSON：`spid`、`showname` |
| 正文 | `.lzl_content_main` |
| 日期 | `.lzl_time` |
| 正文图片 | `.lzl_content_main img` |
| 页数 | `.lzl_li_pager a` 的 `href="#N"` |

示意代码：

```python
field = json.loads(item.get('data-field', '{}'))
record = {
    'id': str(field.get('spid', '')),
    'parent_id': parent_post_id,
    'parent_floor': parent_floor,
    'author': field.get('showname', '').strip(),
    'content': item.select_one('.lzl_content_main').get_text(' ', strip=True),
    'date': item.select_one('.lzl_time').get_text(strip=True),
}
```

对每个父楼层记录 `expected` 和 `actual`。只有两者相等时才把该批标记为成功。安全验证出现时要停止当前批次、保留精确断点，等待人工完成验证后续传；不要尝试绕过验证。

## 5. 图片本地化

贴吧图片 URL 可能带有临时 `tbpicau` 查询参数，不能把远程 URL 当作长期存档。处理流程：

1. 汇总主回复与楼中楼中的图片 URL；
2. 规范化 `//` 和 `http://`；
3. 以完整 URL 的 SHA-256 前 20 位作为本地文件名；
4. 根据 URL 后缀或响应 `Content-Type` 决定扩展名；
5. 下载时携带普通浏览器 `User-Agent` 和帖子页 `Referer`；
6. 为每个 URL 写入 `manifest.json`，记录本地文件、字节数和状态；
7. 将 HTML 中的 `src` 改为相对本地路径；
8. 对失败项单独重试，直到清单中 `failed == 0`。

使用 URL 哈希而不是原文件名可以避免不同图片同名，也便于缓存和断点续传。

## 6. HTML 组织方式

推荐把每个主楼层渲染为 `<article>`，把楼中楼放在对应父楼层内部：

```html
<article class="post" id="floor-123">
  <header>第 123 楼 · 作者 · 日期 · 地区</header>
  <div class="content">主回复正文与本地图片</div>
  <section class="lzl">
    <div class="lzl-item">楼中楼回复</div>
  </section>
</article>
```

把楼层、作者、主回复和楼中楼文字合并到 `data-search`，即可用少量前端 JavaScript 实现离线搜索。CSS、JavaScript 内联，图片使用相对路径，最终产物只需要一个 HTML 和一个资源目录。

## 7. 三层校验

### 记录层

- 主回复按 `post_id` 去重；
- 楼中楼按 `spid` 去重；
- 每个父楼层 `actual == expected`；
- HTML 中 `<article class="post">` 数量等于主楼层数量；
- HTML 中 `<div class="lzl-item">` 数量等于楼中楼数量。

### 资源层

- `manifest.json` 中失败数为 0；
- HTML 所有本地图片引用都存在；
- 唯一本地引用数等于资源清单数；
- 不保留会过期的远程图片依赖。

### 文件层

- UTF-8 标题和正文可正常读取；
- 首楼、尾楼和抽样楼中楼存在；
- 记录 HTML 的字节数和 SHA-256；
- 使用 `tools/verify_archive.py` 做自动校验。

## 8. 本次验证结果

帖子 `9834811133` 的可访问数据最终为：

- 主楼层 566 条（含首楼）；
- 楼中楼 1249 条；
- 共 1815 条可访问记录；
- 220 个唯一图片资源，全部本地化；
- HTML 中 0 个缺失本地图片引用。

页面显示“1840 条回复”，而独立页面实际可访问回复为 1814 条（不含首楼），相差 26 条。因为所有可见父楼层的 `expected` 与 `actual` 均已逐一对账，这 26 条更可能是已删除、审核隐藏或当前账号不可见的回复，不应伪造占位正文。

## 9. 仍需注意

- 贴吧前端结构和反爬策略可能继续变化；选择器必须集中管理并允许快速替换。
- 动态页面抓取要依赖真实浏览器，纯 HTTP 请求可能返回安全验证。
- 长帖必须限速、分批和可续传。
- 真实存档常含个人叙述、头像、图片和地理信息，不应默认提交到公共 GitHub 仓库。

