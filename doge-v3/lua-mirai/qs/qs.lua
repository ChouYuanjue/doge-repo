print("载入确实怪成功")
Event.subscribe("GroupMessageEvent", function(event)

    a = math.random(1, 1200)
    if a == 10 then event.group:sendMessage("确实是这样的") end

    if a == 20 then event.group:sendMessage("嗯确实") end

    if a == 30 then event.group:sendMessage("那确实") end
    if a == 40 then event.group:sendMessage("说的对，确实") end

    if a == 50 then event.group:sendMessage("有一说一确实") end

    if a == 60 then event.group:sendMessage("确实") end

    if a == 70 then
        event.group:sendMessage(Quote(event.message) + "确实是这样的")
    end

    if a == 80 then
        event.group:sendMessage(Quote(event.message) + "嗯确实")
    end

    if a == 90 then
        event.group:sendMessage(Quote(event.message) + "那确实")
    end

    if a == 100 then
        event.group:sendMessage(Quote(event.message) + "说的对，确实")
    end

    if a == 110 then
        event.group:sendMessage(Quote(event.message) + "有一说一确实")
    end

    if a == 120 then event.group:sendMessage(Quote(event.message) + "确实") end

    if tostring(event.message):find("确实") and not tostring(event.message):find("怪") and
        not tostring(event.message):find("有一说一") and
        not tostring(event.message):find("说的对") and not tostring(event.message):find("嗯") then
        event.group:sendMessage("说的对，确实")
    end

    if tostring(event.message):find("有一说一") then
        event.group:sendMessage("确实是这样的")
    end

    if tostring(event.message):find("说的对") or tostring(event.message):find("嗯确实") then
        event.group:sendMessage("有一说一，确实")
    end

    if tostring(event.message):find("确实怪") then
        event.group:sendMessage(
            "请无视确实明白怪，因为确实明白怪确实明白真理")
    end

    --[[if tostring(event.message):find("明白") and not tostring(event.message):find("不") and not tostring(event.message):find("嗯确实") then
        event.group:sendMessage("不明白")
    end]]

    if tostring(event.message):find("明白") and not tostring(event.message):find("了吗") then
        event.group:sendMessage("不是很懂.jpg")
    end

end)

Event.onFinish = function() print("脚本被卸载！") end