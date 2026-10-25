# Assistente Dota 2

Aplicação desktop com builds Dota2ProTracker, counters OpenDota e avisos GSI.

## Requisitos e instalação

- **Python 3.10 ou superior**, com Tcl/Tk (Tkinter).
- **Windows ou Linux**, com Steam e Dota 2 instalados para abrir o jogo.
- `pip` e as dependências já declaradas em `requirements.txt`.
- Windows: Win32 para foco/overlays e `pywin32` para voz SAPI.
- Linux: sessão X11 ou XWayland, bibliotecas X11/XFixes para os recursos de
  janelas e `espeak-ng` com voz `pt-br` para os avisos de voz.

```sh
python -m pip install -r requirements.txt
python app.py
```

A entrada é a mesma nos dois sistemas: `python app.py`. `pywin32` é instalado
somente no Windows pelo marcador em `requirements.txt`. No Linux, Tcl/Tk,
X11/XFixes e `espeak-ng` são componentes do sistema, não pacotes pip; instale-os
pelo mecanismo da sua distribuição, sem misturar versões incompatíveis de Python
e Tcl/Tk. Confira o carregamento da interface com `python -m tkinter`.

O domínio e os testes não exigem interface gráfica. Sistemas diferentes de Windows
e Linux são rejeitados antes da criação de janelas ou trabalhadores. A falta de
Tcl/Tk é informada na saída de erro; voz ou recursos de janelas indisponíveis são
indicados no painel/registro, sem impedir as consultas de recomendações.

### Limites da interface Linux

Foco e clique transparente usam X11, inclusive quando disponível por XWayland.
Não há suporte equivalente genérico a janelas **Wayland nativas**. O compositor e
o modo de exibição do jogo também podem impedir overlays acima do jogo ou a
identificação de foco. O painel informa essas limitações. Sem foco automático,
destrave os overlays para exibição manual; sem clique transparente, eles podem
interceptar cliques.

## Abertura e verificação do Dota 2

Use **Iniciar / verificar Dota 2** no painel. O assistente não abre o jogo ao
iniciar e não encerra Steam ou Dota ao fechar. A informação exibida é uma
observação daquele momento; use o botão novamente para atualizar.

- **Windows:** descobre a Steam pelo Registro (usuário/máquina e visões 32/64 bits)
  ou pelo PATH, sem fixar unidade ou `Program Files`.
- **Linux:** considera `XDG_DATA_HOME/Steam`, `~/.local/share/Steam`, aliases
  `~/.steam/` e os diretórios da Steam Flatpak em
  `~/.var/app/com.valvesoftware.Steam/`.
- Lê `steamapps/libraryfolders.vdf` e `appmanifest_570.acf` para descobrir
  bibliotecas secundárias e o diretório do jogo. Bibliotecas inválidas ou
  desmontadas não impedem a consulta de outras bibliotecas acessíveis.
- Localiza os executáveis específicos de cada sistema. No Linux atual, o
  candidato principal é `game/bin/linuxsteamrt64/dota2`; o layout anterior
  `game/bin/linux64/dota2` também é considerado.
- Lança pela Steam com `-applaunch 570`, usando o cliente correspondente à
  instalação nativa ou Flatpak. O binário Linux não é executado diretamente:
  o script atual do jogo exige o Steam Runtime **sniper**.

Quando há mais de uma instalação válida, a primeira com cliente utilizável é
escolhida; no Linux, a instalação nativa tem prioridade sobre Flatpak. Não há
seletor manual de instalação.

A descoberta ocorre fora da thread gráfica, é reutilizada em memória e é
revalidada quando o executável desaparece. Não há varredura de discos nem novo
cache persistente. Os caminhos e argumentos são validados; comandos são listas
de argumentos, sem `shell=True`.

### Significado do resultado

`IniciarDota` retorna um `ResultadoExecucao` tipado com estado, executável,
`pid_jogo`, `pid_iniciador` e erro, quando disponíveis:

| Estado | Significado |
|---|---|
| `NAO_OBSERVADO` | Nenhum processo correspondente foi observado na consulta. |
| `INICIADOR_ATIVO` | O processo auxiliar da Steam está ativo; ainda não confirma o jogo. |
| `SOLICITADO` | O comando Steam terminou com código zero; o jogo ainda não foi observado. |
| `EM_EXECUCAO` | Um processo com o executável real do Dota foi identificado. |
| `NAO_CONFIRMADO` | O prazo terminou ou a inspeção não pôde confirmar o processo. |
| `FALHA` | Há um erro concreto de descoberta ou execução do comando. |

O PID da Steam **nunca é apresentado como PID do Dota**. Um processo observado
também não comprova que o menu carregou ou que uma partida começou. GSI continua
sendo uma informação separada; ausência de GSI não comprova falha de lançamento.

Há apenas uma operação de inicialização por vez, sem fila ilimitada. O prazo
padrão de confirmação é de 30 segundos, configurável em
`assistente/configuracao.py`. Um timeout não encerra processos e não dispara
outro lançamento: o botão passa a verificar a solicitação pendente. Se ela nunca
for atendida, resolva o problema na Steam e reinicie o assistente antes de reenviar.

## Configuração do jogo

### Configuração pelo painel (recomendada)

O assistente verifica o arquivo GSI automaticamente ao abrir, **sem gravar nada**.
Para configurar, abra a aba **Integração Dota** e clique em **Configurar integração**.
O caminho encontrado pela descoberta Steam é mostrado na própria aba; não é
preciso localizar a biblioteca nem copiar o conteúdo manualmente.

- Se estiver ausente, cria a pasta necessária e
  `game/dota/cfg/gamestate_integration/gamestate_integration_assistente.cfg`.
- O destino usa `127.0.0.1` e a mesma porta efetivamente aberta pelo servidor do
  assistente (por padrão, `4000`). Os campos `provider`, `map`, `player` e `hero`
  são habilitados, pois são os dados consumidos pela aplicação.
- Um arquivo compatível é preservado sem regravar, incluindo comentários,
  personalizações e campos adicionais.
- Se o arquivo existir com conteúdo incompatível, ele é preservado e o botão
  passa a **Reparar integração…**. O reparo exige confirmação, salva uma cópia
  exata com extensão `.bak` e substitui somente o arquivo do assistente. A nova
  configuração usa o modelo padrão; personalizações antigas ficam no backup,
  cujo caminho é mostrado no painel. Alterações detectadas entre a confirmação
  e a gravação exigem reavaliação, sem aplicar a confirmação ao novo conteúdo.
- Outros arquivos de integração não são alterados. Links, destinos fora da
  instalação e arquivos acima de 64 KiB são recusados. Erros de permissão ou
  disco são informados sem solicitar privilégios administrativos automaticamente.

Descoberta, leitura e gravação ocorrem em segundo plano, com uma operação GSI
por vez. Não existe um booleano persistente de “configurado”: o estado é
verificado no arquivo real, inclusive pelo botão **Verificar configuração**.
Nenhum novo pacote ou formato de preferências foi introduzido.

**Se o Dota já estava aberto ao criar ou reparar o arquivo, reinicie-o após
terminar a partida.** O assistente nunca fecha nem relança o jogo para aplicar
a configuração. Criar o arquivo não comprova que o jogo o carregou.

O painel diferencia arquivo configurado, processo do Dota observado e dados GSI
recebidos recentemente. É possível receber dados fora de uma partida; nesse
caso, a interface informa que o GSI está conectado e aguarda a partida. Dados
que ultrapassam o limite de ausência de sinal não são apresentados como recentes.

### Alternativa manual

Também é possível criar `gamestate_integration_assistente.cfg` na pasta
`game/dota/cfg/gamestate_integration/` da instalação do Dota 2 com o conteúdo
abaixo (porta padrão). Depois, reinicie o jogo se ele já estava aberto:

```text
"Assistente Dota 2"
{
    "uri" "http://127.0.0.1:4000"
    "timeout" "5.0"
    "buffer" "0.1"
    "throttle" "0.2"
    "heartbeat" "30.0"
    "data"
    {
        "provider" "1"
        "map" "1"
        "player" "1"
        "hero" "1"
    }
}
```

A porta e o limite de ausência de sinal ficam em `assistente/configuracao.py`.
Se configurar manualmente uma porta diferente, ela precisa corresponder àquela
usada pelo servidor. O servidor escuta somente em `127.0.0.1`, valida JSON,
limita cada corpo recebido a 1 MiB e atende até quatro conexões simultâneas.
Excesso de conexões recebe HTTP 503.

## Builds por função
A build principal usa o endpoint JSON do Dota2ProTracker por herói e posição: Carry (pos 1), Mid (pos 2), Offlane (pos 3), Support (pos 4) e Hard Support (pos 5). O programa usa a build com a maior amostra retornada para aquela posição.

- **Saída:** tenta usar o combo inicial mais popular que caiba em 600 de ouro. Quantidades repetidas são preservadas. Wards e pergaminhos de TP não são mostrados como recomendação.
- **Core:** itens com pick rate de pelo menos 50%, ordenados pelo tempo médio de compra e distribuídos em Early (<12 min), Mid (12–30 min) e Late (30+ min).
- **Situacionais:** itens menos frequentes aparecem no painel principal, junto de pick rate e minuto médio. Não são tratados como obrigatórios.
- **Opções:** continuam separadas e são calculadas em função da lane selecionada, da ameaça marcada e da função/posição escolhida.

Os counters de itens são **heurísticas**, não estatísticas de partidas específicas.
O ranking de heróis combina matchup ponderado por jogos (70%) e meta (30%), com
peso 1,5 para a ameaça. Arquétipos OpenDota não equivalem às posições 1–5.

Benchmarks disponíveis são identificados pelo percentil retornado; metas que usam
fallback são identificadas como estimativas. O parâmetro `role` do endpoint de
benchmarks foi preservado, mas sua efetividade como filtro depende do provedor.

## Atualização/cache
As respostas Dota2ProTracker ficam em `cache/d2pt` por 30 minutos para reduzir chamadas. A janela de dados do site é móvel e depende da amostra recente disponível para aquele herói/função. A rota é mantida pelo próprio site, não é uma API oficial documentada para terceiros; ela pode mudar ou devolver HTTP 403/Cloudflare. Nesses casos, o aplicativo informa a falha em vez de apresentar uma build antiga como se fosse atual.

OpenDota mantém os arquivos em `cache_opendota/`. Os formatos e caminhos existentes
foram preservados, assim como `preferencias_overlay.json`. Novos caches são ignorados
pelo Git; arquivos já versionados não foram removidos automaticamente.

As gravações JSON são atômicas. Falhas de cache não impedem uma resposta válida.
Há um trabalhador de consultas e apenas uma solicitação pendente, substituível
pela seleção mais recente. Consultas obsoletas são interrompidas entre chamadas;
uma requisição HTTP já iniciada termina normalmente ou pelo timeout. Resultados
obsoletos ou posteriores ao fechamento não são enviados à interface.

## Organização

```text
app.py                         entrada canônica
assistente/
  configuracao.py              configurações centrais
  composicao.py                conexão de dependências e ciclo de vida
  dominio/                     modelos, builds, counters, eventos e metas
  aplicacao/                   casos de uso e contratos
  infraestrutura/              HTTP, cache, Steam, processos, voz e janelas por sistema
  apresentacao/                painel, sobreposições, formatação e GSI
tests/                         caracterização, regras e integrações simuladas
AGENTS.md                      instruções obrigatórias para agentes
```

Domínio não importa as outras camadas. Aplicação depende do domínio e de contratos;
infraestrutura implementa esses contratos. A apresentação não importa clientes
concretos. As dependências são conectadas em `composicao.py`.

O caso de uso `aplicacao/iniciar_dota.py` depende da porta `IniciadorDota` em
`aplicacao/contratos.py`. A fábrica `infraestrutura/plataforma.py` seleciona as
estratégias de descoberta e inspeção em `iniciador_windows.py` ou
`iniciador_linux.py`. Ambas compõem `IniciadorSteam`, que compartilha o ciclo de
lançamento, sem classes base por sistema. `steam.py` lê os metadados comuns e
`inicializacao_em_segundo_plano.py` limita trabalho e confirmações. As portas de
voz e janelas existentes foram reutilizadas; janelas agora têm encerramento
explícito para liberar a conexão X11.

`aplicacao/configurar_integracao_gsi.py` orquestra a verificação e a configuração
por um contrato. `infraestrutura/integracao_gsi_arquivo.py` reutiliza a descoberta
Steam e o leitor KeyValues, valida o destino e preserva backups nos reparos.
`configuracao_gsi_em_segundo_plano.py` executa os pedidos sem acessar widgets.
Somente a apresentação solicita a confirmação do usuário e renderiza os estados.

`app.py` é o único arquivo Python na raiz e apenas inicia a aplicação. Os clientes
HTTP, regras, dados de heróis, voz e sobreposições são utilizados diretamente de
`assistente/`. Caches e preferências continuam nos caminhos anteriores, fora do pacote.

As fachadas antigas da raiz, a aplicação independente `assistente_dota.py`,
`matchup_engine.py` e `hero_tags.py` foram removidos por não integrarem o fluxo atual.
Imports antigos, como `import build_engine`, `import config` e
`from app import Assistente`, não são mais suportados. Utilize os módulos de
`assistente/`; o comando de execução continua sendo `python app.py`.

## Testes

```sh
python -m pip install -r requirements-dev.txt
python -B -m pytest tests
python -B -m unittest discover -s tests -v
```

Pytest executa a suíte completa, incluindo os testes novos com fixtures. O
comando unittest continua disponível para os testes baseados em `TestCase`;
ele não executa as funções de teste exclusivas do pytest. Não há dependência de
pytest em produção.

Os testes não consultam os provedores reais; o teste HTTP de integração usa apenas
uma porta local temporária. Testes dos controladores substituem Tkinter e não
validam aparência, foco, COM ou clique transparente reais. Os testes de processos
e recursos nativos usam mocks e arquivos temporários; não abrem o Dota nem
reproduzem áudio, independentemente do sistema operacional do desenvolvedor.
Os testes de configuração GSI gravam apenas em diretórios temporários: cobrem
idempotência, preservação, conflitos, backups, falhas, cancelamento e concorrência
na criação. Nenhum teste instala arquivos na biblioteca Steam real.

Ruff e mypy são opcionais, configurados em `pyproject.toml`, sem instalação automática:

```sh
python -m ruff check .
python -m ruff format --check .
python -m mypy assistente
```

O mypy não está fixado em Windows. Também é possível verificar explicitamente
os dois destinos com `--platform win32` e `--platform linux`.

### Validação real e pendências

No ambiente Linux disponível, foi validada a descoberta em biblioteca Steam
secundária e a identificação de um Dota já em execução pelo executável real,
sem relançá-lo. Uma janela X11 não exibida permitiu verificar a região de entrada
vazia/restaurada e a contenção de erros de janela destruída. A síntese `pt-br`
gerou WAV válido, sem reprodução de áudio.

O Tkinter agora carrega no ambiente disponível. O painel Tk real foi exercitado
com janelas ocultas: verificação inicial sem gravação, criação pelo botão, reparo
com confirmação simulada e backup real em diretório temporário. Um POST HTTP
local sintético também confirmou a indicação de conexão fora de partida. Esse
teste não alterou a instalação Steam, não iniciou o jogo e não reproduziu áudio.
Não foram instalados componentes do sistema pelo agente.

A interação visual durante uma partida e o recebimento de dados do Dota real
continuam pendentes. Um POST sintético e a disponibilidade de bibliotecas X11
não comprovam o funcionamento da integração completa com o jogo.

Não foi realizado lançamento real do jogo. Windows e Steam Flatpak também
precisam de validação real; seus testes simulados não comprovam funcionamento
nesses ambientes. Antes de considerar a compatibilidade desktop integralmente
validada, conferir em cada ambiente: lançamento pela Steam, GSI, cinco funções,
overlays e posições, foco, clique transparente, áudio e fechamento durante consulta.
Não há garantia de paridade em Wayland nativo.

A integração real Dota2ProTracker/OpenDota também deve ser conferida. O endpoint
Dota2ProTracker não é uma API oficial documentada e pode mudar ou ser bloqueado
pelo Cloudflare.
