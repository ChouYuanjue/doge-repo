print("载入JeffJoke成功")
Event.subscribe(FriendMessageEvent, function (event)
  local text = tostring(event.message)
  parse_and_run(event, text)
end)

Event.subscribe(GroupMessageEvent, function (event)
  local text = tostring(event.message)
  parse_and_run(event, text)
end)

local function read_file(path)
  local f = io.open(path, "r")
  if not f then return nil, "cannot open: " .. tostring(path) end
  local s = f:read("*a")
  f:close()
  return s
end

local function trim(s)
  return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function split_jokes(raw)
  if not raw or raw == "" then return {} end
  raw = raw:gsub("\r\n", "\n"):gsub("\r", "\n")
  raw = trim(raw)
  local jokes = {}
  for seg in (raw .. "\n\n"):gmatch("(.-)\n\n+") do
    seg = trim(seg)
    if #seg > 0 then table.insert(jokes, seg) end
  end
  return jokes
end

local function fill_subject(text, subject)
  subject = tostring(subject or "他")
  return (text:gsub("%%%s", subject))
end

local JOKES = {}
local function load_jokes()
  local ok, content = pcall(read_file, "jeff.txt")
  if not ok or not content then
    JOKES = {}
    return false, "jeff.txt 未找到或无法读取"
  end
  JOKES = split_jokes(content)
  if #JOKES == 0 then
    return false, "jeff.txt 为空，或未按空行进行分隔"
  end
  return true
end

local _ = load_jokes()
math.randomseed(os.time())

local function pick_jokes(n)
  local out = {}
  if #JOKES == 0 then return out end
  for i = 1, n do
    table.insert(out, JOKES[math.random(#JOKES)])
  end
  return out
end

local function is_group_event(event)
  return (event and event.group) ~= nil
end

local function get_sender_name(event)
  local s = event and event.sender or nil
  if not s then return "你" end
  if s.nameCard and s.nameCard ~= "" then return s.nameCard end
  if s.nick and s.nick ~= "" then return s.nick end
  if s.nickname and s.nickname ~= "" then return s.nickname end
  if s.name and s.name ~= "" then return s.name end
  if s.id then return tostring(s.id) end
  return "你"
end

local function reply(event, text)
  if is_group_event(event) then
    event.group:sendMessage(text)
  else
    event.sender:sendMessage(text)
  end
end

local HELP = table.concat({
  "jeffjoke 使用说明:",
  "/jeffjoke mj [条数]        —— 生成关于自己的笑话 (别名: myjoke)",
  "/jeffjoke dj <某人> [条数] —— 生成关于某人的笑话 (别名: diyjoke)",
  "注意: 条数可省略, 默认1; 为防刷屏, 限制范围 1-20"
}, "\n")

function parse_and_run(event, raw)
  local head, rest = raw:match("^/jeffjoke%s+([%S]+)%s*(.*)$")
  if not head then return false end
  head = head:lower()

  if head == "help" or head == "h" then
    reply(event, HELP)
    return true
  end

  if head == "mj" or head == "myjoke" then
    local n = tonumber(trim(rest)) or 1
    if n < 1 then n = 1 end
    if n > 20 then n = 20 end

    if #JOKES == 0 then
      local ok, msg = load_jokes()
      if not ok then reply(event, msg); return true end
    end

    local who = get_sender_name(event)
    local chunks = {}
    for _, j in ipairs(pick_jokes(n)) do
      table.insert(chunks, fill_subject(j, who))
    end
    reply(event, table.concat(chunks, "\n\n"))
    return true
  end

  if head == "dj" or head == "diyjoke" then
    if rest == nil or trim(rest) == "" then
      reply(event, "用法: /jeffjoke dj <某人> [条数]")
      return true
    end

    local name, n
    local maybe_num = rest:match("(%d+)%s*$")
    if maybe_num then
      local idx = select(1, rest:find("%d+%s*$"))
      name = trim(rest:sub(1, idx - 1))
      n = tonumber(maybe_num)
    else
      name = trim(rest)
      n = 1
    end

    if name == "" then name = "某人" end
    if n < 1 then n = 1 end
    if n > 20 then n = 20 end

    if #JOKES == 0 then
      local ok, msg = load_jokes()
      if not ok then reply(event, msg); return true end
    end

    local chunks = {}
    for _, j in ipairs(pick_jokes(n)) do
      table.insert(chunks, fill_subject(j, name))
    end
    reply(event, table.concat(chunks, "\n\n"))
    return true
  end

  return false
end
Event.onFinish = function() print("脚本被卸载！") end