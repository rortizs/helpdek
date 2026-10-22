/*
 * 22/10/2026 - Richard Ortiz: sesion del navegador. Aqui, y SOLO aqui, guardo y leo el token de acceso.
 *
 * ¿Donde se guarda el token? Tres opciones, cada una con su costo:
 *   - localStorage: sobrevive al cerrar el navegador, pero cualquier script que corra en la pagina
 *     (un XSS) puede leerlo y se queda ahi dias. Es la peor opcion para un token de acceso.
 *   - sessionStorage (la que elijo): vive solo en la pestana y muere al cerrarla. Un XSS tambien podria
 *     leerlo MIENTRAS la pestana esta abierta, pero la exposicion es mucho menor. Cuesta: hay que ingresar
 *     de nuevo al abrir otra pestana.
 *   - Cookie HttpOnly: JavaScript no puede leerla (la mejor defensa contra el robo por XSS), pero el
 *     navegador la envia SOLA en cada peticion y eso abre la puerta al CSRF; exigiria que la API emita la
 *     cookie y un token anti-CSRF. Nuestra API usa Bearer, asi que queda como mejora para la semana 17+.
 * La amenaza real es el XSS, por eso el resto del cliente jamas pinta datos con innerHTML (ver ui.js) y la
 * politica CSP bloquea los scripts en linea. Guardar el token con cuidado no sirve si dejo entrar XSS.
 *
 * El token VENCE (expires_in de la API); lo guardo con su hora de vencimiento y lo descarto yo mismo
 * en cuanto pasa, sin esperar a que la API conteste 401.
 */

const TOKEN_KEY = "helpdesk.token";
const EXPIRES_KEY = "helpdesk.expiresAt";
const USER_KEY = "helpdesk.user";

// 22/10/2026 - Devuelvo el almacen en cada llamada (no lo guardo en una constante) para que las pruebas
// de Node puedan poner uno falso en globalThis antes de usar el modulo.
function store() {
  return globalThis.sessionStorage;
}

// 22/10/2026 - Guarda el token que acaba de entregar POST /api/auth/login y calcula cuando deja de servir.
export function saveSession({ token, expiresIn }, now = Date.now()) {
  store().setItem(TOKEN_KEY, token);
  store().setItem(EXPIRES_KEY, String(now + expiresIn * 1000));
}

// 22/10/2026 - Devuelve el token vigente o null. Si ya vencio, limpio la sesion: asi nadie lo manda a la API a ciegas.
export function getToken(now = Date.now()) {
  const token = store().getItem(TOKEN_KEY);
  if (!token) {
    return null;
  }
  const expiresAt = Number(store().getItem(EXPIRES_KEY));
  if (!Number.isFinite(expiresAt) || expiresAt <= now) {
    clearSession();
    return null;
  }
  return token;
}

// 22/10/2026 - Guarda quien soy (id, nombre, correo, rol) para dibujar el menu sin pedirlo en cada pagina.
// OJO: es solo para mostrar. Que yo "sea tecnico" lo decide la API con el token, no este dato.
export function saveUser(user) {
  store().setItem(USER_KEY, JSON.stringify(user));
}

// 22/10/2026 - Lee el usuario guardado; si el JSON esta danado, lo trato como que no hay usuario.
export function getUser() {
  try {
    return JSON.parse(store().getItem(USER_KEY));
  } catch {
    return null;
  }
}

// 22/10/2026 - Cierra la sesion local: borra token, vencimiento y usuario. El token no se "revoca" en el
// servidor porque JWT es sin estado; por eso su vida es corta (ACCESS_TOKEN_MINUTES).
export function clearSession() {
  store().removeItem(TOKEN_KEY);
  store().removeItem(EXPIRES_KEY);
  store().removeItem(USER_KEY);
}

// 22/10/2026 - ¿Hay una sesion vigente? Las paginas protegidas lo preguntan antes de pedir datos.
export function isSignedIn() {
  return getToken() !== null;
}
