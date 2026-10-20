#!/usr/bin/env python3
"""Genera las siluetas de busto de la Subasta Futbolera.

Para cada jugador de tools/jugadores.json:
  1. Baja su foto: la de Transfermarkt y, si no tiene o falla, la de Wikipedia.
  2. Le quita el fondo con rembg (modelo de personas) y la pinta de negro.
  3. Guarda sil/<clave>.png (320 px de alto, fondo transparente).

Es incremental: sil/estado.json recuerda qué jugadores ya se procesaron, así que
se puede cortar y volver a correr. Las fotos de Wikipedia que se usen para revelar
quedan anotadas en sil/fotos.json (solo la dirección, la foto no se copia).
"""
import argparse, io, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

UA = 'SubastaFutbolera/1.0 (https://github.com/diegovacapaz/subasta-futbolera; juego entre amigos)'
TM = 'https://img.a.transfermarkt.technology/portrait/'
ALTO = 320
# Modelos de recorte, en orden: si el primero deja fondo pegado, se prueba el segundo.
MODELOS = ('isnet-general-use', 'u2net_human_seg')
# Estados de esta versión del recorte. Los de versiones anteriores se vuelven a procesar.
OK, SIN, FALLO = 'ok2', 'sin-foto2', 'fallo2'


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def strip(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn')


def wiki(name, by):
    """Fotos candidatas de Wikipedia (inglés y castellano), [] si no hay, None si falló la red."""
    words = [w for w in re.split(r"[\s'.-]+", strip(name).lower()) if len(w) >= 4]
    found = []
    for lang, q in (('en', name + ' footballer'), ('es', name + ' futbolista')):
        url = f'https://{lang}.wikipedia.org/w/api.php?' + urllib.parse.urlencode({
            'action': 'query', 'format': 'json', 'formatversion': 2, 'generator': 'search', 'gsrlimit': 4,
            'gsrsearch': q, 'prop': 'pageimages|description', 'piprop': 'thumbnail', 'pithumbsize': 480})
        try:
            j = json.loads(get(url))
        except Exception:
            return None
        pages = sorted((j.get('query') or {}).get('pages') or [], key=lambda p: p.get('index', 0))
        for p in pages:
            src = (p.get('thumbnail') or {}).get('source')
            desc = strip(p.get('description') or '')
            if not src or not re.search(r'footballer|football player|futbolista|soccer player|goalkeeper|arquero|portero|football manager|entrenador', desc, re.I):
                continue
            if re.search(r'stadium|estadio|club|season|temporada|team|equipo|film|pelicula|song|cancion|award|premio|cup|copa', desc, re.I):
                continue
            if words and not any(w in strip(p.get('title', '')).lower() for w in words):
                continue
            m = re.search(r'\b(18|19|20)\d{2}\b', desc)
            if m and by and abs(int(m.group(0)) - by) > 1:
                continue
            if src not in found:
                found.append(src)
            break
        time.sleep(0.2)
    return found


def encuadre(img):
    """Recorta un busto alrededor de la cara más grande (sirve para fotos de cuerpo entero).
    Devuelve la imagen recortada, el centro de la cara (o None si no encontró caras) y si parece foto grupal."""
    import cv2
    import numpy as np
    g = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    det = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    lado = max(24, min(img.size) // 12)
    caras = det.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=(lado, lado))
    if len(caras) == 0:
        return img, None, False
    caras = sorted(caras, key=lambda f: -f[2] * f[3])
    grupal = len(caras) > 1 and caras[1][2] * caras[1][3] >= 0.35 * caras[0][2] * caras[0][3]
    x, y, w, h = caras[0]
    cx = x + w / 2
    caja = (max(0, cx - 1.7 * w), max(0, y - 0.9 * h), min(img.width, cx + 1.7 * w), min(img.height, y + 3.2 * h))
    caja = tuple(int(round(v)) for v in caja)
    return img.crop(caja), (cx - caja[0], y + h / 2 - caja[1]), grupal


def silueta(raw, sessions):
    """PNG de la silueta negra, o None si ningún modelo da un recorte que parezca una persona."""
    from PIL import Image
    import numpy as np
    from rembg import remove
    img = Image.open(io.BytesIO(raw)).convert('RGB')
    if max(img.size) < 320:   # las fotos chicas recortan mejor un poco agrandadas
        k = 320 / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    img, cara, grupal = encuadre(img)
    if grupal:
        return None   # en una foto con varios, la silueta mezcla personas
    if max(img.size) < 320:
        k = 320 / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
        if cara:
            cara = (cara[0] * k, cara[1] * k)
    a = None
    for session in sessions:
        m = np.array(remove(img, session=session, post_process_mask=True).getchannel('A'))
        fg = m > 128
        # Señales de recorte malo: casi nada, casi todo, o el fondo de arriba pegado a la cabeza.
        if 0.06 <= fg.mean() <= 0.9 and fg[0].mean() <= 0.8:
            a = m
            break
    if a is None:
        return None
    # Quedarse solo con la mancha de la persona (la que tiene la cara, o la más grande): limpia vecinos y puntitos.
    import cv2
    n, lab = cv2.connectedComponents((a > 128).astype('uint8'))
    if n > 2:
        if cara and lab[int(min(cara[1], a.shape[0] - 1)), int(min(cara[0], a.shape[1] - 1))] > 0:
            keep = lab[int(min(cara[1], a.shape[0] - 1)), int(min(cara[0], a.shape[1] - 1))]
        else:
            keep = 1 + int(np.argmax(np.bincount(lab.ravel())[1:]))
        mask = cv2.dilate((lab == keep).astype('uint8'), np.ones((5, 5), 'uint8'))
        a = (a * mask).astype('uint8')
    ys, xs = np.where(a > 40)
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = a.shape
    alpha = Image.fromarray(a).resize((max(1, round(w * ALTO / h)), ALTO), Image.LANCZOS)
    alpha = alpha.point(lambda v: 0 if v < 24 else 255 if v > 232 else v // 16 * 16)   # menos tonos: pesa menos
    out = Image.new('LA', alpha.size, 0)
    out.putalpha(alpha)
    buf = io.BytesIO()
    out.save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lista', default='tools/jugadores.json')
    ap.add_argument('--salida', default='sil')
    ap.add_argument('--minutos', type=float, default=320, help='tiempo máximo de trabajo')
    ap.add_argument('--limite', type=int, default=0, help='máximo de jugadores en esta corrida (0 = todos)')
    ap.add_argument('--reintentar', action='store_true', help='volver a probar los que no tuvieron foto')
    ap.add_argument('--resumen', default='', help='archivo donde dejar el resumen en JSON')
    args = ap.parse_args()

    from rembg import new_session
    sessions = [new_session(m) for m in MODELOS]
    os.makedirs(args.salida, exist_ok=True)
    pe, pf = os.path.join(args.salida, 'estado.json'), os.path.join(args.salida, 'fotos.json')
    estado = json.load(open(pe)) if os.path.exists(pe) else {}
    fotos = json.load(open(pf)) if os.path.exists(pf) else {}
    jug = json.load(open(args.lista))

    def guardar():
        json.dump(estado, open(pe, 'w'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        json.dump(fotos, open(pf, 'w'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)

    fin = time.time() + args.minutos * 60
    hechos = cuenta = 0
    stats = {OK: 0, SIN: 0, FALLO: 0, 'red': 0}
    for j in jug:
        k = j['k']
        prev = estado.get(k)
        if prev == OK or (prev in (SIN, FALLO) and not args.reintentar):
            continue
        if time.time() > fin or (args.limite and cuenta >= args.limite):
            break
        cuenta += 1
        fotos.pop(k, None)
        fuentes = [TM + 'big/' + j['img'], TM + 'header/' + j['img']] if j['img'] else []
        png, red = None, False
        for u in fuentes:
            try:
                raw = get(u)
            except Exception:
                continue
            png = silueta(raw, sessions)
            break
        if png is None:
            ws = wiki(j['n'], j['by'])
            if ws is None:
                red = True
            else:
                for w in ws:
                    try:
                        png = silueta(get(w), sessions)
                    except Exception:
                        red = True
                        continue
                    if png:
                        if not j['img']:
                            fotos[k] = w   # para mostrar al revelar a quien no tiene foto de Transfermarkt
                        break
                if not png and ws and not j['img']:
                    fotos[k] = ws[0]       # sin silueta, pero sirve para revelar
                if png:
                    red = False
            time.sleep(0.3)
        if png:
            open(os.path.join(args.salida, k + '.png'), 'wb').write(png)
            estado[k] = OK
        elif red:
            stats['red'] += 1      # sin estado: se reintenta en la próxima corrida
            continue
        else:
            estado[k] = SIN if not fuentes and k not in fotos else FALLO
            try:
                os.remove(os.path.join(args.salida, k + '.png'))   # por si había una de una versión anterior
            except OSError:
                pass
        stats[estado[k]] += 1
        hechos += 1
        if hechos % 100 == 0:
            guardar()
            print(f'{hechos} procesados · {stats}', flush=True)
        time.sleep(0.15)
    guardar()
    pendientes = sum(1 for j in jug if estado.get(j['k']) not in (OK, SIN, FALLO))
    total_ok = sum(1 for v in estado.values() if v == OK)
    print(f'Listo: {hechos} procesados en esta corrida {stats}. Siluetas: {total_ok}. Pendientes: {pendientes}.')
    if args.resumen:
        json.dump({'pendientes': pendientes, 'siluetas': total_ok, 'hechos': hechos}, open(args.resumen, 'w'))


if __name__ == '__main__':
    main()
