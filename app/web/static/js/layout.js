/*
 * 22/10/2026 - Richard Ortiz: lo que comparten TODAS las paginas protegidas: exigir sesion, dibujar el menu
 * superior y mantener el contador de avisos. Cada pagina llama a bootPage() lo primero que hace.
 */

import { api, userMessage } from "./api.js";
import { ROLE_LABELS, label } from "./format.js";
import { isStaff } from "./rules.js";
import { clearSession, getToken, getUser, isSignedIn, saveUser } from "./session.js";
import { consumeFlash, el, focusTitle, showAlert, toast } from "./ui.js";

const LOGIN_PAGE = "index.html";

// 22/10/2026 - Cierra la sesion y vuelve al ingreso. `replace` (y no `assign`) para que el boton "Atras" no
// regrese a una pantalla que ya no puede mostrarse.
function signOut() {
  clearSession();
  window.location.replace(LOGIN_PAGE);
}

// 22/10/2026 - Un enlace del menu. `aria-current="page"` le dice al lector de pantalla cual es la pagina actual
// (y Bootstrap lo pinta como activo).
function navLink(href, text, isActive, ...extra) {
  return el(
    "li",
    { className: "nav-item" },
    el(
      "a",
      { className: `nav-link${isActive ? " active" : ""}`, text, attrs: { href, "aria-current": isActive ? "page" : false } },
      ...extra,
    ),
  );
}

// 22/10/2026 - Construye el menu superior. Un solicitante ve "Mis tickets"; el personal ve "Tickets" (todos).
// El colapso en pantallas pequenas lo hace Bootstrap con los atributos data-bs-*, sin JavaScript mio.
function buildNav(user, active) {
  // El numero es visual (aria-hidden); el texto oculto "avisos sin leer" es el que anuncia el lector de pantalla.
  const unreadBadge = el(
    "span",
    { className: "badge rounded-pill text-bg-light ms-1 d-none", attrs: { id: "unread-badge" } },
    el("span", { attrs: { id: "unread-count", "aria-hidden": "true" } }),
    el("span", { className: "visually-hidden", attrs: { id: "unread-text" } }),
  );
  const collapseId = "main-menu";
  return el(
    "nav",
    { className: "navbar navbar-expand-md navbar-dark app-navbar", attrs: { "aria-label": "Menú principal" } },
    el(
      "div",
      { className: "container" },
      el("a", { className: "navbar-brand fw-semibold", text: "HelpDesk EDU", attrs: { href: "tickets.html" } }),
      el(
        "button",
        {
          className: "navbar-toggler",
          attrs: {
            type: "button",
            "data-bs-toggle": "collapse",
            "data-bs-target": `#${collapseId}`,
            "aria-controls": collapseId,
            "aria-expanded": "false",
            "aria-label": "Mostrar u ocultar el menú",
          },
        },
        el("span", { className: "navbar-toggler-icon" }),
      ),
      el(
        "div",
        { className: "collapse navbar-collapse", attrs: { id: collapseId } },
        el(
          "ul",
          { className: "navbar-nav me-auto mb-2 mb-md-0" },
          navLink("tickets.html", isStaff(user) ? "Tickets" : "Mis tickets", active === "tickets"),
          navLink("ticket-new.html", "Nuevo ticket", active === "ticket-new"),
          navLink("notifications.html", "Avisos", active === "notifications", unreadBadge),
        ),
        el(
          "div",
          { className: "d-flex flex-column flex-md-row align-items-md-center gap-2 text-white" },
          el("span", { className: "small", text: `${user.name} · ${label(ROLE_LABELS, user.role)}` }),
          el("button", {
            className: "btn btn-outline-light btn-sm",
            text: "Cerrar sesión",
            attrs: { type: "button" },
            on: { click: signOut },
          }),
        ),
      ),
    ),
  );
}

// 22/10/2026 - Muestra (o esconde) el numero de avisos sin leer junto a "Avisos". El lector de pantalla
// oye "3 avisos sin leer" y no solo "3".
export function setUnreadBadge(count) {
  const badgeNode = document.getElementById("unread-badge");
  if (!badgeNode) {
    return;
  }
  document.getElementById("unread-count").textContent = String(count);
  document.getElementById("unread-text").textContent = count === 1 ? " (1 aviso sin leer)" : ` (${count} avisos sin leer)`;
  badgeNode.classList.toggle("d-none", count === 0);
}

// 22/10/2026 - Punto de entrada de cada pagina protegida. Devuelve el usuario, o null si no hay sesion
// (en ese caso ya redirigio al ingreso y la pagina debe detenerse: `if (!user) return;`).
export async function bootPage(active) {
  if (!isSignedIn()) {
    window.location.replace(LOGIN_PAGE);
    return null;
  }
  // Si el usuario sale (boton Atras desde otra pagina) y el navegador restaura esta pantalla de su cache,
  // no hay que mostrar datos de una sesion que ya se cerro.
  window.addEventListener("pageshow", (event) => {
    if (event.persisted && getToken() === null) {
      window.location.replace(LOGIN_PAGE);
    }
  });

  let user = getUser();
  if (!user) {
    try {
      user = await api.me();
    } catch (error) {
      // Un 401 ya redirigio dentro de api.js; cualquier otro fallo (red, servidor) se explica en pantalla.
      showAlert(document.getElementById("alert-region"), userMessage(error));
      return null;
    }
    saveUser(user);
  }
  document.getElementById("site-nav").replaceChildren(buildNav(user, active));
  focusTitle();
  const flash = consumeFlash();
  if (flash) {
    toast(flash);
  }

  // El contador es un lujo: si falla, la pagina sigue funcionando.
  api.notifications().then((items) => setUnreadBadge(items.length)).catch(() => {});
  return user;
}
