/*
 * 22/10/2026 - Richard Ortiz: pruebas de las funciones PURAS del cliente web (semana 16) con el corredor de
 * pruebas que ya trae Node (`node:test`), sin instalar nada y sin navegador.
 *
 * Como correrlas (desde la raiz del repositorio, hace falta Node 22 o mayor para el patron con comodin):
 *     node --test "tests/web/*.test.mjs"
 * Cubren: parseo del sobre de error de la API, mensajes en espanol, errores por campo, la envoltura `request`
 * (encabezado Bearer, 401, fallo de red) con un `fetch` falso, la sesion con vencimiento, las reglas por rol
 * y la validacion de formularios. Lo que depende del DOM se prueba a mano (ver README, "Cliente web").
 */

import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import { ApiError, buildQuery, fieldErrors, parseApiError, request, setUnauthorizedHandler, userMessage } from "../../app/web/static/js/api.js";
import { formatDate, formatDateTime, historyDetail, label, pageCount, rangeText, STATUS_LABELS } from "../../app/web/static/js/format.js";
import { allowedTransitions, canCancel, isAssignable, isStaff, isTicketOpen } from "../../app/web/static/js/rules.js";
import { clearSession, getToken, getUser, saveSession, saveUser } from "../../app/web/static/js/session.js";
import { validateComment, validateLogin, validateTicketForm } from "../../app/web/static/js/validation.js";

// 22/10/2026 - Un sessionStorage falso en memoria: Node no tiene navegador, pero session.js solo necesita estos 3 metodos.
function installFakeStorage() {
  const data = new Map();
  globalThis.sessionStorage = {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key),
  };
}

// 22/10/2026 - Un fetch falso: devuelve la respuesta que le pido y recuerda con que lo llamaron.
function installFakeFetch(status, body, headers = {}) {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: status >= 200 && status < 300,
      status,
      headers: new Headers(headers),
      json: async () => {
        if (body === undefined) {
          throw new SyntaxError("no JSON");
        }
        return body;
      },
    };
  };
  return calls;
}

let unauthorizedCalls;

beforeEach(() => {
  installFakeStorage();
  unauthorizedCalls = 0;
  setUnauthorizedHandler(() => {
    unauthorizedCalls += 1;
  });
});

// --- api.js: funciones puras ----------------------------------------------------------

test("buildQuery omite valores vacios y codifica el resto", () => {
  assert.equal(buildQuery({ status: "open", category: "", priority: null, limit: 10, offset: 0, q: "a b&c" }), "?status=open&limit=10&offset=0&q=a+b%26c");
  assert.equal(buildQuery({}), "");
  assert.equal(buildQuery(), "");
});

test("parseApiError entiende el sobre {error, message, details}", () => {
  const error = parseApiError(404, { error: "ticket_not_found", message: "Ticket 9 was not found", details: { ticket_id: 9 } });

  assert.ok(error instanceof ApiError);
  assert.deepEqual([error.status, error.code, error.message, error.details], [404, "ticket_not_found", "Ticket 9 was not found", { ticket_id: 9 }]);
});

test("parseApiError tolera cuerpos que no son el sobre (HTML de un proxy, null)", () => {
  for (const body of [null, "<html>502</html>", { detail: "x" }, 42]) {
    const error = parseApiError(502, body);
    assert.equal(error.status, 502);
    assert.equal(error.code, "http_error");
    assert.deepEqual(error.details, {});
  }
});

test("userMessage devuelve texto en espanol y nunca el mensaje crudo del servidor", () => {
  const cases = [
    [parseApiError(403, { error: "permission_denied", message: "Only staff users can assign tickets", details: {} }), /permiso/],
    [parseApiError(404, { error: "ticket_not_found", message: "Ticket 9 was not found", details: {} }), /No encontramos/],
    [parseApiError(409, { error: "invalid_status_transition", message: "Cannot transition ticket from open to closed", details: {} }), /cambio de estado no está permitido/],
    [parseApiError(422, { error: "validation_error", message: "ticket is closed or cancelled", details: { field: "ticket" } }), /cerrado o cancelado/],
    [parseApiError(401, { error: "unauthenticated", message: "invalid email or password", details: {} }), /Correo o contraseña incorrectos/],
    [parseApiError(500, { error: "internal_error", message: "an unexpected error occurred", details: {} }), /servidor tuvo un problema/],
    [new ApiError({ status: 0, code: "network_error", message: "network error" }), /No se pudo conectar/],
    [new Error("boom"), /error inesperado/],
  ];
  for (const [error, pattern] of cases) {
    assert.match(userMessage(error), pattern);
    assert.doesNotMatch(userMessage(error), /Only staff|Cannot transition|boom/);
  }
});

test("fieldErrors lee details.errors[] (esquema) y details.field (dominio)", () => {
  const schema = parseApiError(422, {
    error: "validation_error",
    message: "the request data is invalid",
    details: { errors: [{ field: "title", message: "String should have at least 3 characters" }, { field: "category", message: "Value error" }] },
  });
  assert.deepEqual(fieldErrors(schema), { title: "String should have at least 3 characters", category: "Value error" });

  const domain = parseApiError(422, { error: "validation_error", message: "priority is invalid", details: { field: "priority" } });
  assert.deepEqual(fieldErrors(domain), { priority: "priority is invalid" });

  assert.deepEqual(fieldErrors(new Error("x")), {});
});

// --- api.js: request() con fetch falso -------------------------------------------------

test("request agrega Authorization: Bearer y devuelve datos + encabezados", async () => {
  saveSession({ token: "tok123", expiresIn: 3600 });
  const calls = installFakeFetch(200, [{ id: 1 }], { "X-Total-Count": "37" });

  const { data, headers } = await request("GET", "/tickets", { query: { status: "open", limit: 10 } });

  assert.deepEqual(data, [{ id: 1 }]);
  assert.equal(headers.get("X-Total-Count"), "37");
  assert.equal(calls[0].url, "/api/tickets?status=open&limit=10");
  assert.equal(calls[0].options.headers.Authorization, "Bearer tok123");
  assert.equal(calls[0].options.method, "GET");
});

test("request envia el cuerpo como JSON con Content-Type", async () => {
  saveSession({ token: "tok123", expiresIn: 3600 });
  const calls = installFakeFetch(201, { id: 5 });

  await request("POST", "/tickets", { body: { title: "Hola" } });

  assert.equal(calls[0].options.body, '{"title":"Hola"}');
  assert.equal(calls[0].options.headers["Content-Type"], "application/json");
});

test("un 401 con sesion borra el token y avisa para ir al ingreso", async () => {
  saveSession({ token: "vencido", expiresIn: 3600 });
  installFakeFetch(401, { error: "unauthenticated", message: "invalid or expired token", details: {} });

  await assert.rejects(request("GET", "/tickets"), (error) => error instanceof ApiError && error.status === 401);

  assert.equal(getToken(), null);
  assert.equal(unauthorizedCalls, 1);
});

test("un 401 del LOGIN (auth: false) es contrasena incorrecta: no redirige", async () => {
  installFakeFetch(401, { error: "unauthenticated", message: "invalid email or password", details: {} });

  await assert.rejects(request("POST", "/auth/login", { body: { email: "a", password: "b" }, auth: false }), (error) => error.status === 401);

  assert.equal(unauthorizedCalls, 0);
});

test("sin token ni siquiera se llama a la API", async () => {
  const calls = installFakeFetch(200, []);

  await assert.rejects(request("GET", "/tickets"), (error) => error.status === 401);

  assert.equal(calls.length, 0);
  assert.equal(unauthorizedCalls, 1);
});

test("un fallo de red se convierte en ApiError network_error", async () => {
  saveSession({ token: "tok", expiresIn: 3600 });
  globalThis.fetch = async () => {
    throw new TypeError("Failed to fetch");
  };

  await assert.rejects(request("GET", "/tickets"), (error) => error.code === "network_error" && error.status === 0);
});

test("una respuesta de error sin JSON sigue dando un ApiError con forma conocida", async () => {
  saveSession({ token: "tok", expiresIn: 3600 });
  installFakeFetch(502, undefined);

  await assert.rejects(request("GET", "/tickets"), (error) => error.code === "http_error" && error.status === 502);
});

// --- session.js -----------------------------------------------------------------------

test("el token vence a la hora indicada y se borra solo", () => {
  saveSession({ token: "abc", expiresIn: 60 }, 1_000_000);

  assert.equal(getToken(1_000_000 + 59_000), "abc");
  assert.equal(getToken(1_000_000 + 60_000), null);
  assert.equal(globalThis.sessionStorage.getItem("helpdesk.token"), null);
});

test("clearSession borra token, vencimiento y usuario; getUser tolera JSON danado", () => {
  saveSession({ token: "abc", expiresIn: 60 });
  saveUser({ id: 4, name: "Requester", role: "requester" });
  assert.deepEqual(getUser(), { id: 4, name: "Requester", role: "requester" });

  clearSession();
  assert.equal(getToken(), null);
  assert.equal(getUser(), null);

  globalThis.sessionStorage.setItem("helpdesk.user", "{no es json");
  assert.equal(getUser(), null);
});

// --- format.js -------------------------------------------------------------------------

test("formatDateTime no mueve la hora (la API entrega hora local sin zona)", () => {
  assert.equal(formatDateTime("2026-10-22T16:41:05.123456"), "22/10/2026 16:41");
  assert.equal(formatDate("2026-10-22T16:41:05"), "22/10/2026");
  assert.equal(formatDateTime(null), "—");
  assert.equal(formatDateTime("basura"), "—");
});

test("label traduce valores conocidos y deja pasar los desconocidos", () => {
  assert.equal(label(STATUS_LABELS, "in_progress"), "En progreso");
  assert.equal(label(STATUS_LABELS, "nuevo_estado"), "nuevo_estado");
  assert.equal(label(STATUS_LABELS, "constructor"), "constructor");
});

test("paginacion: rangeText y pageCount", () => {
  assert.equal(rangeText(0, 10, 37), "1–10 de 37");
  assert.equal(rangeText(30, 7, 37), "31–37 de 37");
  assert.equal(rangeText(0, 0, 0), "0 resultados");
  assert.equal(pageCount(37, 10), 4);
  assert.equal(pageCount(0, 10), 1);
});

test("historyDetail traduce el detalle tecnico del historial", () => {
  assert.equal(historyDetail("status_changed", "in_progress"), "En progreso");
  assert.equal(historyDetail("priority_changed", "High -> Critical"), "Alta → Crítica");
  assert.equal(historyDetail("assigned", "assigned to Ana Lopez"), "A Ana Lopez");
  assert.equal(historyDetail("commented", "comment added"), "");
  assert.equal(historyDetail("otro", "texto"), "texto");
});

// --- rules.js --------------------------------------------------------------------------

test("el flujo de estados del cliente copia el de la API", () => {
  assert.deepEqual(allowedTransitions("open"), ["in_progress", "cancelled"]);
  assert.deepEqual(allowedTransitions("resolved"), ["in_progress", "closed"]);
  assert.deepEqual(allowedTransitions("closed"), []);
  assert.deepEqual(allowedTransitions("inventado"), []);
  assert.equal(isTicketOpen({ status: "resolved" }), true);
  assert.equal(isTicketOpen({ status: "cancelled" }), false);
});

test("roles: quien es personal, a quien se puede asignar y quien puede cancelar", () => {
  assert.equal(isStaff({ role: "technician" }), true);
  assert.equal(isStaff({ role: "administrator" }), true);
  assert.equal(isStaff({ role: "requester" }), false);
  assert.equal(isStaff(null), false);
  assert.equal(isAssignable({ role: "supervisor" }), true);
  assert.equal(isAssignable({ role: "administrator" }), false);

  const mine = { id: 7, requester_id: 4, status: "open" };
  assert.equal(canCancel({ id: 4, role: "requester" }, mine), true);
  assert.equal(canCancel({ id: 5, role: "requester" }, mine), false, "solo el solicitante dueno");
  assert.equal(canCancel({ id: 3, role: "technician" }, mine), false, "el tecnico cambia el estado, no cancela");
  assert.equal(canCancel({ id: 4, role: "requester" }, { ...mine, status: "resolved" }), false, "resolved no pasa a cancelled");
});

// --- validation.js ---------------------------------------------------------------------

test("validateTicketForm replica las reglas de la API", () => {
  const valid = { title: "Teclado roto", description: "Faltan teclas", category: "Hardware", priority: "Low" };
  assert.deepEqual(validateTicketForm(valid), {});

  assert.ok(validateTicketForm({ ...valid, title: "  ab  " }).title, "3 caracteres sin contar espacios de los bordes");
  assert.deepEqual(validateTicketForm({ ...valid, title: "abc" }), {});
  assert.ok(validateTicketForm({ ...valid, title: "x".repeat(161) }).title);
  assert.deepEqual(validateTicketForm({ ...valid, title: "x".repeat(160) }), {});
  assert.ok(validateTicketForm({ ...valid, description: "   " }).description);
  assert.ok(validateTicketForm({ ...valid, category: "" }).category);
  assert.ok(validateTicketForm({ ...valid, category: "Hack" }).category);
  assert.ok(validateTicketForm({ ...valid, priority: "Urgent" }).priority);
  assert.deepEqual(Object.keys(validateTicketForm({})).sort(), ["category", "description", "priority", "title"]);
});

test("validateComment y validateLogin piden texto", () => {
  assert.deepEqual(validateComment("  "), { body: "Escribe un comentario antes de enviarlo." });
  assert.deepEqual(validateComment("hola"), {});
  assert.deepEqual(Object.keys(validateLogin({ email: "", password: "" })).sort(), ["email", "password"]);
  assert.deepEqual(validateLogin({ email: "a@b.c", password: "x" }), {});
});
