"""地域メッシュコード(JIS X 0410)の500mメッシュ(9桁)を経緯度矩形に変換する。

境界シェープファイルを配らなくても、コードから矩形が計算で出る。
  1次(4桁): 緯度=下2桁/1.5, 経度=上2桁+100 … 高さ40分・幅1度
  2次(2桁): 8等分 … 高さ5分・幅7.5分
  3次(2桁): 10等分 … 高さ30秒・幅45秒 (=1kmメッシュ)
  500m(1桁): 1kmを4等分。1=南西 2=南東 3=北西 4=北東
"""

def mesh500_bounds(code: str):
    """9桁の500mメッシュコード → (lat_min, lon_min, lat_max, lon_max)"""
    code = code.strip()
    if len(code) != 9 or not code.isdigit():
        raise ValueError(f"500mメッシュコードは9桁: {code!r}")
    p = int(code[0:2]); u = int(code[2:4])
    q = int(code[4]);   v = int(code[5])
    r = int(code[6]);   w = int(code[7])
    m = int(code[8])
    if not (1 <= m <= 4):
        raise ValueError(f"500m区画は1-4: {code!r}")
    lat = p / 1.5 + q * 5 / 60 + r * 30 / 3600
    lon = 100 + u + v * 7.5 / 60 + w * 45 / 3600
    h = 30 / 3600 / 2      # 15秒
    wd = 45 / 3600 / 2     # 22.5秒
    if m in (2, 4): lon += wd
    if m in (3, 4): lat += h
    return (lat, lon, lat + h, lon + wd)

def latlon_to_mesh500(lat: float, lon: float) -> str:
    p = int(lat * 1.5); u = int(lon - 100)
    a = lat * 1.5 - p;  b = lon - 100 - u
    q = int(a * 8);     v = int(b * 8)
    a = a * 8 - q;      b = b * 8 - v
    r = int(a * 10);    w = int(b * 10)
    a = a * 10 - r;     b = b * 10 - w
    m = 1 + (1 if b >= 0.5 else 0) + (2 if a >= 0.5 else 0)
    return f"{p:02d}{u:02d}{q}{v}{r}{w}{m}"

if __name__ == "__main__":
    # 自己テスト: 逆変換の一致と、実データのコード(523600002)の位置
    import random
    random.seed(0)
    for _ in range(2000):
        lat = random.uniform(24, 45); lon = random.uniform(123, 145)
        c = latlon_to_mesh500(lat, lon)
        lat0, lon0, lat1, lon1 = mesh500_bounds(c)
        assert lat0 - 1e-9 <= lat <= lat1 + 1e-9 and lon0 - 1e-9 <= lon <= lon1 + 1e-9, (lat, lon, c)
    b = mesh500_bounds("523600002")
    assert 34.6 < b[0] < 34.8 and 136.0 <= b[1] < 136.1, b
    # 名古屋市瑞穂区(35.13,136.94)のコードが5236台であること
    c = latlon_to_mesh500(35.13, 136.94)
    assert c.startswith("5236"), c
    print("自己テスト2002件OK / 瑞穂区メッシュ:", c)
