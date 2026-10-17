# maps4drone

Gerador open source de waypoints de mapeamento para drones. Você desenha uma área no
mapa (ou importa KML/KMZ/GeoJSON), escolhe altitude e sobreposição, e o programa gera a
missão pronta para o drone.

Primeiro alvo: **Potensic Atom 2** (app Potensic Eve). A arquitetura permite adicionar
outros drones (um escritor de formato por drone + uma entrada no catálogo).

> **Aviso de segurança.** Este software gera planos que comandam um drone real. Teste
> primeiro numa área aberta e pequena, com visada direta, respeitando a legislação local
> (no Brasil: ANAC/DECEA, limite de 120 m AGL). Os autores não se responsabilizam por
> danos. Veja "O que ainda não foi validado em voo" abaixo.

## Modos

| Comando | O que faz |
|---|---|
| `grid` | Faixas paralelas sobre um polígono (ângulo, sobreposição frontal/lateral); `--double` faz uma segunda passada perpendicular |
| `corridor` | Passadas paralelas ao longo de uma linha (estrada, ferrovia, rio); número ímpar de linhas |
| `orbit` | Órbita em torno de um ponto de interesse, câmera sempre apontada para ele |
| `facade` | Grade vertical diante de uma parede (experimental) |

Em `grid` e `corridor`, `--terrain --takeoff LAT,LNG` ajusta a altura de cada ponto ao
relevo (elevação Copernicus 90 m via Open-Meteo, precisa de internet) para manter a
altura constante sobre o solo.

A velocidade sai do intervalo de disparo e da sobreposição frontal:
`velocidade = (altura da pegada × (1 − sobreposição frontal)) / intervalo`.
O arquivo do Atom 2 **não** dispara a câmera sozinho: configure o modo temporizado no app
com o mesmo intervalo antes de voar (o programa lembra você).

## Instalação

```sh
uv venv && uv pip install -e ".[dev]"
```

## Interfaces

- **CLI** (abaixo).
- **Web:** interface React em passos (missão, área, ajustes, revisão) com mapa, dados do voo
  e perfil de elevação, para o Atom 2 e drones DJI. Veja [docs/web.md](docs/web.md).
- **Plugin WebODM:** o mesmo planejador dentro do WebODM, sobre a ortofoto do projeto e com o
  terreno do DSM ou DTM dele. Veja [docs/webodm.md](docs/webodm.md). Build:
  `python scripts/build_webodm_plugin.py`.
- **Plugin QGIS:** algoritmos de Processing que geram camadas e a pasta da missão. Veja
  [docs/qgis.md](docs/qgis.md). Build: `python scripts/build_qgis_plugin.py`.

## Uso

```sh
# listar drones
maps4drone drones

# grid sobre um polígono, linhas a 35°, 100 m, disparo a cada 3 s
maps4drone grid area.kml --angle 35 --altitude 100 --interval 3 --out out/
# sem --angle, as faixas seguem o eixo maior da área (retângulo mínimo rotacionado)

# seguindo o relevo (ponto de decolagem obrigatório)
maps4drone grid area.geojson --terrain --takeoff=-23.15,-51.90 --out out/

# corredor com 5 linhas
maps4drone corridor estrada.kml --lines 5 --out out/

# órbita (use = em coordenadas negativas)
maps4drone orbit --center=-23.15,-51.90 --radius 40 --height 40 --out out/
```

Cada comando imprime waypoints, distância, tempo, baterias e imagens estimadas, e grava
`preview.geojson` (abra no QGIS ou em geojson.io para conferir a rota).

### Levando a missão para o Atom 2

O app só reconhece missões que ele mesmo criou. O truque (descoberto pela comunidade):

1. No Potensic Eve, crie e salve uma missão qualquer (a "dummy").
2. No celular, abra `Android/data/com.ipotensic.atom/files/Waypoint/<id>/`.
3. Substitua os dois arquivos dessa pasta (`global.json` e `<id>.json`) pelos gerados,
   **mantendo os nomes**. Com a pasta copiada para o computador:

```sh
maps4drone grid area.kml --replace /caminho/da/pasta/<id> --out out/
```

4. Abra a missão no app, confira a rota, configure o temporizador de fotos e voe.

Detalhes do formato em [docs/atom2-format.md](docs/atom2-format.md).

## Desenvolvimento

```sh
.venv/bin/ruff check src tests && .venv/bin/mypy && .venv/bin/pytest
```

A lógica fica em `src/maps4drone` (fora de `web/`) sem dependência de QGIS ou web, para poder ser usada
por qualquer interface.

## O que ainda não foi validado em voo

- O plugin QGIS foi testado em QGIS 4.2 sem interface gráfica; a interface web foi exercitada
  em um navegador automatizado (desenhar a área, planejar, revisar), mas não em celular, e o
  export DJI nunca foi aberto no DJI Fly.
- O formato do Atom 2 foi reconstruído de um arquivo real exportado do app e de
  engenharia reversa da comunidade; ele pode mudar com o firmware.
- Convenções de `yaw` (graus, referência norte) usadas em `orbit` e `facade` e a altura
  relativa à decolagem seguem a documentação da comunidade, mas não foram testadas em voo.
- Os limites do Atom 2 no catálogo (`drones.json`: 32 min, 16 m/s, sensor 6,4×4,8 mm,
  4,5 mm) vêm de especificações públicas e da ferramenta de referência. Confira.

Relatos de voo (com a versão do app e do firmware) são muito bem-vindos nas issues.

## Créditos

- Funcionalidades inspiradas no gerador web da Maps4me.
- A interface web usa o GeoWay 1.2 como referência de recursos e de parâmetros dos drones DJI;
  o código foi reescrito do zero em React.
- [GeoFlight Planner](https://github.com/OpenGeoOne/qgis_drone_flight_planner) (MIT,
  GeoOne): referência de algoritmos de voo para QGIS.
- Formato de missão do Atom 2: engenharia reversa publicada por
  [spwoodcock](https://spwoodcock.dev/blog/2026-02-04-potensic-atom-redux/) (CC0).

## Licença

MIT.
