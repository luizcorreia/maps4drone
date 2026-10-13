# Interface web

Página única (Leaflet, sem build) servida por uma API FastAPI que reutiliza o núcleo.

```sh
uv pip install -e ".[web]"
maps4drone-web --port 8000      # http://127.0.0.1:8000
```

## Uso

1. Escolha o modo (Waypoints, Grid, Double Grid, Corredor, Fachada, Órbita).
2. Clique no mapa para marcar pontos. Arraste para mover; botão direito num ponto remove
   (no celular, use "Desfazer último ponto"). Também dá para importar KML/KMZ/GeoJSON.
3. Ajuste os parâmetros: a rota e as estatísticas são recalculadas sozinhas.
4. Com "Acompanhar terreno", defina o ponto de decolagem no mapa. A elevação vem da API
   Open-Meteo (precisa de internet).
5. "Baixar missão" gera um `.zip` com `global.json`, `<id>.json` e um `README.txt`.
   Siga o passo a passo de substituição da missão dummy em [atom2-format.md](atom2-format.md).

Nos modos Órbita, a "Altitude" é a altura do voo. Em Fachada, o gimbal fica horizontal e
a câmera fotografa em cada waypoint.

## API

| Rota | Descrição |
|---|---|
| `GET /api/drones` | Catálogo de drones, câmeras e intervalos de disparo |
| `GET /api/camera?drone=&altitude=&camera=` | GSD (cm/px) e cobertura da câmera |
| `POST /api/plan` | `{mode, geometry (GeoJSON), params}` → rota, estatísticas, avisos, velocidade, intervalo |
| `POST /api/export` | Mesmo corpo; devolve o `.zip` da missão |
| `POST /api/import?name=arq.kml` | Corpo cru do arquivo; devolve o primeiro polígono e/ou linha |

`mode` é `waypoints`, `grid`, `double_grid`, `corridor`, `orbit` ou `facade`. `geometry`:
Polygon (grid), LineString (corridor, facade), Point (orbit), MultiPoint (waypoints).
`params.takeoff` é `[lng, lat]`. Erros de planejamento voltam como HTTP 422 com
`{"detail": "mensagem"}`; falha de rede na elevação volta como 502.

A API não tem autenticação nem limite de uso: rode localmente ou atrás de um proxy.
