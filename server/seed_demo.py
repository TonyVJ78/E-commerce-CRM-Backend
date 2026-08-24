import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.usuarios.models import Rol, Usuario, BitacoraAcceso
from apps.tiendas.models import Tienda

print("--- 1. Poblando Roles ---")
roles = ['administrador', 'empresa', 'cliente']
for nombre in roles:
    obj, created = Rol.objects.get_or_create(nombre=nombre)
    estado = "creado" if created else "ya existía"
    print(f"Rol '{nombre}': {estado} (ID: {obj.id})")

print("\n--- 2. Creando Usuarios Demo para cada Rol ---")
usuarios_demo = [
    {
        "email": "admin@kantu.bo",
        "password": "Password123!",
        "rol": "administrador",
        "first_name": "Administrador",
        "last_name": "Sistema",
        "is_staff": True,
        "is_superuser": True
    },
    {
        "email": "empresa@kantu.bo",
        "password": "Password123!",
        "rol": "empresa",
        "first_name": "Carlos",
        "last_name": "Mamani",
        "is_staff": False,
        "is_superuser": False
    },
    {
        "email": "cliente@kantu.bo",
        "password": "Password123!",
        "rol": "cliente",
        "first_name": "Ana",
        "last_name": "Pérez",
        "is_staff": False,
        "is_superuser": False
    }
]

for data in usuarios_demo:
    rol = Rol.objects.get(nombre=data["rol"])
    user = Usuario.objects.filter(email=data["email"]).first()
    if not user:
        user = Usuario.objects.create_user(
            email=data["email"],
            password=data["password"],
            rol=rol,
            first_name=data["first_name"],
            last_name=data["last_name"],
            is_staff=data["is_staff"],
            is_superuser=data["is_superuser"],
            activo=True
        )
        print(f"✅ Usuario creado: {data['email']} | Rol: {data['rol']} | Pass: {data['password']}")
    else:
        user.set_password(data["password"])
        user.rol = rol
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]
        user.is_staff = data["is_staff"]
        user.is_superuser = data["is_superuser"]
        user.activo = True
        user.save()
        print(f"🔄 Usuario actualizado: {data['email']} | Rol: {data['rol']} | Pass: {data['password']}")

print("\n--- 3. Creando Tienda Demo para el usuario Empresa ---")
empresa_user = Usuario.objects.get(email="empresa@kantu.bo")
tienda, t_created = Tienda.objects.get_or_create(
    propietario=empresa_user,
    slug="artesanias-bolivianas",
    defaults={
        "nombre": "Artesanías Bolivianas",
        "color_primario": "#C8102E",
        "descripcion": "Tienda demostrativa de textiles y artesanías andinas de Bolivia.",
        "activa": True
    }
)
t_estado = "creada" if t_created else "ya existía"
print(f"Tienda '{tienda.nombre}': {t_estado} (Propietario: {empresa_user.email})")

print("\n🎉 Base de datos poblada con éxito.")
