/*
 * 22/10/2026 - Richard Ortiz: reglas de negocio que el cliente CONOCE para decidir que botones mostrar.
 *
 * Ojo con el limite: estas reglas solo sirven para no ofrecer acciones que seguro fallarian. La autoridad
 * es la API (app/services/tickets.py y app/domain/workflow.py). Si alguien edita este archivo en el
 * navegador y muestra un boton que no le toca, la API contesta 403 y la pantalla lo explica.
 */

// 22/10/2026 - Copia de TRANSITIONS de app/domain/workflow.py: de que estado se puede pasar a cuales.
export const TRANSITIONS = {
  open: ["in_progress", "cancelled"],
  in_progress: ["open", "resolved", "cancelled"],
  resolved: ["in_progress", "closed"],
  closed: [],
  cancelled: [],
};

const STAFF_ROLES = ["technician", "supervisor", "administrator"];
const ASSIGNABLE_ROLES = ["technician", "supervisor"];

// 22/10/2026 - Personal de soporte = tecnico, supervisor o administrador (igual que User.is_staff en Python).
export function isStaff(user) {
  return Boolean(user) && STAFF_ROLES.includes(user.role);
}

// 22/10/2026 - Roles a los que la API permite asignar un ticket (assignee must be support staff).
export function isAssignable(user) {
  return Boolean(user) && ASSIGNABLE_ROLES.includes(user.role);
}

// 22/10/2026 - Estados a los que puede pasar un ticket desde `status`; lista vacia si ya esta cerrado o cancelado.
export function allowedTransitions(status) {
  return Object.hasOwn(TRANSITIONS, status) ? TRANSITIONS[status] : [];
}

// 22/10/2026 - Un ticket "abierto" para la API es todo el que no esta cerrado ni cancelado (Ticket.is_open).
export function isTicketOpen(ticket) {
  return Boolean(ticket) && !["closed", "cancelled"].includes(ticket.status);
}

// 22/10/2026 - Cancelar es SOLO del solicitante que abrio el ticket (TicketService.cancel), y solo mientras
// el flujo lo permita: desde abierto o en progreso. Un tecnico cancela cambiando el estado, no con este boton.
export function canCancel(user, ticket) {
  return (
    Boolean(user) &&
    Boolean(ticket) &&
    ticket.requester_id === user.id &&
    allowedTransitions(ticket.status).includes("cancelled")
  );
}
