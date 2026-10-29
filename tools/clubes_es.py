"""Descarga de OpenStreetMap los clubes de pádel y los pueblos/ciudades de España
y genera data/clubes-es.json para la app."""
import json, math, re, time, unicodedata, urllib.parse, urllib.request

SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

def overpass(q):
    for attempt in range(6):
        for url in SERVERS:
            try:
                data = urllib.parse.urlencode({"data": q}).encode()
                req = urllib.request.Request(url, data=data, headers={"User-Agent": "padelx4-prototipo/1.0"})
                with urllib.request.urlopen(req, timeout=400) as r:
                    return json.load(r)
            except Exception as e:
                print("fallo", url, e); time.sleep(20)
    raise SystemExit("Overpass no responde")

AREA = 'area["ISO3166-1"="ES"][admin_level=2]->.es;'
clubs_raw = overpass('[out:json][timeout:600];' + AREA + 'nwr["sport"~"padel|paddle_tennis"](area.es);out center;')["elements"]
centres_raw = overpass('[out:json][timeout:600];' + AREA + 'nwr["name"]["leisure"~"^(sports_centre|sports_hall|fitness_centre|stadium|club)$"](area.es);nwr["name"]["club"="sport"](area.es);out center;')["elements"]
places_raw = overpass('[out:json][timeout:600];' + AREA + 'node["place"~"^(city|town)$"](area.es);out;')["elements"]

def ll(e):
    if "lat" in e: return e["lat"], e["lon"]
    c = e.get("center"); return (c["lat"], c["lon"]) if c else (None, None)

GENERIC = re.compile(r"(?i)^\s*(pista|pistas|court|padel|p[aá]del|p[aà]del|pista de p[aá]del|padel court)\s*\d*\s*$")
centres = []
for e in centres_raw:
    la, lo = ll(e)
    if la is not None: centres.append((la, lo, e["tags"]["name"].strip()))
cgrid = {}
for c in centres: cgrid.setdefault((round(c[0] / 0.003), round(c[1] / 0.004)), []).append(c)
pts = []
for e in clubs_raw:
    la, lo = ll(e)
    if la is None: continue
    t = e.get("tags", {})
    pts.append({"la": la, "lo": lo, "n": "" if GENERIC.match(t.get("name") or "") else (t.get("name") or "").strip(), "c": t.get("addr:city", ""),
                "big": t.get("leisure") in ("sports_centre", "sports_hall") or t.get("club") == "sport"})

def km(a, b, c, d):
    r = math.pi / 180
    x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))

# Agrupar pistas sueltas que están a menos de 250 m en un solo club
parent = list(range(len(pts)))
def find(i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]; i = parent[i]
    return i
grid = {}
for i, p in enumerate(pts):
    grid.setdefault((round(p["la"] / 0.003), round(p["lo"] / 0.004)), []).append(i)
for (gx, gy), ids in grid.items():
    near = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for j in grid.get((gx + dx, gy + dy), [])]
    for i in ids:
        for j in near:
            if j > i and km(pts[i]["la"], pts[i]["lo"], pts[j]["la"], pts[j]["lo"]) < 0.25:
                parent[find(i)] = find(j)
groups = {}
for i in range(len(pts)): groups.setdefault(find(i), []).append(pts[i])

places = []
for e in places_raw:
    t = e.get("tags", {}); n = t.get("name:es") or t.get("name")
    if n: places.append([n, round(e["lat"], 4), round(e["lon"], 4), 1 if t.get("place") == "city" else 0])

def nearest_place(la, lo):
    best, bd = "", 1e9
    for n, a, b, _ in places:
        if abs(a - la) > 0.3 or abs(b - lo) > 0.4: continue
        d = km(la, lo, a, b)
        if d < bd: best, bd = n, d
    return best

clubs = []
for g in groups.values():
    named = sorted([p for p in g if p["n"]], key=lambda p: (not p["big"], len(p["n"])))
    la0 = sum(p["la"] for p in g) / len(g); lo0 = sum(p["lo"] for p in g) / len(g)
    if named: name = named[0]["n"]
    else:
        gx, gy = round(la0 / 0.003), round(lo0 / 0.004); best, bd = "", 0.25
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for c in cgrid.get((gx + dx, gy + dy), []):
                    d = km(la0, lo0, c[0], c[1])
                    if d < bd: best, bd = c[2], d
        if not best: continue  # sin nombre ni centro deportivo cerca: suele ser una urbanización
        name = best
    if re.fullmatch(r"(?i)(pista|pistas)( de)? (p[aá]del|padel)( \d+)?", name): continue
    la = sum(p["la"] for p in g) / len(g); lo = sum(p["lo"] for p in g) / len(g)
    city = next((p["c"] for p in g if p["c"]), "") or nearest_place(la, lo)
    clubs.append([name, round(la, 5), round(lo, 5), city, len(g)])

# Mismo nombre a menos de 1 km: es el mismo club
merged = []
for c in clubs:
    m = next((x for x in merged if x[0].lower() == c[0].lower() and km(x[1], x[2], c[1], c[2]) < 1), None)
    if m: m[4] += c[4]
    else: merged.append(c)
clubs = merged
clubs.sort(key=lambda c: (c[3], c[0]))
places.sort(key=lambda p: p[0])
import os; os.makedirs("data", exist_ok=True)
with open("data/clubes-es.json", "w", encoding="utf-8") as f:
    json.dump({"fuente": "OpenStreetMap (ODbL)", "fecha": time.strftime("%Y-%m-%d"), "clubes": clubs, "lugares": places},
              f, ensure_ascii=False, separators=(",", ":"))
print(len(pts), "elementos ->", len(clubs), "clubes;", len(places), "pueblos y ciudades")
