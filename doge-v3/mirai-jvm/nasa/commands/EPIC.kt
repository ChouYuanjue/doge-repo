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

import com.google.gson.JsonArray
import net.mamoe.mirai.event.events.MessageEvent
import net.mamoe.mirai.message.data.buildForwardMessage
import tech.eritquearcus.nasaPlugin.*

class EPIC : CommandHandler {
    override suspend fun build(config: Config, data: List<String>, e: MessageEvent) {
        // commandName, naturalDate
        if (data.size != 2) {
            errOut("参数数量不足, 应该传入 Date, 如: EPIC 2022-01-01", e)
            return
        }
        val date = getDate(data[1]) ?: let {
            errOut("日期格式错误, 需要符合yyy-MM-DD 如 2022-01-01", e)
            return
        }
        val re = request(config, "https://epic.gsfc.nasa.gov/api/natural/date/$date", mapOf())
        try {
            val info = gson.fromJson(
                re, JsonArray::class.java
            )[0].asJsonObject
            val img = e.subject.uploadImage(
                getImage(
                    "https://epic.gsfc.nasa.gov/archive/natural/${
                        date.replace(
                            "-",
                            "/"
                        )
                    }/png/" + info["image"].asString + ".png"
                )
            )
            val msg = buildForwardMessage(e.subject, CustomDisplayStrategy("Epic image")) {
                e.bot says img
                e.bot says "介绍:" + info["caption"].asString
            }
            e.subject.sendMessage(msg)
        } catch (exception: Exception) {
            errOut(exception.message ?: "", e)
            errOut("Nasa返回异常: $re", e)
        }
    }
}