# ------------------------------------------------------------------------------
# Copyright (c) 2010-2013, EVEthing team
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#     Redistributions of source code must retain the above copyright notice, this
#       list of conditions and the following disclaimer.
#     Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY
# OF SUCH DAMAGE.
# ------------------------------------------------------------------------------

from xml.sax.saxutils import unescape

from django.db import models

from thing.models.character import Character
from thing.models.corporation import Corporation
from thing.models.corpwallet import CorpWallet
from thing.models.reftype import RefType


class JournalEntry(models.Model):
    """Wallet journal entries"""
    character = models.ForeignKey(Character)
    corp_wallet = models.ForeignKey(CorpWallet, null=True, blank=True)

    date = models.DateTimeField(db_index=True)

    ref_id = models.BigIntegerField(db_index=True)
    #ref_type = models.ForeignKey(RefType)
    ref_type = models.CharField(max_length=64, db_index=True)

    owner1_id = models.IntegerField(default=0)
    owner2_id = models.IntegerField(default=0)

    arg_name = models.CharField(max_length=128, default="")
    arg_id = models.BigIntegerField(default=0)

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance = models.DecimalField(max_digits=17, decimal_places=2)
    reason = models.CharField(max_length=255, default="")

    tax_corp = models.ForeignKey(Corporation, null=True, blank=True)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        app_label = 'thing'
        ordering = ('-date',)

    def ref_type_display(self):
        return self.ref_type.replace("_", " ").title()

    def get_unescaped_reason(self):
        if len(self.reason) > 0:
            return unescape(self.reason)
        else:
            return self.reason

# ------------------------------------------------------------------------------
