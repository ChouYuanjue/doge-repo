package juicesyo.github.ninechess

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import net.mamoe.mirai.console.plugin.jvm.JvmPluginDescription
import net.mamoe.mirai.console.plugin.jvm.KotlinPlugin
import net.mamoe.mirai.contact.Contact
import net.mamoe.mirai.contact.Contact.Companion.sendImage
import net.mamoe.mirai.contact.Group
import net.mamoe.mirai.event.events.GroupMessageEvent
import net.mamoe.mirai.event.globalEventChannel
import net.mamoe.mirai.message.data.Message
import net.mamoe.mirai.message.data.content
import net.mamoe.mirai.utils.info


object PluginMain : KotlinPlugin(
    JvmPluginDescription(
        id = "juicesyo.github.NineChess",
        name = "NineChess",
        version = "0.1.0"
    )
) {
    var next : Long? = -1
    var num = 0 //统计次数
    override fun onEnable() {
        logger.info { "Juice's Games loaded." }
        var matchList = arrayListOf<Long>()
        var ncState = arrayListOf<String>()
        var me = String()
        var you = String()

        suspend fun process(contact: Contact, group: Group, msg: Message) {
           if (contact.id == me.toLong() && next == me.toLong()) {
               next = you.toLong()
               group.sendImage(NineChess.Main(group, msg.contentToString(), 0, contact))
           }
           if (contact.id == you.toLong() && next == you.toLong()) {
               next = me.toLong()
               group.sendImage(NineChess.Main(group, msg.contentToString(), 1, contact))
           }
        }

        this.globalEventChannel().subscribeAlways<GroupMessageEvent> {
            var msg = message.content
            //this.group.sendImage(NineChess.main(message.content,group))
            //NineChess.inputStream.close()

           /* if (sender.id=="315294716".toLong()&&message.contentEquals("test")){
                this.group.sendMessage("NineChess:${NineChess.MyChess}\nYourChess:${NineChess.YourChess}\nAllChess:${NineChess.AllChess}\nnext:${next}")
            }*/


            if (message.contentEquals("/nc")) {
                this.group.sendMessage("command\n·/nc match---匹配\n·/nc matching [@群员]([QQ])---指定匹配\n·/nc rival---查看匹配列表\n·/nc exit---退出匹配")
            }
            if (message.contentEquals("/nc match")) {
                if (matchList.any { it == sender.id }) {
                    this.group.sendMessage("你已经在匹配中。")
                } else {
                    this.group.sendMessage("正在匹配对手...")
                    matchList.add(sender.id)
                    if (matchList.size == 2) {
                        next = sender.id //先手
                        me = matchList[1].toString()
                        you = matchList[0].toString()
                        this.group.sendMessage("匹配到${matchList[0]}")
                        this.group.sendMessage("开始对局。（先手：${sender.nameCard}）")
                        this.group.sendImage(NineChess.Main(group, null, -1,sender))
                        matchList.removeAll(matchList)

                        val scope = CoroutineScope(SupervisorJob())
                        val scopedChannel = globalEventChannel().parentScope(scope) // 将协程作用域 scope 附加到这个 EventChannel
                        scopedChannel.subscribeAlways<GroupMessageEvent> {
                            if (sender.id==me.toLong()&&message.contentToString()=="exit") {
                                group.sendMessage("end.")
                                group.sendMessage("$me give up.\n$you,you win.")
                                scope.cancel()
                                NineChess.Clean()
                            }
                            if (sender.id==you.toLong()&&message.contentToString()=="exit") {
                                group.sendMessage("end.")
                                group.sendMessage("$you give up.\n$me,you win.")
                                scope.cancel()
                                NineChess.Clean()
                            }
                            if (num>50){
                                group.sendMessage("more than 50 steps,it ends in a draw.")
                                scope.cancel()
                            }else{
                                if(num==0) {
                                    num+=1
                                }else {
                                    process(sender, group, message)
                                }
                            }
                            if (sender.id==me.toLong()) {
                                num+=1
                                if (NineChess.Straight_Line(0)) {
                                    group.sendMessage("end.")
                                    group.sendMessage("$senderName,you win.")
                                    scope.cancel()
                                    NineChess.Clean()
                                }
                            }
                            if (sender.id==you.toLong()) {
                                num+=1
                                if(NineChess.Straight_Line(1)) {
                                    group.sendMessage("end.")
                                    group.sendMessage("$senderName,you win.")
                                    NineChess.Clean()
                                    scope.cancel()
                                }
                            }
                        }// 启动监听, 监听器协程会作为 scope 的子任务
                    }
                }
            }
            if (message.content.startsWith("/nc matching")) {
                msg = msg.removePrefix("/nc matching").trim()
                if (msg.isEmpty()) {
                    this.group.sendMessage("参数不能为空。")
                } else {
                    try {
                        if (msg.startsWith("@")) {
                            msg = msg.replace("@", "")
                            //this.group.sendMessage("${senderName}（${sender.id}）向${msg}发出匹配请求，回复 /nc y 应战。")
                        }
                        if (sender.id != msg.toLong()) {
                            this.group.sendMessage("${senderName}（${sender.id}）向（${msg}）发出匹配请求，回复 /nc y 应战。")
                            ncState.add("${sender.id}-${msg}")
                        } else {
                            this.group.sendMessage("不能向自己发起匹配请求。")
                        }
                    } catch (e: Exception) {
                        this.group.sendMessage("参数错误。")
                        //MatchList.removeAt(MatchList.indexOf(sender.id))
                    }
                }
            }
            if (message.contentEquals("/nc rival")) {
                if (matchList.isEmpty()) {
                    group.sendMessage("暂无人匹配。")
                } else {
                    this.group.sendMessage(matchList.toString())
                }
            }
            if (message.contentEquals("/nc exit")) {
                if (matchList.any { it == sender.id }) {
                    matchList.removeIf { it == sender.id }
                    this.group.sendMessage("退出匹配。")
                } else {
                    this.group.sendMessage("你还未开始匹配。")
                }
            }

            if (message.contentEquals("/nc y")) {
                for (s in ncState) {
                    if (s.split("-")[1] == sender.id.toString()) { //-右边为对手，即被邀请者
                        me = s.split("-")[0]
                        you = s.split("-")[1]
                    }
                }
                if (you.isNotEmpty()) {
                    ncState.remove("$me-$you")
                    next = me.toLong() //先手
                    this.group.sendMessage("开始对局。")
                    this.group.sendImage(NineChess.Main(group, null, -1,sender))

                    val scope = CoroutineScope(SupervisorJob())
                    val scopedChannel = globalEventChannel().parentScope(scope) // 将协程作用域 scope 附加到这个 EventChannel
                    scopedChannel.subscribeAlways<GroupMessageEvent> {
                        if (sender.id==me.toLong()&&message.contentToString()=="exit") {
                            group.sendMessage("end.")
                            group.sendMessage("$me give up.\n$you,you win.")
                            scope.cancel()
                            NineChess.Clean()
                        }
                        if (sender.id==you.toLong()&&message.contentToString()=="exit") {
                            group.sendMessage("end.")
                            group.sendMessage("$you give up.\n$me,you win.")
                            scope.cancel()
                            NineChess.Clean()
                        }
                        if (num>50){
                            group.sendMessage("more than 50 steps,it ends in a draw.")
                            scope.cancel()
                        }else{
                            if(num==0) {
                                num+=1
                            }else {
                                process(sender, group, message)
                            }
                        }
                        if (sender.id==me.toLong()) {
                            num+=1
                            if (NineChess.Straight_Line(0)) {
                                group.sendMessage("end.")
                                group.sendMessage("$senderName,you win.")
                                scope.cancel()
                                NineChess.Clean()
                            }
                        }
                        if (sender.id==you.toLong()) {
                            num+=1
                            if(NineChess.Straight_Line(1)) {
                                group.sendMessage("end.")
                                group.sendMessage("$senderName,you win.")
                                NineChess.Clean()
                                scope.cancel()
                            }
                        }
                    } // 启动监听, 监听器协程会作为 scope 的子任务

                }else {
                    this.group.sendMessage("无人向你发起匹配请求。")
                }
                /*
                if (NineChess.END != 1) {
                    this.group.sendMessage(next + "超时，自动判断为失败。")
                } else {
                    group.sendMessage("")
                }
                 */
            }
        }
    }
}
        /*
        this.globalEventChannel().subscribeAlways<FriendMessageEvent> {
            this.sender.sendImage(NineChess.main(message.content,sender))
            //NineChess.inputStream.close()
        }
         */