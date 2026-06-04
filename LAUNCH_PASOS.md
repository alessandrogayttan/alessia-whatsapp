# Lanzamiento oficial de Alessia — Esta noche

Código listo con: ack inmediato, reintentos de envío WhatsApp, health `/health/ready`, volumen persistente en `.do/app.yaml`.

**Tú debes completar las secciones marcadas con ✋ (no se pueden automatizar desde aquí).**

---

## Parte A — Subir código (15 min)

### 1. Commit y push a GitHub

En PowerShell, desde la carpeta del proyecto:

```powershell
cd "c:\Users\aless\OneDrive\Desktop\ALESSIA"
git add .
git status
git commit -m "Preparación lanzamiento: ack, reintentos WhatsApp, health ready, volumen DB"
git push origin main
```

Si DigitalOcean está conectado al repo, el deploy arrancará solo.

### 2. Verificar deploy en DigitalOcean

1. Entra a https://cloud.digitalocean.com/apps
2. Abre la app **alessia-whatsapp**
3. Pestaña **Activity** → espera **Deployed** (verde)
4. Si falla, abre **Runtime Logs** y busca `Variables de entorno faltantes` o errores de Google

### 3. Probar que el servidor vive

En el navegador o con curl:

```
https://alessia-whatsapp-jbems.ondigitalocean.app/health
```

Debe decir `"status": "ok"`.

Luego (con tu secreto si lo configuraste):

```
https://alessia-whatsapp-jbems.ondigitalocean.app/health/ready
```

Debe decir `"ready": true`. Si `"ready": false`, revisa `bloqueantes` en la respuesta.

---

## Parte B — Variables en DigitalOcean (30 min) ✋

**Apps → alessia-whatsapp → Settings → App-Level Environment Variables**

Copia/pega y completa **cada una** (las SECRET no deben ir en GitHub):

| Variable | Qué poner | Obligatorio |
|----------|-----------|-------------|
| `FLASK_ENV` | `production` | Sí |
| `ENABLE_SCHEDULER` | `1` | Sí |
| `ENABLE_LAUNCH_ACK` | `1` | Sí |
| `TOKEN_WHATSAPP` | Token permanente de Meta | Sí |
| `ID_TELEFONO` | ID del número WhatsApp Business | Sí |
| `WHATSAPP_VERIFY_TOKEN` | El mismo que en Meta webhook | Sí |
| `WHATSAPP_APP_SECRET` | App Secret de Meta Developers | Sí |
| `GEMINI_API_KEY` | API key de Google AI Studio | Sí |
| `ID_HOJA_CALCULO` | ID de tu Google Sheet | Sí |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | **Todo el JSON** en una línea | Sí en DO |
| `DATABASE_PATH` | `/data/alessia.db` | Sí |
| `WEBHOOK_CALLBACK_URL` | `https://alessia-whatsapp-jbems.ondigitalocean.app/webhook` | Sí |
| `WHATSAPP_SARA` | `523310265936` | Sí |
| `WHATSAPP_JUAN` | WhatsApp de Juan (52 + 10 dígitos) | Recomendado |
| `WHATSAPP_PATRICIA` | … | Recomendado |
| `WHATSAPP_IVAN` | … | Recomendado |
| `WHATSAPP_NUTRICION` | … | Recomendado |
| `RECEPCION_WHATSAPP` | WhatsApp de recepción para escalaciones | Recomendado |
| `WHATSAPP_TEMPLATE_24H` | Nombre plantilla aprobada (sin espacios) | Ver Parte C |
| `WHATSAPP_TEMPLATE_2H` | Nombre plantilla aprobada | Ver Parte C |
| `API_KEY_MAPS` | Google Maps API key | Opcional |
| `LINK_SESION_ONLINE` | URL Zoom/Meet por defecto | Opcional |
| `HEALTH_CONFIG_SECRET` | Una contraseña larga aleatoria | Recomendado |

### Cómo pegar `GOOGLE_SERVICE_ACCOUNT_JSON` en DigitalOcean ✋

1. Abre el archivo `agente-inpulso-bda72425fab5.json` en tu PC
2. Copia **todo** el contenido
3. En DO, crea variable `GOOGLE_SERVICE_ACCOUNT_JSON`, tipo **Encrypted**
4. Pega el JSON completo (una sola línea está bien)
5. **No** subas ese archivo a GitHub

### Volumen persistente (base de datos) ✋

Si la app **no** tiene volumen aún:

1. En la app de DO → **Settings** → **Components** → servicio **alessia**
2. **Add Volume** → nombre `alessia-data`, montar en `/data`, tamaño 1 GB
3. Confirma que `DATABASE_PATH` = `/data/alessia.db`
4. **Redeploy** la app

Sin volumen, cada deploy borra pacientes, check-ins y referidos.

---

## Parte C — Meta / WhatsApp (45–90 min) ✋

### 1. Webhook

1. https://developers.facebook.com → tu app de WhatsApp
2. **WhatsApp** → **Configuration** → **Webhook**
3. **Callback URL:** `https://alessia-whatsapp-jbems.ondigitalocean.app/webhook`
4. **Verify token:** el mismo valor que `WHATSAPP_VERIFY_TOKEN` en DO
5. Clic **Verify and save**
6. **Manage** → suscribe el campo **messages**

### 2. App Secret (firma del webhook)

1. **App settings** → **Basic** → **App secret** → Show
2. Cópialo a `WHATSAPP_APP_SECRET` en DigitalOcean
3. Redeploy si acabas de añadir la variable

### 3. Plantillas para recordatorios (muy importante) ✋

Sin plantillas, los recordatorios **24 h y 2 h** pueden no llegar si el paciente no escribió en las últimas 24 h.

1. **WhatsApp** → **Message templates** → **Create template**
2. Crea una utilidad, idioma **Spanish (MEX)**, categoría **Utility**

**Plantilla 24 h (ejemplo):**

- Nombre interno: `recordatorio_cita_24h` (anota el nombre exacto)
- Cuerpo: `Hola, te recordamos tu cita en Inpulso 43 mañana a las {{1}}. Ubicación: {{2}}.`

**Plantilla 2 h (ejemplo):**

- Nombre: `recordatorio_cita_2h`
- Cuerpo: `Tu cita en Inpulso 43 es en 2 horas ({{1}}). Mapa: {{2}}`

3. Envía a revisión Meta (puede tardar minutos u horas)
4. Cuando estén **Approved**, en DO pon:
   - `WHATSAPP_TEMPLATE_24H` = nombre exacto (ej. `recordatorio_cita_24h`)
   - `WHATSAPP_TEMPLATE_2H` = nombre exacto

> Si no alcanzan a aprobarse esta noche: el sistema igual intenta texto libre; funciona si el paciente ya chateó en las últimas 24 h.

### 4. Token permanente ✋

1. **WhatsApp** → **API Setup**
2. Genera token con permisos `whatsapp_business_messaging`
3. Pégalo en `TOKEN_WHATSAPP` en DO (si expiró el anterior, cámbialo)

---

## Parte D — Google (20 min) ✋

### 1. Compartir calendarios

Con la cuenta de servicio del JSON, comparte **Editor** en cada calendario de terapeutas (los IDs están en `config.py` → `DIRECTORIO_CALENDARIOS`).

### 2. Google Sheet

Comparte la hoja `ID_HOJA_CALCULO` con la cuenta de servicio (email que termina en `@...gserviceaccount.com`) como **Editor**.

### 3. Pestañas (una sola vez)

En tu PC, con `.env` configurado:

```powershell
cd "c:\Users\aless\OneDrive\Desktop\ALESSIA"
python scripts/inicializar_escalaciones.py
python scripts/inicializar_dashboard.py
python scripts/inicializar_catalogo.py
```

---

## Parte E — Prueba de fuego (20 min) ✋

Haz estas pruebas **después** del deploy:

| # | Acción | Resultado esperado |
|---|--------|-------------------|
| 1 | Escribe a Alessia desde tu WhatsApp personal | En segundos: "Dame un momentito…" y luego respuesta de Alessia |
| 2 | Pregunta precios de un taller | Respuesta coherente desde catálogo |
| 3 | Sara pregunta "¿Tengo citas el lunes?" | Lista de **pacientes agendados**, no horarios libres |
| 4 | Agenda una cita de prueba para mañana | Confirmación con bloque ✅ |
| 5 | Revisa Google Calendar | Descripción con `Teléfono: 52...` |
| 6 | Escribe `HABLAR CON PERSONA` | Mensaje de escalación + aviso a recepción |
| 7 | `/health/ready` en navegador | `"ready": true` |

---

## Parte F — Monitoreo esta noche (10 min) ✋

1. Crea cuenta gratis en https://uptimerobot.com
2. Monitor HTTP cada 5 min:
   - URL: `https://alessia-whatsapp-jbems.ondigitalocean.app/health/ready`
   - Alerta a tu correo si cae

3. Deja abierto **Runtime Logs** en DO la primera hora

---

## Qué hace el código nuevo (automático)

| Función | Efecto |
|---------|--------|
| `ENABLE_LAUNCH_ACK=1` | Responde al instante "Dame un momentito…" |
| Reintentos WhatsApp (3x) | Menos silencios por fallo de red |
| Rescate + reintentos en IA | Si Gemini falla, siempre llega mensaje de rescate |
| `WHATSAPP_APP_SECRET` obligatorio en prod | Webhook más seguro |
| `/health/ready` | DO puede reiniciar si la app no está lista |
| Volumen `/data` | La base de datos sobrevive redeploys |

---

## Si algo falla

| Síntoma | Qué revisar |
|---------|-------------|
| No responde nada | Logs DO, `TOKEN_WHATSAPP`, webhook suscrito a `messages` |
| Solo ack, sin respuesta IA | `GEMINI_API_KEY`, cuota Gemini en logs |
| Recordatorios no llegan | Plantillas Meta, teléfono en descripción de Calendar |
| Error al iniciar | `GOOGLE_SERVICE_ACCOUNT_JSON` mal pegado |
| 403 en webhook | `WHATSAPP_APP_SECRET` incorrecto |

---

## Mensaje para el equipo (copiar al grupo)

> Alessia ya está en producción. Escríbanle al número de Inpulso para pacientes. Terapeutas: usen su WhatsApp registrado para modo staff. Citas en Calendar deben llevar teléfono del paciente. Escalación humana: *HABLAR CON PERSONA*.

---

**Desarrollador:** Alessandro Gaytán
