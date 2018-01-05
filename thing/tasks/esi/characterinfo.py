import json

from datetime import datetime, timedelta

from django import db
from django.db.models import Sum, F, FloatField, Q

from .apitask import APITask
from .mail_fetch_task import ESI_MailFetchTask

from thing.esi_enums import *
from thing.esi import ESI
from thing.models import *

# This task effectively replaces the characterInfo and characterSheet calls
class ESI_CharacterInfo(APITask):
    name = "thing.esi.character_info"
    api = None

    def run(self, token_id):
        self.api = self.get_api(token_id)

        ## Character Data
        characterID = self.api.token.characterID
        public = self.api.get("/v4/characters/$id/")

        # Get or create character object
        try:
            character = Character.objects.select_related('config', 'corporation', 'details').get(pk=characterID)
        except Character.DoesNotExist:
            character = Character()
            character.id = characterID
        character.name = public['name']
        character.corporation = Corporation.get_or_create(public['corporation_id'])

        # Get or create the detail/config objects
        try:
            charConfig = CharacterConfig.objects.get(character=character)
        except CharacterConfig.DoesNotExist:
            charConfig = CharacterConfig(character=character)

        try:
            charDetails = CharacterDetails.objects.get(character=character)
        except CharacterDetails.DoesNotExist:
            charDetails = CharacterDetails(character=character)


        # Perform the rest of the calls
        with db.transaction.atomic():
            location = self.api.get("/v1/characters/$id/location/")
            ship = self.api.get("/v1/characters/$id/ship/")
            wallet = self.api.get("/v1/characters/$id/wallet/")

            # Populate the database
            charDetails.wallet_balance = float(wallet)
            charDetails.plex_balance = 0

            # Get character attributes
            attributes = self.api.get("/v1/characters/$id/attributes/")
            charDetails.cha_attribute = attributes['charisma']
            charDetails.int_attribute = attributes['intelligence']
            charDetails.mem_attribute = attributes['memory']
            charDetails.per_attribute = attributes['perception']
            charDetails.wil_attribute = attributes['willpower']

            charDetails.security_status = public['security_status']
            charDetails.last_known_location = self.last_known_location(location)
            charDetails.ship_name = ship['ship_name']
            charDetails.ship_item = Item.objects.get(id=ship['ship_type_id'])

            # Save
            character.save()
            charDetails.save()
            charConfig.save()
            self.api.token.character = character
            self.api.token.save()

        # Clones
        with db.transaction.atomic():
            clones = self.api.get("/v3/characters/$id/clones/")
            # Delete existing clones
            Clone.objects.filter(character=character).delete()
            if "jump_clones" in clones:
                for clone in clones['jump_clones']:
                    db_clone = Clone(
                        character=character,
                        location=Station.get_or_create(clone['location_id'], self.api)
                    )
                    if "name" in clone:
                        db_clone.name = clone['name']
                    db_clone.save()

                    if "implants" in clone:
                        for implant_id in clone['implants']:
                            db_implant = CloneImplant(
                                clone=db_clone,
                                implant_id=implant_id
                            )
                            db_implant.save()

        # Wallet Journal
        with db.transaction.atomic():
            journal = self.api.get("/v3/characters/$id/wallet/journal/")
            for entry in journal:
                db_entry = JournalEntry.objects.filter(character=character, ref_id=entry['ref_id'])
                if len(db_entry) == 0:
                    db_entry = JournalEntry(
                        character=character,
                        date=self.parse_api_date(entry['date']),
                        ref_id=entry['ref_id'],
                        ref_type=entry['ref_type']
                    )

                    if db_entry.ref_type == "insurance":
                        db_entry.owner1_id = character.id
                        db_entry.owner2_id = 1000132
                        if "extra_info" in entry:
                            db_entry.arg_name = entry['extra_info']['destroyed_ship_type_id']
                    else:
                        if "first_party_id" in entry:
                            db_entry.owner1_id = entry['first_party_id']
                        if "second_party_id" in entry:
                            db_entry.owner2_id = entry['second_party_id']

                    db_entry.amount = entry['amount']
                    db_entry.balance = entry['balance']
                    if "reason" in entry:
                        db_entry.reason = entry['reason']

                    db_entry.save()


        ## Skills
        with db.transaction.atomic():
            skills = self.api.get("/v4/characters/$id/skills/")
            for skill in skills['skills']:
                db_skill = CharacterSkill.objects.filter(character=character, skill_id=skill['skill_id'])
                if len(db_skill) == 1:
                    db_skill = db_skill[0]
                else:
                    db_skill = CharacterSkill(character=character, skill_id=skill['skill_id'])

                db_skill.level = skill['trained_skill_level']
                db_skill.points = skill['skillpoints_in_skill']
                db_skill.save()

            queue = self.api.get("/v2/characters/$id/skillqueue/")
            # Remove all skills
            SkillQueue.objects.filter(character=character).delete()
            try:
                for skill in queue:
                        db_skill = SkillQueue(character=character, skill_id=skill['skill_id'], to_level=skill['finished_level'])
                        db_skill.start_time = self.parse_api_date(skill['start_date'])
                        db_skill.end_time = self.parse_api_date(skill['finish_date'])
                        db_skill.start_sp = skill['training_start_sp']
                        db_skill.end_sp = skill['level_end_sp']
                        db_skill.to_level = skill['finished_level']
                        db_skill.save()

            except KeyError:
                # This character isn't training, wipe the queue
                SkillQueue.objects.filter(character=character).delete()


        ## Assets
        with db.transaction.atomic():
            assets = self.api.get("/v3/characters/$id/assets/")
            asset_map = map(lambda x: x['item_id'], assets)

            for asset in assets:
                db_asset = Asset.objects.filter(asset_id=asset['item_id'])
                if len(db_asset) == 1:
                    db_asset = db_asset[0]
                else:
                    db_asset = Asset(character=character, asset_id=asset['item_id'], item_id=asset['type_id'])

                db_asset.inv_flag_id = PersonalLocationFlagEnum[asset['location_flag']].value

                db_asset.singleton = asset['is_singleton']
                if asset['is_singleton']:
                    db_asset.quantity = 1
                    db_asset.raw_quantity = -1
                else:
                    db_asset.quantity = asset['quantity']
                    db_asset.raw_quantity = 0

                # Calculate parent and location
                # Try asset
                if asset['location_id'] in asset_map:
                    db_asset.parent = asset['location_id']
                    db_asset.station = None
                    db_asset.system = None
                    db_asset.save()
                    continue
                # Try station
                if Station.get_or_create(asset['location_id'], self.api) != None:
                    station = Station.objects.get(id=asset['location_id'])
                    db_asset.station = station
                    db_asset.system_id = station.system_id
                    db_asset.save()
                    continue
                # Try solar system
                if System.objects.filter(id=asset['location_id']).count() > 0:
                    db_asset.station = None
                    db_asset.system_id = asset['location_id']
                    db_asset.save()
                    continue

            # Fix station/system values for parented assets
            def resolve_location(asset):
                if asset.station == None:
                    #print "%s/%s" % (asset.parent, asset.asset_id)
                    parent = Asset.objects.get(asset_id=asset.parent)
                    if parent.station_id != None:
                        asset.station_id = parent.station_id
                        asset.system_id = parent.system_id
                        asset.save()
                        return (parent.station_id, parent.system_id)
                    else:
                        station_id, system_id = resolve_location()
                        asset.station_id = station_id
                        asset.system_id = system_id
                        asset.save()
                        return (station_id, system_id)
                else:
                    return None

            for asset in Asset.objects.filter(character=character, station=None):
                try:
                    resolve_location(asset)
                except Exception:
                    pass

            # Delete all assets not in the map
            Asset.objects.filter(character=character).exclude(asset_id__in=asset_map).delete()

            # Fetch names for all ships/containers
            items = list(Asset.objects.filter(
                Q(character=character),
                Q(item__item_group__category_id=6) | Q(item__item_group__in=[12 , 340, 448])
            ).values_list(
                'asset_id',
                flat=True
            ))
            asset_names = self.api.post("/v1/characters/$id/assets/names/", data=json.dumps(items))
            if asset_names is not None:
                for asset in asset_names:
                    db_asset = Asset.objects.get(asset_id=asset['item_id'])
                    db_asset.name = asset['name']
                    db_asset.save()

            # Rebuild asset summary
            AssetSummary.objects.filter(character=character).delete()
            summaries = Asset.objects.raw('''
                SELECT
                    thing_station.id as id,
                	thing_station.id as station_id,
                    thing_station.system_id as system_id,
                    SUM(thing_asset.quantity) as total_items,
                    SUM(thing_asset.quantity * thing_item.volume) as total_volume,
                    SUM(thing_asset.quantity * thing_item.sell_price) as total_value
                FROM thing_asset
                INNER JOIN thing_station ON thing_station.id = thing_asset.station_id
                INNER JOIN thing_item ON thing_item.id = thing_asset.item_id
                WHERE thing_asset.character_id = %s
                GROUP BY thing_station.id
                ORDER BY thing_station.name
                ''', [character.id])

            for summary in summaries:
                db_summary = AssetSummary(
                    character=character,
                    system_id=summary.system_id,
                    station_id=summary.id,
                    total_items=summary.total_items,
                    total_volume=summary.total_volume,
                    total_value=summary.total_value
                )
                db_summary.save()


        ## Standings
        with db.transaction.atomic():
            standings = self.api.get("/v1/characters/$id/standings/")
            factions = filter(lambda x: x['from_type'] == "faction", standings)
            for faction in factions:
                factionstanding = FactionStanding.objects.filter(character=character, faction_id=faction['from_id'])
                if len(factionstanding) == 1:
                    factionstanding = factionstanding[0]
                else:
                    factionstanding = FactionStanding(character=character, faction_id=faction['from_id'])

                factionstanding.standing = faction['standing']
                factionstanding.save()

            npc_corps = filter(lambda x: x['from_type'] == "npc_corp", standings)
            for npc_corp in npc_corps:
                corpstanding = CorporationStanding.objects.filter(character=character, corporation_id=npc_corp['from_id'])
                if len(corpstanding) == 1:
                    corpstanding = corpstanding[0]
                else:
                    corpstanding = CorporationStanding(character=character, corporation_id=npc_corp['from_id'])

                corpstanding.standing = npc_corp['standing']
                corpstanding.save()


        ## Industry
        with db.transaction.atomic():
            jobs = self.api.get("/v1/characters/$id/industry/jobs/")
            jobs += self.api.get("/v1/corporations/%s/industry/jobs/" % character.corporation_id)
            for job in jobs:
                db_job = IndustryJob.objects.filter(job_id=job['job_id'])
                if len(db_job) == 1:
                    db_job = db_job[0]
                else:
                    db_job = IndustryJob(
                        job_id=job['job_id'],
                        installer_id=job['installer_id'],
                        activity=job['activity_id'],
                        output_location_id=job['output_location_id'],
                        runs=job['runs'],
                        team_id=0,  # This doesn't exist anymore so it's not in ESI
                        licensed_runs=job['licensed_runs'],
                        duration=job['duration'],
                        start_date=self.parse_api_date(job['start_date']),
                        end_date=self.parse_api_date(job['end_date']),
                        pause_date=datetime(0001, 1, 1, 1, 0),
                        completed_date=datetime(0001, 1, 1, 1, 0),
                        blueprint_id=job['blueprint_type_id'],
                        character=character,
                        corporation=None,
                        product_id=job['product_type_id'],

                        # POSes are getting removed soon so we're just going to
                        # assume the facility is a station/structure
                        system_id=Station.get_or_create(job['facility_id'], self.api).system.id
                    )

                # Update other values
                db_job.status = IndustryJobStatusEnum[job['status']].value

                if "completed_date" in job:
                    db_job.completed_date = self.parse_api_date(job['completed_date'])
                if "pause_date" in job:
                    db_job.pause_date = self.parse_api_date(job['pause_date'])

                db_job.save()

            # Fix status of stuck jobs
            job_map = map(lambda x: x['job_id'], jobs)
            for job in IndustryJob.objects.filter(
                    character=character,
                    status=IndustryJob.ACTIVE_STATUS
                ).exclude(
                    job_id__in=job_map
                ):

                # Set stuck jobs to delivered
                job.status = IndustryJob.DELIVERED_STATUS
                job.save()

        ## Orders
        with db.transaction.atomic():
            orders = self.api.get("/v1/characters/$id/orders/")

            # Delete orders if they no longer exist
            order_map = map(lambda x: x['order_id'], orders)
            MarketOrder.objects.filter(character=character).exclude(order_id__in=order_map).delete()

            for order in orders:
                db_order = MarketOrder.objects.filter(order_id=order['order_id'])
                if len(db_order) == 1:
                    db_order = db_order[0]
                else:
                    db_order = MarketOrder(
                        order_id=order['order_id'],
                        character=character,
                        creator_character_id=character.id,
                        escrow=order['escrow'],
                        buy_order=order['is_buy_order'],
                        volume_entered=order['volume_total'],
                        corp_wallet_id=None,
                        item_id=order['type_id'],
                        station=Station.get_or_create(order['location_id'], self.api)
                    )

                db_order.price = order['price']
                db_order.total_price = order['price'] * order['volume_remain']
                db_order.volume_remaining = order['volume_remain']
                db_order.minimum_volume = order['min_volume']
                db_order.issued = self.parse_api_date(order['issued'])
                db_order.expires = db_order.issued + timedelta(days=order['duration'])
                db_order.save()


        ## Mails
        mails = self.api.get("/v1/characters/$id/mail/")

        # Filter out mails we already have
        if mails is not None:
            db_mail_ids = MailMessage.objects.filter(
                character=character
            ).values_list('message_id', flat=True)
            mails = filter(lambda x: x['mail_id'] not in db_mail_ids, mails)

            mail_task = ESI_MailFetchTask()
            for mail in mails:
                mail_task.apply_async(args=[token_id, mail], countdown=30)


        ## PI
        try:
            with db.transaction.atomic():
                planets = self.api.get("/v1/characters/$id/planets/")

                # Delete colonies that no longer exist
                planet_map = map(lambda x: x['planet_id'], planets)
                Colony.objects.filter(character=character).exclude(planet_id__in=planet_map).delete()

                for planet in planets:
                    db_planet = Colony.objects.filter(character=character, planet_id=planet['planet_id'])
                    if len(db_planet) == 1:
                        db_planet = db_planet[0]
                    else:
                        db_planet = Colony(
                            character=character,
                            system_id=planet['solar_system_id'],
                            planet_id=planet['planet_id'],
                            planet=self.api.get("/v1/universe/planets/%s/" % planet['planet_id'])['name'],
                            planet_type=planet['planet_type'],
                            last_update=self.parse_api_date(planet['last_update']),
                            level=planet['upgrade_level'],
                            pins=planet['num_pins']
                        )
                    db_planet.save()

                    # Get planet details
                    details = self.api.get("/v3/characters/$id/planets/%s/" % planet['planet_id'])

                    # Delete the pins that no longer exist
                    pin_map = map(lambda x: x['pin_id'], details['pins'])
                    Pin.objects.filter(colony=db_planet).exclude(pin_id__in=pin_map).delete()

                    for pin in details['pins']:
                        db_pin = Pin.objects.filter(pin_id=pin['pin_id'])
                        if len(db_pin) == 1:
                            db_pin = db_pin[0]
                        else:
                            db_pin = Pin(
                                pin_id=pin['pin_id'],
                                colony=db_planet,
                                type_id=pin['type_id']
                            )

                        if "schematic_id" in pin:
                            db_pin.schematic = pin['schematic_id']
                        if "extractor_details" in pin:
                            db_pin.cycle_time = pin['extractor_details']['cycle_time']
                            db_pin.quantity_per_cycle = pin['extractor_details']['qty_per_cycle']
                            db_pin.installed = self.parse_api_date(pin['install_time'])
                            db_pin.expires = self.parse_api_date(pin['expiry_time'])
                        if "contents" in pin:
                            # Clear contents
                            PinContent.objects.filter(pin=db_pin).delete()

                            # Add new contents
                            contents = []
                            for item in pin['contents']:
                                content = PinContent(
                                    pin=db_pin,
                                    item_id=item['type_id'],
                                    quantity=item['amount']
                                )
                                contents.append(content)
                                content.save()

                            # Calculate content size
                            db_pin.content_size = sum(map(lambda x: x.quantity * x.item.volume, contents))

                        db_pin.save()
        except Exception:
            pass


        ## Contracts
        with db.transaction.atomic():
            try:
                contracts = self.api.get("/v1/characters/$id/contracts/")

                for contract in contracts:
                    db_contract = Contract.objects.filter(contract_id=contract['contract_id'])
                    if len(db_contract) > 0:
                        db_contract = db_contract[0]
                    else:
                        db_contract = Contract(
                            character=character,
                            contract_id=contract['contract_id']
                        )

                    # Update info
                    if "issuer_id" in contract:
                        db_contract.issuer_char = Character.get_or_create(contract['issuer_id'])
                    db_contract.issuer_corp = Corporation.get_or_create(contract['issuer_corporation_id'])
                    db_contract.assignee_id = contract['assignee_id']
                    db_contract.acceptor_id = contract['acceptor_id']

                    db_contract.start_station = Station.get_or_create(contract['start_location_id'], self.api)
                    db_contract.end_station = Station.get_or_create(contract['end_location_id'], self.api)

                    db_contract.type = self.contract_types[contract['type']]
                    db_contract.status = self.contract_states[contract['status']]
                    db_contract.title = contract['title']
                    db_contract.for_corp = contract['for_corporation']
                    if contract['availability'] == "public":
                        db_contract.public = True

                    db_contract.date_issued = self.parse_api_date(contract['date_issued'])
                    db_contract.date_expired = self.parse_api_date(contract['date_expired'])
                    if "date_accepted" in contract:
                        db_contract.date_accepted = self.parse_api_date(contract['date_accepted'])
                    if "date_completed" in contract:
                        db_contract.date_completed = self.parse_api_date(contract['date_completed'])
                    db_contract.num_days = contract['days_to_complete']

                    db_contract.price = contract['price']
                    db_contract.reward = contract['reward']
                    db_contract.collateral = contract['collateral']
                    if "buyout" in contract:
                        db_contract.buyout = contract['buyout']
                    db_contract.volume = contract['volume']

                    db_contract.save()

                    # Items
                    if not db_contract.retrieved_items:
                        items = self.api.get("/v1/characters/$id/contracts/%s/items" % contract['contract_id'])
                        for item in items:
                            db_item = ContractItem(
                                id=item['record_id'],
                                contract=db_contract,
                                item_id=item['type_id'],
                                quantity=item['quantity'],
                                singleton=item['is_singleton'],
                                included=item['is_included']
                            )
                            if "raw_quantity" in item:
                                db_item.raw_quantity = item['raw_quantity']
                            db_item.save()

                        db_contract.retrieved_items = True
                        db_contract.save()
            except Exception:
                # This character hasn't been re-added for contracts
                pass


        ## Fatigue
        try:
            fatigue = self.api.get("/v1/characters/$id/fatigue/")

            charDetails.last_jump_date = self.parse_api_date(fatigue['last_jump_date'])
            charDetails.fatigue_expire_date = self.parse_api_date(fatigue['jump_fatigue_expire_date'])
            charDetails.save()
        except Exception:
            # This character hasn't been re-added since 24/08/17
            pass


        ## Implants
        with db.transaction.atomic():
            try:
                implants = self.api.get("/v1/characters/$id/implants/")

                charDetails.implants.clear()
                for implant in implants:
                    charDetails.implants.add(implant)

            except Exception:
                # This character hasn't been re-added since 24/08/17
                pass


        # If we reach this far the token is active again
        character.esitoken.status = True
        character.esitoken.save()
        print "Finished updating %s:%s" % (character.id, character.name)



    # Generates the last known location string
    def last_known_location(self, location):
        # Check for undocked in space
        if len(location) == 1:
            return System.objects.get(id=location['solar_system_id']).name

        if "station_id" in location:
            return Station.get_or_create(location['station_id'], self.api).name

        if "structure_id" in location:
            try:
                structure = Station.get_or_create(location['structure_id'], self.api)
                str_type = structure.item
                return "%s (%s)" % (structure.name, str_type.name)
            except Exception:
                return ""

        return ""
