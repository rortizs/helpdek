/*
 * 22/10/2026 - Richard Ortiz: logica del formulario "Nuevo ticket" (ticket-new.html).
 * Orden: validacion local (rapida) -> POST /api/tickets -> si la API dice 422, mostrar sus errores por campo.
 * Al crear, aviso con un toast y llevo al detalle del ticket nuevo.
 */

import { api, fieldErrors, userMessage, ApiError } from "../api.js";
import { CATEGORY_LABELS, PRIORITY_LABELS } from "../format.js";
import { bootPage } from "../layout.js";
import { CATEGORIES, PRIORITIES, validateTicketForm } from "../validation.js";
import { clearAlert, clearFieldErrors, el, setBusy, setFlash, showAlert, showFieldErrors } from "../ui.js";

const form = document.getElementById("ticket-form");
const alertRegion = document.getElementById("alert-region");
const submitButton = document.getElementById("ticket-submit");

// 22/10/2026 - Llena un <select> desde las listas de validation.js (una sola fuente de verdad) con etiquetas en espanol.
function fillSelect(select, values, labels, placeholder, selected) {
  if (placeholder) {
    select.append(el("option", { text: placeholder, attrs: { value: "" } }));
  }
  for (const value of values) {
    select.append(el("option", { text: labels[value], attrs: { value, selected: value === selected } }));
  }
}

// 22/10/2026 - Envio del formulario. Los errores locales y los del servidor usan el MISMO mecanismo
// (showFieldErrors), asi el usuario no distingue de donde vinieron: solo ve que campo corregir.
async function handleSubmit(event) {
  event.preventDefault();
  clearAlert(alertRegion);
  clearFieldErrors(form);

  // OJO: leo los campos por `form.elements` y no con `form.title`: en un <form>, `title` tambien es el atributo
  // de tooltip del propio formulario y la confusion es facil.
  const field = (name) => form.elements.namedItem(name).value;
  const values = {
    title: field("title"),
    description: field("description"),
    category: field("category"),
    priority: field("priority"),
  };
  const localErrors = validateTicketForm(values);
  if (Object.keys(localErrors).length > 0) {
    showFieldErrors(form, localErrors);
    return;
  }

  setBusy(submitButton, true, "Creando ticket…");
  try {
    const ticket = await api.createTicket({ ...values, title: values.title.trim() });
    setFlash(`Ticket #${ticket.id} creado correctamente.`);
    window.location.assign(`ticket.html?id=${Number(ticket.id)}`);
  } catch (error) {
    setBusy(submitButton, false);
    const serverErrors = error instanceof ApiError && error.status === 422 ? fieldErrors(error) : {};
    const shown = Object.keys(serverErrors).length > 0 && showFieldErrors(form, serverErrors);
    // Si ningun campo del formulario coincide con el error, lo digo en la alerta general.
    if (!shown) {
      showAlert(alertRegion, userMessage(error));
    }
  }
}

const user = await bootPage("ticket-new");
if (user) {
  fillSelect(form.elements.namedItem("category"), CATEGORIES, CATEGORY_LABELS, "Selecciona una categoría", "");
  fillSelect(form.elements.namedItem("priority"), PRIORITIES, PRIORITY_LABELS, null, "Medium");
  form.addEventListener("submit", handleSubmit);
}
