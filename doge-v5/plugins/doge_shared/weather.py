from __future__ import annotations

import aiohttp

CODES = {0:"晴",1:"大致晴朗",2:"局部多云",3:"阴",45:"雾",48:"雾凇",51:"小毛毛雨",53:"毛毛雨",55:"较强毛毛雨",61:"小雨",63:"中雨",65:"大雨",71:"小雪",73:"中雪",75:"大雪",80:"小阵雨",81:"阵雨",82:"强阵雨",85:"小阵雪",86:"强阵雪",95:"雷暴",96:"雷暴伴小冰雹",99:"雷暴伴大冰雹"}

async def _get(url: str, params: dict) -> dict:
    async with aiohttp.ClientSession(headers={"User-Agent":"Doge-v5/5.1"}) as s:
        async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

class WeatherService:
    @classmethod
    async def forecast(cls, place: str, days: int = 3) -> dict:
        geo = await _get("https://geocoding-api.open-meteo.com/v1/search", {"name":place,"count":1,"language":"zh","format":"json"})
        rows = geo.get("results") or []
        if not rows:
            raise ValueError(f"找不到地点：{place}")
        loc = rows[0]
        days = max(1, min(int(days), 7))
        data = await _get("https://api.open-meteo.com/v1/forecast", {"latitude":loc["latitude"],"longitude":loc["longitude"],"current":"temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m","daily":"weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max","timezone":"auto","forecast_days":days})
        c, d = data.get("current",{}), data.get("daily",{})
        out=[]
        for i,date in enumerate(d.get("time",[])):
            code=d.get("weather_code",[])[i]
            out.append({"date":date,"weather":CODES.get(code,str(code)),"min":d.get("temperature_2m_min",[])[i],"max":d.get("temperature_2m_max",[])[i],"rain":d.get("precipitation_probability_max",[])[i]})
        return {"place":" · ".join(x for x in (loc.get("name"),loc.get("admin1"),loc.get("country")) if x),"current":{"weather":CODES.get(c.get("weather_code"),str(c.get("weather_code",""))),"temp":c.get("temperature_2m"),"feel":c.get("apparent_temperature"),"humidity":c.get("relative_humidity_2m"),"wind":c.get("wind_speed_10m")},"days":out}

    @staticmethod
    def format(data: dict) -> str:
        c=data["current"]
        lines=[data["place"],f"现在：{c['weather']}，{c['temp']}°C，体感 {c['feel']}°C，湿度 {c['humidity']}%，风速 {c['wind']} km/h"]
        lines += [f"{x['date']}：{x['weather']}，{x['min']}–{x['max']}°C，最高降水概率 {x['rain']}%" for x in data["days"]]
        return "\n".join(lines)
