# Deployment

## What one instance needs

| Resource | Amount |
|---|---|
| CPU | 2 cores |
| Memory | 4 GB |
| Disk | about 4 GB: the Docker image is 1.7 GB, the global reference data 280 MB, and the cache of analysed fields grows with use (tens of MB per field) |
| Network | outbound HTTPS to the open data services; no API key or account |

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8790` | Port of the service (Docker image) |
| `PROSPECTOR_CACHE` | `prospector/cache` | Working folder: one sub-folder per analysed field. Mount a persistent volume here |
| `PROSPECTOR_DATOS` | `prospector/mundo_datos` | Global reference data. Read-only after the first download |

## Single server

```bash
docker compose up -d --build
docker compose exec prospector python -m prospector.obtener_datos    # once
```

The container starts in about 5 seconds. A new field takes several minutes to analyse the first time (the terrain appears within about a minute; the vegetation history is the slow part); after that it is served from the cache.

Put a reverse proxy with TLS in front (Caddy, nginx or the provider's load balancer). `GET /api/salud` is the health check; the image declares it as `HEALTHCHECK`. Responses are gzip-compressed by the service.

## Cloud

The image is a standard container that listens on `$PORT`, so it runs on any container service. Two points decide which one fits:

- **It needs a persistent volume** for `/data`. Services with only ephemeral disk lose the cache and the reference data on restart.
- **It must run as one instance with one worker** in its current form (see below).

A small virtual machine with Docker, or a container service with a mounted volume and the instance count fixed at one, is the right target today.

## Current limits for public, multi-user use

These are real limits of the code as submitted. They are listed so nobody deploys it as a public service by mistake.

1. **One analysis at a time.** Jobs are tracked in the memory of the process, and a new analysis pauses the one in progress. Several users starting fields at once would interrupt each other. Reading results of fields already analysed is not affected.
2. **No accounts.** `GET /api/areas` lists every field analysed on the instance. On a shared instance, users would see each other's fields. Put the service behind authentication, or give each group its own instance.
3. **The cache grows without limit.** There is no automatic clean-up of old fields.
4. **Upstream services set the pace.** Each new field reads from NASA POWER, Microsoft Planetary Computer, Overture and SoilGrids. Their rate limits apply to the instance as a whole.
5. **The interface is in Spanish** and designed for a desktop screen.

## Path to scale

In order of value:

1. **Job queue and workers.** Move analyses out of the web process into workers fed by a queue (for example Redis with RQ or Celery). The web tier becomes stateless and can run several replicas.
2. **Shared storage.** Keep the per-field folders in object storage, so any replica can serve any field. Results are immutable files keyed by the polygon hash, which makes them cacheable by a CDN.
3. **Accounts and per-user field lists.**
4. **Regional mirrors of the heavy inputs.** The global reference data is static and can ship with the image or sit in object storage. Weather for a point can be cached by 0.5° cell, since NASA POWER has that resolution.
5. **Cache eviction** by age and size.
6. **Translations and a phone layout.**
