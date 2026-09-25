{{/* Chart name */}}
{{- define "experimentos.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully qualified app name */}}
{{- define "experimentos.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "experimentos.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels */}}
{{- define "experimentos.labels" -}}
helm.sh/chart: {{ include "experimentos.chart" . }}
app.kubernetes.io/name: {{ include "experimentos.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: experimentos
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Selector labels for a component. Usage: include "experimentos.selectorLabels" (dict "ctx" . "component" "api") */}}
{{- define "experimentos.selectorLabels" -}}
app.kubernetes.io/name: {{ include "experimentos.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "experimentos.componentLabels" -}}
{{ include "experimentos.labels" .ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "experimentos.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "experimentos.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "experimentos.apiImage" -}}
{{- printf "%s:%s" .Values.image.api.repository (default .Chart.AppVersion .Values.image.api.tag) -}}
{{- end -}}

{{- define "experimentos.frontendImage" -}}
{{- printf "%s:%s" .Values.image.frontend.repository (default .Chart.AppVersion .Values.image.frontend.tag) -}}
{{- end -}}

{{- define "experimentos.configMapName" -}}
{{- printf "%s-config" (include "experimentos.fullname" .) -}}
{{- end -}}

{{- define "experimentos.secretName" -}}
{{- if .Values.existingSecret -}}
{{- .Values.existingSecret -}}
{{- else -}}
{{- printf "%s-secrets" (include "experimentos.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Secret used by pre-install/pre-upgrade hook Jobs. Hooks run before regular
release resources exist on first install, so when the chart manages the
Secret we render a hook-scoped copy. With existingSecret it is the same name.
*/}}
{{- define "experimentos.hookSecretName" -}}
{{- if .Values.existingSecret -}}
{{- .Values.existingSecret -}}
{{- else -}}
{{- printf "%s-hook-secrets" (include "experimentos.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "experimentos.hookConfigMapName" -}}
{{- printf "%s-hook-config" (include "experimentos.fullname" .) -}}
{{- end -}}

{{/* Rendered ConfigMap data (shared by the regular and hook ConfigMaps) */}}
{{- define "experimentos.configData" -}}
{{- range $k, $v := .Values.config }}
{{ $k }}: {{ $v | toString | quote }}
{{- end }}
{{- end -}}

{{- define "experimentos.secretData" -}}
{{- range $k, $v := .Values.secrets }}
{{ $k }}: {{ $v | toString | b64enc | quote }}
{{- end }}
{{- end -}}

{{/* envFrom block for Django containers */}}
{{- define "experimentos.envFrom" -}}
- configMapRef:
    name: {{ include "experimentos.configMapName" . }}
- secretRef:
    name: {{ include "experimentos.secretName" . }}
{{- end -}}

{{/* Checksums so pods roll when config changes */}}
{{- define "experimentos.configChecksums" -}}
checksum/config: {{ include "experimentos.configData" . | sha256sum }}
checksum/secret: {{ include "experimentos.secretData" . | sha256sum }}
{{- end -}}

{{/* Writable /tmp for readOnlyRootFilesystem containers */}}
{{- define "experimentos.tmpVolume" -}}
- name: tmp
  emptyDir: {}
{{- end -}}

{{- define "experimentos.tmpVolumeMount" -}}
- name: tmp
  mountPath: /tmp
{{- end -}}

{{/* Common scheduling fields for a component values block */}}
{{- define "experimentos.scheduling" -}}
{{- with .nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .affinity }}
affinity:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}
