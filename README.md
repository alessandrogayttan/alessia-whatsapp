# Alessia — Asistente WhatsApp de Inpulso 43

## Requisitos previos

- Python 3.11+
- Cuenta de WhatsApp Business API (Meta)
- Cuenta de servicio de Google con acceso a Calendar y Sheets
- API key de Gemini

## Configuración local

1. Copia el archivo de entorno:

```bash
copy .env.example .env
```

2. Edita `.env` con tus llaves reales. **Rota** cualquier token que haya estado expuesto en código anterior.

3. Instala dependencias:

```bash
pip install -r requirements.txt
```

4. Coloca el JSON de la cuenta de servicio de Google en la raíz del proyecto.

5. Inicia en desarrollo:

```bash
python servidor.py
```

6. Verifica salud:

```
GET http://localhost:5000/health
```

## Webhook de WhatsApp (Meta)

En el panel de Meta Developers configura:

| Campo | Valor |
|-------|-------|
| Callback URL | `https://tu-dominio.com/webhook` |
| Verify Token | El mismo valor que `WHATSAPP_VERIFY_TOKEN` en `.env` |
| App Secret | Va en `WHATSAPP_APP_SECRET` (para validar firmas POST) |

## Producción con Docker

```bash
docker compose up -d --build
```

El servicio escucha en el puerto 5000. Coloca un proxy inverso (nginx/Caddy) con HTTPS delante.

## Producción con Gunicorn (sin Docker)

```bash
set FLASK_ENV=production
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 wsgi:app
```

## Estructura del proyecto

| Archivo | Función |
|---------|---------|
| `servidor.py` | App Flask y webhook |
| `chat.py` | Conversación con Gemini |
| `tools.py` | Agenda, citas, Sheets |
| `jobs.py` | Recordatorios y lista de espera |
| `storage.py` | Persistencia SQLite |
| `config.py` | Variables de entorno |
| `precios.json` | Catálogo de servicios |

> **Nota:** `Agente.py` es una versión anterior. Usa `servidor.py` como entrada principal.

## Comandos especiales para pacientes

- `ELIMINAR DATOS` — borra datos locales del paciente
- `HABLAR CON PERSONA` — escala a recepción

## Checklist antes del lanzamiento

- [ ] Tokens rotados y guardados solo en `.env`
- [ ] `FLASK_ENV=production` con todas las variables requeridas
- [ ] HTTPS activo en el webhook
- [ ] Plantillas de WhatsApp aprobadas para mensajes proactivos (recordatorios)
- [ ] `API_KEY_MAPS` configurada (opcional, para alertas de tráfico)
- [ ] Probar agendar, cancelar y recordatorios en entorno de prueba
