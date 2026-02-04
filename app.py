import os
import logging
import random
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== تنظیمات از Environment Variables ==========
TOKEN = os.environ.get('BOT_TOKEN', '')
OWNER_ID = int(os.environ.get('OWNER_ID', '8588773170'))
CHANNEL_ID = os.environ.get('CHANNEL_ID', '')
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///game.db')
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', '')  # Render خودش اینو میده
BOT_USERNAME = os.environ.get('BOT_USERNAME', '@YourBotUsername')

# بررسی وجود توکن
if not TOKEN:
    logging.error("❌ BOT_TOKEN تنظیم نشده است!")
    exit(1)

# ایجاد ربات
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== توابع کمکی دیتابیس ==========
def get_db_connection():
    """ایجاد اتصال به دیتابیس"""
    try:
        # برای Render (PostgreSQL)
        if DATABASE_URL and DATABASE_URL.startswith('postgres'):
            import psycopg2
            # تبدیل postgres:// به postgresql://
            db_url = DATABASE_URL.replace('postgres://', 'postgresql://')
            conn = psycopg2.connect(db_url, sslmode='require')
            logger.info("✅ اتصال به PostgreSQL برقرار شد")
            return conn
    except ImportError:
        logger.warning("⚠️ psycopg2 نصب نشده، از SQLite استفاده می‌شود")
    except Exception as e:
        logger.error(f"❌ خطا در اتصال به PostgreSQL: {e}")
    
    # SQLite برای توسعه محلی و Fallback
    conn = sqlite3.connect('game.db', check_same_thread=False)
    logger.info("✅ اتصال به SQLite برقرار شد")
    return conn

def init_database():
    """اولیه‌سازی دیتابیس"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # ========== جدول بازیکنان ==========
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                country TEXT,
                gold INTEGER DEFAULT 1000,
                iron INTEGER DEFAULT 500,
                stone INTEGER DEFAULT 500,
                food INTEGER DEFAULT 1000,
                wood INTEGER DEFAULT 500,
                army_infantry INTEGER DEFAULT 50,
                army_archer INTEGER DEFAULT 30,
                army_cavalry INTEGER DEFAULT 20,
                army_spearman INTEGER DEFAULT 40,
                army_thief INTEGER DEFAULT 10,
                defense_wall INTEGER DEFAULT 50,
                defense_tower INTEGER DEFAULT 20,
                defense_gate INTEGER DEFAULT 30,
                mine_gold_level INTEGER DEFAULT 1,
                mine_iron_level INTEGER DEFAULT 1,
                mine_stone_level INTEGER DEFAULT 1,
                farm_level INTEGER DEFAULT 1,
                barracks_level INTEGER DEFAULT 1,
                join_date TIMESTAMP,
                last_active TIMESTAMP,
                diplomacy_notifications INTEGER DEFAULT 1
            )
        ''')
        
        # ========== جدول کشورها ==========
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS countries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                special_resource TEXT,
                controller TEXT DEFAULT 'AI',
                player_id INTEGER,
                capital_x INTEGER DEFAULT 100,
                capital_y INTEGER DEFAULT 100
            )
        ''')
        
        # ========== کشورهای پیش‌فرض ==========
        countries = [
            ('پارس', 'اسب', 100, 100),
            ('روم', 'آهن', 200, 100),
            ('مصر', 'طلا', 100, 200),
            ('چین', 'غذا', 200, 200),
            ('یونان', 'سنگ', 150, 150),
            ('بابل', 'دانش', 50, 150),
            ('آشور', 'نفت', 150, 50),
            ('کارتاژ', 'کشتی', 250, 100),
            ('هند', 'ادویه', 100, 250),
            ('مقدونیه', 'فیل', 200, 50)
        ]
        
        for name, resource, x, y in countries:
            cursor.execute('INSERT OR IGNORE INTO countries (name, special_resource, capital_x, capital_y) VALUES (?, ?, ?, ?)', 
                          (name, resource, x, y))
        
        # ========== جدول نبردها ==========
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS battles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attacker_id INTEGER,
                defender_id INTEGER,
                attacker_country TEXT,
                defender_country TEXT,
                result TEXT,
                attacker_losses INTEGER,
                defender_losses INTEGER,
                gold_looted INTEGER DEFAULT 0,
                iron_looted INTEGER DEFAULT 0,
                food_looted INTEGER DEFAULT 0,
                battle_date TIMESTAMP
            )
        ''')
        
        # ========== جدول دیپلماسی ==========
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS diplomacy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_player_id INTEGER,
                to_player_id INTEGER,
                from_country TEXT,
                to_country TEXT,
                relation_type TEXT,
                status TEXT DEFAULT 'pending',
                message TEXT,
                created_at TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        
        conn.commit()
        logger.info("✅ دیتابیس اولیه‌سازی شد")
        
    except Exception as e:
        logger.error(f"❌ خطا در اولیه‌سازی دیتابیس: {e}")
        conn.rollback()
    finally:
        conn.close()

# ========== اجرای اولیه‌سازی دیتابیس ==========
init_database()

# ========== توابع کمکی ==========
def execute_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    """تابع کمکی برای اجرای کوئری‌ها"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(query, params)
        
        if commit:
            conn.commit()
        
        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
        else:
            result = None
        
        return result
    except Exception as e:
        logger.error(f"خطا در اجرای کوئری: {e}")
        if commit:
            conn.rollback()
        raise e
    finally:
        conn.close()

# ========== توابع محاسباتی ==========
def calculate_army_power(player_data):
    """محاسبه قدرت کلی ارتش"""
    if isinstance(player_data, tuple):
        # تبدیل tuple به dict
        player_dict = {
            'army_infantry': player_data[0],
            'army_archer': player_data[1],
            'army_cavalry': player_data[2],
            'army_spearman': player_data[3],
            'army_thief': player_data[4]
        }
        player_data = player_dict
    
    power = (
        player_data.get('army_infantry', 0) * 1 +
        player_data.get('army_archer', 0) * 1.5 +
        player_data.get('army_cavalry', 0) * 2 +
        player_data.get('army_spearman', 0) * 1.2 +
        player_data.get('army_thief', 0) * 0.8
    )
    return power

def calculate_daily_production(user_id):
    """محاسبه تولید روزانه"""
    player = execute_query('''
        SELECT mine_gold_level, mine_iron_level, mine_stone_level,
               farm_level, barracks_level, country
        FROM players WHERE user_id = ?
    ''', (user_id,), fetchone=True)
    
    if not player:
        return None
    
    mine_gold, mine_iron, mine_stone, farm, barracks, country = player
    
    # تولید پایه
    production = {
        'gold': mine_gold * 50,
        'iron': mine_iron * 30,
        'stone': mine_stone * 40,
        'food': farm * 100,
        'wood': 20
    }
    
    # اعمال بونس کشور
    if country:
        country_data = execute_query(
            'SELECT special_resource FROM countries WHERE name = ?',
            (country,), fetchone=True
        )
        if country_data:
            resource = country_data[0]
            bonuses = {
                'طلا': ('gold', 1.5),
                'آهن': ('iron', 1.5),
                'غذا': ('food', 1.5),
                'سنگ': ('stone', 1.5),
                'اسب': ('food', 1.3),
                'دانش': ('gold', 1.2)
            }
            if resource in bonuses:
                resource_type, multiplier = bonuses[resource]
                production[resource_type] = int(production[resource_type] * multiplier)
    
    return production

# ========== منوها ==========
def main_menu(user_id):
    """منوی اصلی"""
    player = execute_query(
        'SELECT country FROM players WHERE user_id = ?',
        (user_id,), fetchone=True
    )
    
    has_country = player and player[0]
    is_owner = user_id == OWNER_ID
    
    keyboard = InlineKeyboardMarkup()
    
    if is_owner:
        # منوی مالک
        keyboard.row(
            InlineKeyboardButton("👑 افزودن بازیکن", callback_data="add_player"),
            InlineKeyboardButton("🌍 کشورها", callback_data="view_countries")
        )
        keyboard.row(
            InlineKeyboardButton("📊 منابع", callback_data="view_resources"),
            InlineKeyboardButton("⚔️ ارتش", callback_data="army_info")
        )
        keyboard.row(
            InlineKeyboardButton("🤝 دیپلماسی", callback_data="diplomacy"),
            InlineKeyboardButton("⛏️ معادن", callback_data="mines_farms")
        )
        keyboard.row(
            InlineKeyboardButton("▶️ شروع فصل", callback_data="start_season"),
            InlineKeyboardButton("⏹️ پایان فصل", callback_data="end_season")
        )
        keyboard.row(
            InlineKeyboardButton("📈 آمار", callback_data="stats"),
            InlineKeyboardButton("🔄 ریست", callback_data="reset_game")
        )
    elif has_country:
        # منوی بازیکن عادی
        keyboard.row(
            InlineKeyboardButton("🏛️ کشور من", callback_data="my_country"),
            InlineKeyboardButton("📊 منابع", callback_data="view_resources")
        )
        keyboard.row(
            InlineKeyboardButton("⚔️ ارتش", callback_data="army_info"),
            InlineKeyboardButton("🤝 دیپلماسی", callback_data="diplomacy")
        )
        keyboard.row(
            InlineKeyboardButton("⛏️ معادن", callback_data="mines_farms"),
            InlineKeyboardButton("🌍 کشورها", callback_data="view_countries")
        )
    else:
        # منوی کاربر بدون کشور
        keyboard.row(
            InlineKeyboardButton("🌍 مشاهده کشورها", callback_data="view_countries"),
            InlineKeyboardButton("📊 وضعیت من", callback_data="view_resources")
        )
    
    keyboard.row(InlineKeyboardButton("ℹ️ راهنما", callback_data="help"))
    
    return keyboard

def army_menu():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("👮 پیاده نظام", callback_data="army_infantry"),
        InlineKeyboardButton("🏹 کمانداران", callback_data="army_archer")
    )
    keyboard.row(
        InlineKeyboardButton("🐎 سوارهنظام", callback_data="army_cavalry"),
        InlineKeyboardButton("🗡️ نیزه‌داران", callback_data="army_spearman")
    )
    keyboard.row(
        InlineKeyboardButton("👤 دزدان", callback_data="army_thief"),
        InlineKeyboardButton("⚔️ حمله", callback_data="attack_country")
    )
    keyboard.row(
        InlineKeyboardButton("🏰 دفاع", callback_data="defend_borders"),
        InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")
    )
    return keyboard

def diplomacy_menu():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("🕊️ صلح", callback_data="peace_request"),
        InlineKeyboardButton("⚔️ جنگ", callback_data="declare_war")
    )
    keyboard.row(
        InlineKeyboardButton("🤝 اتحاد", callback_data="request_alliance"),
        InlineKeyboardButton("💰 تجارت", callback_data="trade_offer")
    )
    keyboard.row(
        InlineKeyboardButton("📜 پیشنهادها", callback_data="view_diplomacy_offers"),
        InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")
    )
    return keyboard

def mines_menu():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("💰 طلا", callback_data="mine_gold"),
        InlineKeyboardButton("⚒️ آهن", callback_data="mine_iron")
    )
    keyboard.row(
        InlineKeyboardButton("🪨 سنگ", callback_data="mine_stone"),
        InlineKeyboardButton("🌾 غذا", callback_data="farm_food")
    )
    keyboard.row(
        InlineKeyboardButton("🏗️ سرباز", callback_data="barracks"),
        InlineKeyboardButton("📦 جمع‌آوری", callback_data="collect_resources")
    )
    keyboard.row(
        InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")
    )
    return keyboard

# ========== هندلرهای اصلی ==========
@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    now = datetime.now()

    # بررسی وجود کاربر
    exists = execute_query(
        "SELECT country FROM players WHERE user_id = ?",
        (user_id,),
        fetchone=True
    )

    if not exists:
        # ثبت‌نام اولیه
        execute_query(
            '''
            INSERT INTO players (user_id, username, join_date, last_active)
            VALUES (?, ?, ?, ?)
            ''',
            (user_id, username, now, now),
            commit=True
        )
        is_new = True
        country = None
    else:
        # آپدیت فعالیت
        execute_query(
            '''
            UPDATE players
            SET username = ?, last_active = ?
            WHERE user_id = ?
            ''',
            (username, now, user_id),
            commit=True
        )
        is_new = False
        country = exists[0]

    # متن خوش‌آمدگویی
    if is_new:
        text = f"""
👋 سلام {message.from_user.first_name}!

🎮 **به بازی جنگ جهانی باستان خوش آمدید**

🏛️ شما هنوز کشوری ندارید  
📩 از مالک بازی درخواست کشور کنید

⚔️ بعد از دریافت کشور:
• ارتش می‌سازی
• منابع جمع می‌کنی
• حمله می‌کنی
• دیپلماسی می‌کنی

👇 از منوی زیر شروع کن
"""
    else:
        if country:
            text = f"""
👋 خوش برگشتی {message.from_user.first_name}!

🏛️ کشور شما: **{country}**
⚔️ ارتشت آماده فرمانه
⛏️ معادنت در حال تولیدن

👇 ادامه بازی:
"""
        else:
            text = f"""
👋 خوش برگشتی {message.from_user.first_name}

⚠️ هنوز کشوری بهت اختصاص داده نشده  
📩 از مالک بازی درخواست بده

👇 منو:
"""

    bot.send_message(
        chat_id=message.chat.id,
        text=text,
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )

@bot.message_handler(commands=['status'])
def show_status(message):
    """نمایش وضعیت ربات"""
    user_count = execute_query('SELECT COUNT(*) FROM players', fetchone=True)[0]
    country_count = execute_query('SELECT COUNT(*) FROM countries', fetchone=True)[0]
    active_players = execute_query(
        'SELECT COUNT(*) FROM players WHERE country IS NOT NULL',
        fetchone=True
    )[0]
    
    status_text = f"""🤖 **وضعیت ربات جنگ جهانی باستان**

👥 **کاربران:** {user_count} نفر
🏛️ **کشورها:** {country_count} کشور
🎮 **بازیکنان فعال:** {active_players} نفر
⚔️ **نبردها:** {execute_query('SELECT COUNT(*) FROM battles', fetchone=True)[0]} نبرد
🤝 **درخواست‌های دیپلماسی:** {execute_query('SELECT COUNT(*) FROM diplomacy', fetchone=True)[0]} درخواست

🔧 **ورژن:** 3.0
🌐 **میزبان:** Render
✅ **وضعیت:** فعال و آنلاین

برای مدیریت بازی از منو استفاده کنید."""
    
    bot.send_message(
        message.chat.id,
        status_text,
        parse_mode='Markdown',
        reply_markup=main_menu(message.from_user.id)
    )

@bot.message_handler(commands=['stats'])
def show_stats(message):
    """نمایش آمار بازی"""
    user_id = message.from_user.id
    
    # آمار کلی
    top_players = execute_query('''
        SELECT username, country, gold + iron * 2 + stone * 1.5 + food as score
        FROM players 
        WHERE country IS NOT NULL
        ORDER BY score DESC 
        LIMIT 5
    ''', fetchall=True)
    
    recent_battles = execute_query('''
        SELECT attacker_country, defender_country, result, battle_date
        FROM battles 
        ORDER BY battle_date DESC 
        LIMIT 5
    ''', fetchall=True)
    
    stats_text = "📊 **آمار بازی جنگ جهانی باستان**\n\n"
    
    stats_text += "🏆 **برترین بازیکنان:**\n"
    for i, (username, country, score) in enumerate(top_players, 1):
        stats_text += f"{i}. {username} ({country}): {int(score)} امتیاز\n"
    
    stats_text += "\n⚔️ **آخرین نبردها:**\n"
    for attacker, defender, result, date in recent_battles:
        date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else date[:10]
        stats_text += f"• {attacker} vs {defender}: {result} ({date_str})\n"
    
    bot.send_message(
        message.chat.id,
        stats_text,
        parse_mode='Markdown',
        reply_markup=main_menu(user_id)
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """مدیریت کلیک روی دکمه‌ها"""
    user_id = call.from_user.id
    
    try:
        # ========== منوی اصلی ==========
        if call.data == "main_menu":
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="🏛️ **منوی اصلی**\n\nلطفاً گزینه مورد نظر را انتخاب کنید:",
                parse_mode='Markdown',
                reply_markup=main_menu(user_id)
            )
        
        # ========== مشاهده کشورها ==========
        elif call.data == "view_countries":
            countries = execute_query('''
                SELECT c.name, c.special_resource, c.controller, 
                       COALESCE(p.username, 'AI') as controller_name
                FROM countries c
                LEFT JOIN players p ON c.player_id = p.user_id
                ORDER BY c.name
            ''', fetchall=True)
            
            text = "🌍 **لیست کشورهای باستانی:**\n\n"
            for name, resource, controller, controller_name in countries:
                emoji = "🤖" if controller == "AI" else "👤"
                text += f"🏛️ **{name}**\n"
                text += f"   📦 منبع ویژه: {resource}\n"
                text += f"   👥 کنترل: {emoji} {controller_name}\n"
                text += f"   {'─'*20}\n"
            
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu"),
                InlineKeyboardButton("🔄 رفرش", callback_data="view_countries")
            )
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        
        # ========== کشور من ==========
        elif call.data == "my_country":
            player = execute_query('''
                SELECT p.country, p.gold, p.iron, p.stone, p.food, p.wood,
                       p.army_infantry, p.army_archer, p.army_cavalry,
                       p.army_spearman, p.army_thief,
                       p.defense_wall, p.defense_tower, p.defense_gate,
                       c.special_resource
                FROM players p
                LEFT JOIN countries c ON p.country = c.name
                WHERE p.user_id = ?
            ''', (user_id,), fetchone=True)
            
            if player and player[0]:
                country, gold, iron, stone, food, wood, infantry, archer, cavalry, spearman, thief, wall, tower, gate, resource = player
                
                # محاسبه قدرت
                army_power = calculate_army_power((infantry, archer, cavalry, spearman, thief))
                
                text = f"""🏛️ **کشور شما: {country}**

🎁 منبع ویژه: {resource}

💰 **ذخایر:**
• طلا: {gold}
• آهن: {iron}
• سنگ: {stone}
• غذا: {food}
• چوب: {wood}

👮 **ارتش:**
• پیاده نظام: {infantry}
• کمانداران: {archer}
• سوارهنظام: {cavalry}
• نیزه‌داران: {spearman}
• دزدان: {thief}

🛡️ **دفاع:**
• دیوار: {wall}
• برج نگهبانی: {tower}
• دروازه: {gate}

⚡ **قدرت کلی:**
• قدرت حمله: {army_power:.1f}"""
            else:
                text = "⚠️ شما هنوز کشوری ندارید!\nلطفاً از مالک درخواست کشور کنید."
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=main_menu(user_id)
            )
        
        # ========== مشاهده منابع ==========
        elif call.data == "view_resources":
            player = execute_query('''
                SELECT p.gold, p.iron, p.stone, p.food, p.wood, c.name,
                       p.mine_gold_level, p.mine_iron_level, p.mine_stone_level, p.farm_level
                FROM players p
                LEFT JOIN countries c ON p.country = c.name
                WHERE p.user_id = ?
            ''', (user_id,), fetchone=True)
            
            if player:
                gold, iron, stone, food, wood, country, mine_gold, mine_iron, mine_stone, farm = player
                
                production = calculate_daily_production(user_id)
                
                text = f"""📊 **وضعیت منابع{' - ' + country if country else ''}**

💰 **ذخایر:**
• طلا: {gold}
• آهن: {iron}
• سنگ: {stone}
• غذا: {food}
• چوب: {wood}

🏭 **سطح تولیدکننده‌ها:**
• معدن طلا: سطح {mine_gold}
• معدن آهن: سطح {mine_iron}
• معدن سنگ: سطح {mine_stone}
• مزرعه: سطح {farm}

📈 **تولید روزانه:**
• طلا: {production['gold'] if production else 0}
• آهن: {production['iron'] if production else 0}
• سنگ: {production['stone'] if production else 0}
• غذا: {production['food'] if production else 0}
• چوب: {production['wood'] if production else 0}

💡 برای جمع‌آوری منابع به بخش معادن بروید."""
            else:
                text = "⚠️ شما هنوز ثبت‌نام نکرده‌اید."
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=main_menu(user_id)
            )
        
        # ========== بخش ارتش ==========
        elif call.data == "army_info":
            player = execute_query('''
                SELECT army_infantry, army_archer, army_cavalry, 
                       army_spearman, army_thief,
                       defense_wall, defense_tower, defense_gate,
                       country
                FROM players WHERE user_id = ?
            ''', (user_id,), fetchone=True)
            
            if player and player[8]:  # اگر کشور دارد
                infantry, archer, cavalry, spearman, thief, wall, tower, gate, country = player
                
                army_power = calculate_army_power((infantry, archer, cavalry, spearman, thief))
                
                text = f"""⚔️ **ارتش و جنگ - {country}**

👮 **نیروهای شما:**
• پیاده نظام: {infantry}
• کمانداران: {archer}
• سوارهنظام: {cavalry}
• نیزه‌داران: {spearman}
• دزدان: {thief}

🛡️ **سازه‌های دفاعی:**
• دیوار: {wall}
• برج نگهبانی: {tower}
• دروازه: {gate}

⚡ **قدرت کلی:**
• قدرت حمله: {army_power:.1f}

از گزینه‌های زیر برای مدیریت ارتش استفاده کنید:"""
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=text,
                    parse_mode='Markdown',
                    reply_markup=army_menu()
                )
            else:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="⚠️ شما هنوز کشوری ندارید!",
                    reply_markup=main_menu(user_id)
                )
        
        # ========== دیپلماسی ==========
        elif call.data == "diplomacy":
            player = execute_query('SELECT country FROM players WHERE user_id = ?', (user_id,), fetchone=True)
            
            if not player or not player[0]:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="⚠️ شما کشوری ندارید!",
                    reply_markup=main_menu(user_id)
                )
                return
            
            text = """🤝 **دیپلماسی**

از طریق دیپلماسی می‌توانید با دیگر کشورها:
• درخواست صلح کنید
• اعلام جنگ دهید
• درخواست اتحاد کنید
• پیشنهاد تجارت دهید

پیشنهادهای دریافتی خود را نیز می‌توانید مشاهده و پاسخ دهید.

لطفاً گزینه مورد نظر را انتخاب کنید:"""
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=diplomacy_menu()
            )
        
        # ========== معادن و مزارع ==========
        elif call.data == "mines_farms":
            player = execute_query('''
                SELECT mine_gold_level, mine_iron_level, mine_stone_level,
                       farm_level, barracks_level, country,
                       gold, iron, stone, food, wood
                FROM players WHERE user_id = ?
            ''', (user_id,), fetchone=True)
            
            if player:
                mine_gold, mine_iron, mine_stone, farm, barracks, country, gold, iron, stone, food, wood = player
                
                production = calculate_daily_production(user_id)
                
                text = f"""⛏️ **معادن و مزارع{' - ' + country if country else ''}**

🏭 **سطح سازه‌های شما:**
💰 معدن طلا: سطح {mine_gold} (تولید: {production['gold'] if production else 0}/روز)
⚒️ معدن آهن: سطح {mine_iron} (تولید: {production['iron'] if production else 0}/روز)
🪨 معدن سنگ: سطح {mine_stone} (تولید: {production['stone'] if production else 0}/روز)
🌾 مزرعه غذا: سطح {farm} (تولید: {production['food'] if production else 0}/روز)
🏗️ کارخانه سرباز: سطح {barracks}

📦 **منابع ذخیره شده:**
• طلا: {gold}
• آهن: {iron}
• سنگ: {stone}
• غذا: {food}
• چوب: {wood}

💡 برای ارتقاء سازه‌ها یا جمع‌آوری منابع گزینه مورد نظر را انتخاب کنید:"""
            else:
                text = "⚠️ شما هنوز کشوری ندارید!"
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=mines_menu()
            )
        
        # ========== جمع‌آوری منابع ==========
        elif call.data == "collect_resources":
            production = calculate_daily_production(user_id)
            
            if production:
                # افزودن منابع
                execute_query('''
                    UPDATE players 
                    SET gold = gold + ?, 
                        iron = iron + ?, 
                        stone = stone + ?, 
                        food = food + ?,
                        wood = wood + ?,
                        last_active = ?
                    WHERE user_id = ?
                ''', (
                    production['gold'],
                    production['iron'],
                    production['stone'],
                    production['food'],
                    production['wood'],
                    datetime.now(),
                    user_id
                ), commit=True)
                
                text = f"""📦 **منابع جمع‌آوری شد!**

💰 طلا: +{production['gold']}
⚒️ آهن: +{production['iron']}
🪨 سنگ: +{production['stone']}
🍖 غذا: +{production['food']}
🌲 چوب: +{production['wood']}

منابع به حساب شما اضافه شدند."""
            else:
                text = "⚠️ خطا در محاسبه تولید!"
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=mines_menu()
            )
        
        # ========== راهنما ==========
        elif call.data == "help":
            text = """ℹ️ **راهنمای بازی جنگ جهانی باستان**

🎮 **چگونه بازی کنیم؟**
1. با دستور /start بازی را شروع کنید
2. اگر مالک هستید، بازیکنان جدید اضافه کنید
3. یک کشور انتخاب کنید و آن را مدیریت کنید
4. ارتش بسازید و معادن را توسعه دهید
5. با دیگر کشورها دیپلماسی کنید
6. برای فتح جهان بجنگید!

⚔️ **بخش‌های اصلی:**
• **ارتش:** ۵ نوع سرباز مختلف
• **دفاع:** دیوار، برج، دروازه
• **دیپلماسی:** صلح، جنگ، اتحاد، تجارت
• **معادن:** طلا، آهن، سنگ، غذا
• **مزرعه:** تولید غذا

📞 **پشتیبانی:** @amele55"""
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=main_menu(user_id)
            )
        
        # ========== افزودن بازیکن (مالک) ==========
        elif call.data == "add_player":
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "⛔ دسترسی ممنوع!")
                return
            
            # نمایش کشورهای آزاد
            countries = execute_query('SELECT name FROM countries WHERE controller = "AI"', fetchall=True)
            
            if not countries:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="⚠️ هیچ کشور آزادی وجود ندارد!",
                    reply_markup=main_menu(user_id)
                )
                return
            
            keyboard = InlineKeyboardMarkup()
            for country in countries:
                keyboard.row(InlineKeyboardButton(
                    f"🏛️ {country[0]}",
                    callback_data=f"select_{country[0]}"
                ))
            keyboard.row(InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu"))
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="🏛️ انتخاب کشور برای بازیکن جدید:\n\nکشورهای آزاد:",
                reply_markup=keyboard
            )
        
        # ========== انتخاب کشور برای بازیکن جدید ==========
        elif call.data.startswith("select_"):
            if user_id != OWNER_ID:
                return
            
            country_name = call.data.replace("select_", "")
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"کشور '{country_name}' انتخاب شد.\n\nلطفاً آیدی عددی کاربر را ارسال کنید:"
            )
            bot.register_next_step_handler(call.message, lambda m: add_player_step(m, country_name))
        
        # ========== شروع فصل ==========
        elif call.data == "start_season":
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "⛔ دسترسی ممنوع!")
                return
            
            try:
                if CHANNEL_ID:
                    bot.send_message(
                        CHANNEL_ID,
                        "🎉 **شروع فصل جدید جنگ‌های باستان!**\n\n"
                        "جهان باستان زنده شد! کشورها برای فتح جهان آماده می‌شوند...\n\n"
                        "ساخته شده توسط @amele55\n"
                        "ورژن 3.0 ربات"
                    )
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="✅ فصل جدید با موفقیت شروع شد!",
                    reply_markup=main_menu(user_id)
                )
            except Exception as e:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"❌ خطا در شروع فصل: {str(e)}",
                    reply_markup=main_menu(user_id)
                )
        
        # ========== ریست بازی ==========
        elif call.data == "reset_game":
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "⛔ دسترسی ممنوع!")
                return
            
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton("✅ بله، ریست کن", callback_data="confirm_reset"),
                InlineKeyboardButton("❌ خیر، لغو", callback_data="main_menu")
            )
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="⚠️ **هشدار: ریست کامل بازی**\n\nآیا مطمئن هستید؟\nهمه داده‌ها پاک می‌شوند!",
                reply_markup=keyboard
            )
        
        elif call.data == "confirm_reset":
            if user_id != OWNER_ID:
                return
            
            try:
                # ریست بازیکنان
                execute_query('''
                    UPDATE players 
                    SET country = NULL, 
                        gold = 1000, iron = 500, stone = 500, food = 1000, wood = 500,
                        army_infantry = 50, army_archer = 30, army_cavalry = 20,
                        army_spearman = 40, army_thief = 10,
                        defense_wall = 50, defense_tower = 20, defense_gate = 30,
                        mine_gold_level = 1, mine_iron_level = 1, mine_stone_level = 1,
                        farm_level = 1, barracks_level = 1
                ''', commit=True)
                
                # ریست کشورها
                execute_query('UPDATE countries SET controller = "AI", player_id = NULL', commit=True)
                
                # پاک کردن جدول‌های دیگر
                execute_query('DELETE FROM battles', commit=True)
                execute_query('DELETE FROM diplomacy', commit=True)
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="✅ بازی با موفقیت ریست شد!\nهمه کشورها آزاد شدند.",
                    reply_markup=main_menu(user_id)
                )
            except Exception as e:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"❌ خطا در ریست بازی: {str(e)}",
                    reply_markup=main_menu(user_id)
                )
        
        # ========== سایر دکمه‌ها ==========
        elif call.data in ["army_infantry", "army_archer", "army_cavalry", "army_spearman", "army_thief",
                          "attack_country", "defend_borders", "peace_request", "declare_war", 
                          "request_alliance", "trade_offer", "view_diplomacy_offers",
                          "mine_gold", "mine_iron", "mine_stone", "farm_food", "barracks"]:
            
            # برای سادگی، فعلاً پیام در حال توسعه نشان می‌دهیم
            action_names = {
                "army_infantry": "👮 پیاده نظام",
                "army_archer": "🏹 کمانداران",
                "army_cavalry": "🐎 سوارهنظام",
                "army_spearman": "🗡️ نیزه‌داران",
                "army_thief": "👤 دزدان",
                "attack_country": "⚔️ حمله به کشور",
                "defend_borders": "🏰 دفاع از مرز",
                "peace_request": "🕊️ درخواست صلح",
                "declare_war": "⚔️ اعلام جنگ",
                "request_alliance": "🤝 درخواست اتحاد",
                "trade_offer": "💰 پیشنهاد تجارت",
                "view_diplomacy_offers": "📜 مشاهده پیشنهادها",
                "mine_gold": "💰 معدن طلا",
                "mine_iron": "⚒️ معدن آهن",
                "mine_stone": "🪨 معدن سنگ",
                "farm_food": "🌾 مزرعه غذا",
                "barracks": "🏗️ کارخانه سرباز"
            }
            
            action_name = action_names.get(call.data, call.data)
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"🛠️ **{action_name}**\n\nاین بخش به زودی فعال خواهد شد!\nدر حال حاضر می‌توانید از سایر بخش‌ها استفاده کنید.",
                reply_markup=main_menu(user_id)
            )
        
        else:
            bot.answer_callback_query(call.id, "⚠️ این دکمه هنوز فعال نشده است!")
            
    except Exception as e:
        logger.error(f"خطا در هندلر کالبک: {e}")
        bot.answer_callback_query(call.id, "⚠️ خطایی رخ داد! لطفاً دوباره تلاش کنید.")

def add_player_step(message, country_name):
    """افزودن بازیکن جدید"""
    user_id = message.from_user.id
    
    if user_id != OWNER_ID:
        bot.reply_to(message, "⛔ دسترسی ممنوع!")
        return
    
    try:
        new_user_id = int(message.text)
        
        # بررسی اینکه کشور آزاد است
        country = execute_query('SELECT controller FROM countries WHERE name = ?', (country_name,), fetchone=True)
        
        if not country or country[0] != "AI":
            bot.reply_to(message, "❌ این کشور قبلاً اشغال شده است!")
            return
        
        # اختصاص کشور به بازیکن
        execute_query('UPDATE countries SET controller = "HUMAN", player_id = ? WHERE name = ?',
                     (new_user_id, country_name), commit=True)
        
        # به‌روزرسانی بازیکن
        execute_query('UPDATE players SET country = ? WHERE user_id = ?', (country_name, new_user_id), commit=True)
        
        # اگر بازیکن وجود ندارد، ایجاد کن
        if execute_query('SELECT COUNT(*) FROM players WHERE user_id = ?', (new_user_id,), fetchone=True)[0] == 0:
            execute_query('INSERT INTO players (user_id, country, join_date, last_active) VALUES (?, ?, ?, ?)',
                         (new_user_id, country_name, datetime.now(), datetime.now()), commit=True)
        
        # اطلاع به مالک
        bot.reply_to(
            message,
            f"✅ بازیکن با آیدی {new_user_id} به کشور '{country_name}' اضافه شد!"
        )
        
        # اطلاع به بازیکن جدید
        try:
            bot.send_message(
                new_user_id,
                f"""🎉 **شما به بازی جنگ جهانی باستان اضافه شدید!**

🏛️ کشور شما: {country_name}

برای شروع بازی /start را بزنید."""
            )
        except:
            bot.reply_to(message, f"⚠️ نتوانستم به کاربر {new_user_id} پیام بدم.")
            
    except ValueError:
        bot.reply_to(message, "⚠️ لطفاً یک آیدی عددی معتبر وارد کنید!")
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

# ========== Webhook برای Render ==========
@app.route('/', methods=['GET'])
def index():
    """صفحه اصلی"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ancient War Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                padding: 30px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
            }
            h1 {
                text-align: center;
                margin-bottom: 30px;
                font-size: 2.5em;
            }
            .status {
                background: rgba(255, 255, 255, 0.2);
                padding: 15px;
                border-radius: 10px;
                margin: 15px 0;
            }
            .btn {
                display: inline-block;
                background: white;
                color: #667eea;
                padding: 10px 20px;
                margin: 10px;
                border-radius: 5px;
                text-decoration: none;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏛️ Ancient War Bot</h1>
            
            <div class="status">
                <h2>🤖 وضعیت ربات</h2>
                <p>✅ ربات فعال و آنلاین است</p>
                <p>🔧 ورژن: 3.0 (Render Optimized)</p>
                <p>👨‍💻 سازنده: @amele55</p>
            </div>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="https://t.me/''' + BOT_USERNAME.replace('@', '') + '''" class="btn" target="_blank">
                    🚀 شروع بازی در تلگرام
                </a>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook برای تلگرام"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Bad Request', 400

@app.route('/health', methods=['GET'])
def health_check():
    """بررسی سلامت سرویس"""
    return jsonify({
        'status': 'healthy',
        'service': 'Ancient War Bot',
        'version': '3.0',
        'timestamp': datetime.now().isoformat()
    }), 200

# ========== راه‌اندازی ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    logger.info("=" * 50)
    logger.info("🏛️ Ancient War Bot v3.0")
    logger.info("=" * 50)
    logger.info(f"👑 مالک: {OWNER_ID}")
    logger.info(f"🤖 ربات: {BOT_USERNAME}")
    logger.info(f"🌐 پورت: {port}")
    logger.info("=" * 50)
    
    # تنظیم Webhook روی Render
    if 'RENDER' in os.environ or WEBHOOK_URL:
        logger.info("🚀 راه‌اندازی در حالت Production (Webhook)")
        
        # حذف Webhook قبلی و تنظیم جدید
        bot.remove_webhook()
        
        # ساخت آدرس Webhook
        if WEBHOOK_URL:
            webhook_url = f"{WEBHOOK_URL}/webhook"
        else:
            # اگر WEBHOOK_URL تنظیم نشده، از متغیرهای Render استفاده کن
            import os
            render_external_url = os.environ.get('RENDER_EXTERNAL_URL')
            if render_external_url:
                webhook_url = f"{render_external_url}/webhook"
            else:
                webhook_url = None
        
        if webhook_url:
            bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook تنظیم شد: {webhook_url}")
        else:
            logger.warning("⚠️ آدرس Webhook تنظیم نشده!")
        
        # اجرای Flask
        app.run(host='0.0.0.0', port=port)
    else:
        # حالت Development (Polling)
        logger.info("🔧 راه‌اندازی در حالت Development (Polling)")
        bot.remove_webhook()
        bot.polling(none_stop=True)
