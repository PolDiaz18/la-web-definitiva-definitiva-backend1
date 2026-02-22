"""
=============================================================================
AUTH.PY — Sistema de Autenticación
=============================================================================
Gestiona:
  - Hashing de contraseñas (nunca guardar contraseñas en texto plano)
  - Creación y verificación de tokens JWT
  - Obtener el usuario actual desde un token

JWT (JSON Web Token):
  Es una cadena de texto que identifica al usuario.
  Flujo:
    1. Usuario envía email + contraseña
    2. Si son correctos, el servidor genera un JWT
    3. El usuario envía ese JWT en cada petición siguiente
    4. El servidor verifica el JWT y sabe quién es el usuario
  
  Es como un "pase VIP": lo enseñas en la puerta y te dejan pasar
  sin tener que dar tu nombre y contraseña cada vez.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import get_db
from models import User

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("SECRET_KEY", "nexotime-dev-secret-key-cambiar-en-produccion")
# SECRET_KEY → clave secreta para firmar los JWT. En producción, usa una larga y aleatoria.

ALGORITHM = "HS256"
# ALGORITHM → algoritmo de encriptación. HS256 es estándar y seguro.

ACCESS_TOKEN_EXPIRE_DAYS = 30
# ACCESS_TOKEN_EXPIRE_DAYS → el token dura 30 días. Después, hay que volver a hacer login.

# ─────────────────────────────────────────────────────────────────────────────
# HASHING DE CONTRASEÑAS
# ─────────────────────────────────────────────────────────────────────────────
# bcrypt convierte "mi_contraseña" en algo como "$2b$12$LJ3m5..."
# Es IRREVERSIBLE: no puedes obtener la contraseña original desde el hash.
# Usamos bcrypt directamente (más fiable en producción que passlib).

import bcrypt


def hash_password(password: str) -> str:
    """Convierte una contraseña en texto plano a un hash seguro"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara una contraseña en texto plano con un hash almacenado"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# TOKENS JWT
# ─────────────────────────────────────────────────────────────────────────────

def create_access_token(user_id: int, email: str) -> str:
    """
    Crea un token JWT con el ID y email del usuario.
    
    El token contiene:
      - sub (subject): el ID del usuario
      - email: para referencia
      - exp (expiration): cuándo caduca
    
    Todo esto se "firma" con la SECRET_KEY para que nadie pueda falsificarlo.
    """
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": str(user_id),
        "email": email,
        "exp": expire
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """
    Decodifica un token JWT y devuelve sus datos.
    Si el token es inválido o ha expirado, devuelve None.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DEPENDENCIA: OBTENER USUARIO ACTUAL
# ─────────────────────────────────────────────────────────────────────────────
# Esto se usa como "dependencia" en FastAPI para proteger endpoints.
# Si el token es válido → devuelve el usuario.
# Si no → lanza error 401 (no autorizado).

security = HTTPBearer()
# HTTPBearer → busca el token en el header "Authorization: Bearer <token>"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Extrae el usuario del token JWT.
    
    Se usa así en los endpoints:
      @app.get("/mis-datos")
      def mis_datos(user: User = Depends(get_current_user)):
          return user.name
    
    FastAPI automáticamente:
    1. Lee el header "Authorization: Bearer eyJ..."
    2. Llama a esta función con el token
    3. Si es válido, inyecta el usuario en el endpoint
    4. Si no, devuelve 401
    """
    token = credentials.credentials
    payload = decode_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin identificador de usuario"
        )
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    # Actualizar última actividad
    user.last_active = datetime.utcnow()
    db.commit()
    
    return user
