## **ORION REIMBURSE IMPROV**

### **🔴 Phase P0 — Live Demo Threats**




---

### **🟠 Phase P1 — Quality & Reliability**

* **P1.1 — Redundant Validation Agent / Dead-End Pause**

  * *Problem:* A separate Validation node redundantly re-checks what the Supervisor already evaluated, and when it triggers a "request info" pause, the workflow dead-ends with no way to resume.  
  * *Fix:* Merge validation logic into the Supervisor with 3 clear routes: `approval`, `request_user_clarification` (pause \+ emit questions), or `request_human_escalation`. Delete the standalone `validation.py` agent.  
* **P1.2 — Analytics Engine for Duplicate/Volume Detection**

  * *Problem:* Duplicate and volume anomaly detection relied on vague LLM reasoning rather than real statistical computation, producing hallucinated z-scores.  
  * *Fix:* Build a real analytics engine with actual z-score calculations and hash-based duplicate matching to surface concrete, verifiable patterns.  
* **P1.3 — Receipt Amount Cross-Check**

  * *Problem:* The system accepted the claimed amount without verifying it against the uploaded receipt, allowing discrepancies to slip through.  
  * *Fix:* Cross-check the employee-declared amount against the amount extracted from the receipt and flag mismatches for the Intelligence agent.  
* **P1.4 — Sequential Agent Latency (30–40 sec)**

  * *Problem:* Intelligence and Policy agents ran sequentially, making total processing time 30–40 seconds — too slow for a live demo.  
  * *Fix:* Parallelize Intelligence and Policy agents using LangGraph's parallel node execution. Expected latency drops to 20–25 seconds (\~40% reduction) with no logic changes to agents.  
* **P1.5 — Missing Audit Trail / Confidence Snapshots**

  * *Problem:* The ledger only stored the final decision with no reasoning, confidence score, or supporting signals — making it unauditable.  
  * *Fix:* Thread confidence and reasoning through all agents. The Recorder now snapshots intake confidence, duplicate flags, intelligence recommendations, policy violations, and links to LangSmith trace in every ledger record.  
* **P1.6 — No Deduplication on Submission**

  * *Problem:* Double-clicking "Submit" or network retries would create duplicate ledger entries for the same claim.  
  * *Fix:* Compute a SHA256 hash of each submission (excluding timestamp) and check it against recent ledger records. Return the cached result instantly on a duplicate hit, with no LLM calls re-run.

---

### **🟡 Phase P2 — Architecture & Scalability**

* **P2.1 — Policy Token Bloat / No Versioning**

  * *Problem:* All policies were sent to the LLM on every request. As the rulebook grows, latency and token cost increase linearly, with no audit trail of policy changes.  
  * *Fix:* Add amount-range and category metadata to each policy rule. Only send applicable rules to the LLM. Add versioning and an audit trail to `policies.json`.  
* **P2.2 — Hard-Coded Fuzzy Match Threshold**

  * *Problem:* The 55% fuzzy match threshold was hard-coded, causing false positives/negatives with no way to tune or debug matches without code changes.  
  * *Fix:* Move `fuzzy_match_threshold`, `fuzzy_top_k`, and `fuzzy_debug_logging` to `app/config.py`. Add logging that shows match scores and inclusion decisions per candidate.  
* **P2.3 — Undifferentiated Hard vs. Soft Policy Rules**

  * *Problem:* Hard rules (absolute blocks, e.g., "no alcohol expenses") and soft rules (guideline warnings) were treated identically, allowing LLMs to "reason around" rules that should be deterministic.  
  * *Fix:* Split policies into `hard` (evaluated deterministically by a rules engine) and `soft` (evaluated contextually by the LLM). Hard-rule violations always block regardless of LLM output.

---

### **🔵 Phase P3 — Workflow Completeness (Resumption)**

* **P3.1 — No Persistent Pause State**

  * *Problem:* Paused claims awaiting clarification were lost on server restart — employees had no way to retrieve or answer their pending questions.  
  * *Fix:* Create a `ResumableStateStore` backed by a JSON file that persists paused workflow state, including clarification questions and a 72-hour TTL, across restarts.  
* **P3.2 — No Resume Endpoint or UI**

  * *Problem:* Even with state stored, there was no API or UI for employees to view, answer, and resume paused claims.  
  * *Fix:* Add `GET /api/claim/{id}`, `POST /api/resume/{id}`, and `GET /api/employee/{id}/paused-claims` endpoints. Update the UI to show paused claims with a form to answer clarification questions and re-submit.

---

### **🟢 Phase P4 — Developer Experience & Compliance**

* **P4.1 — No Compliance Export**

  * *Problem:* Finance/compliance teams had no way to export bulk decision data — auditors could only inspect individual records manually.  
  * *Fix:* Add `GET /api/audit/export` (returns filtered CSV with full audit trail) and `GET /api/audit/report` (returns a markdown summary with stats and low-confidence flags).  
* **P4.2 — Minimal Health Endpoint**

  * *Problem:* The existing `/api/health` endpoint was too bare for operators to diagnose performance issues, check policy state, or monitor the system.  
  * *Fix:* Expand `/api/health` to return LLM connectivity status, ledger size, paused claim count, average/median latency, deduplication cache hit rate, and current policy version.

