"""
=============================================================================
SCHEMAS.PY — Esquemas de Validación (Pydantic)
=============================================================================
¿Qué es Pydantic?
Es una librería que VALIDA datos. Cuando alguien envía datos a tu API,
Pydantic se asegura de que:
  - Los campos obligatorios estén presentes
  - Los tipos sean correctos (string, int, etc.)
  - Los valores sean válidos

¿Por qué separar Models y Schemas?
  - Models (SQLAlchemy) → definen las TABLAS de la BD
  - Schemas (Pydantic) → definen qué DATOS acepta/devuelve la API

Ejemplo:
  El usuario envía: {"name": "Leer", "icon": "📖", "category": "learning"}
  Pydantic valida que name sea string, icon sea string, etc.
  Si algo falla → error 422 automático con mensaje claro.

Convención de nombres:
  XxxCreate → para crear algo nuevo (POST)
  XxxUpdate → para actualizar algo (PUT/PATCH)
  XxxResponse → lo que devuelve la API (GET)
"""

from pydantic import BaseModel, Field, EmailStr
from datetime import date, datetime
from typing import Optional
from enum import Enum


# =============================================================================
# ===================== AUTH ==================================================
# =============================================================================

class UserRegister(BaseModel):
    """Datos para registrar un usuario nuevo"""
    email: EmailStr
    password: str = Field(min_length=6, description="Mínimo 6 caracteres")
    name: str = Field(min_length=1, max_length=100)

class UserLogin(BaseModel):
    """Datos para iniciar sesión"""
    email: EmailStr
    password: str

class TelegramLogin(BaseModel):
    """Login desde Telegram con email y contraseña"""
    email: EmailStr
    password: str
    telegram_id: str

class TokenResponse(BaseModel):
    """Respuesta con el token JWT"""
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str

class UserResponse(BaseModel):
    """Datos del usuario para la API"""
    id: int
    email: str
    name: str
    telegram_id: Optional[str] = None
    timezone: str
    plan: str
    mode: str
    do_not_disturb: bool
    xp: int
    level: int
    global_streak: int
    best_global_streak: int
    onboarding_completed: bool
    created_at: datetime
    last_active: datetime
    model_config = {"from_attributes": True}

class UserUpdate(BaseModel):
    """Campos actualizables del usuario"""
    name: Optional[str] = None
    timezone: Optional[str] = None
    mode: Optional[str] = None
    do_not_disturb: Optional[bool] = None


# =============================================================================
# ===================== HABITS ================================================
# =============================================================================

class HabitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    icon: str = "✅"
    category: str = "other"
    description: Optional[str] = None
    habit_type: str = "boolean"
    target_quantity: Optional[float] = None
    quantity_unit: Optional[str] = None
    frequency: str = "daily"
    specific_days: Optional[list[str]] = None
    times_per_week: Optional[int] = None

class HabitUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    target_quantity: Optional[float] = None
    frequency: Optional[str] = None
    specific_days: Optional[list[str]] = None
    times_per_week: Optional[int] = None
    active: Optional[bool] = None
    archived: Optional[bool] = None
    order: Optional[int] = None

class HabitResponse(BaseModel):
    id: int
    name: str
    icon: str
    category: str
    description: Optional[str]
    habit_type: str
    target_quantity: Optional[float]
    quantity_unit: Optional[str]
    frequency: str
    specific_days: Optional[list[str]]
    times_per_week: Optional[int]
    current_streak: int
    best_streak: int
    active: bool
    archived: bool
    order: int
    created_at: datetime
    model_config = {"from_attributes": True}


# =============================================================================
# ===================== HABIT LOGS ============================================
# =============================================================================

class HabitLogCreate(BaseModel):
    habit_id: int
    date: date
    completed: bool = True
    quantity_logged: Optional[float] = None
    note: Optional[str] = None

class HabitLogResponse(BaseModel):
    id: int
    habit_id: int
    date: date
    completed: bool
    quantity_logged: float
    note: Optional[str]
    completed_at: Optional[datetime]
    model_config = {"from_attributes": True}

class DaySummary(BaseModel):
    date: date
    total_habits: int
    completed: int
    percentage: float
    habits: list[HabitLogResponse]


# =============================================================================
# ===================== ROUTINES ==============================================
# =============================================================================

class RoutineStepCreate(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    step_order: int
    duration_minutes: Optional[int] = None
    linked_habit_id: Optional[int] = None

class RoutineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    icon: str = "📋"
    description: Optional[str] = None
    scheduled_time: Optional[str] = None
    scheduled_days: Optional[list[str]] = None
    display_mode: str = "list"
    steps: list[RoutineStepCreate] = []

class RoutineUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    scheduled_time: Optional[str] = None
    scheduled_days: Optional[list[str]] = None
    display_mode: Optional[str] = None
    active: Optional[bool] = None
    order: Optional[int] = None

class RoutineStepResponse(BaseModel):
    id: int
    step_order: int
    description: str
    duration_minutes: Optional[int]
    linked_habit_id: Optional[int]
    model_config = {"from_attributes": True}

class RoutineResponse(BaseModel):
    id: int
    name: str
    icon: str
    description: Optional[str]
    scheduled_time: Optional[str]
    scheduled_days: Optional[list[str]]
    display_mode: str
    active: bool
    order: int
    steps: list[RoutineStepResponse] = []
    model_config = {"from_attributes": True}


# =============================================================================
# ===================== REMINDERS =============================================
# =============================================================================

class ReminderCreate(BaseModel):
    type: str
    time: str = Field(pattern=r"^\d{2}:\d{2}$", description="Formato HH:MM")
    days: Optional[list[str]] = None
    message: Optional[str] = None
    linked_routine_id: Optional[int] = None

class ReminderUpdate(BaseModel):
    time: Optional[str] = None
    days: Optional[list[str]] = None
    message: Optional[str] = None
    active: Optional[bool] = None

class ReminderResponse(BaseModel):
    id: int
    type: str
    time: str
    days: Optional[list[str]]
    message: Optional[str]
    linked_routine_id: Optional[int]
    active: bool
    model_config = {"from_attributes": True}


# =============================================================================
# ===================== TASKS =================================================
# =============================================================================

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[date] = None
    due_time: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[date] = None
    due_time: Optional[str] = None
    completed: Optional[bool] = None

class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    priority: str
    due_date: Optional[date]
    due_time: Optional[str]
    completed: bool
    completed_at: Optional[datetime]
    created_at: datetime
    model_config = {"from_attributes": True}


# =============================================================================
# ===================== GOALS =================================================
# =============================================================================

class GoalMilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    order: int = 0

class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    icon: str = "🎯"
    target_date: Optional[date] = None
    milestones: list[GoalMilestoneCreate] = []

class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    target_date: Optional[date] = None
    progress: Optional[float] = None
    completed: Optional[bool] = None

class GoalMilestoneResponse(BaseModel):
    id: int
    title: str
    order: int
    completed: bool
    completed_at: Optional[datetime]
    model_config = {"from_attributes": True}

class GoalResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    icon: str
    target_date: Optional[date]
    progress: float
    completed: bool
    completed_at: Optional[datetime]
    created_at: datetime
    milestones: list[GoalMilestoneResponse] = []
    model_config = {"from_attributes": True}


# =============================================================================
# ===================== TRACKING LOGS =========================================
# =============================================================================

class MoodLogCreate(BaseModel):
    date: date
    level: int = Field(ge=1, le=5, description="1=terrible, 5=increíble")
    note: Optional[str] = None

class MoodLogResponse(BaseModel):
    id: int
    date: date
    level: int
    note: Optional[str]
    model_config = {"from_attributes": True}

class SleepLogCreate(BaseModel):
    date: date
    hours: float = Field(gt=0, le=24)
    bedtime: Optional[str] = None
    wake_time: Optional[str] = None
    quality: Optional[int] = Field(default=None, ge=1, le=5)

class SleepLogResponse(BaseModel):
    id: int
    date: date
    hours: float
    bedtime: Optional[str]
    wake_time: Optional[str]
    quality: Optional[int]
    model_config = {"from_attributes": True}

class ExerciseLogCreate(BaseModel):
    date: date
    exercise_type: str
    duration_minutes: Optional[int] = None
    intensity: Optional[str] = None
    notes: Optional[str] = None

class ExerciseLogResponse(BaseModel):
    id: int
    date: date
    exercise_type: str
    duration_minutes: Optional[int]
    intensity: Optional[str]
    notes: Optional[str]
    model_config = {"from_attributes": True}

class WaterLogCreate(BaseModel):
    date: date
    glasses: int = Field(ge=0)

class WaterLogUpdate(BaseModel):
    """Para añadir un vaso más (incrementar)"""
    date: date
    add_glasses: int = 1

class WaterLogResponse(BaseModel):
    id: int
    date: date
    glasses: int
    target: int
    model_config = {"from_attributes": True}

class WeightLogCreate(BaseModel):
    date: date
    weight_kg: float = Field(gt=0)

class WeightLogResponse(BaseModel):
    id: int
    date: date
    weight_kg: float
    model_config = {"from_attributes": True}

class JournalEntryCreate(BaseModel):
    date: date
    content: str = Field(min_length=1)

class JournalEntryResponse(BaseModel):
    id: int
    date: date
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}

class GratitudeEntryCreate(BaseModel):
    date: date
    item_1: str
    item_2: Optional[str] = None
    item_3: Optional[str] = None

class GratitudeEntryResponse(BaseModel):
    id: int
    date: date
    item_1: str
    item_2: Optional[str]
    item_3: Optional[str]
    model_config = {"from_attributes": True}

class ExpenseLogCreate(BaseModel):
    date: date
    amount: float = Field(gt=0)
    category: Optional[str] = None
    description: Optional[str] = None

class ExpenseLogResponse(BaseModel):
    id: int
    date: date
    amount: float
    category: Optional[str]
    description: Optional[str]
    model_config = {"from_attributes": True}


# =============================================================================
# ===================== GAMIFICATION ==========================================
# =============================================================================

class AchievementResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str
    icon: str
    xp_reward: int
    unlocked: bool = False
    unlocked_at: Optional[datetime] = None
    model_config = {"from_attributes": True}

class LevelInfo(BaseModel):
    level: int
    xp: int
    xp_next_level: int
    xp_progress: float  # porcentaje hacia el siguiente nivel
    title: str  # "Novato", "Aprendiz", etc.


# =============================================================================
# ===================== REFLECTIONS ===========================================
# =============================================================================

class ReflectionCreate(BaseModel):
    week_start: date
    best_moment: Optional[str] = None
    improvement: Optional[str] = None
    lesson: Optional[str] = None
    next_week_focus: Optional[str] = None

class ReflectionResponse(BaseModel):
    id: int
    week_start: date
    best_moment: Optional[str]
    improvement: Optional[str]
    lesson: Optional[str]
    next_week_focus: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# =============================================================================
# ===================== POMODORO ==============================================
# =============================================================================

class PomodoroStart(BaseModel):
    work_minutes: int = 25
    break_minutes: int = 5

class PomodoroResponse(BaseModel):
    id: int
    date: date
    work_minutes: int
    break_minutes: int
    completed: bool
    started_at: datetime
    finished_at: Optional[datetime]
    model_config = {"from_attributes": True}


# =============================================================================
# ===================== ONBOARDING ============================================
# =============================================================================

class OnboardingData(BaseModel):
    """Respuestas del cuestionario de onboarding"""
    name: str
    timezone: Optional[str] = "Europe/Madrid"
    goals: list[str] = []
    # goals → ["health", "productivity", "mental", "social"]
    wake_time: Optional[str] = "07:00"
    sleep_time: Optional[str] = "23:00"
    experience_level: Optional[str] = "beginner"
    # experience_level → "beginner", "intermediate", "advanced"
    preferred_habits: list[str] = []
    # preferred_habits → lista de hábitos que quiere trackear
    reminder_frequency: Optional[str] = "normal"
    # reminder_frequency → "minimal", "normal", "intensive"
    motivation_style: Optional[str] = "coach"
    # motivation_style → "coach", "data", "minimal"
