-- HelpDesk EDU - esquema relacional (semana 10)
-- Dialecto: SQLite. En PostgreSQL cambia "INTEGER PRIMARY KEY AUTOINCREMENT" por "SERIAL PRIMARY ↪ KEY"
-- y "TEXT" por VARCHAR/TEXT segun convenga.
PRAGMA foreign_keys = ON;

CREATE TABLE users (
  id SERIAL NOT NULL,
  email VARCHAR(120) NOT NULL,
  name VARCHAR(100) NOT NULL,
  role VARCHAR(20) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (email)
);

CREATE TABLE tickets (
  id SERIAL NOT NULL,
  title VARCHAR(160) NOT NULL,
  description TEXT NOT NULL,
  category VARCHAR(50) NOT NULL,
  priority VARCHAR(30) NOT NULL,
  status VARCHAR(30) NOT NULL,
  requester_id INTEGER NOT NULL,
  assignee_id INTEGER,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
  due_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
  PRIMARY KEY (id),
  OREIGN KEY(requester_id) REFERENCES users (id),
  FOREIGN KEY(assignee_id) REFERENCES users (id)
);

CREATE TABLE comments (
  id SERIAL NOT NULL,
  ticket_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  body TEXT NOT NULL,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
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
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
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
  channel VARCHAR(30) NOT NULL,
  type VARCHAR(50) NOT NULL,
  read_at TIMESTAMP WITHOUT TIME ZONE,
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
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
  created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
  PRIMARY KEY (id),
  FOREIGN KEY(author_id) REFERENCES users (id)
);

CREATE INDEX idx_tickets_status ON tickets(status);
CREATE INDEX idx_tickets_assignee ON tickets(assignee_id);
CREATE INDEX idx_comments_ticket ON comments(ticket_id);
CREATE INDEX idx_history_ticket ON history(ticket_id);

