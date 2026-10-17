# Plugin do WebODM

Planeja o voo dentro do WebODM, sobre a ortofoto de um projeto, e acompanha o terreno com o
**DSM ou DTM do próprio projeto**: sem serviço de elevação online, sem limite de consultas e
com a resolução do seu modelo. Gera as missões do Potensic Atom 2 e dos drones DJI, como a
[interface web](web.md).

Fica em `webodm_plugin/maps4drone/` e reaproveita o núcleo (`src/maps4drone`), embutido no zip.

## Requisitos

- Um WebODM com a API de plugins (`PluginBase`, `MountPoint`, `TaskView`): o código foi escrito contra a
  versão 3.3.1 e o manifesto não fixa versão mínima, porque o WebODM esconde sem avisar um plugin
  cuja versão mínima seja maior que a dele.
- Nada a instalar no servidor além do plugin: o WebODM já traz Python 3.9, pydantic 1.10,
  pyproj, rasterio e Pillow. O `shapely>=2`, que o planejador usa, está no `requirements.txt` do
  plugin e o WebODM o instala ao ativar o plugin, então o contêiner precisa de internet nessa hora.

## Instalar

```sh
(cd web && npm ci && npm run build:webodm)    # interface para /plugins/maps4drone/
python scripts/build_webodm_plugin.py          # dist/maps4drone-webodm-<versão>.zip
```

No WebODM, entre como administrador: **Administration > Plugins > Load Plugin (.zip)**, escolha o
zip e ative o plugin na lista. Para atualizar, remova o plugin antigo e envie o novo (o WebODM
recusa um nome que já existe).

**Depois de instalar ou atualizar, reinicie o WebODM** (`docker restart webapp`). Ele guarda a lista de
plugins na memória de cada processo, e enquanto algum processo não reinicia, parte das requisições
ao plugin responde 404 de forma intermitente.

## Usar

- Em cada tarefa com mapa (ortofoto, DSM ou DTM) aparece o botão **Planejar voo**. Ele abre o
  planejador já no projeto: o mapa começa na extensão da tarefa, com a ortofoto como fundo.
- O item **Planejar voo** do menu lateral abre o planejador sem tarefa. No cabeçalho, escolha o
  **projeto** e a **tarefa** (só aparecem as concluídas que têm ortofoto, DSM ou DTM) para planejar
  sobre ela; "Sem projeto" volta aos mapas públicos (rua, satélite, híbrido) e à elevação online.
  O botão **← WebODM** volta ao painel, direto ao projeto quando há tarefa aberta.
- **Planos salvos:** escolhido um projeto (mesmo sem nenhuma tarefa, antes das fotos), aparece no topo do
  painel a barra do plano: dê um nome e **Salve**, reabra pela lista de planos salvos, **Duplique**,
  **Apague** ou comece um **Novo**. O indicador mostra se há alterações não salvas, e o programa
  pergunta antes de descartá-las. Os planos são do projeto: quem pode ver o projeto os vê, e quem
  pode alterá-lo salva e apaga. O endereço guarda o projeto (`?project=<id>`) e a tarefa.
- **Antes das fotos:** o mapa abre em satélite e tem **busca de endereço** (OpenStreetMap, só ao
  confirmar a busca) e **Minha posição**, para chegar até a área. O terreno vem da elevação online.
- **Depois do voo:** com a tarefa processada aberta, o plano aberto pode ser **vinculado a ela**
  (vira "realizado" na lista; dá para desvincular), e **Mostrar onde as fotos foram tiradas** desenha
  as posições reais (`shots.geojson` da tarefa) sobre o plano, com a contagem de fotos tiradas contra
  as planejadas. Só aceita tarefas do mesmo projeto do plano.
- Os quatro passos são os da [interface web](web.md). Em **Ajustes**, ao ligar "Acompanhar o
  terreno" e marcar a decolagem, escolha o **modelo de elevação**: DSM do projeto (padrão, já passa
  por cima de árvores e construções), DTM do projeto (só o chão) ou online. O DTM só existe se a
  tarefa foi processada com ele.
- Marque a decolagem dentro da área coberta pelo modelo. Se algum ponto da rota cair fora dele ou
  numa célula sem dado, o planejamento recusa e diz quantos pontos faltam.

## API do plugin

Sob `/api/plugins/maps4drone/` (exige login no WebODM):

| Rota | Descrição |
|---|---|
| `GET drones` | Catálogo de drones |
| `GET camera?drone=&altitude=&camera=` | GSD e cobertura da câmera |
| `POST import?name=arq.kml` | Corpo cru do arquivo; devolve o primeiro polígono e/ou linha |
| `POST plan`, `POST export` | Como na [API web](web.md#api); terreno pela elevação online |
| `GET project/<id>/plans` | Planos de voo salvos do projeto (exige permissão de ver o projeto) |
| `POST project/<id>/plans` | Salva um plano `{name, request}`; com `id`, atualiza (exige permissão de alterar) |
| `DELETE project/<id>/plans/<plano>` | Apaga o plano |
| `POST project/<id>/plans/<plano>/task` | `{"task": "<id>"}` vincula o plano a uma tarefa do mesmo projeto (marca como realizado); `null` desvincula |
| `GET task/<id>/info` | Nome, extensão, camadas disponíveis e URL das tiles da tarefa |
| `POST task/<id>/plan`, `POST task/<id>/export` | Como acima, com `"dem": {"layer": "dsm"\|"dtm"}` para usar o modelo da tarefa |

A permissão é a do próprio WebODM: quem não pode ver o projeto não planeja sobre ele.

## Como é feito

- `logic.py` tem o que o plugin decide (ler o corpo, escolher o modelo, descrever a tarefa) sem
  Django, e é coberto por testes. `views.py` e `plugin.py` só ligam isso ao DRF e ao `PluginBase`.
- `public/main.js` registra o botão da tarefa (`PluginsAPI.Dashboard.addTaskActionButton`).
- A interface é a mesma de `web/`, compilada com `--mode webodm` (base `/plugins/maps4drone/`,
  API em `/api/plugins/maps4drone`). Dentro do WebODM ela envia o token CSRF do Django.
- O núcleo roda em Python 3.9 e com pydantic 1.x; o CI testa essa combinação (`webodm-compat`).

## O que ainda não foi validado

- `plugin.py` e `views.py` dependem de Django 2.2, DRF e `app.plugins`; os testes não os
  executam. O fluxo completo (enviar o zip, ativar, abrir pela tarefa, planejar com o DSM, baixar)
  precisa ser conferido num WebODM real.
- As tiles da ortofoto (`.../orthophoto/tiles/{z}/{x}/{y}.png`) e a importação de arquivos
  (`request.body` numa view DRF) vieram do código-fonte do WebODM, sem teste em execução.
