# Assistente Dota 2

Aplicação desktop com builds Dota2ProTracker, counters OpenDota e avisos GSI.

## Requisitos e instalação

- **Python 3.10 ou superior**, com Tcl/Tk (Tkinter).
- **Windows** para a interface nativa, foco, clique transparente e voz SAPI.
- `pip` e as dependências já declaradas em `requirements.txt`.

```sh
python -m pip install -r requirements.txt
python app.py
```

O domínio e os testes funcionam sem Windows e sem interface gráfica. A entrada
desktop informa a limitação e encerra em outras plataformas; não existe um
adaptador nativo para Linux. Para conferir a instalação Tk no Windows:
`python -m tkinter`.

## Configuração do jogo

Crie `gamestate_integration_assistente.cfg` na pasta
`game/dota/cfg/gamestate_integration/` da instalação do Dota 2 e reinicie o jogo:

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

A porta e as opções ficam em `assistente/configuracao.py`. O servidor escuta somente
em `127.0.0.1`, valida JSON, limita cada corpo recebido a 1 MiB e atende até quatro
conexões simultâneas. Excesso de conexões recebe HTTP 503.

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
  infraestrutura/              HTTP, cache, preferências, voz e Windows
  apresentacao/                painel, sobreposições, formatação e GSI
tests/                         caracterização, regras e integrações simuladas
AGENTS.md                      instruções obrigatórias para agentes
```

Domínio não importa as outras camadas. Aplicação depende do domínio e de contratos;
infraestrutura implementa esses contratos. A apresentação não importa clientes
concretos. As dependências são conectadas em `composicao.py`.

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
python -B -m unittest discover -s tests -v
```

Os testes não consultam os provedores reais; o teste HTTP de integração usa apenas
uma porta local temporária. Testes dos controladores substituem Tkinter e não
validam aparência, foco, COM ou clique transparente.

Ruff e mypy são opcionais, configurados em `pyproject.toml`, sem instalação automática:

```sh
python -m ruff check .
python -m ruff format --check .
python -m mypy assistente
```

Antes de considerar uma versão pronta, validar manualmente no Windows: recebimento
GSI, troca das cinco funções, overlays e posições, voz, fechamento durante consulta,
e integração real Dota2ProTracker/OpenDota. O endpoint Dota2ProTracker não é uma API
oficial documentada e pode mudar ou ser bloqueado pelo Cloudflare.
