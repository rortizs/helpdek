-- HelpDesk EDU - funciones, triggers, vistas y procedimientos (semana 11)
-- Requiere database.sql. Se carga ANTES de seed.sql porque el seed depende
-- del trigger de SLA para calcular tickets.due_at.
--
-- Regla de diseno del curso:
--   La base es duena de INVARIANTES y DATOS DERIVADOS (updated_at, due_at,
--   reportes, busqueda vectorial). Las reglas del flujo de trabajo (asignar,
--   cambiar estado, registrar history, notificar) viven en TicketService.
--   Nada de eso se duplica aqui: dos fuentes de verdad terminan en datos
--   inconsistentes (por ejemplo, eventos de history repetidos).

-- 1. SLA por prioridad ------------------------------------------------------
-- IMMUTABLE: mismo parametro, mismo resultado; PostgreSQL puede optimizarla.
CREATE OR REPLACE FUNCTION fn_sla_interval(p_priority VARCHAR)
RETURNS INTERVAL
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE p_priority
    WHEN 'Critical' THEN INTERVAL '4 hours'
    WHEN 'High'     THEN INTERVAL '1 day'
    WHEN 'Medium'   THEN INTERVAL '2 days'
    WHEN 'Low'      THEN INTERVAL '3 days'
  END;
$$;

-- 2. Trigger: calcula due_at al crear el ticket o al cambiar su prioridad ----
CREATE OR REPLACE FUNCTION fn_tickets_set_due_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.due_at IS NULL THEN
      NEW.due_at := NEW.created_at + fn_sla_interval(NEW.priority);
    END IF;
  ELSIF NEW.priority IS DISTINCT FROM OLD.priority THEN
    NEW.due_at := NEW.created_at + fn_sla_interval(NEW.priority);
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tickets_set_due_at
BEFORE INSERT OR UPDATE OF priority ON tickets
FOR EACH ROW
EXECUTE FUNCTION fn_tickets_set_due_at();

-- 3. Trigger: updated_at como red de seguridad -------------------------------
-- La aplicacion ya envia updated_at. El trigger solo actua si alguien modifica
-- la fila sin tocar updated_at (por ejemplo, un UPDATE manual desde psql).
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW IS DISTINCT FROM OLD
     AND NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at THEN
    NEW.updated_at := CURRENT_TIMESTAMP;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tickets_set_updated_at
BEFORE UPDATE ON tickets
FOR EACH ROW
EXECUTE FUNCTION fn_set_updated_at();

-- 4. Vista: dataset enriquecido para Tableau --------------------------------
-- Un ticket vence solo mientras esta activo (open o in_progress).
CREATE OR REPLACE VIEW v_tickets_dashboard AS
SELECT
  t.id,
  t.title,
  t.category,
  t.priority,
  t.status,
  requester.name AS requester,
  COALESCE(technician.name, 'Sin asignar') AS technician,
  t.created_at,
  t.updated_at,
  t.due_at,
  (t.status IN ('open', 'in_progress') AND t.due_at < CURRENT_TIMESTAMP) AS is_overdue
FROM tickets t
JOIN users requester ON requester.id = t.requester_id
LEFT JOIN users technician ON technician.id = t.assignee_id;

-- 5. Funcion con parametro: lo que una vista no puede hacer -------------------
-- SELECT * FROM fn_tickets_by_status();            -- todas las categorias
-- SELECT * FROM fn_tickets_by_status('Hardware');  -- filtrada
CREATE OR REPLACE FUNCTION fn_tickets_by_status(p_category VARCHAR DEFAULT NULL)
RETURNS TABLE (status VARCHAR, total BIGINT)
LANGUAGE sql
STABLE
AS $$
  SELECT t.status, count(*)
  FROM tickets t
  WHERE p_category IS NULL OR t.category = p_category
  GROUP BY t.status
  ORDER BY count(*) DESC, t.status;
$$;

-- 6. pgvector: articulos parecidos a un vector (distancia coseno <=>) --------
-- SELECT * FROM fn_similar_articles('[1,0,0,0]');
CREATE OR REPLACE FUNCTION fn_similar_articles(p_embedding vector, p_limit INTEGER DEFAULT 3)
RETURNS TABLE (id INTEGER, title VARCHAR, category VARCHAR, distance DOUBLE PRECISION)
LANGUAGE sql
STABLE
AS $$
  SELECT a.id, a.title, a.category, a.embedding <=> p_embedding
  FROM articles a
  WHERE a.embedding IS NOT NULL
  ORDER BY a.embedding <=> p_embedding
  LIMIT p_limit;
$$;

-- 7. pgvector: sugerencias para un ticket ------------------------------------
-- Los tickets no tienen embedding propio. Se usa el promedio (centroide) de
-- los articulos de su categoria y se buscan los mas cercanos de cualquier
-- categoria. Una funcion que reutiliza otra funcion.
-- SELECT * FROM fn_suggest_articles_for_ticket(1);
CREATE OR REPLACE FUNCTION fn_suggest_articles_for_ticket(p_ticket_id INTEGER, p_limit INTEGER DEFAULT 3)
RETURNS TABLE (id INTEGER, title VARCHAR, category VARCHAR, distance DOUBLE PRECISION)
LANGUAGE sql
STABLE
AS $$
  SELECT s.*
  FROM tickets t
  CROSS JOIN LATERAL (
    SELECT avg(a.embedding) AS centroid
    FROM articles a
    WHERE a.category = t.category AND a.embedding IS NOT NULL
  ) c
  CROSS JOIN LATERAL fn_similar_articles(c.centroid, p_limit) s
  WHERE t.id = p_ticket_id AND c.centroid IS NOT NULL;
$$;

-- 8. Procedimiento: operacion por lotes con CALL ------------------------------
-- Diferencia con una funcion: se invoca con CALL, no devuelve un conjunto de
-- filas y puede controlar transacciones (COMMIT/ROLLBACK) en su cuerpo.
-- CALL sp_mark_notifications_read(5, NULL);
CREATE OR REPLACE PROCEDURE sp_mark_notifications_read(
  IN p_user_id INTEGER,
  INOUT p_updated INTEGER DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM users WHERE id = p_user_id) THEN
    RAISE EXCEPTION 'user % does not exist', p_user_id
      USING ERRCODE = 'foreign_key_violation';
  END IF;

  UPDATE notifications
  SET read_at = CURRENT_TIMESTAMP
  WHERE user_id = p_user_id AND read_at IS NULL;

  GET DIAGNOSTICS p_updated = ROW_COUNT;
END;
$$;
