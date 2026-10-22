/*
 * 22/10/2026 - Richard Ortiz: funciones PURAS de presentacion (texto, fechas, etiquetas en espanol).
 * No tocan el DOM ni la red, asi que se pueden probar con `node --test` (ver tests/web/).
 * Los valores que viajan por la API estan en ingles (open, High...); aqui los traduzco para la pantalla.
 */

export const STATUS_LABELS = {
  open: "Abierto",
  in_progress: "En progreso",
  resolved: "Resuelto",
  closed: "Cerrado",
  cancelled: "Cancelado",
};

export const PRIORITY_LABELS = {
  Low: "Baja",
  Medium: "Media",
  High: "Alta",
  Critical: "Crítica",
};

export const CATEGORY_LABELS = {
  General: "General",
  Hardware: "Hardware",
  Software: "Software",
  Network: "Red",
  Security: "Seguridad",
  Other: "Otra",
};

export const ROLE_LABELS = {
  requester: "Solicitante",
  technician: "Técnico",
  supervisor: "Supervisor",
  administrator: "Administrador",
};

const EVENT_LABELS = {
  created: "Ticket creado",
  assigned: "Asignación",
  commented: "Comentario",
  status_changed: "Cambio de estado",
  priority_changed: "Cambio de prioridad",
  cancelled: "Cancelación",
};

// 22/10/2026 - Traduce un valor de la API con su tabla; si llega algo desconocido, lo muestro tal cual
// en vez de romper la pantalla (la API puede crecer antes que este cliente).
export function label(table, value) {
  return Object.hasOwn(table, value) ? table[value] : String(value ?? "");
}

// 22/10/2026 - Nombre en espanol de un tipo de evento del historial del ticket.
export function eventLabel(type) {
  return label(EVENT_LABELS, type);
}

// 22/10/2026 - La API entrega fechas SIN zona (hora de pared de Guatemala). Si las pasara por `new Date()`,
// el navegador las interpretaria en SU zona y podria mover la hora. Por eso leo los numeros del texto
// y los muestro como vienen: dd/mm/aaaa hh:mm.
export function formatDateTime(isoText) {
  const match = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(String(isoText ?? ""));
  if (!match) {
    return "—";
  }
  const [, year, month, day, hour, minute] = match;
  return `${day}/${month}/${year} ${hour}:${minute}`;
}

// 22/10/2026 - Solo la parte de fecha (dd/mm/aaaa), para tablas angostas.
export function formatDate(isoText) {
  const full = formatDateTime(isoText);
  return full === "—" ? full : full.slice(0, 10);
}

// 22/10/2026 - Texto "1–10 de 37" para la paginacion; con 0 resultados devuelvo "0 resultados".
export function rangeText(offset, count, total) {
  if (total === 0 || count === 0) {
    return "0 resultados";
  }
  return `${offset + 1}–${offset + count} de ${total}`;
}

// 22/10/2026 - Cuantas paginas hay para `total` elementos con `pageSize` por pagina (minimo 1).
export function pageCount(total, pageSize) {
  return Math.max(1, Math.ceil(total / pageSize));
}

// 22/10/2026 - El historial guarda `detail` en ingles tecnico ("assigned to Ana", "in_progress", "High -> Low").
// Lo traduzco segun el tipo de evento para mostrar algo legible; si no reconozco el formato, lo devuelvo igual.
export function historyDetail(eventType, detail) {
  const text = String(detail ?? "");
  switch (eventType) {
    case "status_changed":
      return label(STATUS_LABELS, text);
    case "priority_changed":
      return text
        .split(" -> ")
        .map((part) => label(PRIORITY_LABELS, part))
        .join(" → ");
    case "assigned":
      return text.startsWith("assigned to ") ? `A ${text.slice("assigned to ".length)}` : text;
    case "commented":
    case "cancelled":
      return "";
    default:
      return text;
  }
}
