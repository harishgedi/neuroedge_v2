# NeuroEdge — Honest Evaluation from Professor POVs
# Then: What Was Weak | Now: What Was Fixed

---

## 🔬 Dr. Enda Fallon's Lens (SRI / 5G-NFV / CAMINO / Anomaly Detection)

### What he would have spotted as weak in v1:

| Weakness | Why It Matters To Him |
|---|---|
| Z-score only anomaly detection | His published work uses CUSUM + EWMA for network fault detection. Z-score alone is undergraduate-level |
| No CUSUM / EWMA | CAMINO (his EU project) uses multi-algorithm ensemble for intent-driven healing |
| Friis path loss too simplified | 5G NR uses 3GPP TR 38.901 propagation model — he'd notice immediately |
| No network self-healing loop | His research is about orchestrators that *react* to anomalies, not just detect |
| No VNF lifecycle simulation | NFV = core of his SRI work. Absent here entirely |
| "5G slice" label with no SLA enforcement | Slices need actual URLLC/eMBB latency enforcement logic, not just labels |
| Anomaly detector not connected to K8s | Spencer's Retail SRE work shows HPA — but it's not triggered by network anomalies |

### What v2 fixes:
- ✅ CUSUM + EWMA + Z-score ensemble (3-algorithm voting)
- ✅ 3GPP-inspired path loss model (log-distance + shadowing)
- ✅ SLA breach predictor with slice-aware thresholds
- ✅ Self-healing network loop: anomaly → heal action → log
- ✅ VNF state machine (INSTANTIATED → CONFIGURED → ACTIVE → FAILED → HEALING)
- ✅ Research question embedded in code comments linking to his CAMINO work

---

## 📦 Mary Giblin's Lens (Cloud-Native / DevOps / GitOps / CI-CD)

### What she would have spotted as weak in v1:

| Weakness | Why It Matters To Her |
|---|---|
| CI/CD pipeline never actually runs tests | Pipeline.yml had test stage but no working test runner setup |
| K8s manifests missing RBAC entirely | Production K8s always has ServiceAccounts + RoleBindings |
| No NetworkPolicy | Zero-trust networking is a cloud-native baseline |
| No Helm chart — just raw YAML | Helm is what her programme teaches. Raw YAML = not cloud-native |
| No ArgoCD GitOps manifest | GitOps is her programme's key differentiator |
| HPA only on CPU — not custom metrics | She'd expect custom metrics (Prometheus → KEDA) after Spencer's SRE work |
| No readiness/liveness probe logic in code | Probes in YAML but /health endpoint not conformant |
| No resource quota / LimitRange | Namespace isolation missing |

### What v2 fixes:
- ✅ Full Helm chart with values.yaml, helpers, proper templates
- ✅ RBAC: ServiceAccount + Role + RoleBinding per component
- ✅ NetworkPolicy: ingress/egress rules per pod
- ✅ ArgoCD Application manifest (GitOps)
- ✅ KEDA ScaledObject on custom Prometheus metric (anomaly_score)
- ✅ /health returns proper { status, checks: {db, mqtt, camera} } structure
- ✅ ResourceQuota + LimitRange in namespace manifest
- ✅ CI pipeline runs pytest with real coverage gate
