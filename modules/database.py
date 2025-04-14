import asyncpg
import json

from modules.utils import connect_to_database
from loggers import db_logger, bot_logger


async def is_table_empty():
    conn = await connect_to_database()
    try:
        count = await conn.fetchval("SELECT count(*) FROM persistence;")
    except asyncpg.exceptions.PostgresError as err:
        db_logger.error(err)
        raise
    else:
        if count == 1:
            res = await conn.fetch("SELECT data FROM persistence;")
            if len(json.loads(next(res[0].values()))["jsondata"]) == 0:
                # noinspection SqlWithoutWhere
                await conn.execute("DELETE FROM persistence;")
                return True
        await conn.close()
        return count == 0


async def get_columns_order(conn, table_name: str):
    """
    Recupera l'ordine delle colonne dal database.
    :param conn: connessione al database
    :param table_name: nome della tabella
    :return: lista dei nomi delle colonne ordinate
    """
    query = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = $1
    ORDER BY ordinal_position;
    """
    try:
        result = await conn.fetch(query, table_name)
        return [row['column_name'] for row in result]
    except Exception as e:
        db_logger.error(e)
        raise


async def add_to_table(table_name: str, content: dict):
    """
    Aggiunge entry al database. Se l'utente esiste, aggiorna punti e username.
    Se i punti arrivano a 6, vengono azzerati e viene notificato il reset.

    :param table_name: il nome della tabella
    :param content: dizionario del tipo {'colonna1': valore1, ...}
    :return: {'reset': True} se punti sono stati azzerati, altrimenti {'reset': False}
    """
    conn = await connect_to_database()
    try:
        columns_order = await get_columns_order(conn, table_name)
        ordered_content = {col: content[col] for col in columns_order if col in content}
        if not ordered_content:
            raise asyncpg.exceptions.DataError('Colonne non valide')

        columns = list(ordered_content.keys())
        values = list(ordered_content.values())

        query = (
            f"INSERT INTO {table_name} ({', '.join(columns)}) "
            f"VALUES ({', '.join([f'${i + 1}' for i in range(len(values))])}) "
        )

        if table_name == "main_table":
            query += (
                f"ON CONFLICT (user_id) DO UPDATE SET "
                f"points = CASE WHEN {table_name}.points + 1 >= 6 THEN 0 ELSE {table_name}.points + 1 END, "
                f"username = EXCLUDED.username "
                f"RETURNING points"
            )
        else:
            query += "RETURNING id"

        result = await conn.fetchval(query, *values)
        return result

    except Exception as e:
        db_logger.error(f"Errore durante l'inserimento in {table_name}: {e}")
        bot_logger.error("Errore nel database. Vedi i log del database.")
        raise
    finally:
        await conn.close()


async def decrease_user_points(user_id: int | str, points=1):
    conn = await connect_to_database()
    try:
        points = await conn.execute(
            query=f"UPDATE main_table SET "
                  f"points IF(main_table.points = 0, 5, main_table.points - 1),"
                  f"WHERE user_id={user_id} RETURNING points",
        )
        return points
    except asyncpg.exceptions.PostgresError as err:
        db_logger.error(err)
        raise
    finally:
        await conn.close()


async def get_exchange_infos(identifier: int | str):
    conn = await connect_to_database()
    try:
        raw = await conn.fetchrow(
            query=f"SELECT * FROM exchanges WHERE id={str(identifier)};",
        )
    except asyncpg.exceptions.PostgresError as err:
        db_logger.error(err)
        raise
    else:
        if raw is None:
            db_logger.error(f"{identifier} non esistente in 'exchanges'")
            raise asyncpg.exceptions.PostgresError(f"{identifier} non esistente in 'exchanges'")
        else:
            return {key: raw[key] for key in dict(raw)}
    finally:
        await conn.close()
