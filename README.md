# Subasta Futbolera

Subasta ciega de futbolistas por posición, para jugar entre amigos. La compu muestra la subasta y cada uno puja desde su teléfono escaneando un QR.

Jugar: https://diegovacapaz.github.io/subasta-futbolera/

## Cómo está armado

- `index.html`: el juego completo (datos de jugadores incluidos).
- `sil/`: siluetas de busto, una por jugador (`tm<id>.png` para los que tienen foto en Transfermarkt, `n-<nombre>-<año>.png` para el resto). `sil/fotos.json` guarda la dirección de la foto de Wikipedia de quienes no tienen foto de Transfermarkt, para mostrarla al revelar.
- `tools/jugadores.json`: lista de jugadores para generar siluetas.
- `tools/siluetas.py`: baja la foto de cada jugador (Transfermarkt o Wikipedia), le quita el fondo con rembg y guarda la silueta.
- `.github/workflows/siluetas.yml`: corre el script en GitHub Actions. Se lanza solo cuando cambia la lista o el script, o a mano desde la pestaña Actions. Si no termina en una corrida, guarda lo hecho y sigue sola.

Datos: dataset de Transfermarkt (temporada 2025) y una lista de leyendas. Conexión con teléfonos: PeerJS.
