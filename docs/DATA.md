# Data sources

All data are open and public. None requires an account or an API key. Check each source for its preferred citation before reusing the data.

## NASA

| Data | Used for | Link |
|---|---|---|
| NASA POWER (MERRA-2, CERES) | Daily weather 2001–2024: temperature, radiation, humidity, wind | https://power.larc.nasa.gov/ |
| GPM IMERG | Daily rainfall | https://gpm.nasa.gov/data/imerg |
| NASADEM, 30 m | Elevation | https://lpdaac.usgs.gov/products/nasadem_hgtv001/ |
| Harmonized Landsat and Sentinel-2 (HLS) | Vegetation history of the field | https://hls.gsfc.nasa.gov/ |
| MERRA-2 | Reanalysis behind POWER | https://gmao.gsfc.nasa.gov/reanalysis/MERRA-2/ |
| NASA GIBS (MODIS Terra) | Background imagery | https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api |

## Partner agencies and other sources

| Data | Used for | Link |
|---|---|---|
| Copernicus DEM GLO-30 (ESA) | Second elevation source; height margin of error | https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM |
| Sentinel-2 L2A (ESA Copernicus) | Terrain texture | https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2 |
| ESA WorldCover 10 m | Trees, shrubs, water, built-up | https://esa-worldcover.org/ |
| ESA CCI Land Cover | Real cropland (global table and validation) | https://www.esa-landcover-cci.org/ |
| Microsoft Planetary Computer | Data access (STAC) | https://planetarycomputer.microsoft.com/ |
| Impact Observatory 10 m Annual LULC | Annual land use | https://planetarycomputer.microsoft.com/dataset/io-lulc-annual-v02 |
| USDA Cropland Data Layer | Crops by parcel (United States) | https://www.nass.usda.gov/Research_and_Science/Cropland/SARS1a.php |
| SoilGrids (ISRIC) | Soil texture and available water | https://soilgrids.org/ |
| WorldClim 2.1 | Reference climate for the global table | https://www.worldclim.org/data/worldclim21.html |
| Overture Maps | Buildings, roads, and mapped vineyards, orchards and nurseries (land use) | https://overturemaps.org/ |
| Esri World Imagery | Satellite imagery, display only | https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9 |
| Natural Earth | Country boundaries | https://www.naturalearthdata.com/ |
| Esri World Boundaries and Places | City, road and border names over the imagery | https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer |
| Nominatim (OpenStreetMap) | Place search; queried only when the user presses Search | https://nominatim.org/ |
| GGCMI Phase 3 crop calendar (Jägermeyr et al. 2021), CC-BY 4.0 | Local sowing and harvest dates | https://doi.org/10.5281/zenodo.5062513 |
| CROPGRIDS v1.08 (Tang et al. 2024), CC-BY 4.0 | Harvested area actually sown with each crop | https://doi.org/10.6084/m9.figshare.22491997 |
| GDHY (Iizumi and Sakai 2020), CC-BY 4.0 | Measured yields of maize, rice, wheat and soybean, 2007–2016 | https://doi.org/10.1594/PANGAEA.909132 |
| FAO Irrigation and Drainage Paper 56 | Evapotranspiration method | https://www.fao.org/4/x0490e/x0490e00.htm |

## What is stored in this repository

No dataset is redistributed here. Field data are downloaded on demand for the polygon the user draws. The global reference data (WorldClim, SoilGrids, ESA CCI, GGCMI, CROPGRIDS, GDHY) are downloaded from their original publishers by `python -m prospector.obtener_datos`.

## Observed versus simulated

Simulated results are always shown next to observed data for the same area: the share of land sown with each crop (CROPGRIDS) and measured yields (GDHY). Observed data never changes a simulated verdict.
