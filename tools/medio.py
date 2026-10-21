"""Herramientas para llevar cualquier foto a una silueta de medio cuerpo (de la cintura para arriba)."""
import io, os

ALTO = 320          # alto de las siluetas de medio cuerpo
MIN_L = 1.9         # la foto tiene que llegar, como mínimo, al pecho (en "alturas de cara" debajo del centro de la cara)
MAX_L = 4.0         # y se corta a la altura de la cintura


YUNET = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yunet.onnx')   # detector de caras (OpenCV Zoo, MIT)


def caras(rgb):
    """Caras detectadas (también de perfil o chicas), de la más grande a la más chica: [(x, y, w, h), ...]."""
    import cv2
    import numpy as np
    img = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]
    if os.path.exists(YUNET):
        det = cv2.FaceDetectorYN.create(YUNET, '', (w, h), 0.75, 0.3, 5000)
        det.setInputSize((w, h))
        _, f = det.detect(img)
        f = [] if f is None else [(int(c[0]), int(c[1]), int(c[2]), int(c[3])) for c in f]
    else:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        det = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        lado = max(24, min(rgb.size) // 16)
        f = [tuple(int(v) for v in c) for c in det.detectMultiScale(g, scaleFactor=1.1, minNeighbors=5, minSize=(lado, lado))]
    return sorted([c for c in f if c[2] > 0 and c[3] > 0], key=lambda c: -c[2] * c[3])


def una_cara(rgb):
    """La cara principal, o None si no hay o si hay otra persona dentro del encuadre de medio cuerpo."""
    cs = caras(rgb)
    if not cs:
        return None
    p = cs[0]
    bx = caja(p, rgb.width, rgb.height)
    for c in cs[1:]:
        cx, cy = c[0] + c[2] / 2, c[1] + c[3] / 2
        dentro = bx[0] <= cx <= bx[2] and bx[1] <= cy <= bx[3]
        if (dentro and c[2] * c[3] >= 0.06 * p[2] * p[3]) or c[2] * c[3] >= 0.35 * p[2] * p[3]:
            return None     # otra persona en el encuadre (o una foto grupal)
    return p


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


def limpiar(alpha, centro, bordes=False):
    """Deja solo la mancha de la persona y descarta formas que no parecen un medio cuerpo.
    Con bordes=True (fotos con fondo) también descarta si la silueta se pega a los costados del encuadre,
    que suele ser otra persona al lado o el fondo que quedó pegado. Devuelve el canal alfa limpio o None."""
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
    if bordes and max(fg[:, 0].mean(), fg[:, -1].mean()) > 0.35:
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
