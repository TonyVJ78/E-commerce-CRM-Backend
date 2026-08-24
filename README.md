#  Kantu Market — Backend API

Backend RESTful y CRM para la plataforma SaaS multitenant **Kantu Market**, desarrollado con **Django 5.1**, **Django REST Framework**, **SimpleJWT** y **PostgreSQL 16**.

## Estructura del Repositorio

```
E-commerce-CRM-Backend/
├── server/               → Código fuente del backend Django
│   ├── apps/
│   │   ├── tiendas/      → Gestión multitenant de tiendas
│   │   └── usuarios/     → Autenticación, roles y usuarios
│   ├── config/           → Configuración global de Django
│   ├── Dockerfile        → Configuración del contenedor Docker
│   ├── entrypoint.sh     → Script de inicio y migraciones automáticas
│   ├── manage.py         → CLI de Django
│   ├── requirements.txt  → Dependencias de Python
│   └── seed_demo.py      → Datos iniciales de prueba
├── docker-compose.yml    → Orquestación de Backend y Base de Datos
├── test_api.py           → Suite de pruebas automatizadas de la API
├── HERRAMIENTAS.md       → Resumen de herramientas y librerías utilizadas
├── .env.example          → Plantilla de variables de entorno
└── README.md
```

## Inicio Rápido

### Requisitos previos
- [Docker](https://www.docker.com/) (v20+)
- [Docker Compose](https://docs.docker.com/compose/) (v2+)
- [Python](https://www.python.org/) 3.12+ (opcional para desarrollo local)

### 1. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env si deseas cambiar contraseñas o nombres de base de datos
```

### 2. Levantar con Docker Compose

```bash
docker-compose up --build
```

Esto levantará los siguientes servicios:

| Servicio | URL | Descripción |
|---|---|---|
| `db` | `localhost:5432` | Base de datos PostgreSQL 16 |
| `server` | `http://localhost:8000` | Django REST Framework API |

- **API Base**: [http://localhost:8000/api/](http://localhost:8000/api/)
- **Admin Django**: [http://localhost:8000/admin/](http://localhost:8000/admin/)

> Las migraciones y los roles iniciales (`administrador`, `empresa`, `cliente`) se ejecutan de manera automática al iniciar el contenedor `server`.

### 3. Ejecutar pruebas automatizadas

Con el servidor corriendo, puedes ejecutar la suite de pruebas:
```bash
python test_api.py
```
---

##  Endpoints API

| Método | Endpoint | Descripción | Requiere Auth |
|---|---|---|:---:|
| `POST` | `/api/auth/registro/` | Registrar nuevo usuario | ❌ |
| `POST` | `/api/auth/login/` | Iniciar sesión y obtener JWT tokens | ❌ |
| `POST` | `/api/auth/logout/` | Cerrar sesión e invalidar refresh token | ✅ |
| `POST` | `/api/auth/token/refresh/` | Renovar access token expirado | ❌ |
| `GET` | `/api/auth/perfil/` | Consultar perfil del usuario actual | ✅ |
| `PATCH` | `/api/auth/perfil/` | Editar información del perfil | ✅ |
| `POST` | `/api/auth/password-reset/` | Solicitar restablecimiento de contraseña | ❌ |
| `POST` | `/api/auth/password-reset-confirm/` | Confirmar nueva contraseña con token | ❌ |
| `GET` | `/api/tiendas/` | Listar tiendas del usuario autenticado | ✅ |
| `POST` | `/api/tiendas/` | Registrar una nueva tienda | ✅ |

---

##  Modelos de Base de Datos (Sprint 0)

- **Rol**: `administrador`, `empresa`, `cliente` (poblado automáticamente por migración semilla).
- **Usuario**: Extensión de `AbstractUser` con `email` como identificador único principal.
- **BitacoraAcceso**: Registro de auditoría con fecha, hora, IP y usuario en cada login exitoso.
- **Tienda**: Modelo multitenant para la gestión de tiendas vinculadas a un usuario propietario.
