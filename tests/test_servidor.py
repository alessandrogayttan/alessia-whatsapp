import servidor


def test_webhook_envia_ack_antes_de_procesar(monkeypatch):
    llamadas = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(servidor, "verificar_firma_webhook", lambda body, firma: True)
    monkeypatch.setattr(servidor.storage, "reservar_mensaje_para_procesar", lambda mid: True)
    monkeypatch.setattr(servidor, "_preparar_contenido_mensaje", lambda mensaje: "hola")
    monkeypatch.setattr(servidor, "marcar_leido_y_escribiendo", lambda mid: llamadas.append(("read", mid)))
    monkeypatch.setattr(servidor, "enviar_ack_inmediato", lambda tel: llamadas.append(("ack", tel)))
    monkeypatch.setattr(
        servidor,
        "envolver_mensaje_con_contexto_paciente",
        lambda tel, contenido: f"ctx:{contenido}",
    )
    monkeypatch.setattr(
        servidor,
        "encolar_mensaje_texto",
        lambda tel, contenido: llamadas.append(("queue", tel, contenido)) or 1,
    )
    monkeypatch.setattr(servidor, "_registrar_consentimiento_si_aplica", lambda tel: None)
    monkeypatch.setattr(servidor.threading, "Thread", FakeThread)

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": "wamid.test",
                                    "from": "523326505999",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = servidor.app.test_client().post(
        "/webhook",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=test"},
    )

    assert response.status_code == 200
    assert llamadas[:3] == [
        ("read", "wamid.test"),
        ("ack", "523326505999"),
        ("queue", "523326505999", "ctx:hola"),
    ]


def test_health_config_cerrado_si_falta_secret_en_produccion(monkeypatch):
    monkeypatch.setattr(servidor.config, "IS_PRODUCTION", True)
    monkeypatch.setattr(servidor.config, "HEALTH_CONFIG_SECRET", "")

    response = servidor.app.test_client().get("/health/config")

    assert response.status_code == 404


def test_health_config_requiere_secret_correcto_en_produccion(monkeypatch):
    monkeypatch.setattr(servidor.config, "IS_PRODUCTION", True)
    monkeypatch.setattr(servidor.config, "HEALTH_CONFIG_SECRET", "super-secreto")

    client = servidor.app.test_client()
    assert client.get("/health/config").status_code == 403
    assert client.get("/health/config?secret=super-secreto").status_code == 200


def test_meta_domain_verification_meta_tag(monkeypatch):
    monkeypatch.setattr(servidor.config, "META_DOMAIN_VERIFICATION_CODE", "abc123xyz")
    response = servidor.app.test_client().get("/")
    assert response.status_code == 200
    assert b'facebook-domain-verification' in response.data
    assert b'content="abc123xyz"' in response.data


def test_meta_domain_verification_html_file(monkeypatch):
    monkeypatch.setattr(servidor.config, "META_DOMAIN_VERIFICATION_CODE", "abc123xyz")
    response = servidor.app.test_client().get("/facebook-domain-verification.html")
    assert response.status_code == 200
    assert response.data.decode() == "facebook-domain-verification: abc123xyz"
