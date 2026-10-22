"""22/10/2026 - Implementacion SQLAlchemy de los repositorios (semanas 11 y 13).

Traduce entre las tablas (ORM) y los dataclasses de dominio de
app.models.entities, de forma que TicketService y UserService puedan usar
esta implementacion sin cambiar una sola linea de sus reglas de negocio:
solo cambia que repositorio se inyecta.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import FetchedValue, ForeignKey, String, Text, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    selectinload,
)

from app.domain.clock import now
from app.domain.errors import ConflictError
from app.models.comments import Comment
from app.models.entities import HistoryEvent, Ticket, User
from app.models.enums import Role, TicketStatus
from app.repositories.base import TicketPage, TicketQuery, TicketRepository, UserRepository
from app.services.notifications import Notification, NotificationRepository


class Base(DeclarativeBase):
    pass


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
    # No hay autenticacion todavia (llega en la semana 14); se guarda un
    # valor de relleno para satisfacer la columna NOT NULL del esquema.
    password_hash: Mapped[str] = mapped_column(String(255), default="x")


class TicketORM(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    priority: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default=TicketStatus.OPEN.value)
    # Dos FK hacia la misma tabla: sin relationship() explicita no hay
    # AmbiguousForeignKeysError porque aqui no navegamos objetos User desde
    # Ticket (el dominio solo guarda el id, igual que en memoria).
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    # Solo lectura desde Python: la llena el trigger de la base (SLA segun la
    # prioridad). FetchedValue le avisa a SQLAlchemy que el valor lo pone la base.
    due_at: Mapped[datetime | None] = mapped_column(server_default=FetchedValue())

    comments: Mapped[list["CommentORM"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="CommentORM.id",
    )
    history: Mapped[list["HistoryEventORM"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="HistoryEventORM.id",
    )


class CommentORM(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]

    ticket: Mapped["TicketORM"] = relationship(back_populates="comments")


class HistoryEventORM(Base):
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime]

    ticket: Mapped["TicketORM"] = relationship(back_populates="history")


class NotificationORM(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(30), default="in_app")
    type: Mapped[str] = mapped_column(String(50))
    read_at: Mapped[datetime | None]
    created_at: Mapped[datetime]


# --- traduccion entre filas ORM y dataclasses de dominio --------------------

def _user_to_domain(row: UserORM) -> User:
    return User(id=row.id, name=row.name, email=row.email, role=Role(row.role))


def _ticket_to_domain(row: TicketORM) -> Ticket:
    ticket = Ticket(
        id=row.id,
        title=row.title,
        description=row.description,
        category=row.category,
        priority=row.priority,
        requester_id=row.requester_id,
        status=TicketStatus(row.status),
        assignee_id=row.assignee_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        due_at=row.due_at,
    )
    ticket.comments = [
        Comment(
            id=comment.id,
            ticket_id=comment.ticket_id,
            author_id=comment.author_id,
            body=comment.body,
            created_at=comment.created_at,
        )
        for comment in row.comments
    ]
    ticket.history = [
        HistoryEvent(
            id=event.id,
            ticket_id=event.ticket_id,
            actor_id=event.actor_id,
            event_type=event.event_type,
            detail=event.detail,
            created_at=event.created_at,
        )
        for event in row.history
    ]
    return ticket


def _insert(session: Session, row: Base, field: str | None = None) -> None:
    """22/10/2026 - Inserta una fila; si la base la rechaza, lanza un error de DOMINIO.

    El INSERT corre dentro de un SAVEPOINT (begin_nested): si falla, solo se
    deshace ese INSERT y la sesion sigue usable. El rollback completo lo decide
    quien maneja la unidad de trabajo (session_scope), nunca el repositorio.
    """
    try:
        with session.begin_nested():
            session.add(row)
    except IntegrityError as error:
        constraint = getattr(error.orig.diag, "constraint_name", None)
        raise ConflictError(
            "the data conflicts with an existing record",
            field=field,
            constraint=constraint,
        ) from error


class SqlAlchemyUserRepository(UserRepository):
    """22/10/2026 - Mismo contrato que InMemoryUserRepository, respaldado por una tabla real."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User) -> User:
        row = UserORM(email=user.email, name=user.name, role=user.role.value)
        _insert(self._session, row, field="email")
        # El INSERT ya se ejecuto: PostgreSQL asigno la llave.
        user.id = row.id
        return user

    def by_id(self, user_id: int) -> User | None:
        row = self._session.get(UserORM, user_id)
        return _user_to_domain(row) if row else None

    def by_email(self, email: str) -> User | None:
        row = self._session.scalar(
            select(UserORM).where(UserORM.email == email.strip().lower())
        )
        return _user_to_domain(row) if row else None

    def all(self) -> list[User]:
        rows = self._session.scalars(select(UserORM).order_by(UserORM.id)).all()
        return [_user_to_domain(row) for row in rows]

    # 22/10/2026 - El hash vive solo en la capa de persistencia: el dominio y los esquemas
    # (User, UserOut) no lo conocen, asi que no puede salir por la API por descuido.
    def password_hash_for(self, email: str) -> str | None:
        return self._session.scalar(
            select(UserORM.password_hash).where(UserORM.email == email.strip().lower())
        )

    def set_password_hash(self, user_id: int, password_hash: str) -> None:
        row = self._session.get(UserORM, user_id)
        if row is None:
            raise ValueError(f"User {user_id} no existe")
        row.password_hash = password_hash
        self._session.flush()


class SqlAlchemyTicketRepository(TicketRepository):
    """22/10/2026 - Mismo contrato que InMemoryTicketRepository, respaldado por una tabla real.

    `by_id`/`list` devuelven una copia de dominio (no la fila ORM), asi que
    toda mutacion hecha por TicketService debe pasar explicitamente por
    `update()` para persistirse: a diferencia del repositorio en memoria, aqui
    no hay una referencia compartida que "arregle" esto por accidente.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, ticket: Ticket) -> Ticket:
        row = TicketORM(
            title=ticket.title,
            description=ticket.description,
            category=ticket.category,
            priority=ticket.priority,
            status=ticket.status.value,
            requester_id=ticket.requester_id,
            assignee_id=ticket.assignee_id,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )
        _insert(self._session, row)
        # Releemos due_at: lo escribio el trigger, Python no lo conoce todavia.
        self._session.refresh(row, ["due_at"])
        ticket.id = row.id
        ticket.due_at = row.due_at
        return ticket

    def update(self, ticket: Ticket) -> Ticket:
        row = self._session.get(TicketORM, ticket.id)
        if row is None:
            raise ValueError(f"Ticket {ticket.id} no existe; use add() para crearlo")

        row.title = ticket.title
        row.description = ticket.description
        row.category = ticket.category
        row.priority = ticket.priority
        row.status = ticket.status.value
        row.assignee_id = ticket.assignee_id
        row.updated_at = ticket.updated_at

        # Solo los objetos nuevos (id None) se insertan; sin id propio, la base
        # nunca choca con filas existentes ni se descarta nada en silencio.
        new_comments = [
            (
                comment,
                CommentORM(
                    author_id=comment.author_id,
                    body=comment.body,
                    created_at=comment.created_at,
                ),
            )
            for comment in ticket.comments
            if comment.id is None
        ]
        new_events = [
            (
                event,
                HistoryEventORM(
                    actor_id=event.actor_id,
                    event_type=event.event_type,
                    detail=event.detail,
                    created_at=event.created_at,
                ),
            )
            for event in ticket.history
            if event.id is None
        ]
        row.comments.extend(comment_row for _, comment_row in new_comments)
        row.history.extend(event_row for _, event_row in new_events)

        self._session.flush()
        # Devolvemos al dominio las llaves que genero PostgreSQL.
        for comment, comment_row in new_comments:
            comment.id = comment_row.id
        for event, event_row in new_events:
            event.id = event_row.id
        # Si cambio la prioridad, el trigger recalculo due_at: lo releemos.
        self._session.refresh(row, ["due_at"])
        ticket.due_at = row.due_at
        return ticket

    def by_id(self, ticket_id: int) -> Ticket | None:
        row = self._session.get(TicketORM, ticket_id)
        return _ticket_to_domain(row) if row else None

    def list(
        self,
        *,
        status: TicketStatus | str | None = None,
        category: str | None = None,
        priority: str | None = None,
        assignee_id: int | None = None,
        requester_id: int | None = None,
    ) -> list[Ticket]:
        # 22/10/2026 - Cada filtro agrega un WHERE: filtra la base, no Python.
        query = select(TicketORM).order_by(TicketORM.id)
        if status is not None:
            query = query.where(TicketORM.status == TicketStatus(status).value)
        if category is not None:
            query = query.where(TicketORM.category == category)
        if priority is not None:
            query = query.where(TicketORM.priority == priority)
        if assignee_id is not None:
            query = query.where(TicketORM.assignee_id == assignee_id)
        if requester_id is not None:
            query = query.where(TicketORM.requester_id == requester_id)
        rows = self._session.scalars(query).all()
        return [_ticket_to_domain(row) for row in rows]

    def by_category(self, category: str) -> list[Ticket]:
        return self.list(category=category)

    def search(self, query: TicketQuery) -> TicketPage:
        """22/10/2026 - Todo lo hace PostgreSQL: WHERE filtra, ORDER BY ordena,
        LIMIT/OFFSET recortan y COUNT(*) cuenta el total SIN la pagina. A Python
        solo llega lo que se va a devolver."""
        conditions = []
        if query.status is not None:
            conditions.append(TicketORM.status == TicketStatus(query.status).value)
        if query.category is not None:
            conditions.append(TicketORM.category == query.category)
        if query.priority is not None:
            conditions.append(TicketORM.priority == query.priority)
        if query.assignee_id is not None:
            conditions.append(TicketORM.assignee_id == query.assignee_id)
        if query.requester_id is not None:
            conditions.append(TicketORM.requester_id == query.requester_id)

        total = self._session.scalar(
            select(func.count()).select_from(TicketORM).where(*conditions)
        )
        rows = self._session.scalars(
            select(TicketORM)
            .where(*conditions)
            # El id desempata fechas iguales: sin el, el orden no seria estable.
            .order_by(TicketORM.created_at.desc(), TicketORM.id.desc())
            .limit(query.limit)
            .offset(query.offset)
            # Un SELECT extra por tabla en vez de uno por ticket (N+1).
            .options(selectinload(TicketORM.comments), selectinload(TicketORM.history))
        ).all()
        return TicketPage(items=[_ticket_to_domain(row) for row in rows], total=total)

    def count_by_status(self) -> dict[str, int]:
        """22/10/2026 - Un solo GROUP BY en la base: SELECT status, COUNT(*) ... GROUP BY status."""
        rows = self._session.execute(
            select(TicketORM.status, func.count()).group_by(TicketORM.status)
        ).all()
        return {status: total for status, total in rows}

    # 22/10/2026 - La transaccion vive en la Session: el repositorio solo la
    # confirma o la deshace cuando alguien lo pide a mano (scripts y ejercicios).
    # En la API la decision es de session_scope(), no del repositorio.
    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


class SqlAlchemyNotificationRepository(NotificationRepository):
    """22/10/2026 - Avisos guardados en la tabla `notifications`, en la sesion que se le entregue."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, notification: Notification) -> Notification:
        row = NotificationORM(
            user_id=notification.user_id,
            ticket_id=notification.ticket_id,
            title=notification.title,
            message=notification.message,
            type=notification.type,
            created_at=notification.created_at or now(),
        )
        self._session.add(row)
        self._session.flush()
        return _notification_to_domain(row)

    def unread_for(self, user_id: int) -> list[Notification]:
        query = (
            select(NotificationORM)
            .where(NotificationORM.user_id == user_id, NotificationORM.read_at.is_(None))
            .order_by(NotificationORM.created_at.desc(), NotificationORM.id.desc())
        )
        return [_notification_to_domain(row) for row in self._session.scalars(query)]

    def mark_all_read(self, user_id: int) -> int:
        # UPDATE simple en vez de CALL sp_mark_notifications_read: es lo mas facil
        # de leer y de probar, y devuelve igual cuantas filas cambio.
        result = self._session.execute(
            update(NotificationORM)
            .where(NotificationORM.user_id == user_id, NotificationORM.read_at.is_(None))
            .values(read_at=now())
        )
        return result.rowcount


def _notification_to_domain(row: NotificationORM) -> Notification:
    return Notification(
        id=row.id,
        user_id=row.user_id,
        ticket_id=row.ticket_id,
        title=row.title,
        message=row.message,
        type=row.type,
        read_at=row.read_at,
        created_at=row.created_at,
    )
