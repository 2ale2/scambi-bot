import asyncpg
import os
import json

from modules.utils import db_logger, bot_logger


async def connect_to_database():
    try:
        conn = await asyncpg.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME")
        )
    except asyncpg.exceptions.PostgresError as err:
        db_logger.error(err)
        raise
    else:
        return conn


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
        Aggiunge entry al database.
        :param table_name: il nome della tabella
        :param content: dizionario del tipo {'colonna 1': 'valore 1'}
        :return:
        """
    conn = await connect_to_database()
    try:
        columns_order = await get_columns_order(conn, table_name)
        ordered_content = {col: content[col] for col in columns_order if col in content}
        if not ordered_content:
            raise asyncpg.exceptions.DataError('colonne non valide')

        columns = ordered_content.keys()
        values = ordered_content.values()
        query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join([f'${i + 1}' for i in range(len(values))])})"

        await conn.execute(query, *values)
    except Exception as e:
        db_logger.error(f"Errore durante l'inserimento in {table_name}: {e}")
        bot_logger.error("Errore nel database. Vedi i log del database.")
        raise
    finally:
        await conn.close()
