from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import get_db_connection

def owner_main_menu():
    """Owner main menu keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Add Player", callback_data='owner_add_player')],
        [InlineKeyboardButton("🌍 View Countries", callback_data='owner_view_countries')],
        [InlineKeyboardButton("▶️ Start Season", callback_data='owner_start_season')],
        [InlineKeyboardButton("⏹️ End Season", callback_data='owner_end_season')],
        [InlineKeyboardButton("🔄 Reset Game", callback_data='owner_reset_game')],
        [InlineKeyboardButton("📢 Send Global Message", callback_data='owner_send_global')],
    ])

def get_ai_countries_keyboard():
    """Keyboard with AI-controlled countries for player assignment"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.id, c.name 
        FROM countries c 
        WHERE c.is_ai_controlled = 1
        ORDER BY c.name
    ''')
    countries = cursor.fetchall()
    conn.close()
    
    buttons = []
    for country in countries:
        buttons.append([InlineKeyboardButton(
            f"🌍 {country['name']}", 
            callback_data=f'assign_country_{country["id"]}'
        )])
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data='owner_back')])
    return InlineKeyboardMarkup(buttons)

def player_main_menu(country_name, resources, army_level):
    """Player main menu with resources and army status"""
    resource_text = f"💰{resources['gold']} 🏗️{resources['iron']} ⛏️{resources['stone']} 🌾{resources['food']}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🏰 {country_name} | Lvl {army_level}", callback_data='player_status')],
        [InlineKeyboardButton(resource_text, callback_data='player_resources')],
        [InlineKeyboardButton("⚔️ Army Management", callback_data='player_army')],
        [InlineKeyboardButton("🤝 Diplomacy", callback_data='player_diplomacy')],
        [InlineKeyboardButton("📜 Alliances", callback_data='player_alliances')],
        [InlineKeyboardButton("🔄 Refresh", callback_data='player_refresh')],
    ])

def army_upgrade_keyboard(country_id, current_level, can_upgrade):
    """Keyboard for army upgrades"""
    buttons = []
    if current_level < 10 and can_upgrade:
        buttons.append([InlineKeyboardButton(
            f"⬆️ Upgrade to Level {current_level + 1}", 
            callback_data=f'upgrade_army_{country_id}'
        )])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data='player_army_back')])
    return InlineKeyboardMarkup(buttons)

def diplomacy_keyboard(country_id):
    """Keyboard for diplomatic actions"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all other countries
    cursor.execute('''
        SELECT c.id, c.name, c.is_ai_controlled 
        FROM countries c 
        WHERE c.id != ?
        ORDER BY c.is_ai_controlled DESC, c.name
    ''', (country_id,))
    other_countries = cursor.fetchall()
    
    conn.close()
    
    buttons = []
    for country in other_countries:
        prefix = "🤖" if country['is_ai_controlled'] else "👑"
        buttons.append([InlineKeyboardButton(
            f"{prefix} {country['name']}", 
            callback_data=f'diplomacy_target_{country["id"]}'
        )])
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data='player_diplomacy_back')])
    return InlineKeyboardMarkup(buttons)

def diplomacy_action_keyboard(country_id, target_id):
    """Keyboard for specific diplomatic actions with a target country"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤝 Propose Alliance", callback_data=f'alliance_propose_{country_id}_{target_id}')],
        [InlineKeyboardButton("⚔️ Declare War", callback_data=f'war_declare_{country_id}_{target_id}')],
        [InlineKeyboardButton("💰 Send Tribute (500 gold)", callback_data=f'tribute_send_{country_id}_{target_id}')],
        [InlineKeyboardButton("🔙 Back", callback_data=f'diplomacy_back_{country_id}')],
    ])

def alliance_management_keyboard(country_id):
    """Keyboard showing current alliances and options"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get active alliances
    cursor.execute('''
        SELECT a.id, c1.name as country1, c2.name as country2, c1.id as cid1, c2.id as cid2
        FROM alliances a
        JOIN countries c1 ON a.country1_id = c1.id
        JOIN countries c2 ON a.country2_id = c2.id
        WHERE (a.country1_id = ? OR a.country2_id = ?) AND a.end_date IS NULL
    ''', (country_id, country_id))
    alliances = cursor.fetchall()
    conn.close()
    
    buttons = []
    for alliance in alliances:
        other_country = alliance['country2'] if alliance['cid1'] == country_id else alliance['country1']
        other_cid = alliance['cid2'] if alliance['cid1'] == country_id else alliance['cid1']
        buttons.append([InlineKeyboardButton(
            f"🤝 {other_country}", 
            callback_data=f'alliance_manage_{alliance["id"]}_{other_cid}'
        )])
    
    if not buttons:
        buttons.append([InlineKeyboardButton("No active alliances", callback_data='no_action')])
    
    buttons.append([InlineKeyboardButton("🔙 Back to Diplomacy", callback_data='player_diplomacy')])
    return InlineKeyboardMarkup(buttons)

def alliance_action_keyboard(alliance_id, other_country_id):
    """Keyboard for alliance actions (maintain/break)"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💔 Break Alliance", callback_data=f'alliance_break_{alliance_id}_{other_country_id}')],
        [InlineKeyboardButton("✅ Maintain Alliance", callback_data='player_alliances')],
    ])

def confirmation_keyboard(action_data, confirm_text="✅ Confirm", cancel_text="❌ Cancel"):
    """Generic confirmation keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(confirm_text, callback_data=f'confirm_{action_data}')],
        [InlineKeyboardButton(cancel_text, callback_data='cancel_action')],
    ])

def global_message_keyboard():
    """Keyboard for owner to send global messages"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Type Message", callback_data='owner_type_global')],
        [InlineKeyboardButton("🔙 Back", callback_data='owner_back')],
    ])