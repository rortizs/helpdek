/*
 * 22/10/2026 - Richard Ortiz: logica de la LISTA de tickets (tickets.html).
 * Los filtros y la pagina viven en la direccion (?status=open&page=2): asi el boton Atras, recargar y copiar
 * el enlace funcionan como el usuario espera. Los datos vienen de GET /api/tickets (filtros + limit/offset)
 * y el total, del encabezado X-Total-Count.
 */

import { api, buildQuery, userMessage } from "../api.js";
import {
  CATEGORY_LABELS,
  PRIORITY_LABELS,
  STATUS_LABELS,
  formatDate,
  label,
  pageCount,
  rangeText,
} from "../format.js";
import { bootPage } from "../layout.js";
import { isStaff } from "../rules.js";
import { badge, clear, el, loadingIndicator, setBusy, showAlert, clearAlert } from "../ui.js";

const PAGE_SIZE = 10;

const filtersForm = document.getElementById("filters");
const results = document.getElementById("results");
const summary = document.getElementById("results-summary");
const pagination = document.getElementById("pagination");
const alertRegion = document.getElementById("alert-region");
const applyButton = document.getElementById("filters-apply");

let currentUser = null;
let userNames = new Map();
let state = { status: "", category: "", priority: "", mine: false, page: 1 };

// 22/10/2026 - Lee los filtros de la direccion. Esa cadena la controla quien arma el enlace, asi que solo
// acepto valores que existen en las tablas conocidas; cualquier otra cosa se descarta.
function readStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const pick = (name, table) => (Object.hasOwn(table, params.get(name) ?? "") ? params.get(name) : "");
  return {
    status: pick("status", STATUS_LABELS),
    category: pick("category", CATEGORY_LABELS),
    priority: pick("priority", PRIORITY_LABELS),
    mine: params.get("mine") === "1",
    page: Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1),
  };
}

// 22/10/2026 - Refleja los filtros en la direccion SIN recargar (replaceState: no llena el historial de pasos).
function writeStateToUrl() {
  const query = buildQuery({
    status: state.status,
    category: state.category,
    priority: state.priority,
    mine: state.mine ? 1 : "",
    page: state.page > 1 ? state.page : "",
  });
  window.history.replaceState(null, "", `tickets.html${query}`);
}

// 22/10/2026 - Llena un <select> de filtro con la opcion "Todos/Todas" al inicio y las etiquetas en espanol.
function fillFilter(select, table, allLabel, selected) {
  select.replaceChildren(el("option", { text: allLabel, attrs: { value: "" } }));
  for (const [value, text] of Object.entries(table)) {
    select.append(el("option", { text, attrs: { value, selected: value === selected } }));
  }
}

// 22/10/2026 - Nombre de una persona por su id. Solo el personal puede pedir la lista de usuarios a la API;
// para un solicitante muestro "Soporte" o un marcador neutro, sin inventar nombres.
function personName(id) {
  if (id === null || id === undefined) {
    return "Sin asignar";
  }
  if (id === currentUser.id) {
    return "Yo";
  }
  return userNames.get(id) ?? `Usuario #${id}`;
}

function statusBadge(status) {
  return badge(label(STATUS_LABELS, status), `badge-status-${status}`);
}

function priorityBadge(priority) {
  return badge(label(PRIORITY_LABELS, priority), `badge-priority-${String(priority).toLowerCase()}`);
}

// 22/10/2026 - Enlace al detalle. Construyo la direccion con Number(): si el id no fuera un numero, saldria NaN
// y no un texto raro que alguien pudiera usar para colar otra ruta.
function ticketLink(ticket) {
  return el("a", { text: ticket.title, className: "fw-semibold", attrs: { href: `ticket.html?id=${Number(ticket.id)}` } });
}

function overdueBadge(ticket) {
  return ticket.is_overdue ? badge("Vencido", "badge-overdue ms-1") : null;
}

// 22/10/2026 - Vista de ESCRITORIO: una fila de la tabla. Mas columnas para el personal (solicitante y asignado).
function ticketRow(ticket) {
  const staffCells = isStaff(currentUser)
    ? [el("td", { text: personName(ticket.requester_id) }), el("td", { text: personName(ticket.assignee_id) })]
    : [];
  return el(
    "tr",
    {},
    el("th", { text: `#${ticket.id}`, attrs: { scope: "row" }, className: "text-nowrap" }),
    el("td", {}, ticketLink(ticket), overdueBadge(ticket)),
    el("td", { text: label(CATEGORY_LABELS, ticket.category) }),
    el("td", {}, priorityBadge(ticket.priority)),
    el("td", {}, statusBadge(ticket.status)),
    ...staffCells,
    el("td", { text: formatDate(ticket.created_at), className: "text-nowrap" }),
  );
}

function ticketsTable(items) {
  const staffHeads = isStaff(currentUser) ? ["Solicitante", "Asignado a"] : [];
  const heads = ["N.º", "Título", "Categoría", "Prioridad", "Estado", ...staffHeads, "Creado"];
  return el(
    "div",
    { className: "d-none d-md-block table-responsive" },
    el(
      "table",
      { className: "table table-hover align-middle bg-white border" },
      el("caption", { className: "visually-hidden", text: "Lista de tickets" }),
      el("thead", {}, el("tr", {}, ...heads.map((text) => el("th", { text, attrs: { scope: "col" } })))),
      el("tbody", {}, ...items.map(ticketRow)),
    ),
  );
}

// 22/10/2026 - Vista de TELEFONO: una tarjeta por ticket. Una tabla de 7 columnas no cabe en 390 px; la tarjeta
// apila la misma informacion y deja un area tactil grande en el titulo.
function ticketCard(ticket) {
  const staffLines = isStaff(currentUser)
    ? [
        el("div", { className: "small text-body-secondary", text: `Solicitante: ${personName(ticket.requester_id)}` }),
        el("div", { className: "small text-body-secondary", text: `Asignado a: ${personName(ticket.assignee_id)}` }),
      ]
    : [];
  return el(
    "article",
    { className: "card ticket-card" },
    el(
      "div",
      { className: "card-body" },
      el("div", { className: "d-flex justify-content-between gap-2 mb-1" }, el("span", { className: "text-body-secondary small", text: `Ticket #${ticket.id}` }), el("span", { className: "small text-body-secondary", text: formatDate(ticket.created_at) })),
      el("h2", { className: "h6 mb-2" }, ticketLink(ticket), overdueBadge(ticket)),
      el("div", { className: "d-flex flex-wrap gap-2 mb-2" }, statusBadge(ticket.status), priorityBadge(ticket.priority)),
      el("div", { className: "small text-body-secondary", text: `Categoría: ${label(CATEGORY_LABELS, ticket.category)}` }),
      ...staffLines,
    ),
  );
}

function emptyState() {
  const hint = isStaff(currentUser) ? "Prueba con otros filtros." : "Prueba con otros filtros o crea tu primer ticket.";
  return el(
    "div",
    { className: "card card-body text-center py-5" },
    el("p", { className: "h5", text: "No hay tickets para mostrar" }),
    el("p", { className: "text-body-secondary", text: hint }),
    el("div", {}, el("a", { className: "btn btn-primary", text: "Crear un ticket", attrs: { href: "ticket-new.html" } })),
  );
}

// 22/10/2026 - Paginacion: Anterior / "Pagina X de Y" / Siguiente. Son botones reales (no enlaces) porque
// cambian el estado de la pagina; el deshabilitado lo anuncia el lector de pantalla.
function renderPagination(total) {
  clear(pagination);
  const pages = pageCount(total, PAGE_SIZE);
  if (pages <= 1) {
    return;
  }
  const go = (page) => () => {
    state.page = page;
    writeStateToUrl();
    load().then(() => summary.focus());
  };
  const item = (text, page, disabled) =>
    el(
      "li",
      { className: `page-item${disabled ? " disabled" : ""}` },
      el("button", { className: "page-link", text, attrs: { type: "button", disabled }, on: { click: go(page) } }),
    );
  pagination.append(
    el(
      "ul",
      { className: "pagination justify-content-center align-items-center mb-0" },
      item("Anterior", state.page - 1, state.page <= 1),
      el("li", { className: "px-3 small", text: `Página ${state.page} de ${pages}` }),
      item("Siguiente", state.page + 1, state.page >= pages),
    ),
  );
}

// 22/10/2026 - Pide la pagina actual a la API y la dibuja. Muestra los tres estados: cargando (spinner),
// error (alerta) y datos (o el estado vacio).
async function load() {
  clearAlert(alertRegion);
  clear(pagination);
  summary.textContent = "";
  results.replaceChildren(loadingIndicator("Cargando tickets…"));
  setBusy(applyButton, true, "Buscando…");
  try {
    const page = await api.listTickets({
      status: state.status,
      category: state.category,
      priority: state.priority,
      assignee_id: state.mine ? currentUser.id : "",
      limit: PAGE_SIZE,
      offset: (state.page - 1) * PAGE_SIZE,
    });
    // Si despues de filtrar la pagina pedida ya no existe (quedaron menos tickets), voy a la ultima.
    if (page.items.length === 0 && page.total > 0 && state.page > 1) {
      state.page = pageCount(page.total, PAGE_SIZE);
      writeStateToUrl();
      return load();
    }
    summary.textContent = rangeText((state.page - 1) * PAGE_SIZE, page.items.length, page.total);
    results.replaceChildren(
      ...(page.items.length === 0
        ? [emptyState()]
        : [ticketsTable(page.items), el("div", { className: "d-md-none d-grid gap-3" }, ...page.items.map(ticketCard))]),
    );
    renderPagination(page.total);
  } catch (error) {
    results.replaceChildren();
    showAlert(alertRegion, userMessage(error));
  } finally {
    setBusy(applyButton, false);
  }
}

// 22/10/2026 - Cuando el usuario pulsa "Aplicar": tomo los valores del formulario, vuelvo a la pagina 1 y recargo.
function applyFilters(event) {
  event.preventDefault();
  const field = (name) => filtersForm.elements.namedItem(name);
  state = {
    status: field("status").value,
    category: field("category").value,
    priority: field("priority").value,
    mine: field("mine").checked,
    page: 1,
  };
  writeStateToUrl();
  load();
}

function resetFilters() {
  filtersForm.reset();
  state = { status: "", category: "", priority: "", mine: false, page: 1 };
  writeStateToUrl();
  load();
}

// 22/10/2026 - Para el personal traigo la lista de usuarios una vez y asi puedo mostrar nombres en vez de numeros.
// Si falla (por ejemplo, un permiso), la lista sigue funcionando con marcadores "Usuario #id".
async function loadUserNames() {
  try {
    const users = await api.listUsers();
    userNames = new Map(users.map((person) => [person.id, person.name]));
  } catch {
    userNames = new Map();
  }
}

currentUser = await bootPage("tickets");
if (currentUser) {
  state = readStateFromUrl();
  fillFilter(filtersForm.elements.namedItem("status"), STATUS_LABELS, "Todos", state.status);
  fillFilter(filtersForm.elements.namedItem("category"), CATEGORY_LABELS, "Todas", state.category);
  fillFilter(filtersForm.elements.namedItem("priority"), PRIORITY_LABELS, "Todas", state.priority);
  if (isStaff(currentUser)) {
    document.getElementById("mine-group").classList.remove("d-none");
    filtersForm.elements.namedItem("mine").checked = state.mine;
    await loadUserNames();
  } else {
    state.mine = false;
  }
  summary.setAttribute("tabindex", "-1");
  filtersForm.addEventListener("submit", applyFilters);
  document.getElementById("filters-reset").addEventListener("click", resetFilters);
  await load();
}
