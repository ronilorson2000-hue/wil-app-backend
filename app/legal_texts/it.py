"""Traduzione italiana dei testi legali (in caso di discrepanza prevale la versione francese). Vedi fr.py."""

TERMS = {
    "title": "Termini di servizio",
    "updated": "Ultimo aggiornamento: ottobre 2026",
    "prevails": "",
    "back_home": "← Torna alla home",
    "back_settings": "← Torna alle impostazioni",
    "see_also": "Vedi anche la nostra Informativa sulla privacy →",
    "footer": "Wil App — Termini di servizio",
    "intro": "I presenti Termini di servizio (i «Termini») disciplinano l'accesso e l'utilizzo dell'applicazione Wil App (il «Servizio»), disponibile su wilapp.tech e gestita da una persona fisica che agisce a titolo personale (l'«Editore»), contattabile ai recapiti indicati nella sezione 15. Utilizzando il Servizio o sottoscrivendo un abbonamento, accetti integralmente i presenti Termini.",
    "sections": [
        ("1. Oggetto e descrizione del servizio", [
            ("p", "Wil App è uno strumento di analisi basato sull'intelligenza artificiale per i creator di contenuti TikTok. Il Servizio consente, tra le altre cose, di:"),
            ("ul", [
                "collegare il tuo account TikTok per ottenere una diagnosi automatica (punteggio di viralità, tasso di engagement, punti di forza, punti da migliorare, hashtag suggeriti);",
                "analizzare un video (già pubblicato o meno) che importi manualmente, in base al suo contenuto visivo e sonoro;",
                "analizzare lo script di un video che non hai ancora girato, oppure generarne uno;",
                "consultare una libreria e idee giornaliere (hook, idee per video, hashtag) basate su ricerche web effettuate dall'intelligenza artificiale, e salvare quelle che ti piacciono.",
            ]),
            ("p", "I report e i contenuti sono generati da modelli di intelligenza artificiale forniti da terzi: Claude (Anthropic) per l'analisi dell'account, l'analisi e la generazione di script e la libreria, e Gemini (Google) per l'analisi dei video. Si basano sui dati che fornisci, su dati effettivamente ottenuti tramite l'API ufficiale di TikTok o su ricerche web."),
        ]),
        ("2. Età minima, accesso e account", [
            ("p", "<strong>Età minima.</strong> Il Servizio è riservato a persone di almeno 18 anni. Utilizzando il Servizio dichiari di avere almeno 18 anni. Se hai meno di 18 anni, non puoi utilizzare il Servizio e, in particolare, non puoi importare video o script da analizzare. Se veniamo a sapere che un utente ha meno di 18 anni, potremo sospenderne l'accesso ed eliminarne i dati."),
            ("p", "Le funzioni di analisi dell'account richiedono l'accesso tramite il Login Kit ufficiale di TikTok (protocollo OAuth). Wil App non possiede né richiede mai la tua password di TikTok. Puoi revocare in qualsiasi momento l'autorizzazione concessa a Wil App dalle impostazioni delle connessioni di terze parti del tuo account TikTok."),
            ("p", "L'accesso alle funzioni a pagamento è collegato al tuo account Whop, identificato dall'indirizzo e-mail usato al momento del pagamento. Sei responsabile della riservatezza del tuo account Whop."),
        ]),
        ("3. Contenuti che importi", [
            ("p", "Quando importi un file video o il testo di uno script da analizzare, garantisci che:"),
            ("ul", [
                "possiedi i diritti su tale contenuto o disponi delle autorizzazioni necessarie per utilizzarlo (anche per il contenuto di un altro creator, purché tu lo abbia ottenuto lecitamente, mai tramite estrazione automatizzata a partire da un semplice link);",
                "tale contenuto non viola alcuna legge, alcun diritto di terzi né le linee guida della community di TikTok.",
            ]),
            ("p", "Wil App non raccoglie, scarica né estrae alcun video direttamente da TikTok all'insaputa dell'utente: ogni file o testo analizzato è fornito volontariamente da te."),
            ("p", "Per essere analizzato, il file video viene inviato a Google (API Gemini), che ne analizza le immagini e l'audio; il testo di uno script viene inviato ad Anthropic (Claude). Wil App non conserva il tuo file video dopo l'analisi, ma conserva il report generato, come descritto nella nostra Informativa sulla privacy. Questi fornitori trattano i dati secondo le proprie condizioni. I tuoi video e script non vengono utilizzati per alimentare i contenuti mostrati ad altri utenti."),
        ]),
        ("4. Uso consentito", [
            ("p", "Ti impegni a utilizzare il Servizio esclusivamente per scopi personali e leciti e a non:"),
            ("ul", [
                "tentare di aggirare i limiti tecnici del Servizio (ad esempio il limite di parole per l'analisi degli script o i limiti di frequenza delle richieste);",
                "utilizzare il Servizio per reverse engineering, rivendita o estrazione automatizzata massiva dei report generati;",
                "utilizzare il Servizio per analizzare contenuti su cui non hai diritti di utilizzo;",
                "condividere con terzi il tuo accesso a pagamento.",
            ]),
        ]),
        ("5. Offerta gratuita, abbonamento e pagamento", [
            ("p", "<strong>Offerta gratuita.</strong> Il Servizio ti consente di provare gratuitamente un'analisi video e un'analisi dell'account TikTok; il report completo di queste analisi e le altre funzioni sono riservati agli abbonati."),
            ("p", "<strong>Abbonamento.</strong> L'accesso completo al Servizio è offerto in abbonamento, mensile o annuale. Le funzioni incluse, i prezzi e il periodo di fatturazione sono indicati nella pagina Prezzi e nella pagina di pagamento prima dell'acquisto. Le imposte applicabili nel tuo paese sono indicate nella pagina di pagamento. L'abbonamento è soggetto a un uso ragionevole; possono applicarsi limiti tecnici di frequenza per proteggere il Servizio."),
            ("p", "<strong>Pagamento.</strong> I pagamenti sono elaborati da Whop (whop.com), un fornitore terzo, secondo le sue condizioni. L'Editore non riceve né conserva i dati della tua carta. A seconda dei casi, Whop può agire come venditore dell'abbonamento o semplicemente come fornitore di servizi di pagamento; il venditore e il prezzo totale, imposte incluse, sono indicati nella pagina di pagamento."),
            ("p", "<strong>Rinnovo.</strong> L'abbonamento si rinnova automaticamente alla fine di ogni periodo (mensile o annuale), al prezzo vigente, fino a quando non lo disdici. L'Editore può modificare i propri prezzi: qualsiasi aumento si applica a partire dal periodo successivo, previo ragionevole preavviso (via e-mail o nell'app), e puoi disdire prima che entri in vigore."),
        ]),
        ("6. Disdetta e rimborso", [
            ("p", "<strong>Disdetta.</strong> Puoi disdire il tuo abbonamento in qualsiasi momento, da Impostazioni &gt; Gestisci l'abbonamento (un link alla tua area Whop) oppure scrivendoci. La disdetta ha effetto alla fine del periodo già pagato: conservi l'accesso fino a tale data e non viene effettuato alcun ulteriore addebito. Il periodo in corso non è rimborsato, fatta salva la regola seguente."),
            ("p", "<strong>Rimborso entro 14 giorni.</strong> Puoi chiedere il rimborso del tuo abbonamento entro 14 giorni dall'acquisto, a condizione che con tale abbonamento <strong>non sia stata effettuata alcuna analisi</strong> (video, account TikTok o script). Per farlo, scrivici (sezione 15) indicando l'indirizzo e-mail usato per l'acquisto. Il rimborso avviene sul metodo di pagamento originale, tramite il nostro fornitore di pagamenti."),
            ("p", "Una volta effettuata un'analisi, il servizio digitale si considera reso e l'importo pagato non è più rimborsabile, salvo diversa disposizione di legge. Questa regola non limita i diritti inderogabili che ti riconosce la legge del tuo paese di residenza, compreso il diritto di recesso applicabile ai consumatori dell'Unione europea. L'accesso al Servizio inizia immediatamente dopo il tuo pagamento."),
        ]),
        ("7. Natura delle analisi fornite", [
            ("p", "I punteggi, le diagnosi, i consigli e le stime forniti da Wil App (compresi il punteggio di viralità, le fasce di visualizzazioni, like o commenti e il «potenziale di viralità» delle idee giornaliere) sono generati automaticamente dall'intelligenza artificiale a partire dai dati disponibili. Sono stime, non previsioni: costituiscono un supporto decisionale e non garantiscono in alcun modo un risultato (più visualizzazioni, follower o guadagni). Wil App non può essere ritenuta responsabile delle decisioni prese sulla base di tali analisi."),
        ]),
        ("8. Proprietà intellettuale", [
            ("p", "L'applicazione, il suo marchio, il suo design e il suo codice restano di esclusiva proprietà dell'Editore. I report generati per il tuo account ti sono forniti per uso personale; ne conservi il contenuto, senza che ciò comporti la cessione di alcun diritto sulla piattaforma stessa."),
        ]),
        ("9. Disponibilità ed evoluzione del servizio", [
            ("p", "Wil App è un progetto in sviluppo attivo. Alcune funzioni possono essere aggiunte, modificate o temporaneamente rimosse. Ci impegniamo a mantenere il Servizio in funzione ma non garantiamo una disponibilità ininterrotta. Se una funzione inclusa nel tuo abbonamento viene rimossa in via definitiva, potrai disdire l'abbonamento e chiedere il rimborso della parte non utilizzata del periodo in corso."),
        ]),
        ("10. Limitazione di responsabilità", [
            ("p", "Il Servizio è fornito «così com'è». Wil App non è affiliata, sponsorizzata né approvata da TikTok o da ByteDance Ltd. Nei limiti consentiti dalla legge, l'Editore declina ogni responsabilità per i danni indiretti derivanti dall'uso del Servizio. Nulla nei presenti Termini esclude una responsabilità che non possa essere esclusa ai sensi della legge applicabile."),
        ]),
        ("11. Cessazione e sospensione", [
            ("p", "Puoi smettere di utilizzare il Servizio in qualsiasi momento, revocando l'accesso dalle impostazioni del tuo account TikTok o eliminando il tuo account da Impostazioni &gt; Elimina il mio account (ciò elimina i tuoi dati, come descritto nella nostra Informativa sulla privacy). L'eliminazione dell'account non disdice di per sé un abbonamento a pagamento in corso: disdicilo separatamente (sezione 6). L'Editore si riserva il diritto di sospendere l'accesso di un utente in caso di abuso o di violazione dei presenti Termini."),
        ]),
        ("12. Modifica dei presenti Termini", [
            ("p", "I presenti Termini possono essere aggiornati. In caso di modifica rilevante, in particolare dei prezzi o delle regole di rimborso, sarai informato via e-mail o nell'app prima della sua entrata in vigore. L'uso continuato del Servizio dopo una modifica costituisce accettazione dei nuovi termini."),
        ]),
        ("13. Legge applicabile", [
            ("p", "I presenti Termini sono disciplinati dalla legge applicabile nel luogo di residenza dell'Editore, fatte salve le norme imperative a tutela dei consumatori del tuo paese di residenza."),
        ]),
        ("14. Traduzioni", [
            ("p", "I presenti Termini sono offerti in più lingue per tua comodità. In caso di discrepanza, prevale la versione francese."),
        ]),
        ("15. Contatti", [
            ("p", "Per qualsiasi domanda sui presenti Termini, sul tuo abbonamento o per una richiesta di rimborso, contattaci all'indirizzo {EMAIL} o tramite {WHATSAPP}."),
        ]),
    ],
}

PRIVACY = {
    "title": "Informativa sulla privacy",
    "updated": "Ultimo aggiornamento: ottobre 2026",
    "prevails": "",
    "back_home": "← Torna alla home",
    "back_settings": "← Torna alle impostazioni",
    "see_also": "Vedi anche i nostri Termini di servizio →",
    "footer": "Wil App — Informativa sulla privacy",
    "intro": "La presente Informativa sulla privacy spiega come Wil App («noi») raccoglie, utilizza e protegge le informazioni quando utilizzi il nostro Servizio. Wil App è gestita da una persona fisica che agisce a titolo personale, titolare del trattamento dei dati, contattabile ai recapiti indicati nella sezione 12.",
    "sections": [
        ("1. Informazioni che raccogliamo", [
            ("p", "<strong>Account TikTok.</strong> Quando colleghi il tuo account TikTok tramite il Login Kit ufficiale di TikTok, possiamo ricevere, solo con la tua esplicita autorizzazione:"),
            ("ul", [
                "informazioni di base del profilo (nome utente, nome visualizzato, foto del profilo);",
                "contenuti pubblici e metadati dei video associati al tuo account.",
            ]),
            ("p", "Non accediamo ai messaggi privati, alle informazioni di pagamento né ad alcun dato oltre quanto consentito dalle autorizzazioni che concedi. Dal tuo account collegato conserviamo una sessione di accesso (il token è cifrato) e istantanee periodiche delle tue statistiche (tassi di engagement e di viralità), così da poter confrontare il tuo account con se stesso nel tempo."),
            ("p", "<strong>Account Whop e abbonamento.</strong> Per gestire gli abbonamenti utilizziamo Whop: riceviamo il tuo identificativo Whop, il tuo indirizzo e-mail e lo stato del tuo abbonamento (attivo o meno, piano). I pagamenti sono elaborati da Whop: non riceviamo né conserviamo i dati della tua carta."),
            ("p", "<strong>Video e script che fornisci.</strong> Quando carichi un video o incolli uno script da analizzare, questo viene inviato ai nostri fornitori di intelligenza artificiale (sezione 2) per generare il tuo report. Non conserviamo il tuo file video dopo l'analisi. Non utilizziamo i tuoi video o script per costruire i contenuti mostrati ad altri utenti."),
            ("p", "<strong>Report di analisi.</strong> Il report generato viene conservato sui nostri server con un identificativo casuale, senza collegamento diretto alla tua identità, in modo che tu possa ritrovarlo (ad esempio dopo aver aggiornato la pagina o sottoscritto un abbonamento). I report vengono eliminati automaticamente dopo 180 giorni."),
            ("p", "<strong>Riscontro sulle stime.</strong> Se ci indichi che un video è già stato pubblicato e rispondi se la nostra stima era vicina ai risultati reali, registriamo tale risposta in forma anonima (nicchia, punteggio, livello stimato e la tua risposta), senza il video e senza alcun identificativo."),
            ("p", "<strong>Dati conservati sul tuo dispositivo.</strong> Le tue risposte di onboarding, la cronologia delle analisi, gli elementi salvati, le scelte di lingua e di aspetto e una copia degli ultimi report sono memorizzati nel tuo browser (archiviazione locale), sul tuo dispositivo. Se colleghi TikTok, il tuo browser conserva anche il tuo profilo pubblico (nome, nome utente, foto) e un identificativo di sessione."),
            ("p", "<strong>Dati tecnici.</strong> Per proteggere il Servizio dagli abusi, utilizziamo temporaneamente il tuo indirizzo IP (limitazione della frequenza delle richieste); il nostro fornitore di hosting può conservare log tecnici per un periodo limitato."),
        ]),
        ("2. Trattamento tramite intelligenza artificiale", [
            ("p", "Per produrre le tue analisi, Wil App <strong>trasmette i contenuti che fornisci a fornitori esterni di intelligenza artificiale</strong>, che li trattano per analizzarli e classificarli. In concreto:"),
            ("ul", [
                "i tuoi <strong>video</strong> (immagini e audio) vengono inviati a Google (Gemini);",
                "i tuoi <strong>script</strong> vengono inviati ad Anthropic (Claude);",
                "le informazioni del tuo <strong>profilo TikTok</strong> (nome, nome utente, descrizione) e le statistiche dei tuoi video vengono inviate ad Anthropic (Claude);",
                "le <strong>idee di tendenza</strong> sono prodotte da Claude (Anthropic) a partire da ricerche web.",
            ]),
            ("p", "Questi invii avvengono solo quando avvii un'analisi. Sul sito, avviare un'analisi significa accettare questo invio; nella nostra app mobile viene mostrata una finestra di consenso prima della prima analisi, e puoi revocarlo in qualsiasi momento in Profilo. Questi fornitori sono aziende indipendenti: trattano i dati secondo le proprie condizioni e le proprie regole sulla privacy. Non vendiamo i tuoi contenuti e non li usiamo per creare i contenuti mostrati ad altri utenti. Se non vuoi che i tuoi contenuti vengano trasmessi a questi fornitori, non usare le funzioni di analisi."),
        ]),
        ("3. Come utilizziamo le tue informazioni", [
            ("p", "Utilizziamo queste informazioni esclusivamente per fornire il Servizio (analisi dell'account, analisi di video e script, tendenze, gestione del tuo abbonamento), mantenerlo sicuro e migliorarne l'affidabilità e la precisione delle nostre stime. Non vendiamo i tuoi dati personali a terzi."),
        ]),
        ("4. Basi giuridiche", [
            ("p", "A seconda dei casi, il trattamento si fonda sull'esecuzione del contratto (fornitura del Servizio e gestione del tuo abbonamento), sul tuo consenso (collegamento del tuo account TikTok, che puoi revocare in qualsiasi momento), sul nostro legittimo interesse (sicurezza, prevenzione degli abusi, miglioramento del Servizio) e sull'adempimento dei nostri obblighi legali (contabilità e pagamenti)."),
        ]),
        ("5. Conservazione e sicurezza", [
            ("p", "Adottiamo misure tecniche ragionevoli per proteggere le informazioni che conserviamo: i token di accesso di TikTok sono cifrati, le connessioni sono protette da HTTPS e l'accesso ai nostri database è limitato."),
            ("ul", [
                "Sessioni TikTok: al massimo 30 giorni, oppure fino a quando ti scolleghi o elimini il tuo account.",
                "Istantanee delle statistiche dell'account: fino all'eliminazione del tuo account.",
                "Report di analisi: 180 giorni.",
                "Dati di pagamento e fatturazione: conservati da Whop e, se del caso, da noi per il tempo richiesto dalla legge.",
            ]),
        ]),
        ("6. Servizi di terze parti", [
            ("p", "Il nostro Servizio si basa sui seguenti fornitori, ciascuno soggetto alle proprie condizioni e alla propria informativa sulla privacy:"),
            ("ul", [
                "TikTok (API ufficiali e Login Kit);",
                "Anthropic (Claude), che tratta i dati dell'account, gli script e le ricerche web utilizzate per generare report e tendenze;",
                "Google (API Gemini), che tratta i video che carichi per analizzarne immagini e audio;",
                "Whop, che tratta i pagamenti e l'accesso al tuo account Whop;",
                "Sentry, che riceve report tecnici degli errori del server (senza cookie, senza indirizzi e-mail e senza il contenuto dei tuoi video o script) per permetterci di correggere i guasti;",
                "i nostri fornitori di hosting, database e sicurezza di rete (Render, Supabase, Cloudflare), che memorizzano o trasmettono i dati descritti sopra.",
            ]),
            ("p", "L'uso di TikTok da parte tua resta soggetto all'informativa sulla privacy e ai termini propri di TikTok."),
        ]),
        ("7. Trasferimenti internazionali", [
            ("p", "Alcuni di questi fornitori hanno sede al di fuori del tuo paese, in particolare negli Stati Uniti. I tuoi dati possono quindi essere trasferiti e trattati in altri paesi, con le garanzie previste da tali fornitori e dalla legge applicabile."),
        ]),
        ("8. I tuoi diritti", [
            ("p", "Dalla schermata Impostazioni dell'app puoi in qualsiasi momento:"),
            ("ul", [
                "<strong>Scollegare TikTok</strong>: revochiamo il token di accesso ed eliminiamo la tua sessione, conservando la tua cronologia;",
                "<strong>Eliminare il tuo account</strong>: eliminiamo i dati memorizzati sul tuo dispositivo e, se TikTok era collegato, revochiamo l'accesso ed eliminiamo dai nostri server le tue sessioni e la cronologia delle statistiche. Questa azione è definitiva.",
            ]),
            ("p", "Puoi inoltre revocare l'accesso di Wil App dalle impostazioni del tuo account TikTok. In base alla legge applicabile (ad esempio il GDPR), hai inoltre il diritto di accesso, rettifica, cancellazione, limitazione, opposizione e portabilità, nonché il diritto di proporre reclamo all'autorità per la protezione dei dati del tuo paese. Per esercitare tali diritti, in particolare per i dati legati al tuo abbonamento o a un report specifico (indicane il link), contattaci: rispondiamo entro un mese."),
        ]),
        ("9. Cookie e archiviazione locale", [
            ("p", "Utilizziamo solo cookie strettamente necessari al funzionamento del Servizio, senza pubblicità né tracciamento: la tua scelta della lingua (1 anno), il contatore dell'analisi gratuita (1 anno), il tuo accesso Whop (30 giorni) e cookie temporanei durante l'accesso e il pagamento (da pochi minuti a 24 ore). L'archiviazione locale del tuo browser è utilizzata per le preferenze e la cronologia descritte nella sezione 1."),
        ]),
        ("10. Età minima", [
            ("p", "Il Servizio è destinato a persone di almeno 18 anni. Non raccogliamo consapevolmente informazioni da persone di età inferiore a 18 anni. Se ritieni che una persona di età inferiore a 18 anni abbia utilizzato il Servizio, contattaci ed elimineremo i dati corrispondenti."),
        ]),
        ("11. Modifiche", [
            ("p", "Possiamo aggiornare la presente Informativa di tanto in tanto. In caso di modifica rilevante, ti informeremo nell'app. L'uso continuato del Servizio dopo una modifica costituisce accettazione dell'informativa aggiornata. In caso di discrepanza tra le traduzioni, prevale la versione francese."),
        ]),
        ("12. Contatti", [
            ("p", "Domande? Contattaci all'indirizzo {EMAIL} o tramite {WHATSAPP}."),
        ]),
    ],
}
