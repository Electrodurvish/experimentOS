from django.db import models

from apps.common.models import BaseModel


class Organization(BaseModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    class Meta:
        db_table = "organizations"

    def __str__(self):
        return self.name


class Project(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)

    class Meta:
        db_table = "projects"
        unique_together = [("organization", "slug")]

    def __str__(self):
        return f"{self.organization.slug}/{self.name}"
