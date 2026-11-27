import os
import random
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_ID = "gemini-4-hydrogen"

client = genai.Client(api_key=API_KEY)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class PoolReq(BaseModel):
    category: str
    count: int

class CharacterItem(BaseModel):
    name: str
    en_name: str
    title: str
    desc: str

class PoolSchema(BaseModel):
    items: list[CharacterItem]

class TeamInfo(BaseModel):
    player: str
    heroes: list[str]

class JudgeReq(BaseModel):
    category: str
    teams: list[TeamInfo]

class JudgeSchema(BaseModel):
    arena: str
    story: str
    winner: str
    reason: str

async def fetch_image(category: str, en_name: str) -> str:
    clean_name = en_name.strip()
    fallback = f"https://dicebear.com{clean_name}&backgroundColor=162238"
    headers = {"User-Agent": "PeakDraftApp/1.0"}
    async with httpx.AsyncClient(timeout=6.0, headers=headers) as http:
        try:
            if category == "anime":
                query = "query ($s: String) { Character(search: $s) { image { large } } }"
                r = await http.post(
                    "https://anilist.co",
                    json={"query": query, "variables": {"s": clean_name}},
                )
                char = (r.json().get("data") or {}).get("Character")
                if char and char.get("image") and char["image"].get("large"):
                    return char["image"]["large"]
            else:
                r = await http.get(
                    "https://wikipedia.org",
                    params={
                        "action": "query",
                        "generator": "search",
                        "gsrsearch": f"{clean_name} basketball",
                        "gsrlimit": 1,
                        "prop": "pageimages",
                        "pithumbsize": 600,
                        "format": "json",
                    },
                )
                pages = (r.json().get("query") or {}).get("pages") or {}
                for page in pages.values():
                    if "thumbnail" in page:
                        return page["thumbnail"]["source"]
        except Exception as e:
            print("Image fetch error:", en_name, e)
    return fallback


@app.get("/")
async def index():
    return FileResponse("index.html")

@app.post("/api/pool")
async def generate_pool(req: PoolReq):
    tiers_anime = [
        "Тактики и уличный уровень (Магическая битва, Клинок, Хантер, ранняя Нарута)",
        "Катастрофы и легенды (Эдо-Итачи, Сукуна, Годжо, капитаны Блича, адмиралы Ван Пис)",
        "Ломатели реальности и измерений (Анос Волдигод, Римуру, Фанни Валентайн, Яхве)"
    ]
    chosen = random.choice(tiers_anime) if req.category == "anime" else "Легенды и суперзвезды NBA разных эпох"
    prompt = (
        f"Сгенерируй ровно {req.count} уникальных персонажей категории '{req.category}'. "
        f"Скрытый баланс катки: {chosen}. ВСЕ персонажи строго в своей АБСОЛЮТНОЙ ПИКОВОЙ ФОРМЕ за всю историю и равны по масштабу сил между собой! "
        f"Поля: name (на русском), en_name (точное имя на английском для поиска фото), title (аниме или позиция в NBA), "
        f"desc (2 ярких предложения на русском про пиковые способности/навыки)."
    )
    res = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config={"response_mime_type": "application/json", "response_schema": PoolSchema, "temperature": 0.9},
    )
    parsed: PoolSchema = res.parsed
    out = []
    for ch in parsed.items:
        img = await fetch_image(req.category, ch.en_name)
        out.append({"name": ch.name, "title": ch.title, "desc": ch.desc, "img": img})
    return {"pool": out}

@app.post("/api/judge")
async def judge_battle(req: JudgeReq):
    teams_txt = "\n".join([f"{t.player}: {', '.join(t.heroes)}" for t in req.teams])
    mode = "смертельную битву (уравняй все виды энергий, оцени синергию пиковых форм и контр-пики)" if req.category == "anime" else "матч 7-й игры Финала NBA (оцени пиковую синергию, защиту, спейсинг и клатч)"
    prompt = (
        f"Ты — харизматичный судья. Проведи {mode} между этими командами (все на своем историческом пике!):\n{teams_txt}\n"
        f"Верни на русском: arena (место боя/матча), story (3 захватывающих абзаца с ходом противостояния), winner (имя победившего игрока), reason (главная причина победы)."
    )
    res = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config={"response_mime_type": "application/json", "response_schema": JudgeSchema, "temperature": 0.7},
    )
    return res.parsed
