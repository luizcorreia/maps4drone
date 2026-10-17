# Plugin QGIS

O plugin é uma camada fina sobre o núcleo Python: expõe quatro algoritmos do Processing
(Caixa de Ferramentas, modelos gráficos e Python) e um botão que abre um lançador.

| Algoritmo | Entrada |
|---|---|
| `maps4drone:survey_grid` | camada de polígonos (aceita "somente feições selecionadas"); ângulo (em branco = ao longo do eixo maior da área (retângulo mínimo rotacionado)), sobreposições, intervalo, grid duplo, margem |
| `maps4drone:corridor` | camada de linhas; número ímpar de passadas |
| `maps4drone:orbit` | ponto central, raio, altura, nº de pontos |
| `maps4drone:facade` (experimental) | pontos A e B da base da parede, altura, distância |

Saídas: camada de linha da rota, camada de pontos dos waypoints (atributos `height`,
`speed`, `pitch`, `yaw`, `action`, `hover_s`), o resumo (waypoints, distância, tempo,
baterias, imagens, avisos) no log, e a pasta da missão do Atom 2 em "Escrever nova pasta
de missão" ou sobrescrevendo uma pasta já criada pelo app em "Sobrescrever pasta
existente" (o fluxo da missão dummy, veja o README).

Terrain follow: informe um raster DEM (qualquer CRS) **e** o ponto de decolagem. As alturas
saem relativas à decolagem, como o drone espera. Sem DEM, a altura é fixa.

A camada de entrada pode estar em qualquer CRS; ela é reprojetada para EPSG:4326
internamente. O intervalo de disparo **não** vai no arquivo do Atom 2: configure o
temporizador da câmera no app.

## Requisitos

- QGIS 3.28 ou superior (inclui QGIS 4 / Qt6). O núcleo exige **Python 3.9+**, o que cobre o QGIS 3.28
  em diante; com Python mais antigo o plugin avisa e não carrega.
- `shapely>=2` e `pyproj` no Python do QGIS. O QGIS já traz `pyproj`; `shapely` costuma
  faltar:

  ```sh
  python -m pip install shapely          # use o Python do QGIS
  ```

  No Windows (OSGeo4W Shell): `python -m pip install shapely`. No Linux, com o QGIS do
  sistema: `pip install --user shapely` ou o pacote da distro (`python-shapely`).
  Se algo faltar, o botão do plugin mostra a mensagem com o comando.

O núcleo `maps4drone` já vai dentro do zip (pasta `vendor/`), não precisa instalar.

## Gerar e instalar

```sh
.venv/bin/python scripts/build_qgis_plugin.py          # gera dist/maps4drone-qgis-<versão>.zip
```

No QGIS: Complementos > Gerenciar e instalar > Instalar a partir de ZIP.

Para desenvolver sem zip, copie ou faça link simbólico de `qgis_plugin/maps4drone_qgis`
para a pasta de plugins do perfil e deixe o núcleo instalado no Python do QGIS
(`pip install -e .`); sem `vendor/`, o plugin usa o `maps4drone` instalado.

A pasta do plugin se chama `maps4drone_qgis` (e não `maps4drone`) porque o QGIS importa o
plugin pelo nome da pasta, o que colidiria com o pacote `maps4drone` do núcleo.

## Testes

`pytest tests/test_qgis_plugin.py` roda sem QGIS os testes de conversão, metadados e do
zip; os testes que usam o QGIS são pulados. Para rodá-los, use o Python do QGIS com
shapely, pyproj e pytest disponíveis:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m pytest tests/test_qgis_plugin.py
```
