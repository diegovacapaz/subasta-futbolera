#!/usr/bin/env python3
"""Pasa las marcas de revisar.html (formulario de Google → hoja publicada como CSV) a tools/revision.json.

Cada fila del CSV es el estado completo de una ficha en un momento:
  clave = jugador, accion = "marca", valor = {"id": foto juzgada, "mal", "recorte", "url", "t"}, revisor = nombre.
Por cada (jugador, foto) vale la fila más nueva, así desmarcar funciona y las fotos ya descartadas siguen descartadas
aunque después se juzgue otra. El link propuesto sale de la fila más nueva del jugador.
Las correcciones a mano que haya en tools/revision-manual.json se suman.

También toma los jugadores agregados desde la página (accion = "alta", valor = {tipo, n, p, nat, by, club, lg, v,
precio, foto, baja, t}): los guarda en tools/altas.json (en orden de alta, nunca se borran: una baja queda marcada)
y los suma a tools/jugadores.json para que los procesos les busquen foto. Si trajeron link de foto, va primero.
Escribe los archivos solo si cambiaron; imprime "cambio N" o "igual", y "altas" si cambió la lista de agregados.
"""
import csv, io, json, os, sys, urllib.request

CSV = ('https://docs.google.com/spreadsheets/d/e/2PACX-1vR8SOBIPVzFFUOIEp7LPiOu76u5JYCZ5XD8Gsn-CN_ps-TV7-ziAKmKbTv8CMYZgGrAmy4iMNN7sMqG'
       '/pub?gid=1439134911&single=true&output=csv')
AQUI = os.path.dirname(os.path.abspath(__file__))


def leer(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


def bajar():
    req = urllib.request.Request(CSV, headers={'User-Agent': 'subasta-futbolera', 'Cache-Control': 'no-cache'})
    return urllib.request.urlopen(req, timeout=60).read().decode('utf-8')


def armar(txt, claves):
    ult, por_jugador = {}, {}
    for f in csv.DictReader(io.StringIO(txt)):
        k = (f.get('clave') or '').strip()
        if f.get('accion') != 'marca' or k not in claves:
            continue
        try:
            v = json.loads(f.get('valor') or '')
            t = float(v['t'])
        except Exception:
            continue
        foto = str(v.get('id') or '')[:400]
        url = str(v.get('url') or '').strip()
        if url and (not url.startswith(('https://', 'http://')) or len(url) > 1000 or any(c.isspace() for c in url)):
            url = ''
        e = {'t': t, 'mal': bool(v.get('mal')), 'recorte': bool(v.get('recorte')), 'url': url}
        if foto and ((k, foto) not in ult or t >= ult[(k, foto)]['t']):
            ult[(k, foto)] = e
        if k not in por_jugador or t >= por_jugador[k]['t']:
            por_jugador[k] = e

    rev = {}
    for (k, foto), e in sorted(ult.items()):
        r = rev.setdefault(k, {})
        if e['mal'] or (e['recorte'] and foto == 'tsdb'):      # el recorte de TheSportsDB no se rehace: se reemplaza
            r.setdefault('no', []).append(foto)
        elif e['recorte']:
            r.setdefault('recortar', []).append(foto)
    for k, e in por_jugador.items():
        if e['url']:
            rev.setdefault(k, {})['url'] = e['url']
    return {k: r for k, r in rev.items() if r}


def sumar(base, extra):
    for k, r in extra.items():
        d = base.setdefault(k, {})
        for campo in ('no', 'recortar'):
            vals = list(dict.fromkeys(d.get(campo, []) + r.get(campo, [])))
            if vals:
                d[campo] = vals
        if r.get('url') and not d.get('url'):
            d['url'] = r['url']
    return base


TIPOS = {'leyenda', 'troll', 'actual'}
PUESTOS = {'ARQ', 'LD', 'DFC', 'LI', 'MC', 'ED', 'EI', 'DC'}


def num(x, lo, hi, d=None):
    try:
        x = float(x)
        return round(x, 1) if lo <= x <= hi else d
    except Exception:
        return d


def texto(x, n=60):
    return ' '.join(str(x or '').split())[:n]


def altas(txt):
    """Aplica las altas del CSV a tools/altas.json. Devuelve (lista, cambió)."""
    p = os.path.join(AQUI, 'altas.json')
    lista = leer(p, [])
    pos = {a['k']: i for i, a in enumerate(lista)}
    nuevas, primero = {}, {}
    for f in csv.DictReader(io.StringIO(txt)):
        k = texto(f.get('clave'), 80)
        if f.get('accion') != 'alta' or not k.startswith('a-'):
            continue
        try:
            v = json.loads(f.get('valor') or '')
            t = float(v['t'])
        except Exception:
            continue
        tipo, n, p_ = v.get('tipo'), texto(v.get('n')), v.get('p')
        if tipo not in TIPOS or not n or p_ not in PUESTOS:
            continue
        foto = texto(v.get('foto'), 1000)
        if foto and (not foto.startswith(('https://', 'http://')) or ' ' in foto):
            foto = ''
        a = {'k': k, 'tipo': tipo, 'n': n, 'p': p_, 'nat': texto(v.get('nat'), 40), 'by': None if tipo == 'troll' else num(v.get('by'), 1850, 2015),
             'club': '' if tipo == 'troll' else texto(v.get('club'), 50), 'lg': texto(v.get('lg'), 8) if tipo == 'actual' else '',
             'v': num(v.get('v'), 0, 300, 1), 'precio': num(v.get('precio'), 1, 300, 40) if tipo == 'troll' else None,
             'foto': foto, 'baja': bool(v.get('baja')), 'quien': texto(f.get('revisor'), 40), 't': t}
        if a['by']:
            a['by'] = int(a['by'])
        primero[k] = min(t, primero.get(k, t))
        if k not in nuevas or t >= nuevas[k]['t']:
            nuevas[k] = a
    cambio = False
    for a in sorted(nuevas.values(), key=lambda a: primero[a['k']]):    # en orden de alta
        if a['k'] in pos:
            viejo = lista[pos[a['k']]]
            if a['t'] > viejo.get('t', 0) and a != viejo:
                lista[pos[a['k']]] = a
                cambio = True
        else:
            pos[a['k']] = len(lista)
            lista.append(a)
            cambio = True
    if cambio:
        json.dump(lista, open(p, 'w'), ensure_ascii=False, indent=1)
    return lista, cambio


def jugadores_con_altas(lista):
    """Suma (o saca, si se dieron de baja) los agregados en tools/jugadores.json."""
    p = os.path.join(AQUI, 'jugadores.json')
    jug = leer(p, [])
    antes = json.dumps(jug)
    por_k = {j['k']: i for i, j in enumerate(jug)}
    for a in lista:
        if a.get('baja'):
            jug = [j for j in jug if j['k'] != a['k']]
            por_k = {j['k']: i for i, j in enumerate(jug)}
            continue
        e = {'k': a['k'], 'n': a['n'], 'by': a.get('by'), 'img': '', 'v': 0.5 if a['tipo'] == 'troll' else a.get('v') or 1,
             'ley': 1 if a['tipo'] == 'leyenda' else 0, 'lg': {'leyenda': 'LEY', 'troll': 'TRL'}.get(a['tipo'], a.get('lg') or 'ARG1'),
             'club': a.get('club') or '', 'alta': 1}
        if a['tipo'] == 'troll':
            e['troll'] = 1
        if a['k'] in por_k:
            jug[por_k[a['k']]] = e
        else:
            por_k[a['k']] = len(jug)
            jug.append(e)
    if json.dumps(jug) != antes:
        json.dump(jug, open(p, 'w'), ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return jug


def pendientes():
    """Cuántas fichas de revision.json todavía no rehizo el proceso de Commons (su firma no coincide)."""
    import glob
    rev = leer(os.path.join(AQUI, 'revision.json'), {})
    hechas = {}
    for f in glob.glob(os.path.join(AQUI, '..', 'commons', 'rev-*.json')):
        hechas.update(leer(f, {}))
    return sum(1 for k, r in rev.items() if hechas.get(k) != json.dumps(r, sort_keys=True))


def main():
    if sys.argv[1:] == ['--pendientes']:
        print(pendientes())
        return
    txt = open(sys.argv[1]).read() if len(sys.argv) > 1 else bajar()
    lista, cambio_altas = altas(txt)
    claves = {j['k'] for j in jugadores_con_altas(lista)}
    # a los agregados se les busca foto (con el link que trajeron, si trajeron)
    extra = {a['k']: ({'url': a['foto']} if a.get('foto') else {}) for a in lista if not a.get('baja')}
    extra = sumar(extra, leer(os.path.join(AQUI, 'revision-manual.json'), {}))
    rev = sumar(armar(txt, claves), extra)
    for r in rev.values():
        for campo in ('no', 'recortar'):
            if campo in r:
                r[campo] = sorted(set(r[campo]))
    p = os.path.join(AQUI, 'revision.json')
    nuevo = json.dumps(rev, ensure_ascii=False, indent=1, sort_keys=True) + '\n'
    viejo = open(p).read() if os.path.exists(p) else ''
    sufijo = ' altas' if cambio_altas else ''
    if json.loads(viejo or '{}') == rev:
        print('igual' + sufijo)
        return
    open(p, 'w').write(nuevo)
    print('cambio', len(rev), sufijo.strip())


if __name__ == '__main__':
    main()
