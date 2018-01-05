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

from django.db import models

from evething import local_settings
from thing.models.system import System
from thing.models.item import Item

numeral_map = zip(
    (1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1),
    ('M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I')
)


def roman_to_int(n):
    n = unicode(n).upper()

    i = result = 0
    for integer, numeral in numeral_map:
        while n[i:i + len(numeral)] == numeral:
            result += integer
            i += len(numeral)
    return result


class Station(models.Model):
    id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=128, default="**UNKNOWN**")
    short_name = models.CharField(max_length=64, default='')
    structure = models.BooleanField(default=False)
    item = models.ForeignKey(Item, null=True, default=None)
    lastupdated = models.DateTimeField(auto_now=True)

    system = models.ForeignKey(System, null=True)

    class Meta:
        app_label = 'thing'

    # Used to add structures
    @staticmethod
    def get_or_create(id, api):
        # Check database for station/structure
        station = Station.objects.filter(id=id)
        if len(station) == 1:
            station = station[0]
            if not station.structure:
                return station
            else:
                # if station.lastupdated < datetime.now() - timedelta(days=2):
                #     # Update the structures name from the API
                #     try:
                #         r = api.get("/universe/structures/%s/" % station.id)
                #         if r == None:
                #             station.name = r['name']
                #             station.system_id = r['solar_system_id']
                #             station.save()
                #     except Exception:
                #         # We failed to get it, probably because it's a structure
                #         # this token no longer has docking rights for
                #         # Save the station anyway so don't repeatedly bash the API
                #         station.save()

                return station

        try:
            # Check if its a sov station we don't have yet
            if id < 71001146:
                r = api.get("/v2/universe/stations/%s/" % id)
                station = Station(
                    id=id,
                    name=r['name'],
                    system_id=r['system_id'],
                    structure=False
                )
            else:
                # It doesn't exist, lets create it
                r = api.get("/v1/universe/structures/%s/" % id)
                station = Station(
                    id=id,
                    structure=True
                )
                if r is not None:
                    station.name = r['name']
                    station.system_id = r['solar_system_id']
                    if "type_id" in r:
                        station.item_id = r['type_id']

            station.save()
            return station

        except Exception:
            # We crashed out, it must not be a structure
            return None

    def __unicode__(self):
        return self.name

    # Build the short name when this object is saved
    def save(self, *args, **kwargs):
        self._make_shorter_name()
        super(Station, self).save(*args, **kwargs)

    def _make_shorter_name(self):
        out = []

        parts = self.name.split(' - ')
        if len(parts) == 1:
            self.short_name = self.name
        else:
            a_parts = parts[0].split()
            try:
                # Change the roman annoyance to a proper digit
                out.append('%s %s' %
                           (a_parts[0], str(roman_to_int(a_parts[1]))))

                # Moooon
                if parts[1].startswith('Moon') and len(parts) == 3:
                    out[0] = '%s-%s' % (out[0], parts[1][5:])
                    out.append(''.join(s[0] for s in parts[2].split()))
                else:
                    out.append(''.join(s[0] for s in parts[1].split()))
            except Exception:
                out.append(a_parts[0])
                out.append(''.join(s[0] for s in parts[1].split()))

            self.short_name = ' - '.join(out)
