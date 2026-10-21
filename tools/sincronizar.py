#!/usr/bin/env python3
"""Pasa las marcas de revisar.html (formulario de Google → hoja publicada como CSV) a tools/revision.json.

Cada fila del CSV es el estado completo de una ficha en un momento:
  clave = jugador, accion = "marca", valor = {"id": foto juzgada, "mal", "recorte", "url", "t"}, revisor = nombre.
Por cada (jugador, foto) vale la fila más nueva, así desmarcar funciona y las fotos ya descartadas siguen descartadas
aunque después se juzgue otra. El link propuesto sale de la fila más nueva del jugador.
Las correcciones a mano que haya en tools/revision-manual.json se suman.
Escribe el archivo solo si cambió; imprime "cambio" o "igual".
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


def main():
    claves = {j['k'] for j in leer(os.path.join(AQUI, 'jugadores.json'), [])}
    txt = open(sys.argv[1]).read() if len(sys.argv) > 1 else bajar()
    rev = sumar(armar(txt, claves), leer(os.path.join(AQUI, 'revision-manual.json'), {}))
    for r in rev.values():
        for campo in ('no', 'recortar'):
            if campo in r:
                r[campo] = sorted(set(r[campo]))
    p = os.path.join(AQUI, 'revision.json')
    nuevo = json.dumps(rev, ensure_ascii=False, indent=1, sort_keys=True) + '\n'
    viejo = open(p).read() if os.path.exists(p) else ''
    if json.loads(viejo or '{}') == rev:
        print('igual')
        return
    open(p, 'w').write(nuevo)
    print('cambio', len(rev))


if __name__ == '__main__':
    main()
