#!/usr/bin/env bash
# e-Stat統計GISから全国の500mメッシュ統計をダウンロードする。
#   T001141 = 2020国勢調査 人口及び世帯 (JGD2011)
#   T001162 = 2021経済センサス活動調査 産業(大分類)別事業所数及び従業者数 (JGD2011)
# 1次メッシュ151区画 × 2統計。既存zipはスキップ(再実行安全)。
set -uo pipefail
CODES_JSON="$(dirname "$0")/mesh1_codes.json"
OUT=/mnt/data/kshoken/mesh500
mkdir -p "$OUT"
ok=0; skip=0; ng=0
for sid in T001141 T001162; do
  for code in $(python3 -c "import json;print(' '.join(json.load(open('$CODES_JSON'))))"); do
    f="$OUT/${sid}_${code}.zip"
    [ -s "$f" ] && { skip=$((skip+1)); continue; }
    curl -sL "https://www.e-stat.go.jp/gis/statmap-search/data?statsId=${sid}&code=${code}&downloadType=2" -o "$f" --max-time 120
    if file "$f" | grep -q "Zip archive"; then ok=$((ok+1)); else rm -f "$f"; ng=$((ng+1)); fi
    sleep 1   # e-Statへの礼儀
  done
done
echo "取得${ok} スキップ${skip} 失敗${ng}"
