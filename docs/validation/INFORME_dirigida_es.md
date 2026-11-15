# Validación dirigida: ¿el motor reconoce cada cultivo donde de verdad se siembra?

951 puntos elegidos al azar entre las celdas donde cada cultivo ocupa al menos 2 % de la tierra (CROPGRIDS, hacia 2020), repartidos por regiones del mundo. Semilla 53. Clima: NASA POWER diario 2001-2024. Con ajuste al calendario local cuando existe. Solo mide; nada se ajustó con estos puntos.

| Cultivo | Puntos | Regiones | Se da sin riego | Solo con riego | No lo reconoce | ¿Tiene calendario local? |
|---|---|---|---|---|---|---|
| Trigo | 36 | 9 | 81 % | 17 % | 3 % | sí |
| Cebada | 36 | 9 | 64 % | 36 % | 0 % | sí |
| Avena | 27 | 6 | 93 % | 7 % | 0 % | sí |
| Maíz | 35 | 9 | 74 % | 20 % | 6 % | sí |
| Sorgo | 32 | 8 | 78 % | 12 % | 9 % | sí |
| Lenteja | 36 | 9 | 72 % | 28 % | 0 % | sí |
| Garbanzo | 36 | 9 | 83 % | 17 % | 0 % | sí |
| Arveja | 30 | 5 | 47 % | 33 % | 20 % | sí |
| Haba | 25 | 4 | 60 % | 8 % | 32 % | sí |
| Poroto (frijol) | 36 | 9 | 44 % | 56 % | 0 % | sí |
| Soya | 32 | 8 | 75 % | 22 % | 3 % | sí |
| Raps (canola) | 36 | 9 | 58 % | 31 % | 11 % | sí |
| Girasol | 32 | 8 | 53 % | 47 % | 0 % | sí |
| Papa | 35 | 9 | 60 % | 34 % | 6 % | sí |
| Quinoa | 14 | 1 | 100 % | 0 % | 0 % | no |
| Arroz | 36 | 9 | 56 % | 36 % | 8 % | sí |
| Mijo | 34 | 7 | 68 % | 29 % | 3 % | sí |
| Centeno | 22 | 3 | 86 % | 14 % | 0 % | sí |
| Maní | 32 | 8 | 78 % | 16 % | 6 % | sí |
| Algodón | 36 | 9 | 42 % | 53 % | 6 % | sí |
| Yuca (mandioca) | 30 | 6 | 83 % | 17 % | 0 % | sí |
| Tomate | 30 | 5 | 43 % | 57 % | 0 % | no |
| Ají y pimiento | 30 | 5 | 50 % | 23 % | 27 % | no |
| Cebolla | 35 | 7 | 66 % | 31 % | 3 % | no |
| Repollo | 29 | 6 | 62 % | 21 % | 17 % | no |
| Sandía | 30 | 6 | 87 % | 10 % | 3 % | no |
| Remolacha azucarera | 34 | 7 | 65 % | 35 % | 0 % | no |
| Cártamo | 32 | 4 | 59 % | 31 % | 9 % | no |
| Tabaco | 33 | 7 | 64 % | 30 % | 6 % | no |
| Alfalfa | 30 | 1 | 50 % | 50 % | 0 % | no |
| **Todos** | 951 | | **66 %** | **28 %** | **6 %** | |

«No lo reconoce» es el error que importa: el cultivo se siembra ahí y el motor dice que no se da ni con riego.
Límite: CROPGRIDS reparte estadísticas nacionales y regionales sobre mapas de tierra cultivada; en celdas aisladas puede atribuir un cultivo que no está exactamente ahí.
