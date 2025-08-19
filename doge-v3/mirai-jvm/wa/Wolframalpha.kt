package bot.query.wolframalpha.whiter

import io.ktor.client.*
import io.ktor.client.engine.okhttp.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.utils.io.jvm.javaio.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import net.mamoe.mirai.console.command.*
import net.mamoe.mirai.console.data.AutoSavePluginConfig
import net.mamoe.mirai.console.data.ValueDescription
import net.mamoe.mirai.console.data.value
import net.mamoe.mirai.console.plugin.jvm.JvmPluginDescription
import net.mamoe.mirai.console.plugin.jvm.KotlinPlugin
import net.mamoe.mirai.contact.Contact
import net.mamoe.mirai.event.events.BotEvent
import net.mamoe.mirai.event.events.FriendMessageEvent
import net.mamoe.mirai.event.events.GroupMessageEvent
import net.mamoe.mirai.event.events.MessageEvent
import net.mamoe.mirai.event.globalEventChannel
import net.mamoe.mirai.message.data.*
import net.mamoe.mirai.utils.ExternalResource.Companion.uploadAsImage
import net.mamoe.mirai.utils.info
import org.json.JSONArray
import org.json.JSONObject
import java.io.InputStream
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.Charset

const val appIDSite = "https://developer.wolframalpha.com/portal/myapps/index.html"

object Wolframalpha : KotlinPlugin(
    JvmPluginDescription(
        id = "bot.query.wolframalpha.whiter",
        version = "1.5"
    )
) {
    private lateinit var appid: String
    lateinit var errorMsg: String
    private lateinit var slice: String
    private lateinit var separationLine: String
    private val client by lazy {
        HttpClient(OkHttp)
    }
    private var requestByCustom = false

    private fun loadConfig() {
        Config.reload()
        appid = Config.appid
        if (appid.isEmpty()) throw Exception("your appid can not be empty! " +
                "follow link $appIDSite to get a valid appid " +
                "then set property `appid` in file $configFolderPath/config.yml")
        slice = if (Config.prefix == "") "''" else Config.prefix
        errorMsg = if (Config.error_msg == "") "wolfram|alpha抽风啦, 管你看不看懂, 输出就完事啦: {{json}}" else Config.error_msg
        separationLine = when (Config.separation_line) {
            "" -> "\n---------"
            "empty" -> ""
            else -> Config.separation_line
        }
    }

    override fun onEnable() {
        logger.info { "WolframAlpha Plugin loaded" }
        loadConfig()

        CommandManager.registerCommand(object : SimpleCommand(this, "wolfram", description = "发送 wolfram 查询") {
            @Handler
            suspend fun CommandSender.onCommand(message: String) {
                sendMessage(query(message, subject))
            }
        })
        CommandManager.registerCommand(object : SimpleCommand(this, "wolfram-reload", description = "重载 wolfram 配置") {
            @Handler
            suspend fun CommandSender.onCommand() {
                loadConfig()
                sendMessage("OK")
            }
        })

        requestByCustom = runCatching {
            runBlocking {
                logger.info("checking available")
                client.get("https://www.wolframalpha.com/")
            }
        }.apply {
            onFailure {
                logger.error(it)
                logger.error("client is not available, use default instead.")
            }
        }.isFailure

        logger.info { "isClientFailToInit: $requestByCustom" }

        val be = globalEventChannel().filter { it is BotEvent }

        val handle: suspend MessageEvent.() -> Unit = {
            if (message.content.startsWith(slice)) {
                val messages = query(
                    message.content.slice(slice.length until message.content.length),
                    subject,
                    !Config.isForward
                )
                subject.sendMessage(if (Config.isForward) {
                    buildForwardMessage {
                        for (item in messages) bot.says(item)
                    }
                } else messages)
            }
        }

        be.subscribeAlways<GroupMessageEvent> {
            handle()
        }

        be.subscribeAlways<FriendMessageEvent> {
            handle()
        }
    }

    /**
     * httpGet请求
     * @param url 链接
     * @return 返回的字符串
     */
    private fun doGetWithStream(url: String): InputStream = (URL(url).openConnection() as HttpURLConnection).apply {
        requestMethod = "GET"
        setRequestProperty("Content-Type", "application/json; utf-8")
        setRequestProperty("Accept", "application/json")
        connect()
    }.inputStream

    private fun doGet(url: String) = InputStreamReader(doGetWithStream(url), Charset.defaultCharset()).readText()

    /**
     * 进行wolfram|α查询
     * @param str 查询字符串
     * @param subject 发送对象
     * @param needSeparationLine 是否需要分割线
     * @return 消息链，总是返回非空消息
     */
    suspend fun query(str: String, subject: Contact?, needSeparationLine: Boolean = true): MessageChain {
        val enterLine = if (needSeparationLine) "\n" else ""
        val query = withContext(Dispatchers.IO) {
            URLEncoder.encode(str, "utf-8")
        }

        val url = "https://api.wolframalpha.com/v2/query?appid=$appid&input=$query&output=json"
        val json = JSONObject(if (requestByCustom) doGet(url) else
            client.get(url).bodyAsText()
        ).getJSONObject("queryresult")
        var c = 0

        return buildMessageChain {
            if (json.getBoolean("success")) {
                val pods = json.getJSONArray("pods")
                // 兼容 android
                pods.foreach {
                    val title = it["title"].toString().trim()
                    logger.info("\n## $title:\n")
                    +(if (c++ == 0) "# $title: $enterLine" else "$enterLine# $title: $enterLine")

                    withContext(Dispatchers.IO) {
                        for (i in 0 until it["numsubpods"] as Int) {
                            val item = it.getJSONArray("subpods").getJSONObject(i)
                            val imgSrc = item.getJSONObject("img").getString("src")
                            subject?.let { sub ->
                                +(if (requestByCustom) URL(imgSrc).openStream() else client.get(imgSrc).bodyAsChannel().toInputStream()).use { stream ->
                                    stream.uploadAsImage(sub)
                                }
                            } ?: run {
                                +imgSrc
                            }
                            logger.info("![]($imgSrc)")
                        }
                    }

                    if (needSeparationLine) {
                        +separationLine
                        logger.info("\n---------\n")
                    }
                }

            } else if (json.get("error") is Boolean && !json.getBoolean("error")) {
                if (json.has("didyoumeans")) {
                    if (json["didyoumeans"] is JSONObject) {
                        val dum = json.getJSONObject("didyoumeans")
                        +("wolfram|alpha提供的api搜索不到结果, 基于输入值$str, 猜测您" +
//                        "有${dum.getFloat("score") * 100}%的概率" +
                                "可能是想查找: ${dum.getString("val")}")
                        logger.info("> $dum")
                    } else if (json["didyoumeans"] is JSONArray) {
                        val dums = json.getJSONArray("didyoumeans")
                        +("wolfram|alpha提供的api搜索不到结果, 基于输入值$str, 猜测您" +
//                        "有${dum.getFloat("score") * 100}%的概率" +
                                "可能是想查找: \n")
                        dums.foreachIndexed { it, index ->
                            +("${index + 1}. " + it.get("val") + "\n")
                        }
                        logger.info("> $dums")
                    } else  {
                        // re
                        +json["didyoumeans"].toString()
                    }
                }

                if (json.has("tips")) {
                    val tips = json.getJSONObject("tips").getString("text")
                    +tips
                    logger.info("> $tips")
                }

                if (json.has("languagemsg")) {
                    if (json["languagemsg"] is JSONObject) {
                        for (i in json.getJSONObject("languagemsg").keys()) {
                            +json.getJSONObject("languagemsg").get(i).toString()
                        }
                    } else {
                        +json["languagemsg"].toString()
                    }
                }
            } else {
                if (json["error"] is JSONObject) {
                    for (i in json.getJSONObject("error").keys()) {
                        val errmsg = json.getJSONObject("error").get(i)
                        +"$i: $errmsg; \n"
                    }
                    logger.error(json["error"].toString())
                } else if (json["error"] is JSONArray) {
                    json.getJSONArray("error").foreach {
                        +(it.toString() + "\n")
                    }
                    logger.error(json["error"].toString())
                } else {
                    +("error: " + json["error"].toString())
                    logger.error(json["error"].toString())
                }

                logger.info("# error")
            }

            if (isEmpty()) {
                logger.error("message is empty! source: $json")
                +errorMsg.replace("{{json}}", json.toString())
            } else {
                // wolframalpha给出的中国地图是错误的
                if (str == "中国" || str == "中华人民共和国" ||
                    str == "台湾" || str == "台北" ||
                    str == "中国台湾" || str == "中国台北" ||
                    str == "藏南" || str == "zangnan" ||
                    str.equals("China", true) ||
                    str.equals("the People's Republic of China", true) ||
                    str.equals("PRC", true) ||
                    str.equals("taiwan", true) ||
                    str.equals("taipei", true) ||
                    str.equals("chinese taipei", true) ||
                    str.equals("taipei city", true) ||
                    str.equals("People's Republic of China", true)
                ) +"\n注: 以上的地图是错误的, 台湾和藏南是中国领土的一部分"
            }
        }
    }
}

inline fun JSONArray.foreach(action: (JSONObject) -> Unit) {
    for (i in 0 until this.length()) {
        action(this[i] as JSONObject)
    }
}

inline fun JSONArray.foreachIndexed(action: (JSONObject, Int) -> Unit) {
    for (i in 0 until this.length()) {
        action(this[i] as JSONObject, i)
    }
}

object Config : AutoSavePluginConfig("config") {
    @ValueDescription("wolfram|alpha 的 appid, 前往 $appIDSite 获得")
    val appid: String by value()
    @ValueDescription("触发前缀, 为空时是两个单引号")
    val prefix: String by value()
    @ValueDescription("当发生错误时的提示信息")
    val error_msg: String by value()
    @ValueDescription("图片与文本的分割线, 为空时是 ---------, 填 empty 时为空白字符")
    val separation_line: String by value()
    @ValueDescription("是否构建转发消息")
    val isForward by value(false)
}