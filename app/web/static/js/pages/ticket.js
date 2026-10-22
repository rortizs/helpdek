/*
 * 22/10/2026 - Richard Ortiz: logica del DETALLE de un ticket (ticket.html?id=N).
 *
 * Idea central: la pantalla muestra solo lo que el rol puede hacer (rules.js), pero NO confia en eso para la
 * seguridad. Cada accion vuelve a pasar por la API, que revisa permisos y flujo de estados; si responde 403 o
 * 409, el usuario ve un mensaje claro en la alerta y nada se rompe.
 */

import { api, fieldErrors, userMessage } from "../api.js";
import {
  CATEGORY_LABELS,
  PRIORITY_LABELS,
  ROLE_LABELS,
  STATUS_LABELS,
  eventLabel,
  formatDateTime,
  historyDetail,
  label,
} from "../format.js";
import { bootPage } from "../layout.js";
import { allowedTransitions, canCancel, isAssignable, isStaff, isTicketOpen } from "../rules.js";
import {
  badge,
  clearAlert,
  clearFieldErrors,
  el,
  focusAlert,
  loadingIndicator,
  setBusy,
  showAlert,
  showFieldErrors,
  toast,
} from "../ui.js";
import { PRIORITIES, validateComment } from "../validation.js";

const view = document.getElementById("ticket-view");
const alertRegion = document.getElementById("alert-region");
const pageTitle = document.getElementById("page-title");

let user = null;
let ticketId = null;
let userNames = new Map();
let assignableUsers = [];

// 22/10/2026 - El numero viene en la direccion y lo controla quien arma el enlace: solo acepto digitos.
function readTicketId() {
  const raw = new URLSearchParams(window.location.search).get("id") ?? "";
  return /^\d{1,9}$/.test(raw) ? Number(raw) : null;
}

// 22/10/2026 - Nombre de quien escribio o actuo. El personal conoce la lista de usuarios; un solicitante solo
// puede ver SU ticket, asi que cualquier otra persona que aparezca ahi es del equipo de soporte.
function personName(id) {
  if (id === null || id === undefined) {
    return "Sin asignar";
  }
  if (id === user.id) {
    return "Tú";
  }
  return isStaff(user) ? (userNames.get(id) ?? `Usuario #${id}`) : "Soporte";
}

// --- piezas de dibujo -----------------------------------------------------------------

function card(titleId, titleText, ...body) {
  return el(
    "section",
    { className: "card mb-3", attrs: { "aria-labelledby": titleId } },
    el("div", { className: "card-body" }, el("h2", { className: "h5 mb-3", text: titleText, attrs: { id: titleId, tabindex: "-1" } }), ...body),
  );
}

function definition(term, value) {
  return [el("dt", { className: "col-sm-4 text-body-secondary fw-normal", text: term }), el("dd", { className: "col-sm-8", text: value })];
}

// 22/10/2026 - Resumen del ticket: estado, prioridad, descripcion (respetando saltos de linea con CSS, no con HTML) y fechas.
function renderSummary(ticket) {
  return card(
    "summary-title",
    ticket.title,
    el(
      "div",
      { className: "d-flex flex-wrap gap-2 mb-3" },
      badge(label(STATUS_LABELS, ticket.status), `badge-status-${ticket.status}`),
      badge(label(PRIORITY_LABELS, ticket.priority), `badge-priority-${String(ticket.priority).toLowerCase()}`),
      ticket.is_overdue ? badge("Vencido", "badge-overdue") : null,
    ),
    el("p", { className: "pre-wrap", text: ticket.description }),
    el(
      "dl",
      { className: "row mb-0" },
      ...definition("Categoría", label(CATEGORY_LABELS, ticket.category)),
      ...definition("Solicitante", personName(ticket.requester_id)),
      ...definition("Asignado a", personName(ticket.assignee_id)),
      ...definition("Creado", formatDateTime(ticket.created_at)),
      ...definition("Actualizado", formatDateTime(ticket.updated_at)),
      ...definition("Vence", formatDateTime(ticket.due_at)),
    ),
  );
}

// 22/10/2026 - Un formulario de accion: etiqueta + control + boton. `onSubmit` recibe el boton para marcarlo ocupado.
function actionForm({ id, labelText, control, buttonText, busyLabel, run, success, validate = () => null }) {
  control.id = id;
  control.classList.add("form-select");
  const button = el("button", { className: "btn btn-primary", text: buttonText, attrs: { type: "submit" } });
  return el(
    "form",
    {
      className: "mb-3",
      attrs: { novalidate: true },
      on: {
        submit: (event) => {
          event.preventDefault();
          // Validacion local minima (por ejemplo "no elegiste a nadie"): ni siquiera gasto una peticion.
          const problem = validate(control.value);
          if (problem) {
            showAlert(alertRegion, problem);
            focusAlert(alertRegion);
            return;
          }
          runAction(button, busyLabel, () => run(control.value), success);
        },
      },
    },
    el("label", { className: "form-label", text: labelText, attrs: { for: id } }),
    el("div", { className: "d-flex gap-2" }, control, button),
  );
}

function optionList(entries, selected) {
  return entries.map(([value, text]) => el("option", { text, attrs: { value, selected: String(value) === String(selected) } }));
}

// 22/10/2026 - Acciones segun el rol. El personal ve estado, asignacion y prioridad; el solicitante dueno ve "Cancelar".
// Un ticket cerrado o cancelado ya no admite cambios (la API tambien lo rechaza).
function renderActions(ticket) {
  const controls = [];
  if (isStaff(user) && isTicketOpen(ticket)) {
    const transitions = allowedTransitions(ticket.status);
    if (transitions.length > 0) {
      controls.push(
        actionForm({
          id: "action-status",
          labelText: "Cambiar estado",
          control: el("select", {}, ...optionList(transitions.map((status) => [status, label(STATUS_LABELS, status)]), "")),
          buttonText: "Aplicar",
          busyLabel: "Aplicando…",
          run: (status) => api.changeStatus(ticket.id, status),
          success: "Estado actualizado.",
        }),
      );
    }
    if (assignableUsers.length > 0) {
      controls.push(
        actionForm({
          id: "action-assign",
          labelText: "Asignar a",
          control: el(
            "select",
            {},
            ...optionList([["", "Selecciona una persona"], ...assignableUsers.map((person) => [person.id, person.name])], ticket.assignee_id ?? ""),
          ),
          buttonText: "Asignar",
          busyLabel: "Asignando…",
          validate: (technicianId) => (technicianId === "" ? "Elige a quién asignar el ticket." : null),
          run: (technicianId) => api.assign(ticket.id, Number(technicianId)),
          success: "Ticket asignado.",
        }),
      );
    }
    controls.push(
      actionForm({
        id: "action-priority",
        labelText: "Cambiar prioridad",
        control: el("select", {}, ...optionList(PRIORITIES.map((priority) => [priority, label(PRIORITY_LABELS, priority)]), ticket.priority)),
        buttonText: "Cambiar",
        busyLabel: "Cambiando…",
        run: (priority) => api.changePriority(ticket.id, priority),
        success: "Prioridad actualizada.",
      }),
    );
  }
  if (canCancel(user, ticket)) {
    const button = el("button", { className: "btn btn-outline-danger", text: "Cancelar ticket", attrs: { type: "button" } });
    button.addEventListener("click", () => {
      // confirm() es un dialogo nativo: accesible por teclado y lector de pantalla sin escribir nada extra.
      if (window.confirm("¿Seguro que quieres cancelar este ticket? Esta acción no se puede deshacer.")) {
        runAction(button, "Cancelando…", () => api.cancel(ticket.id), "Ticket cancelado.");
      }
    });
    controls.push(el("div", { className: "mb-3" }, button));
  }
  if (!isTicketOpen(ticket)) {
    controls.push(el("p", { className: "text-body-secondary mb-0", text: "Este ticket está cerrado o cancelado y ya no admite cambios." }));
  } else if (controls.length === 0) {
    controls.push(el("p", { className: "text-body-secondary mb-0", text: "No hay acciones disponibles para tu rol en este ticket." }));
  }
  return card("actions-title", "Acciones", ...controls);
}

// 22/10/2026 - Comentarios. El formulario solo existe mientras el ticket este abierto.
function renderComments(ticket) {
  const items = ticket.comments.map((comment) =>
    el(
      "li",
      { className: "comment" },
      el("div", { className: "small text-body-secondary", text: `${personName(comment.author_id)} · ${formatDateTime(comment.created_at)}` }),
      el("p", { className: "pre-wrap mb-0", text: comment.body }),
    ),
  );
  const list =
    items.length === 0
      ? el("p", { className: "text-body-secondary", text: "Aún no hay comentarios." })
      : el("ul", { className: "list-unstyled comment-list" }, ...items);
  return card("comments-title", `Comentarios (${ticket.comments.length})`, list, isTicketOpen(ticket) ? commentForm(ticket) : null);
}

function commentForm(ticket) {
  const area = el("textarea", { className: "form-control", attrs: { id: "comment-body", name: "body", rows: "3", required: true } });
  const button = el("button", { className: "btn btn-primary", text: "Enviar comentario", attrs: { type: "submit" } });
  const form = el(
    "form",
    { attrs: { novalidate: true }, className: "mt-3" },
    el("label", { className: "form-label", text: "Nuevo comentario", attrs: { for: "comment-body" } }),
    area,
    el("div", { className: "mt-2" }, button),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearAlert(alertRegion);
    clearFieldErrors(form);
    const errors = validateComment(area.value);
    if (Object.keys(errors).length > 0) {
      showFieldErrors(form, errors);
      return;
    }
    await runAction(button, "Enviando…", () => api.addComment(ticket.id, area.value.trim()), "Comentario agregado.", {
      form,
      focusId: "comments-title",
    });
  });
  return form;
}

// 22/10/2026 - Historial: quien hizo que y cuando, del mas antiguo al mas reciente (el orden en que llega de la API).
function renderHistory(ticket) {
  const items = ticket.history.map((event) => {
    const detail = historyDetail(event.event_type, event.detail);
    return el(
      "li",
      { className: "list-group-item" },
      el("div", { className: "d-flex justify-content-between gap-2" }, el("strong", { text: eventLabel(event.event_type) }), el("span", { className: "small text-body-secondary text-nowrap", text: formatDateTime(event.created_at) })),
      el("div", { className: "small text-body-secondary", text: detail === "" ? personName(event.actor_id) : `${personName(event.actor_id)} · ${detail}` }),
    );
  });
  return card(
    "history-title",
    "Historial",
    items.length === 0 ? el("p", { className: "text-body-secondary mb-0", text: "Sin eventos todavía." }) : el("ol", { className: "list-group list-group-flush" }, ...items),
  );
}

function renderTicket(ticket) {
  pageTitle.textContent = `Ticket #${ticket.id}`;
  document.title = `Ticket #${ticket.id} · HelpDesk EDU`;
  view.replaceChildren(
    el("div", { className: "row g-3" }, el("div", { className: "col-lg-8" }, renderSummary(ticket)), el("div", { className: "col-lg-4" }, renderActions(ticket))),
    el("div", { className: "row g-3" }, el("div", { className: "col-lg-8" }, renderComments(ticket)), el("div", { className: "col-lg-4" }, renderHistory(ticket))),
  );
}

// --- carga y acciones -------------------------------------------------------------------

// 22/10/2026 - Pide el ticket completo (con comentarios e historial) y lo dibuja. Estados: cargando, error, datos.
// `focusId` dice a donde mandar el foco al terminar: sin esto, al redibujar, el teclado se quedaria en el vacio.
async function loadTicket(focusId = null) {
  view.replaceChildren(loadingIndicator("Cargando ticket…"));
  try {
    renderTicket(await api.getTicket(ticketId));
    (document.getElementById(focusId ?? "") ?? document.getElementById("page-title")).focus();
  } catch (error) {
    view.replaceChildren();
    pageTitle.textContent = "Ticket no disponible";
    showAlert(alertRegion, userMessage(error));
    focusAlert(alertRegion);
  }
}

// 22/10/2026 - Ejecuta una accion contra la API con los tres estados: boton ocupado, exito (toast + recarga)
// o error (alerta con el mensaje en espanol; un 403 o 409 es un resultado normal, no un fallo del cliente).
async function runAction(button, busyLabel, action, successMessage, { form = null, focusId = "page-title" } = {}) {
  clearAlert(alertRegion);
  setBusy(button, true, busyLabel);
  try {
    await action();
  } catch (error) {
    setBusy(button, false);
    const errors = form ? fieldErrors(error) : {};
    if (!(Object.keys(errors).length > 0 && showFieldErrors(form, errors))) {
      showAlert(alertRegion, userMessage(error));
      focusAlert(alertRegion);
    }
    return;
  }
  toast(successMessage);
  await loadTicket(focusId);
}

// 22/10/2026 - Para el personal traigo los usuarios una vez: sirven para mostrar nombres y para el selector de "Asignar a".
async function loadPeople() {
  try {
    const users = await api.listUsers();
    userNames = new Map(users.map((person) => [person.id, `${person.name} (${label(ROLE_LABELS, person.role)})`]));
    assignableUsers = users.filter(isAssignable);
  } catch {
    userNames = new Map();
    assignableUsers = [];
  }
}

user = await bootPage("tickets");
if (user) {
  ticketId = readTicketId();
  if (ticketId === null) {
    pageTitle.textContent = "Ticket no disponible";
    showAlert(alertRegion, "La dirección no incluye un número de ticket válido.");
  } else {
    if (isStaff(user)) {
      await loadPeople();
    }
    await loadTicket();
  }
}
