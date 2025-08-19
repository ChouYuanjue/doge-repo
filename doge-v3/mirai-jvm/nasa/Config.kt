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

import tech.eritquearcus.nasaPlugin.commands.APOD
import tech.eritquearcus.nasaPlugin.commands.EPIC
import tech.eritquearcus.nasaPlugin.commands.Earth
import tech.eritquearcus.nasaPlugin.commands.Mars

data class Config(
    val apikey: String,
    val commandName: Map<String, String> = mapOf(),
    val commandStatus: Map<String, Boolean> = mapOf(),
    val enableFriend: Boolean = true,
    val enableGroup: Boolean = true,
    var errLogWay: Int = 0
)

enum class CommandType {
    APOD, Earth, EPIC, Mars
}

val commandTexts = mutableMapOf(
    CommandType.APOD to (APOD() to "#APOD"),
    CommandType.Earth to (Earth() to "#Earth"),
    CommandType.EPIC to (EPIC() to "#EPIC"),
    CommandType.Mars to (Mars() to "#Mars")
)

data class APODRe(
    val copyright: String,
    val date: String,
    val explanation: String,
    val hdurl: String,
    val media_type: String,
    val service_version: String,
    val title: String,
    val url: String
)

data class EarthRe(
    val date: String, val id: String, val resource: Resource, val service_version: String, val url: String
) {
    data class Resource(
        val dataset: String, val planet: String
    )
}