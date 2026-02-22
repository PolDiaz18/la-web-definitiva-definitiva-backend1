"""
=============================================================================
MODELS.PY — Todos los Modelos (Tablas) de la Base de Datos
=============================================================================
Cada clase aquí = una tabla en la base de datos.
Cada atributo de la clase = una columna en esa tabla.

RELACIONES:
  User tiene muchos → Habits, Routines, Reminders, Tasks, Goals, etc.
  Habit tiene muchos → HabitLogs
  Routine tiene muchos → RoutineSteps
  Goal tiene muchos → GoalMilestones

Piensa en esto como un organigrama:
  USER
  ├── habits[] ──→ habit_logs[]
  ├── routines[] ──→ routine_steps[]
  ├── reminders[]
  ├── tasks[]
  ├── goals[] ──→ goal_milestones[]
  ├── mood_logs[]
  ├── sleep_logs[]
  ├── exercise_logs[]
  ├── water_logs[]
  ├── weight_logs[]
  ├── journal_entries[]
  ├── gratitude_entries[]
  ├── expense_logs[]
  ├── achievements[] (desbloqueados)
  ├── pomodoro_sessions[]
  ├── reflections[]
  └── challenges[] (activos)
"""

from datetime import datetime, date, time
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, Text, Date, Time,
    DateTime, ForeignKey, Enum, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database import Base
import enum


# =============================================================================
# ===================== ENUMS (Tipos predefinidos) ============================
# =============================================================================
# Un Enum es un tipo de dato que solo puede tener ciertos valores.
# Ejemplo: HabitType solo puede ser "boolean" o "quantity", nada más.

class HabitType(str, enum.Enum):
    """Tipo de hábito: sí/no o con cantidad"""
    boolean = "boolean"      # ¿Lo hiciste? Sí/No
    quantity = "quantity"     # ¿Cuánto? (vasos de agua, páginas leídas...)

class HabitFrequency(str, enum.Enum):
    """Con qué frecuencia se repite el hábito"""
    daily = "daily"                  # Todos los días
    specific_days = "specific_days"  # Días concretos (L, M, X...)
    times_per_week = "times_per_week"  # X veces por semana (sin día fijo)

class HabitCategory(str, enum.Enum):
    """Categoría del hábito"""
    health = "health"            # 💪 Salud
    mental = "mental"            # 🧠 Mental
    productivity = "productivity"  # 🚀 Productividad
    social = "social"            # 👥 Social
    finance = "finance"          # 💰 Finanzas
    learning = "learning"        # 📚 Aprendizaje
    other = "other"              # 📌 Otro

class MoodLevel(int, enum.Enum):
    """Nivel de estado de ánimo (1-5)"""
    terrible = 1   # 😢
    bad = 2        # 😞
    neutral = 3    # 😐
    good = 4       # 🙂
    amazing = 5    # 🤩

class UserMode(str, enum.Enum):
    """Modo especial del usuario"""
    normal = "normal"        # Funcionamiento normal
    vacation = "vacation"    # Modo vacaciones (pausa todo, no pierde rachas)
    sick = "sick"            # Modo enfermo (hábitos reducidos al mínimo)

class TaskPriority(str, enum.Enum):
    """Prioridad de una tarea"""
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"

class UserPlan(str, enum.Enum):
    """Plan del usuario"""
    free = "free"
    premium = "premium"


# =============================================================================
# ===================== TABLA 1: USERS ========================================
# =============================================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # ── Datos básicos ──
    email = Column(String(255), unique=True, nullable=False, index=True)
    # index=True → crea un índice para búsquedas rápidas por email
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    
    # ── Telegram ──
    telegram_id = Column(String(50), unique=True, nullable=True)
    # nullable=True → puede ser NULL (usuario no vinculado aún)
    telegram_link_code = Column(String(10), nullable=True)
    # Código temporal para vincular (se borra después de usar)
    
    # ── Configuración ──
    timezone = Column(String(50), default="Europe/Madrid")
    plan = Column(String(20), default=UserPlan.free)
    mode = Column(String(20), default=UserMode.normal)
    # mode → normal, vacation, sick
    do_not_disturb = Column(Boolean, default=False)
    # do_not_disturb → si True, no enviar recordatorios
    
    # ── Gamificación ──
    xp = Column(Integer, default=0)
    level = Column(Integer, default=1)
    global_streak = Column(Integer, default=0)
    # global_streak → días consecutivos completando TODOS los hábitos
    best_global_streak = Column(Integer, default=0)
    # best_global_streak → mejor racha histórica
    
    # ── Onboarding ──
    onboarding_completed = Column(Boolean, default=False)
    
    # ── Timestamps ──
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    
    # ── Relaciones ──
    # back_populates → permite navegar en ambas direcciones:
    #   user.habits → lista de hábitos del usuario
    #   habit.user → el usuario dueño del hábito
    habits = relationship("Habit", back_populates="user", cascade="all, delete-orphan")
    routines = relationship("Routine", back_populates="user", cascade="all, delete-orphan")
    routine_steps = relationship("RoutineStep", back_populates="user", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="user", cascade="all, delete-orphan")
    habit_logs = relationship("HabitLog", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    goals = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    mood_logs = relationship("MoodLog", back_populates="user", cascade="all, delete-orphan")
    sleep_logs = relationship("SleepLog", back_populates="user", cascade="all, delete-orphan")
    exercise_logs = relationship("ExerciseLog", back_populates="user", cascade="all, delete-orphan")
    water_logs = relationship("WaterLog", back_populates="user", cascade="all, delete-orphan")
    weight_logs = relationship("WeightLog", back_populates="user", cascade="all, delete-orphan")
    journal_entries = relationship("JournalEntry", back_populates="user", cascade="all, delete-orphan")
    gratitude_entries = relationship("GratitudeEntry", back_populates="user", cascade="all, delete-orphan")
    expense_logs = relationship("ExpenseLog", back_populates="user", cascade="all, delete-orphan")
    user_achievements = relationship("UserAchievement", back_populates="user", cascade="all, delete-orphan")
    pomodoro_sessions = relationship("PomodoroSession", back_populates="user", cascade="all, delete-orphan")
    reflections = relationship("Reflection", back_populates="user", cascade="all, delete-orphan")
    user_challenges = relationship("UserChallenge", back_populates="user", cascade="all, delete-orphan")
    # cascade="all, delete-orphan" → si borras el usuario, se borran todos sus datos


# =============================================================================
# ===================== TABLA 2: HABITS =======================================
# =============================================================================

class Habit(Base):
    __tablename__ = "habits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # ── Datos del hábito ──
    name = Column(String(100), nullable=False)
    icon = Column(String(10), default="✅")
    category = Column(String(30), default=HabitCategory.other)
    description = Column(Text, nullable=True)
    
    # ── Tipo y frecuencia ──
    habit_type = Column(String(20), default=HabitType.boolean)
    # boolean = sí/no, quantity = número (vasos de agua, páginas...)
    target_quantity = Column(Float, nullable=True)
    # target_quantity → objetivo numérico (ej: 8 vasos, 30 páginas)
    quantity_unit = Column(String(30), nullable=True)
    # quantity_unit → unidad (ej: "vasos", "páginas", "minutos")
    
    frequency = Column(String(20), default=HabitFrequency.daily)
    specific_days = Column(JSON, nullable=True)
    # specific_days → ej: ["mon", "wed", "fri"] para L-X-V
    times_per_week = Column(Integer, nullable=True)
    # times_per_week → ej: 3 (hacerlo 3 veces esta semana, cualquier día)
    
    # ── Rachas ──
    current_streak = Column(Integer, default=0)
    best_streak = Column(Integer, default=0)
    
    # ── Estado ──
    active = Column(Boolean, default=True)
    archived = Column(Boolean, default=False)
    # archived → oculto pero no borrado, conserva historial
    order = Column(Integer, default=0)
    # order → posición en la lista del usuario
    
    # ── Timestamps ──
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # ── Relaciones ──
    user = relationship("User", back_populates="habits")
    logs = relationship("HabitLog", back_populates="habit", cascade="all, delete-orphan")


# =============================================================================
# ===================== TABLA 3: HABIT_LOGS ===================================
# =============================================================================
# Registro diario de cada hábito. Un registro por hábito por día.

class HabitLog(Base):
    __tablename__ = "habit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    habit_id = Column(Integer, ForeignKey("habits.id"), nullable=False)
    
    date = Column(Date, nullable=False)
    completed = Column(Boolean, default=False)
    # Para hábitos de tipo "quantity":
    quantity_logged = Column(Float, default=0)
    # quantity_logged → cuánto se ha registrado hoy (ej: 5 vasos de 8)
    
    note = Column(Text, nullable=True)
    # note → nota opcional ("Hoy leí 30 páginas de Atomic Habits")
    
    completed_at = Column(DateTime, nullable=True)
    # completed_at → cuándo se marcó como completado (para estadísticas)
    
    # ── Restricción única: un log por hábito por día ──
    __table_args__ = (
        UniqueConstraint('habit_id', 'date', name='uq_habit_date'),
    )
    
    user = relationship("User", back_populates="habit_logs")
    habit = relationship("Habit", back_populates="logs")


# =============================================================================
# ===================== TABLA 4: ROUTINES =====================================
# =============================================================================
# Una rutina es un contenedor de pasos. El usuario crea rutinas ilimitadas.

class Routine(Base):
    __tablename__ = "routines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    name = Column(String(100), nullable=False)
    # name → "Rutina mañana", "Pre-gym", "Post-trabajo"...
    icon = Column(String(10), default="📋")
    description = Column(Text, nullable=True)
    
    # ── Programación ──
    scheduled_time = Column(String(5), nullable=True)
    # scheduled_time → "07:00" (hora a la que se sugiere hacer)
    scheduled_days = Column(JSON, nullable=True)
    # scheduled_days → ["mon","tue","wed","thu","fri"] (días que aplica)
    
    # ── Preferencias ──
    display_mode = Column(String(20), default="list")
    # display_mode → "list" (toda de golpe) o "step_by_step" (paso a paso)
    
    active = Column(Boolean, default=True)
    order = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="routines")
    steps = relationship("RoutineStep", back_populates="routine", cascade="all, delete-orphan",
                         order_by="RoutineStep.step_order")


# =============================================================================
# ===================== TABLA 5: ROUTINE_STEPS ================================
# =============================================================================

class RoutineStep(Base):
    __tablename__ = "routine_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    routine_id = Column(Integer, ForeignKey("routines.id"), nullable=False)
    
    step_order = Column(Integer, nullable=False)
    # step_order → 1, 2, 3... (el orden del paso)
    description = Column(String(200), nullable=False)
    # description → "Ducha fría", "Meditar 10 min"
    duration_minutes = Column(Integer, nullable=True)
    # duration_minutes → duración estimada del paso (para modo paso a paso)
    
    # Vínculo opcional con un hábito
    linked_habit_id = Column(Integer, ForeignKey("habits.id"), nullable=True)
    # Si un paso de rutina está vinculado a un hábito, al completar el paso
    # se marca el hábito automáticamente.
    
    user = relationship("User", back_populates="routine_steps")
    routine = relationship("Routine", back_populates="steps")


# =============================================================================
# ===================== TABLA 6: REMINDERS ====================================
# =============================================================================

class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    type = Column(String(30), nullable=False)
    # Tipos: "morning", "midday", "evening", "night", "habits", 
    #        "summary", "weekly_summary", "routine", "custom"
    
    time = Column(String(5), nullable=False)
    # time → "07:00", "14:00", "22:00"
    
    days = Column(JSON, nullable=True)
    # days → ["mon","tue",...] Si null = todos los días
    
    message = Column(Text, nullable=True)
    # message → mensaje personalizado (si null, usa el predeterminado)
    
    linked_routine_id = Column(Integer, ForeignKey("routines.id"), nullable=True)
    # Si el recordatorio está vinculado a una rutina, envía esa rutina
    
    active = Column(Boolean, default=True)
    
    user = relationship("User", back_populates="reminders")


# =============================================================================
# ===================== TABLA 7: TASKS ========================================
# =============================================================================
# Sistema de tareas/to-do separado de hábitos.
# Un hábito es algo recurrente. Una tarea es algo puntual.

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(20), default=TaskPriority.medium)
    
    due_date = Column(Date, nullable=True)
    due_time = Column(String(5), nullable=True)
    # due_time → "15:00" (hora límite)
    
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="tasks")


# =============================================================================
# ===================== TABLA 8: GOALS ========================================
# =============================================================================
# Objetivos a largo plazo con porcentaje de avance.

class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(10), default="🎯")
    
    target_date = Column(Date, nullable=True)
    # target_date → fecha límite del objetivo
    progress = Column(Float, default=0)
    # progress → 0.0 a 100.0 (porcentaje de avance)
    
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="goals")
    milestones = relationship("GoalMilestone", back_populates="goal", cascade="all, delete-orphan")


class GoalMilestone(Base):
    """Hitos dentro de un objetivo. Ej: Objetivo 'Correr maratón' → Hitos: 5k, 10k, 21k, 42k"""
    __tablename__ = "goal_milestones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, ForeignKey("goals.id"), nullable=False)
    
    title = Column(String(200), nullable=False)
    order = Column(Integer, default=0)
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    
    goal = relationship("Goal", back_populates="milestones")


# =============================================================================
# ===================== TABLA 9: MOOD_LOGS ====================================
# =============================================================================

class MoodLog(Base):
    __tablename__ = "mood_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    date = Column(Date, nullable=False)
    level = Column(Integer, nullable=False)
    # level → 1 (terrible) a 5 (increíble)
    note = Column(Text, nullable=True)
    # note → reflexión opcional sobre el estado de ánimo
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uq_mood_date'),
    )
    
    user = relationship("User", back_populates="mood_logs")


# =============================================================================
# ===================== TABLA 10: SLEEP_LOGS ==================================
# =============================================================================

class SleepLog(Base):
    __tablename__ = "sleep_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    date = Column(Date, nullable=False)
    # date → la fecha a la que "pertenece" el sueño (la noche anterior)
    bedtime = Column(String(5), nullable=True)
    # bedtime → "23:30" (hora de acostarse)
    wake_time = Column(String(5), nullable=True)
    # wake_time → "07:00" (hora de levantarse)
    hours = Column(Float, nullable=False)
    # hours → 7.5 (horas totales de sueño)
    quality = Column(Integer, nullable=True)
    # quality → 1 a 5 (calidad subjetiva del sueño)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uq_sleep_date'),
    )
    
    user = relationship("User", back_populates="sleep_logs")


# =============================================================================
# ===================== TABLA 11: EXERCISE_LOGS ===============================
# =============================================================================

class ExerciseLog(Base):
    __tablename__ = "exercise_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    date = Column(Date, nullable=False)
    exercise_type = Column(String(50), nullable=False)
    # exercise_type → "Correr", "Pesas", "Yoga", "Fútbol"...
    duration_minutes = Column(Integer, nullable=True)
    intensity = Column(String(20), nullable=True)
    # intensity → "light", "moderate", "intense"
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="exercise_logs")


# =============================================================================
# ===================== TABLA 12: WATER_LOGS ==================================
# =============================================================================

class WaterLog(Base):
    __tablename__ = "water_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    date = Column(Date, nullable=False)
    glasses = Column(Integer, default=0)
    # glasses → número de vasos de agua bebidos hoy
    target = Column(Integer, default=8)
    # target → objetivo de vasos por día
    
    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uq_water_date'),
    )
    
    user = relationship("User", back_populates="water_logs")


# =============================================================================
# ===================== TABLA 13: WEIGHT_LOGS =================================
# =============================================================================

class WeightLog(Base):
    __tablename__ = "weight_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    date = Column(Date, nullable=False)
    weight_kg = Column(Float, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uq_weight_date'),
    )
    
    user = relationship("User", back_populates="weight_logs")


# =============================================================================
# ===================== TABLA 14: JOURNAL_ENTRIES =============================
# =============================================================================

class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    date = Column(Date, nullable=False)
    content = Column(Text, nullable=False)
    # content → texto libre del diario
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="journal_entries")


# =============================================================================
# ===================== TABLA 15: GRATITUDE_ENTRIES ============================
# =============================================================================

class GratitudeEntry(Base):
    __tablename__ = "gratitude_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    date = Column(Date, nullable=False)
    item_1 = Column(String(300), nullable=False)
    item_2 = Column(String(300), nullable=True)
    item_3 = Column(String(300), nullable=True)
    # 3 cosas por las que estás agradecido hoy
    
    __table_args__ = (
        UniqueConstraint('user_id', 'date', name='uq_gratitude_date'),
    )
    
    user = relationship("User", back_populates="gratitude_entries")


# =============================================================================
# ===================== TABLA 16: EXPENSE_LOGS ================================
# =============================================================================

class ExpenseLog(Base):
    __tablename__ = "expense_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String(50), nullable=True)
    # category → "Comida", "Transporte", "Ocio", "Facturas"...
    description = Column(String(200), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="expense_logs")


# =============================================================================
# ===================== TABLA 17: ACHIEVEMENTS ================================
# =============================================================================
# Tabla de logros DISPONIBLES (los define el sistema, no el usuario)

class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    code = Column(String(50), unique=True, nullable=False)
    # code → identificador único: "streak_7", "streak_30", "first_habit"...
    name = Column(String(100), nullable=False)
    # name → "Semana de fuego 🔥", "Mes imparable 💎"
    description = Column(String(300), nullable=False)
    icon = Column(String(10), default="🏆")
    xp_reward = Column(Integer, default=0)
    # xp_reward → XP que se gana al desbloquear este logro


# =============================================================================
# ===================== TABLA 18: USER_ACHIEVEMENTS ===========================
# =============================================================================
# Logros desbloqueados por cada usuario

class UserAchievement(Base):
    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)
    
    unlocked_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),
    )
    
    user = relationship("User", back_populates="user_achievements")
    achievement = relationship("Achievement")


# =============================================================================
# ===================== TABLA 19: POMODORO_SESSIONS ===========================
# =============================================================================

class PomodoroSession(Base):
    __tablename__ = "pomodoro_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    date = Column(Date, nullable=False)
    work_minutes = Column(Integer, default=25)
    break_minutes = Column(Integer, default=5)
    completed = Column(Boolean, default=False)
    
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="pomodoro_sessions")


# =============================================================================
# ===================== TABLA 20: REFLECTIONS =================================
# =============================================================================
# Reflexiones semanales guiadas

class Reflection(Base):
    __tablename__ = "reflections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    week_start = Column(Date, nullable=False)
    # week_start → lunes de la semana a la que pertenece
    
    best_moment = Column(Text, nullable=True)
    # "¿Qué fue lo mejor de esta semana?"
    improvement = Column(Text, nullable=True)
    # "¿Qué mejorarías?"
    lesson = Column(Text, nullable=True)
    # "¿Qué aprendiste?"
    next_week_focus = Column(Text, nullable=True)
    # "¿En qué te vas a enfocar la próxima semana?"
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'week_start', name='uq_reflection_week'),
    )
    
    user = relationship("User", back_populates="reflections")


# =============================================================================
# ===================== TABLA 21: CHALLENGES ==================================
# =============================================================================
# Desafíos semanales y mensuales generados por el sistema

class Challenge(Base):
    __tablename__ = "challenges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    type = Column(String(20), nullable=False)
    # type → "weekly" o "monthly"
    icon = Column(String(10), default="⚡")
    
    # Condiciones del desafío (en JSON para flexibilidad)
    conditions = Column(JSON, nullable=False)
    # conditions → {"type": "complete_all", "days": 5}
    #              {"type": "streak", "min_days": 7}
    #              {"type": "specific_habit", "habit_category": "health", "times": 5}
    
    xp_reward = Column(Integer, default=50)
    
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)


# =============================================================================
# ===================== TABLA 22: USER_CHALLENGES =============================
# =============================================================================

class UserChallenge(Base):
    __tablename__ = "user_challenges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), nullable=False)
    
    progress = Column(Float, default=0)
    # progress → 0.0 a 100.0
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'challenge_id', name='uq_user_challenge'),
    )
    
    user = relationship("User", back_populates="user_challenges")
    challenge = relationship("Challenge")


# =============================================================================
# ===================== TABLA 23: QUOTES ======================================
# =============================================================================
# Citas motivacionales para /inspiracion y recordatorios

class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    text = Column(Text, nullable=False)
    author = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True)
    # category → "stoicism", "productivity", "sports", "general"


# =============================================================================
# ===================== TABLA 24: FRIENDSHIPS =================================
# =============================================================================
# Para rankings voluntarios entre amigos

class Friendship(Base):
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    friend_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    status = Column(String(20), default="pending")
    # status → "pending", "accepted", "rejected"
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'friend_id', name='uq_friendship'),
    )
