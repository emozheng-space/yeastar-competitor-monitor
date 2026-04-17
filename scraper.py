import requests
import feedparser
import os
import time
import hashlib
from datetime import timezone
from dateutil import parser as dateparser
from bs4 import BeautifulSoup

# ── RSS Feed 配置 ──────────────────────────────────────
FEEDS = [
    {
        "label": "Google Alert - Feed 1",
        "type": "Google Alert",
        "url": "https://www.google.com/alerts/feeds/12333559685857933967/102254494684165410",
    },
    {
        "label": "Google Alert - Feed 2",
        "type": "Google Alert",
        "url": "https://www.google.com/alerts/feeds/12333559685857933967/882652012999967103",
    },
    {
        "label": "Google Alert - Feed 3",
        "type": "Google Alert",
        "url": "https://www.google.com/alerts/feeds/12333559685857933967/591145244202703894",
    },
    {
        "label": "Google Alert - Feed 4",
        "type": "Google Alert",
        "url": "https://www.google.com/alerts/feeds/12333559685857933967/9289355794411533840",
    },
    {
        "label": "Reddit - NetSapiens / Metaswitch / Crexendo",
        "type": "Reddit",
        "url": "https://www.reddit.com/search/.rss?q=NetSapiens+OR+Metaswitch+OR+Crexendo&type=posts&sort=new",
    },
    {
        "label": "3CX Official Blog",
        "type": "3CX",
        "url": "https://www.3cx.com/feed/",
    },
    {
        "label": "RingCentral Blog",
        "type": "RingCentral",
        "url": "https://www.ringcentral.com/blog/feed/",
    },
]

# ── 飞书配置 ───────────────────────────────────────────
FEISHU_APP_ID     = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]
BITABLE_APP_TOKEN = os.environ["BITABLE_APP_TOKEN"]
BITABLE_TABLE_ID  = os.environ["BITABLE_TABLE_ID"]


# ── 飞书 API ───────────────────────────────────────────

def get_feishu_token():
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    return resp.json()["tenant_access_token"]


def get_existing_uids(token):
    uids = set()
    page_token = None
    headers = {"Authorization": f"Bearer {token}"}
    while True:
        params = {"field_names": '["UID"]', "page_size": 100}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records",
            headers=headers, params=params,
        ).json()
        for record in resp.get("data", {}).get("items", []):
            uid = record.get("fields", {}).get("UID")
            if uid:
                uids.add(uid)
        if not resp.get("data", {}).get("has_more"):
            break
        page_token = resp["data"]["page_token"]
    return uids


def write_to_feishu(items, token):
    existing_uids = get_existing_uids(token)
    new_items = [i for i in items if i["uid"] not in existing_uids]

    if not new_items:
        print("没有新内容，跳过写入")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    records = []
    for item in new_items:
        pub_ms = None
        if item.get("pub_date"):
            try:
                dt = dateparser.parse(item["pub_date"])
                if dt:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    pub_ms = int(dt.timestamp() * 1000)
            except Exception:
                pass

        record = {
            "fields": {
                "标题":     item["title"],
                "链接":     {"text": item["link"], "link": item["link"]},
                "摘要":     item.get("summary", "")[:5000],
                "来源":     item.get("source", ""),
                "作者":     item.get("author", ""),
                "Feed类型": item.get("type", ""),
                "UID":      item["uid"],
            }
        }
        if pub_ms:
            record["fields"]["发布时间"] = pub_ms

        records.append(record)

    for i in range(0, len(records), 500):
        batch = records[i:i+500]
        resp = requests.post(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/batch_create",
            headers=headers,
            json={"records": batch},
        ).json()
        print(f"写入 {len(batch)} 条，code: {resp.get('code')} msg: {resp.get('msg')}")


# ── RSS 解析 ───────────────────────────────────────────

def parse_feed(feed_config):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; FeedBot/1.0)",
    }
    raw = feedparser.parse(feed_config["url"], request_headers=headers)

    if raw.bozo and not raw.entries:
        print(f"  解析失败: {raw.bozo_exception}")
        return []

    items = []
    for entry in raw.entries:
        link = entry.get("link", "")
        uid  = hashlib.md5(link.encode()).hexdigest()

        # 清理摘要里的 HTML 标签
        raw_summary = entry.get("summary", "")
        summary = BeautifulSoup(raw_summary, "html.parser").get_text(strip=True)

        # 来源处理
        source = ""
        if feed_config["type"] == "Google Alert":
            src = entry.get("source", {})
            if hasattr(src, "get"):
                source = src.get("title", "")
            if not source and entry.get("tags"):
                source = entry["tags"][0].get("term", "")
        elif feed_config["type"] == "Reddit":
            source = "Reddit"
        else:
            # 3CX、RingCentral 等直接用 label 作为来源
            source = feed_config["label"]

        pub_date = entry.get("published") or entry.get("updated", "")

        items.append({
            "title":    entry.get("title", "(无标题)"),
            "link":     link,
            "summary":  summary,
            "source":   source,
            "author":   entry.get("author", ""),
            "pub_date": pub_date,
            "type":     feed_config["type"],
            "label":    feed_config["label"],
            "uid":      uid,
        })

    return items


# ── 主程序 ─────────────────────────────────────────────

if __name__ == "__main__":
    token = get_feishu_token()
    all_items = []

    for feed in FEEDS:
        print(f"\n读取 Feed: {feed['label']}")
        try:
            items = parse_feed(feed)
            print(f"  解析到 {len(items)} 条")
            all_items.extend(items)
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(1)

    write_to_feishu(all_items, token)
