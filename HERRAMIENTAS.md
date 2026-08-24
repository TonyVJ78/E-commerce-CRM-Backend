# 🛠️ HERRAMIENTAS.md — Kantu Market

Registro de todas las herramientas, lenguajes, frameworks, librerías y servicios utilizados en el proyecto.

> **Última actualización**: Sprint 0

---

## Backend

| Herramienta | Versión | Descripción |
|-------------|---------|-------------|
| Python | 3.12 | Lenguaje de programación del backend |
| Django | 5.1.9 | Framework web principal |
| Django REST Framework | 3.16.0 | Toolkit para construir APIs REST |
| djangorestframework-simplejwt | 5.5.0 | Autenticación JWT (access + refresh tokens, blacklist) |
| django-cors-headers | 4.7.0 | Manejo de CORS para permitir peticiones del frontend |
| django-environ | 0.12.0 | Lectura de variables de entorno desde `.env` |
| psycopg2-binary | 2.9.10 | Driver de PostgreSQL para Python |
| Gunicorn | 23.0.0 | Servidor WSGI para producción (no usado en dev, incluido para futura referencia) |

## Frontend

| Herramienta | Versión | Descripción |
|-------------|---------|-------------|
| Node.js | 20 (Docker) / 24 (host) | Runtime de JavaScript |
| npm | 11.x | Gestor de paquetes de Node.js |
| Angular CLI | 19.2.x | CLI de Angular para scaffolding y compilación |
| Angular | 19.2.x | Framework frontend (standalone components) |
| TypeScript | 5.6.x | Lenguaje tipado que compila a JavaScript |
| RxJS | 7.x | Programación reactiva para HTTP y estados |
| Inter (Google Fonts) | — | Tipografía principal de la interfaz |

## Base de datos

| Herramienta | Versión | Descripción |
|-------------|---------|-------------|
| PostgreSQL | 16 (Alpine) | Base de datos relacional principal |

## Autenticación

| Herramienta | Versión | Descripción |
|-------------|---------|-------------|
| JWT (JSON Web Tokens) | — | Estándar de autenticación stateless |
| Token Blacklist | (simplejwt) | Invalidación de refresh tokens al logout |
| Django Password Reset Tokens | (nativo) | Tokens para recuperación de contraseña |

## Despliegue / DevOps

| Herramienta | Versión | Descripción |
|-------------|---------|-------------|
| Docker | 29.x | Contenedorización de servicios |
| Docker Compose | 5.x | Orquestación de contenedores para desarrollo local |

## Otros

| Herramienta | Versión | Descripción |
|-------------|---------|-------------|
| Git | — | Control de versiones |
| `.env` / `.env.example` | — | Gestión de variables de entorno sensibles |
