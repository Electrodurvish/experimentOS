from django.conf import settings
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


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    EXPERIMENT_MANAGER = "EXPERIMENT_MANAGER", "Experiment manager"
    ANALYST = "ANALYST", "Analyst"
    VIEWER = "VIEWER", "Viewer"


# Higher number = more privilege. A role satisfies any requirement at or below its rank.
ROLE_RANK = {
    Role.VIEWER: 1,
    Role.ANALYST: 2,
    Role.EXPERIMENT_MANAGER: 3,
    Role.ADMIN: 4,
}


class Membership(BaseModel):
    """A user's role within an organization. Organizations are the isolation boundary."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)

    class Meta:
        db_table = "memberships"
        unique_together = [("organization", "user")]

    def __str__(self):
        return f"{self.user} @ {self.organization.slug}: {self.role}"

    def has_role(self, required):
        return ROLE_RANK[Role(self.role)] >= ROLE_RANK[Role(required)]
