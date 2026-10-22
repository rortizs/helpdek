-- HelpDesk EDU - consultas del laboratorio SQL (semana 10-11)
-- Mismos identificadores que el manual (U1, T1, ... Hoja 5).
-- Contrato: status en minusculas ('open', 'in_progress', ...), igual que app/models/enums.py.
--
-- Ejecutar todo:  psql -h 127.0.0.1 -p 5433 -U helpdesk -d helpdesk -f docs/database/queries.sql
-- Las escrituras de practica van entre BEGIN y ROLLBACK: no modifican la base.

-- 0. Verificacion inicial ---------------------------------------------------
SELECT current_database(), current_user;

SELECT 'articles' AS tabla, count(*) FROM articles
UNION ALL SELECT 'comments', count(*) FROM comments
UNION ALL SELECT 'history', count(*) FROM history
UNION ALL SELECT 'notifications', count(*) FROM notifications
UNION ALL SELECT 'tickets', count(*) FROM tickets
UNION ALL SELECT 'users', count(*) FROM users
ORDER BY tabla;

-- 1. Usuarios ---------------------------------------------------------------
-- U1 - Usuarios y roles
SELECT id, email, name, role
FROM users
ORDER BY role, name;

-- U2 - Solo personal de soporte
SELECT id, email, name, role
FROM users
WHERE role IN ('administrator', 'supervisor', 'technician')
ORDER BY role;

-- U3 - Usuarios institucionales
SELECT id, email, name
FROM users
WHERE email ILIKE '%@umg.edu';

-- U4 - Insertar usuario de practica y obtener su id (SERIAL lo asigna)
BEGIN;
INSERT INTO users (email, name, role, password_hash)
VALUES ('practica@umg.edu', 'Usuario Practica', 'requester', 'x')
RETURNING id, email, role;
ROLLBACK;

-- U5 - Error esperado: email duplicado (users_email_key)
BEGIN;
INSERT INTO users (email, name, role, password_hash)
VALUES ('admin@example.com', 'Duplicado', 'requester', 'x');
ROLLBACK;

-- 2. Tickets ----------------------------------------------------------------
-- T1 - Tickets con solicitante y tecnico asignado
SELECT
  t.id,
  t.title,
  t.status,
  t.priority,
  requester.name AS requester,
  technician.name AS technician
FROM tickets t
JOIN users requester ON requester.id = t.requester_id
LEFT JOIN users technician ON technician.id = t.assignee_id
ORDER BY t.id;

-- T2 - Tickets activos por prioridad de negocio y vencimiento (SLA)
SELECT id, title, priority, status, due_at
FROM tickets
WHERE status IN ('open', 'in_progress')
ORDER BY
  CASE priority
    WHEN 'Critical' THEN 1
    WHEN 'High' THEN 2
    WHEN 'Medium' THEN 3
    WHEN 'Low' THEN 4
  END,
  due_at;

-- T3 - Dashboard por estado
SELECT status, count(*) AS total
FROM tickets
GROUP BY status
ORDER BY total DESC, status;

-- T4 - Dashboard por prioridad y estado
SELECT priority, status, count(*) AS total
FROM tickets
GROUP BY priority, status
ORDER BY priority, status;

-- T5 - Carga de trabajo por tecnico
SELECT
  u.name AS technician,
  count(t.id) FILTER (WHERE t.status IN ('open', 'in_progress')) AS tickets_activos,
  count(t.id) AS tickets_totales
FROM users u
LEFT JOIN tickets t ON t.assignee_id = u.id
WHERE u.role = 'technician'
GROUP BY u.id, u.name
ORDER BY tickets_activos DESC, technician;

-- 3. Comentarios ------------------------------------------------------------
-- C1 - Comentarios por ticket
SELECT
  c.ticket_id,
  t.title,
  u.name AS author,
  c.body,
  c.created_at
FROM comments c
JOIN tickets t ON t.id = c.ticket_id
JOIN users u ON u.id = c.author_id
ORDER BY c.ticket_id, c.created_at;

-- C2 - Cantidad de comentarios por ticket
SELECT
  t.id,
  t.title,
  count(c.id) AS comments_count
FROM tickets t
LEFT JOIN comments c ON c.ticket_id = t.id
GROUP BY t.id, t.title
ORDER BY comments_count DESC, t.id;

-- 4. Historial --------------------------------------------------------------
-- H1 - Auditoria completa de tickets
SELECT
  h.ticket_id,
  t.title,
  u.name AS actor,
  h.event_type,
  h.detail,
  h.created_at
FROM history h
JOIN tickets t ON t.id = h.ticket_id
JOIN users u ON u.id = h.actor_id
ORDER BY h.ticket_id, h.created_at;

-- H2 - Ultimo evento de cada ticket (los tickets sin eventos no aparecen)
SELECT DISTINCT ON (h.ticket_id)
  h.ticket_id,
  t.title,
  h.event_type,
  h.detail,
  h.created_at
FROM history h
JOIN tickets t ON t.id = h.ticket_id
ORDER BY h.ticket_id, h.created_at DESC;

-- 5. Notificaciones ---------------------------------------------------------
-- N1 - Bandeja de notificaciones (no leidas primero)
SELECT
  n.id,
  u.name AS user_name,
  n.title,
  n.type,
  n.read_at,
  n.created_at
FROM notifications n
JOIN users u ON u.id = n.user_id
ORDER BY n.read_at NULLS FIRST, n.created_at DESC;

-- N2 - Contador de no leidas por usuario
SELECT
  u.name,
  count(n.id) AS unread_count
FROM users u
LEFT JOIN notifications n
  ON n.user_id = u.id AND n.read_at IS NULL
GROUP BY u.id, u.name
ORDER BY unread_count DESC, u.name;

-- 6. Base de conocimiento y pgvector ---------------------------------------
-- A1 - Busqueda clasica por texto
SELECT id, title, category
FROM articles
WHERE title ILIKE '%Wi-Fi%' OR body ILIKE '%Wi-Fi%';

-- A2 - Articulos parecidos con distancia coseno (vector = [red, acceso, hardware, software])
SELECT
  title,
  category,
  embedding <=> '[1,0,0,0]'::vector AS distance_to_network
FROM articles
ORDER BY embedding <=> '[1,0,0,0]'::vector
LIMIT 3;

-- A3 - Sugerir articulos segun la categoria del ticket
SELECT
  t.id AS ticket_id,
  t.title AS ticket,
  a.title AS suggested_article,
  a.category
FROM tickets t
JOIN articles a ON a.category = t.category
ORDER BY t.id, a.title;

-- 7. Funciones, triggers y procedimientos (functions_triggers.sql) ---------
-- F1 - Trigger de SLA: due_at = created_at + fn_sla_interval(priority)
SELECT id, priority, created_at, due_at, due_at - created_at AS sla
FROM tickets
ORDER BY id;

-- F2 - Cambiar la prioridad recalcula due_at (y updated_at lo pone el otro trigger)
BEGIN;
SELECT id, priority, due_at, updated_at FROM tickets WHERE id = 4;
UPDATE tickets SET priority = 'Critical' WHERE id = 4;
SELECT id, priority, due_at, updated_at FROM tickets WHERE id = 4;
ROLLBACK;

-- F3 - El CHECK rechaza un estado fuera del contrato (error esperado)
BEGIN;
UPDATE tickets SET status = 'Open' WHERE id = 1;
ROLLBACK;

-- F4 - Funcion con parametro (una vista no acepta parametros)
SELECT * FROM fn_tickets_by_status();
SELECT * FROM fn_tickets_by_status('Hardware');

-- F5 - Busqueda vectorial encapsulada en una funcion
SELECT * FROM fn_similar_articles('[1,0,0,0]');

-- F6 - Sugerencias para un ticket (centroide de su categoria)
SELECT * FROM fn_suggest_articles_for_ticket(6);

-- F7 - Procedimiento con CALL: marcar como leidas las notificaciones de un usuario
BEGIN;
CALL sp_mark_notifications_read(4, NULL);
SELECT count(*) AS unread_after FROM notifications WHERE user_id = 4 AND read_at IS NULL;
ROLLBACK;

-- 8. Consultas para Tableau -------------------------------------------------
-- Hoja 1 - Tickets por estado
SELECT status, count(*) AS total
FROM tickets
GROUP BY status;

-- Hoja 2 - Tickets por prioridad
SELECT priority, count(*) AS total
FROM tickets
GROUP BY priority;

-- Hoja 3 - Tickets por categoria
SELECT category, count(*) AS total
FROM tickets
GROUP BY category;

-- Hoja 4 - Tickets activos por tecnico
SELECT technician, count(*) AS active_tickets
FROM v_tickets_dashboard
WHERE status IN ('open', 'in_progress')
GROUP BY technician
ORDER BY active_tickets DESC;

-- Hoja 5 - Dataset enriquecido: conectar Tableau directo a la vista
SELECT * FROM v_tickets_dashboard ORDER BY id;
