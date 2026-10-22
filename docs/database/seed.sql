-- DATOS SEMILLA PARA PRACTICAR CONSULTAS (semana 10-11)
-- Requiere database.sql y functions_triggers.sql cargados.
--
-- Reglas de este archivo:
-- 1. No se insertan ids: SERIAL los asigna (1, 2, 3...) en el orden de los
--    INSERT y la secuencia queda sincronizada. Con ids explicitos, el
--    siguiente INSERT sin id falla con "duplicate key value violates unique
--    constraint users_pkey".
-- 2. No se inserta due_at: lo calcula el trigger de SLA segun la prioridad.
-- 3. Las fechas son relativas a CURRENT_TIMESTAMP para que el dashboard muestre
--    tickets vencidos y al dia sin importar la fecha de la clase.
-- 4. status, event_type y detail usan el mismo vocabulario que TicketService.

-- users: ids 1..6
INSERT INTO users (email, name, role, password_hash) VALUES
('admin@example.com',      'Admin',        'administrator', 'x'),
('supervisor@example.com', 'Supervisor',   'supervisor',    'x'),
('technician@example.com', 'Technician',   'technician',    'x'),
('requester@example.com',  'Requester',    'requester',     'x'),
('ana@umg.edu',            'Ana Lopez',    'requester',     'x'),
('carlos@umg.edu',         'Carlos Perez', 'technician',    'x');

-- tickets: ids 1..6
INSERT INTO tickets (title, description, category, priority, status, requester_id, assignee_id, created_at, updated_at) VALUES
('Proyector danado',           'Sala A101 sin imagen',          'Hardware', 'High',     'open',        4, NULL, CURRENT_TIMESTAMP - INTERVAL '30 hours', CURRENT_TIMESTAMP - INTERVAL '30 hours'),
('Sin acceso al campus',       'Error de credenciales',         'Security', 'Critical', 'in_progress', 4, 3,    CURRENT_TIMESTAMP - INTERVAL '2 hours',  CURRENT_TIMESTAMP - INTERVAL '80 minutes'),
('Impresora de biblioteca',    'No imprime',                    'Hardware', 'Low',      'closed',      4, 3,    CURRENT_TIMESTAMP - INTERVAL '10 days',  CURRENT_TIMESTAMP - INTERVAL '9 days'),
('Wifi lab 2',                 'Sin senal en el laboratorio 2', 'Network',  'Medium',   'open',        5, NULL, CURRENT_TIMESTAMP - INTERVAL '1 day',    CURRENT_TIMESTAMP - INTERVAL '1 day'),
('Correo institucional',       'No llegan mensajes',            'Software', 'Medium',   'resolved',    5, 6,    CURRENT_TIMESTAMP - INTERVAL '5 days',   CURRENT_TIMESTAMP - INTERVAL '3 days'),
('Licencia de Office vencida', 'Word abre en modo solo lectura', 'Software', 'High',     'in_progress', 5, 6,    CURRENT_TIMESTAMP - INTERVAL '3 days',   CURRENT_TIMESTAMP - INTERVAL '2 days');

INSERT INTO comments (ticket_id, author_id, body, created_at) VALUES
(2, 4, 'Sigue sin funcionar desde ayer',               CURRENT_TIMESTAMP - INTERVAL '90 minutes'),
(2, 3, 'Estoy revisando el servidor de autenticacion', CURRENT_TIMESTAMP - INTERVAL '60 minutes'),
(5, 6, 'Reconfigurado el cliente de correo',           CURRENT_TIMESTAMP - INTERVAL '4 days'),
(6, 5, 'Necesito Word para entregar el informe',       CURRENT_TIMESTAMP - INTERVAL '2 days');

-- history: TicketService no registra un evento al crear el ticket,
-- por eso los tickets 1 y 4 todavia no tienen historial.
INSERT INTO history (ticket_id, actor_id, event_type, detail, created_at) VALUES
(2, 2, 'assigned',       'assigned to Technician',    CURRENT_TIMESTAMP - INTERVAL '110 minutes'),
(2, 4, 'commented',      'comment added',             CURRENT_TIMESTAMP - INTERVAL '90 minutes'),
(2, 3, 'status_changed', 'in_progress',               CURRENT_TIMESTAMP - INTERVAL '80 minutes'),
(2, 3, 'commented',      'comment added',             CURRENT_TIMESTAMP - INTERVAL '60 minutes'),
(3, 2, 'assigned',       'assigned to Technician',    CURRENT_TIMESTAMP - INTERVAL '10 days'),
(3, 3, 'status_changed', 'in_progress',               CURRENT_TIMESTAMP - INTERVAL '10 days' + INTERVAL '1 hour'),
(3, 3, 'status_changed', 'resolved',                  CURRENT_TIMESTAMP - INTERVAL '9 days' - INTERVAL '2 hours'),
(3, 2, 'status_changed', 'closed',                    CURRENT_TIMESTAMP - INTERVAL '9 days'),
(5, 2, 'assigned',       'assigned to Carlos Perez',  CURRENT_TIMESTAMP - INTERVAL '5 days'),
(5, 6, 'status_changed', 'in_progress',               CURRENT_TIMESTAMP - INTERVAL '5 days' + INTERVAL '2 hours'),
(5, 6, 'commented',      'comment added',             CURRENT_TIMESTAMP - INTERVAL '4 days'),
(5, 6, 'status_changed', 'resolved',                  CURRENT_TIMESTAMP - INTERVAL '3 days'),
(6, 2, 'assigned',       'assigned to Carlos Perez',  CURRENT_TIMESTAMP - INTERVAL '3 days'),
(6, 6, 'status_changed', 'in_progress',               CURRENT_TIMESTAMP - INTERVAL '2 days' - INTERVAL '4 hours'),
(6, 5, 'commented',      'comment added',             CURRENT_TIMESTAMP - INTERVAL '2 days');

-- notifications: type usa los mismos codigos que TicketService._notify().
INSERT INTO notifications (user_id, ticket_id, title, message, type, read_at, created_at) VALUES
(3, 2, 'Ticket asignado',    'Ticket #2 was assigned to Technician', 'ticket_assigned',       CURRENT_TIMESTAMP - INTERVAL '100 minutes', CURRENT_TIMESTAMP - INTERVAL '110 minutes'),
(4, 2, 'Nuevo comentario',   'Ticket #2 has a new comment',          'ticket_commented',      NULL,                                        CURRENT_TIMESTAMP - INTERVAL '60 minutes'),
(4, 2, 'Cambio de estado',   'Ticket #2 changed to in_progress',     'ticket_status_changed', NULL,                                        CURRENT_TIMESTAMP - INTERVAL '80 minutes'),
(4, 3, 'Cambio de estado',   'Ticket #3 changed to closed',          'ticket_status_changed', CURRENT_TIMESTAMP - INTERVAL '8 days',       CURRENT_TIMESTAMP - INTERVAL '9 days'),
(5, 5, 'Cambio de estado',   'Ticket #5 changed to resolved',        'ticket_status_changed', NULL,                                        CURRENT_TIMESTAMP - INTERVAL '3 days'),
(6, 6, 'Ticket asignado',    'Ticket #6 was assigned to Carlos Perez', 'ticket_assigned',     CURRENT_TIMESTAMP - INTERVAL '2 days',       CURRENT_TIMESTAMP - INTERVAL '3 days');

-- articles: embedding = [red, acceso, hardware, software]
INSERT INTO articles (title, body, category, author_id, embedding) VALUES
('Proyector sin imagen',               'Revisar cable HDMI, fuente de entrada y lampara.',        'Hardware', 2, '[0, 0, 1, 0.2]'),
('Restablecer contrasena del campus',  'Usar el portal de autoservicio o pedir reinicio a TI.',   'Security', 1, '[0.2, 1, 0, 0.1]'),
('Reiniciar el punto de acceso Wi-Fi', 'Apagar el AP 30 segundos y verificar el SSID del lab.',   'Network',  2, '[1, 0.3, 0.2, 0]'),
('Configurar correo institucional',    'Configurar IMAP/SMTP con la cuenta @umg.edu.',             'Software', 1, '[0.3, 0.2, 0, 1]'),
('Atasco de papel en impresoras',      'Abrir la bandeja trasera y retirar el papel con cuidado.', 'Hardware', 2, '[0, 0, 1, 0]'),
('Activar licencia de Office',         'Iniciar sesion con la cuenta institucional en Word.',     'Software', 1, '[0, 0.4, 0, 1]');
