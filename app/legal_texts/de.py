"""Deutsche Übersetzung der Rechtstexte (bei Abweichungen gilt die französische Fassung). Siehe fr.py."""

TERMS = {
    "title": "Nutzungsbedingungen",
    "updated": "Letzte Aktualisierung: Oktober 2026",
    "prevails": "",
    "back_home": "← Zurück zur Startseite",
    "back_settings": "← Zurück zu den Einstellungen",
    "see_also": "Siehe auch unsere Datenschutzerklärung →",
    "footer": "Wil App — Nutzungsbedingungen",
    "intro": "Diese Nutzungsbedingungen (die „Bedingungen“) regeln den Zugang zur Anwendung Wil App (der „Dienst“) und deren Nutzung. Der Dienst ist unter wilapp.tech erreichbar und wird von einer Privatperson betrieben, die in eigenem Namen handelt (der „Betreiber“) und über die Angaben in Abschnitt 15 erreichbar ist. Mit der Nutzung des Dienstes oder dem Abschluss eines Abonnements akzeptieren Sie diese Bedingungen vollständig.",
    "sections": [
        ("1. Gegenstand und Beschreibung des Dienstes", [
            ("p", "Wil App ist ein KI-gestütztes Analysewerkzeug für TikTok-Creator. Der Dienst ermöglicht unter anderem:"),
            ("ul", [
                "Ihr TikTok-Konto zu verbinden, um eine automatische Diagnose zu erhalten (Viralitätswert, Engagement-Rate, Stärken, Verbesserungspunkte, empfohlene Hashtags);",
                "ein von Ihnen manuell importiertes Video (bereits veröffentlicht oder nicht) anhand seines Bild- und Toninhalts zu analysieren;",
                "das Skript eines noch nicht gedrehten Videos zu analysieren oder eines zu erstellen;",
                "eine Bibliothek und tägliche Ideen (Hooks, Videoideen, Hashtags) zu durchsuchen, die auf von künstlicher Intelligenz durchgeführten Websuchen beruhen, und diejenigen zu speichern, die Ihnen gefallen.",
            ]),
            ("p", "Berichte und Inhalte werden von KI-Modellen externer Anbieter erzeugt: Claude (Anthropic) für die Kontoanalyse, die Skriptanalyse und -erstellung sowie die Bibliothek, und Gemini (Google) für die Videoanalyse. Sie beruhen auf den von Ihnen bereitgestellten Daten, auf Daten, die tatsächlich über die offizielle TikTok-API abgerufen wurden, oder auf Websuchen."),
        ]),
        ("2. Mindestalter, Anmeldung und Kontozugang", [
            ("p", "<strong>Mindestalter.</strong> Der Dienst ist Personen ab 18 Jahren vorbehalten. Mit der Nutzung des Dienstes erklären Sie, mindestens 18 Jahre alt zu sein. Wenn Sie unter 18 sind, dürfen Sie den Dienst nicht nutzen, insbesondere keine Videos oder Skripte zur Analyse hochladen. Erfahren wir, dass ein Nutzer unter 18 ist, können wir seinen Zugang sperren und seine Daten löschen."),
            ("p", "Die Funktionen zur Kontoanalyse erfordern die Anmeldung über das offizielle TikTok Login Kit (OAuth-Protokoll). Wil App hat Ihr TikTok-Passwort weder jemals erhalten noch fordert es dieses an. Sie können die Wil App erteilte Berechtigung jederzeit in den Einstellungen Ihres TikTok-Kontos für Verbindungen zu Drittanbietern widerrufen."),
            ("p", "Der Zugang zu den kostenpflichtigen Funktionen ist an Ihr Whop-Konto gebunden, das über die beim Bezahlvorgang verwendete E-Mail-Adresse identifiziert wird. Sie sind für die Vertraulichkeit Ihres Whop-Kontos verantwortlich."),
        ]),
        ("3. Von Ihnen importierte Inhalte", [
            ("p", "Wenn Sie eine Videodatei oder einen Skripttext zur Analyse importieren, sichern Sie zu, dass:"),
            ("ul", [
                "Sie die Rechte an diesem Inhalt besitzen oder über die erforderlichen Erlaubnisse zu seiner Nutzung verfügen (auch bei Inhalten eines anderen Creators, sofern Sie diese rechtmäßig erhalten haben – niemals durch automatisiertes Auslesen allein anhand eines Links);",
                "dieser Inhalt weder gegen Gesetze noch gegen Rechte Dritter noch gegen die Community-Richtlinien von TikTok verstößt.",
            ]),
            ("p", "Wil App sammelt, lädt oder scrapt keine Videos ohne Wissen des Nutzers direkt von TikTok: Jede analysierte Datei und jeder analysierte Text wird freiwillig von Ihnen bereitgestellt."),
            ("p", "Zur Analyse wird die Videodatei an Google (Gemini-API) gesendet, das Bilder und Ton analysiert; der Text eines Skripts wird an Anthropic (Claude) gesendet. Wil App speichert Ihre Videodatei nach der Analyse nicht, bewahrt aber den erzeugten Bericht auf, wie in unserer Datenschutzerklärung beschrieben. Diese Anbieter verarbeiten die Daten nach ihren eigenen Bedingungen. Ihre Videos und Skripte werden nicht verwendet, um Inhalte zu erzeugen, die anderen Nutzern angezeigt werden."),
        ]),
        ("4. Zulässige Nutzung", [
            ("p", "Sie verpflichten sich, den Dienst ausschließlich für persönliche und rechtmäßige Zwecke zu nutzen und nicht:"),
            ("ul", [
                "die technischen Grenzen des Dienstes zu umgehen (zum Beispiel die Wortgrenze bei der Skriptanalyse oder die Begrenzung der Anfragehäufigkeit);",
                "den Dienst für Reverse Engineering, Weiterverkauf oder das massenhafte automatisierte Auslesen der erzeugten Berichte zu verwenden;",
                "den Dienst zur Analyse von Inhalten zu verwenden, an denen Sie keine Nutzungsrechte haben;",
                "Ihren kostenpflichtigen Zugang mit Dritten zu teilen.",
            ]),
        ]),
        ("5. Kostenloses Angebot, Abonnement und Zahlung", [
            ("p", "<strong>Kostenloses Angebot.</strong> Der Dienst ermöglicht es Ihnen, kostenlos eine Videoanalyse und eine TikTok-Kontoanalyse auszuprobieren; der vollständige Bericht dieser Analysen sowie die übrigen Funktionen sind Abonnenten vorbehalten."),
            ("p", "<strong>Abonnement.</strong> Der vollständige Zugang zum Dienst wird im Abonnement angeboten, monatlich oder jährlich. Die enthaltenen Funktionen, die Preise und der Abrechnungszeitraum werden auf der Preisseite und vor dem Kauf auf der Bezahlseite angezeigt. Anfallende Steuern in Ihrem Land werden auf der Bezahlseite ausgewiesen. Das Abonnement unterliegt einer angemessenen Nutzung; zum Schutz des Dienstes können technische Begrenzungen der Anfragehäufigkeit gelten."),
            ("p", "<strong>Zahlung.</strong> Zahlungen werden von Whop (whop.com), einem externen Anbieter, nach dessen eigenen Bedingungen abgewickelt. Der Betreiber erhält und speichert Ihre Zahlungskartendaten nicht. Je nach Fall kann Whop als Verkäufer des Abonnements oder lediglich als Zahlungsdienstleister auftreten; der Verkäufer und der Gesamtpreis einschließlich Steuern werden auf der Bezahlseite angezeigt."),
            ("p", "<strong>Verlängerung.</strong> Das Abonnement verlängert sich am Ende jedes Zeitraums (monatlich oder jährlich) automatisch zum jeweils gültigen Preis, bis Sie kündigen. Der Betreiber kann seine Preise ändern: Eine Erhöhung gilt erst ab dem folgenden Zeitraum, nach angemessener vorheriger Mitteilung (per E-Mail oder in der App), und Sie können vor ihrem Inkrafttreten kündigen."),
        ]),
        ("6. Kündigung und Erstattung", [
            ("p", "<strong>Kündigung.</strong> Sie können Ihr Abonnement jederzeit kündigen, unter Einstellungen &gt; Abo verwalten (ein Link zu Ihrem Whop-Bereich) oder per Nachricht an uns. Die Kündigung wird zum Ende des bereits bezahlten Zeitraums wirksam: Sie behalten den Zugang bis zu diesem Datum und es erfolgen keine weiteren Abbuchungen. Der laufende Zeitraum wird nicht erstattet, vorbehaltlich der folgenden Regel."),
            ("p", "<strong>Erstattung innerhalb von 14 Tagen.</strong> Sie können innerhalb von 14 Tagen nach dem Kauf die Erstattung Ihres Abonnements verlangen, sofern mit diesem Abonnement <strong>keine Analyse</strong> (Video, TikTok-Konto oder Skript) durchgeführt wurde. Schreiben Sie uns dazu (Abschnitt 15) unter Angabe der beim Kauf verwendeten E-Mail-Adresse. Die Erstattung erfolgt über unseren Zahlungsdienstleister auf das ursprüngliche Zahlungsmittel."),
            ("p", "Sobald eine Analyse durchgeführt wurde, gilt die digitale Leistung als erbracht und der gezahlte Betrag ist nicht mehr erstattungsfähig, sofern das Gesetz nichts anderes verlangt. Diese Regel schränkt die zwingenden Rechte, die Ihnen nach dem Recht Ihres Wohnsitzlandes zustehen, nicht ein, einschließlich des Widerrufsrechts, das für Verbraucher in der Europäischen Union gilt. Der Zugang zum Dienst beginnt unmittelbar nach Ihrer Zahlung."),
        ]),
        ("7. Art der bereitgestellten Analysen", [
            ("p", "Die von Wil App bereitgestellten Werte, Diagnosen, Ratschläge und Schätzungen (darunter der Viralitätswert, Spannen für Aufrufe, Likes oder Kommentare und das „Viralitätspotenzial“ der täglichen Ideen) werden von künstlicher Intelligenz automatisch anhand der verfügbaren Daten erzeugt. Es handelt sich um Schätzungen, nicht um Vorhersagen: Sie sind eine Entscheidungshilfe und garantieren in keiner Weise ein Ergebnis (mehr Aufrufe, Follower oder Einnahmen). Wil App haftet nicht für Entscheidungen, die auf Grundlage dieser Analysen getroffen werden."),
        ]),
        ("8. Geistiges Eigentum", [
            ("p", "Die Anwendung, ihre Marke, ihr Design und ihr Code bleiben ausschließliches Eigentum des Betreibers. Die für Ihr Konto erzeugten Berichte werden Ihnen zur persönlichen Nutzung bereitgestellt; Sie behalten deren Inhalt, ohne dass dadurch Rechte an der Plattform selbst übertragen werden."),
        ]),
        ("9. Verfügbarkeit und Weiterentwicklung des Dienstes", [
            ("p", "Wil App ist ein Projekt in aktiver Entwicklung. Einzelne Funktionen können hinzugefügt, geändert oder vorübergehend entfernt werden. Wir bemühen uns, den Dienst am Laufen zu halten, garantieren aber keine ununterbrochene Verfügbarkeit. Wird eine in Ihrem Abonnement enthaltene Funktion dauerhaft entfernt, können Sie Ihr Abonnement kündigen und die Erstattung des nicht genutzten Teils des laufenden Zeitraums verlangen."),
        ]),
        ("10. Haftungsbeschränkung", [
            ("p", "Der Dienst wird „wie besehen“ bereitgestellt. Wil App ist nicht mit TikTok oder ByteDance Ltd. verbunden und wird von diesen weder gesponsert noch unterstützt. Soweit gesetzlich zulässig, schließt der Betreiber jede Haftung für mittelbare Schäden aus, die aus der Nutzung des Dienstes entstehen. Nichts in diesen Bedingungen schließt eine Haftung aus, die nach geltendem Recht nicht ausgeschlossen werden kann."),
        ]),
        ("11. Beendigung und Sperrung", [
            ("p", "Sie können den Dienst jederzeit nicht mehr nutzen, indem Sie den Zugang in den Einstellungen Ihres TikTok-Kontos widerrufen oder Ihr Konto unter Einstellungen &gt; Mein Konto löschen entfernen (dabei werden Ihre Daten gelöscht, wie in unserer Datenschutzerklärung beschrieben). Das Löschen Ihres Kontos kündigt ein laufendes kostenpflichtiges Abonnement nicht automatisch: Kündigen Sie es gesondert (Abschnitt 6). Der Betreiber behält sich das Recht vor, den Zugang eines Nutzers bei Missbrauch oder Verstoß gegen diese Bedingungen zu sperren."),
        ]),
        ("12. Änderungen dieser Bedingungen", [
            ("p", "Diese Bedingungen können aktualisiert werden. Bei einer wesentlichen Änderung, insbesondere der Preise oder der Erstattungsregeln, werden Sie vor Inkrafttreten per E-Mail oder in der App informiert. Die weitere Nutzung des Dienstes nach einer Änderung gilt als Annahme der neuen Bedingungen."),
        ]),
        ("13. Anwendbares Recht", [
            ("p", "Diese Bedingungen unterliegen dem am Wohnsitz des Betreibers geltenden Recht, unbeschadet der zwingenden Verbraucherschutzvorschriften Ihres Wohnsitzlandes."),
        ]),
        ("14. Übersetzungen", [
            ("p", "Diese Bedingungen werden Ihnen zur Erleichterung in mehreren Sprachen angeboten. Bei Abweichungen gilt die französische Fassung."),
        ]),
        ("15. Kontakt", [
            ("p", "Bei Fragen zu diesen Bedingungen, zu Ihrem Abonnement oder für einen Erstattungsantrag erreichen Sie uns unter {EMAIL} oder über {WHATSAPP}."),
        ]),
    ],
}

PRIVACY = {
    "title": "Datenschutzerklärung",
    "updated": "Letzte Aktualisierung: Oktober 2026",
    "prevails": "",
    "back_home": "← Zurück zur Startseite",
    "back_settings": "← Zurück zu den Einstellungen",
    "see_also": "Siehe auch unsere Nutzungsbedingungen →",
    "footer": "Wil App — Datenschutzerklärung",
    "intro": "Diese Datenschutzerklärung erläutert, wie Wil App („wir“) Informationen erhebt, verwendet und schützt, wenn Sie unseren Dienst nutzen. Wil App wird von einer Privatperson betrieben, die in eigenem Namen handelt, Verantwortlicher für die Datenverarbeitung ist und über die Angaben in Abschnitt 12 erreichbar ist.",
    "sections": [
        ("1. Informationen, die wir erheben", [
            ("p", "<strong>TikTok-Konto.</strong> Wenn Sie Ihr TikTok-Konto über das offizielle TikTok Login Kit verbinden, erhalten wir – ausschließlich mit Ihrer ausdrücklichen Berechtigung – möglicherweise:"),
            ("ul", [
                "grundlegende Profilinformationen (Benutzername, Anzeigename, Profilbild);",
                "öffentliche Inhalte und Videometadaten, die Ihrem Konto zugeordnet sind.",
            ]),
            ("p", "Wir greifen weder auf private Nachrichten noch auf Zahlungsinformationen oder sonstige Daten zu, die über die von Ihnen erteilten Berechtigungen hinausgehen. Von Ihrem verbundenen Konto speichern wir eine Zugriffssitzung (das Token wird verschlüsselt) sowie regelmäßige Momentaufnahmen Ihrer Statistiken (Engagement- und Viralitätsraten), damit wir Ihr Konto im Zeitverlauf mit sich selbst vergleichen können."),
            ("p", "<strong>Whop-Konto und Abonnement.</strong> Zur Verwaltung der Abonnements nutzen wir Whop: Wir erhalten Ihre Whop-Kennung, Ihre E-Mail-Adresse und den Status Ihres Abonnements (aktiv oder nicht, Tarif). Zahlungen werden von Whop abgewickelt: Wir erhalten und speichern Ihre Zahlungskartendaten nicht."),
            ("p", "<strong>Videos und Skripte, die Sie bereitstellen.</strong> Wenn Sie ein Video hochladen oder ein Skript zur Analyse einfügen, wird es an unsere KI-Anbieter (Abschnitt 2) gesendet, um Ihren Bericht zu erstellen. Wir speichern Ihre Videodatei nach der Analyse nicht. Wir verwenden Ihre Videos oder Skripte nicht, um Inhalte zu erstellen, die anderen Nutzern angezeigt werden."),
            ("p", "<strong>Analyseberichte.</strong> Der erzeugte Bericht wird auf unseren Servern unter einer zufälligen Kennung ohne direkte Verknüpfung mit Ihrer Identität gespeichert, damit Sie ihn wiederfinden können (zum Beispiel nach dem Neuladen der Seite oder dem Abschluss eines Abonnements). Berichte werden nach 180 Tagen automatisch gelöscht."),
            ("p", "<strong>Rückmeldung zu Schätzungen.</strong> Wenn Sie uns mitteilen, dass ein Video bereits veröffentlicht wurde, und angeben, ob unsere Schätzung den tatsächlichen Ergebnissen nahekam, speichern wir diese Antwort anonym (Nische, Wert, geschätztes Niveau und Ihre Antwort), ohne das Video und ohne Kennung."),
            ("p", "<strong>Auf Ihrem Gerät gespeicherte Daten.</strong> Ihre Antworten im Onboarding, Ihr Analyseverlauf, gespeicherte Elemente, Ihre Sprach- und Darstellungsauswahl sowie eine Kopie Ihrer letzten Berichte werden in Ihrem Browser (lokaler Speicher) auf Ihrem Gerät abgelegt. Wenn Sie TikTok verbinden, speichert Ihr Browser außerdem Ihr öffentliches Profil (Name, Benutzername, Bild) und eine Sitzungskennung."),
            ("p", "<strong>Technische Daten.</strong> Zum Schutz des Dienstes vor Missbrauch verwenden wir vorübergehend Ihre IP-Adresse (Begrenzung der Anfragehäufigkeit); unser Hosting-Anbieter kann technische Protokolle für begrenzte Zeit aufbewahren."),
        ]),
        ("2. Verarbeitung durch künstliche Intelligenz", [
            ("p", "Um Ihre Analysen zu erstellen, <strong>übermittelt Wil App die von Ihnen bereitgestellten Inhalte an externe Anbieter künstlicher Intelligenz</strong>, die sie verarbeiten, um sie zu analysieren und zu klassifizieren. Konkret:"),
            ("ul", [
                "Ihre <strong>Videos</strong> (Bild und Ton) werden an Google (Gemini) gesendet;",
                "Ihre <strong>Skripte</strong> werden an Anthropic (Claude) gesendet;",
                "die Angaben Ihres <strong>TikTok-Profils</strong> (Name, Benutzername, Beschreibung) und die Statistiken Ihrer Videos werden an Anthropic (Claude) gesendet;",
                "<strong>Trendideen</strong> werden von Claude (Anthropic) anhand von Websuchen erstellt.",
            ]),
            ("p", "Diese Übermittlung findet nur statt, wenn Sie eine Analyse starten, und nur mit Ihrer Zustimmung: Vor der ersten Analyse wird ein Einwilligungsfenster angezeigt, und Sie können Ihre Einwilligung jederzeit in den Einstellungen (Profil) widerrufen. Diese Anbieter sind unabhängige Unternehmen: Sie verarbeiten die Daten nach ihren eigenen Bedingungen und Datenschutzregeln. Wir verkaufen Ihre Inhalte nicht und verwenden sie nicht, um Inhalte zu erstellen, die anderen Nutzern angezeigt werden. Wenn Sie nicht möchten, dass Ihre Inhalte an diese Anbieter übermittelt werden, nutzen Sie die Analysefunktionen nicht."),
        ]),
        ("3. Wie wir Ihre Informationen verwenden", [
            ("p", "Wir verwenden diese Informationen ausschließlich, um den Dienst bereitzustellen (Kontoeinblicke, Video- und Skriptanalyse, Trends, Verwaltung Ihres Abonnements), ihn sicher zu halten und seine Zuverlässigkeit sowie die Genauigkeit unserer Schätzungen zu verbessern. Wir verkaufen Ihre personenbezogenen Daten nicht an Dritte."),
        ]),
        ("4. Rechtsgrundlagen", [
            ("p", "Je nach Fall beruht die Verarbeitung auf der Vertragserfüllung (Bereitstellung des Dienstes und Verwaltung Ihres Abonnements), Ihrer Einwilligung (Verbindung Ihres TikTok-Kontos, die Sie jederzeit widerrufen können), unserem berechtigten Interesse (Sicherheit, Missbrauchsprävention, Verbesserung des Dienstes) und der Erfüllung unserer rechtlichen Pflichten (Buchhaltung und Zahlungen)."),
        ]),
        ("5. Aufbewahrung und Sicherheit", [
            ("p", "Wir ergreifen angemessene technische Maßnahmen zum Schutz der gespeicherten Informationen: TikTok-Zugriffstoken werden verschlüsselt, Verbindungen sind durch HTTPS geschützt und der Zugriff auf unsere Datenbanken ist beschränkt."),
            ("ul", [
                "TikTok-Sitzungen: höchstens 30 Tage oder bis Sie die Verbindung trennen oder Ihr Konto löschen.",
                "Momentaufnahmen der Kontostatistiken: bis zum Löschen Ihres Kontos.",
                "Analyseberichte: 180 Tage.",
                "Zahlungs- und Abrechnungsdaten: werden von Whop und gegebenenfalls von uns so lange aufbewahrt, wie das Gesetz es verlangt.",
            ]),
        ]),
        ("6. Dienste Dritter", [
            ("p", "Unser Dienst beruht auf folgenden Anbietern, für die jeweils deren eigene Bedingungen und Datenschutzerklärungen gelten:"),
            ("ul", [
                "TikTok (offizielle APIs und Login Kit);",
                "Anthropic (Claude), das Kontodaten, Skripte und die Websuchen verarbeitet, die zur Erstellung von Berichten und Trends verwendet werden;",
                "Google (Gemini-API), das die von Ihnen hochgeladenen Videos verarbeitet, um Bild und Ton zu analysieren;",
                "Whop, das Zahlungen und die Anmeldung bei Ihrem Whop-Konto verarbeitet;",
                "Sentry, das technische Fehlerberichte des Servers erhält (ohne Cookies, E-Mail-Adressen oder Inhalte Ihrer Videos und Skripte), damit wir Störungen beheben können;",
                "unsere Anbieter für Hosting, Datenbank und Netzwerksicherheit (Render, Supabase, Cloudflare), die die oben beschriebenen Daten speichern oder übertragen.",
            ]),
            ("p", "Ihre Nutzung von TikTok unterliegt weiterhin der Datenschutzerklärung und den Bedingungen von TikTok."),
        ]),
        ("7. Internationale Übermittlungen", [
            ("p", "Einige dieser Anbieter haben ihren Sitz außerhalb Ihres Landes, insbesondere in den Vereinigten Staaten. Ihre Daten können daher in andere Länder übermittelt und dort verarbeitet werden, mit den Garantien, die diese Anbieter und das geltende Recht vorsehen."),
        ]),
        ("8. Ihre Rechte", [
            ("p", "Im Bildschirm „Einstellungen“ der App können Sie jederzeit:"),
            ("ul", [
                "<strong>TikTok trennen</strong>: Wir widerrufen das Zugriffstoken und löschen Ihre Sitzung, Ihr Verlauf bleibt erhalten;",
                "<strong>Ihr Konto löschen</strong>: Wir löschen die auf Ihrem Gerät gespeicherten Daten und, falls TikTok verbunden war, widerrufen wir den Zugang und löschen Ihre Sitzungen und den Statistikverlauf auf unseren Servern. Diese Aktion ist endgültig.",
            ]),
            ("p", "Sie können den Zugang von Wil App auch in den Einstellungen Ihres TikTok-Kontos widerrufen. Nach dem geltenden Recht (zum Beispiel der DSGVO) haben Sie außerdem das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung, Widerspruch und Datenübertragbarkeit sowie das Recht, bei der Datenschutzbehörde Ihres Landes Beschwerde einzulegen. Zur Ausübung dieser Rechte, insbesondere für Daten im Zusammenhang mit Ihrem Abonnement oder einem bestimmten Bericht (bitte mit dessen Link), kontaktieren Sie uns: Wir antworten innerhalb eines Monats."),
        ]),
        ("9. Cookies und lokaler Speicher", [
            ("p", "Wir verwenden nur Cookies, die für das Funktionieren des Dienstes unbedingt erforderlich sind, ohne Werbung und ohne Tracking: Ihre Sprachauswahl (1 Jahr), den Zähler für die kostenlose Analyse (1 Jahr), Ihre Whop-Anmeldung (30 Tage) sowie temporäre Cookies bei Anmeldung und Zahlung (von einigen Minuten bis 24 Stunden). Der lokale Speicher Ihres Browsers wird für die in Abschnitt 1 beschriebenen Einstellungen und den Verlauf verwendet."),
        ]),
        ("10. Mindestalter", [
            ("p", "Der Dienst richtet sich an Personen ab 18 Jahren. Wir erheben wissentlich keine Informationen von Personen unter 18 Jahren. Wenn Sie glauben, dass eine Person unter 18 den Dienst genutzt hat, kontaktieren Sie uns, und wir löschen die zugehörigen Daten."),
        ]),
        ("11. Änderungen", [
            ("p", "Wir können diese Erklärung von Zeit zu Zeit aktualisieren. Bei einer wesentlichen Änderung informieren wir Sie in der App. Die weitere Nutzung des Dienstes nach einer Änderung gilt als Annahme der aktualisierten Erklärung. Bei Abweichungen zwischen den Übersetzungen gilt die französische Fassung."),
        ]),
        ("12. Kontakt", [
            ("p", "Fragen? Kontaktieren Sie uns unter {EMAIL} oder über {WHATSAPP}."),
        ]),
    ],
}
