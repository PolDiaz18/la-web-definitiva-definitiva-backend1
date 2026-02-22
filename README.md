# NexoTime v2 — Backend

Sistema completo de productividad y coaching automatizado.

## Arquitectura

| Archivo | Descripción |
|---------|------------|
| `database.py` | Conexión BD (SQLite local / PostgreSQL prod) |
| `models.py` | 25 tablas con relaciones |
| `schemas.py` | Validación Pydantic entrada/salida |
| `auth.py` | JWT + hashing contraseñas |
| `gamification.py` | XP, niveles, rachas, logros |
| `main.py` | 60+ endpoints API REST |
| `bot.py` | Bot de Telegram (PENDIENTE) |
| `scheduler.py` | Recordatorios programados (PENDIENTE) |

## Variables de entorno (Railway)

```
SECRET_KEY=tu-clave-secreta-larga
DATABASE_URL=postgresql://... (Railway la pone automáticamente)
TELEGRAM_BOT_TOKEN=tu-token-de-botfather
```

## Desarrollo local

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Endpoints

Visita `/docs` para la documentación interactiva (Swagger).
