# NexoTime v2 — Proposal

## Why

Las apps de productividad actuales son pasivas: el usuario tiene que acordarse de abrir la app. NexoTime es un **coach automatizado** que va al usuario, no al revés. Combina hábitos, rutinas, progreso y gamificación en un sistema que te busca por Telegram y te da control total desde la web.

## What Changes

NexoTime v2 es el sistema completo con 3 interfaces:

- **Backend API** (FastAPI + PostgreSQL en Railway) — el cerebro
- **Bot de Telegram** — el coach que te busca
- **Web Dashboard** (Next.js en Vercel) — el panel de control

## Capabilities

### Core
- `auth`: Registro, login, JWT tokens, vinculación Telegram
- `habits`: CRUD de hábitos, logging diario, rachas, frecuencias personalizadas
- `routines`: Rutinas con pasos ordenados y tiempos estimados
- `reminders`: 8 tipos de recordatorio con insistencia escalable
- `gamification`: XP, niveles, logros, rachas globales
- `tracking`: Agua, sueño, estado de ánimo, diario, pomodoro
- `purpose`: Propósito del día editable desde la web

### Interfaces
- `telegram-bot`: 25 comandos, 7 callbacks, teclado persistente
- `web-dashboard`: 5 pantallas (Hoy, Hábitos, Rutinas, Progreso, Perfil)
- `landing-page`: Página de ventas con pricing

## Impact

- 11 archivos backend (Python)
- 7 archivos frontend (Next.js)
- 1 landing page (HTML estático)
- 71 endpoints API
- 25 tablas en base de datos

## Filosofía

Tres pilares:
1. **¿Qué hago?** → Configurar hábitos, rutinas, objetivos
2. **¿Lo hago?** → Tracking, recordatorios, accountability
3. **¿De qué está hecho?** → Gamificación, progreso, análisis
