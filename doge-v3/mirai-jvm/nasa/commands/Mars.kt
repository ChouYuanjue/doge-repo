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

package tech.eritquearcus.nasaPlugin.commands

import com.google.gson.JsonObject
import net.mamoe.mirai.event.events.MessageEvent
import net.mamoe.mirai.message.data.buildForwardMessage
import tech.eritquearcus.nasaPlugin.*
import kotlin.random.Random

class Mars : CommandHandler {
    override suspend fun build(config: Config, data: List<String>, e: MessageEvent) {
        // commandName, date, [camera]
        if (data.size < 2 || data.size > 3) {
            errOut("参数数量不足或多余, 应该传入一个或2个参数(date, [cameraName]), 比如: MARS 2022-01-01 或 MARS 2022-01-01 FNAZ", e)
            return
        }
        val date = getDate(data[1]) ?: let {
            errOut("日期格式错误, 需要符合yyy-MM-DD 如 2022-01-01", e)
            return
        }
        val map = if (data.size == 3) {
            val possibleCameraName =
                listOf("FHAZ", "RHAZ", "MAST", "CHEMCAM", "MAHLI", "MARDI", "NAVCAM", "PANCAM", "MINITES")
            if (!possibleCameraName.contains(data[2])) {
                errOut(
                    "摄像机缩写名错误,可选缩写 " + possibleCameraName.joinToString(",") + " 对应含义见 https://api.nasa.gov/index.html#:~:text=named%20as%20follows%3A-,Rover%20Cameras,-Abbreviation",
                    e
                )
                return
            }
            mapOf("earth_date" to date, "camera" to data[2])
        } else mapOf("earth_date" to date)
        val re = request(config, "https://api.nasa.gov/mars-photos/api/v1/rovers/curiosity/photos", map)
        try {
            val arr = gson.fromJson(re, JsonObject::class.java).get("photos").asJsonArray
            val info = arr[Random.nextInt(0, arr.size())].asJsonObject
            val img = e.subject.uploadImage(getImage(info["img_src"].asString))
            val msg = buildForwardMessage(
                e.subject, CustomDisplayStrategy("Mars photo from ${info["rover"].asJsonObject["name"].asString}")
            ) {
                e.bot says img
                e.bot says """
                |拍摄火星车: ${info["rover"].asJsonObject["name"].asString}
                |拍摄时间: ${info["earth_date"].asString}
                |下载地址: ${info["img_src"].asString}
                |拍摄摄像头: ${info["camera"].asJsonObject["full_name"].asString}
                |编号: id(${info["id"]}) sol-${info["sol"]}}
            """.trimMargin()
            }
            e.subject.sendMessage(msg)
        } catch (exception: Exception) {
            errOut(exception.message ?: "", e)
            errOut("Nasa返回异常: $re", e)
        }
    }
}