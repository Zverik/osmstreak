import config
from playhouse.db_url import connect
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
    score = IntegerField(default=0)
    streak = IntegerField(default=0)
    level = IntegerField(default=1)


class Task(BaseModel):
    user = ForeignKeyField(User, related_name='tasks', index=True)
    day = DateField(index=True)
    task = CharField(max_length=50)
    changeset = IntegerField(null=True)
    correct = BooleanField(null=True)


def create_tables():
    database.create_tables([User, Task], safe=True)
