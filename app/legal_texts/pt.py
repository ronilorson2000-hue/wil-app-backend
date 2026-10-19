"""Tradução para português dos textos legais (em caso de divergência, prevalece a versão francesa). Ver fr.py."""

TERMS = {
    "title": "Termos de serviço",
    "updated": "Última atualização: outubro de 2026",
    "prevails": "",
    "back_home": "← Voltar ao início",
    "back_settings": "← Voltar às configurações",
    "see_also": "Veja também a nossa Política de privacidade →",
    "footer": "Wil App — Termos de serviço",
    "intro": "Estes Termos de serviço (os \"Termos\") regem o acesso e a utilização da aplicação Wil App (o \"Serviço\"), disponível em wilapp.tech e operada por uma pessoa singular que atua a título pessoal (o \"Editor\"), contactável através dos dados da seção 15. Ao utilizar o Serviço ou subscrever um plano, você aceita integralmente estes Termos.",
    "sections": [
        ("1. Objeto e descrição do serviço", [
            ("p", "O Wil App é uma ferramenta de análise com inteligência artificial para criadores de conteúdo do TikTok. Entre outras coisas, o Serviço permite:"),
            ("ul", [
                "conectar a sua conta do TikTok para obter um diagnóstico automático (pontuação de viralidade, taxa de engajamento, pontos fortes, pontos a melhorar, hashtags sugeridas);",
                "analisar um vídeo (já publicado ou não) que você importe manualmente, com base no seu conteúdo visual e sonoro;",
                "analisar o roteiro de um vídeo que ainda não gravou, ou gerar um;",
                "consultar uma biblioteca e ideias diárias (ganchos, ideias de vídeo, hashtags) baseadas em pesquisas na web feitas por inteligência artificial, e guardar as que mais gostar.",
            ]),
            ("p", "Os relatórios e conteúdos são gerados por modelos de inteligência artificial de fornecedores externos: Claude (Anthropic) para a análise de conta, a análise e geração de roteiros e a biblioteca, e Gemini (Google) para a análise de vídeo. Baseiam-se nos dados que você fornece, em dados efetivamente obtidos através da API oficial do TikTok ou em pesquisas na web."),
        ]),
        ("2. Idade mínima, login e acesso à conta", [
            ("p", "<strong>Idade mínima.</strong> O Serviço é reservado a pessoas com 18 anos ou mais. Ao utilizar o Serviço, você declara ter pelo menos 18 anos. Se tiver menos de 18 anos, não pode utilizar o Serviço, nomeadamente importar vídeos ou roteiros para análise. Se tomarmos conhecimento de que um utilizador tem menos de 18 anos, poderemos suspender o seu acesso e eliminar os seus dados."),
            ("p", "As funcionalidades de análise de conta exigem o login através do Login Kit oficial do TikTok (protocolo OAuth). O Wil App nunca tem nem solicita a sua palavra-passe do TikTok. Você pode revogar a qualquer momento a autorização concedida ao Wil App nas configurações de ligações de terceiros da sua conta do TikTok."),
            ("p", "O acesso às funcionalidades pagas está associado à sua conta Whop, identificada pelo endereço de e-mail usado no pagamento. Você é responsável pela confidencialidade da sua conta Whop."),
        ]),
        ("3. Conteúdo que você importa", [
            ("p", "Quando importa um ficheiro de vídeo ou o texto de um roteiro para análise, você garante que:"),
            ("ul", [
                "detém os direitos sobre esse conteúdo ou tem as autorizações necessárias para o utilizar (incluindo o conteúdo de outro criador, desde que o tenha obtido de forma lícita, nunca por extração automatizada a partir de um simples link);",
                "esse conteúdo não viola nenhuma lei, nenhum direito de terceiros nem as diretrizes da comunidade do TikTok.",
            ]),
            ("p", "O Wil App não recolhe, descarrega nem extrai qualquer vídeo diretamente do TikTok sem o conhecimento do utilizador: cada ficheiro ou texto analisado é fornecido voluntariamente por você."),
            ("p", "Para ser analisado, o ficheiro de vídeo é enviado à Google (API Gemini), que analisa as suas imagens e o seu som; o texto de um roteiro é enviado à Anthropic (Claude). O Wil App não guarda o seu ficheiro de vídeo após a análise, mas guarda o relatório gerado, conforme descrito na nossa Política de privacidade. Estes fornecedores tratam os dados segundo as suas próprias condições. Os seus vídeos e roteiros não são usados para alimentar o conteúdo apresentado a outros utilizadores."),
        ]),
        ("4. Utilização permitida", [
            ("p", "Você compromete-se a utilizar o Serviço estritamente para fins pessoais e lícitos e a não:"),
            ("ul", [
                "tentar contornar os limites técnicos do Serviço (por exemplo, o limite de palavras na análise de roteiros ou os limites de frequência de pedidos);",
                "utilizar o Serviço para engenharia reversa, revenda ou extração automatizada em massa dos relatórios gerados;",
                "utilizar o Serviço para analisar conteúdo sobre o qual não tenha direitos de utilização;",
                "partilhar o seu acesso pago com terceiros.",
            ]),
        ]),
        ("5. Oferta gratuita, subscrição e pagamento", [
            ("p", "<strong>Oferta gratuita.</strong> O Serviço permite experimentar gratuitamente uma análise de vídeo e uma análise de conta do TikTok; o relatório completo dessas análises e as restantes funcionalidades estão reservados aos subscritores."),
            ("p", "<strong>Subscrição.</strong> O acesso completo ao Serviço é oferecido por subscrição, mensal ou anual. As funcionalidades incluídas, os preços e o período de faturação são apresentados na página de Preços e na página de pagamento antes da compra. Os impostos aplicáveis no seu país são indicados na página de pagamento. A subscrição está sujeita a utilização razoável; podem aplicar-se limites técnicos de frequência para proteger o Serviço."),
            ("p", "<strong>Pagamento.</strong> Os pagamentos são processados pela Whop (whop.com), um fornecedor externo, de acordo com as suas próprias condições. O Editor não recebe nem guarda os dados do seu cartão. Consoante o caso, a Whop pode atuar como vendedora da subscrição ou apenas como fornecedora de pagamentos; o vendedor e o preço total, impostos incluídos, são indicados na página de pagamento."),
            ("p", "<strong>Renovação.</strong> A subscrição renova-se automaticamente no final de cada período (mensal ou anual), ao preço em vigor, até que você a cancele. O Editor pode alterar os seus preços: qualquer aumento aplica-se a partir do período seguinte, mediante pré-aviso razoável (por e-mail ou na aplicação), e você pode cancelar antes de este entrar em vigor."),
        ]),
        ("6. Cancelamento e reembolso", [
            ("p", "<strong>Cancelamento.</strong> Você pode cancelar a sua subscrição a qualquer momento, em Configurações &gt; Gerir a subscrição (um link para a sua área Whop) ou escrevendo-nos. O cancelamento produz efeito no final do período já pago: mantém o acesso até essa data e não é efetuada nenhuma cobrança adicional. O período em curso não é reembolsado, sem prejuízo da regra seguinte."),
            ("p", "<strong>Reembolso em 14 dias.</strong> Você pode pedir o reembolso da sua subscrição nos 14 dias seguintes à compra, desde que <strong>nenhuma análise</strong> (vídeo, conta do TikTok ou roteiro) tenha sido realizada com essa subscrição. Para tal, escreva-nos (seção 15) indicando o endereço de e-mail usado na compra. O reembolso é feito para o meio de pagamento original, através do nosso fornecedor de pagamentos."),
            ("p", "Assim que uma análise é realizada, o serviço digital considera-se prestado e o valor pago deixa de ser reembolsável, salvo se a lei exigir o contrário. Esta regra não limita os direitos imperativos que a lei do seu país de residência lhe confere, incluindo o direito de livre resolução aplicável aos consumidores da União Europeia. O acesso ao Serviço começa imediatamente após o seu pagamento."),
        ]),
        ("7. Natureza das análises fornecidas", [
            ("p", "As pontuações, diagnósticos, conselhos e estimativas fornecidos pelo Wil App (incluindo a pontuação de viralidade, as faixas de visualizações, curtidas ou comentários e o \"potencial de viralidade\" das ideias diárias) são gerados automaticamente por inteligência artificial a partir dos dados disponíveis. São estimativas, não previsões: constituem uma ajuda à decisão e não garantem de modo algum um resultado (mais visualizações, seguidores ou rendimentos). O Wil App não pode ser responsabilizado por decisões tomadas com base nestas análises."),
        ]),
        ("8. Propriedade intelectual", [
            ("p", "A aplicação, a sua marca, o seu design e o seu código permanecem propriedade exclusiva do Editor. Os relatórios gerados para a sua conta são fornecidos para uso pessoal; você mantém o respetivo conteúdo, sem que isso implique a cedência de qualquer direito sobre a própria plataforma."),
        ]),
        ("9. Disponibilidade e evolução do serviço", [
            ("p", "O Wil App é um projeto em desenvolvimento ativo. Algumas funcionalidades podem ser adicionadas, alteradas ou temporariamente retiradas. Esforçamo-nos por manter o Serviço em funcionamento, mas não garantimos disponibilidade ininterrupta. Se uma funcionalidade incluída na sua subscrição for retirada definitivamente, poderá cancelar a subscrição e pedir o reembolso da parte não utilizada do período em curso."),
        ]),
        ("10. Limitação de responsabilidade", [
            ("p", "O Serviço é fornecido \"tal como está\". O Wil App não é afiliado, patrocinado nem apoiado pelo TikTok ou pela ByteDance Ltd. Na medida permitida por lei, o Editor declina qualquer responsabilidade por danos indiretos resultantes da utilização do Serviço. Nada nestes Termos exclui uma responsabilidade que não possa ser excluída nos termos da lei aplicável."),
        ]),
        ("11. Cessação e suspensão", [
            ("p", "Você pode deixar de utilizar o Serviço a qualquer momento, revogando o acesso nas configurações da sua conta do TikTok ou eliminando a sua conta em Configurações &gt; Eliminar a minha conta (o que elimina os seus dados, conforme descrito na nossa Política de privacidade). Eliminar a conta não cancela, por si só, uma subscrição paga em curso: cancele-a separadamente (seção 6). O Editor reserva-se o direito de suspender o acesso de um utilizador em caso de abuso ou de incumprimento destes Termos."),
        ]),
        ("12. Alteração destes Termos", [
            ("p", "Estes Termos podem ser atualizados. Em caso de alteração significativa, nomeadamente dos preços ou das regras de reembolso, você será informado por e-mail ou na aplicação antes da sua entrada em vigor. A utilização continuada do Serviço após uma alteração constitui aceitação dos novos termos."),
        ]),
        ("13. Lei aplicável", [
            ("p", "Estes Termos são regidos pela lei aplicável no local de residência do Editor, sem prejuízo das normas imperativas de proteção do consumidor do seu país de residência."),
        ]),
        ("14. Traduções", [
            ("p", "Estes Termos são disponibilizados em vários idiomas para sua comodidade. Em caso de divergência, prevalece a versão francesa."),
        ]),
        ("15. Contacto", [
            ("p", "Para qualquer questão sobre estes Termos, a sua subscrição ou um pedido de reembolso, contacte-nos em {EMAIL} ou através de {WHATSAPP}."),
        ]),
    ],
}

PRIVACY = {
    "title": "Política de privacidade",
    "updated": "Última atualização: outubro de 2026",
    "prevails": "",
    "back_home": "← Voltar ao início",
    "back_settings": "← Voltar às configurações",
    "see_also": "Veja também os nossos Termos de serviço →",
    "footer": "Wil App — Política de privacidade",
    "intro": "Esta Política de privacidade explica como o Wil App (\"nós\") recolhe, utiliza e protege as informações quando você utiliza o nosso Serviço. O Wil App é operado por uma pessoa singular que atua a título pessoal, responsável pelo tratamento dos dados, contactável através dos dados da seção 12.",
    "sections": [
        ("1. Informações que recolhemos", [
            ("p", "<strong>Conta do TikTok.</strong> Quando você conecta a sua conta do TikTok através do Login Kit oficial do TikTok, podemos receber, apenas com a sua autorização explícita:"),
            ("ul", [
                "informações básicas do perfil (nome de utilizador, nome de exibição, foto de perfil);",
                "conteúdo público e metadados dos vídeos associados à sua conta.",
            ]),
            ("p", "Não acedemos a mensagens privadas, a informações de pagamento nem a quaisquer dados além do que as autorizações concedidas permitem. Da sua conta conectada guardamos uma sessão de acesso (o token é cifrado) e capturas periódicas das suas estatísticas (taxas de engajamento e de viralidade), para podermos comparar a sua conta consigo mesma ao longo do tempo."),
            ("p", "<strong>Conta Whop e subscrição.</strong> Para gerir as subscrições utilizamos a Whop: recebemos o seu identificador Whop, o seu endereço de e-mail e o estado da sua subscrição (ativa ou não, plano). Os pagamentos são processados pela Whop: não recebemos nem guardamos os dados do seu cartão."),
            ("p", "<strong>Vídeos e roteiros que você fornece.</strong> Quando carrega um vídeo ou cola um roteiro para análise, este é enviado aos nossos fornecedores de inteligência artificial (seção 2) para gerar o seu relatório. Não guardamos o seu ficheiro de vídeo após a análise. Não utilizamos os seus vídeos ou roteiros para construir o conteúdo apresentado a outros utilizadores."),
            ("p", "<strong>Relatórios de análise.</strong> O relatório gerado é guardado nos nossos servidores sob um identificador aleatório, sem ligação direta à sua identidade, para que possa voltar a encontrá-lo (por exemplo, após atualizar a página ou subscrever). Os relatórios são eliminados automaticamente após 180 dias."),
            ("p", "<strong>Feedback sobre as estimativas.</strong> Se nos indicar que um vídeo já foi publicado e responder se a nossa estimativa se aproximou dos resultados reais, registamos essa resposta de forma anónima (nicho, pontuação, nível estimado e a sua resposta), sem o vídeo e sem qualquer identificador."),
            ("p", "<strong>Dados guardados no seu dispositivo.</strong> As suas respostas de integração, o seu histórico de análises, os itens guardados, as suas escolhas de idioma e aparência e uma cópia dos seus últimos relatórios são armazenados no seu navegador (armazenamento local), no seu dispositivo. Se conectar o TikTok, o seu navegador guarda também o seu perfil público (nome, utilizador, foto) e um identificador de sessão."),
            ("p", "<strong>Dados técnicos.</strong> Para proteger o Serviço contra abusos, utilizamos temporariamente o seu endereço IP (limitação da frequência de pedidos); o nosso fornecedor de alojamento pode conservar registos técnicos por um período limitado."),
        ]),
        ("2. Tratamento por inteligência artificial", [
            ("p", "Para produzir as suas análises, o Wil App <strong>transmite o conteúdo que você fornece a fornecedores externos de inteligência artificial</strong>, que o tratam para o analisar e classificar. Concretamente:"),
            ("ul", [
                "os seus <strong>vídeos</strong> (imagens e som) são enviados à Google (Gemini);",
                "os seus <strong>roteiros</strong> são enviados à Anthropic (Claude);",
                "as informações do seu <strong>perfil do TikTok</strong> (nome, nome de utilizador, descrição) e as estatísticas dos seus vídeos são enviadas à Anthropic (Claude);",
                "as <strong>ideias em tendência</strong> são produzidas pelo Claude (Anthropic) a partir de pesquisas na web.",
            ]),
            ("p", "Estes envios só acontecem quando inicia uma análise. No site, iniciar uma análise significa aceitar este envio; na nossa aplicação móvel é apresentada uma janela de consentimento antes da primeira análise, e pode retirá-lo a qualquer momento em Perfil. Estes fornecedores são empresas independentes: tratam os dados segundo as suas próprias condições e regras de privacidade. Não vendemos os seus conteúdos nem os utilizamos para criar os conteúdos mostrados a outros utilizadores. Se não quiser que o seu conteúdo seja transmitido a estes fornecedores, não utilize as funcionalidades de análise."),
        ]),
        ("3. Como utilizamos as suas informações", [
            ("p", "Utilizamos estas informações exclusivamente para fornecer o Serviço (análise de conta, análise de vídeo e de roteiros, tendências, gestão da sua subscrição), mantê-lo seguro e melhorar a sua fiabilidade e a precisão das nossas estimativas. Não vendemos os seus dados pessoais a terceiros."),
        ]),
        ("4. Bases jurídicas", [
            ("p", "Consoante o caso, o tratamento baseia-se na execução do contrato (fornecimento do Serviço e gestão da sua subscrição), no seu consentimento (ligação da sua conta do TikTok, que pode retirar a qualquer momento), no nosso interesse legítimo (segurança, prevenção de abusos, melhoria do Serviço) e no cumprimento das nossas obrigações legais (contabilidade e pagamentos)."),
        ]),
        ("5. Conservação e segurança", [
            ("p", "Tomamos medidas técnicas razoáveis para proteger as informações que guardamos: os tokens de acesso do TikTok são cifrados, as ligações são protegidas por HTTPS e o acesso às nossas bases de dados é restrito."),
            ("ul", [
                "Sessões do TikTok: no máximo 30 dias, ou até se desconectar ou eliminar a sua conta.",
                "Capturas das estatísticas da conta: até à eliminação da sua conta.",
                "Relatórios de análise: 180 dias.",
                "Dados de pagamento e faturação: conservados pela Whop e, se aplicável, por nós durante o tempo que a lei exigir.",
            ]),
        ]),
        ("6. Serviços de terceiros", [
            ("p", "O nosso Serviço assenta nos seguintes fornecedores, cada um sujeito às suas próprias condições e política de privacidade:"),
            ("ul", [
                "TikTok (APIs oficiais e Login Kit);",
                "Anthropic (Claude), que trata os dados da conta, os roteiros e as pesquisas na web usadas para gerar relatórios e tendências;",
                "Google (API Gemini), que trata os vídeos que você carrega para analisar as suas imagens e o seu som;",
                "Whop, que trata os pagamentos e o login na sua conta Whop;",
                "a Sentry, que recebe relatórios técnicos de erros do servidor (sem cookies, sem endereços de e-mail e sem o conteúdo dos seus vídeos ou roteiros) para podermos corrigir avarias;",
                "os nossos fornecedores de alojamento, base de dados e segurança de rede (Render, Supabase, Cloudflare), que armazenam ou transmitem os dados descritos acima.",
            ]),
            ("p", "A sua utilização do TikTok continua sujeita à política de privacidade e aos termos do próprio TikTok."),
        ]),
        ("7. Transferências internacionais", [
            ("p", "Alguns destes fornecedores estão localizados fora do seu país, nomeadamente nos Estados Unidos. Os seus dados podem, portanto, ser transferidos e tratados noutros países, com as garantias previstas por esses fornecedores e pela lei aplicável."),
        ]),
        ("8. Os seus direitos", [
            ("p", "No ecrã Configurações da aplicação, pode a qualquer momento:"),
            ("ul", [
                "<strong>Desconectar o TikTok</strong>: revogamos o token de acesso e eliminamos a sua sessão, mantendo o seu histórico;",
                "<strong>Eliminar a sua conta</strong>: eliminamos os dados armazenados no seu dispositivo e, se o TikTok estava conectado, revogamos o acesso e eliminamos dos nossos servidores as suas sessões e o histórico de estatísticas. Esta ação é definitiva.",
            ]),
            ("p", "Pode também revogar o acesso do Wil App nas configurações da sua conta do TikTok. Nos termos da lei aplicável (por exemplo, o RGPD), tem ainda direito de acesso, retificação, apagamento, limitação, oposição e portabilidade, bem como o direito de apresentar reclamação à autoridade de proteção de dados do seu país. Para exercer estes direitos, nomeadamente sobre dados ligados à sua subscrição ou a um relatório específico (indique o respetivo link), contacte-nos: respondemos no prazo de um mês."),
        ]),
        ("9. Cookies e armazenamento local", [
            ("p", "Utilizamos apenas cookies estritamente necessários ao funcionamento do Serviço, sem publicidade nem rastreamento: a sua escolha de idioma (1 ano), o contador de análise gratuita (1 ano), o seu login Whop (30 dias) e cookies temporários durante o login e o pagamento (de alguns minutos a 24 horas). O armazenamento local do seu navegador é usado para as preferências e o histórico descritos na seção 1."),
        ]),
        ("10. Idade mínima", [
            ("p", "O Serviço destina-se a pessoas com 18 anos ou mais. Não recolhemos conscientemente informações de menores de 18 anos. Se acreditar que uma pessoa com menos de 18 anos utilizou o Serviço, contacte-nos e eliminaremos os dados correspondentes."),
        ]),
        ("11. Alterações", [
            ("p", "Podemos atualizar esta Política de tempos a tempos. Em caso de alteração significativa, informá-lo-emos na aplicação. A utilização continuada do Serviço após uma alteração constitui aceitação da política atualizada. Em caso de divergência entre as traduções, prevalece a versão francesa."),
        ]),
        ("12. Contacto", [
            ("p", "Dúvidas? Contacte-nos em {EMAIL} ou através de {WHATSAPP}."),
        ]),
    ],
}
