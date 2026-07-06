# YAML patterns

## Basic mapping

```yaml
app:
  name: sample
  port: 8080
  debug: false
```

## Sequence of mappings

```yaml
services:
  - name: api
    image: example/api:latest
  - name: worker
    image: example/worker:latest
```

## Multiline string

```yaml
message: |
  first line
  second line
```

## Optional nested section

```yaml
database:
  host: localhost
  port: 5432
  credentials:
    username: app
    password: "${DB_PASSWORD}"
```

## Multi-document YAML

```yaml
---
kind: ConfigMap
metadata:
  name: app-config
---
kind: Secret
metadata:
  name: app-secret
```
