"""Peewee models of the Soil Monitoring context (Edge Local Database)."""
from peewee import AutoField, CharField, DateTimeField, FloatField, IntegerField, Model

from shared.infrastructure.database import db


class SoilReadingModel(Model):
    id = AutoField()
    device_code = CharField(max_length=40)
    platform_device_id = IntegerField()
    raw_conductivity_dsm = FloatField()
    compensated_conductivity_dsm = FloatField(null=True)
    compensation_factor = FloatField(null=True)
    moisture_percentage = FloatField()
    temperature_celsius = FloatField(null=True)
    captured_at = DateTimeField()  # naive UTC
    status = CharField(max_length=16, index=True)
    status_reason = CharField(null=True)
    platform_batch_id = IntegerField(null=True)
    server_errors = IntegerField(default=0)

    class Meta:
        database = db
        table_name = "soil_readings"
        # Same idempotency rule as the platform: one reading per device and instant.
        indexes = ((("platform_device_id", "captured_at"), True),)
