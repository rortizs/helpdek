/*
 * 22/10/2026 - Richard Ortiz: logica de la pagina de ingreso (index.html).
 * Flujo: validar campos -> POST /api/auth/login -> guardar token -> GET /api/users/me -> ir a la lista.
 * Estados: cargando (boton ocupado), error (alerta con aria-live) y exito (redireccion).
 */

import { api, userMessage } from "../api.js";
import { saveSession, saveUser, isSignedIn, clearSession } from "../session.js";
import { clearAlert, clearFieldErrors, focusTitle, setBusy, showAlert, showFieldErrors } from "../ui.js";
import { validateLogin } from "../validation.js";

const form = document.getElementById("login-form");
const alertRegion = document.getElementById("alert-region");
const submitButton = document.getElementById("login-submit");

// 22/10/2026 - Si ya hay sesion vigente no tiene sentido pedir la contrasena otra vez: voy directo a la lista.
// Si llegue aqui porque el token vencio (?expired=1), lo explico UNA vez con un mensaje fijo mio; nunca
// pinto en pantalla el valor que venga en la direccion, porque lo controla quien arma el enlace.
function showEntryState() {
  if (isSignedIn()) {
    window.location.replace("tickets.html");
    return;
  }
  if (new URLSearchParams(window.location.search).get("expired") === "1") {
    showAlert(alertRegion, "Tu sesión venció o ya no es válida. Ingresa de nuevo.", "warning");
  }
  focusTitle();
}

// 22/10/2026 - Envio del formulario. El 401 del login significa "credenciales incorrectas" (la API usa el
// mismo mensaje para correo inexistente y contrasena mala, a proposito: no revela que correos existen).
async function handleSubmit(event) {
  event.preventDefault();
  clearAlert(alertRegion);
  clearFieldErrors(form);

  const passwordField = form.elements.namedItem("password");
  const values = { email: form.elements.namedItem("email").value.trim(), password: passwordField.value };
  const errors = validateLogin(values);
  if (Object.keys(errors).length > 0) {
    showFieldErrors(form, errors);
    return;
  }

  setBusy(submitButton, true, "Ingresando…");
  try {
    const token = await api.login(values.email, values.password);
    saveSession({ token: token.access_token, expiresIn: token.expires_in });
    saveUser(await api.me());
    window.location.replace("tickets.html");
  } catch (error) {
    clearSession();
    passwordField.value = "";
    showAlert(alertRegion, userMessage(error));
    passwordField.focus();
    setBusy(submitButton, false);
  }
}

form.addEventListener("submit", handleSubmit);
showEntryState();
