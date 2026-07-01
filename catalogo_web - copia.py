"""

Catálogo alineado con https://inpulso43.com (páginas PHP reales).

Fuente local cuando Drive está vacío o para enriquecer respuestas de Alessia.

"""

import config



MODALIDAD_PRESENCIAL_ONLINE = "Presencial en Inpulso 43 y online"

MODALIDAD_SOLO_ONLINE = "Únicamente en línea"



PAGINAS_SITIO = {

    "inicio": f"{config.CLINICA_WEB_URL}/index.php",

    "talleres": f"{config.CLINICA_WEB_URL}/talleres.php",

    "nosotros": f"{config.CLINICA_WEB_URL}/nosotros.php",

    "blog": f"{config.CLINICA_WEB_URL}/blog.php",

    "podcast": f"{config.CLINICA_WEB_URL}/podcast.php",

    "contacto": f"{config.CLINICA_WEB_URL}/contacto.php",

}



INICIATIVAS_WEB = [

    {

        "nombre": "Amigas en la palabra",

        "descripcion": (

            "Espacios seguros de crecimiento en comunidad, respaldados por especialistas "

            "y personas en el mismo camino."

        ),

    }

]



# Catálogo vigente alineado con inpulso43.com (revisado 2026-06-25).
# Los talleres y equipo se definen más abajo en este archivo.

MENSAJE_BASE_WEB = (
    "Inpulso 43 integra psicología, nutrición, medicina familiar y espacios de desarrollo humano "
    "en un solo proceso. Acompaña procesos personales, familiares, de pareja y de bienestar físico "
    "con claridad clínica, escucha profunda, cuidado ético y herramientas aplicables a la vida diaria."
)

METODO_WEB = [
    "Escuchamos tu necesidad y qué tipo de apoyo buscas.",
    "Te orientamos para identificar si conviene psicología, nutrición, pareja, familia o taller.",
    "Inicias con el especialista adecuado y objetivos claros.",
    "Damos seguimiento con herramientas prácticas y avances sostenibles.",
]

AREAS_ACOMPANAMIENTO_WEB = [
    "Salud emocional: ansiedad, autoestima, duelo, heridas del pasado y proyecto de vida.",
    "Pareja y familia: comunicación, límites, acuerdos, crianza y reparación de vínculos.",
    "Hábitos y cuerpo: nutrición, hábitos alimenticios, bienestar físico y acompañamiento saludable.",
    "Talleres y recursos: materiales digitales, espacios grupales y formación para desarrollo humano.",
]

CONTACTO_WEB = {
    "direccion": "Av. Hidalgo 533, República, 45146 Zapopan, Jalisco",
    "telefonos": ["+52 33 1469 9772", "+52 331 230 2221"],
}

FAQ_WEB = [
    "Agendado: por WhatsApp, formulario de contacto o en Av. Hidalgo 533.",
    "Servicios: psicología clínica, nutrición, medicina familiar y talleres de desarrollo humano.",
    "Modalidades: presencial y en línea según servicio, especialista y preferencia.",
    "Seguros: no trabajan directo con aseguradoras, pero emiten factura para reembolso si la póliza lo permite.",
    "Duración: las sesiones individuales suelen durar entre 50 y 60 minutos.",
]

# Override con contenido vigente de inpulso43.com revisado el 2026-06-25.
ESPECIALIDADES_INPULSO = {
    "psicologia": (
        "Espacio clínico para entender lo que sientes, ordenar tu historia y construir recursos emocionales sostenibles."
    ),
    "nutricion": (
        "Planes realistas para mejorar energía, digestión y hábitos sin dietas restrictivas ni culpa."
    ),
    "talleres": (
        "Experiencias grupales, materiales digitales y espacios de comunidad para practicar herramientas de crecimiento personal."
    ),
    "medicina": (
        "Atención familiar enfocada en prevención, seguimiento y decisiones de salud con mirada integral."
    ),
}

TALLERES_WEB = [
    {
        "id_web": "sara-club",
        "terapeuta": "Sara Rosales",
        "nombre": "Mente en Capítulos: El Principito",
        "nombre_corto_web": "Mente en Capítulos",
        "fechas": "Todos los viernes",
        "horario": "6:00 PM",
        "modalidad": "Sesión en vivo",
        "precio": "Gratuito",
        "cupo": "Club de lectura",
        "temario": (
            "Lectura y reflexión psicológica en comunidad; "
            "sesiones en vivo todos los viernes a las 6:00 PM; "
            "El Principito con mirada psicológica"
        ),
        "descripcion_web": "Club de lectura gratuito con Sara Rosales.",
        "url_web": PAGINAS_SITIO["talleres"],
    },
    {
        "id_web": "alianza-360",
        "terapeuta": "Juan Rosales",
        "nombre": "Alianza 360",
        "nombre_corto_web": "Alianza 360",
        "fechas": "Programa 12 meses",
        "horario": "1 clase por semana (~1 h 30 min)",
        "modalidad": "Online / Presencial",
        "precio": "Consultar precio",
        "cupo": "Matrimonios — 3 ciclos (sanación, reconciliación, propósito)",
        "temario": (
            "Ciclo 1: Sanación de heridas e historia personal; "
            "Ciclo 2: Reconciliación y reparación; "
            "Ciclo 3: Misión, propósito y legado"
        ),
        "descripcion_web": "Programa integral para fortalecer y restaurar la vida matrimonial.",
        "url_web": PAGINAS_SITIO["talleres"],
    },
    {
        "id_web": "volver-a-encontrarnos",
        "terapeuta": "Juan Rosales",
        "nombre": "Volver a Encontrarnos",
        "nombre_corto_web": "Volver a Encontrarnos",
        "fechas": "Ruta digital de 21 días",
        "horario": "Material digital + sesión grupal exclusiva de 40 minutos",
        "modalidad": "Producto digital",
        "precio": "Compra por Stripe",
        "cupo": "Manual digital para parejas",
        "temario": (
            "Diagnóstico inicial de desconexión; "
            "10 microconexiones para recuperar cercanía; "
            "10 técnicas profundas de comunicación; "
            "formato de reuniones semanales; "
            "sesión grupal con Juan Rosales"
        ),
        "descripcion_web": (
            "Manual práctico de 21 días para parejas que quieren salir del divorcio silencioso, "
            "hablar sin lastimarse y recuperar conversaciones que vuelvan a acercarlos. "
            "No sustituye terapia si existe violencia, adicciones o daño emocional severo."
        ),
        "url_web": PAGINAS_SITIO["talleres"],
    },
]

EQUIPO_WEB = [
    {
        "nombre": "Sara Rosales",
        "rol": "Psicóloga",
        "modalidad": MODALIDAD_PRESENCIAL_ONLINE,
        "especialidades": "Autoestima, manejo de ansiedad, comunicación asertiva y relación familiar.",
    },
    {
        "nombre": "Juan Rosales",
        "rol": "Psicólogo",
        "modalidad": MODALIDAD_PRESENCIAL_ONLINE,
        "especialidades": "Relación de pareja, comunicación asertiva, límites y relaciones familiares.",
    },
    {
        "nombre": "Iván Navarro",
        "rol": "Psicólogo",
        "modalidad": MODALIDAD_PRESENCIAL_ONLINE,
        "especialidades": "Relaciones de pareja sanas, proyecto de vida, autoestima y ansiedad.",
    },
    {
        "nombre": "Marcela Pedraza",
        "rol": "Psicóloga",
        "modalidad": MODALIDAD_SOLO_ONLINE,
        "especialidades": "Crianza responsable, límites con hijos y acuerdos familiares.",
    },
    {
        "nombre": "Magui Cardénas",
        "rol": "Psicóloga",
        "modalidad": MODALIDAD_SOLO_ONLINE,
        "especialidades": "Autoestima familiar, acuerdos familiares y comunicación asertiva familiar.",
    },
    {
        "nombre": "Rebeca Torres",
        "rol": "Psicóloga",
        "modalidad": MODALIDAD_PRESENCIAL_ONLINE,
        "especialidades": "Adicciones, familiares de personas con adicción, nuevos hábitos y manejo emocional.",
    },
    {
        "nombre": "Betty Martínez",
        "rol": "Tanatóloga",
        "modalidad": MODALIDAD_PRESENCIAL_ONLINE,
        "especialidades": "Duelos emocionales, pérdidas, nueva realidad post duelo, niños y adultos mayores.",
    },
    {
        "nombre": "Gabriela Sánchez",
        "rol": "Nutrióloga",
        "modalidad": MODALIDAD_PRESENCIAL_ONLINE,
        "especialidades": "Hábitos alimenticios saludables, objetivos saludables y acompañamiento físico.",
    },
    {
        "nombre": "Patricia Velázquez",
        "rol": "Psicóloga",
        "modalidad": MODALIDAD_PRESENCIAL_ONLINE,
        "especialidades": "Duelos emocionales, proyecto de vida y reestructuración emocional después de la pérdida.",
    },
]

TALLER_WEB = TALLERES_WEB[0]





def _fila(

    terapeuta: str,

    tipo: str,

    nombre: str,

    precio: str,

    *,

    fechas: str = "",

    horario: str = "",

    modalidad: str = MODALIDAD_PRESENCIAL_ONLINE,

    cupo: str = "",

    temario: str = "",

    activo: str = "SI",

) -> list:

    return [

        terapeuta,

        tipo,

        nombre,

        fechas,

        horario,

        modalidad,

        precio,

        cupo,

        temario,

        activo,

    ]





def _fila_taller(t: dict) -> list:

    return _fila(

        t["terapeuta"],

        "taller",

        t["nombre"],

        t["precio"],

        fechas=t.get("fechas", ""),

        horario=t.get("horario", ""),

        modalidad=t.get("modalidad", MODALIDAD_PRESENCIAL_ONLINE),

        cupo=t.get("cupo", ""),

        temario=t.get("temario", ""),

    )





def filas_catalogo_sheet() -> list[list]:

    """Filas listas para la hoja Catalogo (columnas A–J)."""

    filas = [_fila_taller(t) for t in TALLERES_WEB]



    terapeutas_consulta = [

        ("Sara Rosales", "$800", "$900", "$1,200"),

        ("Patricia Velázquez", "$800", "$900", "$1,200"),

        ("Iván Navarro", "$800", "$900", "$1,200"),

        ("Juan Rosales", "$1,000", "$1,100", "$1,300"),

        ("Rebeca Torres", "Consultar precio", "Consultar precio", "Consultar precio"),

        ("Betty Martínez", "Consultar precio", "Consultar precio", "Consultar precio"),

    ]

    for nombre, ind, par, fam in terapeutas_consulta:

        filas.extend(

            [

                _fila(nombre, "servicio", "Terapia individual", f"{ind} MXN"),

                _fila(nombre, "servicio", "Terapia de pareja", f"{par} MXN"),

                _fila(nombre, "servicio", "Terapia familiar", f"{fam} MXN"),

            ]

        )



    filas.extend(

        [

            _fila(

                "Marcela Pedraza",

                "servicio",

                "Terapia individual",

                "Consultar precio",

                modalidad=MODALIDAD_SOLO_ONLINE,

            ),

            _fila(

                "Magui Cárdenas",

                "servicio",

                "Terapia individual",

                "Consultar precio",

                modalidad=MODALIDAD_SOLO_ONLINE,

            ),

            _fila("Nutrición", "servicio", "Consulta nutricional", "$450 MXN"),

            _fila(

                "Mentoras",

                "servicio",

                "Sesión con mentoras",

                "Consultar precio",

                modalidad=MODALIDAD_SOLO_ONLINE,

            ),

            _fila("Inpulso 43", "servicio", "Medicina familiar", "Consultar disponibilidad"),

        ]

    )

    return filas





def _enriquecer_fila_dict(fila: dict) -> dict:

    fila = dict(fila)

    fila["url_web"] = PAGINAS_SITIO.get("talleres" if fila.get("tipo") == "taller" else "inicio")



    if fila.get("tipo") == "taller":

        for t in TALLERES_WEB:

            if t["nombre"].lower() in fila.get("nombre", "").lower() or fila.get(

                "nombre", ""

            ).lower() in t["nombre"].lower():

                fila.update(

                    {

                        "descripcion_web": t.get("descripcion_web", ""),

                        "nombre_corto_web": t.get("nombre_corto_web", ""),

                        "subtitulo_web": t.get("subtitulo_web", ""),

                        "id_web": t.get("id_web", ""),

                        "url_web": t.get("url_web", PAGINAS_SITIO["talleres"]),

                    }

                )

                break

    elif fila.get("tipo") == "servicio":

        if "nutric" in fila.get("nombre", "").lower():

            fila["descripcion_web"] = ESPECIALIDADES_INPULSO["nutricion"]

        elif "medicina" in fila.get("nombre", "").lower():

            fila["descripcion_web"] = ESPECIALIDADES_INPULSO["medicina"]

        elif "mentora" in fila.get("terapeuta", "").lower():

            fila["descripcion_web"] = "Sesiones únicamente en línea."

        else:

            fila["descripcion_web"] = ESPECIALIDADES_INPULSO["psicologia"]

    return fila





def filas_catalogo_dict() -> list[dict]:

    keys = [

        "terapeuta",

        "tipo",

        "nombre",

        "fechas",

        "horario",

        "modalidad",

        "precio",

        "cupo",

        "temario",

        "activo",

    ]

    return [

        _enriquecer_fila_dict(

            {keys[i]: (row[i] if i < len(row) else "") for i in range(len(keys))}

        )

        for row in filas_catalogo_sheet()

    ]





def contexto_web_para_ia() -> str:

    iniciativas = " | ".join(i["nombre"] for i in INICIATIVAS_WEB)

    talleres = "; ".join(t["nombre_corto_web"] for t in TALLERES_WEB)

    equipo = "; ".join(
        f"{e['nombre']} ({e['rol']}, {e['modalidad']}: {e.get('especialidades', '')})"
        for e in EQUIPO_WEB
    )

    paginas = ", ".join(f"{k}={v}" for k, v in PAGINAS_SITIO.items())

    return (

        f"SITIO OFICIAL: {config.CLINICA_WEB_URL} (sitio multi-página PHP, NO es una sola landing). "

        f"Páginas: {paginas}. "

        f"Mensaje base: {MENSAJE_BASE_WEB} "

        f"Especialidades: Psicología, Nutrición, Talleres, Medicina. Iniciativa: {iniciativas}. "

        f"TALLERES en talleres.php (Biblioteca Inpulso): {talleres}. "

        f"Equipo completo en nosotros.php: {equipo}. "

        f"Contacto: {CONTACTO_WEB['direccion']}; teléfonos directos {', '.join(CONTACTO_WEB['telefonos'])}. "

        f"Preguntas frecuentes: {' | '.join(FAQ_WEB)}"

    )


