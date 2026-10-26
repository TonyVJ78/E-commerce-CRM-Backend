# Integración del equipo y Firebase — 26 de octubre de 2026

## Qué quedó actualizado

Los tres proyectos de `C:\Proyecto SI2` están en `sincronizacion-equipo`. Se conservaron CU-25 a CU-28 y se incorporaron las novedades de Limber y rivero: CU-24 (segmentación automática en web/API), CU-33 (factura PDF), CU-34 (informes con IA y exportaciones), voz del chatbot y correcciones de pedidos/Stripe. La estructura local sigue usando `server/` en el backend y `client/` en la web. No se modifica `main`.

Se resolvieron las ramas de migraciones de CRM y marketing. Con autorización se aplicaron las 11 migraciones revisadas en la base compartida, con respaldo privado previo y comprobación de conteos de usuarios, tiendas, productos, variantes, pedidos y pagos. Se corrigieron la carga multipart de imágenes/variantes, la auditoría de stock y los SKU repetidos en la misma tienda. Los segmentos automáticos de CU-24 quedan disponibles para segmentar cupones CU-27 al recalcularlos, conservando los grupos manuales del CRM.

## Qué hicimos con Firebase

Proyecto: **Kantu Market SI2** (`kantu-market-si2`), en el plan **Spark**, sin facturación habilitada. Consola: https://console.firebase.google.com/project/kantu-market-si2/overview

Se registró Android con el paquete **bo.kantu.kantu_market**. Se instaló su configuración local y se integró Google Services con Gradle para que Android tenga los recursos de Firebase al iniciar el proceso, incluso antes de ejecutar Dart. El inicio de Flutter reconoce tanto esa configuración nativa como las opciones del archivo local. Referencia: https://firebase.google.com/docs/android/setup

Se creó la cuenta **Kantu backend notificaciones**, con el rol personalizado **Kantu Enviar FCM**, limitado a un solo permiso: `cloudmessaging.messages.create`. Su clave privada está en `secrets/firebase-admin.json` del backend; `.env` la referencia con `FIREBASE_CREDENTIALS_FILE` y activa `FCM_ENABLED=True`. Ambos archivos están excluidos de Git. La configuración Android también se conserva como archivo local ignorado.

| Componente | Responsabilidad |
| --- | --- |
| Django | Identifica al cliente con JWT, valida reglas/tienda, crea el aviso y solicita el envío |
| PostgreSQL | Conserva la bandeja, la lectura y los dispositivos registrados por cliente |
| Firebase Cloud Messaging | Transporta el mensaje al dispositivo Android |
| Flutter | Registra el dispositivo al activar avisos y abre carrito, cupón, producto o pedido según el tipo |

Se verificaron la autenticación real de la cuenta de servicio y una prueba FCM dirigida exclusivamente al Pixel 8. Google aceptó la validación y el envío. No se imprimieron tokens ni claves. Para que Android muestre avisos fuera de la app, el usuario debe abrir **Inicio → campana → Mis notificaciones → Activar notificaciones** y aceptar el permiso del sistema. La aceptación por FCM y la autorización de visualización de Android son comprobaciones distintas.

Los avisos continúan disponibles en la bandeja si falla una entrega. Cerrar sesión desactiva el registro del dispositivo. El backend descarta dispositivos cuyo token dejó de estar registrado; el móvil valida el destinatario y consulta datos actuales antes de abrir el destino.

## Cómo levantarlo en esta computadora

Abrir `C:\Proyecto SI2\Proyecto SI2.code-workspace` en Visual Studio Code. Para el móvil, seleccionar **Kantu Android + API local + Firebase** y pulsar F5. El Pixel 8 usa `http://10.0.2.2:8000/api` para llegar al backend de esta computadora; las claves nuevas del `.env` se cargan en ese backend local.

Backend, desde su carpeta:

```powershell
.\.venv\Scripts\python.exe server/manage.py runserver 127.0.0.1:8000
```

Web, desde `E-commerce-CRM-Fronted\client`:

```powershell
npm start -- --host 127.0.0.1
```

Móvil, desde `E-commerce-CRM-app-movil`:

```powershell
flutter run -d emulator-5554 --dart-define-from-file=config/firebase.local.json --dart-define=API_BASE_URL=http://10.0.2.2:8000/api
```

Para preparar otro equipo, obtener `google-services.json` del mismo proyecto y ejecutar en la carpeta móvil:

```powershell
python scripts/configurar_firebase.py RUTA/google-services.json
```

La clave privada del servidor debe instalarse mediante el mecanismo de secretos del despliegue. Los compañeros deben coordinar el acceso al proyecto con su propietaria. No copiar esa clave al APK ni publicarla en Git.

## Procesamiento automático y despliegue del equipo

La tarea de reglas de marketing está preparada en Django. Para inspeccionar candidatos sin enviar avisos/correos ni escribir registros:

```powershell
python server/manage.py procesar_marketing --dry-run
```

El responsable del despliegue puede programar `procesar_marketing` en su infraestructura. En este avance no se ejecutaron campañas masivas ni se instaló un cron que contacte clientes. El servidor publicado en Vercel necesita desplegar la rama y recibir sus secretos; el funcionamiento local no actualiza automáticamente ese despliegue.

## Explicación breve para los compañeros

“Creamos el proyecto Firebase de Kantu Market y registramos nuestra app Android. El backend sigue decidiendo qué aviso le corresponde a cada cliente y lo guarda en su bandeja. Firebase Cloud Messaging lleva ese aviso al celular. Para conectar Django creamos una cuenta técnica que solo puede enviar mensajes; su clave privada queda en el servidor. Probamos la conexión y un envío al emulador. Cada usuario activa el permiso de notificaciones en Android.”

## Validación

Se compiló la web y el APK Android. Pasaron las pruebas móviles y del backend, con PostgreSQL de pruebas aislado, además de la comprobación cruzada de segmentación y cupones. Se verificó la autenticación de Cloudinary, OpenAI y Anthropic con peticiones de lectura, sin generar contenido de IA ni mostrar claves. Las nuevas claves del `.env` se conservaron al configurar Firebase.
