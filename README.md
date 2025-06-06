# Financial PDF Scraper

### Requirements

- Python: 3.10
  - poetry <2.0.0
    ```shell
    pip install "poetry<2.0.0"
    ```
  - Dependencies: see pyproject.toml

### Set up Python Virtual Environment

```shell
poetry install [--no-dev]
```

### Command Examples

```shell
# scrap a Japanese quarterly financial report (and debug)
poetry run python scripts/scrap_jqfr.py \
  in_file.pdf \
  [--debug debug.pdf]
```
