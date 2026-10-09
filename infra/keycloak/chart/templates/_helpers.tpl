{{- define "cnp-keycloak.labels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
cnp.io/auth-instance: {{ .Values.instanceKey }}
{{- end -}}
