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
| django-filter | 24.3 | Filtros declarativos por querystring para los endpoints de bitácora/auditoría (CU07) |
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

## App móvil

| Herramienta | Versión | Descripción |
|-------------|---------|-------------|
| Flutter | 3.47.2 | SDK de la app móvil multiplataforma |
| Dart | 3.13.2 | Lenguaje de la app móvil |
| provider | 6.1.2 | Gestión de estado (ChangeNotifier) de los servicios de la app |
| sqflite | 2.4.1 | Base de datos SQLite local para el modo autónomo offline |
| shared_preferences | 2.3.5 | Persistencia de sesión y configuración del backend (claves `km_*`) |
| http | 1.3.0 | Cliente HTTP contra la API REST de Django |
| image_picker | 1.1.2 | Selección de la imagen del producto desde galería o cámara (CU-08) |
| intl | 0.20.2 | Formato de fechas y números en es-BO |
| Inter (fuente empaquetada) | — | Tipografía principal, incluida como asset local |

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
