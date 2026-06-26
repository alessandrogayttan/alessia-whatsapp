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



ESPECIALIDADES_INPULSO = {

    "psicologia": (

        "Acompañamiento clínico enfocado en superar la ansiedad y equilibrar tus emociones."

    ),

    "nutricion": (

        "Planes alimenticios diseñados para adaptarse a ti y mejorar tu energía diaria."

    ),

    "talleres": (

        "Sesiones grupales creadas para impulsar tu desarrollo y crecimiento continuo. "

        "Catálogo completo en talleres.php (Biblioteca Inpulso 43)."

    ),

    "medicina": (

        "Atención integral enfocada en la prevención y el cuidado profundo de la salud."

    ),

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



# Talleres extraídos de talleres.php (objeto JS `data` en la página)

TALLERES_WEB = [

    {

        "id_web": "educacion-sexual-infantil",

        "terapeuta": "Marcela Pedraza y Magui Cárdenas",

        "nombre": "Educación en sexualidad infantil: sin tabúes y sin culpa",

        "nombre_corto_web": "Educar sin tabúes",

        "fechas": "5 de junio de 2026",

        "horario": "7:00 PM (CDMX)",

        "modalidad": "Online (Zoom)",

        "precio": "$150 MXN",

        "cupo": "1 sesión · 1 h 30 min · Grabación 1 mes",

        "temario": (

            "Actualidad en la educación sexual infantil; "

            "El peso de la charla emocional con niños; "

            "Rompiendo mitos de la educación sexual; "

            "Factores protectores: vínculos, autoestima y prevención; "

            "Herramientas prácticas para educar en casa"

        ),

        "descripcion_web": (

            "Charla online para acompañarte a educar con claridad, vínculo y prevención."

        ),

        "url_web": PAGINAS_SITIO["talleres"],

    },

    {

        "id_web": "sara-ansiedad",

        "terapeuta": "Sara Rosales",

        "nombre": "El cuerpo que aprendió a sobrevivir: la ansiedad después del control",

        "nombre_corto_web": "El cuerpo que aprendió a sobrevivir",

        "subtitulo_web": "La ansiedad detrás del control",

        "fechas": "Lunes 1 y 8 de junio (2 sesiones)",

        "horario": "6:00 PM",

        "modalidad": "Presencial / Online",

        "precio": "Online $400 MXN / Presencial $500 MXN",

        "cupo": "Cupo limitado",

        "temario": (

            "Ansiedad: ¿síntoma o problema?; "

            "Origen profundo de la ansiedad; "

            "La ansiedad en tu cuerpo y en tu mente; "

            "Errores para afrontar la realidad; "

            "Regulación emocional"

        ),

        "descripcion_web": (

            "La ansiedad no es una falla: es una respuesta que tu cuerpo aprendió para sobrevivir."

        ),

        "url_web": PAGINAS_SITIO["talleres"],

    },

    {

        "id_web": "sara-club",

        "terapeuta": "Sara Rosales",

        "nombre": "Mente en Capítulos: El Principito",

        "nombre_corto_web": "Mente en Capítulos",

        "fechas": "23 de junio de 2026",

        "horario": "5:00 PM",

        "modalidad": "Online (Zoom/YouTube + Instagram Live)",

        "precio": "Gratuito",

        "cupo": "Club de lectura",

        "temario": (

            "Cuidar la rosa sin morir en el intento; "

            "El peso no hablado de crecer; "

            "Lectura semanal El Principito con mirada psicológica"

        ),

        "descripcion_web": "Conferencia gratuita y club de lectura con Sara Rosales.",

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

        "precio": "Online $500 MXN/mes · Presencial $750 MXN/mes",

        "cupo": "Matrimonios — 3 ciclos (sanación, reconciliación, propósito)",

        "temario": (

            "Ciclo 1 (meses 1-4): Sanación de heridas e historia personal; "

            "Ciclo 2 (meses 5-8): Reconciliación y reparación; "

            "Ciclo 3 (meses 9-12): Misión, propósito y legado"

        ),

        "descripcion_web": (

            "Programa integral para fortalecer y restaurar la vida matrimonial."

        ),

        "url_web": PAGINAS_SITIO["talleres"],

    },

]



# Equipo según nosotros.php (modalidad como en la web)

EQUIPO_WEB = [

    {"nombre": "Sara Rosales", "rol": "Psicóloga", "modalidad": MODALIDAD_PRESENCIAL_ONLINE},

    {"nombre": "Juan Rosales", "rol": "Psicólogo", "modalidad": MODALIDAD_PRESENCIAL_ONLINE},

    {"nombre": "Ivan Narro", "rol": "Psicólogo", "modalidad": MODALIDAD_PRESENCIAL_ONLINE},

    {"nombre": "Patricia Velázquez", "rol": "Psicóloga", "modalidad": MODALIDAD_PRESENCIAL_ONLINE},

    {"nombre": "Marcela Pedraza", "rol": "Psicóloga", "modalidad": MODALIDAD_SOLO_ONLINE},

    {"nombre": "Magui Cárdenas", "rol": "Psicóloga", "modalidad": MODALIDAD_SOLO_ONLINE},

    {"nombre": "Rebeca Torres", "rol": "Psicóloga", "modalidad": MODALIDAD_PRESENCIAL_ONLINE},

    {"nombre": "Betty Martínez", "rol": "Tanatóloga", "modalidad": MODALIDAD_PRESENCIAL_ONLINE},

    {"nombre": "Gabriela Sánchez", "rol": "Especialista", "modalidad": MODALIDAD_PRESENCIAL_ONLINE},

]



TALLER_WEB = TALLERES_WEB[1]





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

        ("Ivan Narro", "$800", "$900", "$1,200"),

        ("Juan Rosales", "$1,000", "$1,100", "$1,300"),

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

    paginas = ", ".join(f"{k}={v}" for k, v in PAGINAS_SITIO.items())

    return (

        f"SITIO OFICIAL: {config.CLINICA_WEB_URL} (sitio multi-página PHP, NO es una sola landing). "

        f"Páginas: {paginas}. "

        f"Especialidades: Psicología, Nutrición, Talleres, Medicina. Iniciativa: {iniciativas}. "

        f"TALLERES en talleres.php (Biblioteca Inpulso): {talleres}. "

        f"Equipo completo en nosotros.php (9 especialistas)."

    )


