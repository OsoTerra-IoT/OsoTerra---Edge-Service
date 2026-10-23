"""Peewee models of the IAM context."""
from peewee import CharField, FloatField, IntegerField, Model

from shared.infrastructure.database import db


class DeviceModel(Model):
    activation_code = CharField(primary_key=True, max_length=40)
    platform_device_id = IntegerField()
    api_key = CharField()
    calibration_factor = FloatField(default=1.0)

    class Meta:
        database = db
        table_name = "devices"
