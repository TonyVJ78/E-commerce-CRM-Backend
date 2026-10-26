# Habilitar Informes IA en el APK — para Tony

## Causa comprobada

El APK usa `https://kantumarket.vercel.app/api`. El 26/10/2026, la petición `GET /api/ia/informes/contexto/` devuelve **404** en ese servidor. La ruta ya existe en el backend de la rama `sincronizacion-equipo`, pero ese código aún no está publicado en la API que usa el APK. La carga falla antes de enviar texto, usar el micrófono o llamar a Anthropic. Firebase no interviene en esta petición.

## Cambio que debe desplegar el administrador de Vercel

Repositorio: https://github.com/TonyVJ78/E-commerce-CRM-Backend/tree/sincronizacion-equipo

1. En el proyecto Vercel que sirve `kantumarket.vercel.app/api`, desplegar la rama **sincronizacion-equipo**, conservando la configuración de servicios y rutas del proyecto existente. Se puede desplegar esa rama sin fusionarla a `main`.
2. Instalar las dependencias de backend declaradas en `requirements.txt` / `server/requirements.txt`; incluyen las exportaciones PDF y Excel. No desplegar solo el archivo de vistas: se necesitan también modelos, migraciones, permisos y servicios de informes.
3. Verificar que el entorno del servidor tenga la clave actualizada `ANTHROPIC_API_KEY`. El modelo usa `INFORMES_MODEL` y, por defecto, `ANTHROPIC_MODEL`. Las claves permanecen en el entorno privado del servidor; no van en Git ni en el APK.
4. Comprobar que Vercel use la base de datos prevista. Las 11 migraciones de integración ya se aplicaron con autorización en la base compartida del `.env` local. Ejecutar `python server/manage.py migrate --check` en el entorno del despliegue. Si hay pendientes o se usa otra base, revisar primero `migrate --plan`; no aplicar cambios a otra base sin revisar.

## Cómo verificar el despliegue

- `GET https://kantumarket.vercel.app/api/health/`: **200**.
- `GET https://kantumarket.vercel.app/api/ia/informes/contexto/` sin sesión: **401**, en lugar del 404 actual. Esta prueba solo comprueba la ruta y la autenticación.
- La misma petición con una cuenta empresa/administrador que tenga `informes.ver`: **200**, con las tiendas permitidas, ejemplos y permisos del usuario.
- En el APK, abrir Informes IA: debe aparecer el formulario y los ejemplos. Generar un informe requiere además `informes.crear`, una tienda autorizada y la configuración de Anthropic. La generación real sí consume el servicio de IA.
- Comprobar también que siguen funcionando el catálogo, el inicio de sesión y las rutas actuales.

## APK y alcance de esta corrección

El APK 1.0.0 (26) ya apunta a esa URL pública: **no necesita reemplazarse para que aparezcan los informes después de publicar el backend**.

La corrección móvil de la rama `sincronizacion-equipo` mejora los mensajes: distingue módulo aún no habilitado, sesión vencida, permisos y fallos de conexión; permite recuperarse al reintentar. Actualizar solo el APK no puede crear una ruta que falta en el servidor.

No se cambió `main`, no se desplegó producción sin acceso a Vercel y no se enviaron claves ni datos de clientes a terceros durante el diagnóstico. Las pruebas móviles de esta corrección usan respuestas HTTP simuladas y no generan informes reales.
