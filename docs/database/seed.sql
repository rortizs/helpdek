-- DATOS SEMILLA PARA PRACTICAR CONSULTAS 
INSERT INTO users (id, email, name, role, password_hash) VALUES
(1, 'admin@example.com', 'Admin', 'administrator', 'x'),(2,'supervisor@example.com','Supervisor', 'supervisor', 'x'),
(3, 'technician@example.com', 'technician', 'technician', 'x'),
(4,'requester@example.com', 'Requester', 'requester', 'x');

INSERT INTO tickets (id, title, description, category, priority, status, requester_id, assignee_id,created_at, due_at) VALUES
(1, 'Proyector danado', 'Sala A101', 'Hardware', 'High', 'Open', 4, NULL, '2026-09-01 08:00:00', '2026-09-02 08:00:00'),
(2, 'Sin acceso al campus', 'Error de credenciales','Access', 'Critical', 'In Progress', 4, 3, '2026-09-01 09:00:00', '2026-09-01 13:00:00'),
(3, 'Impresora de biblioteca', 'No imprime', 'Hardware', 'Low', 'Closed', 4, 3, '2026-08-25 10:00:00', '2026-08-28 10:00:00');

INSERT INTO comments (ticket_id, author_id, body) VALUES
(2, 4, 'Sigue sin funcionar desde ayer'),
(2, 3, 'Estoy revisando el servidor de autenticacion');

INSERT INTO history (ticket_id, actor_id, event_type, detail) VALUES
(1, 4, 'created', 'Ticket creado'),
(2, 4, 'created', 'Ticket creado'),
(2, 3, 'assigned', 'Asignado a Technician'),
(2, 3, 'status_changed', 'In Progress'),
(3, 4, 'created', 'Ticket creado'),
(3, 3, 'status_changed', 'Closed');