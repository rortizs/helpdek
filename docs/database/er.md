erDiagram
USERS ||--o{ TICKETS : "reporta (requester_id)"
USERS |o--o{ TICKETS : "atiende (assignee_id)"
TICKETS ||--o{ COMMENTS : "tiene"
USERS ||--o{ COMMENTS : "escribe (author_id)"
TICKETS ||--o{ HISTORY : "registra"
USERS ||--o{ HISTORY : "actua (actor_id)"
USERS ||--o{ NOTIFICATIONS : "recibe (user_id)"
TICKETS |o--o{ NOTIFICATIONS : "origina (ticket_id)"
USERS ||--o{ ARTICLES : "redacta (author_id)"
USERS {
int id PK
string email UK
string name
string role
string password_hash
}
TICKETS {
int id PK
string title
text description
string category
string priority
string status
int requester_id FK
int assignee_id FK "nullable"
datetime created_at
datetime updated_at
datetime due_at "SLA: trigger"
}
COMMENTS {
int id PK
int ticket_id FK
int author_id FK
text body
datetime created_at
}
HISTORY {
int id PK
int ticket_id FK
int actor_id FK
string event_type
string detail
datetime created_at
}
NOTIFICATIONS {
int id PK
int user_id FK
int ticket_id FK "nullable"
string title
text message
string channel
string type
datetime read_at "nullable"
datetime created_at
}
ARTICLES {
int id PK
string title
text body
string category
int author_id FK
datetime created_at
vector embedding "pgvector(4)"
}