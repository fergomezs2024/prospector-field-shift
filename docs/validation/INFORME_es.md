# Validación mundial del motor de cultivos

Puntos evaluados: **270 en tierras de cultivo** y **90 en tierras sin ningún cultivo**, repartidos por igual en 9 regiones del mundo (muestra al azar con semilla fija, de la tabla mundial de 10 minutos de arco). Clima: NASA POWER diario 2001-2024 de cada punto. Este informe solo mide; ningún parámetro se ajustó con estos resultados.

## A. Motor general (parámetros de literatura, sin calendario local)

Comparación con el calendario mundial GGCMI en los puntos de cultivo. Elegir la fecha al azar daría una diferencia mediana de unos 91 días.

| Cultivo | Puntos | Diferencia mediana de siembra (días) | Dentro de 30 días | Dentro de 60 días | Diferencia mediana de ciclo (días) | Sesgo de ciclo (días) |
|---|---|---|---|---|---|---|
| Algodón | 168 | 84 | 19 % | 36 % | 64 | -54 |
| Arroz | 197 | 46 | 37 % | 60 % | 36 | +8 |
| Arveja | 270 | 108 | 14 % | 31 % | 68 | -50 |
| Cebada | 270 | 74 | 15 % | 41 % | 67 | -60 |
| Centeno | 270 | 61 | 30 % | 44 % | 90 | -90 |
| Girasol | 250 | 66 | 25 % | 46 % | 50 | -20 |
| Maní | 211 | 61 | 30 % | 48 % | 43 | -28 |
| Maíz | 211 | 68 | 28 % | 47 % | 44 | +21 |
| Mijo | 251 | 76 | 23 % | 37 % | 65 | -27 |
| Papa | 269 | 94 | 10 % | 28 % | 71 | -42 |
| Poroto (frijol) | 251 | 91 | 14 % | 31 % | 65 | -2 |
| Raps (canola) | 263 | 76 | 24 % | 44 % | 55 | -25 |
| Sorgo | 213 | 60 | 34 % | 54 % | 54 | -30 |
| Soya | 226 | 85 | 24 % | 42 % | 42 | -7 |
| Trigo | 269 | 56 | 24 % | 57 % | 58 | -52 |
| Yuca (mandioca) | 86 | 61 | 29 % | 49 % | 16 | -13 |
| **Todos** | 3675 | **75** | **23 %** | **43 %** | | |

## C. Motor con calibración local (ciclo ajustado al calendario de la zona)

Comparación con el calendario mundial GGCMI en los puntos de cultivo. Elegir la fecha al azar daría una diferencia mediana de unos 91 días.

| Cultivo | Puntos | Diferencia mediana de siembra (días) | Dentro de 30 días | Dentro de 60 días | Diferencia mediana de ciclo (días) | Sesgo de ciclo (días) |
|---|---|---|---|---|---|---|
| Algodón | 207 | 56 | 44 % | 53 % | 41 | -28 |
| Arroz | 222 | 14 | 57 % | 66 % | 10 | +0 |
| Arveja | 270 | 76 | 31 % | 43 % | 59 | -40 |
| Cebada | 270 | 60 | 37 % | 51 % | 44 | -38 |
| Centeno | 270 | 30 | 50 % | 61 % | 42 | -38 |
| Girasol | 269 | 0 | 54 % | 61 % | 42 | -6 |
| Maní | 238 | 0 | 57 % | 62 % | 30 | -17 |
| Maíz | 252 | 0 | 56 % | 65 % | 14 | +1 |
| Mijo | 268 | 0 | 63 % | 68 % | 49 | -16 |
| Papa | 270 | 75 | 33 % | 43 % | 55 | -42 |
| Poroto (frijol) | 268 | 62 | 38 % | 49 % | 51 | -12 |
| Raps (canola) | 269 | 41 | 48 % | 60 % | 29 | -1 |
| Sorgo | 259 | 0 | 67 % | 71 % | 24 | -5 |
| Soya | 263 | 0 | 62 % | 67 % | 17 | -1 |
| Trigo | 270 | 44 | 41 % | 73 % | 32 | -26 |
| Yuca (mandioca) | 130 | 22 | 58 % | 71 % | 13 | +8 |
| **Todos** | 3995 | **33** | **49 %** | **60 %** | | |

Ojo: en este modo el motor conoce la fecha local y la adopta cuando rinde casi lo mismo, así que la coincidencia de siembra no es una prueba independiente; sí lo es que el veredicto no empeore (sección B).

## B. ¿El veredicto «se da» coincide con lo que se cultiva de verdad?

Uso real: ESA CCI Land Cover 2020. «Secano» = tierras de cultivo con menos de 10 % de riego. Se cuenta si el motor encuentra **al menos un cultivo que se da sin riego**.

| Grupo de puntos | Puntos | Motor general: algo se da sin riego | Con calibración local: algo se da sin riego |
|---|---|---|---|
| Tierras de cultivo de secano | 235 | 96 % | 94 % |
| Tierras de cultivo con riego (≥ 30 %) | 23 | 83 % | 78 % |
| Sin ningún cultivo | 90 | 46 % | 49 % |
| Sin cultivo y áridas (menos de 250 mm al año) | 27 | 0 % | 0 % |

Lectura: en secano el porcentaje debería ser alto (el motor reconoce que ahí se puede cultivar); en tierras áridas sin cultivo debería ser cercano a cero. En «sin ningún cultivo» no se espera cero: hay bosques, praderas y ciudades donde el clima sí permite cultivar.

### Por región (tierras de cultivo de secano)

| Región | Puntos | Motor general | Con calibración local |
|---|---|---|---|
| América Latina | 30 | 100 % | 100 % |
| América del Norte | 30 | 97 % | 97 % |
| Asia del Este y Sudeste | 22 | 100 % | 100 % |
| Asia del Sur | 9 | 100 % | 100 % |
| Europa | 28 | 100 % | 96 % |
| Oceanía | 30 | 97 % | 87 % |
| Rusia y Asia Central | 29 | 97 % | 97 % |
| África del Norte y Medio Oriente | 29 | 79 % | 76 % |
| África subsahariana | 28 | 100 % | 100 % |

## E. Cultivo por cultivo: ¿el motor dice «se da» donde ese cultivo se siembra de verdad?

Dato real: CROPGRIDS (superficie cosechada hacia 2020, celdas de 5,6 km). «Se siembra» = el cultivo ocupa al menos 1 % de la tierra en los 28 km alrededor del punto. Acierto = el motor (con calibración local) dice que se da sin riego o solo con riego. «Ausente» = menos de 0,05 %.

| Cultivo | Puntos donde se siembra | El motor dice que se da sin riego | …o solo con riego | No lo reconoce | Puntos donde está ausente | Ahí el motor dice que se daría |
|---|---|---|---|---|---|---|
| Algodón | 35 | 77 % | 20 % | 3 % | 195 | 29 % |
| Arroz | 76 | 75 % | 17 % | 8 % | 157 | 14 % |
| Arveja | 13 | 69 % | 31 % | 0 % | 139 | 41 % |
| Cebada | 111 | 84 % | 16 % | 0 % | 134 | 73 % |
| Girasol | 28 | 82 % | 18 % | 0 % | 191 | 69 % |
| Maní | 41 | 100 % | 0 % | 0 % | 188 | 32 % |
| Maíz | 149 | 75 % | 15 % | 10 % | 75 | 25 % |
| Mijo | 37 | 100 % | 0 % | 0 % | 187 | 71 % |
| Papa | 29 | 66 % | 34 % | 0 % | 144 | 40 % |
| Poroto (frijol) | 38 | 87 % | 11 % | 3 % | 153 | 44 % |
| Raps (canola) | 64 | 73 % | 25 % | 2 % | 156 | 68 % |
| Sorgo | 49 | 96 % | 2 % | 2 % | 156 | 39 % |
| Soya | 77 | 81 % | 13 % | 6 % | 153 | 46 % |
| Trigo | 159 | 81 % | 18 % | 1 % | 84 | 80 % |
| Yuca (mandioca) | 13 | 92 % | 0 % | 8 % | 220 | 13 % |
| **Todos** | 919 | **81 %** | **15 %** | **3 %** | | |

La última columna no es un error por sí sola: un cultivo puede darse y no sembrarse por mercado, costumbre o falta de agua de riego. Sí lo es la columna «No lo reconoce».

## D. Qué cambia la calibración local

De 3675 casos (cultivo × punto con calendario): en 91 % el veredicto no cambia, en 3 % pasa a «se da» y en 6 % deja de darse.

## Límites de esta validación

- El calendario GGCMI es una grilla de 0,5° (unos 55 km) con fechas por mes y con vacíos rellenados: no dice si el cultivo se siembra realmente en cada punto.
- El uso del suelo dice que hay cultivos, no cuáles. No hay contraste con rendimientos medidos (toneladas por hectárea).
- El suelo de cada punto viene de SoilGrids a 10 minutos de arco; el relieve del lugar no entra en esta prueba.
- Los parámetros de los cultivos siguen siendo valores generales de FAO; esta prueba mide cuánto se equivocan, no los corrige.
