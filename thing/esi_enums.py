from enum import Enum

class IndustryJobStatusEnum(Enum):
    active = 1
    paused = 2
    ready = 3
    delivered = 104
    cancelled = 102
    reverted = 999


class JournalReferenceEnum(Enum):
    player_trading = 1
    market_transaction = 2
    gm_cash_transfer = 3
    mission_reward = 7
    clone_activation = 8
    inheritance = 9
    player_donation = 10
    corporation_payment = 11
    docking_fee = 12
    office_rental_fee = 13
    factory_slot_rental_fee = 14
    repair_bill = 15
    bounty = 16
    bounty_prize = 17
    insurance = 19
    mission_expiration = 20
    mission_completion = 21
    shares = 22
    courier_mission_escrow = 23
    mission_cost = 24
    agent_miscellaneous = 25
    lp_store = 26
    agent_location_services = 27
    agent_donation = 28
    agent_security_services = 29
    agent_mission_collateral_paid = 30
    agent_mission_collateral_refunded = 31
    agents_preward = 32
    agent_mission_reward = 33
    agent_mission_time_bonus_reward = 34
    cspa = 35
    cspaofflinerefund = 36
    corporation_account_withdrawal = 37
    corporation_dividend_payment = 38
    corporation_registration_fee = 39
    corporation_logo_change_cost = 40
    release_of_impounded_property = 41
    market_escrow = 42
    agent_services_rendered = 43
    market_fine_paid = 44
    corporation_liquidation = 45
    brokers_fee = 46
    corporation_bulk_payment = 47
    alliance_registration_fee = 48
    war_fee = 49
    alliance_maintainance_fee = 50
    contraband_fine = 51
    clone_transfer = 52
    acceleration_gate_fee = 53
    transaction_tax = 54
    jump_clone_installation_fee = 55
    manufacturing = 56
    researching_technology = 57
    researching_time_productivity = 58
    researching_material_productivity = 59
    copying = 60
    reverse_engineering = 62
    contract_auction_bid = 63
    contract_auction_bid_refund = 64
    contract_collateral = 65
    contract_reward_refund = 66
    contract_auction_sold = 67
    contract_reward = 68
    contract_collateral_refund = 69
    contract_collateral_payout = 70
    contract_price = 71
    contract_brokers_fee = 72
    contract_sales_tax = 73
    contract_deposit = 74
    contract_deposit_sales_tax = 75
    contract_auction_bid_corp = 77
    contract_collateral_deposited_corp = 78
    contract_price_payment_corp = 79
    contract_brokers_fee_corp = 80
    contract_deposit_corp = 81
    contract_deposit_refund = 82
    contract_reward_deposited = 83
    contract_reward_deposited_corp = 84
    bounty_prizes = 85
    advertisement_listing_fee = 86
    medal_creation = 87
    medal_issued = 88
    dna_modification_fee = 90
    sovereignity_bill = 91
    bounty_prize_corporation_tax = 92
    agent_mission_reward_corporation_tax = 93
    agent_mission_time_bonus_reward_corporation_tax = 94
    upkeep_adjustment_fee = 95
    planetary_import_tax = 96
    planetary_export_tax = 97
    planetary_construction = 98
    corporate_reward_payout = 99
    bounty_surcharge = 101
    contract_reversal = 102
    corporate_reward_tax = 103
    store_purchase = 106
    store_purchase_refund = 107
    datacore_fee = 112
    war_fee_surrender = 113
    war_ally_contract = 114
    bounty_reimbursement = 115
    kill_right_fee = 116
    security_processing_fee = 117
    industry_job_tax = 120
    infrastructure_hub_maintenance = 122
    asset_safety_recovery_tax = 123
    opportunity_reward = 124
    project_discovery_reward = 125
    project_discovery_tax = 126
    reprocessing_tax = 127
    jump_clone_activation_fee = 128
    operation_bonus = 129


class PersonalLocationFlagEnum(Enum):
    AutoFit = 0
    Wardrobe = 3
    Cargo = 5
    CorpseBay = 174
    DroneBay = 87
    FleetHangar = 155
    Deliveries = 173
    HiddenModifiers = 156
    Hangar = 4
    Skill = 7
    HangarAll = 1000
    LoSlot0 = 11
    LoSlot1 = 12
    LoSlot2 = 13
    LoSlot3 = 14
    LoSlot4 = 15
    LoSlot5 = 16
    LoSlot6 = 17
    LoSlot7 = 18
    MedSlot0 = 19
    MedSlot1 = 20
    MedSlot2 = 21
    MedSlot3 = 22
    MedSlot4 = 23
    MedSlot5 = 24
    MedSlot6 = 25
    MedSlot7 = 26
    HiSlot0 = 27
    HiSlot1 = 28
    HiSlot2 = 29
    HiSlot3 = 30
    HiSlot4 = 31
    HiSlot5 = 32
    HiSlot6 = 33
    HiSlot7 = 34
    AssetSafety = 36
    Locked = 63
    Unlocked = 64
    Implant = 89
    QuafeBay = 154
    RigSlot0 = 92
    RigSlot1 = 93
    RigSlot2 = 94
    RigSlot3 = 95
    RigSlot4 = 96
    RigSlot5 = 97
    RigSlot6 = 98
    RigSlot7 = 99
    ShipHangar = 90
    SpecializedFuelBay = 133
    SpecializedOreHold = 134
    SpecializedGasHold = 135
    SpecializedMineralHold = 136
    SpecializedSalvageHold = 137
    SpecializedShipHold = 138
    SpecializedSmallShipHold = 139
    SpecializedMediumShipHold = 140
    SpecializedLargeShipHold = 141
    SpecializedIndustrialShipHold = 142
    SpecializedAmmoHold = 143
    SpecializedCommandCenterHold = 148
    SpecializedPlanetaryCommoditiesHold = 149
    SpecializedMaterialBay = 151
    SubSystemSlot0 = 125
    SubSystemSlot1 = 126
    SubSystemSlot2 = 127
    SubSystemSlot3 = 128
    SubSystemSlot4 = 129
    SubSystemSlot5 = 130
    SubSystemSlot6 = 131
    SubSystemSlot7 = 132
    FighterBay = 158
    FighterTube0 = 159
    FighterTube1 = 160
    FighterTube2 = 161
    FighterTube3 = 162
    FighterTube4 = 163
    SubSystemBay = 177
