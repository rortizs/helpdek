"""22/10/2026 - Reloj unico del dominio.

Las columnas son TIMESTAMP WITHOUT TIME ZONE: guardan fecha y hora sin zona.
Si el dominio usara fechas con zona (aware), el valor que sale de la base
(naive) no seria igual al que entro. Por eso todo el dominio usa hora local
sin zona, y solo se obtiene de aqui.
"""

from datetime import datetime


def now() -> datetime:
    return datetime.now()
