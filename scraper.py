#!/usr/bin/env python3
"""
竞品监控抓取脚本 - 海康威视示例
会自动抓取多个页面内容并生成RSS Feed
"""

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
import datetime
import os
import sys
from urllib.parse import urljoin

# 要监控的页面列表
PAGES_TO_MONITOR = [
    {
        "name": "News",
        "url": "https://www.hikvision.com/en/news-center/",
        "type": "news"
    },
    {
        "name": "Blog",
        "url": "https://www.hikvision.com/en/blog/", 
        "type": "blog"
    },
    {
        "name": "Events",
        "url": "https://www.hikvision.com/en/events/",
        "type": "events"
    }
]

def fetch_page(url):
    """抓取网页内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"抓取失败 {url}: {e}")
        return None

def extract_hikvision_news(content, page_info):
    """解析海康威视新闻中心内容"""
    soup = BeautifulSoup(content, 'lxml')
    items = []

    # 根据海康威视网站结构进行调整
    # 这里使用通用选择器，您可能需要根据实际网站调整
    article_elements = soup.select('article') or soup.select('.news-item') or soup.select('.item')

    if not article_elements:
        # 尝试其他选择器
        article_elements = soup.select('[class*="news"]') or soup.select('[class*="article"]')

    for element in article_elements[:10]:  # 只取最新10条
        # 提取标题
        title_elem = element.select_one('h2, h3, .title, a') or element
        title = title_elem.text.strip() if title_elem else "No title"

        # 提取链接
        link_elem = element.select_one('a')
        if link_elem and link_elem.get('href'):
            link = urljoin(page_info['url'], link_elem.get('href'))
        else:
            link = page_info['url']

        # 提取摘要
        desc_elem = element.select_one('p, .description, .excerpt')
        description = desc_elem.text.strip() if desc_elem else title

        # 提取日期
        date_elem = element.select_one('time, .date, .publish-date')
        if date_elem:
            date_str = date_elem.text.strip()
        else:
            date_str = datetime.datetime.now().strftime('%Y-%m-%d')

        items.append({
            'title': f"[{page_info['name']}] {title}",
            'link': link,
            'description': description,
            'date': date_str
        })

    return items

def generate_feed(all_items, feed_path='feed.xml'):
    """生成RSS Feed文件"""
    fg = FeedGenerator()
    fg.title('Hikvision Competitor Monitor')
    fg.description('Automated monitoring of Hikvision news and updates')
    fg.link(href='https://github.com/yourusername/hikvision-monitor')
    fg.language('en')

    # 按时间排序（最新的在前面）
    sorted_items = sorted(all_items, key=lambda x: x['date'], reverse=True)

    for item in sorted_items[:50]:  # 最多50条记录
        fe = fg.add_entry()
        fe.title(item['title'])
        fe.link(href=item['link'])
        fe.description(item['description'])

        try:
            # 尝试解析日期
            fe.pubDate(datetime.datetime.strptime(item['date'], '%Y-%m-%d'))
        except:
            fe.pubDate(datetime.datetime.now())

    # 生成feed.xml
    fg.rss_file(feed_path, pretty=True)
    print(f"✓ 已生成RSS Feed: {feed_path} ({len(sorted_items)} 条记录)")

def main():
    """主函数"""
    print("开始抓取海康威视内容...")
    print(f"监控页面数: {len(PAGES_TO_MONITOR)}")

    all_items = []

    for page in PAGES_TO_MONITOR:
        print(f"\n正在抓取: {page['name']} ({page['url']})")

        content = fetch_page(page['url'])
        if content:
            items = extract_hikvision_news(content, page)
            print(f"  找到 {len(items)} 条内容")
            all_items.extend(items)
        else:
            print(f"  ✗ 抓取失败")

    print(f"\n总计抓取: {len(all_items)} 条内容")

    # 生成RSS Feed
    generate_feed(all_items)

    return len(all_items)

if __name__ == "__main__":
    item_count = main()
    sys.exit(0 if item_count > 0 else 1)
