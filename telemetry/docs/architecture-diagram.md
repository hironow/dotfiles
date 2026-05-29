# Architecture Diagram

## Data Flow Diagram

```mermaid
graph LR
    FA[FastAPI App<br/>:8000] -->|OTLP gRPC<br/>localhost:4317| OC[OpenTelemetry<br/>Collector<br/>:4317/:4318]
    
    OC -->|Push traces<br/>tempo:4317| T[Tempo<br/>:3200]
    OC -->|Push logs<br/>loki:3100| L[Loki<br/>:3100]
    OC -.->|Expose metrics<br/>:8889| P[Prometheus<br/>:9091]
    
    P -->|Scrape<br/>otel-collector:8889| OC
    
    G[Grafana<br/>:3010] -->|Query| P
    G -->|Query| T
    G -->|Query| L
    
    style FA fill:#e1f5fe
    style OC fill:#fff3e0
    style P fill:#f3e5f5
    style T fill:#e8f5e9
    style L fill:#fce4ec
    style G fill:#fffde7
```

## Port Mapping Summary

```
Host Machine                    Docker Network
============                    ==============
                               
FastAPI (:8000) ──┐            
                  │            
    localhost:4317├──────────> OTel Collector (:4317)
                               ├─> Tempo (:4317)
                               ├─> Loki (:3100)
                               └─> Prometheus (scrapes :8889)
                               
    localhost:3010 ──────────> Grafana (:3000)
    localhost:9091 ──────────> Prometheus (:9090)
    localhost:3200 ──────────> Tempo (:3200)
    localhost:3100 ──────────> Loki (:3100)
```
