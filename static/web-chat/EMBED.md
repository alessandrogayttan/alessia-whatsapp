# Pegar antes de </body> en inpulso43.com (footer PHP compartido).
#
# Opción A — script directo (recomendado):
# <script
#   src="https://alessia-whatsapp-jbems.ondigitalocean.app/static/web-chat/widget.js"
#   data-api="https://alessia-whatsapp-jbems.ondigitalocean.app"
#   defer
# ></script>
#
# Opción B — loader local (alessia-widget.js) que inyecta el remoto:
# el widget resuelve data-api aunque document.currentScript sea null.
# Opcional: window.__ALESSIA_WEB_API__ = "https://alessia-whatsapp-jbems.ondigitalocean.app";
#
# Requiere ENABLE_WEB_CHAT=1 en DigitalOcean.
