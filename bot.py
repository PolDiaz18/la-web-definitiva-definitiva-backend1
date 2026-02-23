"""
=============================================================================
BOT.PY — El Bot de Telegram de NexoTime v2
=============================================================================
USA HTML en vez de MarkdownV2 para evitar errores de escape.
MarkdownV2 es muy estricto con caracteres como - . ( ) !
HTML es más fiable: <b>negrita</b>, <i>cursiva</i>
"""

import os
import logging
from datetime import datetime, date, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
from telegram.constants import ParseMode
from sqlalchemy.orm import Session

from database import SessionLocal
from models import *
from auth import hash_password, verify_password
from gamification import (
    award_xp, get_level_info, update_habit_streak, update_global_streak,
    check_and_unlock_achievements, get_random_quote, habit_applies_today,
    get_level_title
)

logger = logging.getLogger("nexotime.bot")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
HTML = ParseMode.HTML

# ── Helpers ──

def get_user_by_telegram(tid, db):
    return db.query(User).filter(User.telegram_id == tid).first()

def require_user(tid, db):
    u = get_user_by_telegram(tid, db)
    if not u: raise ValueError("not_linked")
    return u

NOT_LINKED = "❌ Su cuenta no está vinculada.\n\nUse /login para vincular su cuenta."

def progress_bar(cur, tot, length=10):
    if tot == 0: return "░" * length + " 0%"
    f = int(length * cur / tot)
    return "█" * f + "░" * (length - f) + f" {round(cur/tot*100)}%"

def color_emoji(p):
    if p >= 80: return "🟢"
    if p >= 50: return "🟡"
    return "🔴"

def mood_emoji(l):
    return {1:"😢",2:"😞",3:"😐",4:"🙂",5:"🤩"}.get(l,"😐")

def greeting():
    h = datetime.now().hour
    if h < 12: return "🌅 ¡Buenos días"
    if h < 20: return "☀️ ¡Buenas tardes"
    return "🌙 Buenas noches"

def motiv(s):
    if s >= 30: return "Usted es imparable. 💎"
    if s >= 14: return "¡Qué constancia! 🔥"
    if s >= 7: return "¡Gran semana! 💪"
    if s >= 3: return "Buen ritmo. 🌱"
    return "Cada día cuenta. 🚀"

async def reply(upd, text, kb=None):
    await upd.message.reply_text(text, parse_mode=HTML, reply_markup=kb)

async def edit(q, text, kb=None):
    await q.edit_message_text(text, parse_mode=HTML, reply_markup=kb)

MAIN_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("📋 Hábitos"), KeyboardButton("📊 Hoy")],
     [KeyboardButton("🌅 Morning"), KeyboardButton("🌙 Night")],
     [KeyboardButton("💧 Agua"), KeyboardButton("💡 Inspiración")]],
    resize_keyboard=True, is_persistent=True)


# ── /start ──
async def cmd_start(upd: Update, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = get_user_by_telegram(tid, db)
        if u:
            await reply(upd, f"{greeting()}, {u.name}! 🔷\n\n📊 Nivel {u.level} | {get_level_title(u.level)}\n🔥 Racha: {u.global_streak} días\n⚡ {u.xp} XP", MAIN_KB)
        else:
            await reply(upd, "👋 ¡Bienvenido a <b>NexoTime</b>!\n\nSoy su coach de productividad.\n\n1️⃣ Regístrese en la web\n2️⃣ Use /login aquí")
    finally: db.close()


# ── /login ──
LOGIN_EMAIL, LOGIN_PASSWORD = range(2)

async def cmd_login(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = get_user_by_telegram(tid, db)
        if u:
            await reply(upd, f"✅ Ya vinculado, {u.name}. Use /help")
            return ConversationHandler.END
    finally: db.close()
    await reply(upd, "🔐 <b>Vincular cuenta</b>\n\nEscriba su email:")
    return LOGIN_EMAIL

async def login_email(upd, ctx):
    ctx.user_data["login_email"] = upd.message.text.strip()
    await reply(upd, "Escriba su contraseña:")
    return LOGIN_PASSWORD

async def login_password(upd, ctx):
    email = ctx.user_data.get("login_email", "")
    pwd = upd.message.text.strip()
    tid = str(upd.effective_user.id)
    try: await upd.message.delete()
    except: pass
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if not u or not verify_password(pwd, u.password_hash):
            await upd.effective_chat.send_message("❌ Email o contraseña incorrectos. Intente /login")
            return ConversationHandler.END
        u.telegram_id = tid
        db.commit()
        await upd.effective_chat.send_message(f"✅ Cuenta vinculada, {u.name}!\n\n🔷 <b>NexoTime listo.</b> Use /help", parse_mode=HTML, reply_markup=MAIN_KB)
    finally: db.close()
    return ConversationHandler.END

async def login_cancel(upd, ctx):
    await reply(upd, "Cancelado.")
    return ConversationHandler.END


# ── /help ──
async def cmd_help(upd, ctx):
    await reply(upd,
        "📖 <b>Comandos</b>\n\n"
        "<b>Hábitos:</b>\n/habitos /pendiente /hoy /ayer\n\n"
        "<b>Rutinas:</b>\n/morning /night /rutinas\n\n"
        "<b>Progreso:</b>\n/racha /nivel /logros /semana /calendario\n\n"
        "<b>Trackeo:</b>\n/mood /agua /sueno /nota\n\n"
        "<b>Extras:</b>\n/pomodoro /inspiracion /tareas\n\n"
        "<b>Config:</b>\n/pausar /reanudar /modo")


# ── /habitos ──
async def cmd_habitos(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        today = date.today()
        habits = db.query(Habit).filter(Habit.user_id==u.id, Habit.active==True, Habit.archived==False).order_by(Habit.order).all()
        if not habits:
            await reply(upd, "No tiene hábitos. Añádalos desde la web."); return
        applicable = [h for h in habits if habit_applies_today(h, today)]
        if not applicable:
            await reply(upd, "Hoy no tiene hábitos programados. 🎉"); return
        logs = db.query(HabitLog).filter(HabitLog.user_id==u.id, HabitLog.date==today).all()
        lm = {l.habit_id: l for l in logs}
        done = sum(1 for h in applicable if lm.get(h.id) and lm[h.id].completed)
        tot = len(applicable)
        pct = round(done/tot*100) if tot else 0
        lines = [f"📋 <b>Hábitos de hoy</b> {color_emoji(pct)}\n", progress_bar(done,tot)+"\n"]
        kb = []
        for h in applicable:
            lg = lm.get(h.id)
            d = lg and lg.completed
            st = "✅" if d else "⬜"
            line = f"{st} {h.icon} {h.name}"
            if h.habit_type=="quantity" and h.target_quantity:
                c = lg.quantity_logged if lg else 0
                line += f" ({int(c)}/{int(h.target_quantity)} {h.quantity_unit or ''})"
            lines.append(line)
            if d:
                kb.append([InlineKeyboardButton(f"↩️ {h.name}", callback_data=f"habit_undo_{h.id}")])
            elif h.habit_type=="quantity":
                kb.append([InlineKeyboardButton(f"➕ +1", callback_data=f"habit_qty_{h.id}"), InlineKeyboardButton("✅", callback_data=f"habit_do_{h.id}")])
            else:
                kb.append([InlineKeyboardButton(f"✅ {h.icon} {h.name}", callback_data=f"habit_do_{h.id}")])
        if done==tot and tot>0:
            lines.append(f"\n🎉 <b>¡Todos completados!</b> {motiv(u.global_streak)}")
        await reply(upd, "\n".join(lines), InlineKeyboardMarkup(kb) if kb else None)
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()


# ── Callback hábitos ──
async def callback_habit(upd, ctx):
    q = upd.callback_query
    await q.answer()
    tid = str(upd.effective_user.id)
    data = q.data
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        today = date.today()
        if data.startswith("habit_do_"): _mark(db, u, int(data[9:]), today, True)
        elif data.startswith("habit_undo_"): _mark(db, u, int(data[11:]), today, False)
        elif data.startswith("habit_qty_"): _incr(db, u, int(data[10:]), today)

        habits = db.query(Habit).filter(Habit.user_id==u.id, Habit.active==True, Habit.archived==False).order_by(Habit.order).all()
        applicable = [h for h in habits if habit_applies_today(h, today)]
        logs = db.query(HabitLog).filter(HabitLog.user_id==u.id, HabitLog.date==today).all()
        lm = {l.habit_id: l for l in logs}
        done = sum(1 for h in applicable if lm.get(h.id) and lm[h.id].completed)
        tot = len(applicable)
        pct = round(done/tot*100) if tot else 0
        lines = [f"📋 <b>Hábitos de hoy</b> {color_emoji(pct)}\n", progress_bar(done,tot)+"\n"]
        kb = []
        for h in applicable:
            lg = lm.get(h.id)
            d = lg and lg.completed
            st = "✅" if d else "⬜"
            line = f"{st} {h.icon} {h.name}"
            if h.habit_type=="quantity" and h.target_quantity:
                c = lg.quantity_logged if lg else 0
                line += f" ({int(c)}/{int(h.target_quantity)} {h.quantity_unit or ''})"
            lines.append(line)
            if d: kb.append([InlineKeyboardButton(f"↩️ {h.name}", callback_data=f"habit_undo_{h.id}")])
            elif h.habit_type=="quantity": kb.append([InlineKeyboardButton("➕ +1", callback_data=f"habit_qty_{h.id}"), InlineKeyboardButton("✅", callback_data=f"habit_do_{h.id}")])
            else: kb.append([InlineKeyboardButton(f"✅ {h.icon} {h.name}", callback_data=f"habit_do_{h.id}")])
        if done==tot and tot>0: lines.append(f"\n🎉 <b>¡Todos completados!</b> {motiv(u.global_streak)}")
        achs = check_and_unlock_achievements(db, u)
        for a in achs: lines.append(f"\n🏆 <b>Logro:</b> {a.icon} {a.name}")
        await edit(q, "\n".join(lines), InlineKeyboardMarkup(kb) if kb else None)
    except ValueError: await edit(q, NOT_LINKED)
    finally: db.close()

def _mark(db, u, hid, today, done):
    h = db.query(Habit).filter(Habit.id==hid, Habit.user_id==u.id).first()
    if not h: return
    lg = db.query(HabitLog).filter(HabitLog.habit_id==hid, HabitLog.date==today).first()
    if lg: lg.completed=done; lg.completed_at=datetime.utcnow() if done else None
    else: lg=HabitLog(user_id=u.id,habit_id=hid,date=today,completed=done,completed_at=datetime.utcnow() if done else None); db.add(lg)
    db.commit()
    if done: update_habit_streak(db,h,True,today); update_global_streak(db,u,today); award_xp(db,u,"habit_complete",h.current_streak)
    else: update_habit_streak(db,h,False,today)

def _incr(db, u, hid, today):
    h = db.query(Habit).filter(Habit.id==hid, Habit.user_id==u.id).first()
    if not h: return
    lg = db.query(HabitLog).filter(HabitLog.habit_id==hid, HabitLog.date==today).first()
    if lg:
        lg.quantity_logged += 1
        if h.target_quantity and lg.quantity_logged >= h.target_quantity: lg.completed=True; lg.completed_at=datetime.utcnow()
    else:
        ic = h.target_quantity and 1 >= h.target_quantity
        lg = HabitLog(user_id=u.id,habit_id=hid,date=today,quantity_logged=1,completed=ic,completed_at=datetime.utcnow() if ic else None); db.add(lg)
    db.commit()
    if lg.completed: update_habit_streak(db,h,True,today); update_global_streak(db,u,today); award_xp(db,u,"habit_complete",h.current_streak)


# ── /pendiente ──
async def cmd_pendiente(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db); today = date.today()
        habits = db.query(Habit).filter(Habit.user_id==u.id, Habit.active==True, Habit.archived==False).order_by(Habit.order).all()
        applicable = [h for h in habits if habit_applies_today(h, today)]
        done_ids = {l.habit_id for l in db.query(HabitLog).filter(HabitLog.user_id==u.id, HabitLog.date==today, HabitLog.completed==True).all()}
        pending = [h for h in applicable if h.id not in done_ids]
        if not pending: await reply(upd, f"✅ <b>¡Todo completado!</b> {motiv(u.global_streak)}"); return
        lines = [f"⏳ <b>Pendientes</b> ({len(pending)})\n"]
        kb = []
        for h in pending:
            lines.append(f"⬜ {h.icon} {h.name}")
            kb.append([InlineKeyboardButton(f"✅ {h.icon} {h.name}", callback_data=f"habit_do_{h.id}")])
        await reply(upd, "\n".join(lines), InlineKeyboardMarkup(kb))
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()


# ── /hoy ──
async def cmd_hoy(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db); today = date.today()
        habits = db.query(Habit).filter(Habit.user_id==u.id, Habit.active==True, Habit.archived==False).all()
        app = [h for h in habits if habit_applies_today(h, today)]
        done = len(db.query(HabitLog).filter(HabitLog.user_id==u.id, HabitLog.date==today, HabitLog.completed==True).all())
        tot = len(app); pct = round(done/tot*100) if tot else 0
        w = db.query(WaterLog).filter(WaterLog.user_id==u.id, WaterLog.date==today).first()
        m = db.query(MoodLog).filter(MoodLog.user_id==u.id, MoodLog.date==today).first()
        pt = db.query(Task).filter(Task.user_id==u.id, Task.completed==False).count()
        lines = [f"{greeting()}! 📊\n", f"<b>Hábitos:</b> {done}/{tot} {color_emoji(pct)}", progress_bar(done,tot),
                 f"\n💧 <b>Agua:</b> {w.glasses if w else 0}/8 vasos"]
        if m: lines.append(f"😊 <b>Ánimo:</b> {mood_emoji(m.level)} ({m.level}/5)")
        if pt: lines.append(f"📝 <b>Tareas:</b> {pt}")
        lines += [f"\n🔥 <b>Racha:</b> {u.global_streak} días", f"⚡ <b>Nivel:</b> {u.level} ({get_level_title(u.level)})"]
        await reply(upd, "\n".join(lines))
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()


# ── /ayer ──
async def cmd_ayer(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db); yday = date.today()-timedelta(days=1)
        habits = db.query(Habit).filter(Habit.user_id==u.id, Habit.active==True).all()
        app = [h for h in habits if habit_applies_today(h, yday)]
        logs = db.query(HabitLog).filter(HabitLog.user_id==u.id, HabitLog.date==yday).all()
        lm = {l.habit_id:l for l in logs}
        done = sum(1 for h in app if lm.get(h.id) and lm[h.id].completed)
        pct = round(done/len(app)*100) if app else 0
        lines = [f"📅 <b>Ayer</b> {color_emoji(pct)}\n", progress_bar(done,len(app))+"\n"]
        for h in app:
            lg = lm.get(h.id); d = lg and lg.completed
            lines.append(f"{'✅' if d else '❌'} {h.icon} {h.name}")
        await reply(upd, "\n".join(lines))
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()


# ── /rutinas, /morning, /night ──
async def cmd_rutinas(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        rs = db.query(Routine).filter(Routine.user_id==u.id, Routine.active==True).order_by(Routine.order).all()
        if not rs: await reply(upd, "No tiene rutinas."); return
        kb = [[InlineKeyboardButton(f"{r.icon} {r.name}", callback_data=f"routine_{r.id}")] for r in rs]
        await reply(upd, "📋 <b>Sus rutinas:</b>", InlineKeyboardMarkup(kb))
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()

async def cmd_morning(upd, ctx): await _routine_kw(upd, ["mañana","morning"])
async def cmd_night(upd, ctx): await _routine_kw(upd, ["noche","night"])

async def _routine_kw(upd, kws):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        rs = db.query(Routine).filter(Routine.user_id==u.id, Routine.active==True).all()
        r = next((r for r in rs if any(k in r.name.lower() for k in kws)), rs[0] if rs else None)
        if not r: await reply(upd, "No tiene rutinas."); return
        await _send_routine(upd, r, db)
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()

async def _send_routine(target, r, db):
    steps = db.query(RoutineStep).filter(RoutineStep.routine_id==r.id).order_by(RoutineStep.step_order).all()
    tt = sum(s.duration_minutes or 0 for s in steps)
    lines = [f"{r.icon} <b>{r.name}</b>"]
    if tt: lines.append(f"⏱ {tt} min\n")
    else: lines.append("")
    for s in steps:
        t = f" ({s.duration_minutes} min)" if s.duration_minutes else ""
        lines.append(f"{s.step_order}. {s.description}{t}")
    lines.append("\n💪 ¡A por ello!")
    text = "\n".join(lines)
    if hasattr(target,'message') and target.message: await target.message.reply_text(text, parse_mode=HTML)
    elif hasattr(target,'edit_message_text'): await target.edit_message_text(text, parse_mode=HTML)

async def callback_routine(upd, ctx):
    q = upd.callback_query; await q.answer()
    rid = int(q.data.replace("routine_",""))
    db = SessionLocal()
    try:
        r = db.query(Routine).filter(Routine.id==rid).first()
        if r: await _send_routine(q, r, db)
    finally: db.close()


# ── /racha ──
async def cmd_racha(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        hs = db.query(Habit).filter(Habit.user_id==u.id, Habit.active==True, Habit.archived==False).order_by(Habit.current_streak.desc()).all()
        lines = ["🔥 <b>Rachas</b>\n", f"🌐 <b>Global:</b> {u.global_streak} días (mejor: {u.best_global_streak})\n"]
        for h in hs:
            f = "🔥" if h.current_streak>=7 else "🌱" if h.current_streak>=3 else "·"
            lines.append(f"{f} {h.icon} {h.name}: {h.current_streak} (mejor: {h.best_streak})")
        await reply(upd, "\n".join(lines))
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()


# ── /nivel ──
async def cmd_nivel(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db); i = get_level_info(u)
        await reply(upd, f"⚡ <b>Nivel {i['level']}</b> — {i['title']}\n\nXP: {i['xp_in_level']}/{i['xp_next_level']}\n{progress_bar(i['xp_in_level'],i['xp_next_level'])}\n\nXP total: {i['xp']}")
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()


# ── /logros ──
async def cmd_logros(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        aa = db.query(Achievement).all()
        ui = {ua.achievement_id for ua in db.query(UserAchievement).filter(UserAchievement.user_id==u.id).all()}
        lines = [f"🏆 <b>Logros</b> ({len(ui)}/{len(aa)})\n"]
        for a in aa:
            if a.id in ui: lines.append(f"  {a.icon} <b>{a.name}</b>")
            else: lines.append(f"  🔒 <i>{a.name}</i>")
        await reply(upd, "\n".join(lines))
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()


# ── /semana ──
async def cmd_semana(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db); today = date.today(); mon = today-timedelta(days=today.weekday())
        dn = ["L","M","X","J","V","S","D"]; lines = ["📊 <b>Semana</b>\n"]; tc=0; th=0
        for i in range(7):
            day = mon+timedelta(days=i)
            hs = db.query(Habit).filter(Habit.user_id==u.id, Habit.active==True, Habit.archived==False).all()
            ap = [h for h in hs if habit_applies_today(h,day)]
            ls = db.query(HabitLog).filter(HabitLog.user_id==u.id, HabitLog.date==day, HabitLog.completed==True).all()
            d=len(ls); t=len(ap); tc+=d; th+=t
            mk = "📍" if day==today else " "
            ck = "✅" if d==t and t>0 else "❌" if t>0 else "·"
            lines.append(f"{mk}{dn[i]} {ck} {d}/{t} {progress_bar(d,t,6)}")
        wp = round(tc/th*100) if th else 0
        lines.append(f"\n<b>Total:</b> {tc}/{th} {color_emoji(wp)}")
        await reply(upd, "\n".join(lines))
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()


# ── /calendario ──
async def cmd_calendario(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db); today = date.today(); fd = today.replace(day=1)
        logs = db.query(HabitLog).filter(HabitLog.user_id==u.id, HabitLog.date>=fd, HabitLog.completed==True).all()
        hs = db.query(Habit).filter(Habit.user_id==u.id, Habit.active==True, Habit.archived==False).all()
        lines = [f"📅 <b>{today.strftime('%B %Y')}</b>\n", "L  M  X  J  V  S  D"]
        row = "   " * fd.weekday(); day = fd
        while day.month == today.month:
            ap = [h for h in hs if habit_applies_today(h, day)]
            dl = [l for l in logs if l.date==day]
            if day>today: c="· "
            elif not ap: c="· "
            elif len(dl)>=len(ap): c="✅"
            elif dl: c="🟡"
            else: c="❌"
            row += c+" "
            if day.weekday()==6: lines.append(row.rstrip()); row=""
            day += timedelta(days=1)
        if row.strip(): lines.append(row.rstrip())
        await reply(upd, "\n".join(lines))
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()


# ── /mood ──
async def cmd_mood(upd, ctx):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("😢 1",callback_data="mood_1"), InlineKeyboardButton("😞 2",callback_data="mood_2"),
        InlineKeyboardButton("😐 3",callback_data="mood_3"), InlineKeyboardButton("🙂 4",callback_data="mood_4"),
        InlineKeyboardButton("🤩 5",callback_data="mood_5")]])
    await reply(upd, "¿Cómo se siente hoy?", kb)

async def callback_mood(upd, ctx):
    q = upd.callback_query; await q.answer()
    lv = int(q.data.replace("mood_","")); tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db); today = date.today()
        ex = db.query(MoodLog).filter(MoodLog.user_id==u.id, MoodLog.date==today).first()
        if ex: ex.level=lv
        else: db.add(MoodLog(user_id=u.id,date=today,level=lv)); award_xp(db,u,"mood_log")
        db.commit()
        await edit(q, f"Registrado: {mood_emoji(lv)} ({lv}/5)\n\n¡Gracias!")
    except ValueError: await edit(q, NOT_LINKED)
    finally: db.close()


# ── /agua ──
async def cmd_agua(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db); today = date.today()
        lg = db.query(WaterLog).filter(WaterLog.user_id==u.id, WaterLog.date==today).first()
        if lg: lg.glasses+=1
        else: lg=WaterLog(user_id=u.id,date=today,glasses=1); db.add(lg)
        db.commit(); db.refresh(lg)
        e = "🎉" if lg.glasses>=lg.target else "💧"
        await reply(upd, f"{e} <b>Agua:</b> {lg.glasses}/{lg.target} vasos\n{progress_bar(lg.glasses,lg.target)}")
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()


# ── /sueno ──
async def cmd_sueno(upd, ctx):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("5h",callback_data="sleep_5"),InlineKeyboardButton("6h",callback_data="sleep_6"),
         InlineKeyboardButton("6.5h",callback_data="sleep_6.5"),InlineKeyboardButton("7h",callback_data="sleep_7")],
        [InlineKeyboardButton("7.5h",callback_data="sleep_7.5"),InlineKeyboardButton("8h",callback_data="sleep_8"),
         InlineKeyboardButton("8.5h",callback_data="sleep_8.5"),InlineKeyboardButton("9h+",callback_data="sleep_9")]])
    await reply(upd, "🛌 ¿Cuántas horas durmió?", kb)

async def callback_sleep(upd, ctx):
    q = upd.callback_query; await q.answer()
    hrs = float(q.data.replace("sleep_","")); tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db); today = date.today()
        ex = db.query(SleepLog).filter(SleepLog.user_id==u.id, SleepLog.date==today).first()
        if ex: ex.hours=hrs
        else: db.add(SleepLog(user_id=u.id,date=today,hours=hrs)); award_xp(db,u,"sleep_log")
        db.commit()
        await edit(q, f"{'😴' if hrs>=7 else '⚠️'} Registrado: {hrs}h de sueño")
    except ValueError: await edit(q, NOT_LINKED)
    finally: db.close()


# ── /nota ──
NOTE_TEXT = 0
async def cmd_nota(upd, ctx):
    await reply(upd, "✍️ Escriba su nota:"); return NOTE_TEXT

async def nota_text(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        db.add(JournalEntry(user_id=u.id, date=date.today(), content=upd.message.text))
        award_xp(db,u,"journal_entry"); db.commit()
        await reply(upd, "✅ Nota guardada.")
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()
    return ConversationHandler.END


# ── /inspiracion ──
async def cmd_inspiracion(upd, ctx):
    db = SessionLocal()
    try:
        q = get_random_quote(db)
        a = f"\n— <i>{q['author']}</i>" if q.get('author') else ""
        await reply(upd, f"💡 <b>Inspiración</b>\n\n<i>{q['text']}</i>{a}")
    finally: db.close()


# ── /tareas ──
async def cmd_tareas(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        ts = db.query(Task).filter(Task.user_id==u.id, Task.completed==False).order_by(Task.due_date.asc().nullslast()).limit(10).all()
        if not ts: await reply(upd, "✅ Sin tareas pendientes."); return
        pi = {"urgent":"🔴","high":"🟠","medium":"🟡","low":"🟢"}
        lines = [f"📝 <b>Tareas</b> ({len(ts)})\n"]
        kb = []
        for t in ts:
            due = f" (vence: {t.due_date})" if t.due_date else ""
            lines.append(f"{pi.get(t.priority,'⚪')} {t.title}{due}")
            kb.append([InlineKeyboardButton(f"✅ {t.title}", callback_data=f"task_done_{t.id}")])
        await reply(upd, "\n".join(lines), InlineKeyboardMarkup(kb))
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()

async def callback_task_done(upd, ctx):
    q = upd.callback_query; await q.answer()
    tid_task = int(q.data.replace("task_done_","")); tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        t = db.query(Task).filter(Task.id==tid_task, Task.user_id==u.id).first()
        if t: t.completed=True; t.completed_at=datetime.utcnow(); award_xp(db,u,"task_complete"); db.commit(); await edit(q, f"✅ <b>{t.title}</b> completada")
    except ValueError: await edit(q, NOT_LINKED)
    finally: db.close()


# ── /pomodoro ──
async def cmd_pomodoro(upd, ctx):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("15 min",callback_data="pomo_15"),InlineKeyboardButton("25 min",callback_data="pomo_25"),InlineKeyboardButton("45 min",callback_data="pomo_45")]])
    await reply(upd, "🍅 <b>Pomodoro</b>\n\n¿Cuánto tiempo?", kb)

async def callback_pomodoro(upd, ctx):
    q = upd.callback_query; await q.answer()
    mins = int(q.data.replace("pomo_","")); tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        s = PomodoroSession(user_id=u.id, date=date.today(), work_minutes=mins, break_minutes=5)
        db.add(s); db.commit(); db.refresh(s)
        ctx.job_queue.run_once(_pomo_done, when=mins*60, data={"sid":s.id,"cid":upd.effective_chat.id}, name=f"pomo_{s.id}")
        await edit(q, f"🍅 <b>Pomodoro: {mins} min</b>\n\nLe aviso cuando termine. ¡Foco!")
    except ValueError: await edit(q, NOT_LINKED)
    finally: db.close()

async def _pomo_done(ctx):
    d = ctx.job.data; db = SessionLocal()
    try:
        s = db.query(PomodoroSession).filter(PomodoroSession.id==d["sid"]).first()
        if s:
            s.completed=True; s.finished_at=datetime.utcnow()
            u = db.query(User).filter(User.id==s.user_id).first()
            if u: award_xp(db,u,"pomodoro_complete")
            db.commit()
        await ctx.bot.send_message(chat_id=d["cid"], text=f"🍅 <b>¡Pomodoro completado!</b>\n\n{s.work_minutes} min de foco. Descanso de {s.break_minutes} min. ☕", parse_mode=HTML)
    finally: db.close()


# ── /pausar, /reanudar, /modo ──
async def cmd_pausar(upd, ctx):
    tid = str(upd.effective_user.id); db = SessionLocal()
    try: u = require_user(tid,db); u.do_not_disturb=True; db.commit(); await reply(upd, "🔇 Recordatorios <b>pausados</b>. /reanudar para reactivar.")
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()

async def cmd_reanudar(upd, ctx):
    tid = str(upd.effective_user.id); db = SessionLocal()
    try: u = require_user(tid,db); u.do_not_disturb=False; db.commit(); await reply(upd, "🔔 Recordatorios <b>reactivados</b>.")
    except ValueError: await reply(upd, NOT_LINKED)
    finally: db.close()

async def cmd_modo(upd, ctx):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏃 Normal",callback_data="mode_normal")],
        [InlineKeyboardButton("🏖 Vacaciones",callback_data="mode_vacation")],
        [InlineKeyboardButton("🤒 Enfermo",callback_data="mode_sick")]])
    await reply(upd, "⚙️ <b>Cambiar modo:</b>", kb)

async def callback_mode(upd, ctx):
    q = upd.callback_query; await q.answer()
    mode = q.data.replace("mode_",""); tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid,db); u.mode=mode; db.commit()
        mn = {"normal":"🏃 Normal","vacation":"🏖 Vacaciones","sick":"🤒 Enfermo"}
        await edit(q, f"Modo: <b>{mn.get(mode,mode)}</b>")
    except ValueError: await edit(q, NOT_LINKED)
    finally: db.close()


# ── Logout ──
async def cmd_logout(upd, ctx):
    tid = str(upd.effective_user.id)
    db = SessionLocal()
    try:
        u = require_user(tid, db)
        u.telegram_id = None
        db.commit()
        await reply(upd, "👋 Cuenta desvinculada. Usa /login para vincular otra.")
    except ValueError:
        await reply(upd, "No tienes cuenta vinculada.")
    finally:
        db.close()


# ── Teclado persistente ──
async def handle_keyboard(upd, ctx):
    t = upd.message.text.strip()
    m = {"📋 Hábitos":cmd_habitos,"📊 Hoy":cmd_hoy,"🌅 Morning":cmd_morning,"🌙 Night":cmd_night,"💧 Agua":cmd_agua,"💡 Inspiración":cmd_inspiracion}
    h = m.get(t)
    if h: await h(upd, ctx)


# ── Setup ──
def create_bot_application():
    if not BOT_TOKEN:
        logger.warning("⚠️ Sin TELEGRAM_BOT_TOKEN. Bot deshabilitado.")
        return None
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("login", cmd_login)],
        states={LOGIN_EMAIL:[MessageHandler(filters.TEXT & ~filters.COMMAND, login_email)], LOGIN_PASSWORD:[MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)]},
        fallbacks=[CommandHandler("cancel", login_cancel)]))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("nota", cmd_nota)],
        states={NOTE_TEXT:[MessageHandler(filters.TEXT & ~filters.COMMAND, nota_text)]},
        fallbacks=[CommandHandler("cancel", login_cancel)]))

    for name, fn in [("start",cmd_start),("help",cmd_help),("habitos",cmd_habitos),("pendiente",cmd_pendiente),("hoy",cmd_hoy),("ayer",cmd_ayer),
                     ("morning",cmd_morning),("night",cmd_night),("rutinas",cmd_rutinas),("racha",cmd_racha),("nivel",cmd_nivel),("logros",cmd_logros),
                     ("semana",cmd_semana),("calendario",cmd_calendario),("mood",cmd_mood),("agua",cmd_agua),("sueno",cmd_sueno),
                     ("pomodoro",cmd_pomodoro),("inspiracion",cmd_inspiracion),("tareas",cmd_tareas),("pausar",cmd_pausar),("reanudar",cmd_reanudar),("modo",cmd_modo),("logout",cmd_logout)]:
        app.add_handler(CommandHandler(name, fn))

    for pat, fn in [("^habit_",callback_habit),("^mood_",callback_mood),("^sleep_",callback_sleep),("^pomo_",callback_pomodoro),
                    ("^task_done_",callback_task_done),("^routine_",callback_routine),("^mode_",callback_mode)]:
        app.add_handler(CallbackQueryHandler(fn, pattern=pat))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyboard))
    logger.info("🤖 Bot configurado")
    return app

async def start_bot(app):
    await app.initialize(); await app.start(); await app.updater.start_polling(drop_pending_updates=True)
    logger.info("🤖 Bot arrancado")

async def stop_bot(app):
    await app.updater.stop(); await app.stop(); await app.shutdown()
    logger.info("🤖 Bot parado")
