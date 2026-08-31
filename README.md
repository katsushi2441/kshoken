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

## データ更新
1. `scripts/download_mesh.sh` … e-Statから151区画×2統計のzipを /mnt/data/kshoken/mesh500 へ
2. `python3 scripts/load_mesh.py` … PostGISへ投入(メッシュ矩形はコードから計算・境界ファイル不要)

出典: 政府統計の総合窓口(e-Stat) 地域メッシュ統計を加工して作成。
