# Monitoring Configurations

This directory contains **cloud-agnostic** monitoring configurations for the Trading Platform.

## 📁 Directory Structure

```
monitoring/
├── grafana/
│   ├── dashboards/              # Dashboard JSON files
│   │   ├── dashboards.yml       # Dashboard provisioning config
│   │   └── market-data.json     # Real-time crypto prices dashboard
│   │
│   ├── provisioning/            # Grafana provisioning configs
│   │   └── datasources.yml      # Datasource definitions (ClickHouse, Prometheus, PostgreSQL)
│   │
│   └── alerts/                  # Alert rules (future)
│       └── .gitkeep
│
└── prometheus/
    └── prometheus.yml           # Prometheus scrape configuration
```

## 🎯 Purpose

**Separation of Concerns:**
- `/monitoring/` = **WHAT** to monitor (dashboards, metrics, alerts) - **Cloud-agnostic**
- `/infrastructure/` = **HOW** to deploy (Docker, K8s, Cloud) - **Infrastructure-specific**

## 🚀 Usage

### Local Development (Docker)

Mounted automatically via docker-compose:

```yaml
# infrastructure/docker/docker-compose.yml
grafana:
  volumes:
    - ../../monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
    - ../../monitoring/grafana/provisioning:/etc/grafana/provisioning/datasources:ro
```

### Cloud Deployment

#### Grafana Cloud
1. Export dashboards: `monitoring/grafana/dashboards/*.json`
2. Import to Grafana Cloud UI or via API

#### AWS Managed Grafana
```bash
aws grafana create-workspace-api-key --workspace-id <id>
# Upload dashboards via API
```

#### Self-hosted Grafana (K8s)
```yaml
# ConfigMap from monitoring configs
kubectl create configmap grafana-dashboards \
  --from-file=monitoring/grafana/dashboards/
```

## 📊 Available Dashboards

### 1. Market Data - Real-time Crypto Prices
- **UID**: `market-data-realtime`
- **URL**: http://localhost:3000/d/market-data-realtime
- **Panels**:
  - Real-time BTC & ETH price chart
  - Latest price stats
  - Trade count metrics
  - Trading volume bars
  - Recent trades table
- **Refresh**: 5 seconds
- **Datasource**: ClickHouse

## 🔧 Adding New Dashboards

1. **Create dashboard** in Grafana UI
2. **Export JSON**:
   ```bash
   # Via UI: Dashboard settings → JSON Model → Copy
   # Or via API:
   curl -u admin:admin http://localhost:3000/api/dashboards/uid/DASHBOARD_UID \
     | jq '.dashboard' > monitoring/grafana/dashboards/new-dashboard.json
   ```

3. **Commit to Git**:
   ```bash
   git add monitoring/grafana/dashboards/new-dashboard.json
   git commit -m "Add new dashboard: XYZ"
   ```

4. **Auto-loaded** on next Grafana restart

## 📝 Datasources

Configured in `monitoring/grafana/provisioning/datasources.yml`:

- **ClickHouse** (default) - Time-series market data
- **Prometheus** - Metrics collection
- **PostgreSQL** - Relational metadata

## 🔄 Prometheus Configuration

Located in `monitoring/prometheus/prometheus.yml`:

- Scrape intervals
- Target endpoints
- Recording rules (future)
- Alert rules (future)

## 🚨 Alerts (Future - Phase 6)

```
monitoring/grafana/alerts/
├── price-alerts.yml          # Price spike detection
├── trading-alerts.yml        # Strategy performance alerts
└── infrastructure-alerts.yml # System health alerts
```

## 📚 References

- [Grafana Provisioning Docs](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Prometheus Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [ClickHouse Grafana Plugin](https://grafana.com/grafana/plugins/grafana-clickhouse-datasource/)
