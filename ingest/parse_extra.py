import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from parse_futures import parse_root
from parse_equity import parse_ticker
for r in ["RTY","YM","SI","NG","HG","ZT","ZF","ZN","ZB"]:
    try: root,n=parse_root(r); print(f"{root}: {n:,}",flush=True)
    except Exception as e: print(f"{r} ERR {e}",flush=True)
try: tk,n=parse_ticker("DIA"); print(f"DIA: {n:,}",flush=True)
except Exception as e: print("DIA ERR",e)
