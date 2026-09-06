"""
Vistas del módulo de Usuarios.
Sprint 0: Registro, Login, Logout, Perfil, Recuperar contraseña.
"""

import logging

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .audit import (
    ACCION_ACTUALIZAR,
    ACCION_CERRAR_SESION,
    ACCION_CREAR,
    registrar_auditoria,
)
from .models import BitacoraAcceso
from .serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PerfilSerializer,
    RegistroSerializer,
)

Usuario = get_user_model()

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Extrae la IP del cliente de la petición HTTP."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def registrar_acceso(request, *, email, exitoso, usuario=None, motivo=''):
    """Registra una fila en `bitacora_acceso` para un intento de login.

    Se llama tanto en el éxito como en cada rechazo. Nunca rompe la petición.
    """
    try:
        BitacoraAcceso.objects.create(
            usuario=usuario,
            email_intento=(email or '')[:254],
            exitoso=exitoso,
            motivo=motivo[:100],
            ip=get_client_ip(request),
            dispositivo=request.META.get('HTTP_USER_AGENT', '')[:255],
        )
    except Exception:
        logging.getLogger(__name__).exception('No se pudo registrar el acceso en bitácora')


class RegistroView(generics.CreateAPIView):
    """POST /api/auth/registro/ — Registrar un nuevo usuario."""
    serializer_class = RegistroSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        registrar_auditoria(
            request,
            ACCION_CREAR,
            tabla=Usuario._meta.db_table,
            registro_id=usuario.pk,
            datos_nuevos={
                'email': usuario.email,
                'rol': usuario.rol.nombre if usuario.rol else None,
            },
        )
        return Response(
            {
                'mensaje': 'Usuario registrado exitosamente.',
                'usuario': {
                    'id': usuario.id,
                    'email': usuario.email,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """POST /api/auth/login/ — Obtener tokens JWT."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        usuario = authenticate(request, email=email, password=password)

        if usuario is None:
            # `authenticate` falla tanto por contraseña incorrecta como por
            # email inexistente; resolvemos el usuario (si existe) para la bitácora.
            usuario_existente = Usuario.objects.filter(email__iexact=email).first()
            registrar_acceso(
                request,
                email=email,
                exitoso=False,
                usuario=usuario_existente,
                motivo='Credenciales inválidas',
            )
            return Response(
                {'error': 'Credenciales inválidas.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not usuario.activo:
            registrar_acceso(
                request,
                email=email,
                exitoso=False,
                usuario=usuario,
                motivo='Cuenta desactivada',
            )
            return Response(
                {'error': 'Esta cuenta está desactivada.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Generar tokens JWT
        refresh = RefreshToken.for_user(usuario)

        # Registrar el acceso exitoso en la bitácora
        registrar_acceso(request, email=email, exitoso=True, usuario=usuario)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'usuario': {
                'id': usuario.id,
                'email': usuario.email,
                'first_name': usuario.first_name,
                'last_name': usuario.last_name,
                'rol': usuario.rol.nombre if usuario.rol else None,
            },
        })


class LogoutView(APIView):
    """POST /api/auth/logout/ — Invalidar refresh token."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if not refresh_token:
                return Response(
                    {'error': 'Se requiere el refresh token.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            logger.warning('Logout con refresh token inválido para el usuario %s', request.user.pk)
            return Response(
                {'error': 'Token inválido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        registrar_auditoria(
            request,
            ACCION_CERRAR_SESION,
            tabla='sesion',
            registro_id=request.user.id,
        )
        return Response(
            {'mensaje': 'Sesión cerrada exitosamente.'},
            status=status.HTTP_200_OK,
        )


class PerfilView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/auth/perfil/ — Ver perfil del usuario autenticado.
    PATCH /api/auth/perfil/ — Editar perfil.
    """
    serializer_class = PerfilSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/ — Solicitar email de recuperación."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        # Siempre responder 200 para no revelar si el email existe
        try:
            usuario = Usuario.objects.get(email=email)
            uid = urlsafe_base64_encode(force_bytes(usuario.pk))
            token = default_token_generator.make_token(usuario)
            reset_url = f"{settings.FRONTEND_URL}/recuperar-password/{uid}/{token}"

            try:
                send_mail(
                    subject='Kantu Market — Recuperación de contraseña',
                    message=(
                        f'Hola {usuario.first_name or usuario.email},\n\n'
                        f'Recibimos una solicitud para restablecer tu contraseña.\n'
                        f'Usa el siguiente enlace para establecer una nueva contraseña:\n\n'
                        f'{reset_url}\n\n'
                        f'Si no solicitaste este cambio, ignora este correo.\n\n'
                        f'— Equipo Kantu Market'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(f"Error al enviar correo de recuperación a {email}: {e}")
                # En desarrollo o si falla el backend de email, se imprime en consola para facilitar pruebas
                print(f"\n=======================================================")
                print(f"🔑 [RECUPERAR CONTRASEÑA] Enlace generado para {email}:")
                print(f"🔗 {reset_url}")
                print(f"=======================================================\n")
        except Usuario.DoesNotExist:
            pass  # No revelar que el email no existe

        return Response(
            {'mensaje': 'Si el correo existe en nuestro sistema, recibirás un enlace de recuperación.'},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset-confirm/ — Confirmar nueva contraseña."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()
        # El actor es anónimo (se identifica por el token del email), por eso
        # `usuario` queda NULL en el log; `registro_id` indica a quién se le cambió.
        registrar_auditoria(
            request,
            ACCION_ACTUALIZAR,
            tabla=Usuario._meta.db_table,
            registro_id=usuario.pk,
            datos_nuevos={
                'evento': 'restablecimiento de contraseña',
                'email': usuario.email,
            },
        )
        return Response(
            {'mensaje': 'Contraseña restablecida exitosamente.'},
            status=status.HTTP_200_OK,
        )
