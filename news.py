from flask import Flask,request,jsonify,send_file
import urllib.request,urllib.parse,json,os,re
from collections import defaultdict

app=Flask(__name__,template_folder="templates")
BASE_DIR=os.path.dirname(os.path.abspath(__file__))
NK="35fca349399e4a548befd46f2654bef3"
AK=os.environ.get("ANTHROPIC_API_KEY","")
# Only exact NewsAPI category names get top-headlines; everything else uses q= search
CATS={"business","entertainment","general","health","science","sports","technology"}
MP={"short":"2 sentences: what happened, why it matters. Plain text.","detailed":"4 sentences: 1)what/who/when 2)reactions 3)implications 4)what's next. Plain text.","bullet":"4 bullet points starting with '• '. Cover: event, people, significance, outlook. No intro.","eli5":"3 simple sentences for a 10-year-old: what happened, why adults care, one fun fact. No jargon."}
POS={"good","great","win","success","growth","rise","gain","improve","hope","strong","record","boost","safe","breakthrough","peace","recovery","profit","award"}
NEG={"bad","crisis","war","attack","death","fail","crash","loss","fear","danger","worst","decline","flood","fire","arrested","killed","threat","collapse","scandal","fraud","conflict"}
NLP={"Politics":["election","president","government","minister","parliament","policy","vote","war","military","nato"],"Economy":["economy","market","stock","inflation","trade","bank","dollar","interest","recession","crypto","bitcoin","tariff"],"Technology":["ai","artificial","tech","robot","software","startup","cyber","openai","google","microsoft","apple","chip"],"Health & Science":["health","covid","vaccine","cancer","climate","nasa","space","research","hospital","medicine","virus"],"Sports":["football","soccer","basketball","tennis","olympic","championship","league","player","team","goal"],"Entertainment":["movie","film","music","celebrity","award","hollywood","streaming","netflix","disney","show"]}

def _req(url,data=None,headers={}):
    with urllib.request.urlopen(urllib.request.Request(url,data,headers),timeout=15) as r: return json.loads(r.read())

def ai_rewrite(title,desc,mode):
    body=f"{MP.get(mode,MP['short'])}\n\nTITLE:{title}\nARTICLE:{desc[:800]}"
    try: return _req("https://api.anthropic.com/v1/messages",json.dumps({"model":"claude-haiku-4-5-20251001","max_tokens":300,"messages":[{"role":"user","content":body}]}).encode(),{"Content-Type":"application/json","x-api-key":AK,"anthropic-version":"2023-06-01"})["content"][0]["text"].strip()
    except Exception as e: print(f"AI err:{e}"); return desc[:250]+"..."

def fetch_news(topic=""):
    t=topic.lower().strip()
    # Use category endpoint ONLY for exact NewsAPI category names; all other topics use q= so results are actually filtered
    p,ep=({"language":"en","pageSize":30,"category":t},"top-headlines") if t in CATS else ({"q":topic,"language":"en","sortBy":"publishedAt","pageSize":30},"everything") if topic else ({"language":"en","pageSize":30},"top-headlines")
    try:
        d=_req(f"https://newsapi.org/v2/{ep}?{urllib.parse.urlencode(p)}",headers={"X-Api-Key":NK,"User-Agent":"SmartNews/1.0"})
        return [{"title":a["title"][:140],"source":(a.get("source") or {}).get("name",""),"description":re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",a.get("description") or a.get("content") or "")).strip()[:600],"url":a.get("url","#"),"image":a.get("urlToImage",""),"pubDate":(a.get("publishedAt",""))[:10]} for a in d.get("articles",[]) if (a.get("title") or "").strip() not in ("","[Removed]")]
    except Exception as e: print(f"NewsAPI err:{e}"); return []

def sentiment(text):
    w=set(re.findall(r'\b\w+\b',text.lower())); p,n=len(w&POS),len(w&NEG)
    return ("Positive",min(50+p*10,95)) if p>n else ("Negative",max(5,50-n*10)) if n>p else ("Neutral",50)

def group(articles):
    g=defaultdict(list)
    for a in articles:
        txt=(a["title"]+" "+a["description"]).lower(); best,bs="General",0
        for grp,kws in NLP.items():
            s=sum(1 for k in kws if k in txt)
            if s>bs: best,bs=grp,s
        g[best].append(a)
    return dict(g)


@app.route("/")
@app.route("/news")
def index(): return send_file(os.path.join(BASE_DIR,"templates","News.html"))

@app.route("/api/news")
def api_news():
    topic,mode,search=request.args.get("topic","").strip(),request.args.get("mode","short"),request.args.get("search","").strip().lower()
    articles=fetch_news(topic)
    if search: articles=[a for a in articles if search in a["title"].lower() or search in a["description"].lower()]
    for a in articles[:20]: a["summary"]=ai_rewrite(a["title"],a["description"],mode); a["sentiment"],a["score"]=sentiment(a["title"]+" "+a["description"])
    groups=group(articles[:20])
    return jsonify({"groups":groups,"chart_data":{g:{"Positive":sum(1 for x in v if x["sentiment"]=="Positive"),"Negative":sum(1 for x in v if x["sentiment"]=="Negative"),"Neutral":sum(1 for x in v if x["sentiment"]=="Neutral")}for g,v in groups.items()},"meta":{"mode":mode,"topic":topic or "Global Trending","total":sum(len(v)for v in groups.values())}})

if __name__=="__main__": app.run(debug=True,port=5000)

# filter news of each major topic like health or sports into multiple related subtopic 
# make the short version the default one( anthropic and upon clicking on a particular news, show the detailed version as a popup or new page using gpt4.0 api)
# need to add voice request( ask for what topic or kind of new you want) feature and option for the user to make an AI read the news to them. 
# improve the UI and make it more interactive.
# add a feature to save news articles to a reading list or bookmark them for later reference.

