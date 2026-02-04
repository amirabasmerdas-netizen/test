import random
import math
from datetime import datetime, timedelta
from database import get_db_connection
from config import (
    RESOURCE_PRODUCTION, ADVISOR_TIP_INTERVAL_HOURS, 
    AI_ACTION_INTERVAL_MINUTES, MAX_ARMY_LEVEL, ARMY_UPGRADE_COST
)

class GameLogic:
    """Core game mechanics including AI behavior and advisor logic"""
    
    @staticmethod
    def collect_resources():
        """Periodically collect resources for all countries"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all countries with their last collection time
        cursor.execute('''
            SELECT r.country_id, r.last_collected, 
                   r.gold, r.iron, r.stone, r.food,
                   c.is_ai_controlled
            FROM resources r
            JOIN countries c ON r.country_id = c.id
        ''')
        countries = cursor.fetchall()
        
        now = datetime.now()
        updated_countries = []
        
        for country in countries:
            last_collected = datetime.strptime(country['last_collected'], '%Y-%m-%d %H:%M:%S')
            hours_passed = (now - last_collected).total_seconds() / 3600
            
            if hours_passed >= 1:  # Collect resources every hour
                # Calculate production with AI bonus (AI collects 1.2x resources)
                multiplier = 1.2 if country['is_ai_controlled'] else 1.0
                
                new_gold = country['gold'] + int(RESOURCE_PRODUCTION['gold'] * hours_passed * multiplier)
                new_iron = country['iron'] + int(RESOURCE_PRODUCTION['iron'] * hours_passed * multiplier)
                new_stone = country['stone'] + int(RESOURCE_PRODUCTION['stone'] * hours_passed * multiplier)
                new_food = country['food'] + int(RESOURCE_PRODUCTION['food'] * hours_passed * multiplier)
                
                # Cap resources to prevent infinite growth
                new_gold = min(new_gold, 1000000)
                new_iron = min(new_iron, 500000)
                new_stone = min(new_stone, 500000)
                new_food = min(new_food, 2000000)
                
                cursor.execute('''
                    UPDATE resources 
                    SET gold = ?, iron = ?, stone = ?, food = ?, last_collected = ?
                    WHERE country_id = ?
                ''', (new_gold, new_iron, new_stone, new_food, now, country['country_id']))
                
                updated_countries.append(country['country_id'])
        
        conn.commit()
        conn.close()
        return updated_countries
    
    @staticmethod
    def ai_decision_maker():
        """AI makes strategic decisions: upgrade army, form alliances, declare war"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all AI-controlled countries with their stats
        cursor.execute('''
            SELECT c.id as country_id, c.name, c.unique_bonus,
                   a.level, a.attack_power, a.defense,
                   r.gold, r.iron, r.stone, r.food
            FROM countries c
            JOIN army a ON c.id = a.country_id
            JOIN resources r ON c.id = r.country_id
            WHERE c.is_ai_controlled = 1
        ''')
        ai_countries = cursor.fetchall()
        
        actions_taken = []
        
        for ai in ai_countries:
            # 1. Decide whether to upgrade army (30% chance if resources allow)
            if ai['level'] < MAX_ARMY_LEVEL and random.random() < 0.3:
                upgrade_cost = ARMY_UPGRADE_COST.get(ai['level'] + 1, {})
                can_afford = (
                    ai['gold'] >= upgrade_cost.get('gold', 0) and
                    ai['iron'] >= upgrade_cost.get('iron', 0) and
                    ai['stone'] >= upgrade_cost.get('stone', 0) and
                    ai['food'] >= upgrade_cost.get('food', 0)
                )
                
                if can_afford:
                    GameLogic.upgrade_army(ai['country_id'], conn)
                    actions_taken.append({
                        'type': 'army_upgrade',
                        'country': ai['name'],
                        'level': ai['level'] + 1
                    })
                    continue  # Only one action per AI per cycle
            
            # 2. Evaluate diplomatic options (40% chance)
            if random.random() < 0.4:
                # Get potential targets (not already at war or allied)
                cursor.execute('''
                    SELECT c.id, c.name, c.is_ai_controlled,
                           a.level as enemy_level, r.gold as enemy_gold
                    FROM countries c
                    LEFT JOIN alliances al ON (al.country1_id = ? AND al.country2_id = c.id AND al.end_date IS NULL)
                                      OR (al.country2_id = ? AND al.country1_id = c.id AND al.end_date IS NULL)
                    JOIN army a ON c.id = a.country_id
                    JOIN resources r ON c.id = r.country_id
                    WHERE c.id != ? AND al.id IS NULL
                    ORDER BY RANDOM() LIMIT 5
                ''', (ai['country_id'], ai['country_id'], ai['country_id']))
                targets = cursor.fetchall()
                
                if targets:
                    # Choose target based on strategy
                    target = random.choice(targets)
                    
                    # If target is weak and AI is strong, attack (60% chance)
                    if ai['attack_power'] > target['enemy_level'] * 60 and random.random() < 0.6:
                        GameLogic.declare_war(ai['country_id'], target['id'], conn)
                        actions_taken.append({
                            'type': 'war_declared',
                            'attacker': ai['name'],
                            'defender': target['name']
                        })
                    # If target is strong, propose alliance (40% chance)
                    elif random.random() < 0.4:
                        GameLogic.propose_alliance(ai['country_id'], target['id'], conn)
                        actions_taken.append({
                            'type': 'alliance_proposed',
                            'country1': ai['name'],
                            'country2': target['name']
                        })
                    # Otherwise send tribute to stronger nation (20% chance)
                    elif target['enemy_gold'] > ai['gold'] * 1.5 and random.random() < 0.2:
                        if ai['gold'] >= 500:
                            GameLogic.send_tribute(ai['country_id'], target['id'], 500, conn)
                            actions_taken.append({
                                'type': 'tribute_sent',
                                'sender': ai['name'],
                                'receiver': target['name']
                            })
        
        conn.commit()
        conn.close()
        return actions_taken
    
    @staticmethod
    def advisor_generate_tips(country_id):
        """Generate strategic tips for human players based on their situation"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get player country data
        cursor.execute('''
            SELECT p.telegram_id, c.name as country_name, c.unique_bonus,
                   a.level, a.attack_power, a.defense, a.speed,
                   r.gold, r.iron, r.stone, r.food,
                   (SELECT COUNT(*) FROM alliances al 
                    WHERE (al.country1_id = c.id OR al.country2_id = c.id) 
                    AND al.end_date IS NULL) as alliance_count
            FROM players p
            JOIN countries c ON p.country_id = c.id
            JOIN army a ON c.id = a.country_id
            JOIN resources r ON c.id = r.country_id
            WHERE p.country_id = ? AND p.telegram_id != ?
        ''', (country_id, 8588773170))  # Exclude owner
        
        player_data = cursor.fetchone()
        if not player_data:
            conn.close()
            return None
        
        tips = []
        data = dict(player_data)
        
        # Resource deficiency warnings
        if data['food'] < 500:
            tips.append(f"⚠️ Critical food shortage ({data['food']} units)! Increase food production or risk army desertion.")
        elif data['food'] < 1000:
            tips.append(f"🌾 Low food reserves ({data['food']} units). Consider focusing on food production.")
        
        if data['gold'] < 300:
            tips.append(f"💰 Treasury running low ({data['gold']} gold). Secure more income sources.")
        
        # Army strength analysis
        avg_army_level = cursor.execute('SELECT AVG(level) FROM army').fetchone()[0] or 1
        if data['level'] < avg_army_level - 1:
            tips.append(f"⚔️ Your army (Level {data['level']}) is weaker than regional average (Level {avg_army_level:.1f}). Consider upgrading soon.")
        elif data['level'] > avg_army_level + 1:
            tips.append(f"🛡️ Your army (Level {data['level']}) is stronger than neighbors. Perfect time to expand your territory!")
        
        # Alliance advice
        if data['alliance_count'] == 0:
            tips.append("🤝 You have no alliances. Forming strategic partnerships could protect you from coordinated attacks.")
        elif data['alliance_count'] >= 3:
            tips.append(f"👑 You have {data['alliance_count']} active alliances. Be cautious of overextension and potential betrayal risks.")
        
        # Unique bonus reminder
        bonus_tips = {
            'cavalry_speed': "🐎 Remember your Persian cavalry speed bonus when planning rapid strikes!",
            'fortress_defense': "🏰 Your Roman fortress defense excels in holding cities - let enemies come to you!",
            'nile_bounty': "🌾 Egypt's Nile bounty ensures stable food supply - focus resources on army expansion.",
            'great_wall': "🧱 China's Great Wall bonus makes border defense highly effective against invasions.",
            'phalanx': "🛡️ Greek phalanx formation gives infantry advantage - perfect for holding defensive lines.",
            'hanging_gardens': "🌿 Babylon's Hanging Gardens boost all resource production - economic powerhouse!",
            'siege_masters': "💥 Assyrian siege masters excel at taking fortified positions - target enemy capitals!",
            'naval_supremacy': "⚓ Carthage dominates seas - control coastal regions and trade routes for advantage.",
            'elephant_warfare': "🐘 Indian war elephants crush infantry formations - devastating in open battles.",
            'companion_cavalry': "🐎 Macedonian companion cavalry delivers devastating charges - perfect for breaking enemy lines.",
            'iron_masters': "⚒️ Hittite iron mastery ensures superior weapons - maintain technological edge.",
            'trade_network': "💰 Phoenician trade networks generate wealth - fund larger armies than neighbors.",
        }
        
        if data['unique_bonus'] in bonus_tips:
            tips.append(bonus_tips[data['unique_bonus']])
        
        # War risk assessment
        cursor.execute('''
            SELECT COUNT(*) as hostile_count
            FROM events e
            WHERE e.event_type = 'war' 
              AND e.country2_id = ? 
              AND e.timestamp > datetime('now', '-7 days')
        ''', (country_id,))
        recent_attacks = cursor.fetchone()[0]
        
        if recent_attacks > 0:
            tips.append(f"⚔️ You've been attacked {recent_attacks} times recently. Strengthen defenses or seek powerful allies!")
        
        conn.close()
        
        if tips:
            # Return one random tip to avoid overwhelming player
            return random.choice(tips)
        return None
    
    @staticmethod
    def upgrade_army(country_id, conn=None):
        """Upgrade army level if resources allow"""
        close_conn = False
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        
        cursor = conn.cursor()
        
        # Get current army and resources
        cursor.execute('''
            SELECT a.level, r.gold, r.iron, r.stone, r.food
            FROM army a
            JOIN resources r ON a.country_id = r.country_id
            WHERE a.country_id = ?
        ''', (country_id,))
        army_data = cursor.fetchone()
        
        if not army_data or army_data['level'] >= MAX_ARMY_LEVEL:
            if close_conn:
                conn.close()
            return False
        
        current_level = army_data['level']
        upgrade_cost = ARMY_UPGRADE_COST.get(current_level + 1, {})
        
        # Check if can afford upgrade
        if (army_data['gold'] < upgrade_cost.get('gold', 0) or
            army_data['iron'] < upgrade_cost.get('iron', 0) or
            army_data['stone'] < upgrade_cost.get('stone', 0) or
            army_data['food'] < upgrade_cost.get('food', 0)):
            if close_conn:
                conn.close()
            return False
        
        # Calculate new stats with bonus progression
        new_level = current_level + 1
        base_attack = 50 + (new_level - 1) * 25
        base_defense = 50 + (new_level - 1) * 25
        base_speed = 50 + (new_level - 1) * 15
        
        # Apply country-specific bonuses
        cursor.execute('SELECT unique_bonus FROM countries WHERE id = ?', (country_id,))
        bonus = cursor.fetchone()['unique_bonus']
        
        if bonus == 'cavalry_speed':
            base_speed = int(base_speed * 1.2)
        elif bonus == 'fortress_defense':
            base_defense = int(base_defense * 1.25)
        elif bonus == 'phalanx':
            base_attack = int(base_attack * 1.2)
        elif bonus == 'siege_masters':
            base_attack = int(base_attack * 1.25)
        elif bonus == 'elephant_warfare':
            base_attack = int(base_attack * 1.2)
        elif bonus == 'companion_cavalry':
            base_attack = int(base_attack * 1.25)
            base_speed = int(base_speed * 1.15)
        
        # Deduct resources
        cursor.execute('''
            UPDATE resources
            SET gold = gold - ?, iron = iron - ?, stone = stone - ?, food = food - ?
            WHERE country_id = ?
        ''', (
            upgrade_cost['gold'], upgrade_cost['iron'], 
            upgrade_cost['stone'], upgrade_cost['food'], country_id
        ))
        
        # Upgrade army
        cursor.execute('''
            UPDATE army
            SET level = ?, attack_power = ?, defense = ?, speed = ?, last_upgrade = CURRENT_TIMESTAMP
            WHERE country_id = ?
        ''', (new_level, base_attack, base_defense, base_speed, country_id))
        
        # Log event
        cursor.execute('''
            INSERT INTO events (event_type, description, country1_id, season_id)
            VALUES (?, ?, ?, (SELECT id FROM seasons WHERE is_active = 1 LIMIT 1))
        ''', (
            'army_upgrade',
            f"Army upgraded to Level {new_level}",
            country_id
        ))
        
        if close_conn:
            conn.commit()
            conn.close()
        
        return True
    
    @staticmethod
    def declare_war(attacker_id, defender_id, conn=None):
        """Declare war between two countries"""
        close_conn = False
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        
        cursor = conn.cursor()
        
        # Check if already at war or allied
        cursor.execute('''
            SELECT id FROM alliances 
            WHERE ((country1_id = ? AND country2_id = ?) OR (country1_id = ? AND country2_id = ?))
            AND end_date IS NULL
        ''', (attacker_id, defender_id, defender_id, attacker_id))
        
        if cursor.fetchone():
            if close_conn:
                conn.close()
            return False, "Cannot declare war on an ally"
        
        # Get army strengths
        cursor.execute('SELECT attack_power FROM army WHERE country_id = ?', (attacker_id,))
        attacker_power = cursor.fetchone()['attack_power']
        
        cursor.execute('SELECT defense FROM army WHERE country_id = ?', (defender_id,))
        defender_power = cursor.fetchone()['defense']
        
        # Determine outcome (simplified combat)
        attacker_strength = attacker_power * random.uniform(0.9, 1.1)
        defender_strength = defender_power * random.uniform(0.9, 1.1)
        
        if attacker_strength > defender_strength * 1.3:  # Decisive victory
            outcome = "decisive_victory"
            result_text = "decisively defeated"
        elif attacker_strength > defender_strength * 0.9:  # Victory
            outcome = "victory"
            result_text = "defeated"
        elif attacker_strength > defender_strength * 0.7:  # Pyrrhic victory
            outcome = "pyrrhic_victory"
            result_text = "barely defeated"
        else:  # Defeat
            outcome = "defeat"
            result_text = "was defeated by"
        
        # Get country names
        cursor.execute('SELECT name FROM countries WHERE id = ?', (attacker_id,))
        attacker_name = cursor.fetchone()['name']
        
        cursor.execute('SELECT name FROM countries WHERE id = ?', (defender_id,))
        defender_name = cursor.fetchone()['name']
        
        # Log war event
        description = f"{attacker_name} attacked {defender_name} and {result_text} them"
        cursor.execute('''
            INSERT INTO events (event_type, description, country1_id, country2_id, season_id)
            VALUES (?, ?, ?, ?, (SELECT id FROM seasons WHERE is_active = 1 LIMIT 1))
        ''', ('war', description, attacker_id, defender_id))
        
        # Break any existing alliances involving these countries
        cursor.execute('''
            UPDATE alliances
            SET end_date = CURRENT_TIMESTAMP, broken_by = ?
            WHERE ((country1_id = ? OR country2_id = ?) OR (country1_id = ? OR country2_id = ?))
            AND end_date IS NULL
        ''', (attacker_id, attacker_id, attacker_id, defender_id, defender_id))
        
        if close_conn:
            conn.commit()
            conn.close()
        
        return True, description
    
    @staticmethod
    def propose_alliance(country1_id, country2_id, conn=None):
        """Create an alliance between two countries"""
        close_conn = False
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        
        cursor = conn.cursor()
        
        # Check if already allied or at war recently
        cursor.execute('''
            SELECT id FROM alliances 
            WHERE ((country1_id = ? AND country2_id = ?) OR (country1_id = ? AND country2_id = ?))
            AND end_date IS NULL
        ''', (country1_id, country2_id, country2_id, country1_id))
        
        if cursor.fetchone():
            if close_conn:
                conn.close()
            return False, "Already allied"
        
        # Create alliance
        cursor.execute('''
            INSERT INTO alliances (country1_id, country2_id)
            VALUES (?, ?)
        ''', (country1_id, country2_id))
        
        # Get country names
        cursor.execute('SELECT name FROM countries WHERE id = ?', (country1_id,))
        country1_name = cursor.fetchone()['name']
        
        cursor.execute('SELECT name FROM countries WHERE id = ?', (country2_id,))
        country2_name = cursor.fetchone()['name']
        
        # Log event
        description = f"{country1_name} and {country2_name} formed an alliance"
        cursor.execute('''
            INSERT INTO events (event_type, description, country1_id, country2_id, season_id)
            VALUES (?, ?, ?, ?, (SELECT id FROM seasons WHERE is_active = 1 LIMIT 1))
        ''', ('alliance', description, country1_id, country2_id))
        
        if close_conn:
            conn.commit()
            conn.close()
        
        return True, description
    
    @staticmethod
    def send_tribute(sender_id, receiver_id, amount, conn=None):
        """Send gold tribute from one country to another"""
        close_conn = False
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        
        cursor = conn.cursor()
        
        # Check sender has enough gold
        cursor.execute('SELECT gold FROM resources WHERE country_id = ?', (sender_id,))
        if cursor.fetchone()['gold'] < amount:
            if close_conn:
                conn.close()
            return False, "Insufficient gold"
        
        # Transfer gold
        cursor.execute('''
            UPDATE resources 
            SET gold = gold - ? 
            WHERE country_id = ?
        ''', (amount, sender_id))
        
        cursor.execute('''
            UPDATE resources 
            SET gold = gold + ? 
            WHERE country_id = ?
        ''', (amount, receiver_id))
        
        # Get country names
        cursor.execute('SELECT name FROM countries WHERE id = ?', (sender_id,))
        sender_name = cursor.fetchone()['name']
        
        cursor.execute('SELECT name FROM countries WHERE id = ?', (receiver_id,))
        receiver_name = cursor.fetchone()['name']
        
        # Log event
        description = f"{sender_name} sent {amount} gold tribute to {receiver_name}"
        cursor.execute('''
            INSERT INTO events (event_type, description, country1_id, country2_id, season_id)
            VALUES (?, ?, ?, ?, (SELECT id FROM seasons WHERE is_active = 1 LIMIT 1))
        ''', ('tribute', description, sender_id, receiver_id))
        
        if close_conn:
            conn.commit()
            conn.close()
        
        return True, description
    
    @staticmethod
    def break_alliance(alliance_id, breaker_id, conn=None):
        """Break an existing alliance"""
        close_conn = False
        if conn is None:
            conn = get_db_connection()
            close_conn = True
        
        cursor = conn.cursor()
        
        # Get alliance details
        cursor.execute('''
            SELECT country1_id, country2_id 
            FROM alliances 
            WHERE id = ? AND end_date IS NULL
        ''', (alliance_id,))
        alliance = cursor.fetchone()
        
        if not alliance:
            if close_conn:
                conn.close()
            return False, "Alliance not found or already broken"
        
        # Break alliance
        cursor.execute('''
            UPDATE alliances
            SET end_date = CURRENT_TIMESTAMP, broken_by = ?
            WHERE id = ?
        ''', (breaker_id, alliance_id))
        
        # Get country names
        cursor.execute('SELECT name FROM countries WHERE id IN (?, ?)', 
                      (alliance['country1_id'], alliance['country2_id']))
        countries = [row['name'] for row in cursor.fetchall()]
        
        breaker_name = countries[0] if alliance['country1_id'] == breaker_id else countries[1]
        victim_name = countries[1] if alliance['country1_id'] == breaker_id else countries[0]
        
        # Log betrayal event
        description = f"{breaker_name} betrayed and broke alliance with {victim_name}"
        cursor.execute('''
            INSERT INTO events (event_type, description, country1_id, country2_id, season_id)
            VALUES (?, ?, ?, ?, (SELECT id FROM seasons WHERE is_active = 1 LIMIT 1))
        ''', ('betrayal', description, breaker_id, alliance['country1_id'] if alliance['country2_id'] == breaker_id else alliance['country2_id']))
        
        if close_conn:
            conn.commit()
            conn.close()
        
        return True, description
    
    @staticmethod
    def start_season():
        """Start a new season"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # End any active season
        cursor.execute('''
            UPDATE seasons 
            SET end_time = CURRENT_TIMESTAMP, is_active = FALSE 
            WHERE is_active = TRUE
        ''')
        
        # Create new season
        cursor.execute('''
            INSERT INTO seasons (start_time, is_active)
            VALUES (CURRENT_TIMESTAMP, TRUE)
        ''')
        
        season_id = cursor.lastrowid
        
        # Reset resources for all countries to starting values
        cursor.execute('''
            UPDATE resources 
            SET gold = 1000, iron = 500, stone = 500, food = 1500, last_collected = CURRENT_TIMESTAMP
        ''')
        
        # Reset army levels to 1 for all countries
        cursor.execute('''
            UPDATE army 
            SET level = 1, attack_power = 50, defense = 50, speed = 50, last_upgrade = CURRENT_TIMESTAMP
        ''')
        
        # Break all alliances
        cursor.execute('''
            UPDATE alliances 
            SET end_date = CURRENT_TIMESTAMP 
            WHERE end_date IS NULL
        ''')
        
        conn.commit()
        conn.close()
        
        return season_id
    
    @staticmethod
    def end_season():
        """End current season and determine winner (human player only)"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get active season
        cursor.execute('SELECT id FROM seasons WHERE is_active = TRUE LIMIT 1')
        season = cursor.fetchone()
        if not season:
            conn.close()
            return None, "No active season"
        
        season_id = season['id']
        
        # Find strongest human-controlled country by army power
        cursor.execute('''
            SELECT c.id as country_id, c.name, a.attack_power + a.defense as power, p.telegram_id
            FROM countries c
            JOIN army a ON c.id = a.country_id
            JOIN players p ON c.id = p.country_id
            WHERE c.is_ai_controlled = FALSE AND p.telegram_id != ?
            ORDER BY power DESC
            LIMIT 1
        ''', (8588773170,))  # Exclude owner
        
        winner = cursor.fetchone()
        
        # End season
        cursor.execute('''
            UPDATE seasons 
            SET end_time = CURRENT_TIMESTAMP, 
                is_active = FALSE,
                winner_country_id = ?,
                winner_player_id = (SELECT id FROM players WHERE country_id = ? LIMIT 1)
            WHERE id = ?
        ''', (winner['country_id'] if winner else None, winner['country_id'] if winner else None, season_id))
        
        conn.commit()
        conn.close()
        
        if winner:
            return winner['country_id'], winner['name'], winner['telegram_id']
        return None, "No human players participated", None
    
    @staticmethod
    def is_season_active():
        """Check if a season is currently active"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM seasons WHERE is_active = TRUE')
        active = cursor.fetchone()[0] > 0
        conn.close()
        return active
    
    @staticmethod
    def get_country_stats(country_id):
        """Get comprehensive stats for a country"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.name, c.is_ai_controlled, c.unique_bonus, c.bonus_description,
                   a.level, a.attack_power, a.defense, a.speed,
                   r.gold, r.iron, r.stone, r.food,
                   (SELECT COUNT(*) FROM alliances al 
                    WHERE (al.country1_id = c.id OR al.country2_id = c.id) 
                    AND al.end_date IS NULL) as alliance_count,
                   (SELECT COUNT(*) FROM events e 
                    WHERE e.country1_id = c.id AND e.event_type = 'war' 
                    AND e.timestamp > datetime('now', '-30 days')) as attacks_launched,
                   (SELECT COUNT(*) FROM events e 
                    WHERE e.country2_id = c.id AND e.event_type = 'war' 
                    AND e.timestamp > datetime('now', '-30 days')) as attacks_received
            FROM countries c
            JOIN army a ON c.id = a.country_id
            JOIN resources r ON c.id = r.country_id
            WHERE c.id = ?
        ''', (country_id,))
        
        stats = cursor.fetchone()
        conn.close()
        return dict(stats) if stats else None