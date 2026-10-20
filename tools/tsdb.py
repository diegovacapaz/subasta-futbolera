#!/usr/bin/env python3
"""Baja los recortes de TheSportsDB (fotos sin fondo) y los guarda en el repositorio.

Para cada jugador de tools/jugadores.json lo busca en la API de TheSportsDB y, si tiene recorte:
  tsdb/c/<clave>.png   silueta negra de cuerpo entero (400 px de alto)
  tsdb/b/<clave>.png   silueta negra de busto (320 px de alto)
  tsdb/f/<clave>.webp  foto a color sin fondo, para revelar (480 px de alto)
tsdb/indice.json dice qué archivos hay de cada jugador ("c", "b", "f").
Es incremental (tsdb/estado.json) y respeta el límite de la clave gratuita (30 consultas por minuto).
"""
import argparse, io, json, os, sys, time, urllib.error, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from siluetas import get, strip, encuadre   # noqa: E402

API = 'https://www.thesportsdb.com/api/v1/json/{key}/searchplayers.php?p={q}'
PAUSA = 2.2          # segundos entre consultas: menos de 30 por minuto
OK, NO = 't1', 'no1'  # estados de esta versión


def consultar(q, key):
    url = API.format(key=urllib.parse.quote(key), q=urllib.parse.quote(q.replace(' ', '_')))
    for intento in range(3):
        try:
            data = json.loads(get(url))
            time.sleep(PAUSA)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(65)   # se pasó del límite: esperar un minuto
                continue
            time.sleep(PAUSA)
            return None
        except Exception:
            time.sleep(5)
    return None


def buscar(j, key):
    """Ficha del jugador en TheSportsDB, {} si no está, None si falló la red."""
    vistos, red = set(), False
    for q in (j['n'], strip(j['n'])):
        if q in vistos:
            continue
        vistos.add(q)
        data = consultar(q, key)
        if data is None:
            red = True
            continue
        for p in (data.get('player') or data.get('players') or []):
            if p.get('strSport') not in (None, '', 'Soccer'):
                continue
            nacio = (p.get('dateBorn') or '')[:4]
            if nacio.isdigit() and j['by']:
                if abs(int(nacio) - j['by']) > 1:
                    continue
            elif strip(p.get('strPlayer', '')).lower() != strip(j['n']).lower():
                continue   # sin fecha, solo si el nombre coincide exacto
            return p
    return None if red else {}


def abrir_recorte(url):
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(get(url, timeout=40))).convert('RGBA')
    except Exception:
        return None
    a = im.getchannel('A')
    lo, hi = a.getextrema()
    if hi == 0 or lo > 200:      # sin transparencia: no es un recorte
        return None
    return im.crop(a.point(lambda v: 255 if v > 40 else 0).getbbox())


def silueta_png(alpha, alto):
    from PIL import Image
    w, h = alpha.size
    alpha = alpha.resize((max(1, round(w * alto / h)), alto), Image.LANCZOS)
    alpha = alpha.point(lambda v: 0 if v < 24 else 255 if v > 232 else v // 16 * 16)
    out = Image.new('LA', alpha.size, 0)
    out.putalpha(alpha)
    buf = io.BytesIO()
    out.save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def busto_de(im):
    """Silueta de busto a partir de un recorte de cuerpo entero, encuadrando por la cara."""
    from PIL import Image
    fondo = Image.new('RGB', im.size, (255, 255, 255))
    fondo.paste(im, mask=im.getchannel('A'))
    _, cara, grupal, caja = encuadre(fondo)
    if not cara or grupal:
        return None
    a = im.getchannel('A').crop(caja)
    bb = a.point(lambda v: 255 if v > 40 else 0).getbbox()
    return silueta_png(a.crop(bb), 320) if bb else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lista', default='tools/jugadores.json')
    ap.add_argument('--salida', default='tsdb')
    ap.add_argument('--minutos', type=float, default=320)
    ap.add_argument('--limite', type=int, default=0)
    ap.add_argument('--solo', default='', help='nombres separados por | (para pruebas)')
    ap.add_argument('--resumen', default='')
    args = ap.parse_args()
    key = os.environ.get('TSDB_KEY') or '123'

    for d in ('c', 'b', 'f'):
        os.makedirs(os.path.join(args.salida, d), exist_ok=True)
    pe, pi = os.path.join(args.salida, 'estado.json'), os.path.join(args.salida, 'indice.json')
    estado = json.load(open(pe)) if os.path.exists(pe) else {}
    indice = json.load(open(pi)) if os.path.exists(pi) else {}
    jug = json.load(open(args.lista))
    if args.solo:
        nombres = set(args.solo.split('|'))
        jug = [j for j in jug if j['n'] in nombres]

    def guardar():
        json.dump(estado, open(pe, 'w'), separators=(',', ':'), sort_keys=True)
        json.dump(indice, open(pi, 'w'), separators=(',', ':'), sort_keys=True)

    from PIL import Image
    fin = time.time() + args.minutos * 60
    hechos = cuenta = 0
    stats = {'con recorte': 0, 'sin recorte': 0, 'no está': 0, 'red': 0}
    for j in jug:
        k = j['k']
        if estado.get(k) in (OK, NO) and not args.solo:
            continue
        if time.time() > fin or (args.limite and cuenta >= args.limite):
            break
        cuenta += 1
        p = buscar(j, key)
        if p is None:
            stats['red'] += 1
            continue
        tiene = ''
        if p:
            render = abrir_recorte(p['strRender']) if p.get('strRender') else None
            corte = abrir_recorte(p['strCutout']) if p.get('strCutout') else None
            cuerpo = render or corte
            if render:
                open(os.path.join(args.salida, 'c', k + '.png'), 'wb').write(silueta_png(render.getchannel('A'), 400))
                tiene += 'c'
            busto = silueta_png(corte.getchannel('A'), 320) if corte else (busto_de(render) if render else None)
            if busto:
                open(os.path.join(args.salida, 'b', k + '.png'), 'wb').write(busto)
                tiene += 'b'
            if cuerpo:
                col = cuerpo.resize((max(1, round(cuerpo.width * 480 / cuerpo.height)), 480), Image.LANCZOS)
                col.save(os.path.join(args.salida, 'f', k + '.webp'), 'WEBP', quality=80, method=6)
                tiene += 'f'
        if tiene:
            indice[k] = tiene
            stats['con recorte'] += 1
        else:
            indice.pop(k, None)
            stats['sin recorte' if p else 'no está'] += 1
        estado[k] = OK if tiene else NO
        hechos += 1
        if hechos % 50 == 0:
            guardar()
            print(f'{hechos} procesados · {stats}', flush=True)
    guardar()
    pendientes = sum(1 for j in json.load(open(args.lista)) if estado.get(j['k']) not in (OK, NO))
    print(f'Listo: {hechos} en esta corrida {stats}. Con recorte en total: {len(indice)}. Pendientes: {pendientes}.')
    if args.resumen:
        json.dump({'pendientes': pendientes, 'recortes': len(indice), 'hechos': hechos}, open(args.resumen, 'w'))


if __name__ == '__main__':
    main()
