#!/usr/bin/env python3
"""
月度项目监控看板 - 自动抓取 + 钉钉推送
- 抓取 GitHub Pages 上的看板 HTML
- 解析 <tr data-start data-end> 字段
- 判定：今天执行中 / 未来 3 天内开始
- 推送到钉钉机器人（关键词: 月度看板）
"""
import os
import re
import sys
import json
import time
import hmac
import base64
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, date, timedelta, timezone

# ─── 配置 ──────────────────────────────────────────────
DASHBOARD_URL = os.environ.get(
    "DASHBOARD_URL",
    "https://jayyangstore.github.io/audi-dashboard/"
)
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET", "")  # 加签密钥（可选）
DINGTALK_KEYWORD = os.environ.get("DINGTALK_KEYWORD", "月度看板")
# 北京时区
TZ = timezone(timedelta(hours=8))
# ──────────────────────────────────────────────────────


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Dashboard-Monitor/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8")


def parse_projects(html: str):
    """从 HTML 中解析所有项目行"""
    pattern = (
        r'<tr\s+data-type="([^"]+)"\s+data-city="([^"]*)"\s+data-cat="([^"]*)"'
        r'\s+data-start="([^"]*)"\s+data-end="([^"]*)">(.+?)</tr>'
    )
    rows = re.findall(pattern, html, re.S)
    projects = []
    for typ, city, cat, start, end, body in rows:
        code_m = re.search(r'<td class="td-code">([^<]+)</td>', body)
        name_m = re.search(r'<td class="td-name" title="([^"]+)">', body)
        leads_m = re.findall(r'<span class="prog-txt">(\d+)/(\d+)</span>', body)
        lead_done, lead_total = (int(leads_m[0][0]), int(leads_m[0][1])) if leads_m else (0, 0)
        order_done, order_total = (int(leads_m[1][0]), int(leads_m[1][1])) if len(leads_m) > 1 else (0, 0)
        projects.append({
            "type": typ,
            "city": city,
            "cat": cat,
            "start": start,
            "end": end,
            "code": code_m.group(1) if code_m else "",
            "name": name_m.group(1) if name_m else "",
            "lead_done": lead_done,
            "lead_total": lead_total,
            "order_done": order_done,
            "order_total": order_total,
        })
    return projects


def classify(projects, today: date):
    """把项目分成：今天执行 / 3天内开始 / 其他"""
    today_list, soon_list, future_list, ended_list = [], [], [], []
    for p in projects:
        if not p["start"] or not p["end"]:
            future_list.append(p)  # 没填日期的放未来
            continue
        s = datetime.strptime(p["start"], "%Y-%m-%d").date()
        e = datetime.strptime(p["end"], "%Y-%m-%d").date()
        if s <= today <= e:
            today_list.append(p)
        elif today < s <= today + timedelta(days=3):
            soon_list.append(p)
        elif today < s:
            future_list.append(p)
        else:
            ended_list.append(p)
    return today_list, soon_list, future_list, ended_list


def build_markdown(today: date, today_list, soon_list, future_list, ended_list):
    """构造钉钉 Markdown 消息"""
    weekday_cn = ["一", "二", "三", "四", "五", "六", "日"][today.weekday()]
    lines = [f"## 📅 {today} 周{weekday_cn} · 月度项目监控"]
    lines.append("")

    if today_list:
        lines.append(f"### 🔥 今日执行中（{len(today_list)} 项）")
        for p in today_list:
            lead_pct = (p["lead_done"] / p["lead_total"] * 100) if p["lead_total"] else 0
            lines.append(
                f"- **{p['name']}** `{p['code'] or '—'}`\n"
                f"  📍{p['city']} · {p['cat']} · {p['start']} ~ {p['end']}\n"
                f"  📊 潜客 {p['lead_done']}/{p['lead_total']} ({lead_pct:.0f}%) · "
                f"订单 {p['order_done']}/{p['order_total']}"
            )
        lines.append("")

    if soon_list:
        lines.append(f"### ⏰ 未来 3 天内开始（{len(soon_list)} 项）")
        for p in soon_list:
            d = (datetime.strptime(p["start"], "%Y-%m-%d").date() - today).days
            lines.append(
                f"- **{p['name']}** `{p['code'] or '—'}` — "
                f"**{d} 天后** ({p['start']} ~ {p['end']}) · {p['city']} · {p['cat']}"
            )
        lines.append("")

    if not today_list and not soon_list:
        lines.append("### ✅ 今日无执行项目，3 天内无新项目")
        lines.append("")

    # 简报
    total = len(today_list) + len(soon_list) + len(future_list) + len(ended_list)
    lines.append(
        f"---\n"
        f"📦 全月共 {total} 个项目 · 🔥今日 {len(today_list)} · "
        f"⏰3日内 {len(soon_list)} · 📋待开始 {len(future_list)} · "
        f"🏁已结束 {len(ended_list)}"
    )
    lines.append(f"🔗 [打开看板]({DASHBOARD_URL})")
    return "\n".join(lines)


def dingtalk_sign(secret: str) -> str:
    """加签"""
    timestamp = str(round(time.time() * 1000))
    secret_enc = secret.encode("utf-8")
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    hmac_code = hmac.new(secret_enc, string_to_sign, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return f"&timestamp={timestamp}&sign={sign}"


def dingtalk_send(text: str, webhook: str, secret: str = "", keyword: str = "月度看板") -> dict:
    """发送钉钉 Markdown 消息"""
    url = webhook
    if secret:
        url += dingtalk_sign(secret)
    # 钉钉自定义机器人要求消息内含关键词
    title = f"[{keyword}] {datetime.now(TZ).strftime('%m-%d %H:%M')}"
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": f"{title}\n\n{text}",
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    if not DINGTALK_WEBHOOK:
        print("❌ DINGTALK_WEBHOOK 未设置", file=sys.stderr)
        sys.exit(1)

    today = datetime.now(TZ).date()
    print(f"⏰ 当前时间: {datetime.now(TZ).strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"📅 判定日期: {today}")
    print(f"🌐 抓取: {DASHBOARD_URL}")

    try:
        html = fetch_html(DASHBOARD_URL)
        print(f"✅ HTML size: {len(html)} bytes")
    except Exception as e:
        print(f"❌ 抓取失败: {e}", file=sys.stderr)
        sys.exit(2)

    projects = parse_projects(html)
    print(f"📊 解析到 {len(projects)} 个项目")

    today_list, soon_list, future_list, ended_list = classify(projects, today)
    print(f"   🔥 今日执行: {len(today_list)}")
    print(f"   ⏰ 3天内开始: {len(soon_list)}")
    print(f"   📋 待开始: {len(future_list)}")
    print(f"   🏁 已结束: {len(ended_list)}")

    # 静默规则：今天无执行 + 3天内无开始 → 默认不推送（避免打扰）
    if not today_list and not soon_list:
        print("🔕 今日无提醒内容，跳过推送")
        # 但仍然可以发一条简短的"无活动"通知
        text = (
            f"📅 **{today}** · 月度项目监控\n\n"
            f"✅ 今日无执行中活动\n"
            f"✅ 未来 3 天内无新项目启动\n\n"
            f"🔗 [打开看板]({DASHBOARD_URL})"
        )
    else:
        text = build_markdown(today, today_list, soon_list, future_list, ended_list)

    print("\n" + "=" * 60)
    print(text)
    print("=" * 60 + "\n")

    try:
        result = dingtalk_send(text, DINGTALK_WEBHOOK, DINGTALK_SECRET, DINGTALK_KEYWORD)
        print(f"📤 钉钉返回: {result}")
        if result.get("errcode") != 0:
            sys.exit(3)
        print("✅ 推送成功")
    except Exception as e:
        print(f"❌ 推送失败: {e}", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
