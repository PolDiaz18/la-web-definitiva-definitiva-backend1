"""
=============================================================================
GAMIFICATION.PY — Sistema de Gamificación
=============================================================================
Gestiona:
  - XP (puntos de experiencia)
  - Niveles (Novato → Leyenda)
  - Rachas (streaks)
  - Logros (achievements)
  - Desafíos (challenges)

Filosofía:
  La gamificación NO es el objetivo. Es un MEDIO para mantener la motivación.
  Por eso los puntos y niveles refuerzan el comportamiento deseado
  (constancia, no perfección).
"""

from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from models import (
    User, Habit, HabitLog, Achievement, UserAchievement, 
    Challenge, UserChallenge, Quote
)
import random
import logging

logger = logging.getLogger("nexotime.gamification")


# =============================================================================
# ===================== SISTEMA DE NIVELES ====================================
# =============================================================================
# Cada nivel necesita más XP que el anterior (progresión exponencial suave).
# Fórmula: XP_necesario = nivel * 100
# Nivel 1 → 100 XP, Nivel 2 → 200 XP, Nivel 10 → 1000 XP...

LEVEL_TITLES = {
    1: "Novato",
    2: "Aprendiz",
    3: "Iniciado",
    5: "Constante",
    7: "Disciplinado",
    10: "Veterano",
    15: "Experto",
    20: "Maestro",
    25: "Gran Maestro",
    30: "Leyenda",
    40: "Mito",
    50: "Inmortal",
}


def get_level_title(level: int) -> str:
    """Devuelve el título correspondiente al nivel del usuario"""
    title = "Novato"
    for lvl, name in sorted(LEVEL_TITLES.items()):
        if level >= lvl:
            title = name
    return title


def xp_for_next_level(level: int) -> int:
    """XP necesario para subir del nivel actual al siguiente"""
    return level * 100


def calculate_level(total_xp: int) -> int:
    """Calcula el nivel basándose en el XP total acumulado"""
    level = 1
    xp_remaining = total_xp
    while xp_remaining >= xp_for_next_level(level):
        xp_remaining -= xp_for_next_level(level)
        level += 1
    return level


def get_level_info(user: User) -> dict:
    """Información completa del nivel del usuario"""
    level = user.level
    xp_needed = xp_for_next_level(level)
    
    # Calcular XP dentro del nivel actual
    xp_accumulated = 0
    for lvl in range(1, level):
        xp_accumulated += xp_for_next_level(lvl)
    xp_in_current_level = user.xp - xp_accumulated
    
    return {
        "level": level,
        "xp": user.xp,
        "xp_in_level": xp_in_current_level,
        "xp_next_level": xp_needed,
        "xp_progress": round((xp_in_current_level / xp_needed) * 100, 1) if xp_needed > 0 else 100,
        "title": get_level_title(level)
    }


# =============================================================================
# ===================== SISTEMA DE XP =========================================
# =============================================================================

# Puntos base por acción
XP_REWARDS = {
    "habit_complete": 10,        # Completar un hábito
    "all_habits_complete": 25,   # Completar TODOS los hábitos del día
    "routine_complete": 15,      # Completar una rutina
    "journal_entry": 10,         # Escribir en el diario
    "gratitude_entry": 10,       # Entrada de gratitud
    "mood_log": 5,               # Registrar mood
    "sleep_log": 5,              # Registrar sueño
    "exercise_log": 15,          # Registrar ejercicio
    "reflection_complete": 20,   # Completar reflexión semanal
    "task_complete": 10,         # Completar una tarea
    "pomodoro_complete": 10,     # Completar un pomodoro
    "challenge_complete": 50,    # Completar un desafío
}

# Multiplicadores de racha
STREAK_MULTIPLIERS = {
    7: 1.5,    # 7+ días → x1.5
    14: 1.75,  # 14+ días → x1.75
    30: 2.0,   # 30+ días → x2
    60: 2.5,   # 60+ días → x2.5
    100: 3.0,  # 100+ días → x3
}


def get_streak_multiplier(streak: int) -> float:
    """Devuelve el multiplicador de XP según la racha actual"""
    multiplier = 1.0
    for days, mult in sorted(STREAK_MULTIPLIERS.items()):
        if streak >= days:
            multiplier = mult
    return multiplier


def award_xp(db: Session, user: User, action: str, streak: int = 0) -> dict:
    """
    Otorga XP al usuario por una acción.
    
    Retorna:
      {
        "xp_earned": 15,
        "multiplier": 1.5,
        "total_xp": 15,
        "leveled_up": True,
        "new_level": 5,
        "new_title": "Constante"
      }
    """
    base_xp = XP_REWARDS.get(action, 0)
    if base_xp == 0:
        return {"xp_earned": 0}
    
    multiplier = get_streak_multiplier(streak) if streak > 0 else 1.0
    total_xp = int(base_xp * multiplier)
    
    old_level = user.level
    user.xp += total_xp
    new_level = calculate_level(user.xp)
    
    leveled_up = new_level > old_level
    if leveled_up:
        user.level = new_level
    
    db.commit()
    
    result = {
        "xp_earned": base_xp,
        "multiplier": multiplier,
        "total_xp": total_xp,
        "leveled_up": leveled_up,
    }
    
    if leveled_up:
        result["new_level"] = new_level
        result["new_title"] = get_level_title(new_level)
    
    return result


# =============================================================================
# ===================== SISTEMA DE RACHAS =====================================
# =============================================================================

def update_habit_streak(db: Session, habit: Habit, completed: bool, log_date: date):
    """
    Actualiza la racha de un hábito individual.
    
    Lógica:
      - Si completó hoy y ayer también → racha +1
      - Si completó hoy pero ayer no → racha = 1
      - Si no completó → racha = 0
    """
    if completed:
        # Buscar si completó ayer
        yesterday = log_date - timedelta(days=1)
        yesterday_log = db.query(HabitLog).filter(
            HabitLog.habit_id == habit.id,
            HabitLog.date == yesterday,
            HabitLog.completed == True
        ).first()
        
        if yesterday_log:
            habit.current_streak += 1
        else:
            habit.current_streak = 1
        
        # Actualizar mejor racha
        if habit.current_streak > habit.best_streak:
            habit.best_streak = habit.current_streak
    else:
        habit.current_streak = 0
    
    db.commit()


def update_global_streak(db: Session, user: User, log_date: date):
    """
    Actualiza la racha global del usuario.
    Se incrementa solo si TODOS los hábitos activos del día fueron completados.
    """
    # Obtener hábitos activos que aplican hoy
    active_habits = db.query(Habit).filter(
        Habit.user_id == user.id,
        Habit.active == True,
        Habit.archived == False
    ).all()
    
    if not active_habits:
        return
    
    # Verificar que todos tienen log completado para hoy
    all_completed = True
    for habit in active_habits:
        # Verificar si el hábito aplica hoy según su frecuencia
        if not habit_applies_today(habit, log_date):
            continue
        
        log = db.query(HabitLog).filter(
            HabitLog.habit_id == habit.id,
            HabitLog.date == log_date,
            HabitLog.completed == True
        ).first()
        
        if not log:
            all_completed = False
            break
    
    if all_completed:
        # Verificar si ayer también completó todo
        yesterday = log_date - timedelta(days=1)
        yesterday_all = check_all_completed(db, user, yesterday)
        
        if yesterday_all:
            user.global_streak += 1
        else:
            user.global_streak = 1
        
        if user.global_streak > user.best_global_streak:
            user.best_global_streak = user.global_streak
    
    db.commit()


def habit_applies_today(habit: Habit, check_date: date) -> bool:
    """Verifica si un hábito aplica en una fecha dada según su frecuencia"""
    if habit.frequency == "daily":
        return True
    
    if habit.frequency == "specific_days" and habit.specific_days:
        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        today_name = day_names[check_date.weekday()]
        return today_name in habit.specific_days
    
    if habit.frequency == "times_per_week":
        # Para "X veces por semana", siempre aplica (el usuario decide cuándo)
        return True
    
    return True


def check_all_completed(db: Session, user: User, check_date: date) -> bool:
    """Verifica si todos los hábitos del día fueron completados"""
    active_habits = db.query(Habit).filter(
        Habit.user_id == user.id,
        Habit.active == True,
        Habit.archived == False
    ).all()
    
    for habit in active_habits:
        if not habit_applies_today(habit, check_date):
            continue
        
        log = db.query(HabitLog).filter(
            HabitLog.habit_id == habit.id,
            HabitLog.date == check_date,
            HabitLog.completed == True
        ).first()
        
        if not log:
            return False
    
    return True


# =============================================================================
# ===================== SISTEMA DE LOGROS =====================================
# =============================================================================

# Definición de todos los logros disponibles
ACHIEVEMENTS_DEFINITIONS = [
    # ── Rachas ──
    {"code": "streak_3", "name": "Tres días seguidos 🌱", "description": "Completa todos tus hábitos 3 días seguidos", "icon": "🌱", "xp": 25},
    {"code": "streak_7", "name": "Semana de fuego 🔥", "description": "Completa todos tus hábitos 7 días seguidos", "icon": "🔥", "xp": 50},
    {"code": "streak_14", "name": "Dos semanas imparable 💪", "description": "14 días seguidos sin fallar", "icon": "💪", "xp": 100},
    {"code": "streak_30", "name": "Mes de acero 🛡️", "description": "30 días seguidos. Usted es de otro nivel.", "icon": "🛡️", "xp": 200},
    {"code": "streak_60", "name": "Disciplina de titanio ⚔️", "description": "60 días seguidos. Impresionante.", "icon": "⚔️", "xp": 400},
    {"code": "streak_100", "name": "Centenario 💎", "description": "100 días seguidos. Leyenda.", "icon": "💎", "xp": 750},
    {"code": "streak_365", "name": "Un año completo 👑", "description": "365 días seguidos. No hay palabras.", "icon": "👑", "xp": 2000},
    
    # ── Hábitos ──
    {"code": "first_habit", "name": "El primer paso 👣", "description": "Complete su primer hábito", "icon": "👣", "xp": 10},
    {"code": "habits_50", "name": "Medio centenar ✨", "description": "Complete 50 hábitos en total", "icon": "✨", "xp": 50},
    {"code": "habits_100", "name": "Centenar de logros 💯", "description": "Complete 100 hábitos en total", "icon": "💯", "xp": 100},
    {"code": "habits_500", "name": "Máquina de hábitos ⚙️", "description": "500 hábitos completados", "icon": "⚙️", "xp": 300},
    {"code": "habits_1000", "name": "Millar dorado 🏅", "description": "1000 hábitos completados", "icon": "🏅", "xp": 500},
    
    # ── Especiales ──
    {"code": "early_bird", "name": "Madrugador 🌅", "description": "Complete todos los hábitos antes de las 9:00", "icon": "🌅", "xp": 30},
    {"code": "night_owl", "name": "Búho nocturno 🦉", "description": "Complete la rutina de noche 7 días seguidos", "icon": "🦉", "xp": 30},
    {"code": "hydrated", "name": "Bien hidratado 💧", "description": "Alcance su objetivo de agua 7 días seguidos", "icon": "💧", "xp": 30},
    {"code": "journaler", "name": "Escritor nato ✍️", "description": "Escriba en su diario 7 días seguidos", "icon": "✍️", "xp": 30},
    {"code": "grateful", "name": "Alma agradecida 🙏", "description": "Complete la gratitud diaria 7 días seguidos", "icon": "🙏", "xp": 30},
    {"code": "reflective", "name": "Pensador profundo 🧠", "description": "Complete 4 reflexiones semanales", "icon": "🧠", "xp": 50},
    {"code": "pomodoro_master", "name": "Maestro del foco 🍅", "description": "Complete 50 pomodoros", "icon": "🍅", "xp": 75},
    
    # ── Niveles ──
    {"code": "level_5", "name": "Constante 🌟", "description": "Alcance el nivel 5", "icon": "🌟", "xp": 0},
    {"code": "level_10", "name": "Veterano ⭐", "description": "Alcance el nivel 10", "icon": "⭐", "xp": 0},
    {"code": "level_20", "name": "Maestro 🌠", "description": "Alcance el nivel 20", "icon": "🌠", "xp": 0},
    {"code": "level_50", "name": "Inmortal 💫", "description": "Alcance el nivel 50", "icon": "💫", "xp": 0},
    
    # ── Hitos de tiempo ──
    {"code": "week_1", "name": "Primera semana 📅", "description": "Lleva una semana usando NexoTime", "icon": "📅", "xp": 15},
    {"code": "month_1", "name": "Primer mes 🗓️", "description": "Lleva un mes usando NexoTime", "icon": "🗓️", "xp": 50},
    {"code": "month_6", "name": "Medio año 📆", "description": "6 meses con NexoTime", "icon": "📆", "xp": 200},
    {"code": "year_1", "name": "Aniversario 🎂", "description": "¡Un año con NexoTime!", "icon": "🎂", "xp": 500},
]


def seed_achievements(db: Session):
    """
    Inserta los logros en la BD si no existen.
    Se ejecuta al arrancar la aplicación.
    """
    for ach_def in ACHIEVEMENTS_DEFINITIONS:
        existing = db.query(Achievement).filter(Achievement.code == ach_def["code"]).first()
        if not existing:
            achievement = Achievement(
                code=ach_def["code"],
                name=ach_def["name"],
                description=ach_def["description"],
                icon=ach_def["icon"],
                xp_reward=ach_def["xp"]
            )
            db.add(achievement)
    db.commit()
    logger.info(f"✅ {len(ACHIEVEMENTS_DEFINITIONS)} logros verificados en BD")


def check_and_unlock_achievements(db: Session, user: User) -> list[Achievement]:
    """
    Verifica si el usuario ha desbloqueado algún logro nuevo.
    Retorna lista de logros recién desbloqueados.
    """
    newly_unlocked = []
    
    # Obtener logros ya desbloqueados
    unlocked_codes = set(
        ua.achievement.code for ua in 
        db.query(UserAchievement).filter(UserAchievement.user_id == user.id).all()
        if ua.achievement
    )
    
    # ── Verificar rachas ──
    streak_checks = {
        "streak_3": 3, "streak_7": 7, "streak_14": 14,
        "streak_30": 30, "streak_60": 60, "streak_100": 100, "streak_365": 365
    }
    for code, days in streak_checks.items():
        if code not in unlocked_codes and user.global_streak >= days:
            newly_unlocked.append(_unlock(db, user, code))
    
    # ── Verificar total de hábitos completados ──
    total_completed = db.query(HabitLog).filter(
        HabitLog.user_id == user.id,
        HabitLog.completed == True
    ).count()
    
    habit_checks = {
        "first_habit": 1, "habits_50": 50, "habits_100": 100,
        "habits_500": 500, "habits_1000": 1000
    }
    for code, count in habit_checks.items():
        if code not in unlocked_codes and total_completed >= count:
            newly_unlocked.append(_unlock(db, user, code))
    
    # ── Verificar niveles ──
    level_checks = {"level_5": 5, "level_10": 10, "level_20": 20, "level_50": 50}
    for code, lvl in level_checks.items():
        if code not in unlocked_codes and user.level >= lvl:
            newly_unlocked.append(_unlock(db, user, code))
    
    # ── Verificar hitos de tiempo ──
    days_since_signup = (datetime.utcnow() - user.created_at).days
    time_checks = {"week_1": 7, "month_1": 30, "month_6": 180, "year_1": 365}
    for code, days in time_checks.items():
        if code not in unlocked_codes and days_since_signup >= days:
            newly_unlocked.append(_unlock(db, user, code))
    
    return [a for a in newly_unlocked if a is not None]


def _unlock(db: Session, user: User, achievement_code: str) -> Achievement:
    """Desbloquea un logro para un usuario"""
    achievement = db.query(Achievement).filter(Achievement.code == achievement_code).first()
    if not achievement:
        return None
    
    # Verificar que no esté ya desbloqueado (doble check)
    existing = db.query(UserAchievement).filter(
        UserAchievement.user_id == user.id,
        UserAchievement.achievement_id == achievement.id
    ).first()
    if existing:
        return None
    
    ua = UserAchievement(user_id=user.id, achievement_id=achievement.id)
    db.add(ua)
    
    # Dar XP del logro
    if achievement.xp_reward > 0:
        user.xp += achievement.xp_reward
        user.level = calculate_level(user.xp)
    
    db.commit()
    logger.info(f"🏆 {user.name} desbloqueó: {achievement.name}")
    return achievement


# =============================================================================
# ===================== CITAS MOTIVACIONALES ==================================
# =============================================================================

DEFAULT_QUOTES = [
    ("La disciplina es el puente entre metas y logros.", "Jim Rohn"),
    ("No se trata de ser perfecto, se trata de ser constante.", None),
    ("Cada día es una nueva oportunidad para ser mejor que ayer.", None),
    ("Los hábitos son el interés compuesto de la mejora personal.", "James Clear"),
    ("La motivación te pone en marcha, la disciplina te mantiene en movimiento.", None),
    ("Usted no necesita ser extremo, solo necesita ser constante.", None),
    ("El éxito es la suma de pequeños esfuerzos repetidos día tras día.", "Robert Collier"),
    ("No cuente los días, haga que los días cuenten.", "Muhammad Ali"),
    ("La mejor hora para plantar un árbol fue hace 20 años. La segunda mejor es ahora.", None),
    ("Somos lo que hacemos repetidamente. La excelencia no es un acto, es un hábito.", "Aristóteles"),
    ("El dolor de la disciplina pesa gramos. El dolor del arrepentimiento pesa toneladas.", None),
    ("Primero formamos nuestros hábitos, luego nuestros hábitos nos forman a nosotros.", "John Dryden"),
    ("Un viaje de mil kilómetros comienza con un solo paso.", "Lao Tse"),
    ("No es lo que hacemos de vez en cuando lo que cuenta, sino lo que hacemos constantemente.", "Tony Robbins"),
    ("La constancia es la madre de la maestría.", None),
    ("Pequeñas acciones diarias suman grandes resultados.", None),
    ("Hoy es un buen día para ser mejor.", None),
    ("Su único competidor es usted mismo ayer.", None),
    ("El progreso, no la perfección, es lo que importa.", None),
    ("Cada hábito completado es un voto por la persona que quiere ser.", "James Clear"),
]


def seed_quotes(db: Session):
    """Inserta las citas en la BD si está vacía"""
    if db.query(Quote).count() == 0:
        for text, author in DEFAULT_QUOTES:
            db.add(Quote(text=text, author=author, category="general"))
        db.commit()
        logger.info(f"✅ {len(DEFAULT_QUOTES)} citas motivacionales insertadas")


def get_random_quote(db: Session) -> dict:
    """Devuelve una cita aleatoria"""
    quotes = db.query(Quote).all()
    if not quotes:
        return {"text": "Cada día es una oportunidad.", "author": None}
    quote = random.choice(quotes)
    return {"text": quote.text, "author": quote.author}
