# Interface web

Aplicação React (Vite + TypeScript) servida por uma API FastAPI que reutiliza o núcleo.
O planejamento é feito todo no servidor Python; o navegador só desenha, ajusta e baixa.

## Rodar

```sh
uv pip install -e ".[web]"
(cd web && npm ci && npm run build)   # compila a interface para src/maps4drone/web/static
maps4drone-web --port 8000            # http://127.0.0.1:8000
```

Sem o build, a API sobe do mesmo jeito e a raiz mostra como compilar a interface.
O wheel inclui a interface compilada (`artifacts` no `pyproject.toml`), então quem instala
o pacote não precisa de Node.

### Desenvolvimento

```sh
maps4drone-web --port 8765
cd web && MAPS4DRONE_API=http://127.0.0.1:8765 npm run dev   # http://localhost:5173
```

`MAPS4DRONE_API` aponta o proxy de `/api` (padrão `http://127.0.0.1:8000`). Em `web/`:
`npm run lint`, `format:check`, `typecheck`, `test` e `build`.

## Uso

A interface tem quatro passos, e o mapa mostra tudo em tempo real:

1. **Missão:** escolha o drone (Potensic Atom 2 ou DJI) e o tipo: Mapeamento (grid), Modelo 3D
   (grid duplo), Corredor, Fachada, Órbita ou Pontos livres. Cada tipo aplica valores prontos.
2. **Área:** clique no mapa para marcar os pontos. Arraste um pino para mover; botão
   direito (ou toque longo) remove. Também dá para importar KML, KMZ ou GeoJSON.
3. **Ajustes:** só os campos do tipo escolhido. O ângulo das faixas é automático (eixo maior
   da área). "Acompanhar o terreno" pede o ponto de decolagem no mapa; a elevação vem do
   Open-Meteo (precisa de internet e tem limite de consultas, por isso as consultas são
   guardadas em cache). "Avançado" tem câmera, gimbal, margem e amostragem do terreno.
4. **Revisar:** resumo, avisos e o download. Atom 2: `.zip` com `global.json`, `<id>.json` e
   um `README.txt` (siga [atom2-format.md](atom2-format.md) para a missão dummy). DJI: `.kmz`.

Sobre o mapa ficam o card **Dados do voo** (GSD, espaçamento, fotos, armazenamento, velocidade
máxima sem borrar, distância, duração e baterias), a legenda e, com terreno, o **perfil de
elevação**. Em Órbita, a "Altura do voo" é a altura sobre o solo; em Fachada, o gimbal fica
horizontal e a câmera fotografa em cada waypoint.

## Drones DJI

O catálogo traz Lito X1, Mini 4 Pro, Mini 3 Pro, Mini 3, Mini 5 Pro, Mavic 3E e Air 3S, com
os parâmetros de sensor e os códigos de drone/payload da referência (GeoWay). O KMZ segue o
layout `wpmz/template.kml` + `wpmz/waylines.wpml`, com uma foto em cada waypoint (a rota é
subdividida na distância de disparo). **Nada disso foi validado em voo**: os valores do Mini 3,
Mini 3 Pro e Air 3S já eram estimativas na referência, e a autonomia da bateria é aproximada.
Confira a missão no DJI Fly antes de decolar.

## API

| Rota | Descrição |
|---|---|
| `GET /api/drones` | Catálogo de drones, câmeras e intervalos de disparo |
| `GET /api/camera?drone=&altitude=&camera=` | GSD (cm/px) e cobertura da câmera |
| `POST /api/plan` | `{mode, geometry (GeoJSON), params}` → rota, estatísticas, avisos, velocidade, intervalo |
| `POST /api/export` | Mesmo corpo; Atom 2 devolve o `.zip` da missão, drones DJI devolvem um `.kmz` (ou um `.zip` de KMZ quando a rota passa de 195 waypoints) |
| `POST /api/import?name=arq.kml` | Corpo cru do arquivo; devolve o primeiro polígono e/ou linha |

`mode` é `waypoints`, `grid`, `double_grid`, `corridor`, `orbit` ou `facade`. `geometry`:
Polygon (grid), LineString (corridor, facade), Point (orbit), MultiPoint (waypoints).
`params.takeoff` é `[lng, lat]`. Erros de planejamento voltam como HTTP 422 com
`{"detail": "mensagem"}`; falha ou limite de consultas do serviço de elevação volta como 502.

A API não tem autenticação nem limite de uso: rode localmente ou atrás de um proxy.
