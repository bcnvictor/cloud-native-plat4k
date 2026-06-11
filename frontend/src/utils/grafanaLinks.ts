const lokiDs = { type: 'loki' };
const promDs = { type: 'prometheus' };

export const grafanaLogsUrl = (grafanaUrl: string, appName: string): string => {
  const panes = JSON.stringify({
    a: {
      datasource: lokiDs,
      queries: [{ refId: 'A', expr: `{container="${appName}"}`, queryType: 'range', datasource: lokiDs }],
      range: { from: 'now-1h', to: 'now' },
    },
  });
  return `${grafanaUrl}/explore?orgId=1&schemaVersion=1&panes=${encodeURIComponent(panes)}`;
};

export const grafanaMetricsUrl = (grafanaUrl: string, appName: string): string => {
  const panes = JSON.stringify({
    a: {
      datasource: promDs,
      queries: [{ refId: 'A', expr: `rate(container_cpu_usage_seconds_total{container="${appName}"}[5m])`, datasource: promDs }],
      range: { from: 'now-1h', to: 'now' },
    },
  });
  return `${grafanaUrl}/explore?orgId=1&schemaVersion=1&panes=${encodeURIComponent(panes)}`;
};

export const grafanaFinopsUrl = (grafanaUrl: string): string =>
  `${grafanaUrl}/d/cnp-finops`;
