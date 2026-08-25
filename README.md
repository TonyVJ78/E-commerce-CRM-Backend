# 🛍️ Kantu Market

Plataforma SaaS multitenant que permite a empresas bolivianas crear y administrar su propia tienda online, con módulo de CRM y motor de recomendaciones por IA.

## 🏗️ Arquitectura

```
kantu-market/
├── client/          → Frontend Angular 19
├── server/          → Backend Django 5.1 + DRF
├── docker-compose.yml
├── .env.example
├── HERRAMIENTAS.md
└── README.md
```

## 🚀 Inicio Rápido

### Requisitos previos

- [Docker](https://www.docker.com/) (v20+)
- [Docker Compose](https://docs.docker.com/compose/) (v2+)

### 1. Clonar y configurar variables de entorno

```bash
git clone <repo-url>
cd kantu-market
cp .env.example .env
# Editar .env si se desea cambiar valores por defecto
```

### 2. Levantar con Docker Compose

```bash
docker-compose up --build
```

Esto levanta 3 servicios:

| Servicio | URL | Descripción |
|----------|-----|-------------|
| `db` | `localhost:5432` | PostgreSQL 16 |
| `server` | `http://localhost:8000` | Django REST API |
| `client` | `http://localhost:4200` | Angular Dev Server |

### 3. Acceder a la aplicación

- **Frontend**: [http://localhost:4200](http://localhost:4200)
- **API**: [http://localhost:8000/api/](http://localhost:8000/api/)
- **Admin Django**: [http://localhost:8000/admin/](http://localhost:8000/admin/)

> Las migraciones y datos semilla (roles: administrador, empresa, cliente) se ejecutan automáticamente al iniciar el contenedor `server`.

### 4. Crear superusuario (opcional)

```bash
docker-compose exec server python manage.py createsuperuser
```

## 📋 Sprint 0 — Casos de uso implementados

1. ✅ Registrar usuario (email, contraseña, rol)
2. ✅ Iniciar sesión (JWT)
3. ✅ Cerrar sesión (blacklist de refresh token)
4. ✅ Ver y editar perfil de usuario
5. ✅ Recuperar contraseña (email con token)
6. ✅ Registrar nueva tienda (asociada al usuario autenticado)

## 🔌 Endpoints API

| Método | Endpoint | Descripción | Auth |
|--------|----------|-------------|------|
| `POST` | `/api/auth/registro/` | Registrar usuario | ❌ |
| `POST` | `/api/auth/login/` | Obtener JWT tokens | ❌ |
| `POST` | `/api/auth/logout/` | Invalidar refresh token | ✅ |
| `POST` | `/api/auth/token/refresh/` | Renovar access token | ❌ |
| `GET` | `/api/auth/perfil/` | Ver perfil | ✅ |
| `PATCH` | `/api/auth/perfil/` | Editar perfil | ✅ |
| `POST` | `/api/auth/password-reset/` | Solicitar recuperación | ❌ |
| `POST` | `/api/auth/password-reset-confirm/` | Confirmar nueva contraseña | ❌ |
| `GET` | `/api/tiendas/` | Listar tiendas del usuario | ✅ |
| `POST` | `/api/tiendas/` | Crear nueva tienda | ✅ |

## 📧 Recuperación de contraseña

En desarrollo, los correos se imprimen en la **consola de Django** (backend de consola). Para ver el enlace de recuperación:

```bash
docker-compose logs -f server
```

Para configurar SMTP real, editar `.env`:
```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=tu-email@gmail.com
EMAIL_HOST_PASSWORD=tu-app-password
```

## 🗄️ Modelos de base de datos (Sprint 0)

- **Rol** — `administrador`, `empresa`, `cliente`
- **Usuario** — Extiende AbstractUser, email como login
- **BitacoraAcceso** — Registro de cada login exitoso
- **Tienda** — Tienda del tenant, asociada al propietario

## 🎨 Identidad Visual

Paleta inspirada en los colores patrios de Bolivia:
- 🔴 **Rojo** `#C8102E` — Color primario, botones principales, alertas
- 🟡 **Amarillo** `#F4D03F` — Acentos, gradientes, detalles
- 🟢 **Verde** `#27AE60` — Estados de éxito, badges activos

## 📄 Licencia

Proyecto académico — Todos los derechos reservados.
