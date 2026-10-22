/*
 * 22/10/2026 - Richard Ortiz: piezas de interfaz reutilizables (DOM) y la regla de oro de seguridad del cliente:
 *
 *   NUNCA se pinta un dato de la API con innerHTML. Se crea el elemento y se le asigna textContent.
 *
 * ¿Por que? Una descripcion de ticket como  <img src=x onerror="robarToken()">  es solo TEXTO para la API, pero si la
 * convierto en HTML el navegador ejecuta ese codigo con acceso al token (XSS almacenado). Con textContent el
 * navegador la muestra literalmente, como letras. Por eso `el()` solo sabe crear nodos de texto y por eso una
 * prueba de pytest falla si aparece la palabra innerHTML en cualquier archivo de js/.
 *
 * Aqui tambien viven los tres estados que toda pantalla debe tener: cargando (spinner), error (alerta
 * anunciada a lectores de pantalla) y exito (aviso emergente).
 */

// 22/10/2026 - Atributos que jamas dejo asignar desde datos: manejadores de eventos y contenido ejecutable.
function isForbiddenAttribute(name, value) {
  const lower = name.toLowerCase();
  if (lower.startsWith("on") || lower === "srcdoc" || lower === "style") {
    return true;
  }
  return ["href", "src", "action"].includes(lower) && /^\s*(javascript|data|vbscript):/i.test(String(value));
}

// 22/10/2026 - Crea un elemento: el(etiqueta, { className, text, attrs, on }, ...hijos).
// `text` va por textContent (seguro), `on` registra oyentes con addEventListener (nunca atributos onclick),
// y los hijos pueden ser nodos o cadenas (las cadenas se convierten en nodos de texto).
export function el(tag, { className, text, attrs = {}, on = {} } = {}, ...children) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = String(text);
  }
  for (const [name, value] of Object.entries(attrs)) {
    if (value === false || value === null || value === undefined) {
      continue;
    }
    if (isForbiddenAttribute(name, value)) {
      throw new Error(`Atributo no permitido: ${name}`);
    }
    node.setAttribute(name, value === true ? "" : String(value));
  }
  for (const [eventName, handler] of Object.entries(on)) {
    node.addEventListener(eventName, handler);
  }
  node.append(...children.flat().filter((child) => child !== null && child !== undefined && child !== false));
  return node;
}

// 22/10/2026 - Vacia un contenedor sin usar HTML (replaceChildren no interpreta cadenas como marcado).
export function clear(container) {
  container.replaceChildren();
}

// 22/10/2026 - Estado "cargando": un spinner con role="status" para que el lector de pantalla diga "Cargando...".
export function loadingIndicator(message = "Cargando…") {
  return el(
    "div",
    { className: "d-flex align-items-center gap-2 text-secondary py-4", attrs: { role: "status" } },
    el("span", { className: "spinner-border spinner-border-sm", attrs: { "aria-hidden": "true" } }),
    el("span", { text: message }),
  );
}

// 22/10/2026 - Estado "error": muestra una alerta dentro de la region #alert-region, que esta marcada con
// aria-live="assertive": el lector de pantalla la lee en cuanto aparece, sin que el usuario tenga que buscarla.
export function showAlert(region, message, kind = "danger") {
  region.replaceChildren(
    el(
      "div",
      { className: `alert alert-${kind} d-flex justify-content-between align-items-start gap-3`, attrs: { role: "alert", tabindex: "-1" } },
      el("span", { text: message }),
      el("button", {
        className: "btn-close",
        attrs: { type: "button", "aria-label": "Cerrar mensaje" },
        on: { click: () => clear(region) },
      }),
    ),
  );
}

// 22/10/2026 - Mueve el foco a la alerta visible. Lo uso cuando una accion del usuario falla: el lector de pantalla
// ya la anuncio por aria-live, y con el foco quien navega con teclado queda justo donde esta el mensaje.
export function focusAlert(region) {
  region.querySelector(".alert")?.focus();
}

// 22/10/2026 - Quita la alerta anterior (por ejemplo, al volver a enviar un formulario).
export function clearAlert(region) {
  clear(region);
}

let toastContainer = null;

// 22/10/2026 - Estado "exito": un aviso emergente que desaparece solo a los 6 s. Vive en un contenedor
// aria-live="polite": el lector lo anuncia sin interrumpir lo que esta leyendo.
export function toast(message, kind = "success") {
  if (toastContainer === null || !toastContainer.isConnected) {
    toastContainer = el("div", {
      className: "toast-container position-fixed bottom-0 end-0 p-3",
      attrs: { "aria-live": "polite", "aria-atomic": "false" },
    });
    document.body.append(toastContainer);
  }
  const node = el(
    "div",
    { className: `toast show align-items-center border-0 text-bg-${kind}`, attrs: { role: "status" } },
    el(
      "div",
      { className: "d-flex" },
      el("div", { className: "toast-body", text: message }),
      el("button", {
        className: "btn-close btn-close-white me-2 m-auto",
        attrs: { type: "button", "aria-label": "Cerrar aviso" },
        on: { click: () => node.remove() },
      }),
    ),
  );
  toastContainer.append(node);
  setTimeout(() => node.remove(), 6000);
}

const FLASH_KEY = "helpdesk.flash";

// 22/10/2026 - Un toast que debe verse en la PAGINA SIGUIENTE (por ejemplo "Ticket #7 creado" justo antes de ir
// a su detalle). Lo dejo en sessionStorage y la pagina que cargue lo muestra una sola vez (consumeFlash).
export function setFlash(message) {
  globalThis.sessionStorage.setItem(FLASH_KEY, message);
}

// 22/10/2026 - Lee y BORRA el mensaje pendiente; null si no habia ninguno.
export function consumeFlash() {
  const message = globalThis.sessionStorage.getItem(FLASH_KEY);
  globalThis.sessionStorage.removeItem(FLASH_KEY);
  return message;
}

// 22/10/2026 - Boton "ocupado": se deshabilita (evita el doble clic que crearia dos tickets) y muestra un
// spinner con el texto de lo que esta pasando. Al terminar, regresa a su texto original.
export function setBusy(button, busy, busyLabel = "Enviando…") {
  if (busy) {
    // Si ya estaba ocupado (una recarga encadenada), conservo el texto original y no el del spinner.
    if (button.getAttribute("aria-busy") !== "true") {
      button.dataset.label = button.textContent;
    }
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.replaceChildren(
      el("span", { className: "spinner-border spinner-border-sm me-2", attrs: { "aria-hidden": "true" } }),
      busyLabel,
    );
  } else {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.textContent = button.dataset.label ?? button.textContent;
  }
}

// 22/10/2026 - Marca campos invalidos: borde rojo (is-invalid), aria-invalid, y el mensaje enlazado con
// aria-describedby para que el lector lo lea al enfocar el campo. Despues pone el foco en el PRIMER campo con error.
export function showFieldErrors(form, errors) {
  clearFieldErrors(form);
  let first = null;
  for (const [name, message] of Object.entries(errors)) {
    const field = form.elements.namedItem(name);
    if (!field || !(field instanceof HTMLElement)) {
      continue;
    }
    const feedbackId = `${field.id || name}-error`;
    field.classList.add("is-invalid");
    field.setAttribute("aria-invalid", "true");
    field.setAttribute("aria-describedby", feedbackId);
    field.insertAdjacentElement("afterend", el("div", { className: "invalid-feedback", text: message, attrs: { id: feedbackId } }));
    first ??= field;
  }
  first?.focus();
  return first !== null;
}

// 22/10/2026 - Limpia los errores de campo de un formulario antes de validar otra vez.
export function clearFieldErrors(form) {
  for (const field of form.querySelectorAll(".is-invalid")) {
    field.classList.remove("is-invalid");
    field.removeAttribute("aria-invalid");
    field.removeAttribute("aria-describedby");
  }
  for (const feedback of form.querySelectorAll(".invalid-feedback")) {
    feedback.remove();
  }
}

// 22/10/2026 - Despues de cargar una pagina o de un error, el foco va al titulo (h1 con tabindex="-1"):
// quien navega con teclado o lector de pantalla sabe donde esta sin recorrer el menu otra vez.
export function focusTitle() {
  document.getElementById("page-title")?.focus();
}

// 22/10/2026 - Insignia (badge) de texto; `className` trae el color (ver css/app.css).
export function badge(text, className) {
  return el("span", { className: `badge ${className}`, text });
}
