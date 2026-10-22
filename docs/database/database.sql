-- HelpDesk EDU - esquema relacional (semana 10-11)
-- Dialecto: PostgreSQL 16 + pgvector (imagen pgvector/pgvector:pg16 en docker-compose.yml).
-- Las llaves foraneas se validan siempre en PostgreSQL; no existe un PRAGMA equivalente.
-- Contrato: los valores de role y status son los de app/models/enums.py.
-- Orden de carga: 01 database.sql -> 02 functions_triggers.sql -> 03 seed.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
  id SERIAL NOT NULL,
  email VARCHAR(120) NOT NULL,
  name VARCHAR(100) NOT NULL,
  role VARCHAR(20) NOT NULL
    CHECK (role IN ('requester', 'technician', 'supervisor', 'administrator')),
  password_hash VARCHAR(255) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (email)
);

CREATE TABLE tickets (
  id SERIAL NOT NULL,
  title VARCHAR(160) NOT NULL,
  description TEXT NOT NULL,
  category VARCHAR(50) NOT NULL,
  priority VARCHAR(30) NOT NULL
    CHECK (priority IN ('Low', 'Medium', 'High', 'Critical')),
  status VARCHAR(30) NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'in_progress', 'resolved', 'closed', 'cancelled')),
  requester_id INTEGER NOT NULL,
  assignee_id INTEGER,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  -- SLA: lo calcula el trigger trg_tickets_set_due_at segun la prioridad
  -- (functions_triggers.sql). Python no lo conoce: la base es la duena del dato.
  due_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
  PRIMARY KEY (id),
  CHECK (due_at >= created_at),
  FOREIGN KEY(requester_id) REFERENCES users (id),
  FOREIGN KEY(assignee_id) REFERENCES users (id)
);

CREATE TABLE comments (
  id SERIAL NOT NULL,
  ticket_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  body TEXT NOT NULL,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
  FOREIGN KEY(author_id) REFERENCES users (id)
);

CREATE TABLE history (
  id SERIAL NOT NULL,
  ticket_id INTEGER NOT NULL,
  actor_id INTEGER NOT NULL,
  event_type VARCHAR(50) NOT NULL,
  detail VARCHAR(255) NOT NULL,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
  FOREIGN KEY(actor_id) REFERENCES users (id)
);

CREATE TABLE notifications (
  id SERIAL NOT NULL,
  user_id INTEGER NOT NULL,
  ticket_id INTEGER,
  title VARCHAR(160) NOT NULL,
  message TEXT NOT NULL,
  channel VARCHAR(30) NOT NULL DEFAULT 'in_app',
  type VARCHAR(50) NOT NULL,
  read_at TIMESTAMP WITHOUT TIME ZONE,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  FOREIGN KEY(user_id) REFERENCES users (id),
  FOREIGN KEY(ticket_id) REFERENCES tickets (id) ON DELETE SET NULL
);

CREATE TABLE articles (
  id SERIAL NOT NULL,
  title VARCHAR(160) NOT NULL,
  body TEXT NOT NULL,
  category VARCHAR(50) NOT NULL,
  author_id INTEGER NOT NULL,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  -- pgvector: 4 dimensiones educativas [red, acceso, hardware, software].
  -- Un modelo real de embeddings usa cientos de dimensiones (384, 768, 1536...).
  embedding vector(4),
  PRIMARY KEY (id),
  FOREIGN KEY(author_id) REFERENCES users (id)
);

CREATE INDEX idx_tickets_status ON tickets(status);
CREATE INDEX idx_tickets_assignee ON tickets(assignee_id);
CREATE INDEX idx_comments_ticket ON comments(ticket_id);
CREATE INDEX idx_history_ticket ON history(ticket_id);
-- Indice parcial: solo indexa lo que la bandeja consulta (no leidas).
CREATE INDEX idx_notifications_unread ON notifications(user_id) WHERE read_at IS NULL;

