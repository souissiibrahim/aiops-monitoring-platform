## 🛠️ RCA Report for Incident #67

**Service:** `service-x`  
**Timestamp:** `2025-06-20 14:00:00`  
**Confidence:** `0.99`

---

### 📋 Logs
- OutOfMemoryError: Java heap space
- OutOfMemoryError: Java heap space

---

### 🧠 Root Cause
**PostgreSQL database is not running or is not listening on the expected port**

---

### ✅ Recommendation
**Check the PostgreSQL service status and ensure it is running and listening on the expected port. If the issue persists, check the PostgreSQL logs for any errors or warnings.**

---
