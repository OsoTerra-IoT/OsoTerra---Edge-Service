"""SQLite database shared by every bounded context of the Edge Service (Edge Local Database)."""
from peewee import DatabaseProxy, SqliteDatabase

db = DatabaseProxy()


def init_db(path: str) -> SqliteDatabase:
    """Binds the proxy to the SQLite file at ``path`` and creates the tables."""
    from iam.infrastructure.models import DeviceModel
    from monitoring.infrastructure.models import SoilReadingModel

    database = SqliteDatabase(path, pragmas={"journal_mode": "wal", "foreign_keys": 1})
    db.initialize(database)
    db.connect(reuse_if_open=True)
    db.create_tables([DeviceModel, SoilReadingModel], safe=True)
    return database
