/*
 * Copyright (c) 2020 - 2022. Eritque arcus and contributors.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or any later version(in your opinion).
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 */

package tech.eritquearcus.nasaPlugin

import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import net.mamoe.mirai.event.events.MessageEvent
import net.mamoe.mirai.message.data.ForwardMessage
import net.mamoe.mirai.message.data.RawForwardMessage
import net.mamoe.mirai.utils.ExternalResource
import net.mamoe.mirai.utils.ExternalResource.Companion.toExternalResource
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.net.URLEncoder
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.text.ParseException
import java.text.SimpleDateFormat

val gson = Gson()
fun String.utf8(): String = URLEncoder.encode(this, "UTF-8")

fun request(config: Config, url: String, p: Map<String, String>): String {
    val urlParams =
        p.map { (k, v) -> "${(k.utf8())}=${v.utf8()}" }.joinToString("&") + "&api_key=${config.apikey.utf8()}"
    val request = HttpClient.newBuilder().build().send(
        HttpRequest.newBuilder().uri(URI.create("${url.removeSuffix("?")}?${urlParams.removePrefix("&")}")).build(),
        HttpResponse.BodyHandlers.ofString()
    )
    if (request.statusCode() != 200) throw IllegalStateException("Nasa返回错误 ${request.statusCode()}, ${request.body()}")
    return request.body()
}

inline fun <reified T> request(config: Config, url: String, p: Map<String, String>): T =
    gson.fromJson(request(config, url, p), T::class.java)

fun getDate(dateStr: String): String? {
    val array = dateStr.split("-")
    if (array.size != 3) return null
    val date =
        array[0] + "-" + (if (array[1].length == 1) "0" else "") + array[1] + "-" + (if (array[2].length == 1) "0" else "") + array[2]
    try {
        SimpleDateFormat("yyyy-MM-dd").parse(date)
    } catch (_: ParseException) {
        return null
    }
    return date
}

suspend fun getImage(url: String): ExternalResource = withContext(Dispatchers.IO) {
    URL(url).openConnection().apply {
        (this as HttpURLConnection).requestMethod = "GET"
        this.setRequestProperty(
            "User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"
        )
        this.connect()
    }.getInputStream()
}.toExternalResource().toAutoCloseable()

interface CommandHandler {
    suspend fun build(config: Config, data: List<String>, e: MessageEvent)
}

class CustomDisplayStrategy(private val title: String) : ForwardMessage.DisplayStrategy {
    override fun generateTitle(forward: RawForwardMessage): String {
        return title
    }
}