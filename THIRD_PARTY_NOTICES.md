# Third-party notices

Local Agent Studio depends on open-source libraries installed from Python package indexes. They are not copied from Siver or wxautox4.

| Component | Purpose | License / source |
|---|---|---|
| FastAPI / Starlette | HTTP service | MIT / BSD-3-Clause |
| SQLAlchemy / Alembic | Database and migrations | MIT |
| LlamaIndex Core | Ingestion and text splitting | MIT |
| Jinja2 | Server-rendered admin UI | BSD-3-Clause |
| HTTPX | Upstream model calls | BSD-3-Clause |
| pypdf | PDF text extraction | BSD-3-Clause |
| python-docx | DOCX text extraction | MIT |
| Uvicorn | ASGI server | BSD-3-Clause |

Release automation must generate a machine-readable SBOM and re-check resolved dependency licenses before publishing.

Siver and wxautox4 are external connector-side products. They are not dependencies, submodules, vendored assets, or distributable parts of this repository.
