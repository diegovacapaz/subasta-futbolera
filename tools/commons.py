#!/usr/bin/env python3
"""Completa con fotos de Wikimedia Commons a quienes TheSportsDB no les da un medio cuerpo.

Para cada jugador (en orden de valor) que ya fue revisado en TheSportsDB y no tiene tsdb/m:
  1. Lo identifica en Wikidata (nombre, que sea futbolista, año de nacimiento) y toma las fotos de su
     categoría en Commons, así no se cuela otra persona con el mismo nombre. Baja hasta 12 candidatas.
  2. Se queda con las que tienen una sola persona, llegan al menos al pecho y tienen fondo simple
     (pocos bordes alrededor). Para las leyendas prefiere fotos de los años en que jugaban.
  3. Recorta la mejor de la cintura para arriba, le quita el fondo y controla que la silueta sea prolija.
Guarda commons/m/<clave>.png (silueta), commons/f/<clave>.webp (foto a color sin fondo, para revelar) y
en commons/indice.json la página de la foto en Commons (autoría y licencia). Lo lanza la descarga de TheSportsDB
cada vez que guarda, y también corre cada hora.
"""
import argparse, io, json, os, re, sys, time, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from siluetas import get, strip   # noqa: E402
import medio                      # noqa: E402

API = 'https://commons.wikimedia.org/w/api.php?'
OK, NO = 'c3', 'nc3'   # versión 2: fotos de la categoría del jugador en Commons (vía Wikidata)
MAX_CAND = 12


WD = 'https://www.wikidata.org/w/api.php?'
# Archivos que no son una foto del jugador solo: objetos, homenajes, lugares, o varias personas en el título.
RUIDO = re.compile(r'logo|signature|firma|autograph|stadium|estadio|tomb|grave|statue|estatua|busto|bust\b|bronze|bronce|monument|'
                   r'memorial|homenaje|tribute|award|premio|trofeo|trophy|placa|plaque|mural|card|cromo|figurita|sticker|stamp|'
                   r'sello|poster|cartel|coin|moneda|street|calle|museum|museo|painting|pintura|drawing|dibujo|caricatur', re.I)
VARIOS = re.compile(r' vs\.? | v\. | versus | contra | and | with | con | y | e | und | et | & |team|equipo|squad|plantel|seleccion|'
                    r'selecao|national team|line-?up|formacion|celebrat|festej', re.I)
FUTBOL = re.compile(r'football|soccer|futbol|calcio|fussball|voetbal|goalkeeper|arquero|portero', re.I)


def jget(base, **params):
    return json.loads(get(base + urllib.parse.urlencode(dict(params, format='json'))))


def ficha_wikidata(j):
    """Ficha de Wikidata del jugador (por nombre, descripción futbolera y año de nacimiento). None si falló la red."""
    try:
        r = jget(WD, action='wbsearchentities', search=j['n'], language='en', uselang='en', type='item', limit=8)
    except Exception:
        return None
    ids = [x['id'] for x in r.get('search', []) if FUTBOL.search(strip(x.get('description', '')))]
    if not ids:
        return {}
    try:
        ents = jget(WD, action='wbgetentities', ids='|'.join(ids), props='claims').get('entities', {})
    except Exception:
        return None
    for i in ids:
        cl = ents.get(i, {}).get('claims', {})
        def val(p):
            try:
                return cl[p][0]['mainsnak']['datavalue']['value']
            except (KeyError, IndexError):
                return None
        nac = val('P569')
        anio = int(nac['time'][1:5]) if isinstance(nac, dict) and nac.get('time', '')[1:5].isdigit() else None
        if anio and j['by'] and abs(anio - j['by']) > 1:
            continue
        return {'qid': i, 'cat': val('P373'), 'img': val('P18')}
    return {}


def archivos(**gen):
    """Archivos de Commons (con miniatura) según un generador de la API."""
    data = jget(API, action='query', formatversion=2, prop='imageinfo', iiprop='url|size|mime', iiurlwidth=900, **gen)
    out = []
    for p in (data.get('query') or {}).get('pages') or []:
        ii = (p.get('imageinfo') or [{}])[0]
        if p.get('ns') == 6 and ii.get('mime') in ('image/jpeg', 'image/png') and min(ii.get('width', 0), ii.get('height', 0)) >= 300:
            out.append({'title': p['title'], 'thumb': ii.get('thumburl') or ii.get('url')})
    return out


def candidatas(j):
    """Fotos de Commons del jugador: las de su categoría en Commons (vía Wikidata, así es seguro que es él)
    y su foto principal. Si no tiene ficha en Wikidata, búsqueda por nombre completo. None si falló la red."""
    toks = [t for t in re.split(r"[\s'.-]+", strip(j['n']).lower()) if len(t) >= 3]
    ficha = ficha_wikidata(j)
    if ficha is None:
        return None
    vistos, cands = set(), []
    def sumar(lista):
        for c in lista:
            if c['title'] not in vistos:
                vistos.add(c['title'])
                cands.append(c)
    try:
        if ficha.get('img'):
            sumar(archivos(titles='File:' + ficha['img']))
        if ficha.get('cat'):
            cat = 'Category:' + ficha['cat']
            sumar([c for c in archivos(generator='categorymembers', gcmtitle=cat, gcmtype='file', gcmlimit=60)
                   if toks[-1] in strip(c['title']).lower()])
            subs = jget(API, action='query', list='categorymembers', cmtitle=cat, cmtype='subcat', cmlimit=30)
            subs = [x['title'] for x in (subs.get('query') or {}).get('categorymembers', [])
                    if toks[-1] in strip(x['title']).lower() and not RUIDO.search(strip(x['title']))]
            def de_epoca(t):
                m = re.search(r'(19[0-9]{2}|20[0-2][0-9])', t)
                return 0 if (m and j['by'] and 17 <= int(m.group(1)) - j['by'] <= 37) else 1
            for sc in sorted(subs, key=de_epoca)[:4]:
                sumar([c for c in archivos(generator='categorymembers', gcmtitle=sc, gcmtype='file', gcmlimit=30)
                       if toks[-1] in strip(c['title']).lower()])
        if not ficha and len(toks) >= 2:   # sin ficha: solo búsqueda con el nombre completo en el archivo
            for c in archivos(generator='search', gsrnamespace=6, gsrsearch=f'"{j["n"]}"', gsrlimit=25):
                if all(t in strip(c['title']).lower() for t in toks):
                    sumar([c])
    except Exception:
        return None
    out = []
    for c in cands:
        t = strip(c['title']).lower()
        if RUIDO.search(t) or VARIOS.search(' ' + t + ' '):
            continue
        anio = re.search(r'\b(19[0-9]{2}|20[0-2][0-9])\b', t)
        c['anio'] = int(anio.group(1)) if anio else None
        c['nombre_completo'] = all(x in t for x in toks)
        out.append(c)
    # primero las de su época (para elegir qué bajar), después el resto
    def orden(c):
        if c['anio'] and j['by'] and 17 <= c['anio'] - j['by'] <= 37:
            return 0
        return 1 if not c['anio'] else 2
    out.sort(key=orden)
    return out[:MAX_CAND]


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
    ap.add_argument('--parte', type=int, default=0, help='qué parte procesar (para correr varias en paralelo)')
    ap.add_argument('--partes', type=int, default=1)
    args = ap.parse_args()

    from rembg import new_session, remove
    sessions = [new_session(m) for m in ('isnet-general-use', 'u2net_human_seg')]
    fino = [None]   # modelo pesado (birefnet-portrait), solo si hace falta
    for d in ('m', 'f'):
        os.makedirs(os.path.join(args.salida, d), exist_ok=True)
    def leer(p):
        return json.load(open(p)) if os.path.exists(p) else {}
    # Con varias partes en paralelo, cada una tiene su estado e índice (estado-N.json, indice-N.json)
    # y arranca con lo que ya había en los archivos comunes de antes.
    suf = f'-{args.parte}' if args.partes > 1 else ''
    import zlib
    mia = lambda k: args.partes <= 1 or zlib.crc32(k.encode()) % args.partes == args.parte
    pe, pi = os.path.join(args.salida, f'estado{suf}.json'), os.path.join(args.salida, f'indice{suf}.json')
    estado, indice = leer(pe), leer(pi)
    if suf and not os.path.exists(pe):   # primera vez en partes: arranca con lo de los archivos comunes
        estado = {k: v for k, v in leer(os.path.join(args.salida, 'estado.json')).items() if mia(k)}
        indice = {k: v for k, v in leer(os.path.join(args.salida, 'indice.json')).items() if mia(k)}
    t_estado, t_indice = leer(os.path.join(args.tsdb, 'estado.json')), leer(os.path.join(args.tsdb, 'indice.json'))
    # Correcciones a mano (tools/revision.json, armado con revisar.html):
    #   {"<clave>": {"no": ["tsdb", "File:..."], "url": "https://... (otra foto)"}}
    rev = leer(os.path.join(os.path.dirname(args.lista), 'revision.json'))
    prev = leer(os.path.join(args.salida, f'rev{suf}.json')) or {k: v for k, v in leer(os.path.join(args.salida, 'rev.json')).items() if mia(k)}
    firma = lambda k: json.dumps(rev.get(k), sort_keys=True) if k in rev else ''
    jug = json.load(open(args.lista))
    if args.solo:
        nombres = set(args.solo.split('|'))
        jug = [j for j in jug if j['n'] in nombres]
    else:   # solo los que TheSportsDB ya revisó y no tienen medio cuerpo
        veto = lambda k: 'tsdb' in (rev.get(k) or {}).get('no', [])
        jug = [j for j in jug if mia(j['k']) and (
               (t_estado.get(j['k']) in ('t2', 'no1', 'skip1') and ('m' not in t_indice.get(j['k'], '') or veto(j['k'])))
               or j['k'] in rev)]

    def guardar():
        json.dump(prev, open(os.path.join(args.salida, f'rev{suf}.json'), 'w'), separators=(',', ':'), sort_keys=True)
        json.dump(estado, open(pe, 'w'), separators=(',', ':'), sort_keys=True)
        json.dump(indice, open(pi, 'w'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)

    fin = time.time() + args.minutos * 60
    hechos = cuenta = 0
    stats = {'con foto': 0, 'sin foto': 0, 'red': 0}
    for j in jug:
        k = j['k']
        if estado.get(k) in (OK, NO) and prev.get(k, '') == firma(k) and not args.solo:
            continue
        if time.time() > fin or (args.limite and cuenta >= args.limite):
            break
        cuenta += 1
        r = rev.get(k) or {}
        if r.get('url'):
            cs = [{'title': r['url'], 'thumb': r['url'], 'anio': None, 'nombre_completo': True, 'manual': True}]
        else:
            cs = candidatas(j)
            if cs is not None:
                cs = [c for c in cs if c['title'] not in r.get('no', [])]
        if cs is None:
            stats['red'] += 1
            continue
        # "Mal recortada" en la revisión: esa misma foto se vuelve a recortar primero, con un modelo más preciso
        recortar = set(r.get('recortar', []))
        if recortar and not r.get('url'):
            presentes = {c['title'] for c in cs}
            for t in recortar - presentes:
                try:
                    cs += [dict(c, anio=None, nombre_completo=True) for c in archivos(titles=t)]
                except Exception:
                    pass
        evaluadas = []
        for c in cs:
            ev = evaluar(c, j)
            if ev:
                evaluadas.append((ev, c))
            time.sleep(0.2)
        evaluadas.sort(key=lambda x: (x[1]['title'] not in recortar, -x[0][0]))
        listo = None
        for (puntos, crop, centro), c in evaluadas[:3 + len(recortar)]:
            ses = sessions
            if c['title'] in recortar:
                if fino[0] is None:
                    fino[0] = new_session('birefnet-portrait')
                ses = [fino[0]]
            for s in ses:
                cut = remove(crop, session=s, post_process_mask=True)
                a = medio.limpiar(cut.getchannel('A'), centro, bordes=not c.get('manual'))
                if a is not None:
                    cut = cut.copy()
                    cut.putalpha(a)
                    listo = (cut, c)
                    break
            if listo:
                break
        if listo:
            cut, c = listo
            open(os.path.join(args.salida, 'm', k + '.png'), 'wb').write(medio.sil_png(cut.getchannel('A')))
            open(os.path.join(args.salida, 'f', k + '.webp'), 'wb').write(medio.color_webp(cut))
            src = c['title'] if c.get('manual') else 'https://commons.wikimedia.org/wiki/' + urllib.parse.quote(c['title'].replace(' ', '_'))
            # '!' adelante: esta foto va antes que la de TheSportsDB (porque la de TheSportsDB se marcó como mala)
            indice[k] = ('!' if 'tsdb' in r.get('no', []) else '') + src
            estado[k] = OK
            stats['con foto'] += 1
        else:
            indice.pop(k, None)
            if 'tsdb' in r.get('no', []):
                indice[k] = '!'      # la de TheSportsDB se descarta aunque no haya otra
            estado[k] = NO
            for d, ext in (('m', '.png'), ('f', '.webp')):   # por si había una de la versión anterior
                try:
                    os.remove(os.path.join(args.salida, d, k + ext))
                except OSError:
                    pass
            stats['sin foto'] += 1
        if k in rev:
            prev[k] = firma(k)
        hechos += 1
        if hechos % 25 == 0:
            guardar()
            print(f'{hechos} procesados · {stats}', flush=True)
    guardar()
    pendientes = sum(1 for j in jug if estado.get(j['k']) not in (OK, NO) or prev.get(j['k'], '') != firma(j['k']))
    print(f'Listo: {hechos} en esta corrida {stats}. Con foto de Commons: {len(indice)}. Pendientes (ya revisados en TheSportsDB): {pendientes}.')
    if args.resumen:
        json.dump({'pendientes': pendientes, 'fotos': len(indice), 'hechos': hechos}, open(args.resumen, 'w'))


if __name__ == '__main__':
    main()
