import requests
import feedparser
import os
import time
import hashlib
from datetime import timezone
from dateutil import parser as dateparser
from bs4 import BeautifulSoup

# ── 配置区 ───────────────────────────────────────────

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
        "url": "https://www.3cx.com/blog/category/news/feed/",
    },
    {
        "label": "RingCentral Blog",
        "type": "RingCentral",
        "url": "https://www.ringcentral.com/blog/feed/",
    },
]

# 环境变量
FEISHU_APP_ID     = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
BITABLE_APP_TOKEN = os.environ.get("BITABLE_APP_TOKEN", "")
BITABLE_TABLE_ID  = os.environ.get("BITABLE_TABLE_ID", "")

# 模拟真实浏览器请求头
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*"
}

# ── 飞书 API 模块 ──────────────────────────────────────

def get_feishu_token():
    """获取飞书租户访问凭证"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10)
        resp_data = resp.json()
        if resp_data.get("code") != 0:
            print(f"获取 Token 失败: {resp_data.get('msg')}")
            return None
        return resp_data["tenant_access_token"]
    except Exception as e:
        print(f"Token 请求异常: {e}")
        return None

def get_existing_uids(token):
    """获取表中已存在的 UID，用于去重"""
    uids = set()
    page_token = None
    headers = {"Authorization": f"Bearer {token}"}
    
    while True:
        params = {"field_names": '["UID"]', "page_size": 100}
        if page_token:
            params["page_token"] = page_token
        
        try:
            url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records"
            resp = requests.get(url, headers=headers, params=params, timeout=15).json()
            
            if resp.get("code") != 0:
                print(f"读取现有记录失败 (Code {resp.get('code')}): {resp.get('msg')}")
                # 如果是权限问题，打印详细建议
                if resp.get("code") == 91403:
                    print("提示: 请检查机器人是否已被添加为该多维表格的'协作者'并赋予'编辑'权限。")
                break

            items = resp.get("data", {}).get("items", [])
            for record in items:
                uid = record.get("fields", {}).get("UID")
                if uid:
                    uids.add(uid)
            
            if not resp.get("data", {}).get("has_more"):
                break
            page_token = resp["data"]["page_token"]
        except Exception as e:
            print(f"获取 UID 异常: {e}")
            break
            
    return uids

def write_to_feishu(items, token):
    """批量写入新记录到飞书"""
    if not token:
        return

    existing_uids = get_existing_uids(token)
    new_items = [i for i in items if i["uid"] not in existing_uids]

    if not new_items:
        print("\n没有检测到新内容，跳过写入。")
        return

    print(f"\n准备写入 {len(new_items)} 条新记录...")
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
                "摘要":     item.get("summary", "")[:5000], # 飞书文本上限
                "来源":     item.get("source", ""),
                "作者":     item.get("author", ""),
                "Feed类型": item.get("type", ""),
                "UID":      item["uid"],
            }
        }
        if pub_ms:
            record["fields"]["发布时间"] = pub_ms
        records.append(record)

    # 飞书批量创建接口限额 500 条
    for i in range(0, len(records), 500):
        batch = records[i:i+500]
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/batch_create"
        resp = requests.post(url, headers=headers, json={"records": batch}, timeout=20).json()
        
        code = resp.get("code")
        if code == 0:
            print(f"成功写入 {len(batch)} 条数据。")
        else:
            print(f"写入失败 (Code {code}): {resp.get('msg')}")
            if code == 91403:
                print(">>> 错误排查: 请确保机器人在多维表格的'协作'按钮里已被添加为编辑者。")

# ── RSS 解析模块 ──────────────────────────────────────

def parse_feed(feed_config):
    """抓取并解析单个 RSS 订阅源"""
    try:
        # 1. 使用 requests 获取内容，解决直接用 feedparser 易被 403 的问题
        response = requests.get(feed_config["url"], headers=COMMON_HEADERS, timeout=15)
        
        if response.status_code != 200:
            print(f"  HTTP 错误 {response.status_code}: 无法访问该源")
            return []

        # 2. 交给 feedparser 解析字节流
        raw = feedparser.parse(response.content)

        if raw.bozo and not raw.entries:
            print(f"  XML 解析异常: {raw.bozo_exception}")
            return []

        items = []
        for entry in raw.entries:
            link = entry.get("link", "")
            if not link:
                continue
            
            uid = hashlib.md5(link.encode()).hexdigest()

            # 清理 HTML
            raw_summary = entry.get("summary", "") or entry.get("description", "")
            summary = BeautifulSoup(raw_summary, "html.parser").get_text(strip=True)

            # 来源归类
            source = ""
            if feed_config["type"] == "Google Alert":
                src = entry.get("source", {})
                if isinstance(src, dict):
                    source = src.get("title", "")
                if not source and entry.get("tags"):
                    source = entry["tags"][0].get("term", "")
            elif feed_config["type"] == "Reddit":
                source = "Reddit"
            else:
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

    except Exception as e:
        print(f"  解析异常: {e}")
        return []

# ── 主程序 ───────────────────────────────────────────

if __name__ == "__main__":
    print("=== 开始执行竞品监控抓取任务 ===")
    
    token = get_feishu_token()
    if not token:
        print("无法获取飞书 Token，请检查 APP_ID 和 APP_SECRET。")
        exit(1)

    all_items = []
    for feed in FEEDS:
        print(f"\n[读取] {feed['label']}...")
        items = parse_feed(feed)
        print(f"  成功获取 {len(items)} 条条目")
        all_items.extend(items)
        # 频率限制，避免抓取过快被封
        time.sleep(1.5)

    if all_items:
        write_to_feishu(all_items, token)
    else:
        print("\n未抓取到任何内容。")
        
    print("\n=== 任务结束 ===")
