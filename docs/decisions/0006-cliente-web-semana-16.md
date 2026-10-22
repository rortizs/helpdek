# ADR 0006 - Cliente web de la semana 16

- Fecha: 22/10/2026
- Autor: Ing. Richard Ortiz
- Estado: aceptado
- Contexto del curso: semana 16, "Cliente web responsivo o aplicación cliente" (Programación II)

## Qué tenemos que lograr

Hasta la semana 15 la API se probaba con Postman, `/docs` y pytest. Esta semana aparece **otro cliente**: un
navegador. Los indicadores de la semana son tres, y los uso como criterio de aceptación:

1. El cliente **consume la API sin acceso directo a la base de datos** (HTTP + JSON, nada de SQLAlchemy en el navegador).
2. Da **retroalimentación útil**: el usuario siempre sabe si está cargando, si algo falló o si funcionó.
3. **Funciona en pantallas razonables**: del teléfono (390 px) al escritorio (1280 px).

Además, el curso pide formularios, manejo seguro del token, accesibilidad y diseño responsivo.

## 1. Decisión: un cliente estático (HTML + Bootstrap + JavaScript), no plantillas del servidor

| Opción | A favor | En contra |
| --- | --- | --- |
| **Plantillas del servidor** (Jinja2 devolviendo HTML) | Menos JavaScript; el servidor controla todo | El navegador ya no consume la API: el servidor "renderiza" y habla directo con los servicios. Se pierde la lección de la semana 16 y la API de la 14 queda sin uso real. Además hace falta CSRF y sesiones con cookies |
| **SPA con framework** (React, Vue...) | Es lo que verán en el trabajo | Exige Node, empaquetado y un curso aparte; esta clase es de Python |
| **Cliente estático + `fetch`** (la elegida) | Es literalmente "un cliente HTTP más": cada pantalla es una llamada a la API que ya probamos. Sin paso de compilación. Bootstrap da accesibilidad y responsividad de base | Hay que cuidar el XSS a mano (ver sección 3) |

Se eligió Bootstrap 5 + HTML por pedido de la cátedra. FastAPI sirve los archivos con `StaticFiles` en `/app`
(`app/web/static_files.py`); no hace falta un servidor aparte.

Bootstrap está **copiado en el repositorio** (`app/web/static/vendor/bootstrap/`, versión 5.3.8, con su SHA-256 en un README y
una prueba que lo recalcula). Así el aula, la demo y las pruebas funcionan sin Internet, y la política de seguridad puede
decir `script-src 'self'`: ningún script sale de un dominio ajeno.

### Estructura

| Pieza | Qué hace |
| --- | --- |
| `index.html` + `js/pages/login.js` | Ingreso: `POST /api/auth/login`, guarda el token, `GET /api/users/me` |
| `tickets.html` + `tickets.js` | Lista con filtros y paginación (`GET /api/tickets`, total en `X-Total-Count`); tabla en escritorio, tarjetas en teléfono |
| `ticket-new.html` + `ticket-new.js` | Alta (`POST /api/tickets`); valida localmente y muestra los 422 del servidor por campo |
| `ticket.html` + `ticket.js` | Detalle, comentarios, historial y acciones **según el rol** (asignar, estado, prioridad, cancelar) |
| `notifications.html` + `notifications.js` | Avisos sin leer y "marcar todo como leído" |
| `js/api.js` | **Único** lugar con `fetch`: Bearer, sobre de error, 401, fallo de red |
| `js/session.js` | **Único** lugar que toca el token |
| `js/ui.js`, `js/layout.js` | Piezas de interfaz (alertas, toasts, botones ocupados) y menú común |
| `js/format.js`, `js/rules.js`, `js/validation.js` | Funciones puras (se prueban con Node) |

La estructura repite lo que ya hicimos en el servidor: una sola puerta hacia afuera (`api.js`, como `HelpDeskFacade`) y reglas puras separadas
de la presentación.

## 2. El cliente no es la autoridad

`rules.js` y `validation.js` **copian** reglas de la API (flujo de estados, categorías, largo del título) para no ofrecer botones que van a
fallar y para avisar rápido. Pero cualquiera puede editar el JavaScript en su navegador o usar `curl`. Por eso:

- La API vuelve a validar todo. Probé a mano forzando en el navegador una opción que el cliente no ofrece (pasar de "En progreso" a
  "Cerrado"): la API respondió 409 y la pantalla mostró "Ese cambio de estado no está permitido…" (captura `detalle-tecnico-error-409-1280.png`).
- Cada acción maneja 403, 404, 409 y 422 con un mensaje en español, no con un error técnico.
- Los mensajes de la API están en inglés; `api.js` los traduce con una tabla y **nunca** muestra el texto crudo del servidor.

## 3. Dónde guardar el token (la decisión de seguridad)

La amenaza real de un cliente web con JavaScript es el **XSS**: si un atacante logra ejecutar su código en nuestra página, todo lo que
JavaScript pueda leer, él también lo lee.

| Dónde | Lo bueno | Lo malo |
| --- | --- | --- |
| `localStorage` | Sobrevive al cerrar el navegador | Un XSS lo lee y se queda días. **Descartada** |
| **`sessionStorage`** (la elegida) | Muere al cerrar la pestaña; no se comparte entre pestañas; exposición mínima | Un XSS lo puede leer mientras la pestaña está abierta; hay que ingresar de nuevo en otra pestaña |
| Cookie `HttpOnly` | JavaScript **no** puede leerla: es la mejor defensa contra el robo por XSS | El navegador la manda sola en cada petición, lo que abre el **CSRF**; exige que la API emita la cookie y un token anti-CSRF. Es un cambio en el servidor, no en el cliente |

Elegí `sessionStorage` porque nuestra API usa `Authorization: Bearer` (semana 14) y porque es un equilibrio razonable para un curso. Si el
sistema fuera de producción con datos sensibles, la cookie `HttpOnly` + `SameSite` + CSRF sería la mejora.

Como `sessionStorage` no protege contra XSS, **la defensa es no dejar entrar XSS**, en capas:

1. **Nunca `innerHTML` con datos de la API.** `ui.js` crea nodos y asigna `textContent`; sus atributos prohíben `on*`, `style` y `javascript:`.
   Una prueba de pytest falla si alguna palabra `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval` o `document.write` aparece en el código
   del cliente. Lo comprobé en vivo: un comentario `<script>alert(1)</script> <img src=x onerror=alert(2)>` se muestra como texto.
2. **CSP estricta** (`Content-Security-Policy` en cada archivo de `/app`): `script-src 'self'`, sin scripts ni estilos en línea, `frame-ancestors 'none'`.
   Si algo se escapara, el navegador no ejecuta el script inyectado. Por eso el HTML no tiene `onclick` ni `<script>` con cuerpo (también lo prueba pytest).
3. **Vida corta** del token (`ACCESS_TOKEN_MINUTES`, 60 por defecto). `session.js` guarda su hora de vencimiento y lo descarta solo; si la API
   contesta 401, `api.js` borra la sesión y lleva al ingreso con el aviso "tu sesión venció".
4. **Cerrar sesión** borra el token local y, con `pageshow`, una pantalla restaurada del caché del navegador no queda mostrando datos de una sesión cerrada.
5. El token no viaja por la URL ni se imprime en consola.

Límite honesto: JWT es sin estado, así que "cerrar sesión" no invalida el token en el servidor; solo deja de usarlo el navegador. Un *refresh token* y
una lista de revocación quedan fuera de esta semana.

## 4. Mismo origen hoy; CORS aparece en la semana 17

El cliente y la API se sirven desde **el mismo host y puerto** (`http://localhost:8000/app` llama a `/api`). Para el navegador eso es el *mismo origen*, así que
**no hace falta CORS**: la ruta de la API es relativa (`API_BASE = "/api"` en `api.js`) y la CSP incluso fija `connect-src 'self'`.

CORS (Cross-Origin Resource Sharing) aparece cuando el cliente y la API viven en orígenes distintos: otro dominio, otro puerto (por ejemplo un cliente en
`:5173` y la API en `:8000`) o una app móvil web. Entonces el navegador bloquea la lectura de la respuesta salvo que la API la permita con
cabeceras `Access-Control-Allow-*`. En la **semana 17** (integración y despliegue) lo configuramos de forma explícita y mínima: orígenes permitidos por lista,
no `*`. El único valor que cambiaría en el cliente es `API_BASE`, y habría que ajustar `connect-src`.

## 5. Accesibilidad y diseño responsivo

Elegí lo que se puede verificar, no una lista de buenas intenciones:

- **Estructura**: `lang="es"`, un `<h1>` por página, `<label for>` en cada campo, tablas con `<th scope>` y `<caption>`, regiones con `aria-labelledby`.
- **Teclado**: enlace "Saltar al contenido" como primer elemento; todo es botón o enlace real (nada de `div` clicables); foco visible de 3 px.
- **Foco administrado**: tras navegar o redibujar, el foco va al `<h1>` (`tabindex="-1"`); si una validación falla, al primer campo con error; si una acción de la API
  falla, a la alerta; al comentar, al título de la sección de comentarios. Sin esto, tras un `replaceChildren` el teclado cae al `<body>`.
- **Anuncios a lectores de pantalla**: errores en una región `aria-live="assertive"` (`role="alert"`), éxitos como toast en una región `aria-live="polite"`,
  contador de avisos con texto oculto "(3 avisos sin leer)", botones ocupados con `aria-busy`.
- **Errores de formulario** con `aria-invalid` + `aria-describedby` apuntando al mensaje.
- **Color nunca solo**: los estados y prioridades llevan texto además de color. Contrastes medidos (WCAG AA pide 4.5:1 en texto normal):

| Combinación | Razón |
| --- | --- |
| Texto principal `#14323a` sobre fondo `#f3f6f7` | 12.5 |
| Blanco sobre botón/marca `#0b5c6b` | 7.6 |
| Enlaces `#0b5c6b` sobre fondo | 7.0 |
| Estados: abierto 7.6, en progreso 5.0, resuelto 6.4, cerrado 7.6, cancelado 8.3 | todas ≥ 5.0 |
| Prioridades: baja 8.7, media 7.2, alta 6.8, crítica 6.6 | todas ≥ 6.6 |
| Rojo de error `#b42318` sobre fondo | 6.1 |
| Menú (blanco al 88 % sobre el degradado) | 6.3 a 11.3 |
| Botón secundario `#495057` sobre fondo | 7.5 |

  Los valores por defecto de Bootstrap que **no** llegaban (azul de enlace 4.2, rojo `#dc3545` 4.0, gris secundario 4.3, menú al 55 %) se sobrescriben en `css/app.css`.
- **Responsivo**: la lista es **tabla** desde 768 px y **tarjetas** en teléfono (una tabla de 7 columnas no cabe en 390 px y el scroll horizontal es mala experiencia);
  filtros apilados, botones de 44 px de alto mínimo en pantallas chicas, y `prefers-reduced-motion` respetado. Verifiqué que ninguna pantalla tiene scroll horizontal a 390 px.
- **Estados de la interfaz** en todas las pantallas: *cargando* (spinner con `role="status"`, botón deshabilitado para evitar el doble clic), *error* (alerta con mensaje en español)
  y *éxito* (toast; si hay redirección, el aviso se pasa a la página siguiente).

## 6. Qué no hace (límites)

- No hay *refresh token*, ni "recordarme", ni revocación (ver sección 3).
- La cancelación usa `window.confirm()` nativo: simple y accesible, pero no se puede estilizar.
- Un solicitante no puede pedir nombres de otras personas a la API (`GET /api/users` es solo para el personal), así que ve "Soporte" en lugar del nombre del técnico.
- Los textos de los avisos y del historial los escribe el servidor en inglés; el cliente traduce el historial pero muestra los avisos tal como llegan.
- Sin *Subresource Integrity*: no hace falta porque Bootstrap no viene de un CDN; la integridad se vigila con la suma SHA-256 y una prueba.
- Las fechas de la API no llevan zona (hora de Guatemala); el cliente las muestra tal cual y no las convierte a la zona del navegador.

## 7. Cómo se prueba

| Qué | Cómo |
| --- | --- |
| Servicio de archivos, CSP, `/`, `/app`, integridad de Bootstrap, HTML sin scripts en línea, ausencia de `innerHTML`, comentarios fechados, `.gitignore` | `uv run pytest tests/test_week16_cliente_web.py` (sin base de datos) |
| Funciones puras de JavaScript (sobre de error, `request` con un `fetch` falso, sesión con vencimiento, reglas, validación) | `node --test "tests/web/*.test.mjs"` (Node 22+; pytest también lo dispara y se omite si no hay Node) |
| Comportamiento real en el navegador | Prueba manual con dos usuarios (solicitante y técnico) y capturas a 1280 y 390 px en `docs/img/semana16/` |

Las pruebas de Python no ejecutan JavaScript: garantizan las reglas de seguridad y de estructura. El comportamiento (foco, toasts, redibujado) se verificó en un navegador real.
