"""
=============================================================================
MAIN.PY — La API de NexoTime v2
=============================================================================
Este archivo define TODOS los endpoints de la API REST.

Organización por secciones:
  1. AUTH         → Registro, login, perfil
  2. HABITS       → CRUD de hábitos
  3. HABIT LOGS   → Marcar hábitos, resúmenes
  4. ROUTINES     → CRUD de rutinas y pasos
  5. REMINDERS    → CRUD de recordatorios
  6. TASKS        → CRUD de tareas (to-do)
  7. GOALS        → CRUD de objetivos a largo plazo
  8. TRACKING     → Mood, sueño, ejercicio, agua, peso, diario, gratitud, gastos
  9. GAMIFICATION → Nivel, logros, rachas, citas
  10. REFLECTIONS → Reflexiones semanales
  11. POMODORO    → Sesiones de pomodoro
  12. ONBOARDING  → Flujo de configuración inicial
  13. TELEGRAM    → Login desde Telegram
  14. ADMIN       → Stats globales (solo para ti)

Total: ~60 endpoints
"""

import os
import logging
import traceback
from datetime import datetime, date, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from database import get_db, init_db, SessionLocal
from models import *
from schemas import *
from auth import (
    hash_password, verify_password, create_access_token, 
    get_current_user
)
from gamification import (
    seed_achievements, seed_quotes, award_xp, get_level_info,
    update_habit_streak, update_global_streak, check_and_unlock_achievements,
    get_random_quote, habit_applies_today
)

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("nexotime.api")

# ─────────────────────────────────────────────────────────────────────────────
# INICIALIZACIÓN TEMPRANA DE LA BD
# ─────────────────────────────────────────────────────────────────────────────
# Creamos las tablas aquí, ANTES del lifespan, para asegurar que existan.
# Esto es un respaldo por si el lifespan no se ejecuta correctamente.

try:
    init_db()
    logger.info("✅ Base de datos inicializada (startup)")
except Exception as e:
    logger.error(f"❌ Error inicializando BD: {e}")

try:
    _db = SessionLocal()
    seed_achievements(_db)
    seed_quotes(_db)
    _db.close()
    logger.info("✅ Seeds completados (startup)")
except Exception as e:
    logger.error(f"❌ Error en seeds: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN (Arranque y apagado)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Se ejecuta al ARRANCAR y al APAGAR la aplicación.
    
    Arranque:
      1. Inicializar BD (crear tablas)
      2. Seed de datos iniciales (logros, citas)
      3. Arrancar bot de Telegram
      4. Arrancar scheduler de recordatorios
    
    Apagado:
      - Parar bot y scheduler limpiamente
    """
    logger.info("🚀 Arrancando NexoTime v2...")
    
    # 1. Crear tablas si no existen
    init_db()
    logger.info("✅ Base de datos inicializada")
    
    # 2. Insertar datos iniciales
    db = SessionLocal()
    try:
        seed_achievements(db)
        seed_quotes(db)
    finally:
        db.close()
    
    # 3. Arrancar bot de Telegram
    bot_app = None
    try:
        from bot import create_bot_application, start_bot, stop_bot
        bot_app = create_bot_application()
        if bot_app:
            await start_bot(bot_app)
            logger.info("🤖 Bot de Telegram arrancado")
        else:
            logger.warning("⚠️ Bot no arrancado (sin token)")
    except Exception as e:
        logger.error(f"❌ Error arrancando bot: {e}")
    
    # 4. Arrancar scheduler de recordatorios
    try:
        from scheduler import create_scheduler, start_scheduler, stop_scheduler
        if bot_app:
            create_scheduler(bot_app.bot)
            start_scheduler()
            logger.info("⏰ Scheduler arrancado")
        else:
            logger.warning("⚠️ Scheduler no arrancado (bot no disponible)")
    except Exception as e:
        logger.error(f"❌ Error arrancando scheduler: {e}")
    
    logger.info("🎉 NexoTime v2 operativo")
    
    yield  # ← La aplicación está corriendo
    
    # Apagado
    logger.info("🛑 Apagando NexoTime v2...")
    
    try:
        stop_scheduler()
    except:
        pass
    
    if bot_app:
        try:
            await stop_bot(bot_app)
        except:
            pass
    
    logger.info("👋 Apagado completo")


# ─────────────────────────────────────────────────────────────────────────────
# APLICACIÓN FASTAPI
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="NexoTime API v2",
    description="Backend completo del sistema de productividad y coaching automatizado",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS → permite que la web (Vercel) haga peticiones a esta API (Railway)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción: ["https://tu-dominio.vercel.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL ERROR HANDLER
# ─────────────────────────────────────────────────────────────────────────────
# Captura CUALQUIER error no manejado y devuelve un JSON con el error real
# en vez de un genérico "Internal Server Error"

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Captura errores no manejados y devuelve detalles útiles"""
    error_msg = str(exc)
    error_trace = traceback.format_exc()
    logger.error(f"❌ Error no manejado en {request.url}: {error_msg}\n{error_trace}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": error_msg,
            "type": type(exc).__name__,
            "path": str(request.url)
        }
    )


# =============================================================================
# ===================== HEALTH CHECK ==========================================
# =============================================================================

@app.get("/", tags=["Health"])
def health_check():
    """Verifica que la API está viva"""
    return {
        "status": "ok",
        "app": "NexoTime v2",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


# =============================================================================
# ===================== SECCIÓN 1: AUTH =======================================
# =============================================================================

@app.post("/auth/register", response_model=TokenResponse, tags=["Auth"])
def register(data: UserRegister, db: Session = Depends(get_db)):
    """
    Registra un usuario nuevo.
    
    Flujo:
      1. Verificar que el email no existe
      2. Hashear la contraseña
      3. Crear el usuario en BD
      4. Crear recordatorios por defecto
      5. Generar y devolver token JWT
    """
    # Verificar email único
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este email"
        )
    
    # Crear usuario
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Crear recordatorios por defecto
    default_reminders = [
        Reminder(user_id=user.id, type="morning", time="07:00", active=True),
        Reminder(user_id=user.id, type="midday", time="14:00", active=True),
        Reminder(user_id=user.id, type="evening", time="20:00", active=True),
        Reminder(user_id=user.id, type="night", time="22:30", active=True),
        Reminder(user_id=user.id, type="summary", time="23:00", active=True),
    ]
    db.add_all(default_reminders)
    db.commit()
    
    # Generar token
    token = create_access_token(user.id, user.email)
    
    logger.info(f"👤 Nuevo usuario registrado: {user.name} ({user.email})")
    
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        name=user.name
    )


@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
def login(data: UserLogin, db: Session = Depends(get_db)):
    """Inicia sesión con email y contraseña"""
    user = db.query(User).filter(User.email == data.email).first()
    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )
    
    token = create_access_token(user.id, user.email)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        name=user.name
    )


@app.post("/auth/telegram-login", response_model=TokenResponse, tags=["Auth"])
def telegram_login(data: TelegramLogin, db: Session = Depends(get_db)):
    """
    Login desde el bot de Telegram con email + contraseña.
    Además de autenticar, vincula el telegram_id al usuario.
    """
    user = db.query(User).filter(User.email == data.email).first()
    
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )
    
    # Verificar que el telegram_id no esté ya vinculado a otra cuenta
    existing_tg = db.query(User).filter(
        User.telegram_id == data.telegram_id,
        User.id != user.id
    ).first()
    if existing_tg:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este Telegram ya está vinculado a otra cuenta"
        )
    
    # Vincular telegram_id
    user.telegram_id = data.telegram_id
    db.commit()
    
    token = create_access_token(user.id, user.email)
    logger.info(f"📱 Login Telegram: {user.name} (tg_id: {data.telegram_id})")
    
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        name=user.name
    )


@app.get("/auth/me", response_model=UserResponse, tags=["Auth"])
def get_me(user: User = Depends(get_current_user)):
    """Devuelve los datos del usuario autenticado"""
    return user


@app.patch("/auth/me", response_model=UserResponse, tags=["Auth"])
def update_me(data: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Actualiza datos del usuario"""
    if data.name is not None:
        user.name = data.name
    if data.timezone is not None:
        user.timezone = data.timezone
    if data.mode is not None:
        user.mode = data.mode
    if data.do_not_disturb is not None:
        user.do_not_disturb = data.do_not_disturb
    
    db.commit()
    db.refresh(user)
    return user


@app.delete("/auth/me", tags=["Auth"])
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Borra la cuenta y TODOS los datos del usuario (irreversible)"""
    db.delete(user)
    db.commit()
    logger.info(f"🗑️ Cuenta borrada: {user.email}")
    return {"message": "Cuenta y todos los datos eliminados correctamente"}


# =============================================================================
# ===================== SECCIÓN 2: HABITS =====================================
# =============================================================================

@app.post("/habits", response_model=HabitResponse, tags=["Habits"])
def create_habit(data: HabitCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Crea un nuevo hábito"""
    # Calcular el orden (siguiente posición)
    max_order = db.query(func.max(Habit.order)).filter(
        Habit.user_id == user.id
    ).scalar() or 0
    
    habit = Habit(
        user_id=user.id,
        name=data.name,
        icon=data.icon,
        category=data.category,
        description=data.description,
        habit_type=data.habit_type,
        target_quantity=data.target_quantity,
        quantity_unit=data.quantity_unit,
        frequency=data.frequency,
        specific_days=data.specific_days,
        times_per_week=data.times_per_week,
        order=max_order + 1
    )
    db.add(habit)
    db.commit()
    db.refresh(habit)
    
    logger.info(f"➕ Hábito creado: {habit.name} (user: {user.name})")
    return habit


@app.get("/habits", response_model=list[HabitResponse], tags=["Habits"])
def list_habits(
    active_only: bool = True,
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista los hábitos del usuario"""
    query = db.query(Habit).filter(Habit.user_id == user.id)
    
    if active_only:
        query = query.filter(Habit.active == True)
    if not include_archived:
        query = query.filter(Habit.archived == False)
    
    return query.order_by(Habit.order).all()


@app.get("/habits/{habit_id}", response_model=HabitResponse, tags=["Habits"])
def get_habit(habit_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Obtiene un hábito por ID"""
    habit = db.query(Habit).filter(
        Habit.id == habit_id, Habit.user_id == user.id
    ).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Hábito no encontrado")
    return habit


@app.patch("/habits/{habit_id}", response_model=HabitResponse, tags=["Habits"])
def update_habit(
    habit_id: int, data: HabitUpdate,
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Actualiza un hábito"""
    habit = db.query(Habit).filter(
        Habit.id == habit_id, Habit.user_id == user.id
    ).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Hábito no encontrado")
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(habit, key, value)
    
    db.commit()
    db.refresh(habit)
    return habit


@app.delete("/habits/{habit_id}", tags=["Habits"])
def delete_habit(habit_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Elimina un hábito y todo su historial"""
    habit = db.query(Habit).filter(
        Habit.id == habit_id, Habit.user_id == user.id
    ).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Hábito no encontrado")
    
    db.delete(habit)
    db.commit()
    return {"message": f"Hábito '{habit.name}' eliminado"}


# =============================================================================
# ===================== SECCIÓN 3: HABIT LOGS =================================
# =============================================================================

@app.post("/habits/log", response_model=HabitLogResponse, tags=["Habit Logs"])
def log_habit(
    data: HabitLogCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Registra el estado de un hábito para un día.
    
    Si ya existe un log para ese hábito+día, lo actualiza.
    Además:
      - Actualiza rachas (individual y global)
      - Otorga XP
      - Verifica logros
    """
    # Verificar que el hábito pertenece al usuario
    habit = db.query(Habit).filter(
        Habit.id == data.habit_id, Habit.user_id == user.id
    ).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Hábito no encontrado")
    
    # Buscar log existente o crear nuevo
    log = db.query(HabitLog).filter(
        HabitLog.habit_id == data.habit_id,
        HabitLog.date == data.date
    ).first()
    
    was_already_completed = False
    
    if log:
        was_already_completed = log.completed
        log.completed = data.completed
        if data.quantity_logged is not None:
            log.quantity_logged = data.quantity_logged
        if data.note is not None:
            log.note = data.note
        if data.completed and not was_already_completed:
            log.completed_at = datetime.utcnow()
    else:
        log = HabitLog(
            user_id=user.id,
            habit_id=data.habit_id,
            date=data.date,
            completed=data.completed,
            quantity_logged=data.quantity_logged or 0,
            note=data.note,
            completed_at=datetime.utcnow() if data.completed else None
        )
        db.add(log)
    
    db.commit()
    db.refresh(log)
    
    # ── Gamificación (solo si es un nuevo completado) ──
    xp_result = None
    new_achievements = []
    
    if data.completed and not was_already_completed:
        # Actualizar rachas
        update_habit_streak(db, habit, True, data.date)
        update_global_streak(db, user, data.date)
        
        # Dar XP
        xp_result = award_xp(db, user, "habit_complete", habit.current_streak)
        
        # Verificar si completó TODOS los hábitos del día
        active_habits = db.query(Habit).filter(
            Habit.user_id == user.id, Habit.active == True, Habit.archived == False
        ).all()
        
        today_applicable = [h for h in active_habits if habit_applies_today(h, data.date)]
        today_completed = db.query(HabitLog).filter(
            HabitLog.user_id == user.id,
            HabitLog.date == data.date,
            HabitLog.completed == True,
            HabitLog.habit_id.in_([h.id for h in today_applicable])
        ).count()
        
        if today_completed >= len(today_applicable) and len(today_applicable) > 0:
            award_xp(db, user, "all_habits_complete", user.global_streak)
        
        # Verificar logros
        new_achievements = check_and_unlock_achievements(db, user)
    
    elif not data.completed and was_already_completed:
        # Desmarcó el hábito → resetear racha
        update_habit_streak(db, habit, False, data.date)
    
    return log


@app.get("/habits/log/today", response_model=DaySummary, tags=["Habit Logs"])
def get_today_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Resumen del día de hoy"""
    today = date.today()
    return _get_day_summary(db, user, today)


@app.get("/habits/log/date/{log_date}", response_model=DaySummary, tags=["Habit Logs"])
def get_day_summary(log_date: date, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Resumen de un día específico"""
    return _get_day_summary(db, user, log_date)


@app.get("/habits/log/week", tags=["Habit Logs"])
def get_week_summary(
    start_date: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Resumen de la semana. Si no se pasa fecha, usa la semana actual.
    Devuelve un resumen por cada día de la semana.
    """
    if start_date is None:
        today = date.today()
        start_date = today - timedelta(days=today.weekday())  # Lunes de esta semana
    
    days = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        summary = _get_day_summary(db, user, day)
        days.append(summary)
    
    # Calcular totales de la semana
    total = sum(d.total_habits for d in days)
    completed = sum(d.completed for d in days)
    
    return {
        "week_start": start_date.isoformat(),
        "week_end": (start_date + timedelta(days=6)).isoformat(),
        "total_habits": total,
        "completed": completed,
        "percentage": round((completed / total * 100) if total > 0 else 0, 1),
        "days": days
    }


@app.get("/habits/{habit_id}/history", tags=["Habit Logs"])
def get_habit_history(
    habit_id: int,
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Historial de un hábito específico (últimos N días)"""
    habit = db.query(Habit).filter(
        Habit.id == habit_id, Habit.user_id == user.id
    ).first()
    if not habit:
        raise HTTPException(status_code=404, detail="Hábito no encontrado")
    
    start = date.today() - timedelta(days=days)
    logs = db.query(HabitLog).filter(
        HabitLog.habit_id == habit_id,
        HabitLog.date >= start
    ).order_by(HabitLog.date.desc()).all()
    
    # Crear mapa de calor
    heatmap = {}
    for d in range(days):
        day = start + timedelta(days=d)
        log = next((l for l in logs if l.date == day), None)
        heatmap[day.isoformat()] = {
            "completed": log.completed if log else False,
            "quantity": log.quantity_logged if log else 0
        }
    
    completed_count = sum(1 for l in logs if l.completed)
    
    return {
        "habit": HabitResponse.model_validate(habit),
        "days_tracked": days,
        "completed_count": completed_count,
        "completion_rate": round((completed_count / days * 100), 1),
        "current_streak": habit.current_streak,
        "best_streak": habit.best_streak,
        "heatmap": heatmap
    }


def _get_day_summary(db: Session, user: User, day: date) -> DaySummary:
    """Helper: genera el resumen de un día"""
    # Hábitos activos que aplican ese día
    active_habits = db.query(Habit).filter(
        Habit.user_id == user.id, Habit.active == True, Habit.archived == False
    ).all()
    
    applicable = [h for h in active_habits if habit_applies_today(h, day)]
    
    # Logs del día
    logs = db.query(HabitLog).filter(
        HabitLog.user_id == user.id,
        HabitLog.date == day
    ).all()
    
    completed = sum(1 for l in logs if l.completed)
    total = len(applicable)
    
    return DaySummary(
        date=day,
        total_habits=total,
        completed=completed,
        percentage=round((completed / total * 100) if total > 0 else 0, 1),
        habits=[HabitLogResponse.model_validate(l) for l in logs]
    )


# =============================================================================
# ===================== SECCIÓN 4: ROUTINES ===================================
# =============================================================================

@app.post("/routines", response_model=RoutineResponse, tags=["Routines"])
def create_routine(data: RoutineCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Crea una rutina nueva con sus pasos"""
    max_order = db.query(func.max(Routine.order)).filter(
        Routine.user_id == user.id
    ).scalar() or 0
    
    routine = Routine(
        user_id=user.id,
        name=data.name,
        icon=data.icon,
        description=data.description,
        scheduled_time=data.scheduled_time,
        scheduled_days=data.scheduled_days,
        display_mode=data.display_mode,
        order=max_order + 1
    )
    db.add(routine)
    db.flush()  # Para obtener el ID antes del commit
    
    # Crear pasos
    for step_data in data.steps:
        step = RoutineStep(
            user_id=user.id,
            routine_id=routine.id,
            step_order=step_data.step_order,
            description=step_data.description,
            duration_minutes=step_data.duration_minutes,
            linked_habit_id=step_data.linked_habit_id
        )
        db.add(step)
    
    db.commit()
    db.refresh(routine)
    return routine


@app.get("/routines", response_model=list[RoutineResponse], tags=["Routines"])
def list_routines(
    active_only: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista todas las rutinas del usuario"""
    query = db.query(Routine).filter(Routine.user_id == user.id)
    if active_only:
        query = query.filter(Routine.active == True)
    return query.order_by(Routine.order).all()


@app.get("/routines/{routine_id}", response_model=RoutineResponse, tags=["Routines"])
def get_routine(routine_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Obtiene una rutina con sus pasos"""
    routine = db.query(Routine).filter(
        Routine.id == routine_id, Routine.user_id == user.id
    ).first()
    if not routine:
        raise HTTPException(status_code=404, detail="Rutina no encontrada")
    return routine


@app.patch("/routines/{routine_id}", response_model=RoutineResponse, tags=["Routines"])
def update_routine(
    routine_id: int, data: RoutineUpdate,
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Actualiza una rutina"""
    routine = db.query(Routine).filter(
        Routine.id == routine_id, Routine.user_id == user.id
    ).first()
    if not routine:
        raise HTTPException(status_code=404, detail="Rutina no encontrada")
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(routine, key, value)
    
    db.commit()
    db.refresh(routine)
    return routine


@app.put("/routines/{routine_id}/steps", response_model=RoutineResponse, tags=["Routines"])
def replace_routine_steps(
    routine_id: int,
    steps: list[RoutineStepCreate],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reemplaza TODOS los pasos de una rutina (borra los actuales y crea nuevos)"""
    routine = db.query(Routine).filter(
        Routine.id == routine_id, Routine.user_id == user.id
    ).first()
    if not routine:
        raise HTTPException(status_code=404, detail="Rutina no encontrada")
    
    # Borrar pasos actuales
    db.query(RoutineStep).filter(RoutineStep.routine_id == routine_id).delete()
    
    # Crear nuevos
    for step_data in steps:
        step = RoutineStep(
            user_id=user.id,
            routine_id=routine_id,
            step_order=step_data.step_order,
            description=step_data.description,
            duration_minutes=step_data.duration_minutes,
            linked_habit_id=step_data.linked_habit_id
        )
        db.add(step)
    
    db.commit()
    db.refresh(routine)
    return routine


@app.delete("/routines/{routine_id}", tags=["Routines"])
def delete_routine(routine_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Elimina una rutina y todos sus pasos"""
    routine = db.query(Routine).filter(
        Routine.id == routine_id, Routine.user_id == user.id
    ).first()
    if not routine:
        raise HTTPException(status_code=404, detail="Rutina no encontrada")
    
    db.delete(routine)
    db.commit()
    return {"message": f"Rutina '{routine.name}' eliminada"}


# =============================================================================
# ===================== SECCIÓN 5: REMINDERS ==================================
# =============================================================================

@app.post("/reminders", response_model=ReminderResponse, tags=["Reminders"])
def create_reminder(data: ReminderCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Crea un recordatorio nuevo"""
    reminder = Reminder(
        user_id=user.id,
        type=data.type,
        time=data.time,
        days=data.days,
        message=data.message,
        linked_routine_id=data.linked_routine_id
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


@app.get("/reminders", response_model=list[ReminderResponse], tags=["Reminders"])
def list_reminders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lista todos los recordatorios del usuario"""
    return db.query(Reminder).filter(Reminder.user_id == user.id).all()


@app.patch("/reminders/{reminder_id}", response_model=ReminderResponse, tags=["Reminders"])
def update_reminder(
    reminder_id: int, data: ReminderUpdate,
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Actualiza un recordatorio"""
    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id, Reminder.user_id == user.id
    ).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado")
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(reminder, key, value)
    
    db.commit()
    db.refresh(reminder)
    return reminder


@app.delete("/reminders/{reminder_id}", tags=["Reminders"])
def delete_reminder(reminder_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Elimina un recordatorio"""
    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id, Reminder.user_id == user.id
    ).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado")
    
    db.delete(reminder)
    db.commit()
    return {"message": "Recordatorio eliminado"}


# =============================================================================
# ===================== SECCIÓN 6: TASKS ======================================
# =============================================================================

@app.post("/tasks", response_model=TaskResponse, tags=["Tasks"])
def create_task(data: TaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Crea una tarea nueva"""
    task = Task(
        user_id=user.id,
        title=data.title,
        description=data.description,
        priority=data.priority,
        due_date=data.due_date,
        due_time=data.due_time
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@app.get("/tasks", response_model=list[TaskResponse], tags=["Tasks"])
def list_tasks(
    completed: Optional[bool] = None,
    priority: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista tareas con filtros opcionales"""
    query = db.query(Task).filter(Task.user_id == user.id)
    
    if completed is not None:
        query = query.filter(Task.completed == completed)
    if priority:
        query = query.filter(Task.priority == priority)
    
    return query.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).all()


@app.patch("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
def update_task(
    task_id: int, data: TaskUpdate,
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Actualiza una tarea"""
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    update_data = data.model_dump(exclude_unset=True)
    
    # Si se marca como completada, registrar timestamp y dar XP
    if "completed" in update_data and update_data["completed"] and not task.completed:
        update_data["completed_at"] = datetime.utcnow()
        award_xp(db, user, "task_complete")
    
    for key, value in update_data.items():
        setattr(task, key, value)
    
    db.commit()
    db.refresh(task)
    return task


@app.delete("/tasks/{task_id}", tags=["Tasks"])
def delete_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Elimina una tarea"""
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    db.delete(task)
    db.commit()
    return {"message": "Tarea eliminada"}


# =============================================================================
# ===================== SECCIÓN 7: GOALS ======================================
# =============================================================================

@app.post("/goals", response_model=GoalResponse, tags=["Goals"])
def create_goal(data: GoalCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Crea un objetivo a largo plazo con hitos opcionales"""
    goal = Goal(
        user_id=user.id,
        title=data.title,
        description=data.description,
        icon=data.icon,
        target_date=data.target_date
    )
    db.add(goal)
    db.flush()
    
    for ms_data in data.milestones:
        milestone = GoalMilestone(
            goal_id=goal.id,
            title=ms_data.title,
            order=ms_data.order
        )
        db.add(milestone)
    
    db.commit()
    db.refresh(goal)
    return goal


@app.get("/goals", response_model=list[GoalResponse], tags=["Goals"])
def list_goals(
    completed: Optional[bool] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lista objetivos"""
    query = db.query(Goal).filter(Goal.user_id == user.id)
    if completed is not None:
        query = query.filter(Goal.completed == completed)
    return query.order_by(Goal.created_at.desc()).all()


@app.patch("/goals/{goal_id}", response_model=GoalResponse, tags=["Goals"])
def update_goal(
    goal_id: int, data: GoalUpdate,
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Actualiza un objetivo"""
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    
    update_data = data.model_dump(exclude_unset=True)
    
    if "completed" in update_data and update_data["completed"] and not goal.completed:
        update_data["completed_at"] = datetime.utcnow()
        update_data["progress"] = 100.0
    
    for key, value in update_data.items():
        setattr(goal, key, value)
    
    db.commit()
    db.refresh(goal)
    return goal


@app.patch("/goals/{goal_id}/milestones/{milestone_id}", tags=["Goals"])
def toggle_milestone(
    goal_id: int, milestone_id: int,
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Marca/desmarca un hito de un objetivo"""
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    
    milestone = db.query(GoalMilestone).filter(
        GoalMilestone.id == milestone_id, GoalMilestone.goal_id == goal_id
    ).first()
    if not milestone:
        raise HTTPException(status_code=404, detail="Hito no encontrado")
    
    milestone.completed = not milestone.completed
    milestone.completed_at = datetime.utcnow() if milestone.completed else None
    
    # Recalcular progreso del objetivo
    total_milestones = db.query(GoalMilestone).filter(GoalMilestone.goal_id == goal_id).count()
    completed_milestones = db.query(GoalMilestone).filter(
        GoalMilestone.goal_id == goal_id, GoalMilestone.completed == True
    ).count()
    
    if total_milestones > 0:
        goal.progress = round((completed_milestones / total_milestones) * 100, 1)
    
    db.commit()
    return {"milestone": milestone.title, "completed": milestone.completed, "goal_progress": goal.progress}


@app.delete("/goals/{goal_id}", tags=["Goals"])
def delete_goal(goal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Elimina un objetivo y sus hitos"""
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    
    db.delete(goal)
    db.commit()
    return {"message": f"Objetivo '{goal.title}' eliminado"}


# =============================================================================
# ===================== SECCIÓN 8: TRACKING ===================================
# =============================================================================

# ── MOOD ──

@app.post("/tracking/mood", response_model=MoodLogResponse, tags=["Tracking"])
def log_mood(data: MoodLogCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registra el estado de ánimo del día"""
    existing = db.query(MoodLog).filter(
        MoodLog.user_id == user.id, MoodLog.date == data.date
    ).first()
    
    if existing:
        existing.level = data.level
        existing.note = data.note
        db.commit()
        db.refresh(existing)
        return existing
    
    log = MoodLog(user_id=user.id, date=data.date, level=data.level, note=data.note)
    db.add(log)
    award_xp(db, user, "mood_log")
    db.commit()
    db.refresh(log)
    return log


@app.get("/tracking/mood", response_model=list[MoodLogResponse], tags=["Tracking"])
def list_mood(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Historial de mood"""
    start = date.today() - timedelta(days=days)
    return db.query(MoodLog).filter(
        MoodLog.user_id == user.id, MoodLog.date >= start
    ).order_by(MoodLog.date.desc()).all()


# ── SLEEP ──

@app.post("/tracking/sleep", response_model=SleepLogResponse, tags=["Tracking"])
def log_sleep(data: SleepLogCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registra horas de sueño"""
    existing = db.query(SleepLog).filter(
        SleepLog.user_id == user.id, SleepLog.date == data.date
    ).first()
    
    if existing:
        existing.hours = data.hours
        existing.bedtime = data.bedtime
        existing.wake_time = data.wake_time
        existing.quality = data.quality
        db.commit()
        db.refresh(existing)
        return existing
    
    log = SleepLog(
        user_id=user.id, date=data.date, hours=data.hours,
        bedtime=data.bedtime, wake_time=data.wake_time, quality=data.quality
    )
    db.add(log)
    award_xp(db, user, "sleep_log")
    db.commit()
    db.refresh(log)
    return log


@app.get("/tracking/sleep", response_model=list[SleepLogResponse], tags=["Tracking"])
def list_sleep(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    start = date.today() - timedelta(days=days)
    return db.query(SleepLog).filter(
        SleepLog.user_id == user.id, SleepLog.date >= start
    ).order_by(SleepLog.date.desc()).all()


# ── EXERCISE ──

@app.post("/tracking/exercise", response_model=ExerciseLogResponse, tags=["Tracking"])
def log_exercise(data: ExerciseLogCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registra ejercicio"""
    log = ExerciseLog(
        user_id=user.id, date=data.date, exercise_type=data.exercise_type,
        duration_minutes=data.duration_minutes, intensity=data.intensity, notes=data.notes
    )
    db.add(log)
    award_xp(db, user, "exercise_log")
    db.commit()
    db.refresh(log)
    return log


@app.get("/tracking/exercise", response_model=list[ExerciseLogResponse], tags=["Tracking"])
def list_exercise(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    start = date.today() - timedelta(days=days)
    return db.query(ExerciseLog).filter(
        ExerciseLog.user_id == user.id, ExerciseLog.date >= start
    ).order_by(ExerciseLog.date.desc()).all()


# ── WATER ──

@app.post("/tracking/water", response_model=WaterLogResponse, tags=["Tracking"])
def log_water(data: WaterLogCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registra vasos de agua (crea o actualiza el día)"""
    existing = db.query(WaterLog).filter(
        WaterLog.user_id == user.id, WaterLog.date == data.date
    ).first()
    
    if existing:
        existing.glasses = data.glasses
        db.commit()
        db.refresh(existing)
        return existing
    
    log = WaterLog(user_id=user.id, date=data.date, glasses=data.glasses)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@app.patch("/tracking/water/add", response_model=WaterLogResponse, tags=["Tracking"])
def add_water_glass(data: WaterLogUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Añade vasos de agua al día (incrementa, no reemplaza)"""
    existing = db.query(WaterLog).filter(
        WaterLog.user_id == user.id, WaterLog.date == data.date
    ).first()
    
    if existing:
        existing.glasses += data.add_glasses
        db.commit()
        db.refresh(existing)
        return existing
    
    log = WaterLog(user_id=user.id, date=data.date, glasses=data.add_glasses)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@app.get("/tracking/water/today", response_model=WaterLogResponse, tags=["Tracking"])
def get_water_today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Vasos de agua de hoy"""
    today = date.today()
    log = db.query(WaterLog).filter(
        WaterLog.user_id == user.id, WaterLog.date == today
    ).first()
    
    if not log:
        log = WaterLog(user_id=user.id, date=today, glasses=0)
        db.add(log)
        db.commit()
        db.refresh(log)
    
    return log


# ── WEIGHT ──

@app.post("/tracking/weight", response_model=WeightLogResponse, tags=["Tracking"])
def log_weight(data: WeightLogCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registra peso corporal"""
    existing = db.query(WeightLog).filter(
        WeightLog.user_id == user.id, WeightLog.date == data.date
    ).first()
    
    if existing:
        existing.weight_kg = data.weight_kg
        db.commit()
        db.refresh(existing)
        return existing
    
    log = WeightLog(user_id=user.id, date=data.date, weight_kg=data.weight_kg)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@app.get("/tracking/weight", response_model=list[WeightLogResponse], tags=["Tracking"])
def list_weight(
    days: int = Query(default=90, ge=1, le=365),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    start = date.today() - timedelta(days=days)
    return db.query(WeightLog).filter(
        WeightLog.user_id == user.id, WeightLog.date >= start
    ).order_by(WeightLog.date.desc()).all()


# ── JOURNAL ──

@app.post("/tracking/journal", response_model=JournalEntryResponse, tags=["Tracking"])
def create_journal_entry(data: JournalEntryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Escribe una entrada de diario"""
    entry = JournalEntry(user_id=user.id, date=data.date, content=data.content)
    db.add(entry)
    award_xp(db, user, "journal_entry")
    db.commit()
    db.refresh(entry)
    return entry


@app.get("/tracking/journal", response_model=list[JournalEntryResponse], tags=["Tracking"])
def list_journal(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    start = date.today() - timedelta(days=days)
    return db.query(JournalEntry).filter(
        JournalEntry.user_id == user.id, JournalEntry.date >= start
    ).order_by(JournalEntry.date.desc()).all()


# ── GRATITUDE ──

@app.post("/tracking/gratitude", response_model=GratitudeEntryResponse, tags=["Tracking"])
def create_gratitude(data: GratitudeEntryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registra las 3 cosas por las que estás agradecido hoy"""
    existing = db.query(GratitudeEntry).filter(
        GratitudeEntry.user_id == user.id, GratitudeEntry.date == data.date
    ).first()
    
    if existing:
        existing.item_1 = data.item_1
        existing.item_2 = data.item_2
        existing.item_3 = data.item_3
        db.commit()
        db.refresh(existing)
        return existing
    
    entry = GratitudeEntry(
        user_id=user.id, date=data.date,
        item_1=data.item_1, item_2=data.item_2, item_3=data.item_3
    )
    db.add(entry)
    award_xp(db, user, "gratitude_entry")
    db.commit()
    db.refresh(entry)
    return entry


@app.get("/tracking/gratitude", response_model=list[GratitudeEntryResponse], tags=["Tracking"])
def list_gratitude(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    start = date.today() - timedelta(days=days)
    return db.query(GratitudeEntry).filter(
        GratitudeEntry.user_id == user.id, GratitudeEntry.date >= start
    ).order_by(GratitudeEntry.date.desc()).all()


# ── EXPENSES ──

@app.post("/tracking/expenses", response_model=ExpenseLogResponse, tags=["Tracking"])
def log_expense(data: ExpenseLogCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Registra un gasto"""
    log = ExpenseLog(
        user_id=user.id, date=data.date, amount=data.amount,
        category=data.category, description=data.description
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@app.get("/tracking/expenses", response_model=list[ExpenseLogResponse], tags=["Tracking"])
def list_expenses(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    start = date.today() - timedelta(days=days)
    return db.query(ExpenseLog).filter(
        ExpenseLog.user_id == user.id, ExpenseLog.date >= start
    ).order_by(ExpenseLog.date.desc()).all()


@app.get("/tracking/expenses/summary", tags=["Tracking"])
def expenses_summary(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Resumen de gastos por categoría"""
    start = date.today() - timedelta(days=days)
    expenses = db.query(ExpenseLog).filter(
        ExpenseLog.user_id == user.id, ExpenseLog.date >= start
    ).all()
    
    by_category = {}
    total = 0
    for exp in expenses:
        cat = exp.category or "Sin categoría"
        by_category[cat] = by_category.get(cat, 0) + exp.amount
        total += exp.amount
    
    return {
        "period_days": days,
        "total": round(total, 2),
        "by_category": {k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda x: -x[1])},
        "daily_average": round(total / days, 2) if days > 0 else 0
    }


# =============================================================================
# ===================== SECCIÓN 9: GAMIFICATION ===============================
# =============================================================================

@app.get("/gamification/level", tags=["Gamification"])
def get_my_level(user: User = Depends(get_current_user)):
    """Devuelve info del nivel actual del usuario"""
    return get_level_info(user)


@app.get("/gamification/achievements", tags=["Gamification"])
def get_my_achievements(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lista todos los logros (desbloqueados y bloqueados)"""
    all_achievements = db.query(Achievement).all()
    user_achievements = db.query(UserAchievement).filter(
        UserAchievement.user_id == user.id
    ).all()
    
    unlocked_map = {ua.achievement_id: ua.unlocked_at for ua in user_achievements}
    
    result = []
    for ach in all_achievements:
        result.append({
            "id": ach.id,
            "code": ach.code,
            "name": ach.name,
            "description": ach.description,
            "icon": ach.icon,
            "xp_reward": ach.xp_reward,
            "unlocked": ach.id in unlocked_map,
            "unlocked_at": unlocked_map.get(ach.id)
        })
    
    return result


@app.get("/gamification/streaks", tags=["Gamification"])
def get_my_streaks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Devuelve todas las rachas del usuario"""
    habits = db.query(Habit).filter(
        Habit.user_id == user.id, Habit.active == True, Habit.archived == False
    ).all()
    
    return {
        "global": {
            "current": user.global_streak,
            "best": user.best_global_streak
        },
        "habits": [
            {
                "habit_id": h.id,
                "name": h.name,
                "icon": h.icon,
                "current_streak": h.current_streak,
                "best_streak": h.best_streak
            }
            for h in habits
        ]
    }


@app.get("/gamification/quote", tags=["Gamification"])
def get_quote(db: Session = Depends(get_db)):
    """Devuelve una cita motivacional aleatoria (no requiere autenticación)"""
    return get_random_quote(db)


# =============================================================================
# ===================== SECCIÓN 10: REFLECTIONS ===============================
# =============================================================================

@app.post("/reflections", response_model=ReflectionResponse, tags=["Reflections"])
def create_reflection(data: ReflectionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Crea o actualiza una reflexión semanal"""
    existing = db.query(Reflection).filter(
        Reflection.user_id == user.id, Reflection.week_start == data.week_start
    ).first()
    
    if existing:
        if data.best_moment is not None:
            existing.best_moment = data.best_moment
        if data.improvement is not None:
            existing.improvement = data.improvement
        if data.lesson is not None:
            existing.lesson = data.lesson
        if data.next_week_focus is not None:
            existing.next_week_focus = data.next_week_focus
        db.commit()
        db.refresh(existing)
        return existing
    
    reflection = Reflection(
        user_id=user.id,
        week_start=data.week_start,
        best_moment=data.best_moment,
        improvement=data.improvement,
        lesson=data.lesson,
        next_week_focus=data.next_week_focus
    )
    db.add(reflection)
    award_xp(db, user, "reflection_complete")
    db.commit()
    db.refresh(reflection)
    return reflection


@app.get("/reflections", response_model=list[ReflectionResponse], tags=["Reflections"])
def list_reflections(
    limit: int = Query(default=10, ge=1, le=52),
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return db.query(Reflection).filter(
        Reflection.user_id == user.id
    ).order_by(Reflection.week_start.desc()).limit(limit).all()


# =============================================================================
# ===================== SECCIÓN 11: POMODORO ==================================
# =============================================================================

@app.post("/pomodoro/start", response_model=PomodoroResponse, tags=["Pomodoro"])
def start_pomodoro(data: PomodoroStart, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Inicia una sesión de pomodoro"""
    session = PomodoroSession(
        user_id=user.id,
        date=date.today(),
        work_minutes=data.work_minutes,
        break_minutes=data.break_minutes
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@app.patch("/pomodoro/{session_id}/complete", response_model=PomodoroResponse, tags=["Pomodoro"])
def complete_pomodoro(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Marca un pomodoro como completado"""
    session = db.query(PomodoroSession).filter(
        PomodoroSession.id == session_id, PomodoroSession.user_id == user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    session.completed = True
    session.finished_at = datetime.utcnow()
    award_xp(db, user, "pomodoro_complete")
    
    # Verificar logro de pomodoros
    check_and_unlock_achievements(db, user)
    
    db.commit()
    db.refresh(session)
    return session


@app.get("/pomodoro/today", tags=["Pomodoro"])
def pomodoro_today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Resumen de pomodoros de hoy"""
    today = date.today()
    sessions = db.query(PomodoroSession).filter(
        PomodoroSession.user_id == user.id, PomodoroSession.date == today
    ).all()
    
    completed = [s for s in sessions if s.completed]
    total_minutes = sum(s.work_minutes for s in completed)
    
    return {
        "date": today.isoformat(),
        "total_sessions": len(sessions),
        "completed_sessions": len(completed),
        "total_focus_minutes": total_minutes
    }


# =============================================================================
# ===================== SECCIÓN 12: ONBOARDING ================================
# =============================================================================

@app.post("/onboarding", tags=["Onboarding"])
def complete_onboarding(
    data: OnboardingData,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Procesa las respuestas del onboarding y configura el sistema.
    
    Esto:
      1. Actualiza datos del usuario (nombre, timezone)
      2. Crea hábitos sugeridos según sus objetivos
      3. Crea rutinas básicas de mañana/noche
      4. Configura recordatorios según preferencias
      5. Marca onboarding como completado
    """
    # Actualizar usuario
    user.name = data.name
    user.timezone = data.timezone or "Europe/Madrid"
    user.onboarding_completed = True
    
    # ── Crear hábitos sugeridos ──
    habit_suggestions = {
        "health": [
            {"name": "Ejercicio", "icon": "🏋️", "category": "health"},
            {"name": "Beber agua", "icon": "💧", "category": "health", "type": "quantity", "target": 8, "unit": "vasos"},
            {"name": "Dormir 7-8h", "icon": "😴", "category": "health"},
        ],
        "mental": [
            {"name": "Meditar", "icon": "🧘", "category": "mental"},
            {"name": "Leer", "icon": "📖", "category": "learning"},
            {"name": "Gratitud", "icon": "🙏", "category": "mental"},
        ],
        "productivity": [
            {"name": "Tarea principal del día", "icon": "🎯", "category": "productivity"},
            {"name": "Planificar mañana", "icon": "📝", "category": "productivity"},
            {"name": "Sin redes sociales 1h", "icon": "📵", "category": "productivity"},
        ],
        "social": [
            {"name": "Llamar/escribir a alguien", "icon": "📱", "category": "social"},
            {"name": "Acto de amabilidad", "icon": "💚", "category": "social"},
        ],
    }
    
    order = 1
    for goal in data.goals:
        suggestions = habit_suggestions.get(goal, [])
        for s in suggestions:
            habit = Habit(
                user_id=user.id,
                name=s["name"],
                icon=s["icon"],
                category=s["category"],
                habit_type=s.get("type", "boolean"),
                target_quantity=s.get("target"),
                quantity_unit=s.get("unit"),
                order=order
            )
            db.add(habit)
            order += 1
    
    # Añadir hábitos personalizados que eligió
    for habit_name in data.preferred_habits:
        if habit_name.strip():
            habit = Habit(
                user_id=user.id,
                name=habit_name.strip(),
                icon="✅",
                category="other",
                order=order
            )
            db.add(habit)
            order += 1
    
    # ── Crear rutinas básicas ──
    morning_routine = Routine(
        user_id=user.id, name="Rutina de mañana", icon="🌅",
        scheduled_time=data.wake_time or "07:00",
        scheduled_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        display_mode="list", order=1
    )
    db.add(morning_routine)
    db.flush()
    
    morning_steps = [
        "Levantarse sin snooze", "Beber un vaso de agua",
        "Estiramientos 5 min", "Ducha", "Desayunar", "Revisar objetivos del día"
    ]
    for i, step_desc in enumerate(morning_steps, 1):
        db.add(RoutineStep(
            user_id=user.id, routine_id=morning_routine.id,
            step_order=i, description=step_desc
        ))
    
    night_routine = Routine(
        user_id=user.id, name="Rutina de noche", icon="🌙",
        scheduled_time=data.sleep_time or "23:00",
        scheduled_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        display_mode="list", order=2
    )
    db.add(night_routine)
    db.flush()
    
    night_steps = [
        "Apagar pantallas", "Preparar ropa de mañana",
        "Diario / Reflexión", "Leer 15 min", "Luces apagadas"
    ]
    for i, step_desc in enumerate(night_steps, 1):
        db.add(RoutineStep(
            user_id=user.id, routine_id=night_routine.id,
            step_order=i, description=step_desc
        ))
    
    # ── Actualizar recordatorios según frecuencia preferida ──
    # Los recordatorios por defecto ya se crearon al registrarse
    # Aquí solo ajustamos las horas según wake_time y sleep_time
    if data.wake_time:
        morning_rem = db.query(Reminder).filter(
            Reminder.user_id == user.id, Reminder.type == "morning"
        ).first()
        if morning_rem:
            morning_rem.time = data.wake_time
    
    if data.sleep_time:
        night_rem = db.query(Reminder).filter(
            Reminder.user_id == user.id, Reminder.type == "night"
        ).first()
        if night_rem:
            # Rutina de noche 30 min antes de dormir
            sleep_hour = int(data.sleep_time.split(":")[0])
            sleep_min = int(data.sleep_time.split(":")[1])
            night_hour = sleep_hour if sleep_min >= 30 else sleep_hour - 1
            night_min = sleep_min - 30 if sleep_min >= 30 else sleep_min + 30
            night_rem.time = f"{night_hour:02d}:{night_min:02d}"
    
    db.commit()
    
    logger.info(f"🎓 Onboarding completado: {user.name}")
    
    return {
        "message": "Onboarding completado",
        "habits_created": order - 1,
        "routines_created": 2,
        "reminders_configured": 5
    }


# =============================================================================
# ===================== SECCIÓN 13: STATS / CORRELATIONS ======================
# =============================================================================

@app.get("/stats/correlations", tags=["Stats"])
def get_correlations(
    days: int = Query(default=30, ge=7, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Analiza correlaciones entre mood y hábitos completados.
    Ejemplo: "Los días que medita, su mood sube un 20%"
    """
    start = date.today() - timedelta(days=days)
    
    # Obtener moods
    moods = db.query(MoodLog).filter(
        MoodLog.user_id == user.id, MoodLog.date >= start
    ).all()
    mood_map = {m.date: m.level for m in moods}
    
    if len(mood_map) < 7:
        return {"message": "Se necesitan al menos 7 días de datos de mood para analizar correlaciones"}
    
    # Obtener hábitos activos
    habits = db.query(Habit).filter(
        Habit.user_id == user.id, Habit.active == True
    ).all()
    
    correlations = []
    
    for habit in habits:
        logs = db.query(HabitLog).filter(
            HabitLog.habit_id == habit.id, HabitLog.date >= start
        ).all()
        
        mood_with = []     # mood los días que completó el hábito
        mood_without = []  # mood los días que NO completó
        
        for log in logs:
            if log.date in mood_map:
                if log.completed:
                    mood_with.append(mood_map[log.date])
                else:
                    mood_without.append(mood_map[log.date])
        
        if mood_with and mood_without:
            avg_with = sum(mood_with) / len(mood_with)
            avg_without = sum(mood_without) / len(mood_without)
            difference = round(avg_with - avg_without, 2)
            
            correlations.append({
                "habit": habit.name,
                "icon": habit.icon,
                "mood_when_done": round(avg_with, 2),
                "mood_when_skipped": round(avg_without, 2),
                "mood_difference": difference,
                "insight": _generate_insight(habit.name, difference)
            })
    
    # Ordenar por mayor impacto
    correlations.sort(key=lambda x: abs(x["mood_difference"]), reverse=True)
    
    return {"period_days": days, "correlations": correlations}


def _generate_insight(habit_name: str, diff: float) -> str:
    """Genera un insight legible sobre la correlación"""
    if diff > 0.5:
        return f"Los días que completa '{habit_name}', su ánimo mejora significativamente"
    elif diff > 0.2:
        return f"'{habit_name}' tiene un impacto positivo en su estado de ánimo"
    elif diff < -0.2:
        return f"Curiosamente, '{habit_name}' parece no correlacionar con mejor ánimo"
    else:
        return f"'{habit_name}' no muestra un impacto claro en su ánimo"


@app.get("/stats/overview", tags=["Stats"])
def get_stats_overview(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resumen general de estadísticas del usuario"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    
    # Hábitos completados
    total_habits_ever = db.query(HabitLog).filter(
        HabitLog.user_id == user.id, HabitLog.completed == True
    ).count()
    
    habits_this_week = db.query(HabitLog).filter(
        HabitLog.user_id == user.id,
        HabitLog.completed == True,
        HabitLog.date >= week_start
    ).count()
    
    habits_this_month = db.query(HabitLog).filter(
        HabitLog.user_id == user.id,
        HabitLog.completed == True,
        HabitLog.date >= month_start
    ).count()
    
    # Tareas
    pending_tasks = db.query(Task).filter(
        Task.user_id == user.id, Task.completed == False
    ).count()
    
    # Pomodoros hoy
    pomodoros_today = db.query(PomodoroSession).filter(
        PomodoroSession.user_id == user.id,
        PomodoroSession.date == today,
        PomodoroSession.completed == True
    ).count()
    
    # Logros
    total_achievements = db.query(Achievement).count()
    unlocked_achievements = db.query(UserAchievement).filter(
        UserAchievement.user_id == user.id
    ).count()
    
    # Días usando NexoTime
    days_active = (datetime.utcnow() - user.created_at).days
    
    return {
        "user": {
            "name": user.name,
            "level": user.level,
            "title": get_level_info(user)["title"],
            "xp": user.xp,
            "days_active": days_active,
            "mode": user.mode
        },
        "streaks": {
            "global_current": user.global_streak,
            "global_best": user.best_global_streak
        },
        "habits": {
            "total_completed_ever": total_habits_ever,
            "completed_this_week": habits_this_week,
            "completed_this_month": habits_this_month
        },
        "tasks_pending": pending_tasks,
        "pomodoros_today": pomodoros_today,
        "achievements": {
            "unlocked": unlocked_achievements,
            "total": total_achievements,
            "percentage": round((unlocked_achievements / total_achievements * 100) if total_achievements > 0 else 0, 1)
        }
    }


# =============================================================================
# ===================== SECCIÓN 14: EXPORT ====================================
# =============================================================================

@app.get("/export/data", tags=["Export"])
def export_all_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Exporta TODOS los datos del usuario en formato JSON.
    Cumple con GDPR: el usuario tiene derecho a descargar sus datos.
    """
    habits = db.query(Habit).filter(Habit.user_id == user.id).all()
    habit_logs = db.query(HabitLog).filter(HabitLog.user_id == user.id).all()
    routines = db.query(Routine).filter(Routine.user_id == user.id).all()
    tasks = db.query(Task).filter(Task.user_id == user.id).all()
    goals = db.query(Goal).filter(Goal.user_id == user.id).all()
    moods = db.query(MoodLog).filter(MoodLog.user_id == user.id).all()
    sleep_logs = db.query(SleepLog).filter(SleepLog.user_id == user.id).all()
    exercise_logs = db.query(ExerciseLog).filter(ExerciseLog.user_id == user.id).all()
    water_logs = db.query(WaterLog).filter(WaterLog.user_id == user.id).all()
    weight_logs = db.query(WeightLog).filter(WeightLog.user_id == user.id).all()
    journal = db.query(JournalEntry).filter(JournalEntry.user_id == user.id).all()
    gratitude = db.query(GratitudeEntry).filter(GratitudeEntry.user_id == user.id).all()
    expenses = db.query(ExpenseLog).filter(ExpenseLog.user_id == user.id).all()
    
    return {
        "export_date": datetime.utcnow().isoformat(),
        "user": UserResponse.model_validate(user).model_dump(),
        "habits": [HabitResponse.model_validate(h).model_dump() for h in habits],
        "habit_logs": [HabitLogResponse.model_validate(l).model_dump() for l in habit_logs],
        "routines": [RoutineResponse.model_validate(r).model_dump() for r in routines],
        "tasks": [TaskResponse.model_validate(t).model_dump() for t in tasks],
        "goals": [GoalResponse.model_validate(g).model_dump() for g in goals],
        "mood_logs": [MoodLogResponse.model_validate(m).model_dump() for m in moods],
        "sleep_logs": [SleepLogResponse.model_validate(s).model_dump() for s in sleep_logs],
        "exercise_logs": [ExerciseLogResponse.model_validate(e).model_dump() for e in exercise_logs],
        "water_logs": [WaterLogResponse.model_validate(w).model_dump() for w in water_logs],
        "weight_logs": [WeightLogResponse.model_validate(w).model_dump() for w in weight_logs],
        "journal_entries": [JournalEntryResponse.model_validate(j).model_dump() for j in journal],
        "gratitude_entries": [GratitudeEntryResponse.model_validate(g).model_dump() for g in gratitude],
        "expense_logs": [ExpenseLogResponse.model_validate(e).model_dump() for e in expenses],
    }
