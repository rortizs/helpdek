/*
 * 22/10/2026 - Richard Ortiz: validacion de formularios en el navegador. Funciones PURAS: reciben los
 * valores y devuelven un objeto { campo: mensaje } (vacio = todo bien).
 *
 * Para que sirve: avisar RAPIDO al usuario sin gastar una peticion. Para que NO sirve: proteger la
 * aplicacion. Cualquiera puede saltarse este archivo con curl o Postman; la autoridad es la API
 * (app/schemas/tickets.py y TicketService). Por eso, aunque aqui todo pase, el formulario igual sabe
 * mostrar los errores 422 que devuelva el servidor.
 */

// 22/10/2026 - Copias de CATEGORIES y PRIORITIES de app/models/enums.py (los valores viajan en ingles).
export const CATEGORIES = ["General", "Hardware", "Software", "Network", "Security", "Other"];
export const PRIORITIES = ["Low", "Medium", "High", "Critical"];

export const TITLE_MIN = 3;
export const TITLE_MAX = 160;

// 22/10/2026 - Reglas del formulario "Nuevo ticket": titulo de 3 a 160 caracteres (sin contar espacios de los
// bordes, como hace TicketService), descripcion con contenido, y categoria y prioridad de las listas validas.
// La API acepta una descripcion vacia; yo la exijo porque un ticket sin descripcion no se puede atender.
export function validateTicketForm({ title, description, category, priority }) {
  const errors = {};
  const cleanTitle = String(title ?? "").trim();
  if (cleanTitle.length < TITLE_MIN) {
    errors.title = `El título necesita al menos ${TITLE_MIN} caracteres.`;
  } else if (String(title).length > TITLE_MAX) {
    errors.title = `El título admite como máximo ${TITLE_MAX} caracteres.`;
  }
  if (String(description ?? "").trim() === "") {
    errors.description = "Describe el problema para que podamos ayudarte.";
  }
  if (!CATEGORIES.includes(category)) {
    errors.category = "Elige una categoría de la lista.";
  }
  if (!PRIORITIES.includes(priority)) {
    errors.priority = "Elige una prioridad de la lista.";
  }
  return errors;
}

// 22/10/2026 - Un comentario no puede estar vacio (la API tambien lo rechaza: "comment body is required").
export function validateComment(body) {
  return String(body ?? "").trim() === "" ? { body: "Escribe un comentario antes de enviarlo." } : {};
}

// 22/10/2026 - Ingreso: la API solo exige que ambos campos tengan texto (el largo maximo lo marca el formulario).
export function validateLogin({ email, password }) {
  const errors = {};
  if (String(email ?? "").trim() === "") {
    errors.email = "Escribe tu correo.";
  }
  if (String(password ?? "") === "") {
    errors.password = "Escribe tu contraseña.";
  }
  return errors;
}
