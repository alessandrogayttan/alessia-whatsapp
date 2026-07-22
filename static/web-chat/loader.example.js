/* Copiar a inpulso43.com como alessia-widget.js (opcional; el widget remoto ya se arregla solo). */
(function () {
  "use strict";

  var loader = document.currentScript;
  var apiBase = (loader && loader.getAttribute("data-api")) || "";
  if (!apiBase) return;
  apiBase = apiBase.replace(/\/$/, "");
  window.__ALESSIA_WEB_API__ = apiBase;

  function loadWidget() {
    if (document.getElementById("alessia-web-widget-loader")) return;
    var remote = document.createElement("script");
    remote.id = "alessia-web-widget-loader";
    remote.src = apiBase + "/static/web-chat/widget.js";
    remote.setAttribute("data-api", apiBase);
    document.body.appendChild(remote);
  }

  function styleLauncher(launcher) {
    if (!launcher || launcher.dataset.inpulsoStyled === "1") return;
    launcher.dataset.inpulsoStyled = "1";
    launcher.classList.add("inpulso-alessia-launcher");
    launcher.setAttribute("aria-label", "Chatear con Alessia");
    launcher.innerHTML =
      '<span class="inpulso-alessia-launcher__icon" aria-hidden="true">💬</span>' +
      '<span class="inpulso-alessia-launcher__label">Alessia</span>';
  }

  function patchWidget() {
    var launcher = document.getElementById("alessia-launcher");
    styleLauncher(launcher);
    var panel = document.getElementById("alessia-panel");
    if (launcher && panel) {
      launcher.classList.toggle("is-open", panel.classList.contains("open"));
    }
  }

  function init() {
    loadWidget();
    patchWidget();
    var observer = new MutationObserver(patchWidget);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
