# Subasta Futbolera

Subasta ciega de futbolistas por posición, para jugar entre amigos. La compu muestra la subasta y cada uno puja desde su teléfono escaneando un QR.

Jugar: https://diegovacapaz.github.io/subasta-futbolera/

## Cómo está armado

- `index.html`: el juego completo (datos de jugadores incluidos).
- `sil/`: siluetas de busto, una por jugador (`tm<id>.png` para los que tienen foto en Transfermarkt, `n-<nombre>-<año>.png` para el resto). `sil/fotos.json` guarda la dirección de la foto de Wikipedia de quienes no tienen foto de Transfermarkt, para mostrarla al revelar.
- Siluetas de medio cuerpo (de la cintura para arriba), en este orden de prioridad:
  - `tsdb/`: recortes de TheSportsDB bajados con su API (`tools/tsdb.py`, workflow `tsdb.yml`). `m/` silueta de medio cuerpo, `f/` foto a color sin fondo, `b/` silueta de los que solo traen la cara.
  - `commons/`: fotos de Wikimedia Commons elegidas automáticamente (una sola persona, hasta la cintura, fondo simple, de su época si se puede) para quienes TheSportsDB no cubre (`tools/commons.py`, workflow `commons.yml`). `indice.json` guarda la página de cada foto en Commons, con su autor y licencia.
  - `sil/`: bustos hechos con la foto de Transfermarkt, como último recurso.
- `revisar.html`: página para revisar las fotos elegidas, marcar las que están mal y proponer otra. Los cambios van a `tools/revision.json` y el proceso de Commons los aplica.
- `tools/medio.py`: el encuadre de medio cuerpo (detecta la cara y corta a la cintura) y los controles de calidad de la silueta.
- `tools/jugadores.json`: lista de jugadores para generar siluetas.
- `tools/siluetas.py`: baja la foto de cada jugador (Transfermarkt o Wikipedia), le quita el fondo con rembg y guarda la silueta.
- `.github/workflows/siluetas.yml`: corre el script en GitHub Actions. Se lanza solo cuando cambia la lista o el script, o a mano desde la pestaña Actions. Si no termina en una corrida, guarda lo hecho y sigue sola.

Detector de caras: YuNet (`tools/yunet.onnx`, OpenCV Zoo, licencia MIT).

Datos: dataset de Transfermarkt (temporada 2025) y una lista de leyendas. Conexión con teléfonos: PeerJS.
