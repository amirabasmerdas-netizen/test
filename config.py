import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
PORT = int(os.getenv('PORT', 8443))
CHANNEL_ID = os.getenv('CHANNEL_ID', '@ancientwars_news')  # News channel username

# Game configuration
OWNER_TELEGRAM_ID = 8588773170
SEASON_DURATION_DAYS = 30
ADVISOR_TIP_INTERVAL_HOURS = 6
AI_ACTION_INTERVAL_MINUTES = 30

# Country definitions with unique bonuses
COUNTRIES = [
    {"name": "Persia", "bonus": "cavalry_speed", "bonus_desc": "+20% army movement speed"},
    {"name": "Rome", "bonus": "fortress_defense", "bonus_desc": "+25% city defense"},
    {"name": "Egypt", "bonus": "nile_bounty", "bonus_desc": "+15% food production"},
    {"name": "China", "bonus": "great_wall", "bonus_desc": "+30% border defense"},
    {"name": "Greece", "bonus": "phalanx", "bonus_desc": "+20% infantry attack"},
    {"name": "Babylon", "bonus": "hanging_gardens", "bonus_desc": "+15% resource production"},
    {"name": "Assyria", "bonus": "siege_masters", "bonus_desc": "+25% siege attack"},
    {"name": "Carthage", "bonus": "naval_supremacy", "bonus_desc": "+30% naval units"},
    {"name": "India", "bonus": "elephant_warfare", "bonus_desc": "+20% heavy unit damage"},
    {"name": "Macedonia", "bonus": "companion_cavalry", "bonus_desc": "+25% cavalry charge"},
    {"name": "Hittites", "bonus": "iron_masters", "bonus_desc": "+20% iron production"},
    {"name": "Phoenicia", "bonus": "trade_network", "bonus_desc": "+25% gold income"},
]

# Resource configuration
RESOURCE_TYPES = ['gold', 'iron', 'stone', 'food']
STARTING_RESOURCES = {'gold': 1000, 'iron': 500, 'stone': 500, 'food': 1500}
RESOURCE_PRODUCTION = {'gold': 50, 'iron': 30, 'stone': 30, 'food': 100}

# Army configuration
MAX_ARMY_LEVEL = 10
ARMY_BASE_STATS = {'attack': 50, 'defense': 50, 'speed': 50}
ARMY_UPGRADE_COST = {
    1: {'gold': 200, 'iron': 100, 'stone': 50, 'food': 200},
    2: {'gold': 400, 'iron': 200, 'stone': 100, 'food': 300},
    3: {'gold': 800, 'iron': 400, 'stone': 200, 'food': 500},
    4: {'gold': 1500, 'iron': 750, 'stone': 400, 'food': 800},
    5: {'gold': 2500, 'iron': 1250, 'stone': 700, 'food': 1200},
    6: {'gold': 4000, 'iron': 2000, 'stone': 1200, 'food': 2000},
    7: {'gold': 6000, 'iron': 3000, 'stone': 2000, 'food': 3000},
    8: {'gold': 9000, 'iron': 4500, 'stone': 3000, 'food': 4500},
    9: {'gold': 13000, 'iron': 6500, 'stone': 4500, 'food': 6500},
    10: {'gold': 20000, 'iron': 10000, 'stone': 7000, 'food': 10000},
}