FINOPS_DASHBOARD_JSON = """{
  "title": "CNP FinOps Dashboard",
  "uid": "cnp-finops",
  "schemaVersion": 38,
  "tags": ["finops", "cnp"],
  "panels": [
    {
      "type": "timeseries",
      "title": "CPU consommé par namespace (cores)",
      "gridPos": { "x": 0, "y": 0, "w": 12, "h": 8 },
      "targets": [
        {
          "expr": "sum by (namespace) (rate(container_cpu_usage_seconds_total{namespace!=''}[5m]))",
          "legendFormat": "{{namespace}}"
        }
      ],
      "datasource": { "type": "prometheus", "uid": "prometheus" }
    },
    {
      "type": "timeseries",
      "title": "RAM consommée par namespace (Mo)",
      "gridPos": { "x": 12, "y": 0, "w": 12, "h": 8 },
      "targets": [
        {
          "expr": "sum by (namespace) (container_memory_working_set_bytes{namespace!=''}) / 1024 / 1024",
          "legendFormat": "{{namespace}}"
        }
      ],
      "datasource": { "type": "prometheus", "uid": "prometheus" }
    },
    {
      "type": "stat",
      "title": "Coût horaire estimé du cluster (USD)",
      "description": "Estimation statique basée sur le prix public Azure Standard_B2ls_v2 x2 nodes (~0.008$/h/node). Ne reflète pas le coût réel Azure Cost Management.",
      "gridPos": { "x": 0, "y": 8, "w": 6, "h": 4 },
      "targets": [
        {
          "expr": "vector(0.016)",
          "legendFormat": "$/h"
        }
      ],
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "options": { "colorMode": "background" },
      "fieldConfig": {
        "defaults": {
          "unit": "currencyUSD",
          "color": { "mode": "fixed", "fixedColor": "blue" }
        }
      }
    },
    {
      "type": "bargauge",
      "title": "Top namespaces par CPU",
      "gridPos": { "x": 6, "y": 8, "w": 18, "h": 4 },
      "targets": [
        {
          "expr": "sort_desc(sum by (namespace) (rate(container_cpu_usage_seconds_total{namespace!=''}[5m])))",
          "legendFormat": "{{namespace}}"
        }
      ],
      "datasource": { "type": "prometheus", "uid": "prometheus" }
    }
  ],
  "time": { "from": "now-1h", "to": "now" },
  "refresh": "30s"
}"""
