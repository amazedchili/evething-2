from datetime import datetime

from django.db import models
from django.contrib.auth.models import User

from thing.models.character import Character
from thing.models.eveaccount import EveAccount

class ESIToken(models.Model):
    access_token = models.CharField(max_length=128)
    refresh_token = models.CharField(max_length=320)

    user = models.ForeignKey(User)
    account = models.ForeignKey(EveAccount, related_name="tokens", null=True, default=None, on_delete=models.SET_NULL)
    status = models.BooleanField(default=True)
    added = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True, default=datetime(0001, 1, 1, 1, 0))

    token_type = models.CharField(max_length=32)
    characterID = models.IntegerField(default=None, null=True)
    corporationID = models.IntegerField(default=None, null=True)
    name = models.CharField(max_length=64)

    character = models.OneToOneField(
        Character,
        on_delete=models.CASCADE,
        null=True,
        related_name="esitoken")

    class Meta:
        app_label = 'thing'
