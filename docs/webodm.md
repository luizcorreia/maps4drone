# Plugin do WebODM

Planeja o voo dentro do WebODM, sobre a ortofoto de um projeto, e acompanha o terreno com o
**DSM ou DTM do próprio projeto**: sem serviço de elevação online, sem limite de consultas e
com a resolução do seu modelo. Gera as missões do Potensic Atom 2 e dos drones DJI, como a
[interface web](web.md).

Fica em `webodm_plugin/maps4drone/` e reaproveita o núcleo (`src/maps4drone`), embutido no zip.

## Requisitos

- WebODM 3.3.1 ou mais novo (o código foi escrito contra a versão 3.3.1).
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

## Usar

- Em cada tarefa com mapa (ortofoto, DSM ou DTM) aparece o botão **Planejar voo**. Ele abre o
  planejador já no projeto: o mapa começa na extensão da tarefa, com a ortofoto como fundo.
- O item **Planejar voo** do menu lateral abre o planejador sem tarefa (mapas de rua, satélite e
  híbrido, e elevação online).
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
