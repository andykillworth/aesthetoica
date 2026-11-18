import requests
H="https://imag-data.bgs.ac.uk/GIN_V1/hapi"
cat=requests.get(H+"/catalog",timeout=30).json()["catalog"]
for st in ["had","esk","ler","val","clf","dou","wng","bfe","ebr","sfs","fur","ngk"]:
    ids=[c["id"] for c in cat if c["id"].startswith(st+"/best-avail/PT1M")]
    if not ids: print(st,"none");continue
    inf=requests.get(H+"/info",params={"dataset":ids[0]},timeout=30).json()
    print(st,ids[0],inf.get("stopDate"))
