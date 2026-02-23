"""
=============================================================================
SCHEDULER.PY — Recordatorios Automáticos (HTML, sin MarkdownV2)
=============================================================================
"""

import logging
from datetime import datetime, date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
import pytz
from sqlalchemy.orm import Session

from database import SessionLocal
from models import *
from gamification import (
    habit_applies_today, get_random_quote, get_level_title,
    check_all_completed, update_global_streak
)

logger = logging.getLogger("nexotime.scheduler")
bot_instance: Bot = None
scheduler: AsyncIOScheduler = None

def progress_bar(cur, tot, length=10):
    if tot == 0: return "░" * length + " 0%"
    f = int(length * cur / tot)
    return "█" * f + "░" * (length - f) + f" {round(cur/tot*100)}%"

def color_emoji(p):
    if p >= 80: return "🟢"
    if p >= 50: return "🟡"
    return "🔴"


async def send_msg(telegram_id, text, keyboard=None):
    if not bot_instance: return False
    try:
        await bot_instance.send_message(chat_id=telegram_id, text=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return True
    except Exception as e:
        logger.error(f"Error enviando a {telegram_id}: {e}")
        return False


async def check_reminders():
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.telegram_id != None, User.do_not_disturb == False, User.mode != "vacation").all()
        for user in users:
            try:
                tz = pytz.timezone(user.timezone or "Europe/Madrid")
                now = datetime.now(tz)
                cur_time = now.strftime("%H:%M")
                cur_day = ["mon","tue","wed","thu","fri","sat","sun"][now.weekday()]
                reminders = db.query(Reminder).filter(Reminder.user_id==user.id, Reminder.active==True, Reminder.time==cur_time).all()
                for rem in reminders:
                    if rem.days and cur_day not in rem.days: continue
                    await _send_reminder(db, user, rem, now)
            except Exception as e:
                logger.error(f"Error reminders {user.name}: {e}")
    finally: db.close()


async def _send_reminder(db, user, rem, now):
    today = now.date()
    handlers = {
        "morning": _morning, "midday": _midday, "evening": _evening,
        "night": _night, "summary": _summary, "weekly_summary": _weekly,
    }
    fn = handlers.get(rem.type)
    if fn:
        if rem.type == "weekly_summary" and now.weekday() != 6: return
        await fn(db, user, today)
    elif rem.type == "routine" and rem.linked_routine_id:
        await _routine_rem(db, user, rem.linked_routine_id)
    elif rem.type == "custom" and rem.message:
        await send_msg(user.telegram_id, rem.message)


async def _morning(db, user, today):
    habits = db.query(Habit).filter(Habit.user_id==user.id, Habit.active==True, Habit.archived==False).all()
    app = [h for h in habits if habit_applies_today(h, today)]
    q = get_random_quote(db)
    lines = [f"🌅 <b>Buenos días, {user.name}!</b>\n", f"Tiene <b>{len(app)} hábitos</b> para hoy.", f"🔥 Racha: {user.global_streak} días\n"]
    for h in app[:5]: lines.append(f"  ⬜ {h.icon} {h.name}")
    if len(app)>5: lines.append(f"  ...y {len(app)-5} más")
    lines.append(f"\n💡 <i>{q['text']}</i>")
    await send_msg(user.telegram_id, "\n".join(lines))
    logger.info(f"🌅 Morning -> {user.name}")


async def _midday(db, user, today):
    habits = db.query(Habit).filter(Habit.user_id==user.id, Habit.active==True, Habit.archived==False).all()
    app = [h for h in habits if habit_applies_today(h, today)]
    done_ids = {l.habit_id for l in db.query(HabitLog).filter(HabitLog.user_id==user.id, HabitLog.date==today, HabitLog.completed==True).all()}
    done = len(done_ids); tot = len(app)
    if done==tot and tot>0:
        await send_msg(user.telegram_id, f"🎉 <b>{user.name}, ya completó todo!</b>\n\nImpresionante. 💎")
        return
    pending = [h for h in app if h.id not in done_ids]
    pct = round(done/tot*100) if tot else 0
    lines = [f"☀️ <b>Checkpoint mediodía</b>\n", f"{progress_bar(done,tot)} {color_emoji(pct)}\n", f"Faltan <b>{len(pending)}</b> hábitos:"]
    for h in pending[:5]: lines.append(f"  ⬜ {h.icon} {h.name}")
    lines.append("\n¡Aún hay tiempo! 💪")
    await send_msg(user.telegram_id, "\n".join(lines))
    logger.info(f"☀️ Midday -> {user.name}")


async def _evening(db, user, today):
    habits = db.query(Habit).filter(Habit.user_id==user.id, Habit.active==True, Habit.archived==False).all()
    app = [h for h in habits if habit_applies_today(h, today)]
    done_ids = {l.habit_id for l in db.query(HabitLog).filter(HabitLog.user_id==user.id, HabitLog.date==today, HabitLog.completed==True).all()}
    pending = [h for h in app if h.id not in done_ids]
    if not pending: return
    done = len(done_ids); tot = len(app); pct = round(done/tot*100) if tot else 0
    lines = [f"🌙 <b>{user.name}, el día no ha terminado</b>\n", f"{progress_bar(done,tot)} {color_emoji(pct)}\n", f"Quedan <b>{len(pending)}</b> hábitos:"]
    kb = []
    for h in pending:
        lines.append(f"  ⬜ {h.icon} {h.name}")
        kb.append([InlineKeyboardButton(f"✅ {h.icon} {h.name}", callback_data=f"habit_do_{h.id}")])
    if user.global_streak>0: lines.append(f"\n⚠️ Su racha de <b>{user.global_streak} días</b> está en juego!")
    await send_msg(user.telegram_id, "\n".join(lines), InlineKeyboardMarkup(kb) if kb else None)
    logger.info(f"🌙 Evening -> {user.name}")


async def _night(db, user, today):
    habits = db.query(Habit).filter(Habit.user_id==user.id, Habit.active==True, Habit.archived==False).all()
    app = [h for h in habits if habit_applies_today(h, today)]
    done_ids = {l.habit_id for l in db.query(HabitLog).filter(HabitLog.user_id==user.id, HabitLog.date==today, HabitLog.completed==True).all()}
    pending = [h for h in app if h.id not in done_ids]
    if not pending: return
    kb = [[InlineKeyboardButton(f"✅ {h.icon} {h.name}", callback_data=f"habit_do_{h.id}")] for h in pending]
    sw = ""
    if user.global_streak>=7: sw = f"\n\n🔥 {user.global_streak} días de racha. No los pierda."
    elif user.global_streak>=3: sw = f"\n\n🌱 Lleva {user.global_streak} días. No pare ahora."
    await send_msg(user.telegram_id, f"⏰ <b>Última llamada, {user.name}</b>\n\nFaltan <b>{len(pending)}</b> hábitos.{sw}", InlineKeyboardMarkup(kb) if kb else None)
    logger.info(f"⏰ Night -> {user.name}")


async def _summary(db, user, today):
    habits = db.query(Habit).filter(Habit.user_id==user.id, Habit.active==True, Habit.archived==False).all()
    app = [h for h in habits if habit_applies_today(h, today)]
    logs = db.query(HabitLog).filter(HabitLog.user_id==user.id, HabitLog.date==today).all()
    lm = {l.habit_id:l for l in logs}
    done = sum(1 for h in app if lm.get(h.id) and lm[h.id].completed)
    tot = len(app); pct = round(done/tot*100) if tot else 0
    w = db.query(WaterLog).filter(WaterLog.user_id==user.id, WaterLog.date==today).first()
    m = db.query(MoodLog).filter(MoodLog.user_id==user.id, MoodLog.date==today).first()
    lines = [f"📊 <b>Resumen del día</b> {color_emoji(pct)}\n", f"<b>Hábitos:</b> {done}/{tot}", progress_bar(done,tot)+"\n"]
    for h in app:
        lg = lm.get(h.id); d = lg and lg.completed
        lines.append(f"  {'✅' if d else '❌'} {h.icon} {h.name}")
    if w: lines.append(f"\n💧 Agua: {w.glasses}/{w.target}")
    if m: lines.append(f"😊 Ánimo: {['','😢','😞','😐','🙂','🤩'][m.level]}")
    if pct==100: lines.append("\n🏆 <b>Día perfecto!</b> Descanse bien.")
    elif pct>=70: lines.append("\n👍 Buen día. Mañana a por el 100%.")
    elif pct>=40: lines.append("\n💪 Hay margen. Mañana será mejor.")
    else: lines.append("\n🌱 No pasa nada. Lo importante es no rendirse.")
    lines.append(f"\nBuenas noches, {user.name} 🌙")
    await send_msg(user.telegram_id, "\n".join(lines))
    logger.info(f"📊 Summary -> {user.name} ({pct}%)")


async def _weekly(db, user, today):
    mon = today-timedelta(days=today.weekday()); dn = ["L","M","X","J","V","S","D"]
    habits = db.query(Habit).filter(Habit.user_id==user.id, Habit.active==True, Habit.archived==False).all()
    tc=0; th=0; dr=[]
    for i in range(7):
        day = mon+timedelta(days=i)
        ap = [h for h in habits if habit_applies_today(h,day)]
        ls = db.query(HabitLog).filter(HabitLog.user_id==user.id, HabitLog.date==day, HabitLog.completed==True).all()
        d=len(ls); t=len(ap); tc+=d; th+=t
        ck = "✅" if d==t and t>0 else "❌" if t>0 else "·"
        dr.append(f"{dn[i]} {ck}")
    wp = round(tc/th*100) if th else 0
    lines = [f"📅 <b>Resumen semanal</b> {color_emoji(wp)}\n", " ".join(dr),
             f"\n<b>Total:</b> {tc}/{th}", f"🔥 Racha: {user.global_streak} días",
             f"⚡ Nivel: {user.level} ({get_level_title(user.level)})", f"💰 XP: {user.xp}"]
    if wp>=90: lines.append("\n🏆 <b>Semana excepcional!</b>")
    elif wp>=70: lines.append("\n💪 Buena semana.")
    elif wp>=50: lines.append("\n📈 Semana decente.")
    else: lines.append("\n🌱 La próxima será mejor.")
    await send_msg(user.telegram_id, "\n".join(lines))
    logger.info(f"📅 Weekly -> {user.name} ({wp}%)")


async def _routine_rem(db, user, rid):
    r = db.query(Routine).filter(Routine.id==rid).first()
    if not r: return
    steps = db.query(RoutineStep).filter(RoutineStep.routine_id==rid).order_by(RoutineStep.step_order).all()
    lines = [f"{r.icon} <b>Es hora de: {r.name}</b>\n"]
    for s in steps:
        t = f" ({s.duration_minutes} min)" if s.duration_minutes else ""
        lines.append(f"{s.step_order}. {s.description}{t}")
    lines.append("\n💪 ¡Vamos!")
    await send_msg(user.telegram_id, "\n".join(lines))


async def midnight_check():
    db = SessionLocal()
    try:
        yday = date.today()-timedelta(days=1)
        users = db.query(User).filter(User.telegram_id!=None, User.mode!="vacation").all()
        for u in users:
            try:
                ok = check_all_completed(db, u, yday)
                if not ok and u.global_streak>0:
                    old = u.global_streak; u.global_streak=0; db.commit()
                    if old>=3:
                        await send_msg(u.telegram_id, f"😔 Su racha de <b>{old} días</b> se ha roto.\n\nNo pasa nada. Hoy es un nuevo comienzo. 🌅\nMejor racha: {u.best_global_streak} días")
                        logger.info(f"💔 Racha rota: {u.name} ({old})")
            except Exception as e:
                logger.error(f"Midnight error {u.name}: {e}")
    finally: db.close()


def create_scheduler(bot: Bot):
    global bot_instance, scheduler
    bot_instance = bot
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(check_reminders, CronTrigger(second=0), id="check_reminders", replace_existing=True)
    scheduler.add_job(midnight_check, CronTrigger(hour=0, minute=5), id="midnight_check", replace_existing=True)
    logger.info("⏰ Scheduler configurado")
    return scheduler

def start_scheduler():
    global scheduler
    if scheduler and not scheduler.running: scheduler.start(); logger.info("⏰ Scheduler arrancado")

def stop_scheduler():
    global scheduler
    if scheduler and scheduler.running: scheduler.shutdown(wait=False); logger.info("⏰ Scheduler parado")
