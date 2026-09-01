from __future__ import annotations

import base64
import random
import urllib.parse
from dataclasses import dataclass

SUBJECTS=("迟到的企鹅","会计系幽灵","月球快递员","一只电子柯基","失业的炼金术士","凌晨三点的路灯","量子鸽子","反方向钟表","图书馆里的海豹","会写代码的蘑菇","一台害羞的服务器","迷路的天气预报")
VERBS=("偷偷交换了","正在申请注销","把密码借给了","决定起诉","误认为自己是","在梦里编译了","用回形针修好了","郑重收藏了","试图说服","突然继承了","向全宇宙广播了","在电梯里孵化了")
OBJECTS=("一公斤星期二","月球的备用钥匙","不存在的第十三个月","一份会反驳人的论文","三分钟的永久会员","北极熊的 Git 历史","一张来自明天的发票","禁止被命名的文件夹","会自我撤回的情书","半个无限循环","一瓶压缩后的晚霞","数据库里最后一只猫")


def _b64(s:str)->str: return base64.b64encode(s.encode()).decode()
def _b64url(s:str)->str: return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")
def _hex(s:str)->str: return s.encode().hex()
def _reverse(s:str)->str: return s[::-1]
def _url(s:str)->str: return urllib.parse.quote(s,safe="")

LAYERS={
    "mirror":(_reverse,"最外层像镜子：先把整串倒过来看。"),
    "base64":(_b64,"最外层是经典 Base64。"),
    "base64url":(_b64url,"最外层像 Base64，但用了 URL-safe 字母表且可能省略 =。"),
    "hex":(_hex,"最外层只剩 0-9a-f：按 UTF-8 十六进制想。"),
    "url":(_url,"最外层有 URL percent-encoding 的味道。"),
}


@dataclass(slots=True)
class SignalGame:
    answer:str
    encoded:str
    layers:list[str]  # encoding order: inner -> outer
    hints_used:int=0

    def first_clue(self)->str:
        return LAYERS[self.layers[-1]][1]

    def hint(self)->str:
        # Reveal from outer to inner; the first clue was free.
        reveal_index=min(self.hints_used+1,len(self.layers)-1)
        self.hints_used+=1
        layer=self.layers[-1-reveal_index]
        if reveal_index==len(self.layers)-1:
            return f"最后一层提示：{LAYERS[layer][1]} 解完后会得到一句完整中文。"
        return f"再往里一层：{LAYERS[layer][1]}"

    def check(self,text:str)->bool:
        return " ".join(text.strip().split())==self.answer

    def score(self)->int:
        return max(10,100-20*self.hints_used)


def new_game(difficulty:str="normal",rng:random.Random|None=None)->SignalGame:
    r=rng or random.SystemRandom()
    answer=f"{r.choice(SUBJECTS)}{r.choice(VERBS)}{r.choice(OBJECTS)}"
    n={"easy":2,"normal":3,"hard":4}.get(difficulty.lower(),3)
    names=list(LAYERS)
    # Avoid two visually similar Base64 layers in one puzzle.
    selected=[]
    while len(selected)<n:
        x=r.choice(names)
        if x in selected: continue
        if x.startswith("base64") and any(y.startswith("base64") for y in selected): continue
        selected.append(x)
    encoded=answer
    for name in selected:
        encoded=LAYERS[name][0](encoded)
    return SignalGame(answer=answer,encoded=encoded,layers=selected)
