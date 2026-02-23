# NexoTime v2 — Specs

## Arquitectura

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   WEB (Vercel)  │────▶│ BACKEND (Railway) │◀────│ BOT (Telegram)  │
│   Next.js 14    │     │ FastAPI + PG      │     │ python-telegram  │
│   5 pantallas   │     │ 71 endpoints      │     │ 25 comandos      │
└─────────────────┘     │ + Scheduler       │     └─────────────────┘
                        └──────────────────┘
```

---

## Backend (11 archivos)

### Archivos y responsabilidad

| Archivo | Qué hace | Líneas aprox |
|---------|----------|-------------|
| `main.py` | API FastAPI, 71 endpoints, CORS, lifespan | 1800 |
| `models.py` | 25 modelos SQLAlchemy (tablas BD) | 500 |
| `schemas.py` | Schemas Pydantic (validación entrada/salida) | 300 |
| `database.py` | Conexión PostgreSQL, SessionLocal | 80 |
| `auth.py` | bcrypt, JWT, hash_password, verify_password | 100 |
| `gamification.py` | XP, niveles, logros, rachas, citas | 400 |
| `bot.py` | Bot Telegram completo (HTML, no MarkdownV2) | 700 |
| `scheduler.py` | 8 tipos de recordatorio automático | 300 |
| `requirements.txt` | Dependencias Python | 15 |
| `Procfile` | Comando de arranque para Railway | 1 |
| `README.md` | Documentación del proyecto | - |

### Base de datos (25 tablas)

| Tabla | Campos clave |
|-------|-------------|
| `users` | id, name, email, password_hash, telegram_id, xp, level, global_streak, mode, timezone |
| `habits` | id, user_id, name, icon, category, frequency, days, habit_type, target_quantity, current_streak, best_streak |
| `habit_logs` | id, user_id, habit_id, date, completed, quantity_logged |
| `routines` | id, user_id, name, icon, active, order |
| `routine_steps` | id, routine_id, step_order, description, duration_minutes |
| `reminders` | id, user_id, type, time, days, active, linked_routine_id |
| `tasks` | id, user_id, title, priority, due_date, completed |
| `goals` | id, user_id, title, category, deadline |
| `achievements` | id, name, icon, description, condition_type, condition_value |
| `user_achievements` | id, user_id, achievement_id, unlocked_at |
| `mood_logs` | id, user_id, date, level (1-5) |
| `water_logs` | id, user_id, date, glasses, target |
| `sleep_logs` | id, user_id, date, hours |
| `journal_entries` | id, user_id, date, content |
| `pomodoro_sessions` | id, user_id, date, work_minutes, completed |
| `quotes` | id, text, author, category |

### API Endpoints (71 total)

| Grupo | Endpoints | Ejemplos |
|-------|-----------|----------|
| Auth (6) | register, login, me, update, delete, telegram-link |
| Habits (12) | CRUD, log, today, week, streaks, reorder |
| Routines (8) | CRUD, steps, reorder |
| Reminders (6) | CRUD, toggle, by-type |
| Tracking (10) | mood, water, sleep, journal, pomodoro |
| Gamification (8) | level, achievements, leaderboard, quotes |
| Stats (4) | overview, heatmap, export |
| Onboarding (2) | setup, complete |
| Tasks/Goals (8) | CRUD para cada uno |
| Telegram (7) | link, unlink, status, send-test |

---

## Bot de Telegram (25 comandos)

### Comandos

| Comando | Qué hace |
|---------|----------|
| `/start` | Bienvenida o resumen si ya vinculado |
| `/login` | Conversación: email → password → vincula cuenta |
| `/help` | Lista todos los comandos |
| `/habitos` | Lista hábitos del día con botones ✅ inline |
| `/pendiente` | Solo los hábitos que faltan |
| `/hoy` | Resumen rápido: hábitos, agua, ánimo, racha, nivel |
| `/ayer` | Resumen del día anterior |
| `/morning` | Rutina de mañana con pasos |
| `/night` | Rutina de noche con pasos |
| `/rutinas` | Todas las rutinas con botones |
| `/racha` | Rachas de todos los hábitos + global |
| `/nivel` | XP actual, barra de progreso, título |
| `/logros` | Logros desbloqueados y bloqueados |
| `/semana` | Heatmap semanal L-D |
| `/calendario` | Mapa de calor del mes |
| `/mood` | 5 botones inline (😢😞😐🙂🤩) |
| `/agua` | Suma 1 vaso, muestra progreso |
| `/sueno` | Botones para registrar horas |
| `/nota` | Conversación: escribe → guarda en diario |
| `/pomodoro` | Botones 15/25/45 min, avisa cuando acaba |
| `/inspiracion` | Cita motivacional aleatoria |
| `/tareas` | Lista tareas pendientes con botones ✅ |
| `/pausar` | Pausa recordatorios |
| `/reanudar` | Reactiva recordatorios |
| `/modo` | Cambiar modo: normal/vacaciones/enfermo |

### Regla técnica CRÍTICA
- **SIEMPRE usar HTML** (`parse_mode=ParseMode.HTML`) para formatear mensajes
- **NUNCA usar MarkdownV2** — causa errores con caracteres como `-`, `.`, `(`, `)`
- Negrita: `<b>texto</b>`, Cursiva: `<i>texto</i>`

### Callbacks (7)

| Pattern | Acción |
|---------|--------|
| `habit_do_*` | Marcar hábito completado |
| `habit_undo_*` | Desmarcar hábito |
| `habit_qty_*` | Incrementar cantidad (+1) |
| `mood_*` | Registrar estado de ánimo |
| `sleep_*` | Registrar horas de sueño |
| `pomo_*` | Iniciar pomodoro |
| `task_done_*` | Completar tarea |
| `routine_*` | Ver rutina específica |
| `mode_*` | Cambiar modo |

### Scheduler (8 tipos de recordatorio)

| Tipo | Cuándo | Qué hace |
|------|--------|----------|
| `morning` | ~7:00 | Lista hábitos del día + cita motivacional |
| `midday` | ~13:00 | Checkpoint: progreso + pendientes |
| `evening` | ~20:00 | Insistencia: racha en juego + botones |
| `night` | ~22:00 | Última llamada con botones directos |
| `summary` | ~23:00 | Resumen completo del día |
| `weekly_summary` | Domingos | Resumen semanal con heatmap |
| `routine` | Configurable | Recuerda ejecutar rutina específica |
| `custom` | Configurable | Mensaje personalizado |

---

## Web Dashboard (Next.js)

### 5 Pantallas

| Pantalla | Contenido |
|----------|-----------|
| **Hoy** | Propósito del día, hábitos para marcar, agua (+vaso), mood (5 botones), stats rápidos |
| **Hábitos** | CRUD completo: crear, editar (nombre/icono/categoría/frecuencia/días), eliminar |
| **Rutinas** | Ver rutinas con pasos desplegables |
| **Progreso** | Nivel + barra XP, semana visual (heatmap), logros (desbloqueados/bloqueados) |
| **Perfil** | Info usuario, stats, config (modo/recordatorios/timezone), cerrar sesión |

### Reglas técnicas
- Single Page App con estado en React (`useState`)
- API_URL configurable en la línea 1 del archivo
- Token JWT guardado en `localStorage`
- Auto-logout si 401

---

## Infraestructura

| Componente | Plataforma | URL |
|-----------|-----------|-----|
| Backend API | Railway | `*.up.railway.app` |
| PostgreSQL | Railway (addon) | Interna |
| Bot Telegram | Railway (mismo proceso) | @NexoTimebot |
| Scheduler | Railway (mismo proceso) | — |
| Web Dashboard | Vercel | `*.vercel.app` |
| Landing Page | Vercel (separada) | TBD |

### Variables de entorno (Railway)

| Variable | Uso |
|----------|-----|
| `DATABASE_URL` | PostgreSQL connection string |
| `TELEGRAM_BOT_TOKEN` | Token del bot |
| `JWT_SECRET` | Secreto para tokens |
| `CORS_ORIGINS` | URLs permitidas (web) |

---

## Brand

| Elemento | Valor |
|----------|-------|
| Color primario | Ember Red `#CC3333` |
| Color fondo | `#0a0a0f` (casi negro) |
| Font títulos | Outfit (800) |
| Font mono | JetBrains Mono |
| Logo | 🔷 (diamond emoji) |
| Tono | Formal pero cercano (usted, no tú) |
