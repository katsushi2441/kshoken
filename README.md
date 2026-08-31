# Kurage 商圏分析 (kshoken)

住所を入れると、徒歩/車N分の到達圏に対して 2020年国勢調査500mメッシュの
人口・年齢構成・世帯数と、2021年経済センサスの事業所数・従業者数を出す1画面サービス。

- 公開: https://kurage.exbridge.jp/kshoken.php/ (php/kshoken.php を heteml に配置)
- 本体: FastAPI :18355 (systemd user unit `kshoken.service`)
- 到達圏: Valhalla (docker `kshoken-valhalla` :18359, OSM japan-latest)
  未稼働時は徒歩80m/分の円で代替し、結果にその旨を明記する
- DB: PostGIS (docker `kshoken-db` 127.0.0.1:55432)
- ジオコーディング: 国土地理院 AddressSearch API
- 地図: MapLibre + 国土地理院タイル

## 設置（VPS・所要1〜2時間＋データ取得）

1. docker で PostGIS と Valhalla を起動
   - `docker run -d --name kshoken-db -e POSTGRES_PASSWORD=<任意> -e POSTGRES_DB=kshoken -v <データ置き場>/pgdata:/var/lib/postgresql/data -p 127.0.0.1:55432:5432 postgis/postgis:16-3.4`
   - OSM日本全図( geofabrik の japan-latest.osm.pbf )を <データ置き場> に置き、
     `docker run -d --name kshoken-valhalla -v <データ置き場>:/custom_files -e serve_tiles=True -p 127.0.0.1:18359:8002 ghcr.io/valhalla/valhalla-scripted:latest`
     （初回はタイル構築に数十分〜数時間。/status が返れば完了）
2. `python3 -m venv .venv && .venv/bin/pip install fastapi "uvicorn[standard]" psycopg2-binary requests`
3. データ投入: 下の「データ更新」を実行（e-Statから自動取得・全国で計約40分）
4. `systemd/kshoken.service` を user unit として登録して起動（ポート既定18355）
5. 公開する場合は `php/kshoken.php` をPHPサーバーに置き、BACKEND を自環境に変更

要件: docker / Python 3.10+ / メモリ4GB以上(Valhallaタイル構築時はさらに余裕を)。

## データ更新
1. `scripts/download_mesh.sh` … e-Statから151区画×2統計のzipを /mnt/data/kshoken/mesh500 へ
2. `python3 scripts/load_mesh.py` … PostGISへ投入(メッシュ矩形はコードから計算・境界ファイル不要)

出典: 政府統計の総合窓口(e-Stat) 地域メッシュ統計を加工して作成。
