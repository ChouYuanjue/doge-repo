# 豆子 Doge 3.10.0 文档

请持续关注本文档，一切指令以文档为准。

以下文档中，用`<>`括起来的表示必须变量，`|`表示“或”，用`[]`括起来的表示可选变量。使用时均**不需要**带上这些符号。

# 简介
豆子 Doge依托于mirai框架， 采用协议为ANDROID_PHONE以及ANDROID_PAD。

功能主要分成两大部分，依托于mirai-console (JVM)的新功能以及依托于mirai-native的由旧版移植的旧功能。目前二者数量基本持平。

初版豆子诞生于2020年3月30日，依托于CQP. 此后四个月内断断续续地进行更新，在此过程中作者收到了许多人善意的帮助和支持，顶峰时期豆子有百余名好友，加入30多个群聊。2020年8月2日，经历腾讯第二次qbot大屠杀，元气大伤，CQP框架倒闭。随后尝试转移至mirai，效果极不理想，作者当即删库跑路，初版豆子就此结束了短暂的一生。

时隔两年，作者在数学吧闲聊时发现还有人记得豆子，大为感动，恰巧那时刚与丽琪的作者fyr进行过关于tex功能的交流，于是重新萌生了写bot的想法。2022年7月25日，作者开始重新写bot，发现两年的时间给qbot的生态造成了极大的变化，花了相当的时间适应。作者目前使用的是mirai-console-2.12.0，仍然存在部分问题。7.27日出现大崩溃事件，7.28重新配置完毕并进行大更新，豆子正式重生。

感谢所有曾提供帮助的人，同样感谢所有时隔两年仍然记得当初那个问题百出的豆子的人。特别感谢fyr和他的丽琪，没有他们两版豆子都不会出现。

友情链接：

mirai主仓库：[mamoe/mirai](https://github.com/mamoe/mirai)

丽琪使用说明：[使用说明](http://liqisese.top:800/help/)

# 更新日志
2022-09-18 更新了`/gen`和`/chart`功能块，修复了一些小问题

2022-09-11 更新了`/dream`, `/style`, `/toonify`功能块，增加了`/pic-url`和`/url-pic`功能

2022-09-04 更新了`/phil`功能块，添加了`/game nc`和`/math oeis`功能，更新了说明文档系统

2022-08-30 更新了`/meme`功能块，添加了`/bing`功能

2022-08-29 第八次大崩溃事件（tx风控）。暂时解决了问题

2022-08-29 更新了`/siku`功能块

2022-08-28 更新了`/genshin`功能块，封印了`/px kw`功能，更新并封印了`/se`功能块

2022-08-28 三号机复活。恢复全部功能

2022-08-18 第七次大崩溃事件（tx封号）。tx怎么还不しね

2022-08-18 bot转移到三号机

2022-08-17 第六次大崩溃事件（二号机永封）

2022-08-16 第五次大崩溃事件（tx冻结）

2022-08-11~2022-08-15 增加`/gan person`, `/gan chem`, `/amuse cp`, `/px kw`功能。增加`/yg`, `/gpt`, `/cotool`功能块。重写`/run`功能块。

2022-08-05 增加`/gan furry`和`/gan anime`功能

2022-08-04 增加`/chem`和`/perc`功能块，增加`/math system`功能

2022-08-03 增加`/insult`和`/fru`功能块

2022-08-02 bot转移至二号机，供私人使用。恢复全部功能

2022-07-31 第四次大崩溃事件（初号机永封）。由于封号影响，大部分功能失效，bot停运。感谢陪伴

2022-07-30 第三次大崩溃事件（tx封号）

2022-07-30 增加`/poem`功能块，增加`/ask`功能，重写`/run`功能块（但仍然不能用）

2022-07-29 第二次大崩溃事件（tx风控）

2022-07-28 恢复大部分旧版功能

2022-07-27 第一次大崩溃事件

2022-07-26 增添部分新功能

2022-07-25 开始配置bot。增添部分新功能

# 开发者

欢迎参与豆子的开发。请阅读mirai的开发文档：[mirai docs](https://docs.mirai.mamoe.net/). 豆子鼓励使用JVM或者mirai-api-http开发的功能，但不太建议使用mirai-native. 目前豆子之所以采用双协议就是为了防止mirai-native崩溃而导致整个bot的停运。

豆子的所有指令原则上都使用`/`开头，后面应该跟着功能的英文或缩写，如果有开发意愿请注意这点。

所有插件请尽量不要夹带私货并且在mcl2里在至少一个bot上成功运行，如果可以的话请连同源码、README和打包好的jar(JVM)或exe(api-http)一并发送给作者。以上是请求而不是要求，但仍然希望有意者自觉遵守。如果不方便调试，日后作者或许会再开一个mcl专门用来测试这类插件（mirai-api-http不必担心此问题）。

关于功能方面，我们不介意大小，倒不如说比起大功能我们更青睐小功能（当然是因为作者的服务器实在是太差啦）。任何一个你觉得有趣或有用的功能都可以pr。当然如果太小的话可以直接联系作者让作者写，但作者不能保证会完成你的请愿。

出于某些原因，作者可能一到两周才能调试一次bot，很可能不能及时回复或者干脆摆烂，非常抱歉。

如果看了以上这些不客气的要求仍然想参与开发，欢迎联系作者询问更多。让我们一起把豆子变得更好

豆子 Doge 项目地址：[doge-qbot/doge-repo](https://github.com/doge-qbot/doge-repo)
# 什么？你不会用？
```
/docs
```
查看使用说明。你的几乎所有问题都可以在这里解决。请认真且严格地遵照指令，不要再问什么诸如为什么`/tex`不能用的问题（因为指令是`/tex render`）。
```
/ask <问题内容>
```
如果你发现本文档无法解决你的问题，请通过该指令提问。问题会被提交给作者并在本文档末的FAQ中解答。

# 加群/加好友
由于之前的封号影响，为了保证豆子的账号安全，加群加好友不再自动通过。请与作者联系。

# 聊天
新版豆子已采用茉莉云api进行智能聊天。

# 运行代码 『/run』
已再次重写。每天调用总额度100次，如果足够受欢迎再考虑增加额度。如果还需要添加别的语言可以和作者联系。

使用说明：
```
/run <语言> <程序内容>
```
**注意**：语言之后一定要有空格！

目前可以使用的语言：
```
/run c
/run cpp
/run c#
/run py2
/run py3
/run haskell
/run java
/run js
/run kt
/run lua
/run php
/run perl
/run R
```
例子：
```
/run py3 print ('Hello, World!')
```
# 科学计算 『/wa』
此功能使用的是WolframAlpha api，一个月调用额度是2000，如果发现数次发送该指令都无回应很可能是额度已用完。

使用说明：
```
/wa <表达式>
```
例子：
```
/wa integrate x^2 sin^3 x dx
```
# LaTeX渲染 『/tex』
支持tikz,tikz-cd,xy-pic,mhchem宏,不支持tcolorbox,physics,calc,unicode宏；
支持`\def`,`\newcommand`,`\renewcommand`进行定义，不支持`\raise`,`\kern`进行微调

使用说明：

*渲染公式*
```
/tex render
<TeX代码>
```
例子：
```
/tex render
A_{m,n} = \begin{pmatrix} a_{1,1} & a_{1,2} & \cdots & a_{1,n} \\ a_{2,1} & a_{2,2} & \cdots & a_{2,n} \\ \vdots  & \vdots  & \ddots & \vdots  \\ a_{m,1} & a_{m,2} & \cdots & a_{m,n} \end{pmatrix}
```
但是目前有可能出现错误（主要是画交换图），如果渲染结果不正常且经检查确认没有使用不支持的宏，请采用以下解决方案：

*渲染URL编码公式*
```
/tex urender
<经URL编码后的TeX代码<>
```
例子：
```
/tex urender
%5Cxymatrix%7B%0A%20%20A%20%5Car%5Br%5D%5Ef%20%5Car%5Bd%5D_g%20&%0A%20%20B%20%5Car%5Bd%5D%5E%7Bg'%7D%20%5C%5C%0A%20%20D%20%5Car%5Br%5D_%7Bf'%7D%20&%0A%20%20C%0A%7D
```
**注意**：对空格符的编码请编成%20，不要编成+号。可使用该网站上的工具：https://www.matools.com/code-convert

*随机TeX公式图片*
```
/tex random
```
公式是从arXiv上爬取保存在本地的，数据库大约有十万张，可能会导致反应稍慢。这是把某次失败的机器学习的残留物拿来废物利用，不会对此功能进行变动。图片只能在电脑端正常查看。

# 四库全书 『/siku』
使用说明：

*查询古籍对应的ID*
```
/siku kw <关键词>
```
例子：
```
/siku kw 全唐诗
```
此时返回的格式形如：
```
ID:3842r >《御定全唐詩 第一冊》[清]康熙四十二年 
ID:3843h >《御定全唐詩 第二冊》[清]康熙四十二年 
ID:3844l >《御定全唐詩 第三冊》[清]康熙四十二年 
ID:3845i >《御定全唐詩 第四冊》[清]康熙四十二年 
ID:3846h >《御定全唐詩 第五冊》[清]康熙四十二年
```
前面为古籍ID，后面为名称。

*阅读指定页*
```
/siku read <ID> <页码>
```
会返回古籍对应页码的图片。页码请写成四位数格式，如1要写为0001。对于分册的古籍（如上），注意下一册的页码要从上一册的最后一页+1开始计数。

# 诗词 『/poem』
使用说明：
```
/poem <类型>
```
类型可填以下几项：
```
shuqing（抒情）

siji（四季）

shanshui（山水）

tianqi（天气）

renwu（人物）

shenghuo（生活）

jieri（节日）

dongwu（动物）

zhiwu（植物）

shiwu（食物）
```

# 约稿 『/yg』
AI通过文本生成图片。你可以尝试一些现实中不可能出现的场景，如An octopus fights with a tiger(章鱼和老虎搏斗)。由于训练用的中文数据库不够，**请使用英文**。由于这个功能十分受欢迎，作者将其由单线程改成多线程，但为了防止服务器崩溃，功能在同一个群内仍然需等待上一个任务结束后再进行下一次调用，否则只返回一个`@…`

使用说明：
```
/yg <内容>
```

# GPT-2生成文本 『/gpt』
GPT-2是由OpenAI研发的强大的语言模型。此功能可通过gpt-2续写文本，如新闻、小说等，可以起到以假乱真的效果。基于和约稿功能同样的原因，**请使用英文**。由于不是很吃内存，写了多线程，可以放心使用。

使用说明：
```
/gpt <内容>
```
例子：
```
/gpt In a shocking finding, scientist from Carnegie Mellon University discovered a herd of zombies living in a remote.
```

# 谷歌深梦 『/dream』
使用Google的DeepDream算法转化图像。详情见此：[DeepDream|TensorFlow Core](https://tensorflow.google.cn/tutorials/generative/deepdream). 因为训练强度不够所以效果一般。

使用说明：
```
/dream <图片>
```
空格可有可无

*随机DeepDream图片*
```
/dream random
```

# 风格迁移 『/style』
使用AI进行风格迁移

使用说明：
```
/style pic <图片1> <图片2>
```
pic后必须有空格，两张图片之间的空格可有可无。此指令是把后一张图片的风格迁移到前一张上。

```
/style url <图链1> <图链2>
```
针对部分手机发不出文字+两张图的问题。可以通过`/pic-url <图片>`指令获得图链。

# 人物迪士尼化 『/toonify』
检测图片中人像并转换成迪士尼画风。使用CNN实现

使用说明：
```
/toonify <图片>
```
空格可有可无

# 论文生成 『/gen』
如果你知道什么是Scigen和Mathgen，你就知道这是什么性质的东西了。

使用说明：

*生成数学论文(Mathgen)*
```
/gen math
```

*生成计科论文(仅摘要)*
```
/gen cs
```

*生成hep-ph论文(仅摘要)*
```
/gen hep-ph
```

# 文化人骂街 『/insult』
使用说明：

*引用莎士比亚的句子*
```
/insult sh
```
是古英语所以看着会很奇怪。

*生成莎士比亚风格的句子*
```
/insult gensh
```
同样是古英语。

*引用马丁路德的句子*
```
/insult lu
```

# 哲学语录 『/phil』
使用说明：

*随机哲学语录*
```
/phil idea
```

*随机哲学家*
```
/phil er
```

*关键词查询*
```
/phil kw <内容>
```

# 化学物质查询 『/chem』
这是为了平衡学术功能中只有数学而产生的功能块。作者不是学化学的因此并没有各大化学站点的通行证，很难写更复杂的功能。

使用说明：

*渲染结构式图片*
```
/chem img <结构简式|名称|SMILES>
```
这个结构简式比较考究，一般不能直接把高中学的写法按上去。比如查询乙烯得用H2C=CH2而不是CH2=CH2。具体规则自己摸索。所以这边建议用SMILES来表达结构或者直接查名字(必须是英文)。

例子：(桥苯环萘)
```
/chem img c1ccc(C2C3c4cc5ccccc5cc4C2c2cc4ccccc4cc23)cc1
```

*查询SMILES*
```
/chem smiles <结构简式|名称>
```
规则同上。如果返回404就是数据库里没有。

*查询名称及相关信息*
```
/chem names <结构简式|名称|SMILES>
```
规则同上。

*查询InChIKey*
```
/chem ick <结构简式|名称|SMILES>
```
如果你不知道InChIKey是什么那你也没必要用它，别问我。

*查询分子式*
```
/chem formula <结构简式|名称|SMILES>
```
存在意义不明（雾

# Chart.js生成图表 『/chart』
使用Chart.js生成图表。

Chart.js v2使用文档：[Charts-2.9.4](https://www.chartjs.org/docs/2.9.4/charts/)

Chart.js v3使用文档：[Charts-latest](https://www.chartjs.org/docs/latest/charts)

使用说明：

*调用Chart.js v2*
```
/chart <code>
```
例子：
```
/chart {
  type: 'line',
  data: {
    labels: ['January', 'February', 'March', 'April', 'May', 'June', 'July'],
    datasets: [{
      label: 'First dataset',
      backgroundColor: 'rgb(255, 99, 132)',
      borderColor: 'rgb(255, 99, 132)',
      data: [10, 30, 39, 20, 25, 34, -10],
      fill: false,
    }, {
      label: 'Second dataset',
      fill: false,
      backgroundColor: 'rgb(54, 162, 235)',
      borderColor: 'rgb(54, 162, 235)',
      data: [18, 33, 22, 19, 11, 39, 30],
    }]
  },
  options: {
    responsive: true,
    title: {
      display: true,
      text: 'Grid Line Settings'
    },
    scales: {
      yAxes: [{
        gridLines: {
          drawBorder: false,
          color: ['pink', 'red', 'orange', 'yellow', 'green', 'blue', 'indigo', 'purple']
        },
        min: 0,
        max: 100,
        ticks: {
          stepSize: 10
        }
      }]
    }
  }
}
```
![v2-sample](https://quickchart.io/chart?c=%7B%0A%20%20type%3A%20%27line%27%2C%0A%20%20data%3A%20%7B%0A%20%20%20%20labels%3A%20%5B%27January%27%2C%20%27February%27%2C%20%27March%27%2C%20%27April%27%2C%20%27May%27%2C%20%27June%27%2C%20%27July%27%5D%2C%0A%20%20%20%20datasets%3A%20%5B%7B%0A%20%20%20%20%20%20label%3A%20%27First%20dataset%27%2C%0A%20%20%20%20%20%20backgroundColor%3A%20%27rgb(255%2C%2099%2C%20132)%27%2C%0A%20%20%20%20%20%20borderColor%3A%20%27rgb(255%2C%2099%2C%20132)%27%2C%0A%20%20%20%20%20%20data%3A%20%5B10%2C%2030%2C%2039%2C%2020%2C%2025%2C%2034%2C%20-10%5D%2C%0A%20%20%20%20%20%20fill%3A%20false%2C%0A%20%20%20%20%7D%2C%20%7B%0A%20%20%20%20%20%20label%3A%20%27Second%20dataset%27%2C%0A%20%20%20%20%20%20fill%3A%20false%2C%0A%20%20%20%20%20%20backgroundColor%3A%20%27rgb(54%2C%20162%2C%20235)%27%2C%0A%20%20%20%20%20%20borderColor%3A%20%27rgb(54%2C%20162%2C%20235)%27%2C%0A%20%20%20%20%20%20data%3A%20%5B18%2C%2033%2C%2022%2C%2019%2C%2011%2C%2039%2C%2030%5D%2C%0A%20%20%20%20%7D%5D%0A%20%20%7D%2C%0A%20%20options%3A%20%7B%0A%20%20%20%20responsive%3A%20true%2C%0A%20%20%20%20title%3A%20%7B%0A%20%20%20%20%20%20display%3A%20true%2C%0A%20%20%20%20%20%20text%3A%20%27Grid%20Line%20Settings%27%0A%20%20%20%20%7D%2C%0A%20%20%20%20scales%3A%20%7B%0A%20%20%20%20%20%20yAxes%3A%20%5B%7B%0A%20%20%20%20%20%20%20%20gridLines%3A%20%7B%0A%20%20%20%20%20%20%20%20%20%20drawBorder%3A%20false%2C%0A%20%20%20%20%20%20%20%20%20%20color%3A%20%5B%27pink%27%2C%20%27red%27%2C%20%27orange%27%2C%20%27yellow%27%2C%20%27green%27%2C%20%27blue%27%2C%20%27indigo%27%2C%20%27purple%27%5D%0A%20%20%20%20%20%20%20%20%7D%2C%0A%20%20%20%20%20%20%20%20min%3A%200%2C%0A%20%20%20%20%20%20%20%20max%3A%20100%2C%0A%20%20%20%20%20%20%20%20ticks%3A%20%7B%0A%20%20%20%20%20%20%20%20%20%20stepSize%3A%2010%0A%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%7D%5D%0A%20%20%20%20%7D%0A%20%20%7D%0A%7D)

*调用Chart.js v3*
```
/chartv3 <code>
```
例子：
```
/chartv3 {
  type: 'line',
  data: {
    labels: ['Q1', 'Q2', 'Q3', 'Q4'],
    datasets: [{
      label: 'Data',
      data: [6.06, 82.2, -22.11, 21.53],
      lineTension: 0.4,
      borderColor: '#ff3333',
      backgroundColor: '#ffcccc',
      fill: {
        target: {
          value: 30,
        },
        above: 'transparent',
        below: '#ffcccc',
      }
    }]
  }
}
```
![v3-sample](https://quickchart.io/chart?v=3&c=%7B%0A%20%20type%3A%20%27line%27%2C%0A%20%20data%3A%20%7B%0A%20%20%20%20labels%3A%20%5B%27Q1%27%2C%20%27Q2%27%2C%20%27Q3%27%2C%20%27Q4%27%5D%2C%0A%20%20%20%20datasets%3A%20%5B%7B%0A%20%20%20%20%20%20label%3A%20%27Data%27%2C%0A%20%20%20%20%20%20data%3A%20%5B6.06%2C%2082.2%2C%20-22.11%2C%2021.53%5D%2C%0A%20%20%20%20%20%20lineTension%3A%200.4%2C%0A%20%20%20%20%20%20borderColor%3A%20%27%23ff3333%27%2C%0A%20%20%20%20%20%20backgroundColor%3A%20%27%23ffcccc%27%2C%0A%20%20%20%20%20%20fill%3A%20%7B%20%0A%20%0A%20%20%20%20%20%20%20%20target%3A%20%7B%0A%20%20%20%20%20%20%20%20%20%20value%3A%2030%2C%0A%20%20%20%20%20%20%20%20%7D%2C%0A%20%20%20%20%20%20%20%20above%3A%20%27transparent%27%2C%0A%20%20%20%20%20%20%20%20below%3A%20%27%23ffcccc%27%2C%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%7D%5D%0A%20%20%7D%0A%7D%0A)

# Perchance外部API 『/perc』
这是一次通过glitch实现JS交互的尝试。服务器上装不上JS所以只能这么做试试。当然功能本身和这些没有半点关系。Perchance是一个文本生成器网站，但没有提供api，作者通过glitch搭建了一个供调用。

Perchance网站：[Generators](https://perchance.org/generators) 可以在这里找你想要玩的生成器。

使用说明：
```
/perc <generatorID> [list]
```
第一次使用某生成器会反应较慢。其中generatorID是在生成器网址中`https://perchance.org/`之后的部分，比如`https://perchance.org/booknamer`的ID就是`booknamer`。list变量可有可无，默认是output，有哪些list请浏览你用的生成器的源代码。
当然你也可以直接使用以下提供的例子：

例子：

*生成诗歌*
```
/perc poemoracle
```
*生成莫名其妙的计算题*
```
/perc mathy
```
*文摘集*
```
/perc bja27rbxpg
```
*生成动物句子*
```
/perc animal-sentence
```
*生成架空历史*
```
/perc gen-history year
```

# 假俄语转换 『/fru』
顾名思义，是看起来像俄语但实际上并不是俄语的语言。可以拿来骗对俄语毫不了解的人。

使用说明：

*英语转假俄语*
```
/fru en <内容>
```
暂不支持大写字母。原理是直接将英语字母西里尔化。

*拼音转假俄语*
```
/fru py <内容>
```
请不要加音调符号。原理是用俄语模拟中文发音。这是作者习惯的转写，和标准转写略有不同。

*中文转假俄语*
```
/fru zh <内容>
```
原理是把中文转换成拼音后再使用上一条。

# 生成表情 『/rua』
mirai特色表情生成。一度成为mirai bot最常见的功能（雾

使用说明：
```
/rua [Key] <@某人>
```
也可以使用图片：
```
/rua [Key] <图片>
```
其中[Key]可不填，若不填则会随机生成。[Key]可填以下几项：

```
anyasuki ( 阿尼亚 喜欢 )
bite ( 啃 咬 )
breast ( 胸 凶 )
cast ( 丢 )
center_symmetry ( 中心对称 左上对称 )
coupon ( 陪睡 )
cover_face ( 挡 )
crawl ( 爬 )
decent_kiss ( 抱歉 )
distracted ( 注意力 )
dont_touch ( 不要靠近 )
down_symmetry ( 对称 下对称 上下对称 )
eat ( 吃 )
fencing ( 击剑  )
garbage ( 垃圾桶 垃圾 探头 )
hammer ( 锤 )
interview ( 采访 )
jiujiu ( 么么 )
keep_away ( 远离 )
kiss ( 亲 热吻 )
knock ( 敲 打 )
left_down_symmetry ( 中心对称 左下对称 )
leg ( 蹭 )
like ( 永远喜欢 )
loading ( 加载 加载中 )
make_friend ( 加好友 )
marry ( 结婚 )
nano ( 纳米科技 )
need ( 需要 )
osu
painter ( 画 )
pat ( 拍 )
perfect ( 完美 )
petpet ( 摸 摸头 )
play ( 玩 顶 )
police ( 警察 )
pound ( 捣 )
pr ( 舔屏 )
punch ( 打拳 )
record ( 唱片 )
right_down_symmetry ( 中心对称 右下对称 )
right_symmetry ( 对称 右对称 左右对称 )
right_up_symmetry ( 中心对称 右上对称 )
roll ( 滚 推 )
rub ( 舔 prpr )
safe_sense ( 安全感 )
suck ( 吸 )
support ( 精神支柱 )
symmetry ( 对称 左对称 左右对称 )
tear ( 撕 )
thinkwhat ( 想 )
throw ( 扔 )
thump ( 锤 )
tightly ( 黏 )
twist ( 抱 )
up_symmetry ( 对称 上对称 上下对称 )
wallpaper ( 壁纸 )
worship ( 膜拜 )
yoasobi ( 群青 )
```

例子：
```
/rua twist @豆子 Doge
```
**[已封印]** 戳一戳将有30%概率触发该功能。(由于协议更改，戳一戳不再触发）

# 表情包 『/meme』
使用说明：
```
/meme mc
```
发送可爱的Menhera-chan的表情包
```
/meme ch
```
小鹦鹉（小黄鸡）表情包
```
/meme wh
```
小白人表情包
```
/meme pg
```
企鹅表情包
```
/meme fu
```
很杂乱的滑稽表情

*另外谁有pusheen猫的表情合集，请速速与豆子联系*

# 原神抽卡 『/genshin』
此功能需要联系作者分群授权。调用此处的api模拟原神抽卡：[GardenHamster/GenshinPray](https://github.com/GardenHamster/GenshinPray)

使用说明：

*查看菜单*
```
/genshin menu
```
*抽卡功能*
```
/genshin 角色单抽[1-10]
```
1-10对应不同的卡池，可省略。下同
```
/genshin 角色十连[1-10]
```
```
/genshin 武器单抽
```
```
/genshin 武器十连
```
```
/genshin 常驻单抽
```
```
/genshin 常驻十连
```
```
/genshin 全角单抽
```
```
/genshin 全角十连
```
```
/genshin 全武单抽
```
```
/genshin 全武十连
```
# 零乱的娱乐功能 『/amuse』
使用说明：

*夸我/夸某人*
```
/amuse chp <me|@某人>
```
彩虹屁功能

*骂我/骂某人*
```
/amuse zuan <me|@某人>
```
对着指定的人口吐芬芳（也可用于抖M）

*毒我/毒某人*
```
/amuse du <me|@某人>
```
输出毒鸡汤

*随机生成乱码*
```
/amuse gar
```
实际上并不是完全随机。

*舔我/舔某人*
```
/amuse tian <me|@某人>
```
调用舔狗日记的接口，内容一定程度上引起不适

*生成cp文*
```
/amuse cp <人物1> <人物2>
```

# 编/解码工具 『/cotool』
使用说明：

*URL编码/解码*
```
/encode url <编码前内容>
```
```
/decode url <编码后内容>
```
*Unicode编码/解码*
```
/encode usc2 <编码前内容>
```
```
/decode usc2 <编码后内容>
```
*Hex编码/解码*
```
/encode hex <编码前内容>
```
```
/decode hex <编码后内容>
```
*Base64编码*
```
/encode base64 <编码前内容>
```
*文本加密/解密*
```
/encrypt <加密前内容> [密码]
```
```
/decrypt <加密后内容> [密码]
```
密码可有可无。
# 网络工具 『/netool』
使用说明：

*ping测试*
```
/ping <目标名称> [ping次数] [超时时间/ms]
```
例子：
```
/ping 127.0.0.1 10
```

*网页测试*
```
/web <URL链接> [编码]
```
例子：
```
/web https://baidu.com
```

*端口扫描*
```
/nmap <目标名称> [端口]
```
例子：
```
/nmap 127.0.0.1 8080
```

*查墙*
```
/gc <目标名称>
```

# 游戏功能 『/game』
一些游戏功能。

使用说明：

*24点*
```
/game 24p
```
发送指令查看规则。（需要作者授权使用。如需要请与作者联系）

允许四则运算 `+, -, *, /` 和位运算 `>>`(右移)，`<<`(左移)，`&`(与)，`^`(异或)，`|`(或)

**注意**：这里的`^`不是乘方运算！！！

关于如何计算位运算，可以使用即将提及的功能
```
/math calc <表达式>
```
关于什么是位运算，参见本文档末的FAQ.

*九子棋*
```
/game nc
```
发送指令查看详情。

**规则**：双方各自在棋盘上下9个棋子后，进入移动棋子阶段，直到某一方的三个棋子在棋盘上连成一条线时即可胜出。
# 数学相关 『/math』
使用说明：

*逻辑判断*
```
/math logic <逻辑表达式>
```
若逻辑正确返回真，否则返回假。
支持符号：
“或”/“||”, “且”/“&&”, “+”, “-”, “*”, “\”, “/”, “%”,“(”,“)”
“=”(值等), “==”(全等), “!=”, “!==”, “>”, “<”, “>=”, “<=”
“in”(包含), “!in”(不包含), “reg”(正则匹配), “!reg”(正则不包含)
例子：
```
/math logic 1!=3+4-5+2||3>4
```

*计算结果*
```
/math calc <表达式>
```
支持四则运算：加 +   减 -   乘 * ×   除 / ÷   括号 ()

支持其他数值运算：  求余 %   求整 \   求次方 ^   如：4%3=1  4\3=1 4^3=64

支持分布运算：符号,  如：4+3,×5,-7 相当于 ((4+3)×5)-7

支持四舍五入：符号@  x@y  表示：将x四舍五入到相对于个位的第y位。
y大于0，舍入到小数点后y位；y=0，舍入到整数；y小于0，舍入到小数点前|y|位(需要带上括号)。

支持位运算：  左位移 <<   右位移 >>   位或 or   位与 and   位异或 xor

例子：
```
/math calc 4+5,^3,/3,@2,xor1
```

*MathWorld*
```
/math mw <词条>
```
词条为英文，省略空格和`'`号，除介词和连词外开头大写（请严格按照要求，否则将无法查询到结果）如：Dyck's Theorem -> DycksTheorem, Lie algebra ->LieAlgebra, probability and statistics -> ProbabilityandStatistics

如果不知道是否词条存在可以通过以下命令查询：
```
/web https://mathworld.wolfram.com/search/?query=<词条>
```
例子：
```
/math mw Handle
```

*Encyclopedia of Math*
```
/math em <词条>
```
词条为英文，空格用符号`_`代替

例子：
```
/math em adjoint_module
```

*查询π*
```
/math pi <起点数位> <查询位数>
```
例子：
```
/math pi 0 100
```

*进制转换*
```
/math system <原数字> <原进制> <转化成的进制>
```
支持的进制：2，4，8，10，16，32，64

例子：
```
/math system 114514 10 2
```

*OEIS数列查询*
```
/math oeis <一部分数列|数列号>
```
数列号请以大写A开头

例子：
```
/math oeis 1,1,4,5,1,4
```
```
/math oeis A004861
```

# Pixiv功能 『/px』
使用说明：

*ID查询*
```
/px id <图片id>
```
如果是多张图片，查看第n张，请在id后加-n。不支持r18图片。

*作者查询*
```
/px user <用户id>[-页数]
```
例子：
```
/px user 54259522-2
```

*以图搜图*
```
/px tst <图片>
```
**注意**：一定要加上空格，否则无法识别。

*以图搜番*
```
/px tsf <图片>
```
旧版豆子最受欢迎的功能。接的是SauceNAO接口。使用限制是一天100次，30s内不超过4次，请慎用。

*СЭОТУ功能*
```
/px setu
```
大家喜闻乐见的功能（但是我是不会让你们用der!）。只有授权才可以使用，请与作者联系。

*搜索关键词*
```
/px kw <关键词>
```
**[已封印]** 出于未知的原因，搜出来图不少都很瑟。慎用。

# Jeff笑话生成 『/jeffjoke』
关于什么是Jeff笑话，参加本文档末FAQ.,

使用说明：

*生成关于自己的笑话*
```
/jeffjoke <mj|myjoke> [条数]
```
条数可不填，默认一条

*生成关于别人的笑话*
```
/jeffjoke <dj|diyjoke> <某人>  [条数]
```
例子：
```
/jeffjoke dj 豆子 3
```

# StyleGAN 『/gan』
使用StyleGAN生成图片，如果图片过于诡异请不要恐慌，它们不是真实存在的。关于什么是StyleGAN，参见文档末的FAQ。

使用说明：

*生成猫*
```
/gan cat
```

*生成画作*
```
/gan art
```

*生成马*
```
/gan horse
```

*生成二次元人像*
```
/gan waifu
```
有概率失败，可以多试几次（中间请间隔一段时间）

*生成动漫图片*
```
/gan anime
```
大多是全身像，人体会比较奇怪

*生成福瑞图*
```
/gan furry
```
效果还不错

*生成人像*
```
/gan person
```
由于训练集很大所以效果相当好。

*生成化学物质结构图*
```
/gan chem
```
# 圣训 『/yan』
记录群友的言行。无差别记录，如果需要制造某人的圣训录请与作者联系。作者必须也在要求该功能的群内，且需要征得被记录者的同意。

使用说明：
```
/yan-<QQID> [关键词]
```
理论上是这个指令，但可以要求作者使用其他的指令，比如“XX圣训”，“XX物语”等

*查看本群被记录者语录条数*
```
/yan length <QQID>
```
使用该命令需要作者授权。

*查看本群有哪些人已被记录*
```
/yan stars
```
使用该命令需要作者授权。

# 神秘功能 『/se』
**[已封印]** 这些功能在诞生之初即被封印，写的目的就是为了挑衅tx。（/se缩写自secret）

使用说明（hex）：
```
/se tu

//B4F3BCD2CFB2CEC5C0D6BCFBB5C4C9ACCDBCB9A6C4DC
```
```
/se ph <content>

//506F726E687562B9D8BCFCB4CACBD1CBF7B7FECEF1A3A8CEDED0E8B4FAC0EDA3ACBFC9D6B1BDD3B7C3CECAA3A9
```
```
/se jav <id code>

//B5BAB9FAD3B0CAD3B7ACBAC5B2E9D1AFA3A8BFC9D4DACFDFB2A5B7C5A3A9
```
```
/se aps

//CBE6BBFACDF8D5BEA1A3C0B4D4B4A3BA68747470733A2F2F616C6C706F726E73697465732E6E6574
```
```
/se bt <content>

//4254D6D6D7D3CBD1CBF7
```
# 其他功能 『/other』
这里是一些零碎的功能，一部分是初版豆子遗留的无法完全恢复的残件。

使用说明：

*图片转图链*
```
/pic-url <图片>
```
空格可有可无

*图链转图片*
```
/url-pic <图链>
```
只有经作者授权才能使用

*发送动漫大图*
```
/anime
```
原`/img`功能块。之前使用的api.computerfreaker.cf接口现在已全部失效。

*Bing每日壁纸*
```
/bing
```
*今日说法*
```
/law
```
随机发送一条宪法内容。原`/laws`功能块，现在只有宪法能调用。

*生成幻影坦克*
```
/mirage
```
关于什么是幻影坦克，请参见文末FAQ.

*说指定的话*
```
/echo <内容>
```
原`/cmd`功能块。出于安全考量，现在只留下这一个鸡肋的功能。

*查看bot版本*
```
/ver
```

# FAQ
**1.什么是位运算？**

位运算就是直接对整数在内存中的二进制位进行操作的运算。参见[位运算](https://www.runoob.com/w3cnote/bit-operation.html)

**2.什么是Jeff笑话？**

Jeff Dean是谷歌的工程师，大神级别。Jeff笑话是以事实为依据（bushi）来表明Jeff非凡的能力的笑话。参见[JeffDeanFacts](https://github.com/LRitzdorf/TheJeffDeanFacts)

**3.什么是StyleGAN？**

StyleGAN是NVIDIA继ProGAN之后提出的新的生成对抗网络，借鉴风格迁移，通过修改不同层级在不影响其他层级的前提下控制视觉特征。参见[NVlabs/StyleGAN](https://github.com/NVlabs/stylegan)

**4.什么是幻影坦克？**

指一种双层图，这种图片分为内外两层，在未点击的情况下是一张图片，点击打开后又是一张图片。

**5.为什么豆子没有xxx功能？**

你去pr就有了。

**6.豆子的所有功能都是自己写的吗？**

不是。一部分来自github。但可以保证有至少八成是自己写的。搬运的功能大多可以自己重写，但这不意味着我会这么做。

**7.为什么**`/tex render`**功能会出错？**

我也没发现我的代码哪里有错。目前提供`/tex urender`作为解决方案，可以解决一切问题。

**8.为什么不提供涩图？**

初版豆子曾被这样封号过。同样，有话说得好，“一个bot只要有了涩图功能，那它就会变得只有涩图功能”。

**9.作者是计科专业的吗？**

不是。要不然豆子会比现在好得多。

**10.作者是谁？**

好问题，作者是谁

**11.什么是GPT-2？**

一个强大的语言模型。见[OpenAI-Better Language Models](https://openai.com/blog/better-language-models/)

**12.豆子现在有多少功能？**

共`31`个功能块，`128`个功能，其中不包括bot管理专用功能。