
        var pendingWorkshopId = null;
        var animType = null;
        var isAnimating = false;
        var vinylSpinTween = null;

        var data = {
            'educacion-sexual-infantil': {
                title: 'Educación en sexualidad infantil: sin tabúes y sin culpa',
                coverImage: 'taller-educacion-sexual-infantil.png',
                coverImageClass: 'is-flyer',
                instructor: 'Por Marcela Pedraza y Magui Cárdenas',
                desc: '<p><strong>Herramientas prácticas de educación en sexualidad infantil desde casa.</strong></p><p>Una charla para acompañarte a educar con claridad, vínculo y prevención — sin tabúes y sin culpa.</p><p><strong>Temario:</strong></p><ul class="desc-list"><li>Actualidad en la educación sexual infantil</li><li>El peso de la charla emocional con niños</li><li>Rompiendo mitos de la educación sexual</li><li>Factores protectores: vínculos, autoestima y prevención</li><li>Herramientas prácticas para educar en casa</li></ul><p>📲 No te quedes fuera: inscríbete hoy y recibe el enlace de Zoom.</p>',
                meta: {
                    inversión: '$150 MXN',
                    fecha: '5 de junio de 2026',
                    hora: '7:00 PM (CDMX)',
                    duración: '1 sesión · 1 h 30 min',
                    modalidad: 'Online (Zoom)',
                    grabación: 'Acceso 1 mes'
                },
                link: 'https://wa.me/523314699772?text=Hola%2C%20me%20interesa%20inscribirme%20a%20la%20charla%20de%20Educaci%C3%B3n%20en%20Sexualidad%20Infantil%20(5%20de%20junio%2C%207%20pm).',
                btnText: 'Inscribirme a la charla'
            },
            'sara-ansiedad': {
                title: 'El cuerpo que aprendió a sobrevivir',
                coverImage: 'Taller de psicología.jpg',
                coverImageFallback: 'https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?q=80&w=1000',
                instructor: 'Por Sara Rosales',
                spreadTeaser: 'La ansiedad no es una falla: es una respuesta que tu cuerpo aprendió para sobrevivir.',
                desc: '<p><strong>La ansiedad detrás del control.</strong></p><p>La ansiedad no es una falla: es una respuesta que tu cuerpo aprendió para sobrevivir. En este taller abordaremos su origen profundo, cómo vive en tu cuerpo y en tu mente, y herramientas reales de regulación emocional basadas en la psicología clínica.</p><p><strong>Temario:</strong></p><ul class="desc-list"><li>Ansiedad: ¿síntoma o problema?</li><li>Origen profundo de la ansiedad</li><li>La ansiedad en tu cuerpo y en tu mente</li><li>Errores para afrontar la realidad</li><li>Regulación emocional</li></ul>',
                meta: { inversión: '$400 MXN', fecha: 'Lun 1 Junio', hora: '6:00 PM', modalidad: 'Presencial / Online' },
                link: 'https://wa.link/orldbq',
                btnText: 'Inscribirme al Taller'
            },
            'sara-club': {
                title: 'Mente en Capítulos: El Principito',
                coverImage: 'club-libros.jpg',
                instructor: 'Por Sara Rosales',
                spreadTeaser: 'Cuidar la rosa sin morir en el intento: el peso no hablado de crecer.',
                desc: '<p><strong>Cuidar la rosa sin morir en el intento: El peso no hablado de crecer.</strong></p><p>Analizaremos "El Principito" bajo una mirada psicológica profunda. Incluye conferencia gratuita el 23 de junio a las 5pm vía Zoom/YouTube, y lectura semanal por Instagram Live.</p>',
                meta: { inversión: 'Gratuito', fecha: '23 Junio', hora: '5:00 PM', modalidad: 'Online' },
                link: 'https://chat.whatsapp.com/F0TvLl10LUaEGhUTQgxKgs',
                btnText: 'Unirme al Club de Lectura'
            },
            'alianza-360': {
                title: 'Alianza 360',
                instructor: 'Por Juan Rosales',
                desc: `
                <div style="max-height: 50vh; overflow-y: auto; padding-right: 15px;">
                    <p>Un programa integral para el fortalecimiento y la restauración de la vida matrimonial estructurado en 3 ciclos fundamentales:</p>
                    <h4 style="color:var(--inpulso-azul); margin-top:20px;">CICLO 1 (Meses 1–4): Sanación de heridas de infancia / historia personal en el matrimonio</h4>
                    <ul class="desc-list">
                        <li><strong>Mes 1 — Mapa de heridas y "gatillos":</strong> Oración #1: Jesús sana lo escondido (Salmo 139: "Tú me conoces"). Oración #2: Milagros de sanación: la hemorroísa (fe + dignidad). Reunión general: "Mi herida no es mi identidad: cómo se activa en pareja". Crecer: Apego + necesidades emocionales (lo que de verdad estamos pidiendo).</li>
                        <li><strong>Mes 2 — Apego, seguridad y niño interior:</strong> Oración #1: El Buen Pastor (seguridad y cuidado). Oración #2: Jesús y el leproso (ternura + acercamiento sin miedo). Reunión general: "Cómo amar cuando mi sistema está en alarma" (co-regulación). Crecer: Neurociencia del conflicto: amígdala, defensa, reparación en 90s.</li>
                        <li><strong>Mes 3 — Límites, roles y familia de origen:</strong> Oración #1: "Dejarán padre y madre…" (unidad, orden, prioridad). Oración #2: Jesús en casa de Marta y María (prioridades sin culpa). Reunión general: "Familia extensa: honra + límites + acuerdos". Crecer: Comunicación que no dispara heridas (lenguaje, tono, timing).</li>
                        <li><strong>Mes 4 — Perdón, duelo y nueva narrativa:</strong> Oración #1: El hijo pródigo (misericordia y regreso). Oración #2: "Venid a mí los cansados…" (descanso interior). Reunión general: "Cerrar ciclos: duelo por lo que no fue + elección por lo que sí será". Crecer: Reescritura de historia personal (narrativa + actos de reparación).</li>
                    </ul>
                    <h4 style="color:var(--inpulso-azul); margin-top:20px;">CICLO 2 (Meses 5–8): Reconciliación y reparación</h4>
                    <ul class="desc-list">
                        <li><strong>Mes 5 — Comunicación con honor:</strong> Oración y tema #1: "Que tu sí sea sí" (verdad + claridad). Oración y tema #2: "La lengua tiene poder" (palabras que sanan vs hieren). Reunión general: "Conversaciones difíciles sin destruirnos". Crecer: Herramientas: escucha activa, validación, pregunta correcta.</li>
                        <li><strong>Mes 6 — Conflicto y reparación:</strong> Oración y tema #1: "No se ponga el sol sobre su enojo" (reparación rápida). Oración y tema #2: Dinámica: oración de perdón guiada + bendición mutua. Reunión general: "El ciclo de pelea: cómo lo cortamos en tiempo real". Crecer: Protocolo de reparación en 4 pasos (script + práctica).</li>
                        <li><strong>Mes 7 — Intimidad emocional y sexualidad integrada:</strong> Oración y tema #1: Cantar de los Cantares (dignidad del amor conyugal). Oración y tema #2: "Amor que cuida" (ternura, paciencia, respeto). Reunión general: "Deseo, seguridad y conexión: intimidad que no se negocia con culpa". Crecer: Intimidad emocional (microconexiones, citas, erotismo saludable).</li>
                        <li><strong>Mes 8 — Pactos y hábitos de alto rendimiento:</strong> Oración y tema #1: Construir sobre roca (hábitos, estructura, constancia). Oración y tema #2: Renovación de promesas (pequeña liturgia/acto simbólico). Reunión general: "Acuerdos claros: tiempo, dinero, pantallas, familia, sexualidad". Crecer: KPI del matrimonio: hábitos medibles (check-in, cita, oración, reparación).</li>
                    </ul>
                    <h4 style="color:var(--inpulso-azul); margin-top:20px;">CICLO 3 (Meses 9–12): Misión, propósito y legado</h4>
                    <ul class="desc-list">
                        <li><strong>Mes 9 — Visión y propósito:</strong> Oración y tema #1: "Busquen primero el Reino" (prioridades). Oración y tema #2: Discernimiento en pareja (qué construir este año). Reunión general: "Regla de vida del hogar: valores, cultura y orden". Crecer: Planeación familiar 3–5 años (visión por áreas).</li>
                        <li><strong>Mes 10 — Finanzas con paz (mayordomía):</strong> Oración y tema #1: Parábola de los talentos (administración y fruto). Oración y tema #2: Generosidad y confianza (miedo vs fe). Reunión general: "Dinero sin pleitos: presupuesto, deudas, metas, transparencia". Crecer: Sistema simple de finanzas en pareja (reunión mensual + tablero).</li>
                        <li><strong>Mes 11 — Crianza, casa y familia extensa:</strong> Oración y tema #1: "Mi casa servirá…" (liderazgo espiritual del hogar). Oración y tema #2: Bendición a los hijos / sanación del ambiente del hogar. Reunión general: "Equipo parental: acuerdos, disciplina, unidad y ejemplo". Crecer: Límites con amor: estructura familiar que da paz.</li>
                        <li><strong>Mes 12 — Legado y renovación:</strong> Oración y tema #1: Gratitud: memorial de lo que Dios hizo este año. Oración y tema #2: Renovación de votos / consagración del hogar (según su estilo). Reunión general: "Cierre del año: testimonios, celebración, graduación". Crecer: Plan del siguiente año (metas + hábitos + pacto de 90 días).</li>
                    </ul>
                </div>`,
                meta: {
                    'inversión online': '$500 MXN / mes',
                    'inversión presencial': '$750 MXN / mes',
                    frecuencia: '1 clase por semana',
                    'duración por clase': '~1 h 30 min',
                    duración: '12 meses',
                    modalidad: 'Online / Presencial'
                },
                link: 'contacto.php',
                btnText: 'Pedir Cotización e Información'
            }
        };

        function applyCoverImage(el, info) {
            if (!info.coverImage) {
                el.style.display = 'none';
                return;
            }
            el.style.display = 'block';
            el.style.backgroundImage = "url('" + info.coverImage + "')";
            var probe = new Image();
            probe.onerror = function () {
                if (info.coverImageFallback) {
                    el.style.backgroundImage = "url('" + info.coverImageFallback + "')";
                }
            };
            probe.src = info.coverImage;
        }

        function buildModalHtml(info) {
            var btnAction = 'href="' + info.link + '" target="' + (info.link === 'contacto.php' ? '_self' : '_blank') + '"';
            var metaHtml = Object.keys(info.meta).map(function (k) {
                return '<div class="meta-row"><span>' + k + '</span><span>' + info.meta[k] + '</span></div>';
            }).join('');
            var imgHtml = '';
            if (info.coverImage) {
                var fallback = info.coverImageFallback || '';
                var coverClass = 'modal-cover-img' + (info.coverImageClass ? ' ' + info.coverImageClass : '');
                imgHtml = '<img class="' + coverClass + '" src="' + info.coverImage + '" alt="' + info.title + '" loading="lazy"' +
                    (fallback ? ' onerror="this.onerror=null;this.src=\'' + fallback + '\';"' : '') + '>';
            }
            return '<div class="modal-text">' + imgHtml + '<h2>' + info.title + '</h2><span class="instructor">' + info.instructor + '</span>' + info.desc +
                '<div class="modal-meta">' + metaHtml + '</div>' +
                '<a ' + btnAction + ' class="btn-modal-action">' + info.btnText + '</a></div>';
        }

        function showModal(id) {
            document.getElementById('modalBody').innerHTML = buildModalHtml(data[id]);
            document.getElementById('workModal').classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        function playBookOpen(id, callback) {
            var info = data[id];
            var stage = document.getElementById('bookStage');
            var coverWrap = document.getElementById('bookCoverWrap');
            var assembly = document.getElementById('bookAssembly');
            var spread = document.getElementById('bookSpread');
            var coverPhoto = document.getElementById('bookCoverPhoto');

            document.getElementById('bookCoverTitle').textContent = info.title;
            document.getElementById('bookSpreadTeaser').textContent = info.spreadTeaser || 'Un taller para abrir nuevas páginas en tu historia.';
            applyCoverImage(coverPhoto, info);

            coverWrap.style.transform = 'rotateY(0deg)';
            spread.style.opacity = '0';
            assembly.style.transform = 'rotateX(18deg) rotateY(-18deg) scale(0.88)';

            stage.classList.add('active');
            document.body.style.overflow = 'hidden';
            isAnimating = true;
            animType = 'book';
            pendingWorkshopId = id;
            gsap.set(stage, { clearProps: 'opacity' });

            var tl = gsap.timeline({
                onComplete: function () {
                    stage.classList.remove('active');
                    gsap.set(stage, { clearProps: 'opacity' });
                    finishAnimation(callback);
                }
            });

            tl.fromTo(stage, { opacity: 0 }, { opacity: 1, duration: 0.35, ease: 'power2.out' })
              .to(assembly, { rotateX: 8, rotateY: -12, scale: 1, duration: 1.1, ease: 'power3.out' }, '-=0.1')
              .to(coverWrap, { rotateY: -168, duration: 1.35, ease: 'power2.inOut' }, '+=0.25')
              .to(spread, { opacity: 1, duration: 0.5, ease: 'power2.out' }, '-=0.6')
              .to(assembly, { rotateY: -6, duration: 0.6, ease: 'power1.inOut' }, '-=0.3')
              .to({}, { duration: 0.7 })
              .to(stage, { opacity: 0, duration: 0.4, ease: 'power2.in' });
        }

        function playVinylOpen(id, callback) {
            var info = data[id];
            var stage = document.getElementById('vinylStage');
            var unit = document.getElementById('turntableUnit');
            var tonearm = document.getElementById('ttTonearm');
            var needle = document.getElementById('ttNeedle');
            var vinyl = document.getElementById('ttVinyl');
            var vinylShine = document.getElementById('ttVinylShine');
            var glow = document.getElementById('vinylGlow');
            var power = document.getElementById('ttPower');

            document.getElementById('vinylTitle').textContent = info.title;
            var vinylAuthor = document.getElementById('vinylAuthor');
            if (vinylAuthor) vinylAuthor.textContent = (info.instructor || '').replace(/^Por\s+/, '');

            gsap.set(unit, { y: 100, opacity: 0, scale: 0.88, rotateX: 12 });
            gsap.set(tonearm, { rotation: -38 });
            gsap.set(needle, { rotation: 18 });
            gsap.set(vinyl, { rotation: 0, y: -90, scale: 1.05, opacity: 0 });
            gsap.set(vinylShine, { rotation: 0 });
            gsap.set(glow, { opacity: 0, scale: 0.7 });
            gsap.set(power, { boxShadow: 'none' });
            if (vinylSpinTween) vinylSpinTween.kill();

            stage.classList.add('active');
            document.body.style.overflow = 'hidden';
            isAnimating = true;
            animType = 'vinyl';
            pendingWorkshopId = id;
            gsap.set(stage, { clearProps: 'opacity' });

            var tl = gsap.timeline({
                onComplete: function () {
                    if (vinylSpinTween) vinylSpinTween.kill();
                    stage.classList.remove('active');
                    gsap.set(stage, { clearProps: 'opacity' });
                    finishAnimation(callback);
                }
            });

            tl.fromTo(stage, { opacity: 0 }, { opacity: 1, duration: 0.55, ease: 'power2.out' })
              .to(unit, { y: 0, opacity: 1, scale: 1, rotateX: 0, duration: 1.1, ease: 'power3.out' }, '-=0.2')
              .to(vinyl, { opacity: 1, duration: 0.4 }, '-=0.5')
              .to(vinyl, { y: 0, scale: 1, duration: 0.65, ease: 'bounce.out' }, '-=0.1')
              .to(power, { boxShadow: '0 0 14px rgba(80,200,120,0.9)', duration: 0.25 }, '-=0.3')
              .to(tonearm, { rotation: -5, duration: 1.2, ease: 'power2.inOut' }, '+=0.15')
              .to(needle, { rotation: 8, duration: 0.35, ease: 'power2.in' }, '-=0.2')
              .to(tonearm, { rotation: 16, duration: 0.55, ease: 'power1.inOut' })
              .to(needle, { rotation: 0, duration: 0.4, ease: 'power2.out' }, '-=0.25')
              .add(function () {
                  vinylSpinTween = gsap.timeline({ repeat: -1 })
                      .to(vinyl, { rotation: 360, duration: 1.6, ease: 'none' }, 0)
                      .to(vinylShine, { rotation: 360, duration: 1.6, ease: 'none' }, 0);
              }, '-=0.15')
              .to(glow, { opacity: 1, scale: 1, duration: 0.7, ease: 'power2.out' }, '-=0.4')
              .to(tonearm, { rotation: 15.5, duration: 0.15, repeat: 5, yoyo: true, ease: 'sine.inOut' }, '-=0.3')
              .to({}, { duration: 1.4 })
              .to(stage, { opacity: 0, duration: 0.45, ease: 'power2.in' });
        }

        function finishAnimation(callback) {
            isAnimating = false;
            animType = null;
            document.getElementById('bookStage').classList.remove('active');
            document.getElementById('vinylStage').classList.remove('active');
            gsap.set('#bookStage, #vinylStage', { clearProps: 'opacity' });
            gsap.set('#bookCoverWrap', { rotateY: 0, clearProps: 'transform' });
            gsap.set('#bookSpread', { opacity: 0 });
            gsap.set('#bookAssembly', { rotateX: 8, rotateY: -12, scale: 1, clearProps: 'transform' });
            gsap.set('#turntableUnit', { y: 0, opacity: 1, scale: 1, rotateX: 0, clearProps: 'transform' });
            gsap.set('#ttVinyl', { rotation: 0, y: 0, scale: 1, opacity: 1, clearProps: 'transform' });
            gsap.set('#ttVinylShine', { rotation: 0 });
            gsap.set('#ttTonearm', { rotation: -38, clearProps: 'transform' });
            gsap.set('#ttNeedle', { rotation: 18 });
            if (vinylSpinTween) { vinylSpinTween.kill(); vinylSpinTween = null; }
            pendingWorkshopId = null;
            if (callback) callback();
        }

        window.openWorkshop = function (id, type) {
            if (isAnimating) return;
            if (!data[id]) return;
            try {
                if (type === true || type === 'book') {
                    playBookOpen(id, function () { showModal(id); });
                } else if (type === 'vinyl') {
                    playVinylOpen(id, function () { showModal(id); });
                } else {
                    showModal(id);
                }
            } catch (err) {
                console.error(err);
                isAnimating = false;
                showModal(id);
            }
        };

        window.skipAnimation = function () {
            if (!pendingWorkshopId || !isAnimating) return;
            gsap.killTweensOf('#bookStage, #bookAssembly, #bookCoverWrap, #bookSpread, #vinylStage, #turntableUnit, #ttTonearm, #ttNeedle, #ttVinyl, #ttVinylShine, #vinylGlow, #ttPower');
            if (vinylSpinTween) { vinylSpinTween.kill(); vinylSpinTween = null; }
            var id = pendingWorkshopId;
            finishAnimation(function () { showModal(id); });
        };

        window.closeWorkshop = function () {
            document.getElementById('workModal').classList.remove('active');
            document.body.style.overflow = '';
        };

        document.getElementById('workModal').addEventListener('click', function (e) {
            if (e.target === this) closeWorkshop();
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                if (isAnimating) skipAnimation();
                else if (document.getElementById('workModal').classList.contains('active')) closeWorkshop();
            }
        });

        document.querySelector('.store-grid').addEventListener('click', function (e) {
            var card = e.target.closest('[data-workshop]');
            if (!card || isAnimating) return;
            var id = card.getAttribute('data-workshop');
            var anim = card.getAttribute('data-anim');
            if (anim === 'book') openWorkshop(id, true);
            else if (anim === 'vinyl') openWorkshop(id, 'vinyl');
            else openWorkshop(id, false);
        });

        function scrollToStore(targetId) {
            var el = document.getElementById('storeSection');
            if (targetId) {
                var card = document.querySelector('[data-workshop="' + targetId + '"]');
                if (card) el = card;
            }
            if (!el) return;
            if (window.lenis) {
                window.lenis.scrollTo(el, { offset: targetId ? -80 : -20, duration: 1.35 });
            } else {
                el.scrollIntoView({ behavior: 'smooth', block: targetId ? 'center' : 'start' });
            }
        }

        function initCinemaHero() {
            if (typeof ScrollTrigger !== 'undefined') gsap.registerPlugin(ScrollTrigger);

            var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            var hero = document.getElementById('heroLibrary');
            var bg = document.getElementById('tchBg');
            var parallax = document.getElementById('tchParallax');
            var content = document.getElementById('tchContent');
            var heroActive = true;
            var floatTween = null;
            var isCoarsePointer = window.matchMedia('(pointer: coarse)').matches;
            var isNarrow = window.matchMedia('(max-width: 1024px)').matches;
            var enableFloatMotion = !isCoarsePointer && !isNarrow;

            document.querySelectorAll('.tch-chapter[data-workshop]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    scrollToStore(btn.getAttribute('data-workshop'));
                });
            });

            if ('IntersectionObserver' in window && hero) {
                new IntersectionObserver(function (entries) {
                    heroActive = entries[0].isIntersecting;
                    if (floatTween) floatTween.paused(!heroActive);
                }, { threshold: 0.05 }).observe(hero);
            }

            if (!reducedMotion && typeof gsap !== 'undefined') {
                gsap.set(['#tchLetterboxTop', '#tchLetterboxBottom'], { scaleY: 1.15 });
                gsap.set('#tchContent', { opacity: 0, y: 36 });
                gsap.set('.tch-float', { opacity: 0, scale: 0.92 });

                gsap.timeline({ defaults: { ease: 'power3.out' } })
                    .to('#tchLetterboxTop', { scaleY: 1, duration: 0.95, ease: 'power4.inOut' })
                    .to('#tchLetterboxBottom', { scaleY: 1, duration: 0.95, ease: 'power4.inOut' }, 0)
                    .from('.tch-aurora', { opacity: 0, scale: 0.92, duration: 1.1, stagger: 0.08 }, 0.08)
                    .from('#tchBadge', { y: 16, opacity: 0, duration: 0.55 }, 0.35)
                    .from('.tch-line-inner', { yPercent: 110, duration: 0.9, stagger: 0.12, ease: 'power4.out' }, 0.45)
                    .from('#tchSub', { y: 18, opacity: 0, duration: 0.65 }, 0.62)
                    .to('#tchContent', { opacity: 1, y: 0, duration: 0.8 }, 0.5)
                    .from('.tch-chapter', { y: 28, opacity: 0, duration: 0.55, stagger: 0.07, ease: 'back.out(1.35)' }, 0.72)
                    .from('.tch-meta', { opacity: 0, duration: 0.4 }, 0.95)
                    .from('#libScrollHint', { opacity: 0, y: 12, duration: 0.45 }, 1.02)
                    .to('.tch-float', { opacity: 1, scale: 1, duration: 0.7, stagger: 0.1, ease: 'power2.out' }, 0.85);

                if (parallax && enableFloatMotion) {
                    floatTween = gsap.to(parallax, {
                        xPercent: -1,
                        yPercent: -0.5,
                        duration: 22,
                        repeat: -1,
                        yoyo: true,
                        ease: 'sine.inOut'
                    });
                }

                gsap.to('#tchScrollLine', {
                    scaleY: 0.35,
                    opacity: 0.35,
                    duration: 1.5,
                    repeat: -1,
                    yoyo: true,
                    ease: 'sine.inOut'
                });

                if (hero && content && parallax && enableFloatMotion) {
                    var mx = 0, my = 0;
                    var qParallaxX = gsap.quickTo(parallax, 'x', { duration: 0.9, ease: 'power2.out' });
                    var qParallaxY = gsap.quickTo(parallax, 'y', { duration: 0.9, ease: 'power2.out' });
                    var qContentX = gsap.quickTo(content, 'x', { duration: 0.85, ease: 'power2.out' });
                    var qContentY = gsap.quickTo(content, 'y', { duration: 0.85, ease: 'power2.out' });

                    hero.addEventListener('mousemove', function (e) {
                        var rect = hero.getBoundingClientRect();
                        mx = (e.clientX - rect.left) / rect.width - 0.5;
                        my = (e.clientY - rect.top) / rect.height - 0.5;
                        qParallaxX(mx * 6);
                        qParallaxY(my * 5);
                        qContentX(mx * -2);
                        qContentY(my * -2);
                    }, { passive: true });
                }

                if (typeof ScrollTrigger !== 'undefined' && hero && content) {
                    ScrollTrigger.matchMedia({
                        '(max-width: 1024px)': function () {
                            gsap.set(content, { opacity: 1, y: 0, scale: 1, clearProps: 'transform' });
                            gsap.timeline({
                                scrollTrigger: {
                                    trigger: hero,
                                    start: 'top top',
                                    end: 'bottom top',
                                    scrub: 0.2
                                }
                            })
                            .to(bg, { y: 12, ease: 'none' }, 0)
                            .to('#tchScrollBridge', { opacity: 0.45, ease: 'none' }, 0.5);
                        },
                        '(min-width: 1025px)': function () {
                            var scrollTl = gsap.timeline({
                                scrollTrigger: {
                                    trigger: hero,
                                    start: 'top top',
                                    end: '+=50%',
                                    pin: true,
                                    scrub: 0.45,
                                    anticipatePin: 1,
                                    invalidateOnRefresh: true
                                }
                            });

                            if (bg) {
                                scrollTl.to(bg, { y: 40, scale: 1.05, ease: 'none' }, 0);
                            }
                            if (parallax) {
                                scrollTl.to(parallax, { y: 50, ease: 'none' }, 0);
                            }
                            scrollTl
                                .to('.tch-aurora--1', { y: -24, ease: 'none' }, 0)
                                .to('.tch-aurora--2', { y: 30, ease: 'none' }, 0)
                                .to('.tch-aurora--3', { y: -18, ease: 'none' }, 0)
                                .to(content, { y: -24, ease: 'none' }, 0)
                                .to('#tchTitle', { scale: 1.03, ease: 'none' }, 0)
                                .to('#tchLetterboxTop, #tchLetterboxBottom', { scaleY: 1.2, ease: 'none' }, 0)
                                .to('#tchScrollBridge', { opacity: 0.85, ease: 'none' }, 0.35);
                        }
                    });

                    ScrollTrigger.refresh();
                }
            } else if (typeof gsap !== 'undefined') {
                gsap.set(['#tchLetterboxTop', '#tchLetterboxBottom'], { scaleY: 1 });
                gsap.set('#tchContent, .tch-float, #libScrollHint', { opacity: 1, clearProps: 'transform' });
            }

            var hint = document.getElementById('libScrollHint');
            if (hint) {
                hint.addEventListener('click', function () { scrollToStore(); });
            }
        }

        var isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
        var prefersCoarse = window.matchMedia('(pointer: coarse)').matches;
        var lenis = null;
        if (!isTouchDevice && !prefersCoarse && typeof Lenis !== 'undefined') {
            lenis = new Lenis({ duration: 1.2, smoothWheel: true, smoothTouch: false });
            window.lenis = lenis;
            if (typeof ScrollTrigger !== 'undefined') {
                lenis.on('scroll', ScrollTrigger.update);
                gsap.ticker.add(function (time) { lenis.raf(time * 1000); });
                gsap.ticker.lagSmoothing(0);
                ScrollTrigger.scrollerProxy(document.documentElement, {
                    scrollTop: function (value) {
                        if (arguments.length) lenis.scrollTo(value, { immediate: true });
                        return lenis.scroll;
                    },
                    getBoundingClientRect: function () {
                        return { top: 0, left: 0, width: window.innerWidth, height: window.innerHeight };
                    }
                });
            } else {
                function rafLenis(t) { lenis.raf(t); requestAnimationFrame(rafLenis); }
                requestAnimationFrame(rafLenis);
            }
        }

        initCinemaHero();

        window.addEventListener('orientationchange', function () {
            if (typeof ScrollTrigger !== 'undefined') {
                setTimeout(function () { ScrollTrigger.refresh(); }, 200);
            }
        });

        if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
            gsap.registerPlugin(ScrollTrigger);
            document.querySelectorAll('#storeSection .gsap-fade').forEach(function (el) {
                gsap.fromTo(el, { y: 36, opacity: 0 }, {
                    y: 0, opacity: 1, duration: 0.75, ease: 'power2.out',
                    scrollTrigger: { trigger: el, start: 'top 92%', toggleActions: 'play none none none' }
                });
            });
        } else {
            document.querySelectorAll('.gsap-fade').forEach(function (el) {
                el.style.opacity = '1';
                el.style.transform = 'none';
            });
        }
        if (typeof ScrollTrigger !== 'undefined') ScrollTrigger.refresh();
    