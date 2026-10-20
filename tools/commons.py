#!/usr/bin/env python3
"""Completa con fotos de Wikimedia Commons a quienes TheSportsDB no les da un medio cuerpo.

Para cada jugador (en orden de valor) que ya fue revisado en TheSportsDB y no tiene tsdb/m:
  1. Busca sus fotos en Commons y baja hasta 10 candidatas.
  2. Se queda con las que tienen una sola persona, llegan al menos al pecho y tienen fondo simple
     (pocos bordes alrededor). Para las leyendas prefiere fotos de los años en que jugaban.
  3. Recorta la mejor de la cintura para arriba, le quita el fondo y controla que la silueta sea prolija.
Guarda commons/m/<clave>.png (silueta), commons/f/<clave>.webp (foto a color sin fondo, para revelar) y
en commons/indice.json la página de la foto en Commons (autoría y licencia).
"""
import argparse, io, json, os, re, sys, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from siluetas import get, strip   # noqa: E402
import medio                      # noqa: E402

API = 'https://commons.wikimedia.org/w/api.php?'
OK, NO = 'c1', 'nc1'
MAX_CAND = 10


def candidatas(j):
    """Fotos de Commons que mencionan al jugador en el nombre del archivo. None si falló la red."""
    toks = [t for t in re.split(r"[\s'.-]+", strip(j['n']).lower()) if len(t) >= 3]
    if not toks:
        return []
    url = API + urllib.parse.urlencode({
        'action': 'query', 'format': 'json', 'formatversion': 2, 'generator': 'search', 'gsrnamespace': 6,
        'gsrsearch': f'"{j["n"]}"', 'gsrlimit': 25, 'prop': 'imageinfo', 'iiprop': 'url|size|mime', 'iiurlwidth': 900})
    try:
        data = json.loads(get(url))
    except Exception:
        return None
    out = []
    for p in sorted((data.get('query') or {}).get('pages') or [], key=lambda p: p.get('index', 0)):
        ii = (p.get('imageinfo') or [{}])[0]
        if ii.get('mime') not in ('image/jpeg', 'image/png') or min(ii.get('width', 0), ii.get('height', 0)) < 300:
            continue
        t = strip(p.get('title', '')).lower()
        if toks[-1] not in t:                       # el apellido tiene que estar en el nombre del archivo
            continue
        if re.search(r'logo|signature|firma|autograph|stadium|estadio|tomb|grave|statue|estatua|mural|card|cromo|sticker', t):
            continue
        anio = re.search(r'\b(19[0-9]{2}|20[0-2][0-9])\b', t)
        out.append({'title': p['title'], 'thumb': ii.get('thumburl') or ii.get('url'),
                    'anio': int(anio.group(1)) if anio else None,
                    'nombre_completo': all(x in t for x in toks)})
        if len(out) >= MAX_CAND:
            break
    return out


def fondo_simple(rgb, cara):
    """Cuántos bordes hay en las franjas laterales y de arriba (0 = fondo liso). Menos es mejor."""
    import cv2
    import numpy as np
    g = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2GRAY)
    e = cv2.Canny(g, 80, 160) > 0
    h, w = e.shape
    x, y, fw, fh = cara
    banda = np.zeros_like(e)
    banda[:, :max(1, int(x - 0.9 * fw))] = True                 # a la izquierda del cuerpo
    banda[:, min(w - 1, int(x + fw + 0.9 * fw)):] = True         # a la derecha
    banda[:max(1, int(y - 0.3 * fh)), :] = True                  # arriba de la cabeza
    return float(e[banda].mean()) if banda.any() else 0.5


def evaluar(c, j):
    """Baja la candidata y la puntúa. Devuelve (puntaje, imagen recortada, centro de la cara) o None."""
    from PIL import Image
    try:
        rgb = Image.open(io.BytesIO(get(c['thumb'], timeout=30))).convert('RGB')
    except Exception:
        return None
    cara = medio.una_cara(rgb)
    if not cara or cara[3] < 36:
        return None
    if medio.alcance(cara, rgb.height) < medio.MIN_L:
        return None
    caja = medio.caja(cara, rgb.width, rgb.height)
    crop = rgb.crop(caja)
    cara_c = (cara[0] - caja[0], cara[1] - caja[1], cara[2], cara[3])
    puntos = -fondo_simple(crop, cara_c) * 4
    if c['nombre_completo']:
        puntos += 0.15
    if c['anio'] and j['by']:
        edad = c['anio'] - j['by']
        if 17 <= edad <= 37:
            puntos += 0.3 if j['ley'] else 0.1      # foto de cuando jugaba
        elif edad > 45:
            puntos -= 0.3
    return puntos, crop, (cara_c[0] + cara_c[2] / 2, cara_c[1] + cara_c[3] / 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lista', default='tools/jugadores.json')
    ap.add_argument('--salida', default='commons')
    ap.add_argument('--tsdb', default='tsdb')
    ap.add_argument('--minutos', type=float, default=320)
    ap.add_argument('--limite', type=int, default=0)
    ap.add_argument('--solo', default='', help='nombres separados por | (para pruebas)')
    ap.add_argument('--resumen', default='')
    args = ap.parse_args()

    from rembg import new_session, remove
    sessions = [new_session(m) for m in ('isnet-general-use', 'u2net_human_seg')]
    for d in ('m', 'f'):
        os.makedirs(os.path.join(args.salida, d), exist_ok=True)
    pe, pi = os.path.join(args.salida, 'estado.json'), os.path.join(args.salida, 'indice.json')
    estado = json.load(open(pe)) if os.path.exists(pe) else {}
    indice = json.load(open(pi)) if os.path.exists(pi) else {}
    def leer(p):
        return json.load(open(p)) if os.path.exists(p) else {}
    t_estado, t_indice = leer(os.path.join(args.tsdb, 'estado.json')), leer(os.path.join(args.tsdb, 'indice.json'))
    jug = json.load(open(args.lista))
    if args.solo:
        nombres = set(args.solo.split('|'))
        jug = [j for j in jug if j['n'] in nombres]
    else:   # solo los que TheSportsDB ya revisó y no tienen medio cuerpo
        jug = [j for j in jug if t_estado.get(j['k']) in ('t2', 'no1') and 'm' not in t_indice.get(j['k'], '')]

    def guardar():
        json.dump(estado, open(pe, 'w'), separators=(',', ':'), sort_keys=True)
        json.dump(indice, open(pi, 'w'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)

    fin = time.time() + args.minutos * 60
    hechos = cuenta = 0
    stats = {'con foto': 0, 'sin foto': 0, 'red': 0}
    for j in jug:
        k = j['k']
        if estado.get(k) in (OK, NO) and not args.solo:
            continue
        if time.time() > fin or (args.limite and cuenta >= args.limite):
            break
        cuenta += 1
        cs = candidatas(j)
        if cs is None:
            stats['red'] += 1
            continue
        evaluadas = []
        for c in cs:
            r = evaluar(c, j)
            if r:
                evaluadas.append((r, c))
            time.sleep(0.2)
        evaluadas.sort(key=lambda x: -x[0][0])
        listo = None
        for (puntos, crop, centro), c in evaluadas[:3]:
            for s in sessions:
                cut = remove(crop, session=s, post_process_mask=True)
                a = medio.limpiar(cut.getchannel('A'), centro)
                if a is not None:
                    cut.putalpha(a)
                    listo = (cut, c)
                    break
            if listo:
                break
        if listo:
            cut, c = listo
            open(os.path.join(args.salida, 'm', k + '.png'), 'wb').write(medio.sil_png(cut.getchannel('A')))
            open(os.path.join(args.salida, 'f', k + '.webp'), 'wb').write(medio.color_webp(cut))
            indice[k] = 'https://commons.wikimedia.org/wiki/' + urllib.parse.quote(c['title'].replace(' ', '_'))
            estado[k] = OK
            stats['con foto'] += 1
        else:
            indice.pop(k, None)
            estado[k] = NO
            stats['sin foto'] += 1
        hechos += 1
        if hechos % 25 == 0:
            guardar()
            print(f'{hechos} procesados · {stats}', flush=True)
    guardar()
    pendientes = sum(1 for j in jug if estado.get(j['k']) not in (OK, NO))
    print(f'Listo: {hechos} en esta corrida {stats}. Con foto de Commons: {len(indice)}. Pendientes (ya revisados en TheSportsDB): {pendientes}.')
    if args.resumen:
        json.dump({'pendientes': pendientes, 'fotos': len(indice), 'hechos': hechos}, open(args.resumen, 'w'))


if __name__ == '__main__':
    main()
