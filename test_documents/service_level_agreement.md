# SERVICE LEVEL AGREEMENT (SLA)

**Agreement Date:** March 1, 2026  
**Service Provider:** CloudBase Infrastructure Pvt. Ltd. ("Provider"), registered at 501, Prestige Tower, Bengaluru – 560001  
**Client:** LegalEdge Technologies Ltd. ("Client"), registered at 22, Connaught Place, New Delhi – 110001

---

## 1. OVERVIEW

This Service Level Agreement ("SLA") defines the performance standards, responsibilities, and remedies applicable to the cloud infrastructure services ("Services") provided by CloudBase Infrastructure Pvt. Ltd. to LegalEdge Technologies Ltd. pursuant to the Master Services Agreement dated February 15, 2026.

---

## 2. SERVICES COVERED

This SLA applies to the following services:

| Service | Description |
|---|---|
| Compute Instances | Virtual machines (VMs) provisioned on demand |
| Managed Database | PostgreSQL and MongoDB managed database clusters |
| Object Storage | Scalable blob/file storage with geo-redundancy |
| CDN | Content Delivery Network for static asset distribution |
| Load Balancer | Automated traffic distribution across instances |
| Managed Kubernetes | Container orchestration and auto-scaling |

---

## 3. UPTIME COMMITMENT

Provider guarantees the following monthly uptime percentages:

| Service Tier | Uptime SLA | Max Monthly Downtime |
|---|---|---|
| Standard | 99.5% | 3 hours 39 minutes |
| Premium | 99.9% | 43 minutes 49 seconds |
| Enterprise | 99.99% | 4 minutes 22 seconds |

LegalEdge Technologies Ltd. is subscribed to the **Enterprise Tier** for Compute, Database, and Load Balancer; **Premium Tier** for Object Storage and CDN.

**Uptime** is calculated as:

> Uptime (%) = ((Total minutes in month − Downtime minutes) / Total minutes in month) × 100

**Scheduled maintenance windows** (notified 72 hours in advance) are excluded from downtime calculations.

---

## 4. INCIDENT CLASSIFICATION AND RESPONSE TIMES

| Severity | Description | Initial Response | Resolution Target |
|---|---|---|---|
| P1 – Critical | Complete service unavailability or data loss | 15 minutes | 2 hours |
| P2 – High | Major degradation affecting majority of users | 30 minutes | 4 hours |
| P3 – Medium | Partial degradation, workaround available | 2 hours | 1 business day |
| P4 – Low | Minor issue, cosmetic, or informational | 8 hours | 5 business days |

All P1/P2 incidents must be reported via the 24/7 emergency hotline: **1800-CLOUD-99**.

---

## 5. SERVICE CREDITS

If Provider fails to meet the uptime SLA in any calendar month, Client is entitled to Service Credits as follows:

| Actual Monthly Uptime | Credit as % of Monthly Fee |
|---|---|
| 99.0% – 99.98% | 10% |
| 95.0% – 98.99% | 25% |
| 90.0% – 94.99% | 50% |
| Below 90.0% | 100% |

### 5.1 Credit Claim Process

- Client must submit a written credit claim within **15 days** of the end of the affected month
- Claims must include incident reference numbers, timestamps, and business impact description
- Credits shall be applied to the following invoice; no cash payments

### 5.2 Credit Exclusions

Service Credits shall not apply to downtime caused by:
- Client's own applications, software, or custom configurations
- Force majeure events (floods, earthquakes, acts of war)
- DDoS attacks exceeding Provider's documented mitigation capacity
- Third-party services not within Provider's control
- Scheduled maintenance windows communicated in advance

---

## 6. DATA BACKUP AND RECOVERY

| Metric | Commitment |
|---|---|
| Backup Frequency | Daily automated snapshots |
| Backup Retention | 30 days for standard; 90 days for Enterprise |
| Recovery Time Objective (RTO) | 4 hours for Enterprise tier |
| Recovery Point Objective (RPO) | Maximum 24 hours data loss |
| Geographic Redundancy | Data replicated across 2 availability zones |

---

## 7. SECURITY COMMITMENTS

Provider shall:
- Maintain ISO 27001 certification throughout the contract term
- Conduct quarterly penetration testing and share executive summaries with Client
- Notify Client within **4 hours** of any confirmed security breach affecting Client data
- Encrypt all data at rest (AES-256) and in transit (TLS 1.2+)
- Maintain SOC 2 Type II compliance

---

## 8. MONITORING AND REPORTING

- Real-time status dashboard available at: status.cloudbase.in
- Monthly uptime and incident reports delivered to Client by the 5th of the following month
- Quarterly business reviews (QBRs) conducted between Client's CTO and Provider's Account Director

---

## 9. ESCALATION MATRIX

| Level | Contact | Trigger |
|---|---|---|
| L1 | Support Portal / Email | P3/P4 incidents |
| L2 | Account Manager | P2 incidents or unresolved P3 > 24 hours |
| L3 | Engineering Lead | P1 incidents or unresolved P2 > 3 hours |
| L4 | VP Operations | P1 unresolved > 1 hour or critical data breach |

---

## 10. REVIEW AND AMENDMENT

This SLA shall be reviewed every six months. Either party may propose amendments with thirty (30) days' written notice. Agreed amendments shall be recorded in a signed addendum.

---

**EXECUTED BY:**

| CloudBase Infrastructure Pvt. Ltd. | LegalEdge Technologies Ltd. |
|---|---|
| Signature: _____________________ | Signature: _____________________ |
| Name: _____________________ | Name: _____________________ |
| Title: _____________________ | Title: _____________________ |
| Date: _____________________ | Date: _____________________ |
