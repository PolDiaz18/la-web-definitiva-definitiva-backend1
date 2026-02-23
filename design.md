# NexoTime v2 — Design

## Decisiones técnicas

### Backend en un solo proceso
El API, bot y scheduler corren en el mismo proceso Python. El API va en el thread principal (uvicorn), el bot en un thread secundario (polling), y el scheduler en otro (APScheduler async). Esto simplifica el deploy en Railway (1 servicio, 1 Procfile).

### PostgreSQL en vez de SQLite
SQLite no soporta accesos concurrentes bien cuando hay bot + API + scheduler accediendo a la vez. PostgreSQL lo maneja nativamente. Railway ofrece PG como addon gratis.

### HTML en vez de MarkdownV2 (Telegram)
MarkdownV2 de Telegram requiere escapar 18 caracteres especiales y rompe con nombres de hábitos que contengan `-`, `.`, `(`, `)`. HTML es 100% fiable. **NUNCA usar MarkdownV2.**

### JWT sin refresh tokens
Para simplificar. El token expira en 30 días. Si expira, el usuario hace login de nuevo. Suficiente para la escala actual.

### Next.js App Router (no Pages Router)
App Router es el estándar actual de Next.js 14. Usamos solo client components (`"use client"`) porque toda la app necesita estado y efectos.

---

## Non-Goals (fuera de alcance actual)

- OAuth / login con Google
- App móvil nativa
- Multi-idioma (solo español por ahora)
- Pagos / suscripciones reales
- Integración con Google Calendar
- IA / análisis con LLM
- Tests automatizados

---

## ⚠️ REGLAS PARA MODIFICAR EL CÓDIGO

### REGLA 1: Cambios mínimos
Si el usuario pide "cambia el color del botón", se cambia SOLO el color del botón. No se regenera el archivo entero. Se usa edición quirúrgica.

### REGLA 2: No reescribir archivos completos
Si hay un bug en una función, se arregla ESA función. No se reescribe bot.py entero. Excepción: si el cambio afecta la estructura fundamental del archivo (como pasar de MarkdownV2 a HTML).

### REGLA 3: Un cambio = un commit lógico
Cada cambio debe poder explicarse en una frase: "Arreglé el formato de /habitos" o "Añadí el campo propósito del día".

### REGLA 4: No romper lo que funciona
Antes de modificar algo, entender qué depende de ello. Si tocas `models.py`, piensa en qué endpoints y qué funciones del bot usan ese modelo.

### REGLA 5: Consistencia
- Backend: Python, snake_case, docstrings en español
- Frontend: JavaScript, camelCase, CSS variables
- Bot: HTML para Telegram, NUNCA MarkdownV2
- Comentarios: español
- API responses: inglés (JSON keys)

### REGLA 6: Probar antes de subir
Si se modifica el backend, hacer al menos una verificación rápida de que los endpoints afectados funcionan. Si se modifica el bot, verificar que el comando afectado responde.

---

## Estructura de archivos

```
nexotime-v2/ (backend - GitHub → Railway)
├── main.py            # API FastAPI (71 endpoints)
├── models.py          # 25 modelos SQLAlchemy
├── schemas.py         # Schemas Pydantic
├── database.py        # Conexión PostgreSQL
├── auth.py            # bcrypt + JWT
├── gamification.py    # XP, niveles, logros
├── bot.py             # Bot Telegram (HTML)
├── scheduler.py       # Recordatorios auto
├── requirements.txt   # Dependencias
├── Procfile           # uvicorn main:app
├── README.md
└── openspec/          # OpenSpec (este sistema)
    └── changes/
        └── nexotime-v2-full-spec/

nexotime-web/ (frontend - GitHub → Vercel)
├── app/
│   ├── page.js        # App completa (single file)
│   ├── globals.css    # Estilos
│   └── layout.js      # Layout + metadata
├── package.json
├── next.config.js
├── vercel.json
└── .gitignore
```
