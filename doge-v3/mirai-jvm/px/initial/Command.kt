package com.hcyacg.initial
import net.mamoe.mirai.console.data.AutoSavePluginConfig
import net.mamoe.mirai.console.data.ValueDescription
import net.mamoe.mirai.console.data.ValueName
import net.mamoe.mirai.console.data.value

/**
 * 自定义触发命令
 */
object Command: AutoSavePluginConfig("Command") {
    @ValueName("getDetailOfId")
    @ValueDescription("根据id获得图片及其数据 /px sid 87984524")
    var getDetailOfId: String by value("/px id ")

    @ValueName("picToSearch")
    @ValueDescription("搜索图片 /px tst 图片")
    var picToSearch: String by value("/px tst")


    @ValueName("showRank")
    @ValueDescription("排行榜 rank-daily-页码 可选daily|weekly|monthly|rookie|original|male|female|daily_r18|weekly_r18|male_r18|female_r18|r18g")
    var showRank: String by value("/px rank ")

    @ValueName("findUserWorksById")
    @ValueDescription("获取作者所有的插画 user-87915-页码")
    var findUserWorksById: String by value("/px user ")

    @ValueName("searchInfoByPic")
    @ValueDescription("搜索番剧 /px tsf-图片")
    var searchInfoByPic: String by value("/px tsf")

    @ValueName("setu")
    @ValueDescription("/px setu 或者/px setu loli")
    var setu: String by value("/px setu")

    @ValueName("lolicon")
    @ValueDescription("Lolicon 详细看https://api.lolicon.app/#/setu?id=tag")
    var lolicon: String by value("/px loli ")

    @ValueName("tag")
    @ValueDescription("搜索标签排行榜 /px tag 萝莉-页码")
    var tag: String by value("/px tag ")

    @ValueName("detect")
    @ValueDescription("检测图片的涩情程度并打上标签")
    var detect: String by value("/px detect")

    @ValueName("help")
    @ValueDescription("帮助")
    var help: String by value("/px help")

    @ValueName("lowPoly")
    @ValueDescription("晶格化命令")
    var lowPoly: String by value("/px lp")

    @ValueName("warehouse")
    @ValueDescription("从指定库存发送图片")
    var warehouse:String by value("/px wh")
}