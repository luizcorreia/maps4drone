# Formato de missão do Potensic Atom 2

Fontes: arquivo real exportado do app (`tests/fixtures/atom2_sample_mission.json`) e
[engenharia reversa da comunidade](https://spwoodcock.dev/blog/2026-02-04-potensic-atom-redux/).
Não é documentação oficial; pode mudar com o firmware.

## Local no celular

`/sdcard/Android/data/com.ipotensic.atom/files/Waypoint/<id>/`, onde `<id>` é um
timestamp Unix em milissegundos:

```
<id>/
├── global.json      configurações da missão
├── <id>.json        waypoints
└── task_<n>.jpg     miniatura da lista de missões (só visual; `<n>` poucos ms antes de `<id>`)
```

O app mantém um índice próprio das missões. Uma pasta colocada de fora é apagada ao abrir
o app; por isso o fluxo é sobrescrever os arquivos de uma missão já criada no app.

## global.json

```json
{"finishAction":"BACK","globalHeight":0,"globalHeightType":0,"isOrder":true,"lostAction":"RETURN","speed":5.0}
```

| Campo | Valores |
|---|---|
| `finishAction` | `BACK`, `LAND`, `HOVER`, `RETURN` |
| `lostAction` | `RETURN` (único conhecido) |
| `speed` | m/s, usada nos pontos com `speedType: GLOBAL` |
| `isOrder` | `true` executa em ordem, `false` em ordem inversa |
| `globalHeight`, `globalHeightType` | `0`; não editáveis no app |

## `<id>.json`

Lista JSON de waypoints, numa linha só. Campos (todos obrigatórios no arquivo real):

| Campo | Observação |
|---|---|
| `lat`, `lng` | graus decimais |
| `height` | metros relativos ao ponto de decolagem |
| `speed`, `speedType` | `GLOBAL` (usa `global.json`) ou `DEFINE` (usa `speed`) |
| `action` | `NONE`, `PHOTO`, `START_RECORD`, `STOP_RECORD` |
| `hoverTime` | segundos parado no ponto |
| `gimbalPitch`, `gimbalType` | -90 a +20; `DEFINE` |
| `yaw`, `yawType` | `TO_WAYPOINT` (nariz para o próximo ponto) ou `HAND` (usa `yaw`) |
| `zoomRatio`, `zoomType` | `1.0`, `HAND` |
| `poiType`, `poiLat`, `poiLng`, `poiHeight` | `0`, `0.0`, `0.0`, `50.0` quando sem POI |

Firmwares anteriores reportam um segundo array de POIs após um `;` (`[...];[]`). O
programa tem `--legacy-poi-list` para isso; o padrão segue o arquivo real mais recente.

## Fotos

Não há comando de intervalo no arquivo. Em missões de mapeamento, ative o modo
temporizado no app com o intervalo usado no planejamento (`shoot_interval_s`).
Em `facade`, cada waypoint tem `action: PHOTO` e `hoverTime: 1`.
