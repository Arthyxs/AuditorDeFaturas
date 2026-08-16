# InvoiceAuditor — Code Review

This file stores periodic independent review findings.

---

# Open findings

None yet.

---

# Finding format

## REVIEW-XXX — Title

**Severity:** CRITICAL | HIGH | MEDIUM | LOW  
**Status:** OPEN | FIXED | ACCEPTED_RISK  
**Area:** Security | Architecture | Audit | IMAP | Storage | Database | Frontend | Docker | Tests | Documentation | Other

### Problem
Describe the issue.

### Evidence
Files, functions, endpoints, migrations, tests or behavior demonstrating the problem.

### Specification impact
Which requirement is affected?

### Recommended fix
Concrete remediation.

### Resolution
Filled when fixed.

### Fix commit
Commit hash.

---

# Periodic review checklist

Review for:

- specification requirements silently omitted;
- placeholder/mock behavior presented as complete;
- partner-specific parsers/rules;
- OpenAI SDK leaking into domain code;
- provider abstraction violations;
- float used for money;
- unsafe dynamic evaluation;
- broken audit evidence/traceability;
- previous revisions overwritten;
- tariff interpretations reused as authoritative truth;
- pending documents incorrectly allowing a `CORRECT` invoice;
- automatic Terra -> Sol fallback;
- weak email deduplication;
- idempotency bugs;
- race conditions;
- migration/database problems;
- files lost after Docker rebuild;
- committed secrets/data;
- unsafe uploads;
- weak authentication;
- insufficient tests;
- misleading project status;
- Windows/Linux portability issues.
