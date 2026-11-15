# Validación mundial del motor de cultivos

Puntos evaluados: **270 en tierras de cultivo** y **90 en tierras sin ningún cultivo**, repartidos por igual en 9 regiones del mundo (muestra al azar con semilla fija, de la tabla mundial de 10 minutos de arco). Clima: NASA POWER diario 2001-2024 de cada punto. Este informe solo mide; ningún parámetro se ajustó con estos resultados.

## A. Motor general (parámetros de literatura, sin calendario local)

Comparación con el calendario mundial GGCMI en los puntos de cultivo. Elegir la fecha al azar daría una diferencia mediana de unos 91 días.

| Cultivo | Puntos | Diferencia mediana de siembra (días) | Dentro de 30 días | Dentro de 60 días | Diferencia mediana de ciclo (días) | Sesgo de ciclo (días) |
|---|---|---|---|---|---|---|
| Algodón | 164 | 59 | 28 % | 52 % | 58 | -56 |
| Arroz | 187 | 44 | 45 % | 60 % | 34 | +6 |
| Arveja | 270 | 94 | 20 % | 36 % | 65 | -54 |
| Cebada | 270 | 74 | 21 % | 41 % | 65 | -63 |
| Centeno | 270 | 61 | 33 % | 48 % | 81 | -81 |
| Girasol | 259 | 61 | 29 % | 49 % | 47 | -30 |
| Maní | 212 | 61 | 33 % | 49 % | 44 | -26 |
| Maíz | 212 | 60 | 32 % | 50 % | 40 | +12 |
| Mijo | 257 | 36 | 46 % | 70 % | 69 | -62 |
| Papa | 270 | 76 | 19 % | 40 % | 68 | -56 |
| Poroto (frijol) | 257 | 76 | 23 % | 41 % | 49 | -22 |
| Raps (canola) | 264 | 76 | 27 % | 42 % | 48 | -24 |
| Sorgo | 220 | 59 | 36 % | 53 % | 53 | -28 |
| Soya | 239 | 62 | 31 % | 46 % | 31 | -8 |
| Trigo | 270 | 44 | 37 % | 68 % | 47 | -40 |
| Yuca (mandioca) | 80 | 58 | 36 % | 51 % | 20 | -18 |
| **Todos** | 3701 | **61** | **30 %** | **50 %** | | |

## C. Motor con calibración local (ciclo ajustado al calendario de la zona)

Comparación con el calendario mundial GGCMI en los puntos de cultivo. Elegir la fecha al azar daría una diferencia mediana de unos 91 días.

| Cultivo | Puntos | Diferencia mediana de siembra (días) | Dentro de 30 días | Dentro de 60 días | Diferencia mediana de ciclo (días) | Sesgo de ciclo (días) |
|---|---|---|---|---|---|---|
| Algodón | 203 | 32 | 48 % | 67 % | 35 | -29 |
| Arroz | 227 | 15 | 59 % | 70 % | 13 | +0 |
| Arveja | 270 | 76 | 31 % | 44 % | 50 | -34 |
| Cebada | 270 | 61 | 33 % | 47 % | 40 | -39 |
| Centeno | 270 | 33 | 49 % | 61 % | 42 | -38 |
| Girasol | 270 | 26 | 53 % | 63 % | 36 | -6 |
| Maní | 245 | 29 | 53 % | 62 % | 26 | -12 |
| Maíz | 258 | 6 | 57 % | 67 % | 11 | +1 |
| Mijo | 270 | 0 | 71 % | 84 % | 40 | -34 |
| Papa | 270 | 74 | 33 % | 46 % | 52 | -39 |
| Poroto (frijol) | 270 | 46 | 44 % | 56 % | 36 | -16 |
| Raps (canola) | 269 | 48 | 44 % | 55 % | 25 | -7 |
| Sorgo | 262 | 0 | 59 % | 69 % | 28 | -8 |
| Soya | 264 | 0 | 64 % | 73 % | 12 | +0 |
| Trigo | 270 | 31 | 50 % | 79 % | 22 | -18 |
| Yuca (mandioca) | 122 | 0 | 68 % | 76 % | 10 | +4 |
| **Todos** | 4010 | **30** | **50 %** | **63 %** | | |

Ojo: en este modo el motor conoce la fecha local y la adopta cuando rinde casi lo mismo, así que la coincidencia de siembra no es una prueba independiente; sí lo es que el veredicto no empeore (sección B).

## B. ¿El veredicto «se da» coincide con lo que se cultiva de verdad?

Uso real: ESA CCI Land Cover 2020. «Secano» = tierras de cultivo con menos de 10 % de riego. Se cuenta si el motor encuentra **al menos un cultivo que se da sin riego**.

| Grupo de puntos | Puntos | Motor general: algo se da sin riego | Con calibración local: algo se da sin riego |
|---|---|---|---|
| Tierras de cultivo de secano | 239 | 88 % | 91 % |
| Tierras de cultivo con riego (≥ 30 %) | 27 | 81 % | 85 % |
| Sin ningún cultivo | 90 | 52 % | 59 % |
| Sin cultivo y áridas (menos de 250 mm al año) | 25 | 0 % | 0 % |

Lectura: en secano el porcentaje debería ser alto (el motor reconoce que ahí se puede cultivar); en tierras áridas sin cultivo debería ser cercano a cero. En «sin ningún cultivo» no se espera cero: hay bosques, praderas y ciudades donde el clima sí permite cultivar.

### Por región (tierras de cultivo de secano)

| Región | Puntos | Motor general | Con calibración local |
|---|---|---|---|
| América Latina | 30 | 100 % | 100 % |
| América del Norte | 30 | 97 % | 97 % |
| Asia del Este y Sudeste | 19 | 100 % | 100 % |
| Asia del Sur | 16 | 88 % | 94 % |
| Europa | 29 | 100 % | 100 % |
| Oceanía | 29 | 90 % | 83 % |
| Rusia y Asia Central | 29 | 69 % | 93 % |
| África del Norte y Medio Oriente | 29 | 55 % | 55 % |
| África subsahariana | 28 | 100 % | 100 % |

## E. Cultivo por cultivo: ¿el motor dice «se da» donde ese cultivo se siembra de verdad?

Dato real: CROPGRIDS (superficie cosechada hacia 2020, celdas de 5,6 km). «Se siembra» = el cultivo ocupa al menos 1 % de la tierra en los 28 km alrededor del punto. Acierto = el motor (con calibración local) dice que se da sin riego o solo con riego. «Ausente» = menos de 0,05 %.

| Cultivo | Puntos donde se siembra | El motor dice que se da sin riego | …o solo con riego | No lo reconoce | Puntos donde está ausente | Ahí el motor dice que se daría |
|---|---|---|---|---|---|---|
| Algodón | 31 | 71 % | 19 % | 10 % | 197 | 30 % |
| Arroz | 69 | 72 % | 7 % | 20 % | 158 | 13 % |
| Arveja | 8 | 12 % | 38 % | 50 % | 146 | 32 % |
| Cebada | 98 | 73 % | 26 % | 1 % | 139 | 74 % |
| Girasol | 26 | 77 % | 15 % | 8 % | 188 | 65 % |
| Maní | 31 | 97 % | 3 % | 0 % | 196 | 38 % |
| Maíz | 156 | 77 % | 13 % | 10 % | 73 | 19 % |
| Mijo | 25 | 96 % | 0 % | 4 % | 197 | 48 % |
| Papa | 41 | 56 % | 37 % | 7 % | 150 | 41 % |
| Poroto (frijol) | 32 | 81 % | 16 % | 3 % | 162 | 36 % |
| Raps (canola) | 59 | 51 % | 29 % | 20 % | 161 | 51 % |
| Sorgo | 40 | 95 % | 2 % | 2 % | 167 | 51 % |
| Soya | 85 | 89 % | 7 % | 4 % | 150 | 47 % |
| Trigo | 155 | 75 % | 24 % | 1 % | 89 | 80 % |
| Yuca (mandioca) | 14 | 100 % | 0 % | 0 % | 221 | 17 % |
| **Todos** | 870 | **76 %** | **17 %** | **7 %** | | |

La última columna no es un error por sí sola: un cultivo puede darse y no sembrarse por mercado, costumbre o falta de agua de riego. Sí lo es la columna «No lo reconoce».

## D. Qué cambia la calibración local

De 3701 casos (cultivo × punto con calendario): en 90 % el veredicto no cambia, en 3 % pasa a «se da» y en 7 % deja de darse.

## Límites de esta validación

- El calendario GGCMI es una grilla de 0,5° (unos 55 km) con fechas por mes y con vacíos rellenados: no dice si el cultivo se siembra realmente en cada punto.
- El uso del suelo dice que hay cultivos, no cuáles. No hay contraste con rendimientos medidos (toneladas por hectárea).
- El suelo de cada punto viene de SoilGrids a 10 minutos de arco; el relieve del lugar no entra en esta prueba.
- Los parámetros de los cultivos siguen siendo valores generales de FAO; esta prueba mide cuánto se equivocan, no los corrige.
