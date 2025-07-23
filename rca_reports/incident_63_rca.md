## 🛠️ RCA Report for Incident #63

**Service:** `backend-api`  
**Timestamp:** `2025-06-18 12:00:00`  
**Confidence:** `0.95`

---

### 📋 Logs
- Memory usage exceeded 95% on node-03
- OutOfMemoryError: Java heap space

---

### 🧠 Root Cause
**Insufficient Java heap size configuration on node-03, causing OutOfMemoryError**

---

### ✅ Recommendation
**Increase the Java heap size configuration on node-03 to prevent memory usage from exceeding 95% and reduce the risk of OutOfMemoryError**

---
