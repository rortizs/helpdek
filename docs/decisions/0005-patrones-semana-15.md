# ADR 0005 - Patrones aplicados en la semana 15

- Fecha: 22/10/2026
- Autor: Ing. Richard Ortiz
- Estado: aceptado
- Contexto del curso: semana 15, "Patrones aplicados en Python y FastAPI" (Programación II)

## Regla de esta semana: primero el problema, después el patrón

Un patrón no se "aplica" porque exista en un libro: se aplica porque hay un dolor concreto en el código
que ya escribimos. Para cada patrón de este ADR el orden es el mismo:

1. **Problema** que ya tenemos en el repositorio (con el código de antes).
2. **Patrón** elegido y por qué ese.
3. **Antes / después** del código.
4. **Cuándo NO usarlo** (el límite honesto).

Estudiamos cinco temas. Tres se aplican, uno se estudia como crítica y uno se descarta a propósito:

| Tema | Decisión | Dónde |
| --- | --- | --- |
| Observer | **Se aplica** | `app/domain/events.py`, `app/services/events.py`, `app/services/audit.py` |
| Facade | **Se aplica** (con límites) | `app/services/helpdesk.py` |
| Inyección de dependencias | **Se aplica** (ya vivía en `Depends`; la hacemos explícita y probada) | `app/api/dependencies.py` |
| Singleton | **Se estudia y se desarma** | `app/core/database.py`, `app/main.py` |
| Decorator | **No se aplica** | (no hay código; ver sección 5) |

MVC queda como referencia conceptual: nuestras capas ya cumplen lo que MVC pide (rutas y esquemas =
interfaz, servicios = reglas, repositorios = datos), y la arquitectura en capas es la que usamos
desde la semana 9. Este ADR no la cambia.

---

## 1. Observer: avisar y auditar sin tocar las reglas del ticket

### Problema (código de la semana 14)

`TicketService` llamaba directamente al notificador en cada caso de uso:

```python
# ANTES (semana 14) - app/services/tickets.py
self._repository.update(ticket)
self._notify(
    user_id=ticket.requester_id,
    title="ticket_status_changed",
    message=f"Ticket #{ticket.id} changed to {ticket.status.value}",
    ticket_id=ticket.id,
)
```

Con **una** reacción (avisar) eso alcanza. El dolor aparece con la **segunda**: queremos dejar una línea
de auditoría por cada cambio. Con el diseño anterior la única salida era agregar *otra* llamada en
cada uno de los cinco métodos del servicio, y el servicio terminaba conociendo a todos los que reaccionan.
Además la regla "no avisar al solicitante de su propio comentario" estaba mezclada con la regla del ticket.

### Patrón

**Observer**: el servicio solo cuenta *qué pasó* (un evento inmutable) y quien quiera reaccionar se suscribe.

```python
# DESPUES (semana 15)
self._repository.update(ticket)
self._publish(
    TicketStatusChanged(
        ticket_id=ticket.id,
        actor_id=actor.id,
        requester_id=ticket.requester_id,
        new_status=ticket.status,
    )
)
```

- Eventos: `TicketCreated`, `TicketAssigned`, `TicketStatusChanged`, `TicketCommented` y `TicketCancelled`
  (este último existe porque el notificador anterior ya avisaba de las cancelaciones y no queremos perder ese comportamiento).
- `EventPublisher` es una lista de funciones y un `for`. Un suscriptor es **cualquier callable**;
  en las pruebas `lista.append` ya sirve como suscriptor.
- El notificador de las semanas 7-13 pasa a ser **un suscriptor más** (`NotifierSubscriber`), que traduce
  cada evento a la misma llamada `notify(...)` de siempre, con los mismos códigos y textos.
  El parámetro `notifier=` de `TicketService` sigue funcionando: compatibilidad total.
- El segundo suscriptor, `AuditLogSubscriber`, escribe `event=<nombre> ticket=<id> actor=<id>` con el módulo
  `logging` (logger `helpdesk.audit`). Agregarlo **no tocó una sola línea** de las reglas del ticket.

### Decisión importante: síncrono y en la misma transacción

Los suscriptores corren en el mismo hilo y dentro de la unidad de trabajo de la petición. Si uno falla,
la operación falla y se hace *rollback*: nunca queda un ticket guardado sin su aviso. Esto es lo que
queremos para `DatabaseNotifier` (el aviso se guarda en la misma sesión). El costo: un suscriptor lento
o roto frena la petición (hay una prueba que fija este comportamiento).

### Cuándo NO usar Observer

- Si solo hay **una** reacción y no se espera otra, una llamada directa es más simple de leer y depurar.
  Aquí se justificó porque ya hay dos (avisos y auditoría) y el diseño anterior dolía con la segunda.
- Si el orden entre reacciones importa y es complejo, un Observer lo esconde. Aquí el orden no importa.
- Si la reacción debe sobrevivir a un fallo o ser asíncrona (correo, webhooks), un Observer síncrono no basta:
  eso pide una cola, y es otra decisión.
- Un Observer con cascadas (un suscriptor que publica otros eventos) se vuelve muy difícil de seguir.
  No lo permitimos: los suscriptores actuales no publican nada.

---

## 2. Facade: una puerta única para los casos de uso

### Problema (código de la semana 14)

Cada ruta recibía una bolsa `Services` con **cuatro** servicios y decidía por su cuenta a cuál llamar y en
qué orden. El caso más claro es el login: dos llamadas escritas *dentro de la ruta*.

```python
# ANTES (semana 14) - app/api/routes/auth.py
@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, services: ServicesDep):
    user = services.auth.authenticate(body.email, body.password)
    token, expires_in = services.auth.issue_token(user)
    return TokenOut(access_token=token, expires_in=expires_in)
```

Otros dolores concretos: para probar *una* ruta había que armar los cuatro servicios; y `get_current_user`
(en la capa HTTP) decodificaba el token y consultaba el repositorio de usuarios, es decir, hacía de
coordinador también.

### Patrón

**Facade**: `HelpDeskFacade` expone los casos de uso con nombres del negocio y las rutas dependen de **un**
objeto.

```python
# DESPUES (semana 15)
@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, facade: FacadeDep):
    token, expires_in = facade.login(body.email, body.password)
    return TokenOut(access_token=token, expires_in=expires_in)
```

Casos de uso: `login`, `user_from_token`, `open_ticket`, `list_tickets`, `get_ticket`, `comment`,
`list_comments`, `assign`, `change_status`, `change_priority`, `cancel`, `my_notifications`,
`mark_notifications_read`, y los de usuarios. La fachada se arma con `Depends` (`get_facade`), una
instancia por petición, sobre los servicios de esa petición.

### Límite honesto (importante para explicarlo en clase)

Hoy **la mayoría de los métodos de la fachada solo reenvían a un servicio**. El valor presente es:

1. Las rutas conocen un solo objeto y un vocabulario de negocio (`open_ticket`, no `services.tickets.create(requester=...)`).
2. La coordinación de varios servicios (login = autenticar + emitir token; token -> usuario) vive en un lugar.
3. Un punto de prueba barato: se prueba una ruta con un doble de la fachada, sin base de datos
   (`test_the_create_ticket_route_only_talks_to_the_facade`).

La fachada **no** agrega reglas de negocio (siguen en los servicios), **no** reemplaza a los servicios y
**no** es un "service locator" para que cualquiera pida cualquier cosa. Si un método solo reenvía y nadie
necesita ese nombre, sobra. La semana 16 (cliente web) es la prueba: si el cliente necesita un caso de uso que
junte dos servicios (por ejemplo "mi resumen": mis tickets y mis avisos sin leer), se agrega *aquí*.

### Cuándo NO usar Facade

- Cuando solo hay un servicio detrás: una fachada sobre un único objeto es una capa de ruido.
- Cuando se convierte en una clase gigante con cientos de métodos ("God object"): ahí se divide por contexto.
- Cuando se usa para esconder un diseño malo de los servicios en vez de arreglarlo.

---

## 3. Inyección de dependencias: cambiar piezas sin variables globales

### Problema

Una prueba de la API necesitaba PostgreSQL y un engine global inicializado aunque solo quisiéramos probar
la regla de una ruta. Y la forma de "cambiar" una pieza era mutar un global.

### Patrón

FastAPI ya trae inyección de dependencias: `Depends`. La cadena es
`get_db -> get_services -> get_facade -> ruta`, y `app.dependency_overrides` reemplaza **un eslabón** por
aplicación:

```python
# prueba - tests/test_week15_patrones.py
app = create_app()
app.dependency_overrides[get_services] = lambda: in_memory_services   # repos en memoria + suscriptor grabador
client = TestClient(app)
# login, abrir ticket, comentar y leer avisos: la API completa, sin PostgreSQL
```

Para que esto sea posible agregamos `InMemoryNotificationRepository` (la bandeja de avisos en memoria),
de modo que la fachada completa corre sobre memoria.

Qué demuestra la prueba:

- La API completa corre sobre piezas de memoria cambiando **una** dependencia.
- El suscriptor grabador ve los eventos reales (`TicketCreated`, `TicketCommented`).
- Los overrides pertenecen a **una** app: otra `create_app()` no los hereda.

Esto es DI por *constructor* (los servicios reciben repositorio y notificador) más DI por *Depends*
(la capa HTTP recibe sus servicios). No hace falta ningún contenedor de DI.

### Cuándo NO usar un contenedor/framework de DI

Para un proyecto de este tamaño `Depends` + constructores alcanzan. Un contenedor (con registro automático,
ciclos de vida, etc.) agrega magia que los estudiantes no pueden seguir con el depurador.

---

## 4. Singleton: crítica y refactor

### El Singleton que teníamos (sin llamarlo así)

Hasta la semana 14, `app/core/database.py` guardaba el engine y la fábrica de sesiones como **variables
globales del módulo**:

```python
# ANTES (semana 14) - app/core/database.py
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None

def init_engine(database_url=None):
    global _engine, _session_factory
    ...
```

Es un Singleton: una única instancia accesible desde cualquier parte. Es cómodo, y por eso se usa tanto.
Pero tiene tres costos que ya vimos en clase:

| Costo | Cómo se manifestó aquí |
| --- | --- |
| **Estado global** | Dos aplicaciones en el mismo proceso compartían la misma base; no se podían tener dos configuraciones a la vez. |
| **Acoplamiento** | Cualquier módulo podía importar `session_scope()` y saltarse al dueño del recurso. |
| **Pruebas difíciles** | Para cambiar de base había que mutar el global y acordarse de limpiarlo (`init_engine(...)` / `dispose_engine()` en cada fixture). Una prueba que olvidaba limpiar contaminaba a la siguiente. |

### Refactor

Ahora `Database` (engine + fábrica de sesiones + `session_scope()` + `dispose()`) es una **clase con dueño**, y el dueño
es la **aplicación**:

```python
# DESPUES (semana 15) - app/main.py
def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(..., lifespan=lifespan)
    app.state.database = Database(database_url or settings.database_url)   # la app crea y posee su Database
    ...

@asynccontextmanager
async def lifespan(app):
    yield
    app.state.database.dispose()       # y la cierra al apagarse

# app/api/dependencies.py
def get_db(request: Request):
    with request.app.state.database.session_scope() as session:    # la sesion sale de LA app de la peticion
        yield session
```

Una prueba demuestra el resultado: dos apps con URLs distintas contestan desde bases distintas
(`SELECT current_database()` devuelve `helpdesk_test` en una y `postgres` en la otra) y la API **nunca** crea el
default de módulo.

### Lo que NO se eliminó (y por qué)

- `init_engine`, `session_scope`, `get_session`, `get_session_factory`, `dispose_engine` siguen existiendo, apoyados en
  un único `_default` de módulo, **solo para scripts** (`app/scripts/set_password.py`) y para las pruebas de aceptación
  de la semana 13 que los estudiantes ya tienen. Un script no tiene una app de la cual colgar el engine. Es estado global,
  está a la vista, está documentado, y la API no lo usa (hay una prueba que lo verifica).
- `get_settings()` **no es un Singleton**: es una función pura del entorno, sin estado guardado. Se lee en cada llamada
  y una prueba lo verifica (`APP_NAME` cambia entre dos llamadas). No usa `lru_cache`, justamente para que las pruebas
  puedan cambiar una variable sin reiniciar el proceso.
- `@cache` en `_dummy_hash()` (`app/core/security.py`) sí cachea un valor, pero es un valor *derivado e inmutable*
  (un hash de relleno para igualar tiempos de respuesta del login), sin dependencias externas. No es estado que las pruebas
  deban reiniciar.
- `app = create_app()` a nivel de módulo en `app/main.py` se queda porque `uvicorn app.main:app` lo necesita.
  Crear el `Database` no abre conexiones; el *lifespan* cierra el pool al apagar.

### Consecuencia que nos mordió (y por qué hay una guardia)

Al quitar el global, `create_app()` sin argumentos usa `DATABASE_URL`, cuyo valor por defecto es la base de
práctica `helpdesk`. Las pruebas que antes dependían del engine global de prueba pasaron a apuntar a la base equivocada
y **escribieron datos en `helpdesk`**. Es el ejemplo perfecto del costo oculto de quitar un global: los valores por defecto
peligrosos dejan de estar "protegidos" por el estado compartido.

Por eso `tests/conftest.py` ahora: (1) rechaza cualquier `TEST_DATABASE_URL` cuya base no contenga `test`,
(2) **fuerza** `DATABASE_URL` a la base de pruebas durante toda la sesión, y (3) tiene pruebas que demuestran que la guardia
rechaza `helpdesk`. Lección para la clase: al refactorizar estado global, revisen qué otra cosa dependía de él por accidente.

### Cuándo SÍ es razonable un Singleton

Cuando el recurso es realmente único en el proceso, inmutable y sin dependencias de entorno (por ejemplo una constante
de configuración ya validada, un logger por nombre). El engine **no** lo es: depende de una URL, tiene un ciclo de vida
(pool abierto/cerrado) y queremos poder tener más de uno (pruebas, apps distintas).

---

## 5. Decorator: no se aplica (y por qué)

El candidato obvio fue la comprobación de permisos: `if not actor.is_staff: raise PermissionDeniedError(...)`
se repite en cuatro casos de uso (`assign`, `change_priority`, `change_status` y `UserService.list_for`).
Revisé si un decorador `@require_staff` resolvía un problema real y concluí que no:

- La repetición son **dos líneas** y cada sitio usa un mensaje y datos de error distintos.
- `assign` acepta `actor=None` (lo usa el método heredado `assign_technician`), así que el decorador necesitaría
  una excepción para ese caso.
- El **orden** es una regla de seguridad, no un detalle: en los tres casos de tickets el permiso se revisa
  *antes* de buscar el ticket (quien no es personal recibe 403 exista o no el id, y así no se averigua qué ids existen).
  Un decorador esconde justo ese orden y tendría que saber en qué parámetro viaja el `ticket_id` para armar el error.
- Las otras reglas de acceso son de otra naturaleza (cancelar = solo el solicitante, crear usuarios = solo administrador,
  ver un ticket ajeno = 404 en vez de 403). No caben en un único `@require_staff`; querer unificarlas exigiría un
  mini lenguaje de permisos que hoy no necesitamos.
- No apareció otra necesidad transversal (reintentos, caché, medición de tiempos) que justifique la complejidad.

Decisión: **no hay Decorator**. La repetición es barata y explícita; el decorador sería abstracción prematura.
Si más adelante aparece una necesidad transversal real (por ejemplo medir la duración de cada caso de uso), ese sería el
momento de reabrir esta decisión.

---

## 6. Resumen de decisiones y compromisos

| Decisión | Beneficio | Costo asumido |
| --- | --- | --- |
| Observer síncrono | Reacciones extensibles sin tocar reglas; compatibilidad total con `notifier=` | Un suscriptor roto/lento rompe la petición (documentado y probado) |
| Facade delgada | Rutas con un solo colaborador; coordinación en un sitio; pruebas sin base | Muchos métodos solo reenvían; hay que vigilar que no crezca |
| DI con `Depends` | Cambiar piezas sin globales; API completa probada en memoria | Ninguno relevante; requiere `InMemoryNotificationRepository` |
| `Database` en `app.state` | Sin estado global en la API; un pool por app; cierre ordenado | El default de módulo sigue existiendo para scripts; el valor por defecto de `DATABASE_URL` exige la guardia de pruebas |
| Sin Decorator | Permisos visibles y en el orden correcto | Dos líneas repetidas en cuatro sitios |

## 7. Archivos y pruebas

- Observer: `app/domain/events.py`, `app/services/events.py`, `app/services/audit.py`, `NotifierSubscriber` en
  `app/services/notifications.py`, `TicketService` (`subscribe`, `_publish`).
- Facade: `app/services/helpdesk.py`, `get_facade`/`FacadeDep` en `app/api/dependencies.py`, rutas en `app/api/routes/`.
- DI: `get_services`/`get_facade` y `InMemoryNotificationRepository` en `app/repositories/memory.py`.
- Singleton: `Database` en `app/core/database.py`, `create_app`/`lifespan` en `app/main.py`.
- Pruebas: `tests/test_week15_patrones.py` (una sección por patrón y una de guardia de la base de pruebas).
