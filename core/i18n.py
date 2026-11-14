"""Interface strings translated to Portuguese (PT-BR).

Usage::

    from core.i18n import t
    label = t("LISTENING")

Strings that have no entry here fall back to the English original.
"""

# ---------------------------------------------------------------------------
# States / status labels
# ---------------------------------------------------------------------------
_STATES = {
    "LISTENING": "OUVINDO",
    "SPEAKING": "FALANDO",
    "SLEEPING": "DORMINDO",
    "MUTED": "MUDO",
    "THINKING": "PENSANDO",
    "PROCESSING": "PROCESSANDO",
}

# ---------------------------------------------------------------------------
# UI labels / buttons / headers
# ---------------------------------------------------------------------------
_UI = {
    # Header
    "Settings & Controls": "Configurações e Controles",
    "Setup — things you set once": "Configuração — itens que você define uma vez",
    "Controls — the everyday switches": "Controles — interruptores do dia a dia",
    "A Friendly Assistant": "Um Assistente Amigável",
    "Personal AI Assistant": "Assistente Pessoal de IA",
    "Just A Rather Very Intelligent System": "Sistema de Inteligência Artificial",

    # Left panel
    "◈ SYS MONITOR": "◈ MONITOR DO SISTEMA",
    "AI CORE\nACTIVE": "NÚCLEO IA\nATIVO",
    "SEC\nCLEARED": "SEG\nLIBERADO",
    "ACTIVITY LOG": "LOG DE ATIVIDADE",
    "FILE UPLOAD": "ENVIO DE ARQUIVO",
    "No file loaded — drop or click above to upload": "Nenhum arquivo carregado — solte ou clique acima para enviar",
    "COMMAND INPUT": "ENTRADA DE COMANDO",
    "Type a command or question…": "Digite um comando ou pergunta…",
    "INTERRUPT": "INTERROMPER",
    "MICROPHONE ACTIVE": "MICROFONE ATIVO",
    "MICROPHONE MUTED": "MICROFONE MUDO",
    "REMOTE CONTROL": "CONTROLE REMOTO",
    "CREATE DESKTOP SHORTCUT": "CRIAR ATALHO NA ÁREA DE TRABALHO",
    "AUTO-START: OFF": "INICIAR AUTOMATICAMENTE: DESLIGADO",
    "AUTO-START: ON": "INICIAR AUTOMATICAMENTE: LIGADO",
    "CUSTOMISE ASSISTANT": "PERSONALIZAR ASSISTENTE",
    "AUDIO DEVICES": "DISPOSITIVOS DE ÁUDIO",
    "MEMORY": "MEMÓRIA",
    "PLUGINS": "PLUGINS",
    "PLUGIN SETTINGS": "CONFIGURAÇÕES DE PLUGINS",
    "FULLSCREEN": "TELA CHEIA",
    "WAKE WORD": "PALAVRA DE ATIVAÇÃO",
    "MORNING BRIEF": "RESUMO MATUTINO",
    "DOWNLOAD": "BAIXAR",
    "SLEEP NOW": "DORMIR AGORA",
    "WAKE NOW": "ACORDAR AGORA",
    "PUSH-TO-TALK": "PRESSIONE PARA FALAR",
    "HUD: ANIMATED FACE": "HUD: ROSTO ANIMADO",
    "HUD: REACTOR CORE": "HUD: NÚCLEO DO REATOR",

    # Right panel / buttons
    "✋  INTERRUPT  [ESC]": "✋  INTERRUPÇÃO  [ESC]",
    "🎙  MICROPHONE ACTIVE": "🎙  MICROFONE ATIVO",
    "🔇  MICROPHONE MUTED": "🔇  MICROFONE MUDO",

    # Quick drawer (setup)
    "◈ SETUP": "◈ CONFIGURAÇÃO",
    "◉  REMOTE CONTROL": "◉  CONTROLE REMOTO",
    "⊞  CREATE DESKTOP SHORTCUT": "⊞  CRIAR ATALHO NA ÁREA DE TRABALHO",
    "◉  AUTO-START: OFF": "◉  INICIAR AUTOMATICAMENTE: DESLIGADO",
    "⚙  CUSTOMISE ASSISTANT": "⚙  PERSONALIZAR ASSISTENTE",
    "🎧  AUDIO DEVICES": "🎧  DISPOSITIVOS DE ÁUDIO",
    "🧠  MEMORY": "🧠  MEMÓRIA",
    "🧩  PLUGINS": "🧩  PLUGINS",
    "⚙  PLUGIN SETTINGS": "⚙  CONFIGURAÇÕES DE PLUGINS",
    "🔌  ENGINE && PROVIDERS": "🔌  MOTOR E PROVEDORES",

    # Controls drawer
    "◈ CONTROLS": "◈ CONTROLES",
    "⛶  FULLSCREEN  [F11]": "⛶  TELA CHEIA  [F11]",
    "🎙  WAKE WORD": "🎙  PALAVRA DE ATIVAÇÃO",

    # Input row
    "▸": "▸",

    # Content panel
    "BRIEFING": "RESUMO MATUTINO",
    "DISMISS  ✕": "DESCARTAR  ✕",

    # Camera / video
    "◈  VISUAL INPUT": "◈  ENTRADA VISUAL",
    "✕": "✕",
    "◈  CAMERA FEED": "◈  FEED DA CÂMERA",
    "✕  CLOSE": "✕  FECHAR",
    "▶  VIDEO": "▶  VÍDEO",
    "🔇  SOUND OFF": "🔇  SOM DESLIGADO",
    "🔊  SOUND ON": "🔊  SOM LIGADO",

    # Setup overlay
    "◈  INITIALISATION REQUIRED": "◈  INICIALIZAÇÃO NECESSÁRIA",
    "Configure J.A.R.V.I.S. before first boot.": "Configure o J.A.R.V.I.S. antes da primeira inicialização.",
    "GEMINI API KEY": "CHAVE DA API GEMINI",
    "OPERATING SYSTEM": "SISTEMA OPERACIONAL",
    "Auto-detected:": "Detectado automaticamente:",
    "▸  INITIALISE SYSTEMS": "▸  INICIALIZAR SISTEMAS",

    # Clipboard
    "◈  CLIPBOARD DETECTED": "◈  ÁREA DE TRANSFERÊNCIA DETECTADA",

    # Memory
    "◈  WHAT JARVIS REMEMBERS": "◈  O QUE O JARVIS LEMBRA",
    "Nothing stored yet.": "Nada armazenado ainda.",
    "Forget this": "Esquecer isto",
    " stored facts — newest first. ": " fatos armazenados — mais recentes primeiro. ",
    "Nothing here is sent anywhere; it lives in ": "Nada disso é enviado; os dados ficam em ",

    # Providers panel
    "◈  ENGINE  &  PROVIDERS": "◈  MOTOR  E  PROVEDORES",
    "Choose what powers the conversation.": "Escolha o que alimenta a conversa.",
    "Gemini Live. Nothing on this panel changes the conversation.": "Gemini Live. Nada neste painel altera a conversa.",
    "② THINKING is not set — without it the assistant falls back ": "② PENSAMENTO não está definido — sem ele o assistente recai ",
    "to Gemini Live and says so in the log.": "para o Gemini Live e diz isso no log.",
    "Only ": "Apenas ",
    " is missing — it will run, but you will type ": " está faltando — ele vai rodar, mas você vai digitar ",
    " instead of speak, or read instead of listen.": " em vez de falar, ou ler em vez de ouvir.",
    "All three set. SAVE & APPLY reconnects; the conversation is kept.": "Os três estão definidos. SALVAR E APLICAR reconecta; a conversa é mantida.",
    "turns what you say into words": "transforma o que você diz em texto",
    "understands, decides, uses your tools": "entende, decide e usa suas ferramentas",
    "reads the answer out loud": "lê a resposta em voz alta",
    "★ recommended": "★ recomendado",
    "⚡  BACKGROUND REQUESTS": "⚡  SOLICITAÇÕES EM SEGUNDO PLANO",
    "🛠  CODING": "🛠  PROGRAMAÇÃO",
    "Reading a document, looking at your screen, writing code — the "
    "assistant's own requests, not the conversation. These use Gemini's "
    "text quota, which runs out before the voice does. Sending them "
    "somewhere else keeps them working, and changes nothing you hear.": "Ler "
    "documentos, analisar sua tela e escrever código são solicitações do "
    "assistente, não parte da conversa. Elas usam a cota de texto do Gemini, "
    "que pode acabar antes da cota de voz. Usar outro serviço para essas tarefas "
    "mantém tudo funcionando sem alterar o que você ouve.",
    "Fall back to": "Usar como alternativa:",
    "Code with": "Programar com",
    "Gemini only  —  the way it has always been": "Somente Gemini — como sempre",
    "Try Gemini first  —  faster": "Tentar o Gemini primeiro — mais rápido",
    "Try the other one first  —  keeps more on your machine": "Tentar o outro "
    "serviço primeiro — mantém mais dados no seu computador",
    "Uses the model you chose for ② THINKING.": "Usa o modelo escolhido para "
    "② PENSAMENTO.",
    "Left as it is, these keep using Gemini and stop working when "
    "its text quota runs out.": "Se mantidas assim, essas tarefas continuarão "
    "usando o Gemini e deixarão de funcionar quando a cota de texto acabar.",
    "The model that plans, writes and fixes projects when you ask the "
    "assistant to build something. Saved to Desktop/JarvisProjects.": "O modelo "
    "que planeja, escreve e corrige projetos quando você pede ao assistente "
    "para criar algo. Os projetos são salvos em Desktop/JarvisProjects.",
    "Same as background requests": "Igual às solicitações em segundo plano",
    "Code is written by whatever answers background requests above.": "O código "
    "será escrito pelo modelo selecionado acima para as solicitações em segundo plano.",
    "Uses the settings under BACKGROUND REQUESTS.": "Usa as configurações de "
    "SOLICITAÇÕES EM SEGUNDO PLANO.",
    "Needed — create one in your ": "Necessária — crie uma na sua conta de ",
    " (optional)": " (opcional)",
    "— default —": "— padrão —",
    "no": "não",
    "yes": "sim",
    "REFRESH": "ATUALIZAR",
    "↻ REFRESH": "↻ ATUALIZAR",
    "⌃ LESS": "⌃ MENOS",
    "⌄ MORE": "⌄ MAIS",
    "checking…": "verificando…",
    "Nothing to check for this one.": "Não há nada para verificar neste serviço.",
    "reading…": "carregando…",
    "Nothing to list for this one.": "Não há nada para listar neste serviço.",
    "None found.": "Nada encontrado.",
    "found.": "encontrado(s).",
    "installing ": "instalando ",
    " — this can take a minute…": " — isso pode levar um minuto…",
    "✓  installed — close and reopen this panel": "✓  instalado — feche e "
    "reabra este painel",
    "pip failed": "falha no pip",

    # Plugin manager
    "🧩  PLUGIN MANAGER": "🧩  GERENCIADOR DE PLUGINS",
    "No plugins found in /plugins.": "Nenhum plugin encontrado em /plugins.",
    "No configurable plugins are installed.\nDrop a plugin that needs "
    "settings (like the 3D-printer suite) into the plugins folder and "
    "it will show up here.": "Nenhum plugin configurável está instalado.\nAdicione "
    "à pasta de plugins um plugin que precise de configurações (como o conjunto "
    "de ferramentas para impressoras 3D) para que ele apareça aqui.",
    "CLOSE": "FECHAR",
    "BROKEN": "QUEBRADO",
    "ON": "LIGADO",
    "OFF": "DESLIGADO",

    # Confirm
    "⚠  CONFIRM": "⚠  CONFIRMAR",
    "▸  CONFIRM": "▸  CONFIRMAR",
    "CANCEL": "CANCELAR",

    # Audio devices
    "🎧  AUDIO DEVICES": "🎧  DISPOSITIVOS DE ÁUDIO",
    "TEST": "TESTAR",
    "OUTPUT VOLUME": "VOLUME DE SAÍDA",
    "Applying reconnects the session. Your conversation is kept.": "Ao aplicar, a sessão é reconectada. Sua conversa é mantida.",
    "▸  APPLY": "▸  APLICAR",
    "Speak now…": "Fale agora…",
    "Playing a tone…": "Tocando um tom…",

    # Remote key overlay
    "NEW KEY": "NOVA CHAVE",
    "DISMISS": "DESCARTAR",
    "Key expires in  {m:02d}:{s:02d}": "Chave expira em  {m:02d}:{s:02d}",
    "CONNECTED": "CONECTADO",
    "Phone connected — JARVIS ready": "Telefone conectado — JARVIS pronto",

    # System monitor labels
    "UP": "ATIVO",
    "PROC": "PROC",
    "CPU": "CPU",
    "MEM": "MEM",
    "NET": "REDE",
    "GPU": "GPU",
    "Mute": "Mudo",
    "Fullscreen": "Tela Cheia",
    "Dashboard not running — remote unavailable.": "Painel não está rodando — controle remoto indisponível.",
    "REMOTE ACCESS": "ACESSO REMOTO",
    "◈  REMOTE ACCESS": "◈  ACESSO REMOTO",
    "Scan with phone camera to connect instantly": "Escaneie com a câmera do celular para se conectar instantaneamente",
    "Or enter manually:": "Ou digite manualmente:",
    "Could not generate remote key.": "Não foi possível gerar a chave remota.",
    "MORNING BRIEF": "RESUMO MATUTINO",
    "AUTO-START: ON": "INICIAR AUTOMATICAMENTE: LIGADO",
    "DOWNLOAD": "BAIXAR",
    "SLEEP NOW": "DORMIR AGORA",
    "WAKE NOW": "ACORDAR AGORA",
    "PUSH-TO-TALK": "PUSH-TO-TALK",
    "HUD: ANIMATED FACE": "HUD: ROSTO ANIMADO",
    "HUD: REACTOR CORE": "HUD: NÚCLEO DO REATOR",
    "Wake word ready.": "Palavra de ativação pronta.",
    "Wake word setup failed: ": "Falha na configuração da palavra de ativação: ",
}

# Merge states into the main dict
_UI.update(_STATES)

# ---------------------------------------------------------------------------
# Log lines (SYS: ...) produced by main.py and shown in the activity log
# ---------------------------------------------------------------------------
_LOG = {
    "Awake": "Acordado",
    "Sleeping": "Dormindo",
    "Say 'Hey Jarvis' to wake me.": "Diga 'Hey Jarvis' para me acordar.",
    "JARVIS is connecting; command queued.": "JARVIS está conectando; comando enfileirado.",
    "Push-to-talk on — hold ": "Push-to-talk ativado — segure ",
    "Microphone muted.": "Microfone mudo.",
    "Microphone active.": "Microfone ativo.",
    "Initialised.": "Inicializado.",
    "online.": "online.",
    "SYS: JARVIS online.": "SYS: JARVIS conectado.",
    "SYS: JARVIS online — sleeping. Say 'Hey Jarvis' to wake me.": "SYS: JARVIS conectado — em espera. Diga 'Hey Jarvis' para me acordar.",
    "SYS: Phone connected via Remote Dashboard.": "SYS: Celular conectado pelo painel remoto.",
    "Dashboard unavailable. ": "Painel indisponível. ",
    "SYS: Recovered from a stopped worker pool.": "SYS: Recuperado de uma interrupção do processamento.",
    "SYS: Could not fetch the news for the briefing.": "SYS: Não foi possível buscar as notícias para o resumo.",
    "SYS: Reconnected — conversation restored.": "SYS: Reconectado — conversa restaurada.",
    "SYS: Could not restore the conversation — starting fresh.": "SYS: Não foi possível restaurar a conversa — iniciando uma nova.",
    "SYS: Microphone '{name}' unavailable — using system default.": "SYS: Microfone '{name}' indisponível — usando o padrão do sistema.",
    "SYS: Speaker '{name}' unavailable — using system default.": "SYS: Alto-falante '{name}' indisponível — usando o padrão do sistema.",
    "Desktop shortcut created.": "Atalho da área de trabalho criado.",
    "Shortcut failed —": "Falha ao criar atalho —",
    "Audio devices updated.": "Dispositivos de áudio atualizados.",
    "Engine settings saved — reconnecting.": "Configurações do motor salvas — reconectando.",
    "The model stopped answering — reconnecting.": "O modelo parou de responder — reconectando.",
    "Applying ": "Aplicando ",
    " — reconnecting": " — reconectando",
    " (starting a fresh conversation)...": " (iniciando uma nova conversa)...",
    "wake word": "palavra de ativação",
    "typed command": "comando digitado",
    "no speech for 2 minutes": "sem fala por 2 minutos",
    "you tapped sleep": "você tocou em dormir",
    "wake word enabled": "palavra de ativação ativada",
    "wake word disabled": "palavra de ativação desativada",
    "works while this window is focused.": "funciona apenas enquanto esta janela está em foco.",
    "Interrupted — listening.": "Interrompido — ouvindo.",
    "Shutdown requested.": "Desligamento solicitado.",
    "SYS: Applying ": "SYS: Aplicando ",
    "DEFAULT": "PADRÃO",
    "APPLY CHANGES": "APLICAR ALTERAÇÕES",
    "SAVE": "SALVAR",
    "QUIZ": "QUESTIONÁRIO",
    "Video playback is not available in this Qt install.": "A reprodução de vídeo não está disponível nesta instalação do Qt.",
    "⚙  CUSTOMISE ASSISTANT": "⚙  PERSONALIZAR ASSISTENTE",
    "ASSISTANT NAME": "NOME DO ASSISTENTE",
    "YOUR NAME  (leave blank for default sir / efendim)": "SEU NOME  (deixe em branco para o padrão)",
    "e.g.  Tony   (leave blank for auto)": "ex.  Tony   (deixe em branco para automático)",
    "ASSISTANT VOICE": "VOZ DO ASSISTENTE",
    "UI COLOUR  —  drag the handle": "COR DA UI  —  arraste o controle",
    "#00d4ff   (custom hex colour)": "#00d4ff   (cor hexadecimal personalizada)",
    "GEMINI LIVE": "GEMINI AO VIVO",
    "MY OWN SETUP": "MEU PRÓPRIO SETUP",
    "Nothing to set up. Your voice goes to Gemini and comes back as speech over one connection, with the transcript and every tool call on the same wire.": "Não há nada para configurar. Sua voz vai para o Gemini e volta como fala através de uma única conexão, com a transcrição e todas as chamadas de ferramenta no mesmo fio.",
    "Pick MY OWN SETUP above to run it on your own machine, or through another company's model.": "Escolha MEU PRÓPRIO SETUP acima para rodar na sua própria máquina, ou através do modelo de outra empresa.",
    "— not set —": "— não definido —",
    "needs install": "precisa instalar",
    "HEARING": "OUVINDO",
    "THINKING": "PENSANDO",
    "SPEAKING": "FALANDO",
    "OS": "SO",
    "WIN": "WIN",
    "macOS": "macOS",
    "LINUX": "LINUX",
    "PROTOCOL": "PROTOCOLO",
    "TMP": "TEMP",
    "📄  Escolher um arquivo…": "📄  Escolher um arquivo…",
    "📁  Escolher uma pasta…  (para programação)": "📁  Escolher uma pasta…  (para programação)",
    "Selecionar uma pasta de projeto para o JARVIS": "Selecionar uma pasta de projeto para o JARVIS",
    "Selecionar um arquivo para o JARVIS": "Selecionar um arquivo para o JARVIS",
    "Todos os Arquivos (*.*)": "Todos os Arquivos (*.*)",
    "Imagens (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg)": "Imagens (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg)",
    "Documentos (*.pdf *.docx *.txt *.md *.pptx)": "Documentos (*.pdf *.docx *.txt *.md *.pptx)",
    "Dados (*.csv *.xlsx *.json *.xml)": "Dados (*.csv *.xlsx *.json *.xml)",
    "Código (*.py *.js *.ts *.html *.css *.java *.cpp *.go)": "Código (*.py *.js *.ts *.html *.css *.java *.cpp *.go)",
    "Áudio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac)": "Áudio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac)",
    "Vídeo (*.mp4 *.avi *.mov *.mkv *.wmv *.webm)": "Vídeo (*.mp4 *.avi *.mov *.mkv *.wmv *.webm)",
    "Arquivos Compactados (*.zip *.rar *.tar *.gz *.7z)": "Arquivos Compactados (*.zip *.rar *.tar *.gz *.7z)",
    "Solte um arquivo ou pasta  ou  Clique para Procurar": "Solte um arquivo ou pasta  ou  Clique para Procurar",
    "Imagens · Vídeo · Áudio · PDF · Documentos · Código · Pastas de projeto": "Imagens · Vídeo · Áudio · PDF · Documentos · Código · Pastas de projeto",
    "Solte para carregar": "Solte para carregar",
    "PASTA": "PASTA",
    "arquivos": "arquivos",
    "MICROPHONE — what JARVIS hears you with": "MICROFONE — o que o JARVIS ouve de você",
    "SPEAKERS — what JARVIS talks through": "CAIXAS DE SOM — o que o JARVIS fala através",
    "Applying reconnects the session. Your conversation is kept.": "Ao aplicar, a sessão é reconectada. Sua conversa é mantida.",
    "Speak now…": "Fale agora…",
    "Playing a tone…": "Tocando um tom…",
    "Nothing stored yet.": "Nada armazenado ainda.",
    "Forget this": "Esquecer isto",
    "TRANSLATE": "TRADUZIR",
    "Translate this text to English: {text}": "Traduzir este texto para o inglês: {text}",
    "SUMMARISE": "RESUMIR",
    "Summarise this: {text}": "Resumir isto: {text}",
    "EXPLAIN": "EXPLICAR",
    "Explain this: {text}": "Explicar isto: {text}",
    "CLOSE": "FECHAR",
    "DISMISS": "DESCARTAR",
    "SAVE": "SALVAR",
    "APPLY": "APLICAR",
    "CONFIRM": "CONFIRMAR",
    "CANCEL": "CANCELAR",
    "DEFAULT": "PADRÃO",
    "APPLY CHANGES": "APLICAR ALTERAÇÕES",
    "QUIZ": "QUESTIONÁRIO",
    "NEXT  →": "PRÓXIMO  →",
    "FINISH  →": "FINALIZAR  →",
    "your answer": "sua resposta",
    "ANSWER": "RESPOSTA",
    "correct": "correto",
    "wrong": "errado",
    "NEEDS MARKING": "PRECISA DE AVALIAÇÃO",
    "correct": "correto",
    "Mute": "Mudo",
    "Fullscreen": "Tela Cheia",
    "By FatihMakes": "Por FatihMakes",
    "Type a command or question…": "Digite um comando ou pergunta…",
    "BRIEFING": "RESUMO MATUTINO",
    "ACTIVITY LOG": "LOG DE ATIVIDADE",
    "COMMAND INPUT": "ENTRADA DE COMANDO",
    "No file loaded — drop or click above to upload": "Nenhum arquivo carregado — solte ou clique acima para enviar",
    "FILE UPLOAD": "ENVIO DE ARQUIVO",
    "Dashboard not running — remote unavailable.": "Painel não está rodando — controle remoto indisponível.",
    "Could not generate remote key.": "Não foi possível gerar a chave remota.",
    "SYS: Dashboard not running — remote unavailable.": "SYS: Painel não está rodando — controle remoto indisponível.",
    "SYS: Could not generate remote key.": "SYS: Não foi possível gerar a chave remota.",
    "SYS: The providers folder is not installed — the assistant runs on Gemini Live.": "SYS: A pasta de provedores não está instalada — o assistente roda no Gemini Live.",
    "SYS: Provider settings unavailable: {e}": "SYS: Configurações de provedor indisponíveis: {e}",
    "SYS: Engine settings saved — reconnecting.": "SYS: Configurações do motor salvas — reconectando.",
    "SYS: Confirmation failed — {e}": "SYS: Falha na confirmação — {e}",
    "SYS: Microphone muted.": "SYS: Microfone mudo.",
    "SYS: Microphone active.": "SYS: Microfone ativo.",
    "SYS: Identity updated — {display}": "SYS: Identidade atualizada — {display}",
    "SYS: UI colour applied — {ui_color}": "SYS: Cor da UI aplicada — {ui_color}",
    "SYS: Voice set — {voice}": "SYS: Voz definida — {voice}",
    "SYS: Config save failed — {e}": "SYS: Falha ao salvar a configuração — {e}",
    "SYS: Audio devices updated.": "SYS: Dispositivos de áudio atualizados.",
    "SYS: Desktop shortcut created.": "SYS: Atalho da área de trabalho criado.",
    "SYS: Shortcut failed — {e}": "SYS: Falha ao criar atalho — {e}",
    "SYS: Auto-start {'enabled' if enabled else 'disabled'}.": "SYS: Início automático {'ativado' if enabled else 'desativado'}.",
    "SYS: Auto-start failed — {e}": "SYS: Falha no início automático — {e}",
    "SYS: HUD switched to the animated face.": "SYS: HUD alternado para o rosto animado.",
    "SYS: HUD switched to the reactor core.": "SYS: HUD alternado para o núcleo do reator.",
    "SYS: Wake word ready.": "SYS: Palavra de ativação pronta.",
    "SYS: Wake word setup failed: ": "SYS: Falha na configuração da palavra de ativação: ",
    "SYS: Push-to-talk failed — {e}": "SYS: Falha no push-to-talk — {e}",
    "SYS: HUD switched to the animated face.": "SYS: HUD alternado para o rosto animado.",
    "(not connected)": "(não conectado)",
    "INSTALL": "INSTALAR",
    "FIX": "CORRIGIR",
    "Saved": "Salvo",
    "Testing…": "Testando…",
    "CODE AGENT": "AGENTE DE CÓDIGO",
    "You": "Você",
}

# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

_ALL: dict[str, str] = {}
_ALL.update(_UI)
_ALL.update(_LOG)


def t(text: str) -> str:
    """Return the Portuguese translation of `text`, or `text` itself if none."""
    return _ALL.get(text, text)
