{{/*
NeuroEdge Helm helpers
*/}}
{{- define "neuroedge.fullname" -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "neuroedge.labels" -}}
app.kubernetes.io/name: neuroedge
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
research: tus-athlone
{{- end -}}

{{- define "neuroedge.selectorLabels" -}}
app: neuroedge-api
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
