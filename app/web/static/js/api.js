/*
 * 22/10/2026 - Richard Ortiz: el UNICO lugar donde el cliente habla con la API (fetch).
 *
 * Todas las paginas llaman a las funciones de `api` y nunca a fetch directamente. Asi hay un solo sitio que:
 *   1. agrega el encabezado `Authorization: Bearer <token>`;
 *   2. entiende el sobre de error de la API {error, message, details} (app/api/errors.py);
 *   3. reacciona al 401 (token vencido o invalido): borra la sesion y manda al ingreso;
 *   4. convierte un fallo de red (servidor apagado, sin Internet) en un mensaje comprensible.
 * Misma idea de la semana 14 en el servidor: un solo formato de error para que el cliente aprenda uno.
 */

import { clearSession, getToken } from "./session.js";

// 22/10/2026 - Hoy el cliente y la API comparten origen (mismo host y puerto), por eso la ruta es relativa
// y el navegador NO necesita CORS. Si la API se mueve a otro dominio (semana 17), este es el unico valor que cambia.
export const API_BASE = "/api";
const LOGIN_PAGE = "index.html?expired=1";

// 22/10/2026 - Error con la forma del sobre de la API. `status` 0 significa "ni siquiera llego una respuesta".
export class ApiError extends Error {
  constructor({ status, code, message, details = {} }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

// 22/10/2026 - Mensajes en espanol para los errores de dominio que la API redacta en ingles. Son los que
// el usuario puede provocar con un uso normal; el resto cae en el mensaje generico de su codigo HTTP.
const KNOWN_MESSAGES = {
  "ticket is closed or cancelled": "El ticket está cerrado o cancelado y ya no admite cambios.",
  "assignee must be support staff": "Solo se puede asignar a personal de soporte (técnico o supervisor).",
  "comment body is required": "Escribe un comentario antes de enviarlo.",
  "invalid email or password": "Correo o contraseña incorrectos.",
  "invalid or expired token": "Tu sesión venció. Ingresa de nuevo.",
  "bearer token required": "Tu sesión no es válida. Ingresa de nuevo.",
};

const STATUS_MESSAGES = {
  401: "Tu sesión no es válida o venció. Ingresa de nuevo.",
  403: "No tienes permiso para realizar esta acción.",
  404: "No encontramos lo que buscas. Puede que no exista o que no tengas acceso.",
  409: "La operación no se puede completar con el estado actual de los datos.",
  422: "Revisa los datos: alguno no es válido.",
  503: "El servicio no está disponible por ahora. Inténtalo en unos minutos.",
};

// 22/10/2026 - Arma la cadena ?a=1&b=2 con codificacion segura, saltando valores vacios (null, undefined, "").
export function buildQuery(params = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

// 22/10/2026 - Convierte (status HTTP, cuerpo JSON) en un ApiError. Si el cuerpo no es el sobre de la API
// (por ejemplo un 502 de un proxy con HTML), igual devuelvo un error con forma conocida.
export function parseApiError(status, body) {
  const isEnvelope = body !== null && typeof body === "object" && typeof body.error === "string";
  if (!isEnvelope) {
    return new ApiError({ status, code: "http_error", message: `HTTP ${status}` });
  }
  const details = body.details !== null && typeof body.details === "object" ? body.details : {};
  return new ApiError({ status, code: body.error, message: String(body.message ?? ""), details });
}

// 22/10/2026 - Texto en espanol para MOSTRAR al usuario. Nunca devuelvo el mensaje crudo del servidor
// (en ingles y a veces tecnico); si no lo conozco, uso el mensaje generico del codigo HTTP.
export function userMessage(error) {
  if (!(error instanceof ApiError)) {
    return "Ocurrió un error inesperado. Inténtalo de nuevo.";
  }
  if (error.code === "network_error") {
    return "No se pudo conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.";
  }
  if (Object.hasOwn(KNOWN_MESSAGES, error.message)) {
    return KNOWN_MESSAGES[error.message];
  }
  if (error.code === "invalid_status_transition") {
    return "Ese cambio de estado no está permitido desde el estado actual del ticket.";
  }
  if (Object.hasOwn(STATUS_MESSAGES, error.status)) {
    return STATUS_MESSAGES[error.status];
  }
  if (error.status >= 500) {
    return "El servidor tuvo un problema. Inténtalo más tarde.";
  }
  return "No se pudo completar la operación.";
}

// 22/10/2026 - Errores por campo de un 422: { campo: mensaje }. La API los entrega de dos formas:
// details.errors[] (validacion de esquema) o details.field (regla de dominio). El texto es el del servidor.
export function fieldErrors(error) {
  const result = {};
  if (!(error instanceof ApiError)) {
    return result;
  }
  const list = Array.isArray(error.details.errors) ? error.details.errors : [];
  for (const item of list) {
    if (item && typeof item.field === "string" && item.field !== "") {
      result[item.field] = String(item.message ?? "");
    }
  }
  if (typeof error.details.field === "string") {
    result[error.details.field] = error.message;
  }
  return result;
}

let onUnauthorized = () => {
  if (typeof window !== "undefined") {
    window.location.replace(LOGIN_PAGE);
  }
};

// 22/10/2026 - Permite cambiar que pasa tras un 401 (las pruebas de Node lo reemplazan para no navegar).
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

// 22/10/2026 - La funcion central: una peticion a la API. Devuelve { data, headers } o lanza ApiError.
// `auth: false` es solo para el login (todavia no hay token, y un 401 ahi significa "contrasena incorrecta",
// no "sesion vencida", asi que no debe redirigir).
export async function request(method, path, { query, body, auth = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (auth) {
    const token = getToken();
    if (token === null) {
      onUnauthorized();
      throw new ApiError({ status: 401, code: "unauthenticated", message: "bearer token required" });
    }
    headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await globalThis.fetch(`${API_BASE}${path}${buildQuery(query)}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError({ status: 0, code: "network_error", message: "network error" });
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const error = parseApiError(response.status, payload);
    if (response.status === 401 && auth) {
      clearSession();
      onUnauthorized();
    }
    throw error;
  }
  return { data: payload, headers: response.headers };
}

// 22/10/2026 - Un metodo por caso de uso de la API, con el nombre del negocio. Las paginas leen como una receta:
// `await api.assign(5, 3)` en vez de armar URLs y cuerpos a mano.
export const api = {
  async login(email, password) {
    const { data } = await request("POST", "/auth/login", { body: { email, password }, auth: false });
    return data;
  },
  async me() {
    return (await request("GET", "/users/me")).data;
  },
  async listUsers(role) {
    return (await request("GET", "/users", { query: { role } })).data;
  },
  // El total no va en el cuerpo sino en el encabezado X-Total-Count (ver app/api/routes/tickets.py).
  async listTickets(query) {
    const { data, headers } = await request("GET", "/tickets", { query });
    return { items: data, total: Number(headers.get("X-Total-Count") ?? data.length) };
  },
  async getTicket(id) {
    return (await request("GET", `/tickets/${id}`)).data;
  },
  async createTicket(payload) {
    return (await request("POST", "/tickets", { body: payload })).data;
  },
  async addComment(id, body) {
    return (await request("POST", `/tickets/${id}/comments`, { body: { body } })).data;
  },
  async assign(id, technicianId) {
    return (await request("POST", `/tickets/${id}/assign`, { body: { technician_id: technicianId } })).data;
  },
  async changeStatus(id, status) {
    return (await request("PATCH", `/tickets/${id}/status`, { body: { status } })).data;
  },
  async changePriority(id, priority) {
    return (await request("PATCH", `/tickets/${id}/priority`, { body: { priority } })).data;
  },
  async cancel(id) {
    return (await request("POST", `/tickets/${id}/cancel`)).data;
  },
  async notifications() {
    return (await request("GET", "/notifications")).data;
  },
  async markAllRead() {
    return (await request("POST", "/notifications/read-all")).data;
  },
};
