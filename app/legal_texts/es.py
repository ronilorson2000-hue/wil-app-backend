"""Traducción al español de los textos legales (en caso de discrepancia prevalece la versión francesa). Ver fr.py."""

TERMS = {
    "title": "Términos de servicio",
    "updated": "Última actualización: octubre de 2026",
    "prevails": "",
    "back_home": "← Volver al inicio",
    "back_settings": "← Volver a los ajustes",
    "see_also": "Consulta también nuestra Política de privacidad →",
    "footer": "Wil App — Términos de servicio",
    "intro": "Estos Términos de servicio (los «Términos») regulan el acceso y el uso de la aplicación Wil App (el «Servicio»), disponible en wilapp.tech y operada por una persona física que actúa a título personal (el «Editor»), a quien puedes contactar con los datos del apartado 15. Al usar el Servicio o contratar una suscripción, aceptas íntegramente estos Términos.",
    "sections": [
        ("1. Objeto y descripción del servicio", [
            ("p", "Wil App es una herramienta de análisis con inteligencia artificial para creadores de contenido de TikTok. Entre otras cosas, el Servicio permite:"),
            ("ul", [
                "conectar tu cuenta de TikTok para obtener un diagnóstico automático (puntuación de viralidad, tasa de interacción, puntos fuertes, puntos a mejorar, hashtags sugeridos);",
                "analizar un vídeo (ya publicado o no) que importes manualmente, a partir de su contenido visual y sonoro;",
                "analizar el guion de un vídeo que aún no has grabado, o generar uno;",
                "consultar una biblioteca e ideas diarias (ganchos, ideas de vídeo, hashtags) basadas en búsquedas web realizadas por inteligencia artificial, y guardar las que te gusten.",
            ]),
            ("p", "Los informes y contenidos los generan modelos de inteligencia artificial de proveedores externos: Claude (Anthropic) para el análisis de cuenta, el análisis y la generación de guiones y la biblioteca, y Gemini (Google) para el análisis de vídeo. Se basan en los datos que proporcionas, en datos obtenidos realmente a través de la API oficial de TikTok o en búsquedas web."),
        ]),
        ("2. Edad mínima, conexión y acceso a la cuenta", [
            ("p", "<strong>Edad mínima.</strong> El Servicio está reservado a personas de 18 años o más. Al usar el Servicio declaras tener al menos 18 años. Si eres menor de 18 años, no puedes usar el Servicio y, en particular, no puedes importar vídeos ni guiones para su análisis. Si tenemos conocimiento de que un usuario es menor de 18 años, podremos suspender su acceso y eliminar sus datos."),
            ("p", "Las funciones de análisis de cuenta requieren iniciar sesión mediante el Login Kit oficial de TikTok (protocolo OAuth). Wil App nunca tiene ni solicita tu contraseña de TikTok. Puedes revocar en cualquier momento la autorización concedida a Wil App desde los ajustes de conexiones de terceros de tu cuenta de TikTok."),
            ("p", "El acceso a las funciones de pago está vinculado a tu cuenta de Whop, identificada por la dirección de correo electrónico usada al pagar. Eres responsable de la confidencialidad de tu cuenta de Whop."),
        ]),
        ("3. Contenido que importas", [
            ("p", "Cuando importas un archivo de vídeo o el texto de un guion para analizarlo, garantizas que:"),
            ("ul", [
                "posees los derechos sobre ese contenido o cuentas con los permisos necesarios para usarlo (incluso si se trata del contenido de otro creador, siempre que lo hayas obtenido de forma lícita, nunca mediante extracción automatizada a partir de un simple enlace);",
                "ese contenido no infringe ninguna ley, ningún derecho de terceros ni las normas de la comunidad de TikTok.",
            ]),
            ("p", "Wil App no recopila, descarga ni extrae ningún vídeo directamente de TikTok sin el conocimiento del usuario: cada archivo o texto analizado lo proporcionas tú voluntariamente."),
            ("p", "Para analizarlo, el archivo de vídeo se envía a Google (API de Gemini), que analiza sus imágenes y su sonido; el texto de un guion se envía a Anthropic (Claude). Wil App no conserva tu archivo de vídeo tras el análisis, pero sí conserva el informe generado, como se describe en nuestra Política de privacidad. Estos proveedores tratan los datos según sus propias condiciones. Tus vídeos y guiones no se usan para generar el contenido mostrado a otros usuarios."),
        ]),
        ("4. Uso permitido", [
            ("p", "Te comprometes a usar el Servicio estrictamente con fines personales y lícitos y a no:"),
            ("ul", [
                "intentar eludir los límites técnicos del Servicio (por ejemplo, el límite de palabras en el análisis de guiones o los límites de frecuencia de solicitudes);",
                "usar el Servicio para ingeniería inversa, reventa o extracción automatizada masiva de los informes generados;",
                "usar el Servicio para analizar contenido sobre el que no tengas derechos de uso;",
                "compartir tu acceso de pago con terceros.",
            ]),
        ]),
        ("5. Oferta gratuita, suscripción y pago", [
            ("p", "<strong>Oferta gratuita.</strong> El Servicio te permite probar gratis un análisis de vídeo y un análisis de cuenta de TikTok; el informe completo de estos análisis y las demás funciones están reservados a los suscriptores."),
            ("p", "<strong>Suscripción.</strong> El acceso completo al Servicio se ofrece mediante suscripción, mensual o anual. Las funciones incluidas, los precios y el periodo de facturación se muestran en la página de Precios y en la página de pago antes de comprar. Los impuestos aplicables en tu país se muestran en la página de pago. La suscripción está sujeta a un uso razonable; pueden aplicarse límites técnicos de frecuencia para proteger el Servicio."),
            ("p", "<strong>Pago.</strong> Los pagos los procesa Whop (whop.com), un proveedor externo, conforme a sus propias condiciones. El Editor no recibe ni conserva los datos de tu tarjeta. Según el caso, Whop puede actuar como vendedor de la suscripción o simplemente como proveedor de pagos; el vendedor y el precio total, impuestos incluidos, se muestran en la página de pago."),
            ("p", "<strong>Renovación.</strong> La suscripción se renueva automáticamente al final de cada periodo (mensual o anual), al precio vigente, hasta que la canceles. El Editor puede modificar sus precios: cualquier aumento se aplica a partir del periodo siguiente, con un preaviso razonable (por correo electrónico o en la aplicación), y puedes cancelar antes de que entre en vigor."),
        ]),
        ("6. Cancelación y reembolso", [
            ("p", "<strong>Cancelación.</strong> Puedes cancelar tu suscripción en cualquier momento, desde Ajustes &gt; Gestionar mi suscripción (un enlace a tu área de Whop) o escribiéndonos. La cancelación surte efecto al final del periodo ya pagado: conservas el acceso hasta esa fecha y no se realiza ningún cargo adicional. El periodo en curso no se reembolsa, salvo lo dispuesto en la regla siguiente."),
            ("p", "<strong>Reembolso en 14 días.</strong> Puedes solicitar el reembolso de tu suscripción en los 14 días siguientes a la compra, siempre que <strong>no se haya realizado ningún análisis</strong> (vídeo, cuenta de TikTok o guion) con esa suscripción. Para ello, escríbenos (apartado 15) indicando la dirección de correo electrónico usada en la compra. El reembolso se efectúa al medio de pago original, a través de nuestro proveedor de pagos."),
            ("p", "Una vez realizado un análisis, se considera prestado el servicio digital y el importe pagado deja de ser reembolsable, salvo que la ley exija otra cosa. Esta regla no limita los derechos imperativos que te reconoce la ley de tu país de residencia, incluido el derecho de desistimiento que se aplica a los consumidores de la Unión Europea. El acceso al Servicio comienza inmediatamente después de tu pago."),
        ]),
        ("7. Naturaleza de los análisis proporcionados", [
            ("p", "Las puntuaciones, diagnósticos, consejos y estimaciones que proporciona Wil App (incluidos la puntuación de viralidad, los rangos de visualizaciones, «me gusta» o comentarios y el «potencial de viralidad» de las ideas diarias) los genera automáticamente la inteligencia artificial a partir de los datos disponibles. Son estimaciones, no predicciones: constituyen una ayuda a la decisión y no garantizan en modo alguno un resultado (más visualizaciones, seguidores o ingresos). Wil App no se hace responsable de las decisiones tomadas a partir de estos análisis."),
        ]),
        ("8. Propiedad intelectual", [
            ("p", "La aplicación, su marca, su diseño y su código siguen siendo propiedad exclusiva del Editor. Los informes generados para tu cuenta se te proporcionan para tu uso personal; conservas su contenido, sin que ello suponga la cesión de ningún derecho sobre la propia plataforma."),
        ]),
        ("9. Disponibilidad y evolución del servicio", [
            ("p", "Wil App es un proyecto en desarrollo activo. Algunas funciones pueden añadirse, modificarse o retirarse temporalmente. Nos esforzamos por mantener el Servicio en funcionamiento, pero no garantizamos una disponibilidad ininterrumpida. Si una función incluida en tu suscripción se retira de forma definitiva, podrás cancelar tu suscripción y solicitar el reembolso de la parte no utilizada del periodo en curso."),
        ]),
        ("10. Limitación de responsabilidad", [
            ("p", "El Servicio se presta «tal cual». Wil App no está afiliada, patrocinada ni respaldada por TikTok ni por ByteDance Ltd. En la medida en que la ley lo permita, el Editor declina toda responsabilidad por los daños indirectos derivados del uso del Servicio. Nada en estos Términos excluye una responsabilidad que no pueda excluirse según la ley aplicable."),
        ]),
        ("11. Terminación y suspensión", [
            ("p", "Puedes dejar de usar el Servicio en cualquier momento, revocando el acceso desde los ajustes de tu cuenta de TikTok o cerrando tu cuenta desde Ajustes &gt; Cerrar cuenta (lo que elimina tus datos, como se describe en nuestra Política de privacidad). Cerrar tu cuenta no cancela por sí solo una suscripción de pago en curso: cancélala por separado (apartado 6). El Editor se reserva el derecho de suspender el acceso de un usuario en caso de abuso o de incumplimiento de estos Términos."),
        ]),
        ("12. Modificación de estos Términos", [
            ("p", "Estos Términos pueden actualizarse. En caso de cambio importante, en particular de los precios o de las reglas de reembolso, se te informará por correo electrónico o en la aplicación antes de su entrada en vigor. El uso continuado del Servicio tras un cambio supone la aceptación de las nuevas condiciones."),
        ]),
        ("13. Ley aplicable", [
            ("p", "Estos Términos se rigen por la ley aplicable en el lugar de residencia del Editor, sin perjuicio de las normas imperativas de protección de los consumidores de tu país de residencia."),
        ]),
        ("14. Traducciones", [
            ("p", "Estos Términos se ofrecen en varios idiomas para tu comodidad. En caso de discrepancia, prevalece la versión francesa."),
        ]),
        ("15. Contacto", [
            ("p", "Para cualquier pregunta sobre estos Términos, tu suscripción o una solicitud de reembolso, escríbenos a {EMAIL} o a través de {WHATSAPP}."),
        ]),
    ],
}

PRIVACY = {
    "title": "Política de privacidad",
    "updated": "Última actualización: octubre de 2026",
    "prevails": "",
    "back_home": "← Volver al inicio",
    "back_settings": "← Volver a los ajustes",
    "see_also": "Consulta también nuestros Términos de servicio →",
    "footer": "Wil App — Política de privacidad",
    "intro": "Esta Política de privacidad explica cómo Wil App («nosotros») recopila, usa y protege la información cuando utilizas nuestro Servicio. Wil App la opera una persona física que actúa a título personal, responsable del tratamiento de los datos, a quien puedes contactar con los datos del apartado 11.",
    "sections": [
        ("1. Información que recopilamos", [
            ("p", "<strong>Cuenta de TikTok.</strong> Cuando conectas tu cuenta de TikTok mediante el Login Kit oficial de TikTok, podemos recibir, únicamente con tu autorización explícita:"),
            ("ul", [
                "información básica del perfil (nombre de usuario, nombre visible, foto de perfil);",
                "contenido público y metadatos de los vídeos asociados a tu cuenta.",
            ]),
            ("p", "No accedemos a mensajes privados, a información de pago ni a ningún dato más allá de lo que permiten las autorizaciones que concedes. De tu cuenta conectada conservamos una sesión de acceso (el token está cifrado) y capturas periódicas de tus estadísticas (tasas de interacción y de viralidad), para poder comparar tu cuenta consigo misma a lo largo del tiempo."),
            ("p", "<strong>Cuenta de Whop y suscripción.</strong> Para gestionar las suscripciones usamos Whop: recibimos tu identificador de Whop, tu dirección de correo electrónico y el estado de tu suscripción (activa o no, plan). Los pagos los procesa Whop: no recibimos ni conservamos los datos de tu tarjeta."),
            ("p", "<strong>Vídeos y guiones que proporcionas.</strong> Cuando subes un vídeo o pegas un guion para analizarlo, se envía a nuestros proveedores de inteligencia artificial (apartado 5) para generar tu informe. No conservamos tu archivo de vídeo tras el análisis. No usamos tus vídeos ni guiones para elaborar el contenido mostrado a otros usuarios."),
            ("p", "<strong>Informes de análisis.</strong> El informe generado se conserva en nuestros servidores bajo un identificador aleatorio, sin vínculo directo con tu identidad, para que puedas recuperarlo (por ejemplo, tras actualizar la página o suscribirte). Los informes se eliminan automáticamente pasados 180 días."),
            ("p", "<strong>Valoración de las estimaciones.</strong> Si nos indicas que un vídeo ya se publicó y respondes si nuestra estimación se acercó a los resultados reales, registramos esa respuesta de forma anónima (nicho, puntuación, nivel estimado y tu respuesta), sin el vídeo y sin ningún identificador."),
            ("p", "<strong>Datos conservados en tu dispositivo.</strong> Tus respuestas de incorporación, tu historial de análisis, los elementos guardados, tus preferencias de idioma y apariencia y una copia de tus últimos informes se almacenan en tu navegador (almacenamiento local), en tu dispositivo. Si conectas TikTok, tu navegador también conserva tu perfil público (nombre, usuario, foto) y un identificador de sesión."),
            ("p", "<strong>Datos técnicos.</strong> Para proteger el Servicio contra abusos, usamos temporalmente tu dirección IP (limitación de la frecuencia de solicitudes); nuestro proveedor de alojamiento puede conservar registros técnicos durante un tiempo limitado."),
        ]),
        ("2. Cómo usamos tu información", [
            ("p", "Usamos esta información únicamente para prestar el Servicio (análisis de cuenta, análisis de vídeo y guiones, tendencias, gestión de tu suscripción), mantenerlo seguro y mejorar su fiabilidad y la precisión de nuestras estimaciones. No vendemos tus datos personales a terceros."),
        ]),
        ("3. Bases jurídicas", [
            ("p", "Según el caso, el tratamiento se basa en la ejecución del contrato (prestación del Servicio y gestión de tu suscripción), en tu consentimiento (conexión de tu cuenta de TikTok, que puedes retirar en cualquier momento), en nuestro interés legítimo (seguridad, prevención de abusos, mejora del Servicio) y en el cumplimiento de nuestras obligaciones legales (contabilidad y pagos)."),
        ]),
        ("4. Conservación y seguridad", [
            ("p", "Aplicamos medidas técnicas razonables para proteger la información que almacenamos: los tokens de acceso de TikTok están cifrados, las conexiones están protegidas mediante HTTPS y el acceso a nuestras bases de datos está restringido."),
            ("ul", [
                "Sesiones de TikTok: 30 días como máximo, o hasta que te desconectes o cierres tu cuenta.",
                "Capturas de estadísticas de la cuenta: hasta que cierres tu cuenta.",
                "Informes de análisis: 180 días.",
                "Datos de pago y facturación: los conserva Whop y, en su caso, nosotros durante el tiempo que exija la ley.",
            ]),
        ]),
        ("5. Servicios de terceros", [
            ("p", "Nuestro Servicio se apoya en los siguientes proveedores, cada uno sujeto a sus propias condiciones y política de privacidad:"),
            ("ul", [
                "TikTok (API oficiales y Login Kit);",
                "Anthropic (Claude), que trata los datos de la cuenta, los guiones y las búsquedas web usadas para generar informes y tendencias;",
                "Google (API de Gemini), que trata los vídeos que subes para analizar sus imágenes y su sonido;",
                "Whop, que trata los pagos y el inicio de sesión en tu cuenta de Whop;",
                "Sentry, que recibe informes técnicos de errores del servidor (sin cookies, sin direcciones de correo electrónico y sin el contenido de tus vídeos o guiones) para que podamos corregir las averías;",
                "nuestros proveedores de alojamiento, base de datos y seguridad de red (Render, Supabase, Cloudflare), que almacenan o transmiten los datos descritos anteriormente.",
            ]),
            ("p", "Tu uso de TikTok sigue sujeto a la política de privacidad y a las condiciones propias de TikTok."),
        ]),
        ("6. Transferencias internacionales", [
            ("p", "Algunos de estos proveedores están ubicados fuera de tu país, en particular en Estados Unidos. Por tanto, tus datos pueden transferirse y tratarse en otros países, con las garantías previstas por esos proveedores y por la ley aplicable."),
        ]),
        ("7. Tus derechos", [
            ("p", "Desde la pantalla Ajustes de la aplicación puedes en cualquier momento:"),
            ("ul", [
                "<strong>Desconectar TikTok</strong>: revocamos el token de acceso y eliminamos tu sesión, y conservamos tu historial;",
                "<strong>Cerrar tu cuenta</strong>: eliminamos los datos almacenados en tu dispositivo y, si TikTok estaba conectado, revocamos el acceso y eliminamos de nuestros servidores tus sesiones y el historial de estadísticas. Esta acción es definitiva.",
            ]),
            ("p", "También puedes revocar el acceso de Wil App desde los ajustes de tu cuenta de TikTok. Según la ley aplicable (por ejemplo, el RGPD), tienes además derecho de acceso, rectificación, supresión, limitación, oposición y portabilidad, así como derecho a presentar una reclamación ante la autoridad de protección de datos de tu país. Para ejercer estos derechos, en particular sobre los datos vinculados a tu suscripción o a un informe concreto (indica su enlace), contáctanos: respondemos en el plazo de un mes."),
        ]),
        ("8. Cookies y almacenamiento local", [
            ("p", "Solo usamos cookies estrictamente necesarias para el funcionamiento del Servicio, sin publicidad ni seguimiento: tu elección de idioma (1 año), el contador de análisis gratuito (1 año), tu inicio de sesión de Whop (30 días) y cookies temporales durante el inicio de sesión y el pago (de unos minutos a 24 horas). El almacenamiento local de tu navegador se usa para las preferencias y el historial descritos en el apartado 1."),
        ]),
        ("9. Edad mínima", [
            ("p", "El Servicio está dirigido a personas de 18 años o más. No recopilamos a sabiendas información de menores de 18 años. Si crees que una persona menor de 18 años ha usado el Servicio, contáctanos y eliminaremos los datos correspondientes."),
        ]),
        ("10. Cambios", [
            ("p", "Podemos actualizar esta Política de vez en cuando. En caso de cambio importante, te lo comunicaremos en la aplicación. El uso continuado del Servicio tras un cambio supone la aceptación de la política actualizada. En caso de discrepancia entre las traducciones, prevalece la versión francesa."),
        ]),
        ("11. Contacto", [
            ("p", "¿Preguntas? Contáctanos en {EMAIL} o a través de {WHATSAPP}."),
        ]),
    ],
}
