#!/usr/bin/env python3
"""e-Statの500mメッシュzip群をPostGISへ投入する。

依存を増やさないため、DBへは `docker exec -i kshoken-db psql` のCOPYで流す。
メッシュ矩形はコードから計算する(app/meshcode.py)ので境界ファイル不要。
秘匿値(数値でないセル)はNULL。再実行時はテーブルを作り直す(冪等)。

使い方: python3 scripts/load_mesh.py [pop|biz|all]
"""
import glob, io, os, subprocess, sys, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
from meshcode import mesh500_bounds

SRC = '/mnt/data/kshoken/mesh500'
PSQL = ['docker', 'exec', '-i', 'kshoken-db', 'psql', '-U', 'postgres', '-d', 'kshoken', '-q']

def sql(q):
    r = subprocess.run(PSQL + ['-c', q], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:500])
    return r.stdout

def num(s):
    s = s.strip()
    return s if s.isdigit() else ''   # COPYのCSVで空=NULL

def rows_from_zip(path):
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.endswith('.txt')][0]
        text = z.read(name).decode('cp932', 'replace')
    lines = text.split('\r\n')
    header = lines[0].split(',')
    return header, lines[2:]   # 2行目は日本語見出し

def load_pop():
    sql("""DROP TABLE IF EXISTS mesh_pop;
CREATE TABLE mesh_pop(
  key_code text PRIMARY KEY, pop_total int, pop_m int, pop_f int,
  age0_14 int, age15_64 int, age65 int, age75 int,
  households int, geom geometry(Polygon,4326));""")
    n = 0
    for zp in sorted(glob.glob(f'{SRC}/T001141_*.zip')):
        _, lines = rows_from_zip(zp)
        buf = io.StringIO()
        for ln in lines:
            c = ln.split(',')
            if len(c) < 40 or not c[0].strip().isdigit() or len(c[0].strip()) != 9:
                continue
            code = c[0].strip()
            la0, lo0, la1, lo1 = mesh500_bounds(code)
            wkt = f"POLYGON(({lo0} {la0},{lo1} {la0},{lo1} {la1},{lo0} {la1},{lo0} {la0}))"
            buf.write(','.join([code, num(c[4]), num(c[5]), num(c[6]), num(c[7]),
                                num(c[13]), num(c[22]), num(c[25]), num(c[37]),
                                f'"SRID=4326;{wkt}"']) + '\n')
            n += 1
        r = subprocess.run(PSQL + ['-c',
            "COPY mesh_pop(key_code,pop_total,pop_m,pop_f,age0_14,age15_64,age65,age75,households,geom) FROM STDIN CSV"],
            input=buf.getvalue(), capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f'{zp}: {r.stderr[:300]}')
        print(f'  {os.path.basename(zp)}: 累計{n}行', flush=True)
    sql('CREATE INDEX ON mesh_pop USING GIST(geom);')
    print('mesh_pop 完了:', sql('SELECT count(*) FROM mesh_pop;').split()[2], '行')

def load_biz():
    # T001162: 列名から「全産業」の事業所数・従業者数の列位置を実測で決める
    zp0 = sorted(glob.glob(f'{SRC}/T001162_*.zip'))[0]
    with zipfile.ZipFile(zp0) as z:
        name = [n for n in z.namelist() if n.endswith('.txt')][0]
        text = z.read(name).decode('cp932', 'replace')
    h1 = text.split('\r\n')[0].split(',')
    h2 = text.split('\r\n')[1].split(',')
    # T001162のヘッダーは産業名だけで「事業所数/従業者数」の語が無い。
    # 実測(2026-09-01): 「Ａ～Ｓ全産業」が列1(事業所数ブロック先頭)と列22(従業者数
    # ブロック先頭)に現れる。位置決め打ちにし、ラベルが全産業であることだけ検証する。
    idx_office, idx_emp = 1, 22
    assert '全産業' in h2[idx_office] and '全産業' in h2[idx_emp], (h2[idx_office], h2[idx_emp])
    print(f'T001162 列判定: 事業所数={idx_office}({h2[idx_office].strip()[:16]}) 従業者数={idx_emp}({h2[idx_emp].strip()[:16]})')
    sql("""DROP TABLE IF EXISTS mesh_biz;
CREATE TABLE mesh_biz(key_code text PRIMARY KEY, offices int, employees int, geom geometry(Polygon,4326));""")
    n = 0
    for zp in sorted(glob.glob(f'{SRC}/T001162_*.zip')):
        _, lines = rows_from_zip(zp)
        buf = io.StringIO()
        for ln in lines:
            c = ln.split(',')
            if len(c) <= max(idx_office, idx_emp or 0) or not c[0].strip().isdigit() or len(c[0].strip()) != 9:
                continue
            code = c[0].strip()
            la0, lo0, la1, lo1 = mesh500_bounds(code)
            wkt = f"POLYGON(({lo0} {la0},{lo1} {la0},{lo1} {la1},{lo0} {la1},{lo0} {la0}))"
            buf.write(','.join([code, num(c[idx_office]), num(c[idx_emp]) if idx_emp else '',
                                f'"SRID=4326;{wkt}"']) + '\n')
            n += 1
        r = subprocess.run(PSQL + ['-c', "COPY mesh_biz(key_code,offices,employees,geom) FROM STDIN CSV"],
                           input=buf.getvalue(), capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f'{zp}: {r.stderr[:300]}')
        print(f'  {os.path.basename(zp)}: 累計{n}行', flush=True)
    sql('CREATE INDEX ON mesh_biz USING GIST(geom);')
    print('mesh_biz 完了:', sql('SELECT count(*) FROM mesh_biz;').split()[2], '行')

if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if what in ('pop', 'all'): load_pop()
    if what in ('biz', 'all'): load_biz()
