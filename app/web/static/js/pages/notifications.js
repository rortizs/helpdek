/*
 * 22/10/2026 - Richard Ortiz: logica de los AVISOS (notifications.html).
 * GET /api/notifications entrega solo los avisos SIN LEER de quien tiene la sesion; POST /api/notifications/read-all
 * los marca todos y responde cuantos fueron. Los textos de cada aviso los escribe el servidor: se pintan con
 * textContent, jamas como HTML.
 */

import { api, userMessage } from "../api.js";
import { formatDateTime } from "../format.js";
import { bootPage, setUnreadBadge } from "../layout.js";
import { clearAlert, el, loadingIndicator, setBusy, showAlert, toast } from "../ui.js";

const list = document.getElementById("notifications-list");
const summary = document.getElementById("notifications-summary");
const readAllButton = document.getElementById("read-all");
const alertRegion = document.getElementById("alert-region");

// 22/10/2026 - Un aviso: titulo, mensaje, fecha y enlace al ticket del que habla (si lo tiene).
function notificationItem(notification) {
  const link =
    notification.ticket_id === null
      ? null
      : el("a", {
          text: `Ver ticket #${notification.ticket_id}`,
          className: "small",
          attrs: { href: `ticket.html?id=${Number(notification.ticket_id)}` },
        });
  return el(
    "li",
    { className: "list-group-item" },
    el(
      "div",
      { className: "d-flex justify-content-between gap-2" },
      el("strong", { text: notification.title }),
      el("span", { className: "small text-body-secondary text-nowrap", text: formatDateTime(notification.created_at) }),
    ),
    el("p", { className: "mb-1", text: notification.message }),
    link,
  );
}

// 22/10/2026 - Dibuja la lista (o el estado vacio) y ajusta el resumen, el boton y el contador del menu.
function render(items) {
  setUnreadBadge(items.length);
  readAllButton.disabled = items.length === 0;
  summary.textContent = items.length === 0 ? "Estás al día." : `${items.length} avisos sin leer`;
  if (items.length === 0) {
    list.replaceChildren(
      el("div", { className: "card card-body text-center py-5" }, el("p", { className: "h5 mb-1", text: "No tienes avisos nuevos" }), el("p", { className: "text-body-secondary mb-0", text: "Cuando alguien comente o cambie tus tickets, lo verás aquí." })),
    );
    return;
  }
  list.replaceChildren(el("ul", { className: "list-group" }, ...items.map(notificationItem)));
}

// 22/10/2026 - Carga los avisos con estados de cargando y de error.
async function load() {
  clearAlert(alertRegion);
  list.replaceChildren(loadingIndicator("Cargando avisos…"));
  try {
    render(await api.notifications());
  } catch (error) {
    list.replaceChildren();
    showAlert(alertRegion, userMessage(error));
  }
}

// 22/10/2026 - "Marcar todo como leido": la API responde {updated: n}; confirmo con un toast y vuelvo a cargar.
async function markAllRead() {
  clearAlert(alertRegion);
  setBusy(readAllButton, true, "Marcando…");
  try {
    const result = await api.markAllRead();
    toast(result.updated === 1 ? "1 aviso marcado como leído." : `${result.updated} avisos marcados como leídos.`);
    await load();
  } catch (error) {
    showAlert(alertRegion, userMessage(error));
  } finally {
    setBusy(readAllButton, false);
    readAllButton.disabled = list.querySelector("li") === null;
  }
}

const user = await bootPage("notifications");
if (user) {
  readAllButton.addEventListener("click", markAllRead);
  await load();
}
