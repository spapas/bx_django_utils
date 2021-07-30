from django.db import models

from bx_django_utils.data_types.gtin.model_fields import GtinModelField
from bx_django_utils.models.color_field import ColorModelField
from bx_django_utils.models.timetracking import TimetrackingBaseModel


class TimetrackingTestModel(TimetrackingBaseModel):
    pass


class CreateOrUpdateTestModel(TimetrackingBaseModel):
    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=64)


class GtinFieldTestModel(models.Model):
    default_gtin = GtinModelField()  # accept default length: 12,13 and 14
    all_gtin = GtinModelField(
        blank=True,
        accepted_length=(8, 10, 12, 13, 14)
    )
    ean13 = GtinModelField(
        blank=True, null=True,
        accepted_length=(13,)  # accept one length
    )


class ColorFieldTestModel(models.Model):
    required_color = ColorModelField()
    optional_color = ColorModelField(blank=True, null=True)
