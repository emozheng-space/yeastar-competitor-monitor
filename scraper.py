import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
import hashlib

PAGES = [
    {
        "label": "3CX Blog",
        "url": "https://www.3cx.com/blog/",
        "item_selector": "article",        # CSS selector for each post card
        "title_selector": "h2, h3",        # within the article
        "link_selector": "a",              # first <a> in the article
    },
]

def scrape_page(page):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FeedBot/1.0)"}
    resp = requests.get(page["url"], headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for article in soup.select(page["item_selector"])[:20]:
        title_el = article.select_one(page["title_selector"])
        link_el = article.select_one(page["link_selector"])
        if not title_el or not link_el:
            continue

        title = title_el.get_text(strip=True)
        href = link_el.get("href", "")
        if href.startswith("/"):
            from urllib.parse import urlparse
            base = urlparse(page["url"])
            href = f"{base.scheme}://{base.netloc}{href}"

        uid = hashlib.md5(href.encode()).hexdigest()
        items.append({"title": title, "link": href, "uid": uid})

    return items


def build_feed(all_items):
    fg = FeedGenerator()
    fg.id("https://emozheng-space.github.io/yeastar-competitor-monitor/feed.xml")
    fg.title("Competitor Monitor — 3CX")
    fg.link(href="https://www.3cx.com/blog/", rel="alternate")
    fg.link(href="https://emozheng-space.github.io/yeastar-competitor-monitor/feed.xml", rel="self")
    fg.description("Auto-generated feed tracking 3CX blog updates")
    fg.language("en")

    for item in all_items:
        fe = fg.add_entry()
        fe.id(item["uid"])
        fe.title(item["title"])
        fe.link(href=item["link"])
        fe.published(datetime.now(timezone.utc))
        fe.updated(datetime.now(timezone.utc))

    fg.rss_file("feed.xml", pretty=True)
    print(f"feed.xml written with {len(all_items)} items")


if __name__ == "__main__":
    all_items = []
    for page in PAGES:
        print(f"Scraping: {page['url']}")
        try:
            items = scrape_page(page)
            print(f"  Found {len(items)} items")
            all_items.extend(items)
        except Exception as e:
            print(f"  ERROR: {e}")

    build_feed(all_items)
