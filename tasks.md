# NexoTime v2 — Tasks

## Estado actual

### 1. Backend (Railway) ✅ COMPLETADO
- [x] 1.1 FastAPI con 71 endpoints
- [x] 1.2 PostgreSQL con 25 tablas
- [x] 1.3 Autenticación JWT + bcrypt
- [x] 1.4 Onboarding automático (9 hábitos, 2 rutinas, 5 recordatorios)
- [x] 1.5 Gamificación (XP, niveles, logros, rachas)
- [x] 1.6 Tracking (agua, sueño, mood, diario, pomodoro)
- [x] 1.7 Deploy en Railway: ACTIVO

### 2. Bot de Telegram ✅ COMPLETADO (con issues)
- [x] 2.1 25 comandos implementados
- [x] 2.2 7 callbacks con inline keyboards
- [x] 2.3 Teclado persistente
- [x] 2.4 Login por conversación
- [x] 2.5 Migración de MarkdownV2 → HTML
- [x] 2.6 Scheduler con 8 tipos de recordatorio
- [ ] 2.7 **PENDIENTE**: /habitos no responde (posible error en API /habits/log/today)
- [ ] 2.8 **PENDIENTE**: /inspiracion no responde (posible error en quotes)
- [ ] 2.9 Verificar TODOS los 25 comandos uno por uno

### 3. Web Dashboard 🔄 EN PROGRESO
- [x] 3.1 Proyecto Next.js creado y compilado
- [x] 3.2 Pantalla auth (login/registro)
- [x] 3.3 Pantalla Hoy (propósito, hábitos, agua, mood)
- [x] 3.4 Pantalla Hábitos (CRUD)
- [x] 3.5 Pantalla Rutinas (ver + desplegar)
- [x] 3.6 Pantalla Progreso (nivel, semana, logros)
- [x] 3.7 Pantalla Perfil
- [ ] 3.8 **PENDIENTE**: Subir a GitHub
- [ ] 3.9 **PENDIENTE**: Deploy en Vercel
- [ ] 3.10 **PENDIENTE**: Verificar conexión con API Railway
- [ ] 3.11 **PENDIENTE**: Configurar CORS en backend para URL de Vercel

### 4. Landing Page ❌ PENDIENTE
- [ ] 4.1 Página de ventas HTML
- [ ] 4.2 Sección hero con propuesta de valor
- [ ] 4.3 Comparativa vs otras apps
- [ ] 4.4 Pricing (3 planes)
- [ ] 4.5 Mockup de la app
- [ ] 4.6 Deploy en Vercel

### 5. Mejoras futuras ❌ BACKLOG
- [ ] 5.1 Editar rutinas desde la web
- [ ] 5.2 Crear recordatorios desde la web
- [ ] 5.3 Gráficos de progreso (Chart.js)
- [ ] 5.4 Notificaciones push web
- [ ] 5.5 Modo oscuro/claro toggle
- [ ] 5.6 Exportar datos a CSV
- [ ] 5.7 Integración Google Calendar
- [ ] 5.8 Análisis IA de patrones
