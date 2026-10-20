#!/usr/bin/env python3
"""Baja los recortes de TheSportsDB (fotos sin fondo) y los lleva a medio cuerpo.

Para cada jugador de tools/jugadores.json lo busca en la API de TheSportsDB y, si tiene recorte:
  tsdb/f/<clave>.webp  foto a color sin fondo, para revelar (cortada a la cintura si viene más larga)
  tsdb/m/<clave>.png   silueta de medio cuerpo, si el recorte llega al menos al pecho
  tsdb/b/<clave>.png   silueta de lo que haya (solo cara, por ejemplo), como último recurso
tsdb/indice.json dice qué archivos hay de cada jugador ("f", "m", "b").
Es incremental (tsdb/estado.json) y respeta el límite de la clave gratuita (30 consultas por minuto).
"""
import argparse, io, json, os, sys, time, urllib.error, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from siluetas import get, strip   # noqa: E402
import medio                      # noqa: E402

API = 'https://www.thesportsdb.com/api/v1/json/{key}/searchplayers.php?p={q}'
PAUSA = 2.2                       # segundos entre consultas: menos de 30 por minuto
OK, NO = 't2', 'no1'              # estados finales ('no1' de la versión anterior sigue valiendo)
VIEJO = 't1'                      # bajados con la versión anterior: se migran sin volver a consultar la API


def consultar(q, key):
    url = API.format(key=urllib.parse.quote(key), q=urllib.parse.quote(q.replace(' ', '_')))
    for _ in range(3):
        try:
            data = json.loads(get(url))
            time.sleep(PAUSA)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(65)
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
                continue
            return p
    return None if red else {}


def abrir(raw):
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(raw)).convert('RGBA')
    except Exception:
        return None
    lo, hi = im.getchannel('A').getextrema()
    if hi == 0 or lo > 200:          # sin transparencia: no es un recorte
        return None
    return im


def procesar(im, salida, k):
    """Guarda f, m y b a partir de un recorte. Devuelve las letras guardadas."""
    tiene = ''
    m, _ = medio.de_recorte(im)
    if m is not None:
        open(os.path.join(salida, 'm', k + '.png'), 'wb').write(medio.sil_png(m.getchannel('A')))
        open(os.path.join(salida, 'f', k + '.webp'), 'wb').write(medio.color_webp(m))
        tiene += 'fm'
    else:
        open(os.path.join(salida, 'f', k + '.webp'), 'wb').write(medio.color_webp(im))
        b = medio.sil_png(im.getchannel('A'))
        if b:
            open(os.path.join(salida, 'b', k + '.png'), 'wb').write(b)
            tiene += 'fb'
        else:
            tiene += 'f'
    return tiene


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lista', default='tools/jugadores.json')
    ap.add_argument('--salida', default='tsdb')
    ap.add_argument('--minutos', type=float, default=320)
    ap.add_argument('--limite', type=int, default=0)
    ap.add_argument('--resumen', default='')
    args = ap.parse_args()
    key = os.environ.get('TSDB_KEY') or '123'

    for d in ('m', 'b', 'f'):
        os.makedirs(os.path.join(args.salida, d), exist_ok=True)
    pe, pi = os.path.join(args.salida, 'estado.json'), os.path.join(args.salida, 'indice.json')
    estado = json.load(open(pe)) if os.path.exists(pe) else {}
    indice = json.load(open(pi)) if os.path.exists(pi) else {}
    jug = json.load(open(args.lista))

    def guardar():
        json.dump(estado, open(pe, 'w'), separators=(',', ':'), sort_keys=True)
        json.dump(indice, open(pi, 'w'), separators=(',', ':'), sort_keys=True)

    # Migración: los recortes de la versión anterior se llevan a medio cuerpo con la foto ya guardada.
    from PIL import Image
    for k, v in list(estado.items()):
        if v != VIEJO:
            continue
        fp = os.path.join(args.salida, 'f', k + '.webp')
        im = Image.open(fp).convert('RGBA') if os.path.exists(fp) else None
        for d in ('b', 'c'):
            try:
                os.remove(os.path.join(args.salida, d, k + '.png'))
            except OSError:
                pass
        if im is None:
            estado.pop(k)            # sin foto guardada: se vuelve a consultar
            indice.pop(k, None)
            continue
        indice[k] = procesar(im, args.salida, k)
        estado[k] = OK
    guardar()

    fin = time.time() + args.minutos * 60
    hechos = cuenta = 0
    stats = {'medio cuerpo': 0, 'solo cara': 0, 'sin recorte': 0, 'red': 0}
    for j in jug:
        k = j['k']
        if estado.get(k) in (OK, NO):
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
            for campo in ('strCutout', 'strRender'):
                if not p.get(campo):
                    continue
                try:
                    im = abrir(get(p[campo], timeout=40))
                except Exception:
                    im = None
                if im is not None:
                    tiene = procesar(im, args.salida, k)
                    if 'm' in tiene:
                        break
        if tiene:
            indice[k] = tiene
            stats['medio cuerpo' if 'm' in tiene else 'solo cara'] += 1
            estado[k] = OK
        else:
            indice.pop(k, None)
            stats['sin recorte'] += 1
            estado[k] = NO
        hechos += 1
        if hechos % 50 == 0:
            guardar()
            print(f'{hechos} procesados · {stats}', flush=True)
    guardar()
    pendientes = sum(1 for j in jug if estado.get(j['k']) not in (OK, NO))
    con_m = sum(1 for v in indice.values() if 'm' in v)
    print(f'Listo: {hechos} en esta corrida {stats}. Con medio cuerpo: {con_m}. Pendientes: {pendientes}.')
    if args.resumen:
        json.dump({'pendientes': pendientes, 'recortes': con_m, 'hechos': hechos}, open(args.resumen, 'w'))


if __name__ == '__main__':
    main()
