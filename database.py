import sqlite3
import os
from datetime import datetime
from config import COUNTRIES

DB_PATH = 'game.db'

def init_db():
    """Initialize database with all required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Players table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            country_id INTEGER,
            is_owner BOOLEAN DEFAULT FALSE,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (country_id) REFERENCES countries(id)
        )
    ''')
    
    # Countries table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS countries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            is_ai_controlled BOOLEAN DEFAULT TRUE,
            unique_bonus TEXT NOT NULL,
            bonus_description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Army table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS army (
            country_id INTEGER PRIMARY KEY,
            level INTEGER DEFAULT 1,
            attack_power INTEGER DEFAULT 50,
            defense INTEGER DEFAULT 50,
            speed INTEGER DEFAULT 50,
            last_upgrade TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (country_id) REFERENCES countries(id)
        )
    ''')
    
    # Resources table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resources (
            country_id INTEGER PRIMARY KEY,
            gold INTEGER DEFAULT 1000,
            iron INTEGER DEFAULT 500,
            stone INTEGER DEFAULT 500,
            food INTEGER DEFAULT 1500,
            last_collected TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (country_id) REFERENCES countries(id)
        )
    ''')
    
    # Alliances table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alliances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country1_id INTEGER NOT NULL,
            country2_id INTEGER NOT NULL,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_date TIMESTAMP,
            broken_by INTEGER,  -- country_id that broke the alliance
            FOREIGN KEY (country1_id) REFERENCES countries(id),
            FOREIGN KEY (country2_id) REFERENCES countries(id),
            FOREIGN KEY (broken_by) REFERENCES countries(id),
            UNIQUE(country1_id, country2_id)
        )
    ''')
    
    # Events table (for news channel)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,  -- 'war', 'alliance', 'betrayal', 'season_start', 'season_end', 'ai_action'
            description TEXT NOT NULL,
            country1_id INTEGER,
            country2_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            season_id INTEGER,
            FOREIGN KEY (country1_id) REFERENCES countries(id),
            FOREIGN KEY (country2_id) REFERENCES countries(id)
        )
    ''')
    
    # Seasons table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            winner_country_id INTEGER,
            winner_player_id INTEGER,
            is_active BOOLEAN DEFAULT TRUE,
            FOREIGN KEY (winner_country_id) REFERENCES countries(id),
            FOREIGN KEY (winner_player_id) REFERENCES players(id)
        )
    ''')
    
    # Insert default countries if not exists
    cursor.execute('SELECT COUNT(*) FROM countries')
    if cursor.fetchone()[0] == 0:
        for country in COUNTRIES:
            cursor.execute('''
                INSERT INTO countries (name, is_ai_controlled, unique_bonus, bonus_description)
                VALUES (?, ?, ?, ?)
            ''', (country['name'], True, country['bonus'], country['bonus_desc']))
    
    # Insert owner player if not exists
    cursor.execute('SELECT COUNT(*) FROM players WHERE telegram_id = ?', (8588773170,))
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO players (telegram_id, username, is_owner)
            VALUES (?, ?, ?)
        ''', (8588773170, 'BotOwner', True))
    
    # Initialize army and resources for all countries
    cursor.execute('SELECT id FROM countries')
    country_ids = [row[0] for row in cursor.fetchall()]
    
    for country_id in country_ids:
        # Army
        cursor.execute('SELECT COUNT(*) FROM army WHERE country_id = ?', (country_id,))
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO army (country_id, level, attack_power, defense, speed)
                VALUES (?, 1, 50, 50, 50)
            ''', (country_id,))
        
        # Resources
        cursor.execute('SELECT COUNT(*) FROM resources WHERE country_id = ?', (country_id,))
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO resources (country_id, gold, iron, stone, food)
                VALUES (?, 1000, 500, 500, 1500)
            ''', (country_id,))
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get a database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Initialize DB on import
if not os.path.exists(DB_PATH):
    init_db()