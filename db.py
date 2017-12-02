import config
from hashlib import sha256
from playhouse.db_url import connect
from playhouse.migrate import (
    migrate as peewee_migrate,
    SqliteMigrator,
    MySQLMigrator,
    PostgresqlMigrator
)
from peewee import (
    Model,
    CharField,
    IntegerField,
    ForeignKeyField,
    BooleanField,
    DateField
)

database = connect(config.DATABASE_URI)


class BaseModel(Model):
    class Meta:
        database = database


class User(BaseModel):
    uid = IntegerField(primary_key=True)
    name = CharField(max_length=250)
    email = CharField(max_length=250, null=True)
    lang = CharField(max_length=7, default='en')
    score = IntegerField(default=0)
    streak = IntegerField(default=0)
    level = IntegerField(default=1)

    def generate_code(self):
        m = sha256()
        m.update(str(self.uid))
        m.update(self.name.encode('utf-8'))
        m.update(config.SECRET_KEY)
        return m.hexdigest()


class Task(BaseModel):
    user = ForeignKeyField(User, related_name='tasks', index=True)
    day = DateField(index=True)
    task = CharField(max_length=50)
    changeset = IntegerField(null=True)
    correct = BooleanField(null=True)


class Telegram(BaseModel):
    channel = IntegerField(primary_key=True)
    user = ForeignKeyField(User)
    remind_on = CharField(max_length=5, null=True, index=True)


LAST_VERSION = 1


class Version(BaseModel):
    version = IntegerField()


def migrate():
    database.create_tables([Version], safe=True)
    try:
        v = Version.select().get()
    except Version.DoesNotExist:
        database.create_tables([User, Task, Telegram])
        v = Version(version=LAST_VERSION)
        v.save()

    if v.version >= LAST_VERSION:
        return

    if 'mysql' in config.DATABASE_URI:
        migrator = MySQLMigrator(database)
    elif 'sqlite' in config.DATABASE_URI:
        migrator = SqliteMigrator(database)
    else:
        migrator = PostgresqlMigrator(database)

    if v.version == 0:
        database.create_tables([Telegram])
        peewee_migrate(
            migrator.add_column(User._meta.db_table, User.lang.name, User.lang)
        )
        v.version = 1
        v.save()

    if v.version != LAST_VERSION:
        raise ValueError('LAST_VERSION in db.py should be {}'.format(v.version))
