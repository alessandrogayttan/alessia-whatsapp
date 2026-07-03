/* Alessia — widget chat web Inpulso 43 */
(function () {
  "use strict";

  var script = document.currentScript;
  var apiBase = (script && script.getAttribute("data-api")) || "";
  if (!apiBase) {
    var src = (script && script.src) || "";
    apiBase = src.replace(/\/static\/web-chat\/widget\.js.*$/, "");
  }

  var COLORS = {
    azul: "#2563A8",
    azulOscuro: "#1E3A5F",
    rojo: "#C94C4C",
    fondo: "#F4F7FB",
    blanco: "#FFFFFF",
    texto: "#2D3748",
  };

  var sessionId = null;
  var config = { whatsapp_url: "", aviso_privacidad_url: "" };
  var busy = false;

  function storageKey() {
    return "alessia_web_session";
  }

  function loadSession() {
    try {
      return localStorage.getItem(storageKey());
    } catch (e) {
      return null;
    }
  }

  function saveSession(id) {
    try {
      localStorage.setItem(storageKey(), id);
    } catch (e) {}
  }

  function formatReply(text) {
    var escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return escaped.replace(/\*([^*]+)\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>");
  }

  function injectStyles() {
    if (document.getElementById("alessia-web-chat-styles")) return;
    var style = document.createElement("style");
    style.id = "alessia-web-chat-styles";
    style.textContent =
      "#alessia-launcher{position:fixed;bottom:24px;right:24px;z-index:99998;width:60px;height:60px;border-radius:50%;border:none;background:" +
      COLORS.azul +
      ";color:#fff;font-size:28px;cursor:pointer;box-shadow:0 4px 20px rgba(37,99,168,.45);transition:transform .2s}" +
      "#alessia-launcher:hover{transform:scale(1.05)}" +
      "#alessia-panel{position:fixed;bottom:96px;right:24px;z-index:99999;width:min(380px,calc(100vw - 32px));height:min(520px,calc(100vh - 120px));background:" +
      COLORS.blanco +
      ";border-radius:16px;box-shadow:0 8px 40px rgba(30,58,95,.2);display:none;flex-direction:column;overflow:hidden;font-family:Segoe UI,system-ui,sans-serif}" +
      "#alessia-panel.open{display:flex}" +
      "#alessia-header{background:linear-gradient(135deg," +
      COLORS.azul +
      "," +
      COLORS.azulOscuro +
      ");color:#fff;padding:16px 18px;border-bottom:3px solid " +
      COLORS.rojo +
      "}" +
      "#alessia-header h3{margin:0;font-size:17px;font-weight:600}" +
      "#alessia-header p{margin:4px 0 0;font-size:12px;opacity:.9}" +
      "#alessia-messages{flex:1;overflow-y:auto;padding:14px;background:" +
      COLORS.fondo +
      "}" +
      ".alessia-msg{max-width:88%;margin-bottom:10px;padding:10px 12px;border-radius:12px;font-size:14px;line-height:1.45;color:" +
      COLORS.texto +
      "}" +
      ".alessia-msg.bot{background:#fff;border:1px solid #e2e8f0;border-bottom-left-radius:4px}" +
      ".alessia-msg.user{background:" +
      COLORS.azul +
      ";color:#fff;margin-left:auto;border-bottom-right-radius:4px}" +
      ".alessia-msg.typing{opacity:.7;font-style:italic}" +
      "#alessia-input-row{display:flex;gap:8px;padding:12px;border-top:1px solid #e2e8f0;background:#fff}" +
      "#alessia-input{flex:1;border:1px solid #cbd5e1;border-radius:20px;padding:10px 14px;font-size:14px;outline:none}" +
      "#alessia-input:focus{border-color:" +
      COLORS.azul +
      "}" +
      "#alessia-send{border:none;background:" +
      COLORS.azul +
      ";color:#fff;border-radius:20px;padding:10px 16px;font-size:14px;cursor:pointer}" +
      "#alessia-send:disabled{opacity:.5;cursor:not-allowed}" +
      "#alessia-footer{font-size:10px;text-align:center;padding:6px;color:#64748b;background:#fff}" +
      "#alessia-footer a{color:" +
      COLORS.azul +
      "}";
    document.head.appendChild(style);
  }

  function el(tag, attrs, html) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        node.setAttribute(k, attrs[k]);
      });
    }
    if (html !== undefined) node.innerHTML = html;
    return node;
  }

  function appendMessage(text, who) {
    var box = document.getElementById("alessia-messages");
    if (!box) return;
    var div = el("div", { class: "alessia-msg " + who });
    if (who === "bot") div.innerHTML = formatReply(text);
    else div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function api(path, options) {
    return fetch(apiBase + path, options).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  function ensureSession() {
    if (sessionId) return Promise.resolve(sessionId);
    var saved = loadSession();
    if (saved) {
      sessionId = saved;
      return Promise.resolve(sessionId);
    }
    return api("/api/web-chat/session", { method: "POST" }).then(function (data) {
      sessionId = data.session_id;
      saveSession(sessionId);
      return sessionId;
    });
  }

  function sendMessage(text) {
    if (busy || !text.trim()) return;
    busy = true;
    appendMessage(text, "user");
    var input = document.getElementById("alessia-input");
    var btn = document.getElementById("alessia-send");
    if (input) input.value = "";
    if (btn) btn.disabled = true;
    appendMessage("Escribiendo…", "bot typing");

    ensureSession()
      .then(function (sid) {
        return api("/api/web-chat/message", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sid, message: text }),
        });
      })
      .then(function (data) {
        var typing = document.querySelector(".alessia-msg.typing");
        if (typing) typing.remove();
        appendMessage(data.reply || "…", "bot");
      })
      .catch(function () {
        var typing = document.querySelector(".alessia-msg.typing");
        if (typing) typing.remove();
        appendMessage(
          "No pude conectar en este momento. Si prefieres, escríbenos por WhatsApp 💙",
          "bot"
        );
      })
      .finally(function () {
        busy = false;
        if (btn) btn.disabled = false;
        if (input) input.focus();
      });
  }

  function buildUI() {
    injectStyles();

    var launcher = el("button", { id: "alessia-launcher", type: "button", "aria-label": "Abrir chat" }, "💬");
    var panel = el("div", { id: "alessia-panel" });
    panel.appendChild(
      el(
        "div",
        { id: "alessia-header" },
        "<h3>Alessia · Inpulso 43</h3><p>¿En qué te puedo acompañar hoy?</p>"
      )
    );
    panel.appendChild(el("div", { id: "alessia-messages" }));

    var row = el("div", { id: "alessia-input-row" });
    var input = el("input", {
      id: "alessia-input",
      type: "text",
      placeholder: "Escribe tu mensaje…",
      maxlength: "4000",
      autocomplete: "off",
    });
    var send = el("button", { id: "alessia-send", type: "button" }, "Enviar");
    row.appendChild(input);
    row.appendChild(send);
    panel.appendChild(row);

    var footer = el("div", { id: "alessia-footer" });
    panel.appendChild(footer);

    document.body.appendChild(launcher);
    document.body.appendChild(panel);

    launcher.addEventListener("click", function () {
      panel.classList.toggle("open");
      if (panel.classList.contains("open")) {
        input.focus();
        if (!document.querySelector(".alessia-msg")) {
          appendMessage(
            "Hola, soy Alessia de Inpulso 43 😊 Estoy aquí para ayudarte con talleres, citas, precios o lo que necesites.",
            "bot"
          );
        }
      }
    });

    function submit() {
      sendMessage(input.value);
    }
    send.addEventListener("click", submit);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") submit();
    });

    api("/api/web-chat/config")
      .then(function (cfg) {
        config = cfg;
        var links = [];
        if (cfg.whatsapp_url) {
          links.push(
            '<a href="' +
              cfg.whatsapp_url +
              '" target="_blank" rel="noopener">WhatsApp</a>'
          );
        }
        if (cfg.aviso_privacidad_url) {
          links.push(
            '<a href="' +
              cfg.aviso_privacidad_url +
              '" target="_blank" rel="noopener">Privacidad</a>'
          );
        }
        footer.innerHTML = links.join(" · ");
      })
      .catch(function () {});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildUI);
  } else {
    buildUI();
  }
})();
