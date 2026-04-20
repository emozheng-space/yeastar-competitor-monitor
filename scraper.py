import requests
import feedparser
import os
import time
import hashlib
import random
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
        "url": "https://www.3cx.com/feed/",
    },
    {
        "label": "RingCentral Blog",
        "type": "RingCentral",
        "url": "https://www.ringcentral.com/blog/feed/",
    },
]

# 环境变量读取 (GitHub Secrets 或本地环境)
FEISHU_APP_ID     = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
BITABLE_APP_TOKEN = os.environ.get("BITABLE_APP_TOKEN", "")
BITABLE_TABLE_ID  = os.environ.get("BITABLE_TABLE_ID", "")

# ── 飞书 API 模块 ──────────────────────────────────────

def get_feishu_token():
    """获取飞书租户访问凭证 (Tenant Access Token)"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = requests.post(url, json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10)
        resp_data = resp.json()
        if resp_data.get("code") != 0:
            print(f"❌ 获取 Token 失败: {resp_data.get('msg')}")
            return None
        return resp_data["tenant_access_token"]
    except Exception as e:
        print(f"❌ Token 请求异常: {e}")
        return None

def get_existing_uids(token):
    """获取表中已存在的 UID，用于增量抓取去重"""
    uids = set()
    page_token = None
    headers = {"Authorization": f"Bearer {token}"}
    while True:
        params = {"field_names": '["UID"]', "page_size": 100}
        if page_token: params["page_token"] = page_token
        try:
            url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records"
            resp = requests.get(url, headers=headers, params=params, timeout=15).json()
            if resp.get("code") != 0:
                if resp.get("code") == 91403:
                    print("⚠️ 权限错误(91403): 请在飞书多维表格中，点击'协作'并添加机器人为'编辑'权限。")
                break
            for record in resp.get("data", {}).get("items", []):
                uid = record.get("fields", {}).get("UID")
                if uid: uids.add(uid)
            if not resp.get("data", {}).get("has_more"): break
            page_token = resp["data"]["page_token"]
        except Exception as e:
            print(f"⚠️ 获取现有记录异常: {e}")
            break
    return uids

def write_to_feishu(items, token):
    """将抓取到的新内容写入飞书多维表格"""
    if not token or not items: return
    
    existing_uids = get_existing_uids(token)
    new_items = [i for i in items if i["uid"] not in existing_uids]
    
    if not new_items:
        print("\n✨ 暂无新条目需要同步。")
        return

    print(f"\n🚀 准备同步 {len(new_items)} 条新动态...")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    records = []
    for item in new_items:
        pub_ms = None
        if item.get("pub_date"):
            try:
                dt = dateparser.parse(item["pub_date"])
                if dt:
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                    pub_ms = int(dt.timestamp() * 1000)
            except: pass

        records.append({
            "fields": {
                "标题":     item["title"],
                "链接":     {"text": item["link"], "link": item["link"]},
                "摘要":     item.get("summary", "")[:5000], # 截断防止超过字段上限
                "来源":     item.get("source", ""),
                "作者":     item.get("author", ""),
                "Feed类型": item.get("type", ""),
                "UID":      item["uid"],
                "发布时间": pub_ms
            }
        })

    # 分批写入，每批最多 500 条（飞书 API 限制）
    for i in range(0, len(records), 500):
        batch = records[i:i+500]
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/batch_create"
        resp = requests.post(url, headers=headers, json={"records": batch}, timeout=20).json()
        if resp.get("code") == 0:
            print(f"✅ 成功同步 {len(batch)} 条记录。")
        else:
            print(f"❌ 同步失败: {resp.get('msg')}")

# ── RSS 解析模块 ──────────────────────────────────────

def fetch_content_safely(url):
    """
    深度模拟浏览器访问，处理 403 风险。
    包含：随机延迟、完善的 Headers、Cloudflare 诊断。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/",
        "DNT": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Upgrade-Insecure-Requests": "1"
    }
    
    try:
        # 增加随机延迟，避免被识别为固定频率机器人
        time.sleep(random.uniform(1.5, 3.5))
        resp = requests.get(url, headers=headers, timeout=30)
        
        if resp.status_code == 403:
            # 诊断是否为 Cloudflare 拦截
            if "cloudflare" in resp.text.lower() or "checking your browser" in resp.text.lower():
                print("  [诊断] 受到 Cloudflare WAF 强力拦截。建议使用 Google Alerts 监控该站点的关键词。")
            return None, 403
            
        return resp.content, resp.status_code
    except Exception as e:
        print(f"  [网络错误] {e}")
        return None, 999

def parse_feed(feed_config):
    """解析 RSS 逻辑，包含对 HTML 误解析的拦截"""
    content, status = fetch_content_safely(feed_config["url"])
    
    if status != 200 or not content:
        print(f"  抓取失败 (HTTP {status})")
        return []

    # 预检：如果返回的内容以 <html 开头，说明是网页而非 RSS
    # 这是处理 RingCentral 和 3CX 解析报错的关键：拦截非 XML 内容
    try:
        snippet = content.strip()[:20].decode('utf-8', errors='ignore').lower()
        if "<html" in snippet or "<!doctype" in snippet:
            print(f"  [跳过] 返回的是 HTML 网页验证页，而非 RSS 数据。")
            return []
    except:
        pass

    # 使用 feedparser 解析字节内容
    raw = feedparser.parse(content)
    
    # 彻底检查 XML 是否格式正确
    if raw.bozo and not raw.entries:
        print(f"  [格式错误] XML 无法解析: {raw.bozo_exception}")
        return []

    items = []
    for entry in raw.entries:
        link = entry.get("link", "")
        if not link: continue
        
        # 根据 URL 生成唯一 ID
        uid = hashlib.md5(link.encode()).hexdigest()
        
        # 清理摘要中的 HTML 标签
        raw_summary = entry.get("summary", "") or entry.get("description", "")
        summary = BeautifulSoup(raw_summary, "html.parser").get_text(strip=True)

        # 来源归一化处理
        source = feed_config["label"]
        if feed_config["type"] == "Google Alert":
            src = entry.get("source", {})
            if isinstance(src, dict): source = src.get("title", "")
            if not source and entry.get("tags"): source = entry["tags"][0].get("term", "")
        elif feed_config["type"] == "Reddit":
            source = "Reddit"

        items.append({
            "title":    entry.get("title", "(无标题)"),
            "link":     link,
            "summary":  summary,
            "source":   source,
            "author":   entry.get("author", ""),
            "pub_date": entry.get("published") or entry.get("updated", ""),
            "type":     feed_config["type"],
            "uid":      uid,
        })
    return items

# ── 主程序 ───────────────────────────────────────────

if __name__ == "__main__":
    print(">>> 竞品监控任务启动...")
    
    # 1. 认证
    token = get_feishu_token()
    if not token:
        print("❌ 脚本终止: 飞书身份验证失败，请检查环境变量。")
        exit(1)

    # 2. 循环抓取
    all_found = []
    for feed in FEEDS:
        print(f"\n[读取] {feed['label']} ...")
        results = parse_feed(feed)
        print(f"  - 成功获取 {len(results)} 条新动态")
        all_found.extend(results)

    # 3. 写入
    write_to_feishu(all_found, token)
    
    print("\n>>> 任务全部执行完毕。")
