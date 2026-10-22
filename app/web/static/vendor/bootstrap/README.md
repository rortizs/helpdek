# Bootstrap (copia local)

22/10/2026 - Estos dos archivos son Bootstrap tal como lo publica el proyecto oficial, sin tocar ni una
letra. Los guardo en el repositorio para que el cliente funcione sin Internet (el aula, la demo y las
pruebas no dependen de un CDN) y para que la politica de seguridad del navegador pueda ser estricta
(`script-src 'self'`): ningun script viene de un dominio ajeno.

- Version: **5.3.8**
- Licencia: MIT (<https://github.com/twbs/bootstrap/blob/main/LICENSE>)
- Origen: `https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/` (paquete npm oficial `bootstrap`)

| Archivo | Origen dentro de `dist/` | SHA-256 |
| --- | --- | --- |
| `bootstrap.min.css` | `css/bootstrap.min.css` | `d85327d99c7a3ee1f9b5d0500d1370acea3ad2db39c163c2f51f232baedbdede` |
| `bootstrap.bundle.min.js` | `js/bootstrap.bundle.min.js` | `e4fd49181388c48ec5040bd3fe66f57c29c8e67fcd8502b3354b96ec7ab47cc7` |

Una prueba (`tests/test_week16_cliente_web.py`) recalcula estas sumas: si alguien edita un archivo de
esta carpeta, la prueba falla. Para actualizar Bootstrap se descargan los dos archivos nuevos desde el
mismo origen, se cambian la version y las sumas de esta tabla, y se corre la suite.

El `.min.css` termina con un comentario `sourceMappingURL=bootstrap.min.css.map`; no incluimos el mapa,
asi que si abres las herramientas de desarrollo veras un aviso 404 sobre ese archivo. No afecta nada.
