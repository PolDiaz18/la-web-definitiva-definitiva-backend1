"""
=============================================================================
DATABASE.PY — Configuración de la Base de Datos
=============================================================================
Este archivo configura la conexión a la base de datos.

En DESARROLLO (tu PC): usa SQLite (un archivo .db)
En PRODUCCIÓN (Railway): usa PostgreSQL (base de datos real en la nube)

¿Cómo sabe cuál usar?
→ Si existe la variable de entorno DATABASE_URL, usa PostgreSQL.
→ Si no existe, usa SQLite local.

SQLAlchemy: es una librería que te permite hablar con la base de datos
usando Python en vez de escribir SQL directamente.
Es como un "traductor": tú escribes Python → SQLAlchemy lo convierte a SQL.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ─────────────────────────────────────────────────────────────────────────────
# CONEXIÓN
# ─────────────────────────────────────────────────────────────────────────────

# DATABASE_URL viene de Railway automáticamente cuando añades PostgreSQL.
# Si no existe (estás en local), usamos SQLite.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nexotime.db")

# Railway da la URL con "postgres://" pero SQLAlchemy necesita "postgresql://"
# Además, usamos psycopg (v3) como driver, así que la URL debe ser "postgresql+psycopg://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# ─────────────────────────────────────────────────────────────────────────────
# ENGINE (Motor de la base de datos)
# ─────────────────────────────────────────────────────────────────────────────
# El engine es el "motor" que ejecuta las consultas SQL.
# connect_args={"check_same_thread": False} → solo necesario para SQLite
# porque SQLite no permite acceso desde múltiples hilos por defecto.

engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, echo=False, **engine_args)
# echo=False → no imprime cada consulta SQL en la terminal (pon True para debug)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION (Sesión de base de datos)
# ─────────────────────────────────────────────────────────────────────────────
# Una sesión es una "conversación" con la BD. Abres una, haces operaciones,
# y la cierras. SessionLocal es una "fábrica" de sesiones.

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ─────────────────────────────────────────────────────────────────────────────
# BASE (Clase base para los modelos)
# ─────────────────────────────────────────────────────────────────────────────
# Todos los modelos (User, Habit, etc.) heredan de esta clase.
# Es lo que les da "poderes" de base de datos.

Base = declarative_base()


def get_db():
    """
    Generador que crea una sesión de BD y la cierra al terminar.
    
    Se usa como "dependencia" en FastAPI:
      @app.get("/algo")
      def mi_endpoint(db: Session = Depends(get_db)):
          ...
    
    El 'yield' hace que:
    1. Se crea la sesión (db = SessionLocal())
    2. Se usa en el endpoint (yield db)
    3. Se cierra automáticamente (finally: db.close())
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Crea todas las tablas en la BD si no existen.
    Se llama una vez al arrancar la aplicación.
    
    Base.metadata.create_all → lee todos los modelos que heredan de Base
    y crea sus tablas correspondientes en la BD.
    """
    Base.metadata.create_all(bind=engine)
