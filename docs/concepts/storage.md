# Storage And Data Layout

`BIOINFOFLOW_HOME` is Bioinfoflow's platform data root. It is a normal directory on the host machine or server.

The current backend settings resolve it this way:

- Docker Compose default: `${PWD}/data`
- backend code default for local development: repo-root `data`
- explicit override: `BIOINFOFLOW_HOME=/absolute/path`

Relative `BIOINFOFLOW_HOME` values are resolved to an absolute path by the backend. For Docker, prefer leaving it unset or setting an absolute path.

## Platform Roots

The backend exposes these roots from `backend/app/config.py` and `backend/app/path_layout.py`:

```text
BIOINFOFLOW_HOME/
  state/
    bioinfoflow.db
    auth/better-auth.db
    workflows/
    run_uploads/
    engine/cache/nextflow/
    engine/cache/miniwdl/
  projects/
  sources/
    deliveries/
    reference/
    database/
```

The backend creates the platform roots during application startup. Project and run directories are created when projects and runs are created.

## User-Facing Storage Zones

| Zone | Backing path | Use it for |
| --- | --- | --- |
| Project Data | `BIOINFOFLOW_HOME/projects/<project_id>/data` | project-private manifests, helper files, small uploaded inputs |
| Run Results | `BIOINFOFLOW_HOME/projects/<project_id>/runs/<run_id>/results` | outputs produced by a run |
| Deliveries | `BIOINFOFLOW_HOME/sources/deliveries` | incoming FASTQ/BAM/VCF files from instruments or collaborators |
| Reference Library | `BIOINFOFLOW_HOME/sources/reference` | FASTA, indexes, BED/GTF, known-sites VCFs, and reusable references |
| Database | `BIOINFOFLOW_HOME/sources/database` | shared database-style resources exposed as managed assets |

## Asset URIs

The run compiler resolves storage-backed inputs from asset URIs:

```text
asset://project/...
asset://results/<run_id>/...
asset://deliveries/...
asset://reference/...
asset://database/...
asset://run_upload/...
```

Resolution is implemented in `backend/app/path_layout.py`:

- `asset://project/...` resolves under the current project's `data/` directory.
- `asset://deliveries/...` resolves under `sources/deliveries/`.
- `asset://reference/...` resolves under `sources/reference/`.
- `asset://database/...` resolves under `sources/database/`.
- `asset://run_upload/...` resolves under per-project run upload staging.
- `asset://results/<run_id>/...` resolves under a run's `results/` directory.

Each resolver keeps paths inside its allowed root and rejects escaping paths.

## Run Layout

For a managed project, each run lives under:

```text
BIOINFOFLOW_HOME/projects/<project_id>/runs/<run_id>/
  input/
    request/
    materialized/
    attachments/
  engine/
    nextflow/work/
    wdl/work/
  results/
  audit/
```

The exact engine directory is normalized from the workflow engine name.

## Path Contract v3

Docker execution relies on an identity mount:

```text
host BIOINFOFLOW_HOME == container BIOINFOFLOW_HOME
```

Compose implements this as:

```yaml
- ${BIOINFOFLOW_HOME:-${PWD}/data}:${BIOINFOFLOW_HOME:-${PWD}/data}
```

The backend checks `BIOINFOFLOW_HOME_HOST` against `BIOINFOFLOW_HOME` at startup. If they differ, startup fails with a Path Contract v3 error.

This contract is what lets Nextflow, MiniWDL, backend code, and task containers share absolute paths without translation.
