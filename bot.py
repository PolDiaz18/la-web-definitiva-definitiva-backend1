"""
=============================================================================
BOT.PY — El Bot de Telegram de NexoTime v2
=============================================================================
Este bot es el "coach automatizado". No guarda datos por sí solo,
todo lo lee/escribe directamente en la base de datos.

¿Por qué acceso directo a BD y no por HTTP?
  En v1 el bot llamaba a la API por HTTP. Pero como bot y API corren
  en el MISMO proceso, es más rápido y fiable acceder directo a la BD.
  No hay red de por medio → no hay latencia ni errores de conexión.

Arquitectura:
  Usuario → Telegram → Bot (este archivo) → Base de Datos ← API (main.py) ← Web

Comandos implementados:
  BÁSICOS:      /start, /help, /login
  HÁBITOS:      /habitos, /pendiente, /hoy, /ayer
  RUTINAS:      /morning, /night, /rutinas
  PROGRESO:     /racha, /nivel, /logros, /semana, /calendario
  TRACKEO:      /mood, /agua, /sueno, /nota
  EXTRAS:       /pomodoro, /inspiracion, /tareas
  CONFIG:       /pausar, /reanudar, /modo
"""

import os
import logging
from datetime import datetime, date, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
from telegram.constants import ParseMode
from sqlalchemy.orm import Session

from database import SessionLocal
from models import *
from auth import hash_password, verify_password, create_access_token
from gamification import (
    award_xp, get_level_info, update_habit_streak, update_global_streak,
    check_and_unlock_achievements, get_random_quote, habit_applies_today,
    get_level_title
)

logger = logging.getLogger("nexotime.bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS (Funciones auxiliares)
# ─────────────────────────────────────────────────────────────────────────────

def get_user_by_telegram(telegram_id: str, db: Session) -> User | None:
    """Busca un usuario por su telegram_id"""
    return db.query(User).filter(User.telegram_id == telegram_id).first()


def require_user(telegram_id: str, db: Session) -> User:
    """Como get_user_by_telegram pero lanza excepción si no existe"""
    user = get_user_by_telegram(telegram_id, db)
    if not user:
        raise ValueError("not_linked")
    return user


NOT_LINKED_MSG = (
    "❌ Su cuenta no está vinculada\\.\n\n"
    "Use /login para vincular su cuenta de NexoTime\\."
)

def mood_emoji(level: int) -> str:
    """Convierte nivel de mood a emoji"""
    return {1: "😢", 2: "😞", 3: "😐", 4: "🙂", 5: "🤩"}.get(level, "😐")


def progress_bar(current: int, total: int, length: int = 10) -> str:
    """Genera barra de progreso ASCII: ██████░░░░ 60%"""
    if total == 0:
        return "░" * length + " 0%"
    filled = int(length * current / total)
    bar = "█" * filled + "░" * (length - filled)
    pct = round(current / total * 100)
    return f"{bar} {pct}%"


def color_emoji(percentage: float) -> str:
    """Emoji de color según porcentaje"""
    if percentage >= 80:
        return "🟢"
    elif percentage >= 50:
        return "🟡"
    else:
        return "🔴"


def get_time_greeting() -> str:
    """Saludo según la hora del día"""
    hour = datetime.now().hour
    if hour < 12:
        return "🌅 ¡Buenos días"
    elif hour < 20:
        return "☀️ ¡Buenas tardes"
    else:
        return "🌙 Buenas noches"


def get_motivational_suffix(streak: int) -> str:
    """Mensaje motivacional según racha"""
    if streak >= 30:
        return "Usted es imparable. 💎"
    elif streak >= 14:
        return "¡Qué constancia! Siga así. 🔥"
    elif streak >= 7:
        return "¡Gran semana! No afloje. 💪"
    elif streak >= 3:
        return "Buen ritmo, a por más. 🌱"
    else:
        return "Cada día cuenta. ¡Vamos! 🚀"


# ─────────────────────────────────────────────────────────────────────────────
# MENÚ PERSISTENTE
# ─────────────────────────────────────────────────────────────────────────────
# Este teclado aparece siempre en la parte inferior del chat.

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📋 Hábitos"), KeyboardButton("📊 Hoy")],
        [KeyboardButton("🌅 Morning"), KeyboardButton("🌙 Night")],
        [KeyboardButton("💧 Agua"), KeyboardButton("💡 Inspiración")],
    ],
    resize_keyboard=True,
    is_persistent=True
)


# =============================================================================
# ===================== COMANDO: /start =======================================
# =============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Primer contacto con el bot"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = get_user_by_telegram(telegram_id, db)
        
        if user:
            greeting = get_time_greeting()
            await update.message.reply_text(
                f"{greeting}, {user.name}\\! 🔷\n\n"
                f"📊 Nivel {user.level} \\| {get_level_title(user.level)}\n"
                f"🔥 Racha: {user.global_streak} días\n"
                f"⚡ {user.xp} XP\n\n"
                f"¿Qué desea hacer?",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=MAIN_KEYBOARD
            )
        else:
            await update.message.reply_text(
                "👋 ¡Bienvenido a *NexoTime*\\!\n\n"
                "Soy su coach de productividad personal\\. "
                "Le ayudaré a construir hábitos, seguir rutinas "
                "y alcanzar sus objetivos\\.\n\n"
                "Para empezar, vincule su cuenta:\n\n"
                "1️⃣ Regístrese en la web de NexoTime\n"
                "2️⃣ Use aquí: /login\n\n"
                "Si ya tiene cuenta, escriba /login ahora\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /login =======================================
# =============================================================================
# Flujo conversacional: pide email → pide contraseña → vincula

LOGIN_EMAIL, LOGIN_PASSWORD = range(2)

async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo de login"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    try:
        user = get_user_by_telegram(telegram_id, db)
        if user:
            await update.message.reply_text(
                f"✅ Ya tiene su cuenta vinculada, {user.name}\\.\n"
                f"Use /help para ver los comandos disponibles\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return ConversationHandler.END
    finally:
        db.close()
    
    await update.message.reply_text(
        "🔐 *Vincular cuenta*\n\n"
        "Escriba su email de NexoTime:",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return LOGIN_EMAIL


async def login_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el email"""
    context.user_data["login_email"] = update.message.text.strip()
    await update.message.reply_text("Ahora escriba su contraseña:")
    return LOGIN_PASSWORD


async def login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la contraseña e intenta vincular"""
    email = context.user_data.get("login_email", "")
    password = update.message.text.strip()
    telegram_id = str(update.effective_user.id)
    
    # Borrar mensaje con contraseña por seguridad
    try:
        await update.message.delete()
    except:
        pass
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        
        if not user or not verify_password(password, user.password_hash):
            await update.effective_chat.send_message(
                "❌ Email o contraseña incorrectos\\. Intente de nuevo con /login",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return ConversationHandler.END
        
        # Verificar que no esté vinculado a otro Telegram
        existing = db.query(User).filter(
            User.telegram_id == telegram_id, User.id != user.id
        ).first()
        if existing:
            existing.telegram_id = None
            db.commit()
        
        user.telegram_id = telegram_id
        db.commit()
        
        await update.effective_chat.send_message(
            f"✅ ¡Cuenta vinculada correctamente, {user.name}\\!\n\n"
            f"🔷 *NexoTime está listo*\n\n"
            f"Use /help para ver todos los comandos\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=MAIN_KEYBOARD
        )
        
        logger.info(f"📱 Cuenta vinculada: {user.name} → tg:{telegram_id}")
    finally:
        db.close()
    
    return ConversationHandler.END


async def login_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela el flujo de login"""
    await update.message.reply_text("Login cancelado\\.", parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END


# =============================================================================
# ===================== COMANDO: /help ========================================
# =============================================================================

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Comandos de NexoTime*\n\n"
        "*Hábitos:*\n"
        "  /habitos — Ver y marcar hábitos del día\n"
        "  /pendiente — Solo los que faltan\n"
        "  /hoy — Resumen rápido del día\n"
        "  /ayer — Cómo fue ayer\n\n"
        "*Rutinas:*\n"
        "  /morning — Rutina de mañana\n"
        "  /night — Rutina de noche\n"
        "  /rutinas — Todas sus rutinas\n\n"
        "*Progreso:*\n"
        "  /racha — Sus rachas actuales\n"
        "  /nivel — XP y nivel\n"
        "  /logros — Insignias desbloqueadas\n"
        "  /semana — Resumen semanal\n"
        "  /calendario — Mapa de calor del mes\n\n"
        "*Trackeo rápido:*\n"
        "  /mood — Registrar estado de ánimo\n"
        "  /agua — Sumar un vaso de agua\n"
        "  /sueno — Registrar horas de sueño\n"
        "  /nota — Escribir en el diario\n\n"
        "*Extras:*\n"
        "  /pomodoro — Timer de productividad\n"
        "  /inspiracion — Cita motivacional\n"
        "  /tareas — Tareas pendientes\n\n"
        "*Configuración:*\n"
        "  /pausar — Pausar recordatorios\n"
        "  /reanudar — Reactivar recordatorios\n"
        "  /modo — Cambiar modo \\(normal/vacaciones/enfermo\\)",
        parse_mode=ParseMode.MARKDOWN_V2
    )


# =============================================================================
# ===================== COMANDO: /habitos =====================================
# =============================================================================

async def cmd_habitos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los hábitos del día con botones ✅/❌"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        today = date.today()
        
        habits = db.query(Habit).filter(
            Habit.user_id == user.id, Habit.active == True, Habit.archived == False
        ).order_by(Habit.order).all()
        
        if not habits:
            await update.message.reply_text(
                "No tiene hábitos configurados\\.\n"
                "Añádalos desde la web de NexoTime\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Filtrar hábitos que aplican hoy
        applicable = [h for h in habits if habit_applies_today(h, today)]
        
        if not applicable:
            await update.message.reply_text(
                "Hoy no tiene hábitos programados\\. ¡Día libre\\! 🎉",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        # Obtener logs de hoy
        logs = db.query(HabitLog).filter(
            HabitLog.user_id == user.id, HabitLog.date == today
        ).all()
        log_map = {l.habit_id: l for l in logs}
        
        # Construir mensaje y botones
        completed = sum(1 for h in applicable if log_map.get(h.id) and log_map[h.id].completed)
        total = len(applicable)
        pct = round(completed / total * 100) if total > 0 else 0
        
        lines = [f"📋 *Hábitos de hoy* {color_emoji(pct)}\n"]
        lines.append(f"{progress_bar(completed, total)}\n")
        
        keyboard = []
        for habit in applicable:
            log = log_map.get(habit.id)
            done = log and log.completed
            status = "✅" if done else "⬜"
            
            lines.append(f"{status} {habit.icon} {habit.name}")
            
            if habit.habit_type == "quantity" and habit.target_quantity:
                current = log.quantity_logged if log else 0
                lines[-1] += f" \\({int(current)}/{int(habit.target_quantity)} {habit.quantity_unit or ''}\\)"
            
            # Botones
            if done:
                keyboard.append([InlineKeyboardButton(
                    f"↩️ Desmarcar {habit.name}",
                    callback_data=f"habit_undo_{habit.id}"
                )])
            else:
                if habit.habit_type == "quantity":
                    keyboard.append([
                        InlineKeyboardButton(
                            f"➕ {habit.icon} +1",
                            callback_data=f"habit_qty_{habit.id}"
                        ),
                        InlineKeyboardButton(
                            f"✅ Completar",
                            callback_data=f"habit_do_{habit.id}"
                        )
                    ])
                else:
                    keyboard.append([InlineKeyboardButton(
                        f"✅ {habit.icon} {habit.name}",
                        callback_data=f"habit_do_{habit.id}"
                    )])
        
        if completed == total and total > 0:
            lines.append(f"\n🎉 *¡Todos completados\\!* {get_motivational_suffix(user.global_streak)}")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== CALLBACK: Marcar/Desmarcar hábitos ====================
# =============================================================================

async def callback_habit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones de hábitos"""
    query = update.callback_query
    await query.answer()
    
    telegram_id = str(update.effective_user.id)
    data = query.data
    
    db = SessionLocal()
    try:
        user = require_user(telegram_id, db)
        today = date.today()
        
        if data.startswith("habit_do_"):
            habit_id = int(data.replace("habit_do_", ""))
            _mark_habit(db, user, habit_id, today, completed=True)
        
        elif data.startswith("habit_undo_"):
            habit_id = int(data.replace("habit_undo_", ""))
            _mark_habit(db, user, habit_id, today, completed=False)
        
        elif data.startswith("habit_qty_"):
            habit_id = int(data.replace("habit_qty_", ""))
            _increment_habit_quantity(db, user, habit_id, today)
        
        # Regenerar el mensaje de hábitos (editar in-place)
        habits = db.query(Habit).filter(
            Habit.user_id == user.id, Habit.active == True, Habit.archived == False
        ).order_by(Habit.order).all()
        
        applicable = [h for h in habits if habit_applies_today(h, today)]
        logs = db.query(HabitLog).filter(
            HabitLog.user_id == user.id, HabitLog.date == today
        ).all()
        log_map = {l.habit_id: l for l in logs}
        
        completed = sum(1 for h in applicable if log_map.get(h.id) and log_map[h.id].completed)
        total = len(applicable)
        pct = round(completed / total * 100) if total > 0 else 0
        
        lines = [f"📋 *Hábitos de hoy* {color_emoji(pct)}\n"]
        lines.append(f"{progress_bar(completed, total)}\n")
        
        keyboard = []
        for habit in applicable:
            log = log_map.get(habit.id)
            done = log and log.completed
            status = "✅" if done else "⬜"
            
            line = f"{status} {habit.icon} {habit.name}"
            if habit.habit_type == "quantity" and habit.target_quantity:
                current = log.quantity_logged if log else 0
                line += f" \\({int(current)}/{int(habit.target_quantity)} {habit.quantity_unit or ''}\\)"
            lines.append(line)
            
            if done:
                keyboard.append([InlineKeyboardButton(
                    f"↩️ Desmarcar {habit.name}",
                    callback_data=f"habit_undo_{habit.id}"
                )])
            else:
                if habit.habit_type == "quantity":
                    keyboard.append([
                        InlineKeyboardButton(f"➕ {habit.icon} +1", callback_data=f"habit_qty_{habit.id}"),
                        InlineKeyboardButton(f"✅ Completar", callback_data=f"habit_do_{habit.id}")
                    ])
                else:
                    keyboard.append([InlineKeyboardButton(
                        f"✅ {habit.icon} {habit.name}", callback_data=f"habit_do_{habit.id}"
                    )])
        
        if completed == total and total > 0:
            lines.append(f"\n🎉 *¡Todos completados\\!* {get_motivational_suffix(user.global_streak)}")
        
        # Verificar nuevos logros
        new_achievements = check_and_unlock_achievements(db, user)
        for ach in new_achievements:
            lines.append(f"\n🏆 *¡Logro desbloqueado\\!* {ach.icon} {ach.name}")
        
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
    
    except ValueError:
        await query.edit_message_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


def _mark_habit(db: Session, user: User, habit_id: int, today: date, completed: bool):
    """Marca o desmarca un hábito"""
    habit = db.query(Habit).filter(Habit.id == habit_id, Habit.user_id == user.id).first()
    if not habit:
        return
    
    log = db.query(HabitLog).filter(
        HabitLog.habit_id == habit_id, HabitLog.date == today
    ).first()
    
    if log:
        log.completed = completed
        log.completed_at = datetime.utcnow() if completed else None
    else:
        log = HabitLog(
            user_id=user.id, habit_id=habit_id, date=today,
            completed=completed, completed_at=datetime.utcnow() if completed else None
        )
        db.add(log)
    
    db.commit()
    
    if completed:
        update_habit_streak(db, habit, True, today)
        update_global_streak(db, user, today)
        award_xp(db, user, "habit_complete", habit.current_streak)
    else:
        update_habit_streak(db, habit, False, today)


def _increment_habit_quantity(db: Session, user: User, habit_id: int, today: date):
    """Incrementa la cantidad de un hábito (+1)"""
    habit = db.query(Habit).filter(Habit.id == habit_id, Habit.user_id == user.id).first()
    if not habit:
        return
    
    log = db.query(HabitLog).filter(
        HabitLog.habit_id == habit_id, HabitLog.date == today
    ).first()
    
    if log:
        log.quantity_logged += 1
        if habit.target_quantity and log.quantity_logged >= habit.target_quantity:
            log.completed = True
            log.completed_at = datetime.utcnow()
    else:
        is_complete = habit.target_quantity and 1 >= habit.target_quantity
        log = HabitLog(
            user_id=user.id, habit_id=habit_id, date=today,
            quantity_logged=1, completed=is_complete,
            completed_at=datetime.utcnow() if is_complete else None
        )
        db.add(log)
    
    db.commit()
    
    if log.completed:
        update_habit_streak(db, habit, True, today)
        update_global_streak(db, user, today)
        award_xp(db, user, "habit_complete", habit.current_streak)


# =============================================================================
# ===================== COMANDO: /pendiente ===================================
# =============================================================================

async def cmd_pendiente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra solo los hábitos NO completados de hoy"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        today = date.today()
        
        habits = db.query(Habit).filter(
            Habit.user_id == user.id, Habit.active == True, Habit.archived == False
        ).order_by(Habit.order).all()
        
        applicable = [h for h in habits if habit_applies_today(h, today)]
        logs = db.query(HabitLog).filter(
            HabitLog.user_id == user.id, HabitLog.date == today, HabitLog.completed == True
        ).all()
        completed_ids = {l.habit_id for l in logs}
        
        pending = [h for h in applicable if h.id not in completed_ids]
        
        if not pending:
            await update.message.reply_text(
                "✅ *¡No tiene nada pendiente\\!*\n\n"
                f"Ha completado todo hoy\\. {get_motivational_suffix(user.global_streak)}",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        lines = [f"⏳ *Hábitos pendientes* \\({len(pending)} restantes\\)\n"]
        keyboard = []
        
        for habit in pending:
            lines.append(f"⬜ {habit.icon} {habit.name}")
            keyboard.append([InlineKeyboardButton(
                f"✅ {habit.icon} {habit.name}",
                callback_data=f"habit_do_{habit.id}"
            )])
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /hoy ========================================
# =============================================================================

async def cmd_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resumen rápido del día"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        today = date.today()
        
        # Hábitos
        habits = db.query(Habit).filter(
            Habit.user_id == user.id, Habit.active == True, Habit.archived == False
        ).all()
        applicable = [h for h in habits if habit_applies_today(h, today)]
        logs = db.query(HabitLog).filter(
            HabitLog.user_id == user.id, HabitLog.date == today, HabitLog.completed == True
        ).all()
        h_completed = len(logs)
        h_total = len(applicable)
        h_pct = round(h_completed / h_total * 100) if h_total > 0 else 0
        
        # Agua
        water = db.query(WaterLog).filter(
            WaterLog.user_id == user.id, WaterLog.date == today
        ).first()
        water_glasses = water.glasses if water else 0
        water_target = water.target if water else 8
        
        # Mood
        mood = db.query(MoodLog).filter(
            MoodLog.user_id == user.id, MoodLog.date == today
        ).first()
        
        # Tareas pendientes
        pending_tasks = db.query(Task).filter(
            Task.user_id == user.id, Task.completed == False
        ).count()
        
        # Pomodoros
        pomodoros = db.query(PomodoroSession).filter(
            PomodoroSession.user_id == user.id,
            PomodoroSession.date == today,
            PomodoroSession.completed == True
        ).count()
        
        greeting = get_time_greeting()
        
        lines = [
            f"{greeting}\\! 📊\n",
            f"*Hábitos:* {h_completed}/{h_total} {color_emoji(h_pct)}",
            f"{progress_bar(h_completed, h_total)}",
            f"\n💧 *Agua:* {water_glasses}/{water_target} vasos",
        ]
        
        if mood:
            lines.append(f"😊 *Ánimo:* {mood_emoji(mood.level)} \\({mood.level}/5\\)")
        
        if pomodoros > 0:
            lines.append(f"🍅 *Pomodoros:* {pomodoros}")
        
        if pending_tasks > 0:
            lines.append(f"📝 *Tareas pendientes:* {pending_tasks}")
        
        lines.append(f"\n🔥 *Racha:* {user.global_streak} días")
        lines.append(f"⚡ *Nivel:* {user.level} \\({get_level_title(user.level)}\\)")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /ayer ========================================
# =============================================================================

async def cmd_ayer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resumen del día anterior"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        yesterday = date.today() - timedelta(days=1)
        
        habits = db.query(Habit).filter(
            Habit.user_id == user.id, Habit.active == True
        ).all()
        applicable = [h for h in habits if habit_applies_today(h, yesterday)]
        logs = db.query(HabitLog).filter(
            HabitLog.user_id == user.id, HabitLog.date == yesterday
        ).all()
        log_map = {l.habit_id: l for l in logs}
        
        completed = sum(1 for h in applicable if log_map.get(h.id) and log_map[h.id].completed)
        total = len(applicable)
        pct = round(completed / total * 100) if total > 0 else 0
        
        lines = [f"📅 *Ayer* {color_emoji(pct)}\n"]
        lines.append(f"{progress_bar(completed, total)}\n")
        
        for habit in applicable:
            log = log_map.get(habit.id)
            done = log and log.completed
            status = "✅" if done else "❌"
            lines.append(f"{status} {habit.icon} {habit.name}")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /rutinas, /morning, /night ===================
# =============================================================================

async def cmd_rutinas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todas las rutinas del usuario"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        routines = db.query(Routine).filter(
            Routine.user_id == user.id, Routine.active == True
        ).order_by(Routine.order).all()
        
        if not routines:
            await update.message.reply_text(
                "No tiene rutinas configuradas\\. Créelas desde la web\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        keyboard = []
        for r in routines:
            keyboard.append([InlineKeyboardButton(
                f"{r.icon} {r.name}",
                callback_data=f"routine_{r.id}"
            )])
        
        await update.message.reply_text(
            "📋 *Sus rutinas:*",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


async def cmd_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la primera rutina con 'mañana' o 'morning' en el nombre, o la primera rutina"""
    await _show_routine_by_keyword(update, ["mañana", "morning", "morn"])


async def cmd_night(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la primera rutina con 'noche' o 'night' en el nombre"""
    await _show_routine_by_keyword(update, ["noche", "night", "nocturna"])


async def _show_routine_by_keyword(update: Update, keywords: list[str]):
    """Helper para buscar rutina por palabra clave"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        routines = db.query(Routine).filter(
            Routine.user_id == user.id, Routine.active == True
        ).all()
        
        # Buscar rutina que coincida
        routine = None
        for r in routines:
            if any(kw in r.name.lower() for kw in keywords):
                routine = r
                break
        
        if not routine and routines:
            routine = routines[0]
        
        if not routine:
            await update.message.reply_text(
                "No tiene rutinas configuradas\\. Créelas desde la web\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        await _send_routine(update, routine, db)
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


async def _send_routine(update_or_query, routine: Routine, db: Session):
    """Envía una rutina formateada"""
    steps = db.query(RoutineStep).filter(
        RoutineStep.routine_id == routine.id
    ).order_by(RoutineStep.step_order).all()
    
    total_time = sum(s.duration_minutes or 0 for s in steps)
    
    lines = [f"{routine.icon} *{routine.name}*"]
    if total_time > 0:
        lines.append(f"⏱ Tiempo estimado: {total_time} min\n")
    else:
        lines.append("")
    
    for step in steps:
        time_str = f" \\({step.duration_minutes} min\\)" if step.duration_minutes else ""
        lines.append(f"{step.step_order}\\. {step.description}{time_str}")
    
    lines.append(f"\n💪 ¡A por ello\\!")
    
    # Determinar dónde enviar
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )
    elif hasattr(update_or_query, 'edit_message_text'):
        await update_or_query.edit_message_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )


async def callback_routine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para botones de rutinas"""
    query = update.callback_query
    await query.answer()
    
    routine_id = int(query.data.replace("routine_", ""))
    db = SessionLocal()
    
    try:
        routine = db.query(Routine).filter(Routine.id == routine_id).first()
        if routine:
            await _send_routine(query, routine, db)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /racha =======================================
# =============================================================================

async def cmd_racha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        habits = db.query(Habit).filter(
            Habit.user_id == user.id, Habit.active == True, Habit.archived == False
        ).order_by(Habit.current_streak.desc()).all()
        
        lines = [
            "🔥 *Rachas actuales*\n",
            f"🌐 *Global:* {user.global_streak} días \\(mejor: {user.best_global_streak}\\)\n",
        ]
        
        for h in habits:
            fire = "🔥" if h.current_streak >= 7 else "🌱" if h.current_streak >= 3 else "·"
            lines.append(f"{fire} {h.icon} {h.name}: {h.current_streak} días \\(mejor: {h.best_streak}\\)")
        
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /nivel =======================================
# =============================================================================

async def cmd_nivel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        info = get_level_info(user)
        
        await update.message.reply_text(
            f"⚡ *Nivel {info['level']}* — {info['title']}\n\n"
            f"XP: {info['xp_in_level']}/{info['xp_next_level']}\n"
            f"{progress_bar(info['xp_in_level'], info['xp_next_level'])}\n\n"
            f"XP total: {info['xp']}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /logros ======================================
# =============================================================================

async def cmd_logros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        all_achievements = db.query(Achievement).all()
        unlocked = db.query(UserAchievement).filter(
            UserAchievement.user_id == user.id
        ).all()
        unlocked_ids = {ua.achievement_id for ua in unlocked}
        
        total = len(all_achievements)
        done = len(unlocked_ids)
        
        lines = [f"🏆 *Logros* \\({done}/{total}\\)\n"]
        
        for ach in all_achievements:
            if ach.id in unlocked_ids:
                lines.append(f"  {ach.icon} *{ach.name}*")
            else:
                lines.append(f"  🔒 _{ach.name}_")
        
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /semana ======================================
# =============================================================================

async def cmd_semana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        
        day_names = ["L", "M", "X", "J", "V", "S", "D"]
        lines = ["📊 *Resumen semanal*\n"]
        
        total_completed = 0
        total_habits = 0
        
        for i in range(7):
            day = monday + timedelta(days=i)
            habits = db.query(Habit).filter(
                Habit.user_id == user.id, Habit.active == True, Habit.archived == False
            ).all()
            applicable = [h for h in habits if habit_applies_today(h, day)]
            logs = db.query(HabitLog).filter(
                HabitLog.user_id == user.id, HabitLog.date == day, HabitLog.completed == True
            ).all()
            
            done = len(logs)
            total = len(applicable)
            total_completed += done
            total_habits += total
            
            pct = round(done / total * 100) if total > 0 else 0
            marker = "📍" if day == today else " "
            check = "✅" if done == total and total > 0 else "❌" if total > 0 else "·"
            
            lines.append(f"{marker}{day_names[i]} {check} {done}/{total} {progress_bar(done, total, 6)}")
        
        week_pct = round(total_completed / total_habits * 100) if total_habits > 0 else 0
        lines.append(f"\n*Total:* {total_completed}/{total_habits} {color_emoji(week_pct)}")
        
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /calendario ==================================
# =============================================================================

async def cmd_calendario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mapa de calor del mes actual estilo GitHub"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        today = date.today()
        first_day = today.replace(day=1)
        
        # Obtener todos los logs del mes
        logs = db.query(HabitLog).filter(
            HabitLog.user_id == user.id,
            HabitLog.date >= first_day,
            HabitLog.completed == True
        ).all()
        
        habits = db.query(Habit).filter(
            Habit.user_id == user.id, Habit.active == True, Habit.archived == False
        ).all()
        
        # Calcular completado por día
        lines = [f"📅 *{today.strftime('%B %Y')}*\n"]
        lines.append("L  M  X  J  V  S  D")
        
        # Padding para el primer día
        first_weekday = first_day.weekday()
        row = "   " * first_weekday
        
        day = first_day
        while day.month == today.month:
            applicable = [h for h in habits if habit_applies_today(h, day)]
            day_logs = [l for l in logs if l.date == day]
            
            if day > today:
                cell = "· "
            elif len(applicable) == 0:
                cell = "· "
            elif len(day_logs) >= len(applicable):
                cell = "✅"
            elif len(day_logs) > 0:
                cell = "🟡"
            else:
                cell = "❌"
            
            row += cell + " "
            
            if day.weekday() == 6:  # Domingo
                lines.append(row.rstrip())
                row = ""
            
            day += timedelta(days=1)
        
        if row.strip():
            lines.append(row.rstrip())
        
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /mood ========================================
# =============================================================================

async def cmd_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pregunta el estado de ánimo con botones"""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("😢 1", callback_data="mood_1"),
            InlineKeyboardButton("😞 2", callback_data="mood_2"),
            InlineKeyboardButton("😐 3", callback_data="mood_3"),
            InlineKeyboardButton("🙂 4", callback_data="mood_4"),
            InlineKeyboardButton("🤩 5", callback_data="mood_5"),
        ]
    ])
    
    await update.message.reply_text(
        "¿Cómo se siente hoy?",
        reply_markup=keyboard
    )


async def callback_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra el mood seleccionado"""
    query = update.callback_query
    await query.answer()
    
    level = int(query.data.replace("mood_", ""))
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        today = date.today()
        
        existing = db.query(MoodLog).filter(
            MoodLog.user_id == user.id, MoodLog.date == today
        ).first()
        
        if existing:
            existing.level = level
        else:
            db.add(MoodLog(user_id=user.id, date=today, level=level))
            award_xp(db, user, "mood_log")
        
        db.commit()
        
        await query.edit_message_text(
            f"Registrado: {mood_emoji(level)} \\({level}/5\\)\n\n"
            f"¡Gracias por registrar su ánimo\\!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    except ValueError:
        await query.edit_message_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /agua ========================================
# =============================================================================

async def cmd_agua(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Añade un vaso de agua"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        today = date.today()
        
        log = db.query(WaterLog).filter(
            WaterLog.user_id == user.id, WaterLog.date == today
        ).first()
        
        if log:
            log.glasses += 1
        else:
            log = WaterLog(user_id=user.id, date=today, glasses=1)
            db.add(log)
        
        db.commit()
        db.refresh(log)
        
        bar = progress_bar(log.glasses, log.target)
        emoji = "🎉" if log.glasses >= log.target else "💧"
        
        await update.message.reply_text(
            f"{emoji} *Agua:* {log.glasses}/{log.target} vasos\n{bar}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /sueno =======================================
# =============================================================================

async def cmd_sueno(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra horas de sueño con botones"""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5h", callback_data="sleep_5"),
            InlineKeyboardButton("6h", callback_data="sleep_6"),
            InlineKeyboardButton("6.5h", callback_data="sleep_6.5"),
            InlineKeyboardButton("7h", callback_data="sleep_7"),
        ],
        [
            InlineKeyboardButton("7.5h", callback_data="sleep_7.5"),
            InlineKeyboardButton("8h", callback_data="sleep_8"),
            InlineKeyboardButton("8.5h", callback_data="sleep_8.5"),
            InlineKeyboardButton("9h+", callback_data="sleep_9"),
        ],
    ])
    
    await update.message.reply_text(
        "🛌 ¿Cuántas horas durmió anoche?",
        reply_markup=keyboard
    )


async def callback_sleep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    hours = float(query.data.replace("sleep_", ""))
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        today = date.today()
        
        existing = db.query(SleepLog).filter(
            SleepLog.user_id == user.id, SleepLog.date == today
        ).first()
        
        if existing:
            existing.hours = hours
        else:
            db.add(SleepLog(user_id=user.id, date=today, hours=hours))
            award_xp(db, user, "sleep_log")
        
        db.commit()
        
        emoji = "😴" if hours >= 7 else "⚠️"
        await query.edit_message_text(
            f"{emoji} Registrado: {hours}h de sueño",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    except ValueError:
        await query.edit_message_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /nota ========================================
# =============================================================================
# Usa ConversationHandler para pedir el texto

NOTE_TEXT = 0

async def cmd_nota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✍️ Escriba su nota del diario:")
    return NOTE_TEXT


async def nota_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        today = date.today()
        
        entry = JournalEntry(
            user_id=user.id, date=today, content=update.message.text
        )
        db.add(entry)
        award_xp(db, user, "journal_entry")
        db.commit()
        
        await update.message.reply_text(
            "✅ Nota guardada en su diario\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()
    
    return ConversationHandler.END


# =============================================================================
# ===================== COMANDO: /inspiracion =================================
# =============================================================================

async def cmd_inspiracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        quote = get_random_quote(db)
        author = f"\n— _{quote['author']}_" if quote['author'] else ""
        await update.message.reply_text(
            f"💡 *Inspiración*\n\n_{quote['text']}_\n{author}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /tareas ======================================
# =============================================================================

async def cmd_tareas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista tareas pendientes"""
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        tasks = db.query(Task).filter(
            Task.user_id == user.id, Task.completed == False
        ).order_by(Task.due_date.asc().nullslast()).limit(10).all()
        
        if not tasks:
            await update.message.reply_text(
                "✅ No tiene tareas pendientes\\. ¡Bien hecho\\!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        priority_icons = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        
        lines = [f"📝 *Tareas pendientes* \\({len(tasks)}\\)\n"]
        keyboard = []
        
        for t in tasks:
            icon = priority_icons.get(t.priority, "⚪")
            due = f" \\(vence: {t.due_date}\\)" if t.due_date else ""
            lines.append(f"{icon} {t.title}{due}")
            keyboard.append([InlineKeyboardButton(
                f"✅ {t.title}", callback_data=f"task_done_{t.id}"
            )])
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


async def callback_task_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Marca tarea como completada"""
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.replace("task_done_", ""))
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        task = db.query(Task).filter(Task.id == task_id, Task.user_id == user.id).first()
        
        if task:
            task.completed = True
            task.completed_at = datetime.utcnow()
            award_xp(db, user, "task_complete")
            db.commit()
            
            await query.edit_message_text(
                f"✅ Tarea completada: *{task.title}*",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    
    except ValueError:
        await query.edit_message_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /pomodoro ====================================
# =============================================================================

async def cmd_pomodoro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia un timer pomodoro"""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("15 min", callback_data="pomo_15"),
            InlineKeyboardButton("25 min", callback_data="pomo_25"),
            InlineKeyboardButton("45 min", callback_data="pomo_45"),
        ]
    ])
    
    await update.message.reply_text(
        "🍅 *Pomodoro*\n\n¿Cuánto tiempo de foco?",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )


async def callback_pomodoro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    minutes = int(query.data.replace("pomo_", ""))
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        
        session = PomodoroSession(
            user_id=user.id, date=date.today(),
            work_minutes=minutes, break_minutes=5
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        
        # Programar recordatorio cuando termine
        context.job_queue.run_once(
            _pomodoro_finished,
            when=minutes * 60,
            data={"session_id": session.id, "chat_id": update.effective_chat.id},
            name=f"pomo_{session.id}"
        )
        
        await query.edit_message_text(
            f"🍅 *Pomodoro iniciado: {minutes} minutos*\n\n"
            f"Le avisaré cuando termine\\. ¡A enfocarse\\!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    except ValueError:
        await query.edit_message_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


async def _pomodoro_finished(context: ContextTypes.DEFAULT_TYPE):
    """Se ejecuta cuando termina el pomodoro"""
    data = context.job.data
    db = SessionLocal()
    
    try:
        session = db.query(PomodoroSession).filter(
            PomodoroSession.id == data["session_id"]
        ).first()
        
        if session:
            session.completed = True
            session.finished_at = datetime.utcnow()
            
            user = db.query(User).filter(User.id == session.user_id).first()
            if user:
                award_xp(db, user, "pomodoro_complete")
            
            db.commit()
        
        await context.bot.send_message(
            chat_id=data["chat_id"],
            text="🍅 *¡Pomodoro completado\\!*\n\n"
                 f"Ha estado enfocado {session.work_minutes} minutos\\. "
                 f"Tómese un descanso de {session.break_minutes} minutos\\. ☕",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /pausar y /reanudar ==========================
# =============================================================================

async def cmd_pausar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    try:
        user = require_user(telegram_id, db)
        user.do_not_disturb = True
        db.commit()
        await update.message.reply_text(
            "🔇 Recordatorios *pausados*\\.\nUse /reanudar para reactivarlos\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


async def cmd_reanudar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    try:
        user = require_user(telegram_id, db)
        user.do_not_disturb = False
        db.commit()
        await update.message.reply_text(
            "🔔 Recordatorios *reactivados*\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except ValueError:
        await update.message.reply_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== COMANDO: /modo ========================================
# =============================================================================

async def cmd_modo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏃 Normal", callback_data="mode_normal")],
        [InlineKeyboardButton("🏖 Vacaciones (pausa sin perder rachas)", callback_data="mode_vacation")],
        [InlineKeyboardButton("🤒 Enfermo (hábitos mínimos)", callback_data="mode_sick")],
    ])
    
    await update.message.reply_text(
        "⚙️ *Cambiar modo*\n\nSeleccione su modo actual:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )


async def callback_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    mode = query.data.replace("mode_", "")
    telegram_id = str(update.effective_user.id)
    db = SessionLocal()
    
    try:
        user = require_user(telegram_id, db)
        user.mode = mode
        db.commit()
        
        mode_names = {"normal": "🏃 Normal", "vacation": "🏖 Vacaciones", "sick": "🤒 Enfermo"}
        await query.edit_message_text(
            f"Modo cambiado a: *{mode_names.get(mode, mode)}*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    except ValueError:
        await query.edit_message_text(NOT_LINKED_MSG, parse_mode=ParseMode.MARKDOWN_V2)
    finally:
        db.close()


# =============================================================================
# ===================== HANDLER: Botones del teclado persistente ==============
# =============================================================================

async def handle_keyboard_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redirige los botones del teclado persistente a los comandos"""
    text = update.message.text.strip()
    
    BUTTON_MAP = {
        "📋 Hábitos": cmd_habitos,
        "📊 Hoy": cmd_hoy,
        "🌅 Morning": cmd_morning,
        "🌙 Night": cmd_night,
        "💧 Agua": cmd_agua,
        "💡 Inspiración": cmd_inspiracion,
    }
    
    handler = BUTTON_MAP.get(text)
    if handler:
        await handler(update, context)


# =============================================================================
# ===================== CONFIGURAR Y ARRANCAR BOT =============================
# =============================================================================

def create_bot_application() -> Application:
    """
    Crea y configura la aplicación del bot con todos los handlers.
    Se llama desde main.py en el lifespan.
    """
    if not BOT_TOKEN:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN no configurado. Bot deshabilitado.")
        return None
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # ── Conversación: Login ──
    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", cmd_login)],
        states={
            LOGIN_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_email)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
    )
    
    # ── Conversación: Nota ──
    nota_conv = ConversationHandler(
        entry_points=[CommandHandler("nota", cmd_nota)],
        states={
            NOTE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, nota_text)],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
    )
    
    # ── Registrar handlers ──
    app.add_handler(login_conv)
    app.add_handler(nota_conv)
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("habitos", cmd_habitos))
    app.add_handler(CommandHandler("pendiente", cmd_pendiente))
    app.add_handler(CommandHandler("hoy", cmd_hoy))
    app.add_handler(CommandHandler("ayer", cmd_ayer))
    app.add_handler(CommandHandler("morning", cmd_morning))
    app.add_handler(CommandHandler("night", cmd_night))
    app.add_handler(CommandHandler("rutinas", cmd_rutinas))
    app.add_handler(CommandHandler("racha", cmd_racha))
    app.add_handler(CommandHandler("nivel", cmd_nivel))
    app.add_handler(CommandHandler("logros", cmd_logros))
    app.add_handler(CommandHandler("semana", cmd_semana))
    app.add_handler(CommandHandler("calendario", cmd_calendario))
    app.add_handler(CommandHandler("mood", cmd_mood))
    app.add_handler(CommandHandler("agua", cmd_agua))
    app.add_handler(CommandHandler("sueno", cmd_sueno))
    app.add_handler(CommandHandler("pomodoro", cmd_pomodoro))
    app.add_handler(CommandHandler("inspiracion", cmd_inspiracion))
    app.add_handler(CommandHandler("tareas", cmd_tareas))
    app.add_handler(CommandHandler("pausar", cmd_pausar))
    app.add_handler(CommandHandler("reanudar", cmd_reanudar))
    app.add_handler(CommandHandler("modo", cmd_modo))
    
    # ── Callbacks inline ──
    app.add_handler(CallbackQueryHandler(callback_habit, pattern="^habit_"))
    app.add_handler(CallbackQueryHandler(callback_mood, pattern="^mood_"))
    app.add_handler(CallbackQueryHandler(callback_sleep, pattern="^sleep_"))
    app.add_handler(CallbackQueryHandler(callback_pomodoro, pattern="^pomo_"))
    app.add_handler(CallbackQueryHandler(callback_task_done, pattern="^task_done_"))
    app.add_handler(CallbackQueryHandler(callback_routine, pattern="^routine_"))
    app.add_handler(CallbackQueryHandler(callback_mode, pattern="^mode_"))
    
    # ── Botones del teclado persistente ──
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_keyboard_buttons
    ))
    
    logger.info(f"🤖 Bot configurado con {len(app.handlers[0])} handlers")
    return app


async def start_bot(app: Application):
    """Arranca el bot en modo polling (compatible con hilos secundarios)"""
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("🤖 Bot de Telegram arrancado")


async def stop_bot(app: Application):
    """Para el bot limpiamente"""
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    logger.info("🤖 Bot de Telegram parado")
