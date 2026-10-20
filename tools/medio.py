"""Herramientas para llevar cualquier foto a una silueta de medio cuerpo (de la cintura para arriba)."""
import io

ALTO = 320          # alto de las siluetas de medio cuerpo
MIN_L = 1.9         # la foto tiene que llegar, como mínimo, al pecho (en "alturas de cara" debajo del centro de la cara)
MAX_L = 4.0         # y se corta a la altura de la cintura


def caras(rgb):
    """Caras detectadas, de la más grande a la más chica: [(x, y, w, h), ...]."""
    import cv2
    import numpy as np
    g = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2GRAY)
    det = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    lado = max(24, min(rgb.size) // 16)
    f = det.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=(lado, lado))
    return sorted([tuple(int(v) for v in c) for c in f], key=lambda c: -c[2] * c[3])


def una_cara(rgb):
    """La cara principal, o None si no hay o si es una foto grupal."""
    cs = caras(rgb)
    if not cs:
        return None
    if len(cs) > 1 and cs[1][2] * cs[1][3] >= 0.35 * cs[0][2] * cs[0][3]:
        return None
    return cs[0]


def caja(cara, ancho, alto):
    """Caja de medio cuerpo alrededor de una cara: de arriba de la cabeza a la cintura."""
    x, y, w, h = cara
    cx, cy = x + w / 2, y + h / 2
    return (int(max(0, cx - 2.4 * w)), int(max(0, y - 0.9 * h)),
            int(min(ancho, cx + 2.4 * w)), int(min(alto, cy + MAX_L * h)))


def alcance(cara, fondo_y):
    """Cuántas 'alturas de cara' llega la foto por debajo del centro de la cara."""
    x, y, w, h = cara
    return (fondo_y - (y + h / 2)) / h


def blanco(rgba):
    from PIL import Image
    f = Image.new('RGB', rgba.size, (255, 255, 255))
    f.paste(rgba, mask=rgba.getchannel('A'))
    return f


def limpiar(alpha, centro):
    """Deja solo la mancha de la persona y descarta formas que no parecen un medio cuerpo.
    Devuelve el canal alfa limpio (PIL L) o None."""
    import cv2
    import numpy as np
    from PIL import Image
    a = np.array(alpha)
    fg = (a > 128).astype('uint8')
    if fg.mean() < 0.12 or fg.mean() > 0.85:
        return None
    if fg[0].mean() > 0.5:          # el fondo de arriba quedó pegado
        return None
    n, lab = cv2.connectedComponents(fg)
    if n > 2:
        cy, cx = int(min(centro[1], a.shape[0] - 1)), int(min(centro[0], a.shape[1] - 1))
        keep = lab[cy, cx] if lab[cy, cx] > 0 else 1 + int(np.argmax(np.bincount(lab.ravel())[1:]))
        a = (a * cv2.dilate((lab == keep).astype('uint8'), np.ones((5, 5), 'uint8'))).astype('uint8')
        fg = (a > 128).astype('uint8')
    cy, cx = int(min(centro[1], a.shape[0] - 1)), int(min(centro[0], a.shape[1] - 1))
    if not fg[cy, cx]:               # la cara tiene que estar dentro de la silueta
        return None
    cs, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cs, key=cv2.contourArea)
    hull = cv2.contourArea(cv2.convexHull(c))
    if not hull or cv2.contourArea(c) / hull < 0.72:
        return None
    return Image.fromarray(a)


def sil_png(alpha, alto=ALTO):
    """Silueta negra (PNG con transparencia) a partir de un canal alfa."""
    from PIL import Image
    bb = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
    if not bb:
        return None
    alpha = alpha.crop(bb)
    w, h = alpha.size
    alpha = alpha.resize((max(1, round(w * alto / h)), alto), Image.LANCZOS)
    alpha = alpha.point(lambda v: 0 if v < 24 else 255 if v > 232 else v // 16 * 16)
    out = Image.new('LA', alpha.size, 0)
    out.putalpha(alpha)
    buf = io.BytesIO()
    out.save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def color_webp(rgba, alto=480):
    """Foto a color sin fondo, achicada, en WebP."""
    from PIL import Image
    bb = rgba.getchannel('A').point(lambda v: 255 if v > 40 else 0).getbbox()
    if bb:
        rgba = rgba.crop(bb)
    if rgba.height > alto:
        rgba = rgba.resize((max(1, round(rgba.width * alto / rgba.height)), alto), Image.LANCZOS)
    buf = io.BytesIO()
    rgba.save(buf, 'WEBP', quality=80, method=6)
    return buf.getvalue()


def de_recorte(rgba):
    """Medio cuerpo a partir de un recorte ya sin fondo. Devuelve (rgba recortado o None, alcance)."""
    bb = rgba.getchannel('A').point(lambda v: 255 if v > 40 else 0).getbbox()
    if not bb:
        return None, 0
    rgba = rgba.crop(bb)
    c = una_cara(blanco(rgba))
    if not c:
        return None, 0
    L = alcance(c, rgba.height)
    if L < MIN_L:
        return None, L
    b = caja(c, rgba.width, rgba.height)
    out = rgba.crop(b)
    centro = (c[0] + c[2] / 2 - b[0], c[1] + c[3] / 2 - b[1])
    a = limpiar(out.getchannel('A'), centro)
    if a is None:
        return None, L
    out.putalpha(a)
    return out, L
