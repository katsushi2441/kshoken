#!/usr/bin/env python3
"""Kurage 商圏分析 (kshoken) の MCP サーバー。

Claude Code / Claude Desktop に登録すると、AIエージェントが商圏の質問に
実データ(国勢調査500mメッシュ×道路網到達圏)で答えられるようになります。

  claude mcp add kshoken -- python3 /path/to/kshoken_mcp.py

設計の線(kaimom/kdbagentと同じ): 読み取り専用。分析APIを呼ぶだけで、
データを書き換える口はありません。標準ライブラリのみで動きます。

環境変数:
  KSHOKEN_API ... 本体のURL(既定 http://127.0.0.1:18355)
"""
import json
import os
import sys
import urllib.parse
import urllib.request

VERSION = "1.0.0"
API = os.environ.get("KSHOKEN_API", "http://127.0.0.1:18355").rstrip("/")

TOOLS = [
    {
        "name": "kshoken_analyze",
        "description": (
            "住所・駅名から商圏分析を行う。道路網ベースの到達圏(徒歩/車1〜30分)に対して、"
            "2020年国勢調査500mメッシュの人口・男女・年齢構成(0-14/15-64/65+/75+)・世帯数と、"
            "2021年経済センサスの事業所数・従業者数を面積按分で返す。"
            "出店判断・営業テリトリー・立地比較の一次調査に使う。数値は推計値。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":   {"type": "string", "description": "住所・駅名・施設名(例: 名古屋市瑞穂区内浜町)"},
                "minutes": {"type": "integer", "description": "到達時間(分)。1〜30。既定10", "minimum": 1, "maximum": 30},
                "mode":    {"type": "string", "enum": ["walk", "drive"], "description": "walk=徒歩 / drive=車。既定walk"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kshoken_health",
        "description": "商圏分析サービスの稼働状態と収録メッシュ数を返す。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def http_get(path, timeout=60):
    req = urllib.request.Request(API + path, headers={"User-Agent": f"kshoken-mcp/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def tool_analyze(args):
    q = str(args.get("query", "")).strip()
    if not q:
        return False, {"ok": False, "error": "query(住所)を指定してください"}
    minutes = max(1, min(int(args.get("minutes", 10) or 10), 30))
    mode = args.get("mode", "walk")
    mode = mode if mode in ("walk", "drive") else "walk"
    d = http_get(f"/api/analyze?q={urllib.parse.quote(q)}&minutes={minutes}&mode={mode}", timeout=90)
    # 地図描画用の重いジオメトリ(メッシュ・等時圏ポリゴン)は落とし、数値だけ返す
    return True, {
        "ok": True,
        "query": q,
        "resolved": d.get("point", {}).get("label"),
        "mode": "徒歩" if mode == "walk" else "車",
        "minutes": minutes,
        "method": d.get("method"),
        "population": d.get("population"),
        "business": d.get("business"),
        "source": d.get("source"),
        "note": "数値は500mメッシュを到達圏との交差面積で按分した推計値。秘匿された小規模メッシュは含まれない場合がある",
    }


def tool_health(_args):
    d = http_get("/healthz", timeout=15)
    return True, {"ok": d.get("status") == "ok", **d}


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def result(rid, r):
    send({"jsonrpc": "2.0", "id": rid, "result": r})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        rid = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}
        if rid is None and method.startswith("notifications/"):
            continue
        if method == "initialize":
            result(rid, {
                "protocolVersion": str(params.get("protocolVersion", "2024-11-05")),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "kshoken", "version": VERSION},
                "instructions": (
                    "商圏分析の窓口です。住所を渡すと徒歩/車N分圏の人口・年齢構成・世帯数・"
                    "事業所数を国勢調査500mメッシュから返します。読み取り専用。"
                    "答えに使うときは「どの地点の・徒歩/車何分圏か」と、推計値である旨を添えてください。"
                ),
            })
        elif method == "ping":
            result(rid, {})
        elif method == "tools/list":
            result(rid, {"tools": TOOLS})
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            try:
                if name == "kshoken_analyze":
                    ok, payload = tool_analyze(args)
                elif name == "kshoken_health":
                    ok, payload = tool_health(args)
                else:
                    ok, payload = False, {"ok": False, "error": f"使えないツールです: {name}"}
            except Exception as e:
                ok, payload = False, {"ok": False, "error": str(e)[:300]}
            result(rid, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                         "isError": not ok})
        elif rid is not None:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}})


if __name__ == "__main__":
    main()
