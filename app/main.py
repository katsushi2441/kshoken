"""Kurage 商圏分析 (kshoken) — 住所→到達圏→500mメッシュ集計の1画面サービス。

構成:
  ジオコーディング: 国土地理院 AddressSearch API(無料・キー不要)
  到達圏          : Valhalla(:18359, isochrone) / 未稼働時は徒歩80m/分の円で代替(結果に明記)
  集計            : PostGIS(kshoken-db)。メッシュとポリゴンの交差面積で按分
データ出典: 2020年国勢調査 500mメッシュ(e-Stat T001141) / 2021年経済センサス活動調査(T001162)
"""
import json, os, time
import psycopg2, requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

PORT = int(os.environ.get("KSHOKEN_PORT", "18355"))
VALHALLA = os.environ.get("KSHOKEN_VALHALLA", "http://127.0.0.1:18359")
DB = dict(host="127.0.0.1", port=55432, dbname="kshoken", user="postgres",
          password=os.environ.get("KSHOKEN_DB_PASS", "kshoken_local"))
GSI = "https://msearch.gsi.go.jp/address-search/AddressSearch"
WALK_M_PER_MIN = 80          # 不動産表示規約の徒歩80m/分
DRIVE_M_PER_MIN = 400        # 円代替時の車の目安(市街地24km/h)

app = FastAPI(title="Kurage 商圏分析")
_rate = {}

def limited(ip, per_min=20):
    now = time.time()
    q = [t for t in _rate.get(ip, []) if now - t < 60]
    if len(q) >= per_min:
        return True
    q.append(now); _rate[ip] = q
    return False

def geocode(q: str):
    r = requests.get(GSI, params={"q": q}, timeout=10,
                     headers={"User-Agent": "kshoken/1.0 (kurage.exbridge.jp)"})
    r.raise_for_status()
    items = r.json()
    if not items:
        return None
    it = items[0]
    lon, lat = it["geometry"]["coordinates"]
    return {"lat": lat, "lon": lon, "label": it.get("properties", {}).get("title", q)}

def isochrone(lat, lon, minutes, mode):
    """Valhallaの到達圏GeoJSONポリゴン。落ちていればNone(呼び出し側で円代替)。"""
    try:
        body = {"locations": [{"lat": lat, "lon": lon}],
                "costing": "pedestrian" if mode == "walk" else "auto",
                "contours": [{"time": minutes}], "polygons": True}
        r = requests.post(f"{VALHALLA}/isochrone", json=body, timeout=25)
        r.raise_for_status()
        feats = r.json().get("features", [])
        if feats:
            return feats[0]["geometry"]
    except Exception:
        pass
    return None

def aggregate(poly_geojson: str):
    """交差面積按分でメッシュ統計を合算し、表示用のメッシュ一覧も返す。"""
    q = """
WITH a AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) g)
SELECT
 (SELECT json_build_object(
   'pop', round(sum(m.pop_total*w)), 'pop_m', round(sum(m.pop_m*w)), 'pop_f', round(sum(m.pop_f*w)),
   'age0_14', round(sum(m.age0_14*w)), 'age15_64', round(sum(m.age15_64*w)),
   'age65', round(sum(m.age65*w)), 'age75', round(sum(m.age75*w)),
   'households', round(sum(m.households*w)), 'mesh_count', count(*))
  FROM (SELECT m.*, ST_Area(ST_Intersection(m.geom,a.g))/NULLIF(ST_Area(m.geom),0) w
        FROM mesh_pop m, a WHERE ST_Intersects(m.geom, a.g)) m),
 (SELECT json_build_object('offices', round(sum(b.offices*w)), 'employees', round(sum(b.employees*w)))
  FROM (SELECT b.*, ST_Area(ST_Intersection(b.geom,a.g))/NULLIF(ST_Area(b.geom),0) w
        FROM mesh_biz b, a WHERE ST_Intersects(b.geom, a.g)) b),
 (SELECT json_agg(json_build_object('c', ST_AsGeoJSON(geom,5)::json, 'p', pop_total))
  FROM (SELECT m.geom, m.pop_total FROM mesh_pop m, a
        WHERE ST_Intersects(m.geom,a.g) ORDER BY m.pop_total DESC NULLS LAST LIMIT 400) t)
"""
    with psycopg2.connect(**DB) as con, con.cursor() as cur:
        cur.execute(q, (poly_geojson,))
        pop, biz, meshes = cur.fetchone()
    return pop or {}, biz or {}, meshes or []

@app.get("/api/analyze")
def analyze(request: Request, q: str, minutes: int = 10, mode: str = "walk"):
    ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    if limited(ip):
        raise HTTPException(429, "アクセスが多すぎます。1分ほど待ってください")
    minutes = max(1, min(minutes, 30))
    if mode not in ("walk", "drive"):
        mode = "walk"
    g = geocode(q)
    if not g:
        raise HTTPException(404, "住所が見つかりません。市区町村から入れてください")
    iso = isochrone(g["lat"], g["lon"], minutes, mode)
    method = f"到達圏（Valhalla・道路網ベース）"
    poly = iso
    if poly is None:
        radius = minutes * (WALK_M_PER_MIN if mode == "walk" else DRIVE_M_PER_MIN)
        with psycopg2.connect(**DB) as con, con.cursor() as cur:
            cur.execute("SELECT ST_AsGeoJSON(ST_Buffer(ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s)::geometry,5)",
                        (g["lon"], g["lat"], radius))
            poly = json.loads(cur.fetchone()[0])
        method = f"半径{radius}mの円（到達圏エンジン準備中のため簡易計算）"
    pop, biz, meshes = aggregate(json.dumps(poly))
    return JSONResponse({
        "query": q, "point": g, "minutes": minutes, "mode": mode, "method": method,
        "population": pop, "business": biz, "isochrone": poly, "meshes": meshes,
        "source": "2020年国勢調査・2021年経済センサス活動調査（e-Stat 500mメッシュ）を当社加工",
    })

@app.get("/healthz")
def healthz():
    try:
        with psycopg2.connect(**DB) as con, con.cursor() as cur:
            cur.execute("SELECT count(*) FROM mesh_pop"); n = cur.fetchone()[0]
        return {"status": "ok", "mesh_pop": n,
                "valhalla": bool(isochrone(35.17, 136.88, 3, "walk"))}
    except Exception as e:
        return JSONResponse({"status": "ng", "error": str(e)[:200]}, status_code=500)

@app.get("/", response_class=HTMLResponse)
def index():
    return open(os.path.join(os.path.dirname(__file__), "index.html"), encoding="utf-8").read()
