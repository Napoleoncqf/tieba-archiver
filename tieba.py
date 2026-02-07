from DrissionPage import ChromiumPage, ChromiumOptions
import os
import time
import random
import re

# --- 配置 ---
BASE_DIR = r'C:\Users\admin\Downloads'
MAX_PAGES = 100


def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def get_clean_img_name(url):
    base_name = url.split('/')[-1]
    return base_name.split('?')[0]


def extract_post_id(url):
    """从贴吧链接中提取帖子 ID"""
    match = re.search(r'/p/(\d+)', url)
    return match.group(1) if match else None


def backup_thread(page, post_id):
    assets_dir = os.path.join(BASE_DIR, 'assets')
    os.makedirs(assets_dir, exist_ok=True)

    # 设置页面加载策略和超时
    page.set.load_mode.eager()  # 不等待所有资源加载完毕
    page.set.timeouts(base=15, page_load=30)

    # 先访问帖子获取标题
    page.get(f'https://tieba.baidu.com/p/{post_id}?see_lz=1')
    while "安全验证" in page.title or "百度安全" in page.html:
        print("   [!!!] 遇到验证码！请手动处理！")
        time.sleep(1)

    raw_title = page.title.replace('_百度贴吧', '').strip()
    clean_title = clean_filename(raw_title) if raw_title else str(post_id)

    md_file_path = os.path.join(BASE_DIR, f"{clean_title}.md")

    # 断点续传
    if os.path.exists(md_file_path) and os.path.getsize(md_file_path) > 100:
        print(f"--- [跳过] {clean_title} 已存在 ---")
        return

    print(f"\n--- 正在归档: {clean_title} ---")
    full_markdown = f"# {clean_title}\n\n> 原始链接: https://tieba.baidu.com/p/{post_id}?see_lz=1\n\n---\n"

    from bs4 import BeautifulSoup
    import json

    # 指纹集合，用于去重
    seen_post_ids = set()
    actual_total_pages = 999

    for pn in range(1, MAX_PAGES + 1):
        if pn > actual_total_pages:
            print(f"   已达到最后一页 ({actual_total_pages})，停止。")
            break

        url = f'https://tieba.baidu.com/p/{post_id}?see_lz=1&pn={pn}'
        print(f"   读取第 {pn} 页...", end="", flush=True)

        try:
            page.get(url)

            # 验证码检测
            if "安全验证" in page.title or "百度安全" in page.html:
                print("\n   [!!!] 遇到验证码！请手动处理！")
                while "安全验证" in page.title or "百度安全" in page.html:
                    time.sleep(1)

            html_content = page.html
            soup = BeautifulSoup(html_content, 'html.parser')

            # 检测总页数 (只在第1页做)
            if pn == 1:
                try:
                    total_span = soup.find('span', class_='tP')
                    if total_span:
                        actual_total_pages = int(total_span.get_text())
                        print(f" [识别到共 {actual_total_pages} 页] ", end="", flush=True)
                    else:
                        next_page = soup.find('a', text='下一页')
                        if not next_page:
                            actual_total_pages = 1
                            print(f" [识别到共 1 页] ", end="", flush=True)
                except:
                    pass

            # 解析楼层
            post_list = soup.find_all('div', class_='l_post')
            if not post_list:
                print("   [x] 本页无内容。")
                break

            page_has_new_content = False

            for post in post_list:
                # 防重复检测
                try:
                    data_field = post.get('data-field')
                    if data_field:
                        info_json = json.loads(data_field)
                        pid = info_json['content']['post_id']

                        if pid in seen_post_ids:
                            continue

                        seen_post_ids.add(pid)
                        page_has_new_content = True
                        floor_num = f"{info_json['content']['post_no']}楼"
                    else:
                        pid = str(hash(post.text[:20]))
                        if pid in seen_post_ids:
                            continue
                        seen_post_ids.add(pid)
                        page_has_new_content = True
                        floor_num = "未知楼层"
                except:
                    floor_num = "未知"
                    page_has_new_content = True

                # 解析内容
                md_content = ""
                try:
                    content_div = post.find('div', class_='d_post_content')
                    if content_div:
                        for child in content_div.children:
                            if child.name == 'br':
                                md_content += "\n"
                            elif child.name == 'img':
                                src = child.get('src')
                                if src and ('imgsa.baidu.com' in src or 'tiebapic.baidu.com' in src):
                                    filename = get_clean_img_name(src)
                                    save_path = os.path.join(assets_dir, filename)

                                    if not os.path.exists(save_path):
                                        hd_url = f"https://imgsrc.baidu.com/forum/pic/item/{filename}"
                                        try:
                                            page.download(hd_url, assets_dir, filename)
                                            time.sleep(0.05)
                                        except:
                                            pass

                                    md_content += f"\n![{filename}](assets/{filename})\n\n"
                            elif child.string:
                                md_content += f"{child.string.strip()}\n\n"
                except:
                    pass

                if md_content.strip():
                    full_markdown += f"### {floor_num}\n\n{md_content}\n---\n"

            # 循环终止判定
            if not page_has_new_content:
                print("   [!] 检测到页面内容重复，任务结束。")
                break

            print(f" √")
            time.sleep(random.uniform(2, 3))

        except Exception as e:
            print(f" [x] 出错: {e}")
            break

    with open(md_file_path, 'w', encoding='utf-8') as f:
        f.write(full_markdown)
    print(f"   [√] {clean_title}.md 完成")


def connect_browser():
    """连接浏览器，支持接管模式和独立模式"""
    print("\n[启动模式]")
    print("  1. 接管模式 — 连接已打开的 Chrome (需先启动带调试端口的 Chrome)")
    print("  2. 独立模式 — 自动启动新浏览器实例")

    choice = input("\n请选择 [1/2] (默认 1): ").strip()

    if choice == '2':
        print("正在启动浏览器...")
        try:
            co = ChromiumOptions()
            co.set_argument('--no-proxy-server')
            page = ChromiumPage(co)
            print(">>> 浏览器启动成功！")
            return page
        except Exception as e:
            print(f"\n[!!!] 启动失败: {e}")
            return None
    else:
        print("正在接管浏览器...")
        co = ChromiumOptions()
        co.set_address('127.0.0.1:9222')
        co.set_argument('--no-proxy-server')
        try:
            page = ChromiumPage(co)
            print(f">>> 接管成功！当前页面: {page.title}")
            return page
        except:
            print("\n[!!!] 接管失败，请确认已运行:")
            print("      chrome.exe --remote-debugging-port=9222")
            return None


def main():
    os.makedirs(BASE_DIR, exist_ok=True)

    page = connect_browser()
    if not page:
        return

    print("\n" + "=" * 50)
    print("  贴吧帖子归档工具 | Tieba Archiver")
    print("  输入帖子链接开始下载，输入 q 退出")
    print("=" * 50)

    while True:
        user_input = input("\n>>> ").strip()

        if user_input.lower() == 'q':
            print("再见。")
            break

        if not user_input:
            continue

        post_id = extract_post_id(user_input)
        if not post_id:
            if user_input.isdigit():
                post_id = user_input
            else:
                print("[!] 无效输入。支持格式:")
                print("    - https://tieba.baidu.com/p/1234567890")
                print("    - 1234567890 (纯数字帖子 ID)")
                continue

        backup_thread(page, post_id)

    print("全部任务结束。")


if __name__ == '__main__':
    main()
