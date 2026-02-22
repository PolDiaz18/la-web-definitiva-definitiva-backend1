"""
=============================================================================
SCHEDULER.PY — Sistema de Recordatorios Automáticos
=============================================================================
Este es el "cerebro proactivo" de NexoTime. En vez de esperar a que
el usuario abra la app, NOSOTROS le buscamos a él.

Funciones:
  1. Recordatorios programados (mañana, mediodía, noche)
  2. Insistencia (si no marca hábitos, insiste 2 veces)
  3. Resumen diario nocturno
  4. Resumen semanal (domingo noche)
  5. Verificar rachas a medianoche

Usa APScheduler con CronTrigger para ejecutar tareas a horas específicas.

¿Cómo funciona?
  - Cada MINUTO se ejecuta check_reminders()
  - Compara la hora actual con los recordatorios de cada usuario
  - Si coincide → envía el mensaje por Telegram
  - Respeta: do_not_disturb, modo vacaciones, zona horaria del usuario
"""

import logging
from datetime import datetime, date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import pytz

from database import SessionLocal
from sqlalchemy.orm import Session
from models import *
from gamification import (
    habit_applies_today, get_random_quote, get_level_title,
    check_all_completed, update_global_streak
)

logger = logging.getLogger("nexotime.scheduler")

# Referencia global al bot (se asigna al arrancar)
bot_instance: Bot = None
scheduler: AsyncIOScheduler = None


def progress_bar(current: int, total: int, length: int = 10) -> str:
    if total == 0:
        return "░" * length + " 0%"
    filled = int(length * current / total)
    bar = "█" * filled + "░" * (length - filled)
    pct = round(current / total * 100)
    return f"{bar} {pct}%"


def color_emoji(pct: float) -> str:
    if pct >= 80: return "🟢"
    elif pct >= 50: return "🟡"
    return "🔴"


# =============================================================================
# ===================== ENVÍO DE MENSAJES =====================================
# =============================================================================

async def send_telegram_message(telegram_id: str, text: str, keyboard=None):
    """
    Envía un mensaje por Telegram a un usuario.
    Función centralizada para no repetir try/except en cada lugar.
    """
    if not bot_instance:
        logger.warning("Bot no inicializado, no se puede enviar mensaje")
        return False
    
    try:
        await bot_instance.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return True
    except Exception as e:
        logger.error(f"Error enviando mensaje a {telegram_id}: {e}")
        return False


# =============================================================================
# ===================== VERIFICAR RECORDATORIOS ===============================
# =============================================================================

async def check_reminders():
    """
    Se ejecuta cada minuto.
    Compara la hora actual (en la zona horaria del usuario) con sus recordatorios.
    Si coincide → envía el recordatorio correspondiente.
    """
    db = SessionLocal()
    
    try:
        # Obtener todos los usuarios con Telegram vinculado
        users = db.query(User).filter(
            User.telegram_id != None,
            User.do_not_disturb == False,
            User.mode != "vacation"
        ).all()
        
        for user in users:
            try:
                # Obtener hora actual en la zona horaria del usuario
                tz = pytz.timezone(user.timezone or "Europe/Madrid")
                user_now = datetime.now(tz)
                current_time = user_now.strftime("%H:%M")
                current_day_name = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][user_now.weekday()]
                
                # Buscar recordatorios que coincidan con esta hora
                reminders = db.query(Reminder).filter(
                    Reminder.user_id == user.id,
                    Reminder.active == True,
                    Reminder.time == current_time
                ).all()
                
                for reminder in reminders:
                    # Verificar si aplica hoy (por días)
                    if reminder.days and current_day_name not in reminder.days:
                        continue
                    
                    await _send_reminder(db, user, reminder, user_now)
            
            except Exception as e:
                logger.error(f"Error procesando recordatorios de {user.name}: {e}")
    
    finally:
        db.close()


async def _send_reminder(db: Session, user: User, reminder: Reminder, user_now: datetime):
    """Envía un recordatorio específico según su tipo"""
    today = user_now.date()
    
    if reminder.type == "morning":
        await _send_morning_reminder(db, user, today)
    
    elif reminder.type == "midday":
        await _send_midday_reminder(db, user, today)
    
    elif reminder.type == "evening":
        await _send_evening_reminder(db, user, today)
    
    elif reminder.type == "night":
        await _send_night_reminder(db, user, today)
    
    elif reminder.type == "summary":
        await _send_daily_summary(db, user, today)
    
    elif reminder.type == "weekly_summary":
        # Solo domingos
        if user_now.weekday() == 6:
            await _send_weekly_summary(db, user, today)
    
    elif reminder.type == "routine" and reminder.linked_routine_id:
        await _send_routine_reminder(db, user, reminder.linked_routine_id)
    
    elif reminder.type == "custom" and reminder.message:
        await send_telegram_message(user.telegram_id, reminder.message)


# =============================================================================
# ===================== TIPOS DE RECORDATORIO =================================
# =============================================================================

async def _send_morning_reminder(db: Session, user: User, today: date):
    """Recordatorio matutino: saludo + hábitos del día + cita"""
    habits = db.query(Habit).filter(
        Habit.user_id == user.id, Habit.active == True, Habit.archived == False
    ).all()
    applicable = [h for h in habits if habit_applies_today(h, today)]
    
    quote = get_random_quote(db)
    
    lines = [
        f"🌅 *Buenos días, {user.name}\\!*\n",
        f"Tiene *{len(applicable)} hábitos* para hoy\\.",
        f"🔥 Racha: {user.global_streak} días\n",
    ]
    
    for h in applicable[:5]:  # Max 5 para no saturar
        lines.append(f"  ⬜ {h.icon} {h.name}")
    
    if len(applicable) > 5:
        lines.append(f"  \\.\\.\\.y {len(applicable) - 5} más")
    
    lines.append(f"\n💡 _{quote['text']}_")
    
    # Botón para ver todos los hábitos
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Ver hábitos", callback_data="cmd_habitos")]
    ])
    
    await send_telegram_message(user.telegram_id, "\n".join(lines), keyboard)
    logger.info(f"🌅 Recordatorio mañana → {user.name}")


async def _send_midday_reminder(db: Session, user: User, today: date):
    """Recordatorio de mediodía: progreso + lo que falta"""
    habits = db.query(Habit).filter(
        Habit.user_id == user.id, Habit.active == True, Habit.archived == False
    ).all()
    applicable = [h for h in habits if habit_applies_today(h, today)]
    
    logs = db.query(HabitLog).filter(
        HabitLog.user_id == user.id, HabitLog.date == today, HabitLog.completed == True
    ).all()
    completed_ids = {l.habit_id for l in logs}
    
    done = len(completed_ids)
    total = len(applicable)
    pending = [h for h in applicable if h.id not in completed_ids]
    
    if done == total and total > 0:
        # Ya completó todo → felicitar
        await send_telegram_message(
            user.telegram_id,
            f"🎉 *¡{user.name}, ya completó todo\\!*\n\n"
            f"Todos los hábitos de hoy están marcados\\. Impresionante\\. 💎"
        )
        return
    
    pct = round(done / total * 100) if total > 0 else 0
    
    lines = [
        f"☀️ *Checkpoint de mediodía*\n",
        f"{progress_bar(done, total)} {color_emoji(pct)}\n",
    ]
    
    if pending:
        lines.append(f"Le faltan *{len(pending)}* hábitos:")
        for h in pending[:5]:
            lines.append(f"  ⬜ {h.icon} {h.name}")
    
    lines.append(f"\n¡Aún hay tiempo\\! 💪")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Marcar hábitos", callback_data="cmd_habitos")]
    ])
    
    await send_telegram_message(user.telegram_id, "\n".join(lines), keyboard)
    logger.info(f"☀️ Recordatorio mediodía → {user.name}")


async def _send_evening_reminder(db: Session, user: User, today: date):
    """
    Recordatorio de tarde/noche: insistencia si faltan hábitos.
    
    Tono más urgente que el de mediodía porque queda menos tiempo.
    Este es el recordatorio de "insistencia nivel 1".
    """
    habits = db.query(Habit).filter(
        Habit.user_id == user.id, Habit.active == True, Habit.archived == False
    ).all()
    applicable = [h for h in habits if habit_applies_today(h, today)]
    
    logs = db.query(HabitLog).filter(
        HabitLog.user_id == user.id, HabitLog.date == today, HabitLog.completed == True
    ).all()
    completed_ids = {l.habit_id for l in logs}
    
    done = len(completed_ids)
    total = len(applicable)
    pending = [h for h in applicable if h.id not in completed_ids]
    
    if done == total and total > 0:
        return  # Ya completó todo, no molestar
    
    if not pending:
        return
    
    pct = round(done / total * 100) if total > 0 else 0
    
    # Tono adaptado: más directo por la noche
    lines = [
        f"🌙 *{user.name}, el día no ha terminado*\n",
        f"{progress_bar(done, total)} {color_emoji(pct)}\n",
        f"Le quedan *{len(pending)}* hábitos por completar:",
    ]
    
    keyboard_buttons = []
    for h in pending:
        lines.append(f"  ⬜ {h.icon} {h.name}")
        keyboard_buttons.append([InlineKeyboardButton(
            f"✅ {h.icon} {h.name}", callback_data=f"habit_do_{h.id}"
        )])
    
    if user.global_streak > 0:
        lines.append(f"\n⚠️ ¡Su racha de *{user.global_streak} días* está en juego\\!")
    
    await send_telegram_message(
        user.telegram_id,
        "\n".join(lines),
        InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None
    )
    logger.info(f"🌙 Recordatorio noche (insistencia 1) → {user.name}")


async def _send_night_reminder(db: Session, user: User, today: date):
    """
    Último recordatorio del día: insistencia nivel 2.
    Tono más directo pero respetuoso. Es la última oportunidad.
    """
    habits = db.query(Habit).filter(
        Habit.user_id == user.id, Habit.active == True, Habit.archived == False
    ).all()
    applicable = [h for h in habits if habit_applies_today(h, today)]
    
    logs = db.query(HabitLog).filter(
        HabitLog.user_id == user.id, HabitLog.date == today, HabitLog.completed == True
    ).all()
    completed_ids = {l.habit_id for l in logs}
    
    done = len(completed_ids)
    total = len(applicable)
    pending = [h for h in applicable if h.id not in completed_ids]
    
    if done == total and total > 0:
        return  # Ya completó todo
    
    if not pending:
        return
    
    # Tono final: urgente pero motivador
    keyboard_buttons = []
    for h in pending:
        keyboard_buttons.append([InlineKeyboardButton(
            f"✅ {h.icon} {h.name}", callback_data=f"habit_do_{h.id}"
        )])
    
    streak_warning = ""
    if user.global_streak >= 7:
        streak_warning = f"\n\n🔥 {user.global_streak} días de racha\\. No los pierda\\."
    elif user.global_streak >= 3:
        streak_warning = f"\n\n🌱 Lleva {user.global_streak} días seguidos\\. No se detenga ahora\\."
    
    await send_telegram_message(
        user.telegram_id,
        f"⏰ *Última llamada, {user.name}*\n\n"
        f"Faltan *{len(pending)}* hábitos para cerrar el día\\.\n"
        f"Solo necesita unos minutos\\."
        f"{streak_warning}",
        InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None
    )
    logger.info(f"⏰ Recordatorio noche (insistencia 2) → {user.name}")


async def _send_daily_summary(db: Session, user: User, today: date):
    """
    Resumen del día completo. Se envía al final de la noche.
    Incluye hábitos, agua, mood, y mensaje de cierre.
    """
    habits = db.query(Habit).filter(
        Habit.user_id == user.id, Habit.active == True, Habit.archived == False
    ).all()
    applicable = [h for h in habits if habit_applies_today(h, today)]
    
    logs = db.query(HabitLog).filter(
        HabitLog.user_id == user.id, HabitLog.date == today
    ).all()
    log_map = {l.habit_id: l for l in logs}
    
    done = sum(1 for h in applicable if log_map.get(h.id) and log_map[h.id].completed)
    total = len(applicable)
    pct = round(done / total * 100) if total > 0 else 0
    
    # Agua
    water = db.query(WaterLog).filter(
        WaterLog.user_id == user.id, WaterLog.date == today
    ).first()
    
    # Mood
    mood = db.query(MoodLog).filter(
        MoodLog.user_id == user.id, MoodLog.date == today
    ).first()
    
    lines = [
        f"📊 *Resumen del día* {color_emoji(pct)}\n",
        f"*Hábitos:* {done}/{total}",
        f"{progress_bar(done, total)}\n",
    ]
    
    for h in applicable:
        log = log_map.get(h.id)
        status = "✅" if log and log.completed else "❌"
        lines.append(f"  {status} {h.icon} {h.name}")
    
    if water:
        lines.append(f"\n💧 Agua: {water.glasses}/{water.target} vasos")
    
    if mood:
        mood_emojis = {1: "😢", 2: "😞", 3: "😐", 4: "🙂", 5: "🤩"}
        lines.append(f"😊 Ánimo: {mood_emojis.get(mood.level, '😐')}")
    
    # Mensaje de cierre según rendimiento
    if pct == 100:
        lines.append(f"\n🏆 *¡Día perfecto\\!* Descanse bien\\, se lo ha ganado\\.")
    elif pct >= 70:
        lines.append(f"\n👍 Buen día\\. Mañana a por el 100%\\.")
    elif pct >= 40:
        lines.append(f"\n💪 Hay margen de mejora\\. Mañana será mejor\\.")
    else:
        lines.append(f"\n🌱 No pasa nada\\. Lo importante es no rendirse\\.")
    
    lines.append(f"\nBuenas noches, {user.name} 🌙")
    
    await send_telegram_message(user.telegram_id, "\n".join(lines))
    logger.info(f"📊 Resumen diario → {user.name} ({pct}%)")


async def _send_weekly_summary(db: Session, user: User, today: date):
    """Resumen semanal con estadísticas de la semana"""
    monday = today - timedelta(days=today.weekday())
    
    total_completed = 0
    total_habits = 0
    day_results = []
    day_names = ["L", "M", "X", "J", "V", "S", "D"]
    
    habits = db.query(Habit).filter(
        Habit.user_id == user.id, Habit.active == True, Habit.archived == False
    ).all()
    
    for i in range(7):
        day = monday + timedelta(days=i)
        applicable = [h for h in habits if habit_applies_today(h, day)]
        logs = db.query(HabitLog).filter(
            HabitLog.user_id == user.id, HabitLog.date == day, HabitLog.completed == True
        ).all()
        
        done = len(logs)
        total = len(applicable)
        total_completed += done
        total_habits += total
        
        check = "✅" if done == total and total > 0 else "❌" if total > 0 else "·"
        day_results.append(f"{day_names[i]} {check}")
    
    week_pct = round(total_completed / total_habits * 100) if total_habits > 0 else 0
    
    lines = [
        f"📅 *Resumen semanal* {color_emoji(week_pct)}\n",
        " ".join(day_results),
        f"\n*Total:* {total_completed}/{total_habits} hábitos",
        f"{progress_bar(total_completed, total_habits)}",
        f"\n🔥 Racha global: {user.global_streak} días",
        f"⚡ Nivel: {user.level} \\({get_level_title(user.level)}\\)",
        f"💰 XP: {user.xp}",
    ]
    
    # Mensaje motivacional según rendimiento
    if week_pct >= 90:
        lines.append(f"\n🏆 *Semana excepcional\\!* Usted es una máquina\\.")
    elif week_pct >= 70:
        lines.append(f"\n💪 Buena semana\\. La constancia paga\\.")
    elif week_pct >= 50:
        lines.append(f"\n📈 Semana decente\\. Puede dar más la próxima\\.")
    else:
        lines.append(f"\n🌱 Semana floja\\. La próxima será mejor\\.")
    
    lines.append(f"\n¿Listo para la reflexión semanal? Hágala desde la web\\.")
    
    await send_telegram_message(user.telegram_id, "\n".join(lines))
    logger.info(f"📅 Resumen semanal → {user.name} ({week_pct}%)")


async def _send_routine_reminder(db: Session, user: User, routine_id: int):
    """Envía una rutina como recordatorio"""
    routine = db.query(Routine).filter(Routine.id == routine_id).first()
    if not routine:
        return
    
    steps = db.query(RoutineStep).filter(
        RoutineStep.routine_id == routine_id
    ).order_by(RoutineStep.step_order).all()
    
    lines = [f"{routine.icon} *Es hora de: {routine.name}*\n"]
    
    for step in steps:
        time_str = f" \\({step.duration_minutes} min\\)" if step.duration_minutes else ""
        lines.append(f"{step.step_order}\\. {step.description}{time_str}")
    
    lines.append(f"\n💪 ¡Vamos\\!")
    
    await send_telegram_message(user.telegram_id, "\n".join(lines))
    logger.info(f"📋 Rutina recordatorio: {routine.name} → {user.name}")


# =============================================================================
# ===================== TAREA DE MEDIANOCHE ===================================
# =============================================================================

async def midnight_check():
    """
    Se ejecuta a las 00:05 hora del servidor.
    Verifica rachas de todos los usuarios para el día anterior.
    
    Si alguien no completó todos sus hábitos ayer, su racha global se rompe.
    """
    db = SessionLocal()
    
    try:
        yesterday = date.today() - timedelta(days=1)
        users = db.query(User).filter(
            User.telegram_id != None,
            User.mode != "vacation"  # Vacaciones no rompe racha
        ).all()
        
        for user in users:
            try:
                all_done = check_all_completed(db, user, yesterday)
                
                if not all_done and user.global_streak > 0:
                    old_streak = user.global_streak
                    user.global_streak = 0
                    db.commit()
                    
                    if old_streak >= 3:
                        await send_telegram_message(
                            user.telegram_id,
                            f"😔 Su racha de *{old_streak} días* se ha roto\\.\n\n"
                            f"No pasa nada\\. Hoy es un nuevo comienzo\\. 🌅\n"
                            f"Su mejor racha sigue siendo: {user.best_global_streak} días"
                        )
                        logger.info(f"💔 Racha rota: {user.name} ({old_streak} días)")
            
            except Exception as e:
                logger.error(f"Error en midnight_check para {user.name}: {e}")
    
    finally:
        db.close()


# =============================================================================
# ===================== INICIALIZAR SCHEDULER =================================
# =============================================================================

def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    """
    Crea y configura el scheduler con las tareas automáticas.
    
    Tareas:
      - Cada minuto: verificar recordatorios de usuarios
      - A las 00:05: verificar rachas del día anterior
    """
    global bot_instance, scheduler
    bot_instance = bot
    
    scheduler = AsyncIOScheduler(timezone="UTC")
    
    # Verificar recordatorios cada minuto
    scheduler.add_job(
        check_reminders,
        CronTrigger(second=0),  # Segundo 0 de cada minuto
        id="check_reminders",
        name="Verificar recordatorios",
        replace_existing=True
    )
    
    # Verificar rachas a medianoche (00:05 para dar margen)
    scheduler.add_job(
        midnight_check,
        CronTrigger(hour=0, minute=5),
        id="midnight_check",
        name="Verificar rachas nocturnas",
        replace_existing=True
    )
    
    logger.info("⏰ Scheduler configurado: recordatorios cada minuto + midnight check")
    return scheduler


def start_scheduler():
    """Arranca el scheduler"""
    global scheduler
    if scheduler and not scheduler.running:
        scheduler.start()
        logger.info("⏰ Scheduler arrancado")


def stop_scheduler():
    """Para el scheduler"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("⏰ Scheduler parado")
