#!/usr/bin/env python3
"""
竞品监控抓取脚本 - Yeastar示例
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
        "url": "https://www.yeastar.com/category/news/",
        "type": "news"
    },
    {
        "name": "Blog",
        "url": "https://www.yeastar.com/category/blog/", 
        "type": "blog"
    },
    {
        "name": "Events",
        "url": "https://www.yeastar.com/events/",
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

def extract_yeastar_news(content, page_info):
    """解析Yeastar新闻中心内容"""
    soup = BeautifulSoup(content, 'lxml')
    items = []

    # 根据Yeastar网站结构进行调整
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
    fg.title('Yeastar Competitor Monitor')
    fg.description('Automated monitoring of Yeastar news and updates')
    fg.link(href='https://github.com/emozheng-space/yeastar-competitor-monitor')
    fg.language('en')

    # 按时间排序（最新的在前面）
    sorted_items = sorted(all_items, key=lambda x: x['date'], reverse=True)

    for item in sorted_items[:50]:  # 最多50条记录
        fe = fg.add_entry()
        fe.title(item['title'])
        fe.link(href=item['link'])
        fe.description(item['description'])
def generate_feed(items, filename='feed.xml'):
    """生成RSS Feed"""
    fg = FeedGenerator()
    fg.title('竞品监控 - RSS Feed')
    fg.description('自动抓取的竞品最新动态')
    fg.link(href='https://github.com/yourusername/yeastar-monitor')
    fg.language('zh-cn')
    
    # 设置Feed的发布时间（有时区）
    fg.lastBuildDate(datetime.datetime.now(datetime.timezone.utc))
    
    for item in items:
        fe = fg.add_entry()
        fe.title(item['title'])
        fe.link(href=item['url'])
        fe.description(item['summary'])
        
        # 处理日期 - 必须添加时区信息
        try:
            # 尝试解析日期字符串
            date_str = item.get('date', '')
            
            # 处理不同的日期格式
            date_formats = ['%Y-%m-%d', '%Y/%m/%d', '%d %b %Y', '%B %d, %Y']
            date_obj = None
            
            for fmt in date_formats:
                try:
                    date_obj = datetime.datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            
            # 如果没有解析成功，使用当前时间
            if date_obj is None:
                date_obj = datetime.datetime.now()
            
            # 添加时区信息（亚洲/上海时区）
            date_obj = date_obj.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
            fe.pubDate(date_obj)
            
        except Exception as e:
            print(f"日期处理错误: {e}, 使用当前时间")
            # 使用当前时间并添加时区
            fe.pubDate(datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))))
    
    # 生成RSS文件
    fg.rss_file(filename)
    print(f"✓ 已生成RSS Feed: {filename} ({len(items)} 条记录)")

def main():
    """主函数"""
    print("开始抓取Yeastar内容...")
    print(f"监控页面数: {len(PAGES_TO_MONITOR)}")

    all_items = []

    for page in PAGES_TO_MONITOR:
        print(f"\n正在抓取: {page['name']} ({page['url']})")

        content = fetch_page(page['url'])
        if content:
            items = extract_yeastar_news(content, page)
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
