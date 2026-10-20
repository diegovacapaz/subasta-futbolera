#!/usr/bin/env python3
"""Prueba rápida del recorte: arma muestras/<clave>.png con la foto original y su silueta lado a lado,
para los jugadores listados en tools/muestra.txt (un nombre por línea). No toca la carpeta sil/."""
import io, json, os, sys, urllib.error
sys.path.insert(0, os.path.dirname(__file__))
import siluetas as S
from PIL import Image
from rembg import new_session

nombres = [l.strip() for l in open('tools/muestra.txt', encoding='utf-8') if l.strip()]
jug = {j['n']: j for j in json.load(open('tools/jugadores.json'))}
sessions = [new_session(x) for x in S.MODELOS]
os.makedirs('muestras', exist_ok=True)
res = []
for n in nombres:
    j = jug.get(n)
    if not j:
        res.append({'n': n, 'error': 'no está en la lista'}); continue
    r = {'n': n, 'k': j['k'], 'intentos': []}
    raw = None
    urls = [S.TM + 'big/' + j['img'], S.TM + 'header/' + j['img']] if j['img'] else []
    for u in urls:
        try:
            raw = S.get(u); r['fuente'] = u; break
        except urllib.error.HTTPError as e:
            r['intentos'].append(f'{u} -> HTTP {e.code}')
        except Exception as e:
            r['intentos'].append(f'{u} -> {type(e).__name__}: {e}')
    if raw is None:
        w = S.wiki(j['n'], j['by'])
        r['wikipedia'] = w
        if w:
            try:
                raw = S.get(w); r['fuente'] = w
            except Exception as e:
                r['intentos'].append(f'{w} -> {type(e).__name__}: {e}')
    if raw is None:
        res.append(r); continue
    png = S.silueta(raw, sessions)
    r['silueta'] = bool(png)
    orig = Image.open(io.BytesIO(raw)).convert('RGB')
    H = 320
    orig = orig.resize((round(orig.width * H / orig.height), H))
    sil = Image.open(io.BytesIO(png)).convert('RGBA') if png else None
    W = orig.width + 20 + (sil.width if sil else 0) + 20
    out = Image.new('RGB', (W, H + 20), (237, 230, 205))
    out.paste(orig, (10, 10))
    if sil:
        out.paste(sil, (orig.width + 30, 10), sil)
    out.save(os.path.join('muestras', j['k'] + '.png'))
    res.append(r)
json.dump(res, open('muestras/resultado.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
