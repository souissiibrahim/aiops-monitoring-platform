import os, glob, json
from pathlib import Path
from typing import List, Dict
from sentence_transformers import SentenceTransformer
import faiss, numpy as np
from app.monitor.heartbeat import start_heartbeat

hb = start_heartbeat("scripts/build_rag_index.py", interval_s=30, version="dev")
RCA_DIR   = Path(os.getenv("RCA_DOCS_DIR", "rca_reports"))
RAG_DIR   = Path(os.getenv("RAG_DIR", "rag"))
EMB_MODEL = os.getenv("RAG_EMB_MODEL", "all-MiniLM-L6-v2")

RAG_DIR.mkdir(parents=True, exist_ok=True)
IDX_PATH = RAG_DIR / "faiss.index"
CH_PATH  = RAG_DIR / "chunks.jsonl"

def collect_paths() -> List[Path]:
    exts = ("md", "txt", "json")
    paths: List[Path] = []
    for ext in exts:
        paths += [Path(p) for p in glob.glob(str(RCA_DIR / f"**/*.{ext}"), recursive=True)]
    return paths

def read_text(p: Path) -> str:
    try:
        if p.suffix.lower() == ".json":
            obj = json.loads(p.read_text(encoding="utf-8"))
            keys = ["title","summary","description","context","analysis","root_cause",
                    "contributing_factors","observations","findings","impact",
                    "recommendations","mitigations","resolution","timeline"]
            parts=[]
            for k in keys:
                v = obj.get(k)
                if isinstance(v,str): parts.append(v)
                elif isinstance(v,list): parts.append("\n".join(map(str,v)))
                elif isinstance(v,dict): parts.append(json.dumps(v,ensure_ascii=False))
            txt = "\n\n".join([x for x in parts if x and x.strip()])
            return txt or json.dumps(obj,ensure_ascii=False)
        return p.read_text(encoding="utf-8")
    except Exception as e:
        print(f"skip {p}: {e}"); return ""

def chunk(text: str, max_chars=1400):
    paras = [s.strip() for s in text.split("\n\n") if s.strip()]
    out, buf = [], ""
    for para in paras:
        if len(buf)+len(para)+2 <= max_chars:
            buf = (buf+"\n\n"+para).strip()
        else:
            if buf: out.append(buf); buf=""
            if len(para) <= max_chars: out.append(para)
            else:
                for i in range(0,len(para),max_chars):
                    out.append(para[i:i+max_chars])
    if buf: out.append(buf)
    return out

def main():
    files = collect_paths()
    if not files: return print(f"❌ no docs under {RCA_DIR.resolve()}")
    texts, metas = [], []
    for p in files:
        raw = read_text(p)
        if not raw: continue
        for c in chunk(raw):
            texts.append(c); metas.append({"source": str(p)})
    if not texts: return print("❌ all docs empty/unreadable")

    print(f"📚 indexing {len(texts)} chunks from {len(files)} files …")
    model = SentenceTransformer(EMB_MODEL)
    X = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)
    index = faiss.IndexFlatIP(X.shape[1]); index.add(X)
    faiss.write_index(index, str(IDX_PATH))
    with CH_PATH.open("w",encoding="utf-8") as w:
        for t,m in zip(texts,metas): w.write(json.dumps({"text":t,**m},ensure_ascii=False)+"\n")
    print(f"✅ built RAG → {IDX_PATH}\n📝 chunks → {CH_PATH}")

if __name__ == "__main__":
    main()
